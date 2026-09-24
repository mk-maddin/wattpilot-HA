# AGENTS.md

Guidelines for agents working on this project. These rules apply to automated contributors and to any other contributor working in the repository.

## 1. Ownership and Maintenance of This File

Agents own and maintain this file. Keeping it current is part of completing the work, not an optional courtesy for the next contributor.

No human reviews changes made here. Therefore, the agent making a change is responsible for ensuring that the guidance remains accurate, useful and justified.

### Rules for Maintaining This Guidance

- Record lessons learned in the same change that revealed them.
  - The next agent starts with this file. Missing knowledge can cause avoidable work or regressions.
- Include the reason for every new rule.
  - State the rationale directly below the rule or in an immediately associated sub-bullet.
  - The rationale must explain the concrete risk, failure mode or maintenance cost that the rule prevents.
  - Rules without rationale are likely to be removed when they appear inconvenient.
- When modifying this file, add a rationale to an existing rule that lacks one if that rule is touched, relied upon or closely related to the change.
  - Do not rewrite unrelated rules solely to standardise wording.
- Add only rules that have been earned through a real issue, constraint or failure.
  - Unnecessary rules add noise and reduce the usefulness of this document.
- Keep this direct writing style within this project only.
  - It is intended to prevent agents from accidentally breaking the integration.

## 2. Role and Repository Scope

You are an experienced Python and Home Assistant integration developer.

Handle the repository below carefully, using minimal and traceable changes:

https://github.com/mk-maddin/wattpilot-HA

## 3. Context and Repository Structure

### 3.1 Purpose and Supported Systems

This project is a Home Assistant custom integration for Fronius Wattpilot wallboxes.

Supported systems and connection types:

- Wattpilot
- Wattpilot V2
- Wattpilot flex from firmware version 42.8 onwards
- Local LAN connections
- Cloud connections

The core integration is located under:

```text
custom_components/wattpilot/
```

Its functionality includes:

- Setup through a config flow
- Connection via local IP address or cloud/serial number
- Control of the charging mode
- Starting and stopping charging
- Configuration of various charging behaviours
- Sensors for status and measurement values
- Manual disconnection and reconnection of the wallbox
- Services, for example for next-trip scheduling and logging

### 3.2 Wattpilot Communication and Local Library

The integration communicates with Wattpilot wallboxes through an unofficial, partially reverse-engineered API.

The project originally used this external Python library:

https://github.com/joscha82/wattpilot

This library uses a partially undocumented WebSocket API to communicate with Fronius Wattpilot wallboxes.

Because the external library is developed only sporadically, the integration contains an adapted and further-developed local copy. This local copy is authoritative and is located under:

```text
custom_components/wattpilot/wattpilot/
```

#### Internal Wattpilot Package Versioning

- Changes within the internal Wattpilot Python package at
  `custom_components/wattpilot/wattpilot/` should be rare.
- When such a change is made, update the package version in both
  `custom_components/wattpilot/wattpilot/src/wattpilot/__init__.py` and
  `custom_components/wattpilot/wattpilot/PKG-INFO` for every change until the
  next pull request.
- Increment the suffix alphabetically: `0.2.2d`, `0.2.2e`, …, `0.2.2z`, then
  `0.2.2aa`, `0.2.2ab`, …, `0.2.2az`, `0.2.2ba`, `0.2.2bb`, …, up to `0.2.2zz`.

Rationale:
- The internal package is maintained as part of the integration and may be
  consumed independently within the repository. Keeping both version
  declarations synchronised makes package changes traceable and prevents
  inconsistent version information during development before the next pull
  request.

#### Constant Naming in the Internal Wattpilot Package

- Constants for the integrated Wattpilot Python package must always use the
  `CONST_` prefix.

Rationale:
- A consistent prefix makes package constants immediately recognisable and
  prevents naming conflicts with variables, functions and other module-level
  names.

#### Requirements for Communication and API Changes

