#!/bin/bash
# One run of the fork's `meridian` agent, without a terminal, against the
# scripted model following SCRIPT. Exits non-zero when the run fails or the
# script stopped before its end.
#
# Usage: run-flow.sh NAME SCRIPT PROMPT
#   NAME   the run's name: its output is RUN_DIR/NAME/ (run.jsonl, steps.jsonl,
#          offered-tools.json)
#   SCRIPT the scripted model's steps (scripted_model.py)
# Reads: OPENCODE, RUN_DIR, WORK, MODEL_PORT.
set -euo pipefail
: "${OPENCODE:?}" "${RUN_DIR:?}" "${WORK:?}" "${MODEL_PORT:?}"
name="$1" script="$2" prompt="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
out="$RUN_DIR/$name"
mkdir -p "$out"

python3 "$HERE/scripted_model.py" "$MODEL_PORT" "$script" "$out" &
model=$!
trap 'kill "$model" 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  curl -fsS "http://127.0.0.1:$MODEL_PORT/v1/models" >/dev/null 2>&1 && break
  sleep 0.2
done

cd "$WORK"
status=0
timeout 300 "$OPENCODE" --standalone run --format json --agent meridian --model scripted/flow "$prompt" \
  >"$out/run.jsonl" 2>"$out/run.stderr" || status=$?
if [ "$status" -ne 0 ]; then
  echo "run-flow: $name: opencode run exited $status" >&2
  tail -20 "$out/run.stderr" >&2
  exit 1
fi
if grep -q '"stopped"' "$out/steps.jsonl" 2>/dev/null; then
  echo "run-flow: $name: the script stopped:" >&2
  grep '"stopped"' "$out/steps.jsonl" >&2
  exit 1
fi
grep -q '"end": true' "$out/steps.jsonl" \
  || { echo "run-flow: $name: the script never reached its end" >&2; cat "$out/steps.jsonl" >&2 || true; exit 1; }
echo "run-flow: $name: every step taken"
