import cmd2
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

from enum import Enum, auto
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
            if "childProps" in p and Cfg.WATTPILOT_SPLIT_PROPERTIES.val:
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
    _LOGGER.debug(f"wp_initialize()")
    wp = wattpilot.Wattpilot(host, password)
    wp._auto_reconnect = Cfg.WATTPILOT_AUTO_RECONNECT.val
    wp._reconnect_interval = Cfg.WATTPILOT_RECONNECT_INTERVAL.val
    wp.add_event_handler(wattpilot.Event.WS_CLOSE, wp_handle_events)
    wp.add_event_handler(wattpilot.Event.WS_OPEN, wp_handle_events)
    return wp

def wp_connect(wp, wait_for_timeouts=True):
    wp.connect()
    # Wait for connection and initialization - TODO: Use event handler instead to make it more responsive!
    if wait_for_timeouts:
        utils_wait_timeout(lambda: wp.connected, Cfg.WATTPILOT_CONNECT_TIMEOUT.val) or exit(
            "ERROR: Timeout while connecting to Wattpilot!")
        utils_wait_timeout(lambda: wp.allPropsInitialized, Cfg.WATTPILOT_INIT_TIMEOUT.val) or exit(
            "ERROR: Timeout while waiting for property initialization!")
    return wp


def wp_handle_events(event, *args):
    global mqtt_client
    _LOGGER.debug(f"wp_handle_events(event={event},{args})")
    if not mqtt_client:
        _LOGGER.debug(f"wp_handle_events(): MQTT client not yet initialized - status publishing skipped.")
        return
    available_topic = mqtt_subst_topic(Cfg.MQTT_TOPIC_AVAILABLE.val, {})
    if event['type'] == 'on_close':
        mqtt_client.publish(available_topic, payload="offline", qos=0, retain=True)
    elif event['type'] == 'on_open':
        mqtt_client.publish(available_topic, payload="online", qos=0, retain=True)


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
    global wp
    global wpdef
    if available_only:
        props = {k: v for k, v in wp.allProps.items()}
        if Cfg.WATTPILOT_SPLIT_PROPERTIES.val:
            for cp_key in wpdef["splitProperties"]:
                props[cp_key] = wp_get_child_prop_value(cp_key)
    else:
        props = {k: (wp.allProps[k] if k in wp.allProps else None)
                 for k in wpdef["properties"].keys()}
    return props


#### Shell Functions ####

