#!/usr/bin/env bash
# 批量生成桌宠：读取 manifest (slug\tname\tprompt)，并发度受限，失败自动重试 1 次。
set -uo pipefail
cd "$(dirname "$0")/.."

MANIFEST="${1:-scripts/batch20.tsv}"
PARALLEL="${PARALLEL:-4}"
TS="$(date +%Y%m%d-%H%M%S)"
LOGDIR="outputs/_batch_${TS}"
mkdir -p "$LOGDIR"

gen_one() {  # slug name prompt
  local slug="$1" name="$2" prompt="$3"
  local out="outputs/${slug}-${TS}" logfile="$LOGDIR/${slug}.log"
  if .venv/bin/petgen generate --prompt "$prompt" --name "$name" --output "$out" >"$logfile" 2>&1; then
    echo "OK   $slug -> $(basename "$out")"
    return 0
  fi
  echo "RETRY $slug (first attempt failed)"
  if .venv/bin/petgen generate --prompt "$prompt" --name "$name" --output "$out" >>"$logfile" 2>&1; then
    echo "OK   $slug -> $(basename "$out") (after retry)"
    return 0
  fi
  echo "FAIL $slug"
  return 1
}

pids=()
while IFS=$'\t' read -r slug name prompt || [[ -n "$slug" ]]; do
  [[ -z "$slug" || "$slug" == \#* ]] && continue
  gen_one "$slug" "$name" "$prompt" &
  pids+=($!)
  if (( ${#pids[@]} >= PARALLEL )); then
    wait -n "${pids[@]}" || true
    live=()
    for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && live+=("$p"); done
    pids=("${live[@]+"${live[@]}"}")
  fi
done < "$MANIFEST"

fail=0
for p in "${pids[@]}"; do wait "$p" || fail=$((fail+1)); done

echo "================ SUMMARY ================"
ok=$(grep -rl '"displayName"' outputs/*-"${TS}"/pet.json 2>/dev/null | wc -l | tr -d ' ')
echo "manifest lines processed; successful pet dirs for this batch: $ok ; job-fails: $fail"
echo "logs: $LOGDIR"