- Review and implement changes to wallbox communication, data models or API abstraction primarily in:

  ```text
  custom_components/wattpilot/wattpilot/
  ```

- Treat the external library only as a historical origin and, where useful, as a reference.
- Do not add or update the external library as a runtime dependency unless this is expressly requested.

The Fronius Wattpilot wallbox is technically based on the go-e Charger, with customised firmware. The go-e Charger may therefore provide useful context when investigating Wattpilot behaviour:

https://github.com/goecharger/go-eCharger-API-v2

However:

- Do not adopt API behaviour or properties from that reference without verification.
- First verify that the property exists in the local Wattpilot library.
- Verify support for the affected Wattpilot model and its firmware.
- Treat reverse-engineered or observed API behaviour as unverified until it has been validated using real data, existing tests or traceable device evidence.
- Do not implement such behaviour until it has also been approved by a human reviewer.
  - Reverse-engineered behaviour may vary by model or firmware; technical validation and human approval reduce the risk of unsafe or incorrect wallbox control.

### 3.3 Entity Definitions

Home Assistant entities are defined per platform in YAML files, referred to as `entities_cfg` files. Examples include:

```text
sensor.yaml
binary_sensor.yaml
switch.yaml
select.yaml
button.yaml
number.yaml
```

Each YAML file begins with a comment listing available properties and their explanations or descriptions.

#### Requirements for `entities_cfg` Files

- Treat the property-overview comment as binding guidance when modifying entities.
- Keep the overview current whenever available properties, their meaning or their platform assignment changes.
- For every new `entity_cfg` property, update the property-overview comment in every affected `entities_cfg` YAML file.
- Use the exact configuration key names used in the implementation.
- Preserve the existing compact comment style.
- Do not replace a required one-line property description with a longer paragraph or a new formatting style.
- When adding a property, include a description and examples.
- Where a property has a limited set of permitted values, list those values in the comment.
- Keep Home Assistant metadata, translations, YAML definitions and tests consistent when adding or changing entities, services or attributes.
  - Home Assistant exposes entities and services through several connected definitions; incomplete updates create broken setup, missing UI text or inconsistent behaviour.

## 4. Working Principles

### 4.1 Before Implementing Changes

First analyse the relevant repository areas:

- Repository structure
- README
- Manifest
- Config flow
- Coordinator
- Entity platforms
- Services
- Translations
- Existing tests

### 4.2 Change Scope

- Change only files necessary for the requested task.
- Before completion, verify that the change set contains no unintended modifications, generated files, local artefacts or formatting-only changes outside the task scope.
  - Unrelated changes make reviews, debugging and rollback harder and can introduce regressions outside the requested task.
- Implement the smallest working solution.
- Prefer fixing the root cause over adding a workaround.
  - Workarounds can conceal the underlying defect, increase maintenance complexity and allow the same failure to recur in another execution path.
- Do not remove existing code merely to simplify it when its purpose is unclear.
- Prefer small, focused commits or logically separated changes.
- If requirements are unclear or essential information is missing, ask specific questions before inventing functionality.

### 4.3 Home Assistant and Python Requirements

Follow Home Assistant conventions and current Python best practices:

- Use asynchronous APIs. Do not make blocking calls in the event loop.
- Use a `DataUpdateCoordinator`, or respect the existing coordinator logic.
- Keep unique entity IDs stable.
- Assign new entities cleanly to the appropriate platforms, such as `sensor`, `binary_sensor`, `switch`, `select`, `button` and `number`.
- Write clear, maintainable and typed Python code consistent with the repository style.
- Place constants for the Home Assistant integration in `custom_components/wattpilot/const.py`.
  - A central constants module prevents duplicated definitions, keeps shared integration values discoverable and maintains the repository's established module structure.
- Write every `_LOGGER` call on a single line. Do not split `_LOGGER` calls across multiple lines.

### 4.4 Compatibility, Safety and Behaviour

