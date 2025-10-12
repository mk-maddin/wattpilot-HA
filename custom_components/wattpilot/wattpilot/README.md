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

Documented commands (use 'help -v' for verbose/'help <topic>' for details):
===========================================================================
alias       docs  ha       macro       propset       run_script  shortcuts
config      edit  help     mqtt        quit          server      unwatch  
connect     EOF   history  properties  rawvalues     set         values   
disconnect  exit  info     propget     run_pyscript  shell       watch    
```

The shell supports TAB-completion for all commands and their arguments.
Detailed documentation can be found in [ShellCommands.md](ShellCommands.md).

It's also possible to pass a single command to the shell to integrate it into scripts:

```bash
# Usage:
wattpilotshell "<command> <args...>"

# Examples:
wattpilotshell "propget amp"
wattpilotshell "propset amp 6"
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

The Docker images for the Wattpilot MQTT bridge with Home Assistant MQTT discovery can be found on [GitHub Packages](https://github.com/joscha82/wattpilot/pkgs/container/wattpilot):

```bash
# Pull Image:
docker pull ghcr.io/joscha82/wattpilot:latest
# NOTE: Use the tag 'latest' for the latest release, a specific release version or 'main' for the current image of the not yet released main branch.

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

For a complete list of supported environment variables see [ShellEnvVariables.md](ShellEnvVariables.md).

## HELP improving API definition in wattpilot.yaml

The MQTT and Home Assistant support heavily depends on the API definition in [wattpilot.yaml](src/wattpilot/ressources/wattpilot.yaml) which has been compiled from different sources and does not yet contain a full set of information for all relevant properties.
See [API.md](API.md) for a generated documentation of the available data.

If you want to help, please have a look at the properties defined in [wattpilot.yaml](src/wattpilot/ressources/wattpilot.yaml) and fill in the missing pieces (e.g. `title`, `description`, `rw`, `jsonType`, `childProps`, `homeAssistant`, `device_class`, `unit_of_measurement`, `enabled_by_default`) to properties you care about.
The file contains enough documentation and a lot of working examples to get you started.
