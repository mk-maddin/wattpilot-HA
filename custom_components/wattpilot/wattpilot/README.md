# Wattpilot

> :warning: This project is still in early development and might never leave this state

`wattpilot` is a Python 3 (>= 3.10) module to interact with Fronius Wattpilot wallboxes which do not support (at the time of writting) a documented API. This functionality of this module utilized a undocumented websockets API, which is also utilized by the official Wattpilot.Solar mobile app.

## Wattpilot API Documentation

See [API.md](API.md) for the current state of the API documentation this implementation is based on.

It has been compiled from different sources, but primarily from:

* [go-eCharger-API-v1](https://github.com/goecharger/go-eCharger-API-v1/blob/master/go-eCharger%20API%20v1%20EN.md)
* [go-eCharger-API-v2](https://github.com/goecharger/go-eCharger-API-v2/blob/main/apikeys-en.md)

## Wattpilot Shell

The shell provides an easy way to explore the available properties and get or set their values.

```bash
# Install the wattpilot module, if not yet done so:
pip install .
```

Run the interactive shell

```bash
# Usage:
export WATTPILOT_HOST=<wattpilot_ip>
export WATTPILOT_PASSWORD=<password>
wattpilotshell
Welcome to the Wattpilot Shell 0.2.   Type help or ? to list commands.

wattpilot> help

Documented commands (type help <topic>):
========================================
EOF      exit  ha    info  properties  server  unwatch  watch
connect  get   help  mqtt  rawvalues   set     values 
```

The shell supports TAB-completion for all commands and their arguments.
Detailed documentation can be found in [ShellCommands.md](ShellCommands.md).

It's also possible to pass a single command to the shell to integrate it into scripts:

```bash
# Usage:
wattpilotshell <wattpilot_ip> <password> "<command> <args...>"

# Examples:
wattpilotshell <wattpilot_ip> <password> "get amp"
wattpilotshell <wattpilot_ip> <password> "set amp 6"
```

## MQTT Bridge Support

It is possible to publish JSON messages received from Wattpilot and/or individual property value changes to an MQTT server.
The easiest way to start the shell with MQTT support is using these environment variables:

```bash
export MQTT_ENABLED=true
export MQTT_HOST=<mqtt_host>
export WATTPILOT_HOST=<wattpilot_ip>
export WATTPILOT_PASSWORD=<wattpilot_password>
wattpilotshell
```

Pay attention to environment variables starting with `MQTT_` to fine-tune the MQTT support (e.g. which messages or properties should published to MQTT topics).

MQTT support can be easily tested using mosquitto:

```bash
# Start mosquitto in a separate console:
mosquitto

# Subscribe to topics in a separate console:
mosquitto_sub -t 'wattpilot/#' -v
```

## Home Assistant MQTT Discovery Support

To enable Home Assistant integration (using MQTT) set `MQTT_ENABLED` and `HA_ENABLED` to `true` and make sure to correctly configure the [MQTT Integration](https://www.home-assistant.io/integrations/mqtt).
It provides auto-discovery of entities using property configuration from [wattpilot.yaml](src/wattpilot/ressources/wattpilot.yaml).
The is the simplest possible way to start the shell with HA support:

```bash
export MQTT_ENABLED=true
export HA_ENABLED=true
export MQTT_HOST=<mqtt_host>
export WATTPILOT_HOST=<wattpilot_ip>
export WATTPILOT_PASSWORD=<wattpilot_password>
wattpilotshell
```

Pay attention to environment variables starting with `HA_` to fine-tune the Home Assistant integration (e.g. which properties should be exposed).

The discovery config published to MQTT can be tested using this in addition to the testing steps from MQTT above:

MQTT support can be easily tested using mosquitto:

```bash
# Subscribe to homeassisant topics in a separate console:
mosquitto_sub -t 'homeassistant/#' -v
```

## Docker Support

The Wattpilot MQTT bridge with Home Assistant MQTT discovery can be run as a docker container.
Here's how to do that:

```bash
# Build image:
docker-compose build

# Create .env file with environment variables:
cat .env
HA_ENABLED=true
MQTT_ENABLED=true
MQTT_HOST=<mqtt_host>
WATTPILOT_HOST=<wattpilot_ip>
WATTPILOT_PASSWORD=<my_secret_password>

# Run container (recommended with MQTT_ENABLED=true and HA_ENABLED=true - e.g. on a Raspberry Pi):
docker-compose up -d
```

To diagnose the hundreds of Wattpilot parameters the shell can be started this way (typically recommended with `MQTT_ENABLED=false` and `HA_ENABLED=false` on a local machine, in case a Docker container with MQTT support may be running permanently on e.g. a Raspberry Pi):

```bash
# Create .env file with environment variables:
cat .env
HA_ENABLED=false
MQTT_ENABLED=false
MQTT_HOST=<mqtt_host>
WATTPILOT_HOST=<wattpilot_ip>
WATTPILOT_PASSWORD=<my_secret_password>

# Run the shell:
docker-compose run wattpilot shell
```

## Environment Variables

| Environment Variable        | Description                                                                                                                                                                                  | Default Value                                 |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `HA_ENABLED`                | Enable Home Assistant Discovery                                                                                                                                                              | `false`                                       |
| `HA_PROPERTIES`             | Only discover given properties (leave unset for all properties having `homeAssistant` set in [wattpilot.yaml](src/wattpilot/ressources/wattpilot.yaml))                                                                               |                                               |
| `HA_TOPIC_CONFIG`           | Topic pattern for HA discovery config                                                                                                                                                        | `homeassistant/{component}/{uniqueId}/config` |
| `HA_WAIT_INIT_S`            | Wait initial number of seconds after starting discovery (in addition to wait time depending on the number of properties). May be increased, if entities in HA are not populated with values. | `5`                                           |
| `HA_WAIT_PROPS_MS`          | Wait milliseconds per property after discovery before publishing property values. May be increased, if entities in HA are not populated with values.                                         | `50`                                          |
| `MQTT_AVAILABLE_PAYLOAD`    | Payload for the availability topic in case the MQTT bridge is online                                                                                                                                                                                | `online`                              |
| `MQTT_CLIENT_ID`            | MQTT client ID                                                                                                                                                                               | `wattpilot2mqtt`                              |
| `MQTT_ENABLED`              | Enable MQTT                                                                                                                                                                                  | `false`                                       |
| `MQTT_HOST`                 | MQTT host to connect to                                                                                                                                                                      |                                               |
| `MQTT_MESSAGES`             | List of space-separated message types to be published to MQTT (leave unset for all messages)                                                                                                 |                                               |
| `MQTT_NOT_AVAILABLE_PAYLOAD` | Payload for the availability topic in case the MQTT bridge is offline (last will message)                                                                                                                                                                               | `offline`                              |
| `MQTT_PORT`                 | Port of the MQTT host to connect to                                                                                                                                                          | `1883`                                        |
| `MQTT_PROPERTIES`           | List of space-separated property names to publish changes for (leave unset for all properties)                                                                                               |                                               |
| `MQTT_PUBLISH_MESSAGES`     | Publish received Wattpilot messages to MQTT                                                                                                                                                  | `false`                                       |
| `MQTT_PUBLISH_PROPERTIES`   | Publish received property values to MQTT                                                                                                                                                     | `true`                                        |
| `MQTT_TOPIC_AVAILABLE`      | Topic pattern to publish Wattpilot availability status to                                                                                                                                               | `{baseTopic}/available`          |
| `MQTT_TOPIC_BASE`           | Base topic for MQTT                                                                                                                                                                          | `wattpilot`                                   |
| `MQTT_TOPIC_MESSAGES`       | Topic pattern to publish Wattpilot messages to                                                                                                                                               | `{baseTopic}/messages/{messageType}`          |
| `MQTT_TOPIC_PROPERTY_BASE`  | Base topic for properties                                                                                                                                                                    | `{baseTopic}/properties/{propName}`           |
| `MQTT_TOPIC_PROPERTY_SET`   | Topic pattern to listen for property value changes for                                                                                                                                       | `~/set`                                       |
| `MQTT_TOPIC_PROPERTY_STATE` | Topic pattern to publish property values to                                                                                                                                                  | `~/state`                                     |
| `WATTPILOT_AUTOCONNECT`     | Automatically connect to Wattpilot on startup                                                                                                                                                | `true`                                        |
| `WATTPILOT_CONNECT_TIMEOUT` | Connect timeout for Wattpilot connection                                                                                                                                                     | `30`                                          |
| `WATTPILOT_DEBUG_LEVEL`     | Debug level                                                                                                                                                                                  | `INFO`                                        |
| `WATTPILOT_HOST`            | IP address of the Wattpilot device to connect to                                                                                                                                             |                                               |
| `WATTPILOT_INIT_TIMEOUT`    | Wait timeout for property initialization                                                                                                                                                     | `30`                                          |
| `WATTPILOT_PASSWORD`        | Password for connecting to the Wattpilot device                                                                                                                                              |                                               |
| `WATTPILOT_SPLIT_PROPERTIES` | Whether compound properties (e.g. JSON arrays or objects) should be decomposed into separate properties                                                                                      | `true`                                        |

## HELP improving API definition in wattpilot.yaml

The MQTT and Home Assistant support heavily depends on the API definition in [wattpilot.yaml](src/wattpilot/ressources/wattpilot.yaml) which has been compiled from different sources and does not yet contain a full set of information for all relevant properties.
See [API.md](API.md) for a generated documentation of the available data.

If you want to help, please have a look at the properties defined in [wattpilot.yaml](src/wattpilot/ressources/wattpilot.yaml) and fill in the missing pieces (e.g. `title`, `description`, `rw`, `jsonType`, `childProps`, `homeAssistant`, `device_class`, `unit_of_measurement`, `enabled_by_default`) to properties you care about.
The file contains enough documentation and a lot of working examples to get you started.