class WattpilotShell(cmd2.Cmd):
    intro = f"Welcome to the Wattpilot Shell {version('wattpilot')}.   Type help or ? to list commands.\n"
    prompt = 'wattpilot> '
    file = None
    watching_messages = []
    watching_properties = []

    def __init__(self, wp, wpdef):
        super().__init__()
        self.wp = wp
        self.wpdef = wpdef

    def postloop(self) -> None:
        print()
        return super().postloop()

    def emptyline(self) -> bool:
        return False

    def _complete_list(self, clist, text):
        return [x for x in clist if x.startswith(text)]

    def _complete_message(self, text, sender=None):
        return [md["key"] for md in self.wpdef["messages"].values() if (not sender or md["sender"] == sender) and md["key"].startswith(text)]

    def _complete_propname(self, text, rw=False, available_only=True):
        return [k for k in wp_get_all_props(available_only).keys() if (not rw or ("rw" in self.wpdef["properties"][k] and self.wpdef["properties"][k]["rw"] == "R/W")) and k.startswith(text)]

    def _complete_values(self, text, line):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_propname(text, rw=False, available_only=True) + ['<propRegex>']
        elif len(token) == 3 and text in self.wpdef["properties"]:
            return ['<value>', '<valueRegex>']
        return []

    def do_EOF(self, arg: str) -> bool | None:
        """Exit the shell"""
        return True

    def do_connect(self, arg: str) -> bool | None:
        """Connect to Wattpilot
Usage: connect"""
        wp_connect(self.wp)

    def do_disconnect(self, arg: str) -> bool | None:
        """Disconnect from Wattpilot
Usage: disconnect"""
        wp.disconnect()

    def do_docs(self, arg: str) -> bool | None:
        """Show markdown documentation for environment variables
Usage: docs"""
        Cfg.docs_markdown()

    def do_config(self, arg: str) -> bool | None:
        """Show configuration values
Usage: config"""
        for e in list(Cfg):
            #print(f"{e.name}={os.environ.get(e.name,'')} (-> {e.val})")
            print(e.value.format())

    def do_exit(self, arg: str) -> bool | None:
        """Exit the shell
Usage: exit"""
        return True

    def do_propget(self, arg: str) -> bool | None:
        """Get a property value
Usage: propget <propName>"""
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 1 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
        elif args[0] in self.wp.allProps:
            pd = self.wpdef["properties"][args[0]]
            print(mqtt_get_encoded_property(pd, self.wp.allProps[args[0]]))
        elif args[0] in self.wpdef["splitProperties"]:
            pd = self.wpdef["properties"][args[0]]
            print(mqtt_get_encoded_property(
                pd, wp_get_child_prop_value(pd["key"])))
        else:
            print(f"ERROR: Unknown property: {args[0]}")

    def complete_propget(self, text, line, begidx, endidx):
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
        global mqtt_client
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 1 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
            return
        if args[0] == "properties":
            print(
                f"List of properties activated for discovery: {Cfg.HA_PROPERTIES.val}")
        elif args[0] == "start":
            Cfg.HA_ENABLED.val = True
            mqtt_client = ha_setup(wp)
        elif args[0] == "stop":
            ha_stop(mqtt_client)
            Cfg.HA_ENABLED.val = False
        elif args[0] == "status":
            print(
                f"HA discovery is {'enabled' if Cfg.HA_ENABLED.val else 'disabled'}.")
        elif len(args) > 1 and args[0] in ['enable', 'disable', 'discover', 'undiscover']:
            self._ha_prop_cmds(args[0], args[1])
        else:
            print(f"ERROR: Unsupported argument: {args[0]}")

    def _ha_prop_cmds(self, cmd, prop_name):
        global mqtt_client
        if prop_name not in wpdef["properties"]:
            print(f"ERROR: Unknown property '{prop_name}!")
        elif cmd == "enable":
            if prop_name not in Cfg.MQTT_PROPERTIES.val:
                Cfg.MQTT_PROPERTIES.val.append(prop_name)
            ha_discover_property(
                self.wp, mqtt_client, self.wpdef["properties"][prop_name], disable_discovery=False, force_enablement=True)
        elif cmd == "disable":
            if prop_name in Cfg.MQTT_PROPERTIES.val:
                Cfg.MQTT_PROPERTIES.val.remove(prop_name)
            ha_discover_property(
                self.wp, mqtt_client, self.wpdef["properties"][prop_name], disable_discovery=False, force_enablement=False)
        elif cmd == "discover":
            if prop_name not in Cfg.HA_PROPERTIES.val:
                Cfg.HA_PROPERTIES.val.append(prop_name)
            if prop_name not in Cfg.MQTT_PROPERTIES.val:
                Cfg.MQTT_PROPERTIES.val.append(prop_name)
            ha_discover_property(
                self.wp, mqtt_client, self.wpdef["properties"][prop_name], disable_discovery=False, force_enablement=True)
        elif cmd == "undiscover":
            if prop_name in Cfg.HA_PROPERTIES.val:
                Cfg.HA_PROPERTIES.val.remove(prop_name)
            if prop_name in Cfg.MQTT_PROPERTIES.val:
                Cfg.MQTT_PROPERTIES.val.remove(prop_name)
            ha_discover_property(
                self.wp, mqtt_client, self.wpdef["properties"][prop_name], disable_discovery=True, force_enablement=False)

    def complete_ha(self, text, line, begidx, endidx):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_list(['enable', 'disable', 'discover', 'properties', 'start', 'status', 'stop', 'undiscover'], text)
        elif len(token) == 3 and token[1] == 'discover':
            return self._complete_list([p for p in self._complete_propname(text, available_only=True) if p not in Cfg.HA_PROPERTIES.val], text)
        elif len(token) == 3 and token[1] in ['enable', 'disable', 'undiscover']:
            return self._complete_list(Cfg.HA_PROPERTIES.val, text)
        return []

    def do_info(self, arg: str) -> bool | None:
        """Print device infos
Usage: info"""
        if not self._ensure_connected():
            return
        print(self.wp)

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
        global mqtt_client
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 1 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
            return
        if args[0] == "properties":
            print(
                f"List of properties activated for MQTT publishing: {Cfg.MQTT_PROPERTIES.val}")
        elif args[0] == "start":
            Cfg.MQTT_ENABLED.val = True
            mqtt_client = mqtt_setup(self.wp)
        elif args[0] == "stop":
            mqtt_stop(mqtt_client)
            Cfg.MQTT_ENABLED.val = False
        elif args[0] == "status":
            print(
                f"MQTT client is {'enabled' if Cfg.MQTT_ENABLED.val else 'disabled'}.")
        elif len(args) > 1 and args[0] in ['publish', 'unpublish']:
            self._mqtt_prop_cmds(args[0], args[1])
        else:
            print(f"ERROR: Unsupported argument: {args[0]}")

    def _mqtt_prop_cmds(self, cmd, prop_name):
        global mqtt_client
        if prop_name not in self.wpdef["properties"]:
            print(f"ERROR: Undefined property '{prop_name}'!")
        elif cmd == "publish" and prop_name not in Cfg.MQTT_PROPERTIES.val:
            Cfg.MQTT_PROPERTIES.val.append(prop_name)
        elif cmd == "unpublish" and prop_name in Cfg.MQTT_PROPERTIES.val:
            Cfg.MQTT_PROPERTIES.val.remove(prop_name)

    def complete_mqtt(self, text, line, begidx, endidx):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_list(['properties', 'publish', 'start', 'status', 'stop', 'unpublish'], text)
        elif len(token) == 3 and token[1] == 'publish':
            return self._complete_list([p for p in self._complete_propname(text, available_only=True) if p not in Cfg.MQTT_PROPERTIES.val], text)
        elif len(token) == 3 and token[1] == 'unpublish':
            return self._complete_list(Cfg.MQTT_PROPERTIES.val, text)
        return []

    def do_properties(self, arg: str) -> bool | None:
        """List property definitions and values
Usage: properties [propRegex]"""
        if not self._ensure_connected():
            return
        props = self._get_props_matching_regex(arg, available_only=False)
        if not props:
            print(f"No matching properties found!")
            return
        print(f"Properties:")
        for prop_name, value in sorted(props.items()):
            self._print_prop_info(self.wpdef["properties"][prop_name], value)
        print()

    def complete_properties(self, text, line, begidx, endidx):
        return self._complete_propname(text, rw=False, available_only=False) + ['<propRegex>']

    def do_rawvalues(self, arg: str) -> bool | None:
        """List raw values of properties (without value mapping)
Usage: rawvalues [propRegex] [valueRegex]"""
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

    def do_propset(self, arg: str) -> bool | None:
        """Set a property value
Usage: propset <propName> <value>"""
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
                self.wpdef["properties"][args[0]], v))

    def do_UpdateInverter(self, arg: str) -> bool | None:
        """Performs an Inverter Operation
Usage: updateInverter pair|unpair <inverterID>
<inverterID> is normally in the form 123.456789"""
        global wp
        global wpdef
        args = arg.split(' ')
        if not self._ensure_connected():
            return
        if len(args) < 2 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
        elif args[0] not in ["pair", "unpair"]:
            print(f"ERROR: Unknown Operation: {args[0]}")
        else:
            if args[0] == 'pair':
                wp.pairInverter(args[1])
            if args[0] == 'unpair':
                wp.unpairInverter(args[1])
            

    def complete_propset(self, text, line, begidx, endidx):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_propname(text, rw=True, available_only=True)
        elif len(token) == 3 and token[1] in self.wpdef["properties"]:
            pd = self.wpdef["properties"][token[1]]
            if "jsonType" in pd and pd["jsonType"] == 'boolean':
                return [v for v in ['false', 'true'] if v.startswith(text)]
            elif "valueMap" in pd:
                return [v for v in pd["valueMap"].values() if v.startswith(text)]
            elif "jsonType" in pd:
                return [f"<{pd['jsonType']}>"]
        return []

    def do_unwatch(self, arg: str) -> bool | None:
        """Unwatch a message or property
Usage: unwatch <event|message|property> <eventType|msgType|propName>"""
        args = arg.split(' ')
        if len(args) < 2 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
        elif args[0] == 'event' and args[1] not in [e.name for e in list(wattpilot.Event)]:
            print(f"ERROR: Event of type '{args[1]}' is not watched")
        elif args[0] == 'event':
            self.wp.remove_event_handler(wattpilot.Event[args[1]], self._watched_event_received)
        elif args[0] == 'message' and args[1] not in self.watching_messages:
            print(f"ERROR: Message of type '{args[1]}' is not watched")
        elif args[0] == 'message':
            self.watching_messages.remove(args[1])
            if len(self.watching_messages) == 0:
                self.wp.remove_event_handler(wattpilot.Event.WS_MESSAGE,self._watched_message_received)
        elif args[0] == 'property' and args[1] not in self.watching_properties:
            print(f"ERROR: Property with name '{args[1]}' is not watched")
        elif args[0] == 'property':
            self.watching_properties.remove(args[1])
            if len(self.watching_properties) == 0:
                self.wp.remove_event_handler(wattpilot.Event.WP_PROPERTY,self._watched_property_changed)
        else:
            print(f"ERROR: Unknown watch type: {args[0]}")

    def complete_unwatch(self, text, line, begidx, endidx):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_list(['event', 'message', 'property'], text)
        elif len(token) == 3 and token[1] == 'event':
            return self._complete_list([e.name for e in list(wattpilot.Event) if len(wp._event_handler[e])>0], text)
        elif len(token) == 3 and token[1] == 'message':
            return self._complete_list(self.watching_messages, text)
        elif len(token) == 3 and token[1] == 'property':
            return self._complete_list(self.watching_properties, text)
        return []

    def do_values(self, arg: str) -> bool | None:
        """List values of properties (with value mapping enabled)
Usage: values [propRegex] [valueRegex]"""
        if not self._ensure_connected():
            return
        print(f"List values of properties (with value mapping):")
        props = self._get_props_matching_regex(arg)
        for pd, value in sorted(props.items()):
            print(
                f"- {pd}: {mqtt_get_encoded_property(self.wpdef['properties'][pd],value)}")
        print()

    def complete_values(self, text, line, begidx, endidx):
        return self._complete_values(text, line)

    def do_watch(self, arg: str) -> bool | None:
        """Watch an event, a message or a property
Usage: watch <event|message|property> <eventType|msgType|propName>"""
        args = arg.split(' ')
        if len(args) < 2 or arg == '':
            print(f"ERROR: Wrong number of arguments!")
        elif args[0] == 'event' and args[1] not in [e.name for e in list(wattpilot.Event)]:
            print(f"ERROR: Unknown event type: {args[1]}")
        elif args[0] == 'event':
            self.wp.add_event_handler(wattpilot.Event[args[1]], self._watched_event_received)
        elif args[0] == 'message' and args[1] not in self.wpdef['messages']:
            print(f"ERROR: Unknown message type: {args[1]}")
        elif args[0] == 'message':
            msg_type = args[1]
            if len(self.watching_messages) == 0:
                self.wp.add_event_handler(wattpilot.Event.WS_MESSAGE,self._watched_message_received)
            if msg_type not in self.watching_messages:
                self.watching_messages.append(msg_type)
        elif args[0] == 'property' and args[1] not in wp.allProps:
            print(f"ERROR: Unknown property: {args[1]}")
        elif args[0] == 'property':
            prop_name = args[1]
            if len(self.watching_properties) == 0:
                wp.add_event_handler(wattpilot.Event.WP_PROPERTY,self._watched_property_changed)
            if prop_name not in self.watching_properties:
                self.watching_properties.append(prop_name)
        else:
            print(f"ERROR: Unknown watch type: {args[0]}")

    def complete_watch(self, text, line, begidx, endidx):
        token = line.split(' ')
        if len(token) == 2:
            return self._complete_list(['event', 'message', 'property'], text)
        elif len(token) == 3 and token[1] == 'event':
            return self._complete_list([e.name for e in list(wattpilot.Event)], text)
        elif len(token) == 3 and token[1] == 'message':
            return self._complete_message(text, 'server')
        elif len(token) == 3 and token[1] == 'property':
            return self._complete_propname(text, rw=False, available_only=True) + ['<propRegex>']
        return []

    def _print_prop_info(self, pd, value):
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
        if pd['key'] in self.wp.allProps.keys():
            print(
                f"  Value: {mqtt_get_encoded_property(pd,value)}{' (raw:' + utils_value2json(value) + ')' if 'valueMap' in pd else ''}")
        else:
            print(
                f"  NOTE: This property is currently not provided by the connected device!")

    def _watched_event_received(self, event, *args):
        print(f"Event of type '{event['type']}' with args '{args}' received!")

    def _watched_property_changed(self, wp, name, value):
        if name in self.watching_properties:
            pd = self.wpdef["properties"][name]
            _LOGGER.info(
                f"Property {name} changed to {mqtt_get_encoded_property(pd,value)}")

    def _watched_message_received(self, event, message):
        msg_dict = json.loads(message)
        if msg_dict["type"] in self.watching_messages:
            _LOGGER.info(f"Message of type {msg_dict['type']} received: {message}")

    def _ensure_connected(self):
        if not self.wp or not self.wp._connected:
            print('Not connected to wattpilot!')
            return False
        return True

    def _get_props_matching_regex(self, arg, available_only=True):
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
                                                            str(mqtt_get_encoded_property(self.wpdef["properties"][k], v)), flags=re.IGNORECASE)}
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
    if not (force_publish or not Cfg.MQTT_PROPERTIES.val or prop_name in Cfg.MQTT_PROPERTIES.val):
        _LOGGER.debug(f"Skipping publishing of property '{prop_name}' ...")
        return
    property_topic = mqtt_subst_topic(Cfg.MQTT_TOPIC_PROPERTY_STATE.val, {
        "baseTopic": Cfg.MQTT_TOPIC_BASE.val,
        "serialNumber": wp.serial,
        "propName": prop_name,
    })
    encoded_value = mqtt_get_encoded_property(pd, value)
    _LOGGER.debug(
        f"Publishing property '{prop_name}' with value '{encoded_value}' to MQTT ...")
    mqtt_client.publish(property_topic, encoded_value, retain=True)
    if Cfg.WATTPILOT_SPLIT_PROPERTIES.val and "childProps" in pd:
        _LOGGER.debug(
            f"Splitting child props of property {prop_name} as {pd['jsonType']} for value {value} ...")
        for cpd in pd["childProps"]:
            _LOGGER.debug(f"Extracting child property {cpd['key']},  ...")
            split_value = wp_get_child_prop_value(cpd['key'])
            _LOGGER.debug(
                f"Publishing sub-property {cpd['key']} with value {split_value} to MQTT ...")
            mqtt_publish_property(wp, mqtt_client, cpd, split_value, True)


