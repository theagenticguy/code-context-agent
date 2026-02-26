#!/usr/bin/env bash
# AI code critic for DRY/SOLID violations, code smells, tech debt, and dead code.
# Outputs structured JSON findings with "5 Why" root cause analysis.
#
# Usage:
#   scripts/code-critic.sh              # diff mode (pre-commit): reviews staged changes
#   scripts/code-critic.sh --full       # full mode (pre-push): scans entire src/ tree
#
# Uses cc-y (alias for claude --dangerously-skip-permissions) in headless mode.
set -euo pipefail

# Skip gracefully if claude is not installed
if ! command -v claude &>/dev/null; then
  echo "code-critic: claude not found, skipping AI review"
  exit 0
fi

# Allow running from inside a Claude Code session (e.g. when claude triggers git push)
unset CLAUDECODE

MODE="diff"
if [ "${1:-}" = "--full" ]; then
  MODE="full"
fi

# ── JSON Schema (shared) ────────────────────────────────────────────────
read -r -d '' SCHEMA << 'SCHEMA_EOF' || true
{
  "type": "object",
  "properties": {
    "passed": {
      "type": "boolean",
      "description": "true if no error-severity findings, false otherwise"
    },
    "summary": {
      "type": "string",
      "description": "One-line overall assessment"
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "file": { "type": "string" },
          "line": { "type": "integer" },
          "severity": {
            "type": "string",
            "enum": ["error", "warning", "info"]
          },
          "category": {
            "type": "string",
            "enum": [
              "dry-violation",
              "solid-violation",
              "code-smell",
              "tech-debt",
              "dead-code",
              "complexity",
              "naming",
              "error-handling"
            ]
          },
          "principle": {
            "type": "string",
            "description": "Which principle is violated (e.g. SRP, OCP, DRY, Law of Demeter)"
          },
          "message": {
            "type": "string",
            "description": "Concise description of the issue"
          },
          "suggestion": {
            "type": "string",
            "description": "Concrete fix or refactoring suggestion"
          },
          "references": {
            "type": "array",
            "items": { "type": "string" },
            "description": "Related files, functions, or prior patterns in the codebase"
          },
          "five_whys": {
            "type": "array",
            "items": { "type": "string" },
            "minItems": 5,
            "maxItems": 5,
            "description": "5 Whys root cause chain, each element is one why"
          }
        },
        "required": ["file", "severity", "category", "message", "suggestion", "five_whys"]
      }
    }
  },
  "required": ["passed", "summary", "findings"]
}
SCHEMA_EOF

# ── Diff mode (pre-commit) ──────────────────────────────────────────────
if [ "$MODE" = "diff" ]; then
  DIFF=$(git diff --cached --diff-algorithm=minimal -- '*.py')
  if [ -z "$DIFF" ]; then
    exit 0
  fi

  read -r -d '' PROMPT << 'PROMPT_EOF' || true
You are an expert code critic performing a pre-commit review on a Python codebase.
You receive a staged git diff via stdin.

## Your Review Mandate

Analyze ONLY the changed/added lines for:

1. **DRY Violations** — duplicated logic, copy-pasted blocks, repeated patterns
   that should be abstracted. Check if similar logic already exists elsewhere
   in the diff.

2. **SOLID Violations** — single-responsibility breaches (god functions/classes),
   open-closed violations (modifying instead of extending), Liskov substitution
   issues, interface segregation problems, dependency inversion violations
   (concrete dependencies instead of abstractions).

3. **Code Smells** — long methods (>20 lines of logic), deep nesting (>3 levels),
   feature envy, data clumps, primitive obsession, message chains (Law of Demeter),
   inappropriate intimacy between modules.

4. **Tech Debt** — TODO/FIXME/HACK comments, hardcoded values that should be
   configurable, missing error handling at boundaries, broad exception catches,
   implicit coupling between components.

5. **Dead Code** — unreachable branches, unused imports/variables in the diff,
   commented-out code, functions defined but never called within the diff scope.

## Severity Rules

- **error**: Blocks the commit. Use ONLY for clear bugs, broken logic, or severe
  SOLID violations that will cause maintenance nightmares.
- **warning**: Should be fixed soon. DRY violations with 3+ repetitions, complex
  methods, meaningful tech debt.
- **info**: Nice-to-know. Minor smells, style-adjacent observations.

Set "passed" to false ONLY if there are "error" severity findings.

## 5 Whys Root Cause Analysis

For EVERY finding, provide a "5 Whys" chain that traces the symptom back to its
root cause. Each why should be a single sentence. The chain should go from the
immediate symptom to the systemic/architectural root cause.

Example:
- "Why? This function handles both parsing and validation."
- "Why? There is no separate validator class for this data type."
- "Why? The validation rules were added incrementally as edge cases appeared."
- "Why? There is no upfront schema definition for this data format."
- "Why? The data contract between these modules was never formalized."

## Output Rules

- Be precise with file paths and line numbers from the diff.
- In "references", cite existing functions/files/patterns that are relevant.
- In "suggestion", give a concrete refactoring step (not vague advice).
- If the diff is clean, return passed=true with an empty findings array.
- Do NOT flag style issues (formatting, import order) — linters handle those.
PROMPT_EOF

  RESULT=$(echo "$DIFF" | claude --dangerously-skip-permissions -p "$PROMPT" \
    --output-format json \
    --json-schema "$SCHEMA" \
    --model sonnet \
    --max-turns 1 \
    --max-budget-usd 0.50 \
    --tools "" \
    --no-session-persistence 2>/dev/null) || true

