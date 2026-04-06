# CI Init Command

The `ci-init` command generates CI/CD workflow files that automate codebase analysis and change verdicts. It produces ready-to-use templates for GitHub Actions and GitLab CI.

## Usage

```bash
code-context-agent ci-init [PATH] [OPTIONS]
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `PATH` | `.` (current directory) | Path to the repository where workflow files will be created |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--provider` | `both` | CI/CD provider: `github`, `gitlab`, or `both` |

### Examples

```bash
# Generate workflows for both GitHub Actions and GitLab CI
code-context-agent ci-init .

# GitHub Actions only
code-context-agent ci-init . --provider github

# GitLab CI only
code-context-agent ci-init . --provider gitlab
```

## Generated Files

| Provider | File Path | Description |
|----------|-----------|-------------|
| GitHub Actions | `.github/workflows/code-context-analysis.yml` | Multi-job workflow with all three cadences |
| GitLab CI | `.code-context-ci.yml` | Include-ready CI config with all three cadences |

!!! info
    For GitLab, the generated file is `.code-context-ci.yml` at the repository root. Include it in your main `.gitlab-ci.yml` with:

    ```yaml
    include:
      - local: .code-context-ci.yml
    ```

## Three Analysis Cadences

Both templates implement three complementary cadences that keep your codebase context current at different cost/fidelity tradeoffs.

### 1. Nightly Full Analysis

Runs a standard analysis nightly to refresh risk profiles, architectural patterns, and temporal snapshots.

| Property | Value |
|----------|-------|
| **Trigger** | Scheduled (daily at 1:00 AM UTC) |
| **Command** | `code-context-agent analyze . --output-format json --quiet` |
| **Timeout** | 30 minutes |
| **Artifact retention** | 30 days |

### 2. Weekly Deep Analysis

Runs an exhaustive `--full` mode analysis once per week for the highest fidelity results.

| Property | Value |
|----------|-------|
| **Trigger** | Scheduled (Sunday at 3:00 AM UTC) |
| **Command** | `code-context-agent analyze . --full --output-format json --quiet` |
| **Timeout** | 90 minutes |
| **Artifact retention** | 90 days |

### 3. On-Merge Incremental Index

Runs the fast deterministic indexer on every push to the default branch, keeping the structural graph and static analysis outputs current between full analyses.

| Property | Value |
|----------|-------|
| **Trigger** | Push to default branch |
| **Command** | `code-context-agent index .` |
| **Timeout** | 5 minutes |
| **Artifact retention** | 30 days |

### 4. PR/MR Verdict

Computes a change verdict for every pull request (GitHub) or merge request (GitLab) against cached context from the latest analysis.

| Property | Value |
|----------|-------|
| **Trigger** | Pull request / Merge request |
| **Command** | `code-context-agent verdict . --base origin/<target> --output-format json --exit-code` |
| **Timeout** | 5 minutes |
| **Artifact retention** | 7 days (GitLab only) |

## GitHub Actions Template

The generated workflow handles:

- **Artifact caching** via `actions/upload-artifact` and `actions/download-artifact` to persist `.code-context/` across runs
- **PR comments** that post (or update) a verdict comment on each pull request using `actions/github-script`
- **Label application** that automatically adds labels like `auto-approvable`, `needs-security-review`, or `high-blast-radius` based on the verdict
- **Graceful degradation** with `continue-on-error: true` on artifact download (first run has no cached context)

=== "Workflow Structure"

    ```yaml
    jobs:
      nightly-analysis:     # Daily at 1am UTC
      weekly-deep-analysis: # Sunday at 3am UTC
      incremental-index:    # On push to main
      pr-verdict:           # On pull request
    ```

=== "Environment"

    ```yaml
    env:
      UV_VERSION: "0.9"
      PYTHON_VERSION: "3.13"
    ```

!!! tip
    The workflow installs `gitnexus` globally via npm. If your repository already has a setup step for Node.js, you can consolidate the installation.

## GitLab CI Template

The generated config uses:

- **YAML anchors** (`&setup`) for shared setup across all jobs (image, dependency installation, cache)
- **Cache by branch** (`key: code-context-${CI_COMMIT_REF_SLUG}`) to persist `.code-context/` between pipeline runs
- **Schedule variables** to differentiate nightly vs. weekly runs (set `ANALYSIS_MODE` to `nightly` or `weekly_deep` in GitLab scheduled pipelines)
- **The official uv Docker image** (`ghcr.io/astral-sh/uv`) as the base image

=== "Pipeline Stages"

    ```yaml
    stages:
      - index
      - analyze
      - verdict
    ```

=== "Schedule Configuration"

    Create two scheduled pipelines in GitLab CI/CD settings:

    | Pipeline | Schedule | Variable |
    |----------|----------|----------|
    | Nightly analysis | Daily at 1:00 AM | `ANALYSIS_MODE=nightly` |
    | Weekly deep analysis | Sunday at 3:00 AM | `ANALYSIS_MODE=weekly_deep` |

## Prerequisites

Both templates assume:

- **Python 3.13+** available in the runner
- **uv** for Python package management
- **Node.js/npm** for gitnexus installation
- **AWS credentials** configured in CI secrets for Bedrock access (nightly/weekly analysis only; the verdict command does not use LLMs)
- A `pyproject.toml` with `code-context-agent` as a dependency (installed via `uv sync`)

!!! warning
    The verdict job downloads cached `.code-context/` artifacts from prior analysis runs. On the very first run, no artifacts exist yet. Both templates handle this gracefully — GitHub uses `continue-on-error: true` on the download step, and GitLab uses cache which is empty on first run.
