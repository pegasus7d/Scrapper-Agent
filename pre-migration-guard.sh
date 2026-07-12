#!/usr/bin/env bash
# PreToolUse guardrail (Bash, every command): CLAUDE.md's real,
# incident-driven rule -- a migration downgrade must never run against
# the real hirable.db directly, only via a scratch copy (-x db_url=...).
# Reads the actual command from stdin JSON; a fast grep short-circuits
# before the jq parse for every non-matching command.
COMMAND=$(jq -r '.tool_input.command // ""' 2>/dev/null)

# Real false positive found live: a `git commit` using this project's own
# heredoc convention for the message body can contain the literal words
# "alembic"/"downgrade" as prose (e.g. describing this very rule), which
# a plain grep over the whole command text would wrongly match. `git`
# itself never invokes alembic, and a heredoc body is message text, not
# a command -- skip the check entirely for either shape.
if printf '%s' "$COMMAND" | grep -q '<<' || printf '%s' "$COMMAND" | grep -qE '^\s*git\b'; then
  echo '{}'
  exit 0
fi

if printf '%s' "$COMMAND" | grep -qi 'alembic' && printf '%s' "$COMMAND" | grep -qi 'downgrade'; then
  if ! printf '%s' "$COMMAND" | grep -q -- '-x db_url='; then
    jq -n --arg r "Blocking: an alembic downgrade without -x db_url=... would run against the real hirable.db directly.
CLAUDE.md's rule (a real incident already happened this way, PHASE11.md step 5):
  cp hirable.db /tmp/scratch.db
  alembic -x db_url=sqlite:////tmp/scratch.db <command>
Round-trip test the migration against that scratch copy, never hirable.db directly." '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
    exit 0
  fi
fi

echo '{}'
