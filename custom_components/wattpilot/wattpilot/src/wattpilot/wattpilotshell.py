import cmd
import json
import logging
import math
import os
import paho.mqtt.client as mqtt
import re
import sys
import wattpilot
import yaml
import pkgutil

from importlib.metadata import version
from time import sleep
from threading import Event
from types import SimpleNamespace

_LOGGER = logging.getLogger(__name__)


#### Utility Functions ####

def utils_add_to_dict_unique(d, k, v):
    if k in d:
        _LOGGER.warning(
            f"About to add duplicate key {k} to dictionary - skipping!")
    else:
        d[k] = v
    return d


def utils_wait_timeout(fn, timeout):
    """Generic timeout waiter"""
    t = 0
    within_timeout = True
    while not fn() and t < timeout:
        sleep(1)
        t += 1
    if t >= timeout:
        within_timeout = False
    return within_timeout


class JSONNamespaceEncoder(json.JSONEncoder):
    # See https://gist.github.com/jdthorpe/313cafc6bdaedfbc7d8c32fcef799fbf
    def default(self, obj):
        if isinstance(obj, SimpleNamespace):
            return obj.__dict__
        return super(JSONNamespaceEncoder, self).default(obj)


def utils_value2json(value):
    return json.dumps(value, cls=JSONNamespaceEncoder)


#### Wattpilot Functions ####

def wp_read_apidef():
    global WATTPILOT_SPLIT_PROPERTIES

    api_definition = pkgutil.get_data(__name__, "ressources/wattpilot.yaml")
    wpdef = {
        "config": {},
        "messages": {},
        "properties:": {},
        "splitProperties": [],
    }
    try:
        wpdef["config"] = yaml.safe_load(api_definition)
        wpdef["messages"] = dict(zip(
            [x["key"] for x in wpdef["config"]["messages"]],
            [x for x in wpdef["config"]["messages"]],
        ))
        wpdef["properties"] = {}
        for p in wpdef["config"]["properties"]:
            wpdef["properties"] = utils_add_to_dict_unique(
                wpdef["properties"], p["key"], p)
            if "childProps" in p and WATTPILOT_SPLIT_PROPERTIES:
                for cp in p["childProps"]:
                    cp = {
                        # Defaults for split properties:
                        "description": f"This is a child property of '{p['key']}'. See its description for more information.",
                        "category": p["category"] if "category" in p else "",
                        "jsonType": p["itemType"] if "itemType" in p else "",
                    } | cp | {
                        # Overrides for split properties:
                        "parentProperty": p["key"],
                        "rw": "R",  # NOTE: Split properties currently can only be read
                    }
                    _LOGGER.debug(f"Adding child property {cp['key']}: {cp}")
                    wpdef["properties"] = utils_add_to_dict_unique(
                        wpdef["properties"], cp["key"], cp)
                    wpdef["splitProperties"].append(cp["key"])
        _LOGGER.debug(
            f"Resulting properties config:\n{utils_value2json(wpdef['properties'])}")
    except yaml.YAMLError as exc:
        _LOGGER.fatal(exc)
    return wpdef


def wp_initialize(host, password):
    global wp
    # Connect to Wattpilot:
    wp = wattpilot.Wattpilot(host, password)
    wp.connect()
    # Wait for connection and initialization:
    utils_wait_timeout(lambda: wp.connected, WATTPILOT_CONNECT_TIMEOUT) or exit(
        "ERROR: Timeout while connecting to Wattpilot!")
    utils_wait_timeout(lambda: wp.allPropsInitialized, WATTPILOT_INIT_TIMEOUT) or exit(
        "ERROR: Timeout while waiting for property initialization!")
    return wp


def wp_get_child_prop_value(cp):
    global wpdef
    cpd = wpdef["properties"][cp]
    if "parentProperty" not in cpd:
        _LOGGER.warning(
            f"Child property '{cpd['key']}' is not linked to a parent property: {cpd}")
        return None
    ppd = wpdef["properties"][cpd["parentProperty"]]
    parent_value = wp.allProps[ppd["key"]]
    value = None
    if ppd["jsonType"] == "array":
        value = parent_value[int(cpd["valueRef"])] if int(
            cpd["valueRef"]) < len(parent_value) else None
        _LOGGER.debug(f"  -> got array value {value}")
    elif ppd["jsonType"] == "object":
        if parent_value == None:
            value = None
            _LOGGER.debug(f"  -> parent value is None, so child as well")
        elif isinstance(parent_value, SimpleNamespace) and cpd["valueRef"] in parent_value.__dict__:
            value = parent_value.__dict__[cpd["valueRef"]]
            _LOGGER.debug(f"  -> got object value {value}")
        elif cpd["valueRef"] in parent_value:
            value = parent_value[cpd["valueRef"]]
            _LOGGER.debug(f"  -> got object value {value}")
        else:
            _LOGGER.warning(
                f"Unable to map child property {cpd['key']}: type={type(parent_value)}, value={utils_value2json(parent_value)}")
    else:
        _LOGGER.warning(f"Property {ppd['key']} cannot be split!")
    return value


def wp_get_all_props(available_only=True):
    global WATTPILOT_SPLIT_PROPERTIES
    global wp
    global wpdef
    if available_only:
        props = {k: v for k, v in wp.allProps.items()}
        if WATTPILOT_SPLIT_PROPERTIES:
            for cp_key in wpdef["splitProperties"]:
                props[cp_key] = wp_get_child_prop_value(cp_key)
    else:
        props = {k: (wp.allProps[k] if k in wp.allProps else None)
                 for k in wpdef["properties"].keys()}
    return props


#### Shell Functions ####

