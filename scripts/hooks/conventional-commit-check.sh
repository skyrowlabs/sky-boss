#!/bin/bash
# commit-msg hook: enforce Conventional Commits, with ONE subject line.
#
# The one-subject-line rule is the half people are surprised by, and it is the
# half that matters: a message carrying three `feat:` lines is three commits
# wearing one hat, and the changelog generator will take only the first. The
# other two changes then ship undocumented.
set -euo pipefail

MSG_FILE="$1"
# SCAFFOLD-OPTIONAL .github/release-please-config.json
# Absent in a tree scaffolded with `--versioning tag`, which is the whole
# reason the branch below exists — asked of the FILE and not of a flag,
# because the flag is gone by the time this runs.
RELEASE_CONFIG=".github/release-please-config.json"

# The vocabulary is DERIVED, and the list below is reached only where nothing
# derives it. `scripts/check_commit_subjects.py` reads `changelog-sections` out
# of the Release Please config and rejects any type with no section — so a list
# here is a second home for that set, and it drifted: the hardcoded set carried
# `style` and `revert`, the config gives them no section, and a `style(lint):`
# subject passed this hook and failed CI. That script's own docstring argues for
# deriving the set — *"a list here would disagree with the config the day
# somebody edits one of them"* — and it shipped beside the list that already
# did. The file naming the failure mode had it as a neighbour.
#
# The fallback is not the same bug wearing a hat. It applies only when the
# config is ABSENT, which is the `--versioning tag` tree, and there
# `check_commit_subjects.py` finds no contract and checks nothing — so there is
# no second opinion to disagree with. Wider is right there: the hook is
# enforcing style alone, and `style`/`revert` are real conventional types.
#
# A missing python3 with the config PRESENT is a hard failure rather than a
# quiet fallback, because the quiet fallback is *precisely* the defect — a
# wider set locally than CI will accept, green here and red there. Every tree
# this template scaffolds ships a python CLI, and pre-commit is itself python,
# so the interpreter is not an extra dependency.
FALLBACK_TYPES="feat|fix|perf|refactor|docs|test|chore|ci|build|style|revert"

if [ -f "$RELEASE_CONFIG" ]; then
    if ! TYPES="$(python3 - "$RELEASE_CONFIG" <<'PYEOF'
import json
import sys

# One line to stderr, never a traceback: this runs inside a commit-msg hook and
# a wall of python frames buries the sentence below that says what to do.
try:
    config = json.loads(open(sys.argv[1], encoding="utf-8").read())
    sections = []
    for package in (config.get("packages") or {}).values():
        sections += package.get("changelog-sections") or []
    types = sorted({s["type"] for s in sections if "type" in s})
except Exception as exc:  # noqa: BLE001 - any parse failure is the same answer
    sys.exit(f"   {type(exc).__name__}: {exc}")
if not types:
    sys.exit("   parsed, but no changelog-sections declares a type")
print("|".join(types))
PYEOF
    )"; then
        cat >&2 <<MSG
❌ cannot read the commit-type vocabulary from $RELEASE_CONFIG

This hook derives its types from that file's \`changelog-sections\` so it agrees
with \`scripts/check_commit_subjects.py\`, which CI runs over the pushed range.
Falling back to a wider list here would let a subject through that CI rejects,
which is the divergence this derivation exists to close.

Fix the config, or delete it if this repository does not use Release Please.
MSG
        exit 1
    fi
else
    TYPES="$FALLBACK_TYPES"
fi

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
