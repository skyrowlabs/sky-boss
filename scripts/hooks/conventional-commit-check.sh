#!/bin/bash
# commit-msg hook: enforce Conventional Commits, with ONE subject line.
#
# The one-subject-line rule is the half people are surprised by, and it is the
# half that matters: a message carrying three `feat:` lines is three commits
# wearing one hat, and the changelog generator will take only the first. The
# other two changes then ship undocumented.
set -euo pipefail

MSG_FILE="$1"
TYPES="feat|fix|perf|refactor|docs|test|chore|ci|build|style|revert"
PATTERN="^(${TYPES})(\([a-z0-9._/-]+\))?!?: .+"

# Strip comments and trailing blank lines.
BODY="$(grep -v '^#' "$MSG_FILE" | sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba')"
SUBJECT="$(printf '%s\n' "$BODY" | head -n1)"

if [ -z "$SUBJECT" ]; then
    echo "❌ empty commit message" >&2
    exit 1
fi

if ! printf '%s' "$SUBJECT" | grep -qE "$PATTERN"; then
    cat >&2 <<MSG
❌ Not a conventional commit subject:

    $SUBJECT

Expected:  <type>(<scope>): <summary in imperative mood>
Types:     ${TYPES//|/, }

Examples:
    feat(api): add the profile export endpoint
    fix(worker): stop retrying a permanently rejected job
    docs: record why the drift allowlist has three entries
MSG
    exit 1
fi

# Any FURTHER line that looks like a subject means several commits in one.
EXTRA="$(printf '%s\n' "$BODY" | tail -n +2 | grep -cE "$PATTERN" || true)"
if [ "$EXTRA" -gt 0 ]; then
    cat >&2 <<MSG
❌ $EXTRA additional subject line(s) found in the body.

One commit, one subject line. If this is genuinely several ideas, make several
commits — the changelog generator reads only the first line, so the rest would
ship undocumented.
MSG
    exit 1
fi

if [ "${#SUBJECT}" -gt 72 ]; then
    echo "❌ subject is ${#SUBJECT} chars (max 72): $SUBJECT" >&2
    exit 1
fi

FIRST_WORD_CHAR="$(printf '%s' "$SUBJECT" | sed -E 's/^[a-z]+(\([^)]*\))?!?: (.)/\2/' | cut -c1)"
if printf '%s' "$FIRST_WORD_CHAR" | grep -qE '[A-Z]'; then
    echo "❌ summary starts with a capital: $SUBJECT" >&2
    exit 1
fi

if printf '%s' "$SUBJECT" | grep -qE '\.$'; then
    echo "❌ summary ends with a period: $SUBJECT" >&2
    exit 1
fi

exit 0