def mqtt_publish_message(event, message):
    _LOGGER.debug(f"""mqtt_publish_message(event={event},message={message})""")
    global mqtt_client
    global wpdef
    wp = event['wp']
    if mqtt_client == None:
        _LOGGER.debug(f"Skipping MQTT message publishing.")
        return
    msg_dict = json.loads(message)
    if Cfg.MQTT_PUBLISH_MESSAGES.val and (not Cfg.MQTT_MESSAGES.val or msg_dict["type"] in Cfg.MQTT_MESSAGES.val):
        message_topic = mqtt_subst_topic(Cfg.MQTT_TOPIC_MESSAGES.val, {
            "baseTopic": Cfg.MQTT_TOPIC_BASE.val,
            "serialNumber": wp.serial,
            "messageType": msg_dict["type"],
        })
        mqtt_client.publish(message_topic, message)
    if Cfg.MQTT_PUBLISH_PROPERTIES.val and msg_dict["type"] in ["fullStatus", "deltaStatus"]:
        for prop_name, value in msg_dict["status"].items():
            pd = wpdef["properties"][prop_name]
            mqtt_publish_property(wp, mqtt_client, pd, value)

# Substitute topic patterns


def mqtt_subst_topic(s, values, expand=True):
    if expand:
        s = re.sub(r'^~', Cfg.MQTT_TOPIC_PROPERTY_BASE.val, s)
    all_values = {
        "baseTopic": Cfg.MQTT_TOPIC_BASE.val,
    } | values
    return s.format(**all_values)