class WattpilotShell(cmd.Cmd):
    intro = f"Welcome to the Wattpilot Shell {version('wattpilot')}.   Type help or ? to list commands.\n"
    prompt = 'wattpilot> '
    file = None
    watching_messages = []
    watching_properties = []

    def postloop(self) -> None:
        print()
        return super().postloop()

    def emptyline(self) -> bool:
        return False

    def _complete_list(self, clist, text):
        return [x for x in clist if x.startswith(text)]

    def _complete_message(self, text, sender=None):
        global wpdef
        return [md["key"] for md in wpdef["messages"].values() if (not sender or md["sender"] == sender) and md["key"].startswith(text)]

    def _complete_propname(self, text, rw=False, available_only=True):
        global wpdef
        return [k for k in wp_get_all_props(available_only).keys() if (not rw or ("rw" in wpdef["properties"][k] and wpdef["properties"][k]["rw"] == "R/W")) and k.startswith(text)]

    def _complete_values(self, text, line):
        global wpdef
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_propname(text, rw=False, available_only=True) + ['<propRegex>']
        elif len(token) == 3 and text in wpdef["properties"]:
            return ['<value>', '<valueRegex>']
        return []

    def do_EOF(self, arg: str) -> bool | None:
        """Exit the shell"""
        return True

    def do_connect(self, arg: str) -> bool | None:
        """Connect to Wattpilot (using WATTPILOT_* env variables)
Usage: connect"""
        global WATTPILOT_HOST
        global WATTPILOT_PASSWORD
        global wp
        wp = wp_initialize(WATTPILOT_HOST, WATTPILOT_PASSWORD)

    def do_exit(self, arg: str) -> bool | None:
        """Exit the shell
Usage: exit"""
        return True

    def do_get(self, arg: str) -> bool | None:
        """Get a property value
Usage: get <propName>"""
        global wp
        global wpdef
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 1 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
        elif args[0] in wp.allProps:
            pd = wpdef["properties"][args[0]]
            print(mqtt_get_encoded_property(pd, wp.allProps[args[0]]))
        elif args[0] in wpdef["splitProperties"]:
            pd = wpdef["properties"][args[0]]
            print(mqtt_get_encoded_property(
                pd, wp_get_child_prop_value(pd["key"])))
        else:
            print(f"ERROR: Unknown property: {args[0]}")

    def complete_get(self, text, line, begidx, endidx):
        return self._complete_propname(text, rw=False, available_only=True)

    def do_ha(self, arg: str) -> bool | None:
        """Control Home Assistant discovery (+MQTT client)
Usage: ha <enable|disable|discover|properties|start|status|stop|undiscover> [args...]

Home Assistant commands:
  enable <propName>
    Enable a discovered entity representing the property <propName>
    NOTE: Re-enabling of disabled entities may still be broken in HA and require a restart of HA.
  disable <propName>
    Disable a discovered entity representing the property <propName>
  discover <propName>
    Let HA discover an entity representing the property <propName>
  properties
    List properties activated for HA discovery
  start
    Start HA MQTT discovery (using HA_* env variables)
  status
    Status of HA MQTT discovery
  stop
    Stop HA MQTT discovery
  undiscover <propName>
    Let HA remove a discovered entity representing the property <propName>
    NOTE: Removing of disabled entities may still be broken in HA and require a restart of HA.
"""
        global HA_ENABLED
        global HA_PROPERTIES
        global mqtt_client
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 1 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
            return
        if args[0] == "properties":
            print(
                f"List of properties activated for discovery: {HA_PROPERTIES}")
        elif args[0] == "start":
            HA_ENABLED = 'true'
            mqtt_client = ha_setup(wp)
        elif args[0] == "stop":
            ha_stop(mqtt_client)
            HA_ENABLED = 'false'
        elif args[0] == "status":
            print(
                f"HA discovery is {'enabled' if HA_ENABLED == 'true' else 'disabled'}.")
        elif len(args) > 1 and args[0] in ['enable', 'disable', 'discover', 'undiscover']:
            self._ha_prop_cmds(args[0], args[1])
        else:
            print(f"ERROR: Unsupported argument: {args[0]}")

    def _ha_prop_cmds(self, cmd, prop_name):
        global HA_PROPERTIES
        global MQTT_PROPERTIES
        global mqtt_client
        global wp
        global wpdef
        if prop_name not in wpdef["properties"]:
            print(f"ERROR: Unknown property '{prop_name}!")
        elif cmd == "enable":
            if prop_name not in MQTT_PROPERTIES:
                MQTT_PROPERTIES.append(prop_name)
            ha_discover_property(
                wp, mqtt_client, wpdef["properties"][prop_name], disable_discovery=False, force_enablement=True)
        elif cmd == "disable":
            if prop_name in MQTT_PROPERTIES:
                MQTT_PROPERTIES.remove(prop_name)
            ha_discover_property(
                wp, mqtt_client, wpdef["properties"][prop_name], disable_discovery=False, force_enablement=False)
        elif cmd == "discover":
            if prop_name not in HA_PROPERTIES:
                HA_PROPERTIES.append(prop_name)
            if prop_name not in MQTT_PROPERTIES:
                MQTT_PROPERTIES.append(prop_name)
            ha_discover_property(
                wp, mqtt_client, wpdef["properties"][prop_name], disable_discovery=False, force_enablement=True)
        elif cmd == "undiscover":
            if prop_name in HA_PROPERTIES:
                HA_PROPERTIES.remove(prop_name)
            if prop_name in MQTT_PROPERTIES:
                MQTT_PROPERTIES.remove(prop_name)
            ha_discover_property(
                wp, mqtt_client, wpdef["properties"][prop_name], disable_discovery=True, force_enablement=False)

    def complete_ha(self, text, line, begidx, endidx):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_list(['enable', 'disable', 'discover', 'properties', 'start', 'status', 'stop', 'undiscover'], text)
        elif len(token) == 3 and token[1] == 'discover':
            return self._complete_list([p for p in self._complete_propname(text, available_only=True) if p not in HA_PROPERTIES], text)
        elif len(token) == 3 and token[1] in ['enable', 'disable', 'undiscover']:
            return self._complete_list(HA_PROPERTIES, text)
        return []

    def do_info(self, arg: str) -> bool | None:
        """Print device infos
Usage: info"""
        global wp
        if not self._ensure_connected():
            return
        print(wp)

    def do_mqtt(self, arg: str) -> bool | None:
        """Control the MQTT bridge
Usage: mqtt <publish|start|status|stop|unpublish> [args...]

MQTT commands:
  properties
    List properties activated for MQTT publishing
  publish <messages|properties>
    Enable publishing of messages or properties
  publish <message> <msgType>
    Enable publishing of a certain message type
  publish <property> <propName>
    Enable publishing of a certain property
  start
    Start the MQTT bridge (using MQTT_* env variables)
  status
    Status of the MQTT bridge
  stop
    Stop the MQTT bridge
  unpublish <messages|properties>
    Disable publishing of messages or properties
  unpublish <message> <msgType>
    Disable publishing of a certain message type
  unpublish <property> <propName>
    Disable publishing of a certain property
"""
        global MQTT_ENABLED
        global mqtt_client
        global wp
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 1 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
            return
        if args[0] == "properties":
            print(
                f"List of properties activated for MQTT publishing: {MQTT_PROPERTIES}")
        elif args[0] == "start":
            MQTT_ENABLED = 'true'
            mqtt_client = mqtt_setup(wp)
        elif args[0] == "stop":
            mqtt_stop(mqtt_client)
            MQTT_ENABLED = 'false'
        elif args[0] == "status":
            print(
                f"MQTT client is {'enabled' if MQTT_ENABLED == 'true' else 'disabled'}.")
        elif len(args) > 1 and args[0] in ['publish', 'unpublish']:
            self._mqtt_prop_cmds(args[0], args[1])
        else:
            print(f"ERROR: Unsupported argument: {args[0]}")

    def _mqtt_prop_cmds(self, cmd, prop_name):
        global MQTT_PROPERTIES
        global mqtt_client
        global wp
        global wpdef
        if prop_name not in wpdef["properties"]:
            print(f"ERROR: Undefined property '{prop_name}'!")
        elif cmd == "publish" and prop_name not in MQTT_PROPERTIES:
            MQTT_PROPERTIES.append(prop_name)
        elif cmd == "unpublish" and prop_name in MQTT_PROPERTIES:
            MQTT_PROPERTIES.remove(prop_name)

    def complete_mqtt(self, text, line, begidx, endidx):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_list(['properties', 'publish', 'start', 'status', 'stop', 'unpublish'], text)
        elif len(token) == 3 and token[1] == 'publish':
            return self._complete_list([p for p in self._complete_propname(text, available_only=True) if p not in MQTT_PROPERTIES], text)
        elif len(token) == 3 and token[1] == 'unpublish':
            return self._complete_list(MQTT_PROPERTIES, text)
        return []

    def do_properties(self, arg: str) -> bool | None:
        """List property definitions and values
Usage: properties [propRegex]"""
        global wpdef
        if not self._ensure_connected():
            return
        props = self._get_props_matching_regex(arg, available_only=False)
        if not props:
            print(f"No matching properties found!")
            return
        print(f"Properties:")
        for prop_name, value in sorted(props.items()):
            self._print_prop_info(wpdef["properties"][prop_name], value)
        print()

    def complete_properties(self, text, line, begidx, endidx):
        return self._complete_propname(text, rw=False, available_only=False) + ['<propRegex>']

    def do_rawvalues(self, arg: str) -> bool | None:
        """List raw values of properties (without value mapping)
Usage: rawvalues [propRegex] [valueRegex]"""
        global wp
        if not self._ensure_connected():
            return
        print(f"List raw values of properties (without value mapping):")
        props = self._get_props_matching_regex(arg)
        for pd, value in sorted(props.items()):
            print(f"- {pd}: {utils_value2json(value)}")
        print()

    def complete_rawvalues(self, text, line, begidx, endidx):
        return self._complete_values(text, line)

    def do_server(self, arg: str) -> bool | None:
        """Start in server mode (infinite wait loop)
Usage: server"""
        if not self._ensure_connected():
            return
        _LOGGER.info("Server started.")
        try:
            Event().wait()
        except KeyboardInterrupt:
            _LOGGER.info("Server shutting down.")
        return True

    def do_set(self, arg: str) -> bool | None:
        """Set a property value
Usage: set <propName> <value>"""
        global wp
        global wpdef
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 2 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
        elif args[0] not in wp.allProps:
            print(f"ERROR: Unknown property: {args[0]}")
        else:
            if args[1].lower() in ["false", "true"]:
                v = json.loads(args[1].lower())
            elif str(args[1]).isnumeric():
                v = int(args[1])
            elif str(args[1]).isdecimal():
                v = float(args[1])
            else:
                v = str(args[1])
            wp.send_update(args[0], mqtt_get_decoded_property(
                wpdef["properties"][args[0]], v))

    def complete_set(self, text, line, begidx, endidx):
        global wpdef
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_propname(text, rw=True, available_only=True)
        elif len(token) == 3 and token[1] in wpdef["properties"]:
            pd = wpdef["properties"][token[1]]
            if "jsonType" in pd and pd["jsonType"] == 'boolean':
                return [v for v in ['false', 'true'] if v.startswith(text)]
            elif "valueMap" in pd:
                return [v for v in pd["valueMap"].values() if v.startswith(text)]
            elif "jsonType" in pd:
                return [f"<{pd['jsonType']}>"]
        return []

    def do_unwatch(self, arg: str) -> bool | None:
        """Unwatch a message or property
Usage: unwatch <message|property> <msgType|propName>"""
        global wp
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 2 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
        elif args[0] == 'message' and args[1] not in self.watching_messages:
            print(f"ERROR: Message of type '{args[1]}' is not watched")
        elif args[0] == 'message':
            self.watching_messages.remove(args[1])
            if len(self.watching_messages) == 0:
                wp.unregister_message_callback()
        elif args[0] == 'property' and args[1] not in self.watching_properties:
            print(f"ERROR: Property with name '{args[1]}' is not watched")
        elif args[0] == 'property':
            self.watching_properties.remove(args[1])
            if len(self.watching_properties) == 0:
                wp.unregister_property_callback()
        else:
            print(f"ERROR: Unknown watch type: {args[0]}")

    def complete_unwatch(self, text, line, begidx, endidx):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_list(['message', 'property'], text)
        elif len(token) == 3 and token[1] == 'message':
            return self._complete_list(self.watching_messages, text)
        elif len(token) == 3 and token[1] == 'property':
            return self._complete_list(self.watching_properties, text)
        return []

    def do_values(self, arg: str) -> bool | None:
        """List values of properties (with value mapping enabled)
Usage: values [propRegex] [valueRegex]"""
        global wp
        global wpdef
        if not self._ensure_connected():
            return
        print(f"List values of properties (with value mapping):")
        props = self._get_props_matching_regex(arg)
        for pd, value in sorted(props.items()):
            print(
                f"- {pd}: {mqtt_get_encoded_property(wpdef['properties'][pd],value)}")
        print()

    def complete_values(self, text, line, begidx, endidx):
        return self._complete_values(text, line)

    def do_watch(self, arg: str) -> bool | None:
        """Watch message or a property
Usage: watch <message|property> <msgType|propName>"""
        global wp
        global wpdef
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 2 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
        elif args[0] == 'message' and args[1] not in wpdef['messages']:
            print(f"ERROR: Unknown message type: {args[1]}")
        elif args[0] == 'message':
            msg_type = args[1]
            if len(self.watching_messages) == 0:
                wp.register_message_callback(self._watched_message_received)
            if msg_type not in self.watching_messages:
                self.watching_messages.append(msg_type)
        elif args[0] == 'property' and args[1] not in wp.allProps:
            print(f"ERROR: Unknown property: {args[1]}")
        elif args[0] == 'property':
            prop_name = args[1]
            if len(self.watching_properties) == 0:
                wp.register_property_callback(self._watched_property_changed)
            if prop_name not in self.watching_properties:
                self.watching_properties.append(prop_name)
        else:
            print(f"ERROR: Unknown watch type: {args[0]}")

    def complete_watch(self, text, line, begidx, endidx):
        global wpdef
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_list(['message', 'property'], text)
        elif len(token) == 3 and token[1] == 'message':
            return self._complete_message(text, 'server')
        elif len(token) == 3 and token[1] == 'property':
            return self._complete_propname(text, rw=False, available_only=True) + ['<propRegex>']
        return []

    def _print_prop_info(self, pd, value):
        global wp
        _LOGGER.debug(f"Property definition: {pd}")
        title = ""
        desc = ""
        alias = ""
        rw = ""
        if 'alias' in pd:
            alias = f", alias:{pd['alias']}"
        if 'rw' in pd:
            rw = f", rw:{pd['rw']}"
        if 'title' in pd:
            title = pd['title']
        if 'description' in pd:
            desc = pd['description']
        print(f"- {pd['key']} ({pd['jsonType']}{alias}{rw}): {title}")
        if desc:
            print(f"  Description: {desc}")
        if pd['key'] in wp.allProps.keys():
            print(
                f"  Value: {mqtt_get_encoded_property(pd,value)}{' (raw:' + utils_value2json(value) + ')' if 'valueMap' in pd else ''}")
        else:
            print(
                f"  NOTE: This property is currently not provided by the connected device!")

    def _watched_property_changed(self, name, value):
        global wpdef
        if name in self.watching_properties:
            pd = wpdef["properties"][name]
            _LOGGER.info(
                f"Property {name} changed to {mqtt_get_encoded_property(pd,value)}")

    def _watched_message_received(self, wp, wsapp, msg, msg_json):
        if msg.type in self.watching_messages:
            _LOGGER.info(f"Message of type {msg.type} received: {msg}")

    def _ensure_connected(self):
        global wp
        if not wp:
            print('Not connected to wattpilot!')
            return False
        return True

    def _get_props_matching_regex(self, arg, available_only=True):
        global wp
        global wpdef
        args = arg.split(' ')
        prop_regex = '.*'
        if len(args) > 0 and args[0] != '':
            prop_regex = args[0]
        props = {k: v for k, v in wp_get_all_props(available_only).items() if re.match(
            r'^'+prop_regex+'$', k, flags=re.IGNORECASE)}
        value_regex = '.*'
        if len(args) > 1:
            value_regex = args[1]
        props = {k: v for k, v in props.items() if re.match(r'^'+value_regex+'$',
                                                            str(mqtt_get_encoded_property(wpdef["properties"][k], v)), flags=re.IGNORECASE)}
        return props


