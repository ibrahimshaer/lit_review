#!/bin/bash
# One process per step, one process per Tier 1 diff. Each records its own JSON
# usage. Usage: run_pipeline.sh <experiment_dir> <anchor_id> <short_name> <notes_file>
set -u
EXP="$1"; ANCHOR="$2"; SHORT="$3"; NOTES="$4"
PIPE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"   # set PYTHON to the interpreter that has the dependencies
COMMON=(--model claude-opus-5 --mcp-config .mcp.json --strict-mcp-config
        --allowedTools "mcp__arxiv__*,Skill,Read,Write,Edit,Glob,Grep,Bash" --output-format json)
export MCP_TOOL_TIMEOUT=1800000
cd "$EXP" || exit 1
mkdir -p runs scratch diffs

fill() { sed -e "s|{ANCHOR}|$ANCHOR|g" -e "s|{SHORT}|$SHORT|g" -e "s|{NOTES}|$NOTES|g" -e "s|{PAPER}|${1:-}|g" -e "s|{EXP}|$EXP|g"; }

# Step 3
fill < "$PIPE/step3_prompt.md" > runs/step3_prompt.md
claude -p "$(cat runs/step3_prompt.md)" "${COMMON[@]}" > runs/step3.json 2> runs/step3.err
[ -f "${ANCHOR}_search_space.md" ] || { echo "step3 produced no artifact" >> runs/step3.err; exit 2; }

# Step 4
fill < "$PIPE/step4_prompt.md" > runs/step4_prompt.md
claude -p "$(cat runs/step4_prompt.md)" "${COMMON[@]}" > runs/step4.json 2> runs/step4.err
[ -f "${ANCHOR}_tiers.md" ] || { echo "step4 produced no tiers file" >> runs/step4.err; exit 3; }

# Step 5: one process per Tier 1 paper, sequential
awk '/^## Tier 1/{f=1;next} /^## /{f=0} f' "${ANCHOR}_tiers.md" \
  | grep -oE '\[[0-9]{4}\.[0-9]{4,5}\]\(https://arxiv\.org/abs/' | grep -oE '[0-9]{4}\.[0-9]{4,5}' | sort -u > runs/tier1_ids.txt
while read -r PID; do
  [ -z "$PID" ] && continue
  fill "$PID" < "$PIPE/step5_prompt.md" > "runs/step5_${PID}_prompt.md"
  claude -p "$(cat "runs/step5_${PID}_prompt.md")" "${COMMON[@]}" > "runs/step5_${PID}.json" 2> "runs/step5_${PID}.err"
done < runs/tier1_ids.txt

# Usage summary
"$PYTHON" "$PIPE/summarise_usage.py" "$EXP" > usage_summary.md
echo "pipeline done" >> runs/pipeline.log
