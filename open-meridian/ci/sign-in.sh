#!/bin/bash
# Step 1: the fork, unchanged, signs in to a real dashboard and lists its tools.
#
#   - `opencode mcp auth meridian`: dynamic registration, then the person signs
#     in and consents in a headless browser (consent.py), and the fork exchanges
#     the code at its loopback callback;
#   - `opencode mcp list` says the server is connected;
#   - one run with the scripted model, which records the tools it was offered:
#     the deployment's tools/list, through the delegation.
#
# Reads: OPENCODE (the fork's binary), RUN_DIR, WORK (a copy of the example
# workspace, with the CI overlay in WORK/.opencode/opencode.jsonc), ROWS.
set -euo pipefail
: "${OPENCODE:?}" "${RUN_DIR:?}" "${WORK:?}" "${ROWS:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$WORK"

auth_log="$RUN_DIR/mcp-auth.log"
timeout 300 "$OPENCODE" --standalone mcp auth meridian >"$auth_log" 2>&1 &
auth=$!
# shellcheck disable=SC2086 # ROWS is a list of words
if ! timeout 180 python3 "$HERE/consent.py" "$RUN_DIR" "$auth_log" $ROWS; then
  kill "$auth" 2>/dev/null || true
  echo "sign-in: the consent did not complete; the auth command said:" >&2
  sed -E 's/(code|state|code_challenge)=[^&[:space:]]*/\1=…/g' "$auth_log" >&2
  exit 1
fi
if ! wait "$auth"; then
  echo "sign-in: opencode mcp auth failed:" >&2
  sed -E 's/(code|state|code_challenge)=[^&[:space:]]*/\1=…/g' "$auth_log" >&2
  exit 1
fi
echo "sign-in: opencode mcp auth finished"

timeout 120 "$OPENCODE" --standalone mcp list | tee "$RUN_DIR/mcp-list.txt"
grep -Eq '^✓ +meridian +connected' "$RUN_DIR/mcp-list.txt" \
  || { echo "sign-in: the meridian server is not connected" >&2; exit 1; }