#### MQTT Functions ####

def mqtt_get_mapped_value(pd, value):
    mapped_value = value
    if value == None:
        mapped_value = None
    elif "valueMap" in pd:
        if str(value) in list(pd["valueMap"].keys()):
            mapped_value = pd["valueMap"][str(value)]
        else:
            _LOGGER.warning(
                f"Unable to map value '{value}' of property '{pd['key']} - using unmapped value!")
    return mapped_value


def mqtt_get_mapped_property(pd, value):
    if value and "jsonType" in pd and pd["jsonType"] == "array":
        mapped_value = []
        for v in value:
            mapped_value.append(mqtt_get_mapped_value(pd, v))
    else:
        mapped_value = mqtt_get_mapped_value(pd, value)
    return mapped_value


def mqtt_get_remapped_value(pd, mapped_value):
    remapped_value = mapped_value
    if "valueMap" in pd:
        if mapped_value in pd["valueMap"].values():
            remapped_value = json.loads(str(list(pd["valueMap"].keys())[
                                        list(pd["valueMap"].values()).index(mapped_value)]))
        else:
            _LOGGER.warning(
                f"Unable to remap value '{mapped_value}' of property '{pd['key']} - using mapped value!")
    return remapped_value


def mqtt_get_remapped_property(pd, mapped_value):
    if "jsonType" in pd and pd["jsonType"] == "array":
        remapped_value = []
        for v in mapped_value:
            remapped_value.append(mqtt_get_remapped_value(pd, v))
    else:
        remapped_value = mqtt_get_remapped_value(pd, mapped_value)
    return remapped_value


