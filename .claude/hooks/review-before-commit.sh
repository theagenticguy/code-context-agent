#!/bin/bash
# PreToolUse hook: blocks the first git commit attempt per session and
# instructs Claude to delegate the review to an INDEPENDENT subagent
# (no conversation context = no bias toward its own code).
#
# On the second attempt the marker file exists, so the commit goes through.
#
# Loop-prevention: marker file keyed by session_id in /tmp.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

# Only intercept git commit commands
if ! echo "$COMMAND" | grep -qE '^\s*git\s+commit'; then
  exit 0
fi

MARKER="/tmp/claude-commit-reviewed-${SESSION_ID}"

if [ -f "$MARKER" ]; then
  # Second attempt: review was already requested, allow the commit
  rm -f "$MARKER"
  exit 0
fi

# First attempt: block and instruct Claude to delegate review
touch "$MARKER"

REASON=$(cat <<'REASON_EOF'
COMMIT BLOCKED: Independent code review required.

You MUST delegate this review to a FRESH subagent to avoid self-review bias.
Do NOT review the code yourself — you wrote it and will be biased.

Steps:
1. Run `git diff --cached` to capture the staged diff
2. Use the Task tool to spawn a subagent with subagent_type="general-purpose"
   and model="sonnet". Pass the FULL diff output in the prompt along with
   these review instructions:

   ---BEGIN REVIEW PROMPT---
   You are an independent code critic. You have NOT seen the conversation that
   produced this code. Review the following staged git diff with zero bias.

   Check for:
   1. DRY Violations - duplicated logic, copy-pasted blocks, repeated patterns
   2. SOLID Violations - god functions (SRP), modifying not extending (OCP),
      concrete deps where abstractions belong (DIP)
   3. Code Smells - methods >20 lines, nesting >3 levels, feature envy,
      Law of Demeter violations, data clumps
   4. Tech Debt - TODO/FIXME/HACK, hardcoded values, broad except catches,
      implicit coupling
   5. Dead Code - unreachable branches, unused imports/vars, commented-out code

   For each finding report:
   - File and line number
   - Category and severity (error/warning/info)
   - Which principle is violated
   - A concrete fix suggestion
   - A "5 Whys" root cause chain (5 sentences: symptom → architectural root cause)

   If no issues found, say "No findings. Code is clean."

   Severity guide:
   - error: blocks commit (bugs, broken logic, severe SOLID violations)
   - warning: should fix soon (DRY 3+ reps, complexity, tech debt)
   - info: nice-to-know (minor smells)
   ---END REVIEW PROMPT---

3. After the subagent returns:
   - If there are ERROR-severity findings → fix them, then retry the commit
   - If only warnings/info or no findings → retry the commit as-is
REASON_EOF
)

jq -n --arg reason "$REASON" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $reason
  }
}'
exit 0