def mqtt_setup_client(host, port, client_id, available_topic, command_topic, username="", password=""):
    # Connect to MQTT server:
    mqtt_client = mqtt.Client(client_id)
    mqtt_client.on_message = mqtt_set_value
    _LOGGER.info(f"Connecting to MQTT host {host} on port {port} ...")
    mqtt_client.will_set(
        available_topic, payload="offline", qos=0, retain=True)
    if username != "":
        mqtt_client.username_pw_set(username, password)
    mqtt_client.connect(host, port)
    mqtt_client.loop_start()
    mqtt_client.publish(available_topic, payload="online", qos=0, retain=True)
    _LOGGER.info(f"Subscribing to command topics {command_topic}")
    mqtt_client.subscribe(command_topic)
    return mqtt_client


def mqtt_setup(wp):
    _LOGGER.debug(f"mqtt_setup(wp)")

    # Connect to MQTT server:
    mqtt_client = mqtt_setup_client(Cfg.MQTT_HOST.val, Cfg.MQTT_PORT.val, Cfg.MQTT_CLIENT_ID.val,
                                    mqtt_subst_topic(Cfg.MQTT_TOPIC_AVAILABLE.val, {}),
                                    mqtt_subst_topic(Cfg.MQTT_TOPIC_PROPERTY_SET.val, {
                                                     "propName": "+"}),
                                    Cfg.MQTT_USERNAME.val,
                                    Cfg.MQTT_PASSWORD.val,
                                    )
    Cfg.MQTT_PROPERTIES.val = mqtt_get_watched_properties(wp)
    _LOGGER.info(
        f"Registering message callback to publish updates to the following properties to MQTT: {Cfg.MQTT_PROPERTIES.val}")
    wp.add_event_handler(wattpilot.Event.WS_MESSAGE, mqtt_publish_message)
    return mqtt_client


