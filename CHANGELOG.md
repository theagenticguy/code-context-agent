## v1.0.0 (2026-01-18)

### BREAKING CHANGE

- Renamed FAST_MODE_SOP → FAST_PROMPT, DEEP_MODE_SOP → DEEP_PROMPT

### Feat

- **agent**: refactor prompts with separate FAST/DEEP modes and steering support
- **agent**: add exit criteria, output format requirements, and fix STDIO capture

## v0.4.0 (2026-01-17)

### Feat

- **agent**: add focus arg, graph tool, 1M context, and fix stdio

## v0.3.7 (2026-01-17)

### Fix

- stdio for ag ui

## v0.3.6 (2026-01-17)

### Fix

- **agent**: disable shell approval prompts and count actual turns

## v0.3.5 (2026-01-14)

### Feat

- **cli**: add --debug flag to analyze command for troubleshooting

## v0.3.4 (2026-01-14)

### Fix

- **telemetry**: patch OTEL context detach to suppress async generator errors

## v0.3.3 (2026-01-14)

### Fix

- **telemetry**: disable OpenTelemetry by default to avoid context detachment errors

## v0.3.2 (2026-01-14)

### Fix

- **config**: set default temperature to 1.0 for extended thinking

## v0.3.1 (2026-01-14)

### Fix

- **docs**: add basic README content
- **config**: use pep621 version_provider for commitizen

## v0.3.0 (2026-01-14)

### Feat

- add agent-based code context analysis system

## v0.2.0 (2026-01-14)

### Feat

- init the package