# ── Full mode (pre-push) ────────────────────────────────────────────────
else
  read -r -d '' PROMPT << 'PROMPT_EOF' || true
You are an expert code critic performing a thorough codebase-wide review of a
Python project. The source code lives in src/.

## Your Review Mandate

Use the Read, Grep, and Glob tools to scan the ENTIRE src/ directory. Analyze
the codebase holistically for cross-file and cross-module issues:

1. **DRY Violations** — duplicated logic across modules, copy-pasted utility
   functions, repeated error-handling patterns, similar data transformations
   that should share a common abstraction.

2. **SOLID Violations** — god classes/modules with too many responsibilities,
   tight coupling between modules, concrete dependencies where abstractions
   should be injected, interface segregation issues where callers depend on
   methods they never use.

3. **Code Smells** — long methods (>20 lines of logic), deep nesting (>3 levels),
   feature envy (functions that use another module's data more than their own),
   data clumps (groups of parameters that travel together), primitive obsession,
   message chains (Law of Demeter violations), inappropriate intimacy.

4. **Tech Debt** — TODO/FIXME/HACK comments, hardcoded values that should be
   configurable, missing error handling at system boundaries, overly broad
   exception catches, implicit coupling between components, missing abstractions.

5. **Dead Code** — unused imports, unreachable branches, functions/classes that
   are defined but never referenced anywhere in the codebase, commented-out
   code blocks, stale conditional logic.

## Analysis Strategy

1. First use Glob to discover all Python files in src/.
2. Use Grep to find patterns: TODO/FIXME/HACK comments, broad except clauses,
   duplicated function signatures, unused imports.
3. Read key files to understand module boundaries and coupling.
4. Focus on cross-cutting issues that single-file linters cannot catch.

## Severity Rules

- **error**: Blocks the push. Severe architectural violations, dead code that
  indicates broken functionality, security-relevant code smells.
- **warning**: Should be fixed in the next iteration. Cross-module DRY violations,
  significant tech debt, complexity hotspots.
- **info**: Improvement opportunities. Minor smells, refactoring suggestions.

Set "passed" to false ONLY if there are "error" severity findings.

## 5 Whys Root Cause Analysis

For EVERY finding, provide a "5 Whys" chain that traces the symptom back to its
root cause. Each why should be a single sentence. The chain should go from the
immediate symptom to the systemic/architectural root cause.

## Output Rules

- Be precise with file paths and line numbers.
- In "references", cite related files/functions/patterns across the codebase.
- In "suggestion", give a concrete refactoring step (not vague advice).
- If the codebase is clean, return passed=true with an empty findings array.
- Do NOT flag style issues (formatting, import order) — linters handle those.
- Limit to the top 20 most impactful findings. Prioritize errors > warnings > info.
PROMPT_EOF

  RESULT=$(claude --dangerously-skip-permissions -p "$PROMPT" \
    --output-format json \
    --json-schema "$SCHEMA" \
    --model sonnet \
    --max-turns 10 \
    --max-budget-usd 2.00 \
    --tools "Read,Grep,Glob" \
    --no-session-persistence 2>/dev/null) || true
fi

# ── Guard: if claude failed or returned empty, skip gracefully ───────────
if [ -z "$RESULT" ] || ! echo "$RESULT" | jq -e '.structured_output' &>/dev/null; then
  echo "code-critic: claude returned no results, skipping AI review"
  exit 0
fi

# ── Display results ──────────────────────────────────────────────────────
PASSED=$(echo "$RESULT" | jq -r '.structured_output.passed')
SUMMARY=$(echo "$RESULT" | jq -r '.structured_output.summary')
FINDING_COUNT=$(echo "$RESULT" | jq '.structured_output.findings | length')

echo ""
echo "=== Code Critic Review ($MODE mode) ==="
echo "$SUMMARY"
echo ""

if [ "$FINDING_COUNT" -gt 0 ]; then
  echo "$RESULT" | jq -r '.structured_output.findings[] |
    "  \(.severity | ascii_upcase): [\(.category)] \(.file):\(.line // "?")\n" +
    "    \(.message)\n" +
    "    Principle: \(.principle // "N/A")\n" +
    "    Suggestion: \(.suggestion)\n" +
    "    References: \(.references // [] | join(", "))\n" +
    "    Root Cause (5 Whys):\n" +
    (.five_whys | to_entries | map("      \(.key + 1). \(.value)") | join("\n")) +
    "\n"'
  echo ""
fi

ERRORS=$(echo "$RESULT" | jq '[.structured_output.findings[] | select(.severity == "error")] | length')
WARNINGS=$(echo "$RESULT" | jq '[.structured_output.findings[] | select(.severity == "warning")] | length')
INFOS=$(echo "$RESULT" | jq '[.structured_output.findings[] | select(.severity == "info")] | length')
echo "Findings: $FINDING_COUNT (errors: $ERRORS, warnings: $WARNINGS, info: $INFOS)"

if [ "$PASSED" = "true" ]; then
  echo "Review passed."
  exit 0
else
  echo ""
  echo "Review FAILED. Fix error-severity findings before pushing."
  exit 1
fi
