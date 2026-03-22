# ADR-0007: Adopt OpenSpec for Spec-Driven Development

**Date**: 2025-06-01

**Status**: accepted

## Context

As code-context-agent matured past v7.0, the pace of changes accelerated with AI-assisted development. Multiple features, refactors, and integrations could be in flight simultaneously. Without a structured workflow for proposing and tracking changes, the project faced:

- Ad-hoc feature proposals scattered across commits, Slack threads, and mental notes
- No systematic design review before implementation
- Difficulty tracking what changes are in progress, planned, or completed
- No connection between high-level proposals and concrete implementation tasks

The team uses AI coding assistants extensively (Claude Code, Cursor), which can generate artifacts quickly but benefit from structured templates that define what needs to be produced.

## Decision

Adopt OpenSpec with the `spec-driven` schema for managing change proposals and specifications.

The OpenSpec directory structure at `openspec/` contains:

```
openspec/
  config.yaml          # Schema declaration (spec-driven)
  specs/               # Feature specifications with design docs
  changes/             # Change proposals and tracking
    archive/           # Completed/rejected changes
```

The workflow follows the spec-driven lifecycle:

1. **Proposal**: A change starts as a proposal document describing the problem, proposed solution, and scope
2. **Specs**: Accepted proposals get detailed specifications with technical design, interface contracts, and data models
3. **Design**: Architecture decisions and integration points are documented (linking to ADRs where appropriate)
4. **Tasks**: Specifications are broken into concrete implementation tasks with acceptance criteria

This integrates with the project's existing conventions:
- ADRs (this directory) capture architectural decisions that emerge from specs
- Conventional commits link implementation to specs via commit messages
- The `mise run` task runner executes checks that specs reference

## Consequences

**Positive:**

- Consistent change management: every significant change has a proposal, design, and task breakdown before implementation begins
- AI-friendly artifact generation: structured templates let AI assistants produce high-quality specs and task lists
- Traceability: proposals link to specs, specs link to ADRs, ADRs link to code paths
- The archive pattern preserves history of completed and rejected changes

**Negative:**

- Process overhead for small changes; trivial bug fixes do not need a full spec workflow
- The `spec-driven` schema is specific to OpenSpec tooling; teams unfamiliar with OpenSpec need onboarding
- Empty `specs/` and `changes/` directories indicate the workflow is newly adopted and has no track record yet in this project

**Neutral:**

- The `config.yaml` currently has minimal configuration (schema declaration only); project context and per-artifact rules can be added as the workflow matures
- OpenSpec does not enforce any specific CI/CD integration; it is purely a document organization convention