- Maintain user-visible text through the existing translation files.
- Never log sensitive credentials.
- Treat local and cloud connections as separate, potentially error-prone paths.
  - Errors must be handled clearly and must not block Home Assistant.
- Preserve backwards compatibility.
  - Do not change existing configuration data, entity unique IDs, service names or attributes without a compelling reason and a migration path.
  - Changes to persisted configuration data require an explicit migration strategy, tests for existing installations, and documented fallback or error handling.
  - Existing installations retain configuration across updates; incompatible changes can otherwise prevent setup or silently alter user configuration.
- Do not use API calls or assumptions unsupported by the installed Wattpilot Python client or existing code.
- Introduce new or changed dependencies only when justified and after checking licence, security and compatibility implications.
  - Keep dependency definitions and lockfiles consistent where they exist.
  - Do not perform unrequested dependency upgrades.
  - Unreviewed dependency changes can introduce security vulnerabilities, licensing conflicts, compatibility issues and unplanned maintenance work.
- Do not create, modify, remove or rename any licence file, licence notice, copyright notice or licence-related repository metadata.
- Do not create a commit that changes the repository licence or the licensing terms of repository content.
- If an agent identifies a potential need for a licence change, it must only report:
  - Why the current licence may be unsuitable.
  - The affected files, dependencies or distribution scenario.
  - A recommended target licence and the compatibility reasoning for that recommendation.
  - Any legal, contributor-consent or downstream-compatibility risks.
- A human person must explicitly decide on, create and commit every licence change.
  - Licence changes can affect legal rights, contributor agreements, dependency compatibility and downstream use. They require a human decision and must not be made autonomously by an agent.
- Do not include production credentials, serial numbers, IP addresses or personal data in tests, fixtures, logs, commits or documentation.
  - Consistently anonymise sensitive example values.
  - Test artefacts, logs and documentation are often shared or retained, so sensitive production data can be exposed beyond its intended audience.
- When communication fails, follow existing Home Assistant conventions for availability, exceptions and recovery.
  - Do not hide errors by inventing fallback values.
  - Invented fallback values can conceal communication failures and lead users to make charging decisions based on incorrect wallbox state.
- Do not change wallbox behaviour, particularly start/stop, current, charging scheduling or cloud usage, unless explicitly requested.
- If a change affects a potentially security- or cost-relevant cloud function:
  - Explicitly identify the risk.
  - Implement it only after clear approval.

### 4.5 Comments, Commits and Pull Requests

- Code comments, commit titles and commit descriptions must be written in English.
- Do not delete, shorten or reword existing comments unless expressly requested.
- Do not add comments to source code unless expressly requested.
  - Exceptions: mandatory metadata or existing project-wide conventions.
- Clearly describe created or changed source code in the associated commit description.
- Never create a pull request or perform PR-related actions unless expressly requested.

### 4.6 Versioning

Check versioning before changing the integration:

- Update `custom_components/wattpilot/manifest.json` when the latest repository release has the same or a higher version number than the branch being worked on.
- Never update `custom_components/wattpilot/manifest.json` when the latest repository release has a lower version number than the branch being worked on.
  - Preventing version downgrades preserves correct release ordering and avoids replacing a newer branch version with an older release version.

## 5. Data-File Inspection

Apply these requirements when a task concerns attached or repository data files, especially JSON, CSV, YAML or similarly structured files.

### 5.1 General Inspection Requirements

- Inspect every relevant file directly from the filesystem or sandbox.
- Do not rely solely on semantic file-search excerpts when exhaustive results are required.
- Before analysis:
  - Enumerate all matching files.
  - Verify that each expected file is readable.
  - Verify that every expected file is included.
- If a file is unavailable or cannot be read, state this before presenting results as complete.

### 5.2 JSON Requirements

For JSON files:

- Parse the complete document recursively, including nested objects and arrays.
- Never infer that a property is absent from incomplete search excerpts.

When the user requests all values for one or more properties:

1. Report every occurrence with:
   - Filename
   - JSON path
   - Property name
   - Exact value
2. Provide a separate list of unique values for each property.
3. Preserve duplicate occurrences in the occurrence list.
4. Explicitly report files in which a requested property does not occur.
5. Validate the result by:
   - Comparing the number of parsed files with the expected number of files
   - Reporting parsing errors

For Wattpilot JSON export files, perform exhaustive property analysis programmatically. Search properties recursively across all JSON files and report exact values.

## 6. Procedure for Every Task

### 6.1 Implementation Process

1. Briefly summarise the relevant existing implementation.
2. Name the affected files and briefly justify each planned change.
3. Implement the smallest working solution.
4. Add or update tests if a test structure exists in the repository.
5. Verify at least:
   - Syntax and imports
   - Async behaviour
   - Setup, unload and reload of the integration
   - Error handling when the wallbox cannot be reached
   - Translations for new visible text
   - No regression of existing entities and services
6. Document the commands actually executed for testing and verification, together with their results.
   - Clearly identify checks that were not run and explain why.
   - Recorded commands and results make verification reproducible and clearly distinguish tested behaviour from assumptions.
7. Do not claim that a change works unless it has been run and verified.
   - State plainly what was verified, what was assumed and what could not be checked.
   - If verification requires a real Fronius/SolarWeb account, Wattpilot device or unavailable hardware, state that limitation rather than implying coverage.
   - Unverified claims can hide failures on real devices and may result in silent data loss or incorrect behaviour for other users.
8. Write all documentation in English.
   - Update user-facing documentation, including README, configuration guidance and service documentation, whenever installation, configuration or visible behaviour changes.
   - Do not change documentation when the implementation change has no impact on installation, configuration or user-visible behaviour.
   - English documentation is accessible to the project’s international contributors and users, while timely updates prevent configuration and service behaviour from being misrepresented.

### 6.2 Required Final Report

At the end of the task, provide:

- Overview of changed files
- Description of the behavioural change
- Tests and verification results
- Remaining risks, open assumptions or manual verification steps

## 7. Maintaining This Working Context

Update this working context whenever repository structure changes.

Relevant changes include:

- Directories
- Module boundaries
- Local libraries
- Entity definition files
- Supported platforms
- Configuration structures
- Service structures
- Central integration paths

If such a change is implemented:

- Update the affected information in this file in the same commit.
- Add a new rule only when the triggering technical finding, concrete failure case or verified repository change is traceably documented in the same change.
- Write the commit title and commit description in English.

## 8. Agent Instruction Files

This repository uses `AGENTS.md` as the single authoritative source for instructions for AI agents.

The following repository instruction files are pointers to this file and must not contain conflicting or independent project rules:

- `CLAUDE.md` in the repository root
- `GEMINI.md` in the repository root
- `.github/copilot-instructions.md`
- `CODEWHISPERER.md` in the repository root
- `replit.md` in the repository root
- `AI_INSTRUCTIONS.md` in the repository root

Before planning or modifying the repository, read and apply the applicable `AGENTS.md` file. If multiple `AGENTS.md` files exist in the directory hierarchy, apply the file with the narrowest applicable scope together with the relevant parent instructions.

If another instruction file conflicts with `AGENTS.md`, treat `AGENTS.md` as the authoritative project guidance unless the agent's platform-specific rules require otherwise. Do not duplicate, weaken or silently override rules from `AGENTS.md` in the pointer files.

Rationale:
- Centralising project guidance reduces conflicting instructions, prevents duplicated rules from becoming inconsistent and gives agents one maintained source of truth.
- Hierarchical handling is required because repository subdirectories may contain more specific instructions for a narrower scope.
Die Struktur wurde so überarbeitet, dass Regeln, Begründungen, Prüfschritte und Erweiterungspflichten für Agenten eindeutig auffindbar bleiben. Grundlage waren die verfügbaren Inhalte der angehängten Datei.Sources:
[1] AGENTS.md