def mqtt_get_encoded_property(pd, value):
    mapped_value = mqtt_get_mapped_property(pd, value)
    if value == None or "jsonType" in pd and (
            pd["jsonType"] == "array"
            or pd["jsonType"] == "object"
            or pd["jsonType"] == "boolean"):
        return json.dumps(mapped_value, cls=JSONNamespaceEncoder)
    else:
        return mapped_value


def mqtt_get_decoded_property(pd, value):
    if "jsonType" in pd and (pd["jsonType"] == "array" or pd["jsonType"] == "object"):
        decoded_value = json.loads(value)
    else:
        decoded_value = value
    return mqtt_get_remapped_property(pd, decoded_value)


def mqtt_publish_property(wp, mqtt_client, pd, value, force_publish=False):
    prop_name = pd["key"]
    if not (force_publish or MQTT_PROPERTIES == [''] or prop_name in MQTT_PROPERTIES):
        _LOGGER.debug(f"Skipping publishing of property '{prop_name}' ...")
        return
    property_topic = mqtt_subst_topic(MQTT_TOPIC_PROPERTY_STATE, {
        "baseTopic": MQTT_TOPIC_BASE,
        "serialNumber": wp.serial,
        "propName": prop_name,
    })
    encoded_value = mqtt_get_encoded_property(pd, value)
    _LOGGER.debug(
        f"Publishing property '{prop_name}' with value '{encoded_value}' to MQTT ...")
    mqtt_client.publish(property_topic, encoded_value, retain=True)
    if WATTPILOT_SPLIT_PROPERTIES and "childProps" in pd:
        _LOGGER.debug(
            f"Splitting child props of property {prop_name} as {pd['jsonType']} for value {value} ...")
        for cpd in pd["childProps"]:
            _LOGGER.debug(f"Extracting child property {cpd['key']},  ...")
            split_value = wp_get_child_prop_value(cpd['key'])
            _LOGGER.debug(
                f"Publishing sub-property {cpd['key']} with value {split_value} to MQTT ...")
            mqtt_publish_property(wp, mqtt_client, cpd, split_value, True)