def mqtt_stop(mqtt_client):
    if mqtt_client.is_connected():
        _LOGGER.info(f"Disconnecting from MQTT server ...")
        mqtt_client.disconnect()

# Subscribe to topic for setting property values:


def mqtt_set_value(client, userdata, message):
    global wpdef
    topic_regex = mqtt_subst_topic(
        Cfg.MQTT_TOPIC_PROPERTY_SET.val, {"propName": "([^/]+)"})
    name = re.sub(topic_regex, r'\1', message.topic)
    if not name or name == "" or not wpdef["properties"][name]:
        _LOGGER.warning(f"Unknown property '{name}'!")
    pd = wpdef["properties"][name]
    if pd['rw'] == "R":
        _LOGGER.warning(f"Property '{name}' is not writable!")
    try:
        value = int(mqtt_get_decoded_property(pd, str(message.payload.decode("utf-8"))))
    except ValueError:
        value = mqtt_get_decoded_property(pd, str(message.payload.decode("utf-8")))
    _LOGGER.info(
        f"MQTT Message received: topic={message.topic}, name={name}, value={value}")
    wp.send_update(name, value)


def mqtt_get_watched_properties(wp):
    if not Cfg.MQTT_PROPERTIES.val:
        return list(wp.allProps.keys())
    else:
        return Cfg.MQTT_PROPERTIES.val


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
        Cfg.MQTT_TOPIC_PROPERTY_BASE.val, topic_subst_map, False)
    ha_discovery_config = ha_get_default_config_for_prop(pd) | {
        "~": base_topic,
        "name": title,
        "object_id": object_id,
        "unique_id": unique_id,
        "state_topic": mqtt_subst_topic(Cfg.MQTT_TOPIC_PROPERTY_STATE.val, topic_subst_map, False),
        "availability_topic": mqtt_subst_topic(Cfg.MQTT_TOPIC_AVAILABLE.val, {}),
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": ha_device,
    }
    if "valueMap" in pd:
        ha_discovery_config["options"] = list(pd["valueMap"].values())
    if pd.get("rw", "") == "R/W":
        ha_discovery_config["command_topic"] = mqtt_subst_topic(
            Cfg.MQTT_TOPIC_PROPERTY_SET.val, topic_subst_map, False)
    ha_discovery_config = dict(
        list(ha_discovery_config.items())
        + list(ha_config.items())
    )
    if force_enablement != None:
        ha_discovery_config["enabled_by_default"] = force_enablement
    topic_cfg = mqtt_subst_topic(Cfg.HA_TOPIC_CONFIG.val, topic_subst_map)
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
        mqtt_client.publish(mqtt_subst_topic(Cfg.HA_TOPIC_CONFIG.val, topic_subst_map | {
                            "component": "sensor"}), payload, retain=True)
    if Cfg.WATTPILOT_SPLIT_PROPERTIES.val and "childProps" in pd:
        for p in pd["childProps"]:
            ha_discover_property(wp, mqtt_client, p,
                                 disable_discovery, force_enablement)


