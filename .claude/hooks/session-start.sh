#!/bin/bash
# SessionStart hook — install the host toolchain in a fresh remote session.
#
# Reproduces what CI's lint and unit-test jobs install, so the same gates are
# runnable from the first prompt. Keep in sync with .github/workflows/ci.yml:
# a session that cannot run a gate locally turns every fix into a push.
#
# Idempotent and non-interactive; safe to re-run.
set -euo pipefail

# Local machines manage their own environment — only run in the remote one.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"

echo "[session-start] Installing host toolchain…"
python3 -m pip install --quiet --disable-pip-version-check -r scripts/requirements.txt

if [ -f package.json ]; then
  # --no-save is deliberate: some environments rewrite package-lock.json on
  # install, which would leave every session starting with a dirty tree and risk
  # committing lockfile churn that ping-pongs on other machines.
  echo "[session-start] Installing JS deps…"
  npm install --no-save --no-audit --no-fund --prefer-offline
fi

echo "[session-start] Host toolchain ready."