def mqtt_publish_message(wp, wsapp, msg, msg_json):
    global mqtt_client
    global MQTT_PUBLISH_MESSAGES
    global MQTT_TOPIC_BASE
    global MQTT_PUBLISH_PROPERTIES
    global MQTT_TOPIC_MESSAGES
    global wpdef
    if mqtt_client == None:
        _LOGGER.debug(f"Skipping MQTT message publishing.")
        return
    msg_dict = json.loads(msg_json)
    if MQTT_PUBLISH_MESSAGES == "true" and (MQTT_MESSAGES == [] or MQTT_MESSAGES == [''] or msg.type in MQTT_MESSAGES):
        message_topic = mqtt_subst_topic(MQTT_TOPIC_MESSAGES, {
            "baseTopic": MQTT_TOPIC_BASE,
            "serialNumber": wp.serial,
            "messageType": msg.type,
        })
        mqtt_client.publish(message_topic, msg_json)
    if MQTT_PUBLISH_PROPERTIES == "true" and msg.type in ["fullStatus", "deltaStatus"]:
        for prop_name, value in msg_dict["status"].items():
            pd = wpdef["properties"][prop_name]
            mqtt_publish_property(wp, mqtt_client, pd, value)

# Substitute topic patterns


def mqtt_subst_topic(s, values, expand=True):
    if expand:
        s = re.sub(r'^~', MQTT_TOPIC_PROPERTY_BASE, s)
    all_values = {
        "baseTopic": MQTT_TOPIC_BASE,
    } | values
    return s.format(**all_values)


def mqtt_setup_client(host, port, client_id, available_topic, command_topic):
    # Connect to MQTT server:
    mqtt_client = mqtt.Client(client_id)
    mqtt_client.on_message = mqtt_set_value
    _LOGGER.info(f"Connecting to MQTT host {host} on port {port} ...")
    mqtt_client.will_set(
        available_topic, payload="offline", qos=0, retain=True)
    mqtt_client.connect(host, port)
    mqtt_client.loop_start()
    mqtt_client.publish(available_topic, payload="online", qos=0, retain=True)
    _LOGGER.info(f"Subscribing to command topics {command_topic}")
    mqtt_client.subscribe(command_topic)
    return mqtt_client


