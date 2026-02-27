# Closing the loop: automated code review for AI-generated code

I shipped an entire DevSecOps pipeline in an afternoon last week. Bandit, semgrep, osv-scanner, gitleaks, license compliance, SBOM generation, container scanning — wired into GitLab CI with SARIF conversion and unified reporting. The code worked. The tests passed. I committed it.

Then I looked at what I'd actually written.

Copy-pasted error handling in three tool modules. A function that grew to 40 lines because I kept saying "add this check too." A hardcoded CVSS threshold buried in a helper that should have been a config value. The kind of stuff that passes every linter and scanner but makes you wince six months later when you're trying to refactor.

The AI wrote the code. The AI passed the tests. The AI generated tech debt. And I, the supposed reviewer, approved all of it — because I'd been watching it get written in real time and my brain had already pattern-matched it as "correct."

That's the gap. Static analysis catches syntax. Type checkers catch contracts. SAST catches security. Nothing catches *design rot* — and when AI is writing code at 10x speed, design rot accumulates at 10x speed too.

## Linters are table stakes, not a finish line

Let me be clear about what the standard shift-left toolkit actually covers, because it covers a lot.

**Type checkers** are the first line of defense against structural bugs. For Python, [ty](https://github.com/astral-sh/ty) (from the Astral team behind ruff and uv) catches type errors statically without running your code. TypeScript projects get this from `tsc --noEmit`. Rust has it built into `cargo check`. Go has `go vet`. These tools catch an entire class of bugs — wrong argument types, missing return values, null reference paths — before a single test runs.

**Linters and formatters** handle consistency. Ruff for Python (lint + format in one pass). ESLint and Prettier for JavaScript/TypeScript. `clippy` for Rust. They enforce style rules so your team doesn't waste review cycles arguing about import order or line length.

**SAST scanners** find security patterns. Semgrep runs OWASP Top 10 rules against your source. Bandit catches Python-specific issues like `subprocess` calls with `shell=True` or Jinja2 templates without autoescape. Gitleaks scans for secrets in staged files and git history.

**Dependency scanners** audit your supply chain. [osv-scanner](https://github.com/google/osv-scanner) (from Google) reads lockfiles natively — `uv.lock`, `package-lock.json`, `Cargo.lock` — and checks the OSV vulnerability database. [Guarddog](https://github.com/DataDog/guarddog) (from Datadog) detects typosquatting and malicious packages in your dependency tree.

**IaC scanners** catch infrastructure misconfigurations before deployment. [Checkov](https://www.checkov.io/) scans Terraform plans, CloudFormation templates, Kubernetes manifests, and Dockerfiles against hundreds of policy rules — open S3 buckets, unencrypted databases, overly permissive IAM roles. For AWS CDK specifically, [cdk-nag](https://github.com/cdklabs/cdk-nag) runs rule packs (AWS Solutions, HIPAA, NIST 800-53, PCI DSS) directly against your CDK constructs at synth time, failing the build before a template ever reaches CloudFormation. If you're writing infrastructure as code alongside application code — and if AI is generating that infrastructure — these checks are non-negotiable.

**License compliance** tools like pip-licenses verify your dependency tree against a blocklist. You don't want to ship a GPL-licensed transitive dependency in your proprietary product because the AI picked a library that looked convenient.

All of this runs automatically. Pre-commit hooks via [lefthook](https://github.com/evilmartians/lefthook) or husky catch fast issues locally. CI pipelines run the heavier scans. Each tool produces artifacts — SARIF reports, Cobertura XML, CycloneDX SBOMs — that feed into your platform's security dashboard and MR widgets.

Here's what that looks like in practice for a Python project:

| Layer | Tool | What it catches |
|-------|------|----------------|
| Pre-commit | ruff check + format | Syntax, style, import order |
| Pre-commit | ty check | Type errors |
| Pre-commit | gitleaks | Secrets in staged files |
| Commit-msg | commitizen | Conventional commit format |
| Pre-push | pytest | Functional regressions |
| Pre-push | semgrep OWASP | Security vulnerability patterns |
| CI | bandit | Python-specific SAST |
| CI | osv-scanner | Known dependency vulnerabilities |
| CI | pip-licenses | License compliance |
| CI | guarddog | Typosquatting detection |
| CI | checkov / cdk-nag | IaC misconfigurations |
| CI | trivy | Container image vulnerabilities |
| CI | syft | SBOM generation (CycloneDX + SPDX) |
| CI | pytest-cov | Coverage reporting (Cobertura) |

Every one of these tools is open source. Every one runs in CI without vendor lock-in. Together they form a solid foundation.

And none of them will tell you that you just violated the Single Responsibility Principle.

## The judgment gap

Static analysis operates on rules. A function is too complex if its cyclomatic complexity exceeds a threshold. A variable is unused if no reference exists. A dependency is vulnerable if it appears in a CVE database. These are binary checks with deterministic answers.

Design quality is different. A 15-line function might be fine, or it might be doing two unrelated things that happen to fit in 15 lines. A class might have reasonable complexity scores while violating the Open-Closed Principle in a way that makes every future feature change touch six files. Duplicated logic across three modules might be intentional (different contexts) or accidental (copy-paste during a fast session).

Humans catch this. Experienced reviewers pattern-match against years of seeing codebases evolve. They recognize the early signs of a god class. They notice when a function's name says one thing and its body does another. They spot the coupling between modules that will make the next refactor painful.

When AI writes the code, this review step often gets compressed or skipped entirely. The human watched the code get generated. They saw the reasoning. They approved each step. By the time the diff is ready for review, the reviewer's judgment is already anchored to the AI's design decisions.

I tested this directly. I set up a Claude Code hook that blocked `git commit` and told Claude to review its own staged diff before proceeding. Claude ran `git diff --cached`, scanned the output, and reported: "Code looks clean. No issues found."

It had just written the code five minutes earlier in the same conversation. Every design decision felt intentional because, from Claude's perspective, it *was* intentional. The anchoring effect was identical to what happens with human self-review — but faster, because the AI's memory of its own reasoning was perfect.

## Independent review through context isolation

Code review works because the reviewer lacks context. They didn't sit through the two-hour pairing session. They don't know about the three approaches that were tried and abandoned. They see only the diff, and they evaluate it on its own merits. That lack of context is the feature.

Claude Code has a mechanism for this: the `Task` tool spawns independent subagents. Each subagent starts with a blank context — no conversation history, no memory of prior decisions. You provide a prompt and (optionally) a set of tools. The subagent does its work and returns results. It has no knowledge of the parent conversation.

The architecture uses a `PreToolUse` hook — a script that fires before any tool call and can block it:

```
Developer: "commit this"
        │
        ▼
Claude tries: git commit -m "feat: ..."
        │
        ▼
PreToolUse hook intercepts the Bash call
        │
        ├─ First attempt → BLOCK
        │  Create session-keyed marker file in /tmp
        │  Return instructions: "Spawn an independent reviewer"
        │
        ▼
Claude captures the staged diff with git diff --cached
Claude spawns a Task subagent (fresh context, no history)
        │
        ▼
Subagent reviews the diff against a structured checklist
Returns findings with severity ratings and root cause analysis
        │
        ▼
Claude processes findings:
  • Error-severity issues → fix first, then retry
  • Warnings and info only → retry the commit
        │
        ▼
Claude tries: git commit -m "feat: ..."
        │
        ├─ Marker file exists → ALLOW
        │  Delete marker, let the commit through
        │
        ▼
Lefthook runs (ruff, ty, gitleaks, commitizen)
Commit succeeds
```

The marker file prevents infinite loops. First `git commit` attempt gets blocked and creates a marker keyed to the session ID. Second attempt finds the marker, deletes it, and passes through. Simple state machine, two states, no race conditions in practice.

The subagent is the critical piece. It receives only the raw diff and a review checklist. It has no access to the conversation that produced the code. It evaluates the diff the way any external reviewer would — on its own merits, without anchoring to the author's intent.

## What the reviewer evaluates

The review checklist targets the categories that static analysis misses:

**DRY violations** — duplicated logic across the diff, copy-pasted blocks, patterns that should share a common abstraction. This includes structural duplication that linters can't detect, like two functions with different names that follow identical logic flows.

**SOLID violations** — functions or classes that handle multiple unrelated responsibilities (SRP). Modules that require modification instead of extension for new behavior (OCP). Concrete dependencies where an abstraction would decouple components (DIP).

**Code smells** — methods over 20 lines of logic. Nesting deeper than three levels. Feature envy (a function that reaches into another module's data more than its own). Law of Demeter violations (long chains of attribute access). Data clumps (groups of parameters that travel together and should be a struct or dataclass).

**Tech debt markers** — TODO/FIXME/HACK comments in new code. Hardcoded values that should be configurable. Overly broad exception catches (`except Exception`). Implicit coupling between components that should be explicit.

**Dead code** — unreachable branches, unused imports or variables within the diff scope, commented-out blocks, functions defined but never called.

Each finding includes a **5 Whys root cause chain** — five sentences that trace the surface symptom back to its architectural origin. The value of this is the difference between "extract this method" (symptom treatment) and "this module lacks a formal data contract between its input parser and validator" (architectural fix). Surface findings recur. Root cause fixes compound.

## The severity contract

The system has to work at speed or it gets bypassed. Three severity levels enforce this:

**Error** blocks the commit. Reserved for bugs, broken logic, and severe architectural violations that will compound over time. This is a hard gate — Claude fixes the issue before retrying.

**Warning** gets reported but doesn't block. DRY violations with three or more repetitions, meaningful complexity, tech debt in new code. These items land in the conversation for the developer to see and address at their discretion.

**Info** is observational. Minor smells, refactoring suggestions, things worth knowing but not worth stopping for.

The key calibration: only errors block. If warnings blocked commits, every session would end in a review-fix-review loop that adds twenty minutes to each commit. That's the fastest way to get developers to disable the hook entirely.

## Extending this to your stack

The pattern — automated static checks plus AI-powered design review — applies beyond Python.

**TypeScript projects** replace ruff with ESLint and Prettier, swap `ty check` for `tsc --noEmit`, and add [Knip](https://github.com/webpro/knip) for dead code detection. The subagent review prompt adjusts to check for React anti-patterns, proper TypeScript generic usage, and module boundary violations.

**Rust projects** get `cargo clippy` for linting, `cargo check` for type verification, and `cargo audit` for dependency vulnerabilities. The subagent prompt focuses on ownership patterns, lifetime complexity, and unsafe block justification.

**Infrastructure as Code** adds its own layer. Checkov validates Terraform, CloudFormation, and Kubernetes manifests against policy rules. cdk-nag runs compliance rule packs against AWS CDK constructs at synthesis time. Both integrate into CI pipelines and produce structured reports. The subagent review prompt for IaC shifts to focus on least-privilege IAM policies, encryption-at-rest defaults, and network isolation patterns.

The implementation adapts to each ecosystem. The principle stays the same: static tools catch rules violations, the AI reviewer catches design violations, and the severity contract keeps the system fast enough to use every commit.

## What this actually looks like in practice

Here's a real commit from the project where I built this system. I'd staged changes across three files — a new CI job, a security report script, and a config update. I said "commit this."

The hook blocked the commit. Claude spawned the reviewer subagent. The subagent came back with four findings:

- **Warning** (tech debt): Race condition in the marker file — `touch` + `[ -f ]` isn't atomic, and a crash between marker creation and commit retry leaves an orphaned file.
- **Warning** (tech debt): Removed the lefthook code-critic jobs but didn't delete the script file they referenced. Dead code in the repo.
- **Info** (tech debt): Hardcoded model name (`sonnet`) buried in a heredoc. Should be a configurable variable.
- **Info** (code smell): Triple `jq` parse of the same stdin input. Wasteful and masks integration bugs if the JSON is malformed.

No errors, so the commit went through on retry. But the warnings were legitimate — the kind of things I would have caught in a human review two days later, when the context had faded and I was reading the code fresh. The subagent caught them in thirty seconds, before the code ever hit the remote.

## Three files, five minutes

The implementation is minimal:

1. **`.claude/hooks/review-before-commit.sh`** — the PreToolUse hook. Reads tool input from stdin, checks for `git commit`, manages the marker file, returns the review instructions as a denial reason. About 80 lines of bash.

2. **`.claude/settings.json`** — registers the hook on `Bash` tool calls with a `PreToolUse` matcher. Four lines of JSON.

3. **`scripts/code-critic.sh`** — a standalone version that runs outside Claude Code sessions, piping `git diff --cached` to `claude -p` with structured JSON output via `--output-format json --json-schema`. For terminal use without the interactive hooks system.

No external services. No API keys beyond what you already have for Claude Code. No plugins to install. The hook uses Claude Code's native hooks API, and the subagent uses the built-in `Task` tool.

The playbook for adding this to your own workflow:

1. **Automate the mechanical checks.** Linting, formatting, type checking, secret scanning. These are solved problems. Run them on every commit via git hooks.
2. **Add IaC scanning if you write infrastructure.** Checkov for Terraform and CloudFormation. cdk-nag for CDK. Run them at synth/plan time, not just in CI.
3. **Add the judgment layer.** An independent AI reviewer that checks for design quality — DRY, SOLID, smells, debt, dead code. Use context isolation (subagents) to prevent self-review bias.
4. **Gate on severity.** Errors block. Warnings inform. Info educates. The system stays fast enough to use at velocity.
5. **Require root cause analysis.** Surface findings recur. "5 Whys" traces the symptom to its architectural origin, so the fix compounds instead of just patching.
6. **Layer the defenses.** Pre-commit for fast local checks. Pre-push for tests and deeper scans. CI for everything else. Each layer catches what the others miss.

The AI builds. An independent AI reviews. The quality bar holds — even at the speed AI-assisted development actually moves.
