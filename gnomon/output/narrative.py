import json
import os

from gnomon.config import OUT_DIR


def write_narrative_input(s, opening_prompts, longest_prompts, output_dir=None):
    L = []
    A = L.append
    A("# Narrative input (LOCAL ONLY — for the archetype/traits pass)\n")
    A("Full metrics:\n```json")
    A(json.dumps(s, indent=2, default=str))
    A("```\n")
    A("## Opening prompts (first human message per session — characteristic asks)\n")
    op = [p for p in opening_prompts if p[0] is not None]
    op.sort(key=lambda x: x[0])
    # spread a sample across the timeline
    sample = op[:: max(1, len(op) // 60)] if op else []
    for dt, proj, text in sample[:60]:
        A(f"- [{dt.date()} · {proj}] {text.replace(chr(10), ' ')[:280]}")
    A("\n## Longest prompts (most detailed specs)\n")
    longest_prompts.sort(key=lambda x: -x[0])
    for ln, proj, text in longest_prompts[:20]:
        A(f"- [{ln} chars · {proj}] {text.replace(chr(10), ' ')[:280]}")
    with open(os.path.join(output_dir or OUT_DIR, "narrative_input.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