def mqtt_setup(wp):
    global MQTT_CLIENT_ID
    global MQTT_HOST
    global MQTT_PORT
    global MQTT_PROPERTIES
    global MQTT_TOPIC_AVAILABLE
    global MQTT_TOPIC_PROPERTY_SET
    # Connect to MQTT server:
    mqtt_client = mqtt_setup_client(MQTT_HOST, MQTT_PORT, MQTT_CLIENT_ID,
                                    mqtt_subst_topic(MQTT_TOPIC_AVAILABLE, {}),
                                    mqtt_subst_topic(MQTT_TOPIC_PROPERTY_SET, {
                                                     "propName": "+"}),
                                    )
    MQTT_PROPERTIES = mqtt_get_watched_properties(wp)
    _LOGGER.info(
        f"Registering message callback to publish updates to the following properties to MQTT: {MQTT_PROPERTIES}")
    wp.register_message_callback(mqtt_publish_message)
    return mqtt_client


def mqtt_stop(mqtt_client):
    if mqtt_client.is_connected():
        _LOGGER.info(f"Disconnecting from MQTT server ...")
        mqtt_client.disconnect()

# Subscribe to topic for setting property values:


def mqtt_set_value(client, userdata, message):
    global wpdef
    topic_regex = mqtt_subst_topic(
        MQTT_TOPIC_PROPERTY_SET, {"propName": "([^/]+)"})
    name = re.sub(topic_regex, r'\1', message.topic)
    if not name or name == "" or not wpdef["properties"][name]:
        _LOGGER.warning(f"Unknown property '{name}'!")
    pd = wpdef["properties"][name]
    if pd['rw'] == "R":
        _LOGGER.warning(f"Property '{name}' is not writable!")
    value = mqtt_get_decoded_property(
        pd, str(message.payload.decode("utf-8")))
    _LOGGER.info(
        f"MQTT Message received: topic={message.topic}, name={name}, value={value}")
    wp.send_update(name, value)


def mqtt_get_watched_properties(wp):
    global MQTT_PROPERTIES
    if MQTT_PROPERTIES == [] or MQTT_PROPERTIES == ['']:
        return list(wp.allProps.keys())
    else:
        return MQTT_PROPERTIES


#### Home Assistant Functions ####

# Generate device information for HA discovery
def ha_get_device_info(wp):
    ha_device = {
        "connections": [
        ],
        "identifiers": [
            f"wattpilot_{wp.serial}",
        ],
        "manufacturer": wp.manufacturer,
        "model": wp.devicetype,
        "name": wp.name,
        "suggested_area": "Garage",
        "sw_version": wp.version,
    }
    if "maca" in wp.allProps:
        ha_device["connections"] += [["mac", wp.allProps["maca"]]]
    if "macs" in wp.allProps:
        ha_device["connections"] += [["mac", wp.allProps["macs"]]]
    return ha_device


def ha_get_component_for_prop(prop_info):
    component = "sensor"
    if "rw" in prop_info and prop_info["rw"] == "R/W":
        if "valueMap" in prop_info:
            component = "select"
        elif "jsonType" in prop_info and prop_info["jsonType"] == "boolean":
            component = "switch"
        elif "jsonType" in prop_info and prop_info["jsonType"] == "float":
            component = "number"
        elif "jsonType" in prop_info and prop_info["jsonType"] == "integer":
            component = "number"
    elif "rw" in prop_info and prop_info["rw"] == "R":
        if "jsonType" in prop_info and prop_info["jsonType"] == "boolean":
            component = "binary_sensor"
    return component


def ha_get_default_config_for_prop(prop_info):
    config = {}
    if "rw" in prop_info and prop_info["rw"] == "R/W":
        if "jsonType" in prop_info and \
                (prop_info["jsonType"] == "float" or prop_info["jsonType"] == "integer"):
            config["mode"] = "box"
        if "category" in prop_info and prop_info["category"] == "Config":
            config["entity_category"] = "config"
    if "homeAssistant" not in prop_info:
        config["enabled_by_default"] = False
    return config


def ha_get_template_filter_from_json_type(json_type):
    template = "{{ value | string }}"
    if json_type == "float":
        template = "{{ value | float }}"
    elif json_type == "integer":
        template = "{{ value | int }}"
    elif json_type == "boolean":
        template = "{{ value == 'true' }}"
    return template

# Publish HA discovery config for a single property