def ha_is_default_prop(pd):
    v = "homeAssistant" in pd
    if not Cfg.HA_DISABLED_ENTITIES.val:
        ha = pd.get("homeAssistant", {}) if pd.get("homeAssistant", {}) else {}
        v = v and ha.get("config", {}).get("enabled_by_default", True)
    return v


def ha_get_discovery_properties():
    global wpdef
    _LOGGER.debug(
        f"get_ha_discovery_properties(): HA_PROPERTIES='{Cfg.HA_PROPERTIES.val}', propdef size='{len(wpdef['properties'])}'")
    ha_properties = Cfg.HA_PROPERTIES.val
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
    global wpdef
    _LOGGER.info(
        f"Publishing all initial property values to MQTT to populate the entity values ...")
    for prop_name in Cfg.HA_PROPERTIES.val:
        if prop_name in wp.allProps:
            value = wp.allProps[prop_name]
            pd = wpdef["properties"][prop_name]
            mqtt_publish_property(wp, mqtt_client, pd, value)


def ha_setup(wp):
    global wpdef
    # Configure list of relevant properties:
    Cfg.HA_PROPERTIES.val = ha_get_discovery_properties()
    if Cfg.MQTT_PROPERTIES.val == [] or Cfg.MQTT_PROPERTIES.val == ['']:
        Cfg.MQTT_PROPERTIES.val = Cfg.HA_PROPERTIES.val
    # Setup MQTT client:
    mqtt_client = mqtt_setup(wp)
    # Publish HA discovery config:
    ha_discover_properties(mqtt_client, Cfg.HA_PROPERTIES.val, False)
    # Wait a bit for HA to catch up:
    wait_time = math.ceil(
        Cfg.HA_WAIT_INIT_S.val + len(Cfg.HA_PROPERTIES.val)*Cfg.HA_WAIT_PROPS_MS.val*0.001)
    if wait_time > 0:
        _LOGGER.info(
            f"Waiting {wait_time}s to allow Home Assistant to discovery entities and subscribe MQTT topics before publishing initial values ...")
        # Sleep to let HA discover the entities before publishing values
        sleep(wait_time)
    # Publish initial property values to MQTT:
    ha_publish_initial_properties(wp, mqtt_client)
    return mqtt_client


