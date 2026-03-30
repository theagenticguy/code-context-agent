## v10.1.0 (2026-03-30)

### Feat

- fix viz UI, enrich graph with semantic edges, add multi-pass narrative quality (#28)

## v10.0.1 (2026-03-29)

## v10.0.0 (2026-03-29)

### BREAKING CHANGE

- Default pipeline changed from sequential Swarm to
coordinator with parallel teams. Set CODE_CONTEXT_PIPELINE=swarm to
restore previous behavior.
- removes swarm pipeline, old coordinator prompt, analyst
sub-agents, and 10-phase analysis model. Single coordinator-driven pipeline
with progressive disclosure replaces all prior analysis modes.

### Feat

- coordinator agent with parallel swarm teams (#26)

## v9.0.2 (2026-03-28)

## v9.0.1 (2026-03-27)

### Fix

- add graph mutation tools to Swarm and auto-index before analysis (#20)

## v9.0.0 (2026-03-26)

### BREAKING CHANGE

- `--next-ui` flag removed from `viz` command. The multi-view
ui-next visualizer is now the default. Use `--legacy-viz` for the old
single-page D3.js visualizer.
- The `src/code_context_agent/viz/` directory and
`--legacy-viz` flag are removed. The ui-next multi-view visualizer
is now the sole visualization option.

### Feat

- fix TUI swarm tool counter, remediate docs drift, default to ui-next viz (#19)

## v8.1.0 (2026-03-26)

### Feat

- **ui**: Pure HTML/CSS/JS visualizer with neobrutalism design (#18)

## v8.0.1 (2026-03-24)

### Fix

- auto-detect tsserver path and fix jscpd clone detection (#16)

## v8.0.0 (2026-03-24)

### Feat

- v8 index-first pipeline with Strands Swarm, kill AG-UI (#12)

## v7.2.0 (2026-03-22)

### Feat

- adapt GitNexus patterns — blast radius, flows, indexer, registry, BM25, KuzuDB, viz (#11)

## v7.1.0 (2026-03-14)

### Feat

- Phase 6.5 Deep Read + viz packaging fix + CI bump (#8)

### Fix

- **ci**: use BUMP_TOKEN PAT to bypass branch ruleset
- **ci**: add graphviz system deps to bump workflow
- **ci**: exclude false-positive semgrep jinja2 XSS rule (#6)

## v7.0.0 (2026-03-13)

### BREAKING CHANGE

- create_all_hooks() now accepts full_mode kwarg;
get_prompt() now accepts mode kwarg; run_analysis() now accepts
mode kwarg; create_agent() now accepts mode parameter.

### Feat

- add --full exhaustive analysis mode (v7.0.0)

### Fix

- sync uv.lock after v6.1.1 version bump

## v6.1.1 (2026-03-13)

### Fix

- **security**: pin actions by SHA, scope workflow permissions, resolve code scanning findings

## v6.1.0 (2026-03-10)

### Feat

- add security hardening, Apache 2.0 license, and comprehensive README
- add code health analysis tools (clone detection, unused symbols, refactoring candidates)
- add --output-format json, --since, and fix quiet mode hang
- add code_graph_ingest_git tool for git-to-graph pipeline

### Fix

- ignore extra env vars from .env files in foreign directories
- mise
- **ci**: pin osv-scanner-action to v2.3.3 (no major version tag exists)
- **ci**: pin osv-scanner to v1, fix scorecard permissions scope
- **ci**: use setup-uv action instead of container images, pin scorecard version, fix CodeQL permissions

## v6.0.0 (2026-03-01)

### Fix

- **ci**: use cz version --project instead of cz version
- **ci**: add self-healing tag recovery and atomic push to release script
- **ci**: fetch tags after setting authenticated remote in bump job
- **ci**: disable unused security tools in bump job

## v5.4.1 (2026-02-28)

### Fix

- **ci**: fetch tags in bump job and suppress cz interactive prompt
- **ci**: use pinned uv 0.9.30 image tag (0.10 not yet published)
- **ci**: sync uv.lock version and upgrade CI to uv 0.10
- **ci**: sync uv.lock after cz bump in release script

### Refactor

- **ci**: centralize uv sync into shared install job

## v5.4.0 (2026-02-27)

### Feat

- updates
- replace lefthook code-critic with Claude Code PreToolUse hook
- add AI code-critic pre-commit and pre-push hooks
- **security**: add comprehensive DevSecOps pipeline with bandit, SBOM, license checks, and more

### Fix

- **ci**: move multi-line mise tasks to file-based scripts
- **ci**: use shebangs instead of shell property in mise tasks
- resolve ruff lint and format violations
- **ci**: resolve guarddog DNS failure in CI environment
- **ci**: fix trivy entrypoint and switch to filesystem scan
- **ci**: resolve bandit, osv-scanner, and gitleaks CI job failures
- **ci**: consolidate deps-update script into single block for GitLab YAML validation
- **ci**: use bash for release task and skip unneeded tools in bump job

### Refactor

- **security**: replace pip-audit with osv-scanner for dependency scanning

## v5.3.0 (2026-02-25)

### Feat

- **viz**: improve contrast, font sizes, edge visibility, and add autocomplete

## v5.2.0 (2026-02-25)

### Feat

- **viz**: redesign UI with dark precision SaaS aesthetic

## v5.1.0 (2026-02-25)

### BREAKING CHANGE

- None. All existing CLI commands and tool interfaces unchanged.

### Feat

- add MCP server and context7 integration

## v5.0.4 (2026-02-25)

### Fix

- handle workspace/configuration requests to unblock Pyright initialization
- resolve ruff lint warnings in viz CLI command

## v5.0.3 (2026-02-25)

### Fix

- entry point fallback should not filter by node type

## v5.0.2 (2026-02-25)

### Fix

- add viz tooltips, broaden entry point detection, and optimize LSP performance

## v5.0.1 (2026-02-25)

### Fix

- resolve viz landing page bleed-through and add mermaid rendering

## v5.0.0 (2026-02-25)

### Feat

- add interactive visualization UI for analysis results
- add lefthook git hooks and mise.toml task runner

### Fix

- install git in test job for git tool tests
- use full git clone depth for test job
- add libc6-dev for C standard library headers in CI
- install gcc, graphviz-dev, and pkg-config for pygraphviz in CI
- restore networkx[extra] and skip pygraphviz install in CI
- drop networkx[extra] to remove pygraphviz C dependency from CI
- install graphviz dev headers in CI for pygraphviz compilation

## v4.3.0 (2026-02-24)

### Feat

- add MkDocs Material documentation site and GitLab CI/CD pipeline

## v4.2.0 (2026-02-24)

### Feat

- LSP fallback chain, 5 Whys reasoning, and issue-focused analysis

## v4.1.1 (2026-02-24)

### Fix

- suppress loguru output during Rich Live to prevent stacked panels

## v4.1.0 (2026-02-24)

### Feat

- reimagine TUI as tool-execution dashboard

### Fix

- TUI glitchiness and unfortunate run ID truncation

## v4.0.1 (2026-02-24)

### Fix

- TUI glitchiness and unfortunate run ID truncation

## v4.0.0 (2026-02-24)

### BREAKING CHANGE

- removed --deep and --no-steering CLI flags

### Feat

- modernize to Opus 4.6, Pydantic structured output, Jinja2 templates, and enhanced tooling

## v3.1.0 (2026-01-21)

### Feat

- add git tools

### Fix

- pydantic errors

## v3.0.3 (2026-01-19)

### Refactor

- migrate from standard logging to loguru (Tier 3 & 4)
- reduce runner.py complexity (2 functions)
- reduce shell_tool.py complexity from 16 to <10
- add infrastructure and fix style issues (Tier 0 & 1)

## v3.0.2 (2026-01-18)

### Fix

- TUI and tool errors

## v3.0.1 (2026-01-18)

### Fix

- prompt fixes

## v3.0.0 (2026-01-18)

### Feat

- major graph features and prompt edits

## v2.0.0 (2026-01-18)

### Feat

- major rewrites and migrate to ty lsp

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