def ha_discover_property(wp, mqtt_client, pd, disable_discovery=False, force_enablement=None):
    global HA_TOPIC_CONFIG
    global WATTPILOT_SPLIT_PROPERTIES
    global MQTT_TOPIC_PROPERTY_BASE
    global MQTT_TOPIC_PROPERTY_SET
    global MQTT_TOPIC_PROPERTY_STATE
    name = pd["key"]
    ha_info = {}
    if "homeAssistant" in pd:
        ha_info = pd["homeAssistant"] or {}
    component = ha_get_component_for_prop(pd)
    if "component" in ha_info:  # Override component from config
        component = ha_info["component"]
    _LOGGER.debug(
        f"Homeassistant config: haInfo={ha_info}, component={component}")
    title = pd.get("title", pd.get("alias", name))
    _LOGGER.debug(
        f"Publishing HA discovery config for property '{name}' ...")
    ha_config = ha_info.get("config", {})
    unique_id = f"wattpilot_{wp.serial}_{name}"
    object_id = f"wattpilot_{name}"
    topic_subst_map = {
        "component": component,
        "propName": name,
        "serialNumber": wp.serial,
        "uniqueId": unique_id,
    }
    ha_device = ha_get_device_info(wp)
    base_topic = mqtt_subst_topic(
        MQTT_TOPIC_PROPERTY_BASE, topic_subst_map, False)
    ha_discovery_config = ha_get_default_config_for_prop(pd) | {
        "~": base_topic,
        "name": title,
        "object_id": object_id,
        "unique_id": unique_id,
        "state_topic": mqtt_subst_topic(MQTT_TOPIC_PROPERTY_STATE, topic_subst_map, False),
        "availability_topic": mqtt_subst_topic(MQTT_TOPIC_AVAILABLE, {}),
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": ha_device,
    }
    if "valueMap" in pd:
        ha_discovery_config["options"] = list(pd["valueMap"].values())
    if pd.get("rw", "") == "R/W":
        ha_discovery_config["command_topic"] = mqtt_subst_topic(
            MQTT_TOPIC_PROPERTY_SET, topic_subst_map, False)
    ha_discovery_config = dict(
        list(ha_discovery_config.items())
        + list(ha_config.items())
    )
    if force_enablement != None:
        ha_discovery_config["enabled_by_default"] = force_enablement
    topic_cfg = mqtt_subst_topic(HA_TOPIC_CONFIG, topic_subst_map)
    if disable_discovery:
        payload = ''
    else:
        payload = utils_value2json(ha_discovery_config)
    _LOGGER.debug(
        f"Publishing property '{name}' to {topic_cfg}: {payload}")
    mqtt_client.publish(topic_cfg, payload, retain=True)
    # Publish additional read-only sensor for special rw properties:
    if pd.get("rw", "") == "R/W" and component != "sensor":
        if payload != "":
            del ha_discovery_config["command_topic"]
            payload = utils_value2json(ha_discovery_config)
        mqtt_client.publish(mqtt_subst_topic(HA_TOPIC_CONFIG, topic_subst_map | {
                            "component": "sensor"}), payload, retain=True)
    if WATTPILOT_SPLIT_PROPERTIES and "childProps" in pd:
        for p in pd["childProps"]:
            ha_discover_property(wp, mqtt_client, p,
                                 disable_discovery, force_enablement)


def ha_is_default_prop(pd):
    global HA_DISABLED_ENTITIES
    v = "homeAssistant" in pd
    if HA_DISABLED_ENTITIES != 'true':
        ha = pd.get("homeAssistant", {}) if pd.get("homeAssistant", {}) else {}
        v = v and ha.get("config", {}).get("enabled_by_default", True)
    return v


def ha_get_discovery_properties():
    global HA_PROPERTIES
    global wpdef
    _LOGGER.debug(
        f"get_ha_discovery_properties(): HA_PROPERTIES='{HA_PROPERTIES}', propdef size='{len(wpdef['properties'])}'")
    ha_properties = HA_PROPERTIES
    if ha_properties == [''] or ha_properties == []:
        ha_properties = [p["key"]
                         for p in wpdef["properties"].values() if ha_is_default_prop(p)]
    _LOGGER.debug(
        f"get_ha_discovery_properties(): ha_properties='{ha_properties}'")
    return ha_properties


def ha_discover_properties(mqtt_client, ha_properties, disable_discovery=True):
    global wpdef
    _LOGGER.info(
        f"{'Disabling' if disable_discovery else 'Enabling'} HA discovery for the following properties: {ha_properties}")
    for name in ha_properties:
        ha_discover_property(
            wp, mqtt_client, wpdef["properties"][name], disable_discovery)


def ha_publish_initial_properties(wp, mqtt_client):
    global HA_PROPERTIES
    global wpdef
    _LOGGER.info(
        f"Publishing all initial property values to MQTT to populate the entity values ...")
    for prop_name in HA_PROPERTIES:
        if prop_name in wp.allProps:
            value = wp.allProps[prop_name]
            pd = wpdef["properties"][prop_name]
            mqtt_publish_property(wp, mqtt_client, pd, value)


def ha_setup(wp):
    global HA_PROPERTIES
    global HA_WAIT_INIT_S
    global HA_WAIT_PROPS_MS
    global MQTT_PROPERTIES
    global wpdef
    # Configure list of relevant properties:
    HA_PROPERTIES = ha_get_discovery_properties()
    if MQTT_PROPERTIES == [] or MQTT_PROPERTIES == ['']:
        MQTT_PROPERTIES = HA_PROPERTIES
    # Setup MQTT client:
    mqtt_client = mqtt_setup(wp)
    # Publish HA discovery config:
    ha_discover_properties(mqtt_client, HA_PROPERTIES, False)
    # Wait a bit for HA to catch up:
    wait_time = math.ceil(
        HA_WAIT_INIT_S + len(HA_PROPERTIES)*HA_WAIT_PROPS_MS*0.001)
    if wait_time > 0:
        _LOGGER.info(
            f"Waiting {wait_time}s to allow Home Assistant to discovery entities and subscribe MQTT topics before publishing initial values ...")
        # Sleep to let HA discover the entities before publishing values
        sleep(wait_time)
    # Publish initial property values to MQTT:
    ha_publish_initial_properties(wp, mqtt_client)
    return mqtt_client


def ha_stop(mqtt_client):
    global HA_PROPERTIES
    ha_discover_properties(mqtt_client, HA_PROPERTIES, True)
    mqtt_stop(mqtt_client)


#### Main Program ####