def ha_stop(mqtt_client):
    ha_discover_properties(mqtt_client, Cfg.HA_PROPERTIES.val, True)
    mqtt_stop(mqtt_client)

class Env():
    def __init__(self, datatype, default, description, name="", val="", required=False, requiredIf=None):
        self.datatype = datatype
        self.default = default
        self.description = description
        self.name = name
        self.val = val
        self.required = required
        self.requiredIf = requiredIf
    def format(self):
        val = self.val
        if self.datatype == "password" and self.val != "":
            val = "********"
        return f"{self.name}={val}"


# Wattpilot Configuration
class Cfg(Enum):
    HA_DISABLED_ENTITIES = Env("boolean", "false", "Create disabled entities in Home Assistant")
    HA_ENABLED = Env("boolean", "false", "Enable Home Assistant Discovery")
    HA_PROPERTIES = Env("list", "", "List of space-separated properties that should be discovered by Home Assistant (leave unset for all properties having `homeAssistant` set in [wattpilot.yaml](src/wattpilot/ressources/wattpilot.yaml)")
    HA_TOPIC_CONFIG = Env("string", "homeassistant/{component}/{uniqueId}/config", "Topic pattern for HA discovery config")
    HA_WAIT_INIT_S = Env("integer", "0", "Wait initial number of seconds after starting discovery (in addition to wait time depending on the number of properties). May be increased, if entities in HA are not populated with values.")
    HA_WAIT_PROPS_MS = Env("integer", "0", "Wait milliseconds per property after discovery before publishing property values. May be increased, if entities in HA are not populated with values.")
    MQTT_AVAILABLE_PAYLOAD = Env("string", "online", "Payload for the availability topic in case the MQTT bridge is online")
    MQTT_CLIENT_ID = Env("string", "wattpilot2mqtt", "MQTT client ID")
    MQTT_ENABLED = Env("boolean", "false", "Enable MQTT")
    MQTT_HOST = Env("string", "", "MQTT host to connect to", requiredIf='MQTT_ENABLED')
    MQTT_MESSAGES = Env("list", "", "List of space-separated message types to be published to MQTT (leave unset for all messages)")
    MQTT_NOT_AVAILABLE_PAYLOAD = Env("string", "offline", "Payload for the availability topic in case the MQTT bridge is offline (last will message)")
    MQTT_PASSWORD = Env("password", "", "Password for connecting to MQTT")
    MQTT_PORT = Env("integer", "1883", "Port of the MQTT host to connect to")
    MQTT_PROPERTIES = Env("list", "", "List of space-separated property names to publish changes for (leave unset for all properties)")
    MQTT_PUBLISH_MESSAGES = Env("boolean", "false", "Publish received Wattpilot messages to MQTT")
    MQTT_PUBLISH_PROPERTIES = Env("boolean", "true", "Publish received property values to MQTT")
    MQTT_TOPIC_AVAILABLE = Env("string", "{baseTopic}/available", "Topic pattern to publish Wattpilot availability status to")
    MQTT_TOPIC_BASE = Env("string", "wattpilot", "Base topic for MQTT")
    MQTT_TOPIC_MESSAGES = Env("string", "{baseTopic}/messages/{messageType}", "Topic pattern to publish Wattpilot messages to")
    MQTT_TOPIC_PROPERTY_BASE = Env("string", "{baseTopic}/properties/{propName}", "Base topic for properties")
    MQTT_TOPIC_PROPERTY_SET = Env("string", "~/set", "Topic pattern to listen for property value changes for")
    MQTT_TOPIC_PROPERTY_STATE = Env("string", "~/state", "Topic pattern to publish property values to")
    MQTT_USERNAME = Env("string", "", "Username for connecting to MQTT")
    WATTPILOT_AUTOCONNECT = Env("boolean", "true", "Automatically connect to Wattpilot on startup")
    WATTPILOT_AUTO_RECONNECT = Env("boolean", "true", "Automatically re-connect to Wattpilot on lost connections")
    WATTPILOT_CONNECT_TIMEOUT = Env("integer", "30", "Connect timeout for Wattpilot connection")
    WATTPILOT_HOST = Env("string", "", "IP address of the Wattpilot device to connect to", required=True)
    WATTPILOT_INIT_TIMEOUT = Env("integer", "30", "Wait timeout for property initialization")
    WATTPILOT_LOGLEVEL = Env("string", "INFO", "Log level (CRITICAL,ERROR,WARNING,INFO,DEBUG)")
    WATTPILOT_PASSWORD = Env("password", "", "Password for connecting to the Wattpilot device", required=True)
    WATTPILOT_RECONNECT_INTERVAL = Env("integer", "30", "Waiting time in seconds before a lost connection is re-connected")
    WATTPILOT_SPLIT_PROPERTIES = Env("boolean", "true", "Whether compound properties (e.g. JSON arrays or objects) should be decomposed into separate properties")

    @classmethod
    def set(cls, env: dict):
        for var in list(cls):
            #print(f"Setting parameter {var.name} ...")
            d = var.value
            d.name = var.name
            strval = env.get(var.name, d.default)
            if d.datatype == "boolean":
                d.val = (strval == "true")
            elif d.datatype == "integer":
                d.val = int(strval)
            elif d.datatype == "list":
                d.val = strval.split(sep=' ') if strval else []
            elif d.datatype == "password":
                d.val = strval
                if strval != "":
                    strval = "********"
            elif d.datatype == "string":
                d.val = strval
            _LOGGER.debug(f"{d.format()} (from '{strval}')")
            assert not d.required or d.val, f"{var.name} is not set!"
        for var in [e for e in list(cls) if e.value.requiredIf]:
            d = var.value
            assert not Cfg[d.requiredIf].value.val or d.val, f"{var.name} is not set (required for '{d.requiredIf}')!"

    @classmethod
    def docs_markdown(cls):
        print("|" + "|".join(["Environment Variable", "Type", "Default Value", "Description"]) + "|")
        print("|" + "|".join(["--------------------", "----", "-------------", "-----------"]) + "|")
        for e in list(cls):
            d = e.value
            print("|" + "|".join([f"`{e.name}`", f"`{d.datatype}`", f"{'`'+d.default+'`' if d.default else ''}", d.description]) + "|")

    @property
    def val(self):
        return self.value.val

    @val.setter
    def val(self,value):
        self.value.val = value


#### Main Program ####

def main():
    global mqtt_client
    global wp
    global wpdef

    # Set debug level:
    logging.basicConfig(level=os.environ.get('WATTPILOT_LOGLEVEL','INFO').upper())

    # Setup environment variables:
    Cfg.set(os.environ)

    # Initialize globals:
    mqtt_client = None
    wp = wp_initialize(Cfg.WATTPILOT_HOST.val, Cfg.WATTPILOT_PASSWORD.val)
    wpdef = wp_read_apidef() # TODO: Should be part of the wattpilot core library!

    # Initialize shell:
    wpsh = WattpilotShell(wp, wpdef)
    if Cfg.WATTPILOT_AUTOCONNECT.val:
        _LOGGER.info("Automatically connecting to Wattpilot ...")
        wpsh.do_connect("")
        # Enable MQTT and/or HA integration:
        if Cfg.MQTT_ENABLED.val and not Cfg.HA_ENABLED.val:
            wpsh.do_mqtt("start")
        elif Cfg.MQTT_ENABLED.val and Cfg.HA_ENABLED.val:
            wpsh.do_ha("start")
        wpsh.do_info("")
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
