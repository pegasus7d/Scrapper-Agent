#!/usr/bin/env bash
# PreToolUse guardrail (Bash, "git commit *"): blocks a commit unless
# validate.sh passes and no test file is being deleted outright (CLAUDE.md:
# never remove tests to fake a pass). Output is JSON per Claude Code's
# PreToolUse hook schema (hookSpecificOutput.permissionDecision).
cd "$(dirname "$0")"

OUTPUT=$(./validate.sh 2>&1)
CODE=$?
if [ $CODE -ne 0 ]; then
  REASON=$(printf '%s' "$OUTPUT" | tail -c 2500)
  jq -n --arg r "validate.sh failed -- fix before committing:
$REASON" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
  exit 0
fi

DELETED=$(git diff --cached --diff-filter=D --name-only -- tests/ 2>/dev/null || true)
if [ -n "$DELETED" ]; then
  jq -n --arg r "Blocking commit: these test files are staged for deletion:
$DELETED
CLAUDE.md: never remove tests to fake a pass -- confirm with the user first." '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
  exit 0
fi

echo '{}'