def main_setup_env():
    global HA_DISABLED_ENTITIES
    global HA_ENABLED
    global HA_PROPERTIES
    global HA_TOPIC_CONFIG
    global HA_WAIT_INIT_S
    global HA_WAIT_PROPS_MS
    global MQTT_AVAILABLE_PAYLOAD
    global MQTT_CLIENT_ID
    global MQTT_ENABLED
    global MQTT_HOST
    global MQTT_MESSAGES
    global MQTT_NOT_AVAILABLE_PAYLOAD
    global MQTT_PORT
    global MQTT_PROPERTIES
    global MQTT_PUBLISH_MESSAGES
    global MQTT_PUBLISH_PROPERTIES
    global MQTT_TOPIC_AVAILABLE
    global MQTT_TOPIC_BASE
    global MQTT_TOPIC_MESSAGES
    global MQTT_TOPIC_PROPERTY_BASE
    global MQTT_TOPIC_PROPERTY_SET
    global MQTT_TOPIC_PROPERTY_STATE
    global WATTPILOT_AUTOCONNECT
    global WATTPILOT_CONNECT_TIMEOUT
    global WATTPILOT_DEBUG_LEVEL
    global WATTPILOT_HOST
    global WATTPILOT_INIT_TIMEOUT
    global WATTPILOT_PASSWORD
    global WATTPILOT_SPLIT_PROPERTIES
    HA_DISABLED_ENTITIES = os.environ.get('HA_DISABLED_ENTITIES', 'false')
    HA_ENABLED = os.environ.get('HA_ENABLED', 'false')
    HA_PROPERTIES = os.environ.get('HA_PROPERTIES', '').split(sep=' ')
    HA_TOPIC_CONFIG = os.environ.get(
        'HA_TOPIC_CONFIG', 'homeassistant/{component}/{uniqueId}/config')
    HA_WAIT_INIT_S = int(os.environ.get('HA_WAIT_INIT_S', '0'))
    HA_WAIT_PROPS_MS = int(os.environ.get('HA_WAIT_PROPS_MS', '0'))
    MQTT_AVAILABLE_PAYLOAD = os.environ.get('MQTT_AVAILABLE_PAYLOAD', 'online')
    MQTT_CLIENT_ID = os.environ.get('MQTT_CLIENT_ID', 'wattpilot2mqtt')
    MQTT_ENABLED = os.environ.get('MQTT_ENABLED', 'false')
    MQTT_HOST = os.environ.get('MQTT_HOST', '')
    MQTT_MESSAGES = os.environ.get('MQTT_MESSAGES', '').split(sep=' ')
    MQTT_NOT_AVAILABLE_PAYLOAD = os.environ.get(
        'MQTT_NOT_AVAILABLE_PAYLOAD', 'offline')
    MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
    MQTT_PROPERTIES = os.environ.get('MQTT_PROPERTIES', '').split(sep=' ')
    MQTT_PUBLISH_MESSAGES = os.environ.get('MQTT_PUBLISH_MESSAGES', 'false')
    MQTT_PUBLISH_PROPERTIES = os.environ.get('MQTT_PUBLISH_PROPERTIES', 'true')
    MQTT_TOPIC_AVAILABLE = os.environ.get(
        'MQTT_TOPIC_AVAILABLE', '{baseTopic}/available')
    MQTT_TOPIC_BASE = os.environ.get('MQTT_TOPIC_BASE', 'wattpilot')
    MQTT_TOPIC_MESSAGES = os.environ.get(
        'MQTT_TOPIC_MESSAGES', '{baseTopic}/messages/{messageType}')
    MQTT_TOPIC_PROPERTY_BASE = os.environ.get(
        'MQTT_TOPIC_PROPERTY_BASE', '{baseTopic}/properties/{propName}')
    MQTT_TOPIC_PROPERTY_SET = os.environ.get(
        'MQTT_TOPIC_PROPERTY_SET', '~/set')
    MQTT_TOPIC_PROPERTY_STATE = os.environ.get(
        'MQTT_TOPIC_PROPERTY_STATE', '~/state')
    WATTPILOT_AUTOCONNECT = os.environ.get('WATTPILOT_AUTOCONNECT', 'true')
    WATTPILOT_CONNECT_TIMEOUT = int(
        os.environ.get('WATTPILOT_CONNECT_TIMEOUT', '30'))
    WATTPILOT_DEBUG_LEVEL = os.environ.get('WATTPILOT_DEBUG_LEVEL', 'INFO')
    WATTPILOT_HOST = os.environ.get('WATTPILOT_HOST', '')
    WATTPILOT_INIT_TIMEOUT = int(
        os.environ.get('WATTPILOT_INIT_TIMEOUT', '30'))
    WATTPILOT_PASSWORD = os.environ.get('WATTPILOT_PASSWORD', '')
    WATTPILOT_SPLIT_PROPERTIES = bool(
        os.environ.get('WATTPILOT_SPLIT_PROPERTIES', 'true'))

    # Ensure wattpilot host an password are set:
    assert WATTPILOT_HOST != '', "WATTPILOT_HOST not set!"
    assert WATTPILOT_PASSWORD != '', "WATTPILOT_PASSWORD not set!"
    assert MQTT_ENABLED == 'false' or MQTT_HOST != '', 'MQTT_HOST not set!'


def main():
    global MQTT_ENABLED
    global WATTPILOT_AUTOCONNECT
    global WATTPILOT_DEBUG_LEVEL
    global mqtt_client
    global wp
    global wpdef

    # Setup environment variables:
    main_setup_env()

    # Set debug level:
    logging.basicConfig(level=WATTPILOT_DEBUG_LEVEL)

    # Initialize globals:
    mqtt_client = None
    wp = None
    wpdef = wp_read_apidef()

    # Initialize shell:
    wpsh = WattpilotShell()
    if WATTPILOT_AUTOCONNECT == 'true':
        _LOGGER.info("Automatically connecting to Wattpilot ...")
        wpsh.onecmd('connect')
        # Enable MQTT and/or HA integration:
        if MQTT_ENABLED == "true" and HA_ENABLED == "false":
            wpsh.onecmd('mqtt start')
        elif MQTT_ENABLED == "true" and HA_ENABLED == "true":
            wpsh.onecmd('ha start')
        wpsh.onecmd('info')
    if len(sys.argv) < 2:
        wpsh.cmdloop()
    else:
        wpsh.onecmd(sys.argv[1])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
