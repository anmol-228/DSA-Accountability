"""Renders curriculum/CURRICULUM.md from schedule.json for human reading.
The JSON is the source of truth consumed by the app; this file is a
convenience view. Run after editing build_schedule.py and regenerating
schedule.json."""
import json
from pathlib import Path

HERE = Path(__file__).parent
schedule = json.loads((HERE / "schedule.json").read_text(encoding="utf-8"))

lines = ["# Canonical 135-Day Curriculum", "",
         "Generated from `schedule.json` — do not hand-edit; edit `build_schedule.py` and regenerate.", ""]

for day in schedule["days"]:
    flags = []
    if day["is_oa"]:
        flags.append("OA")
    if day["is_mock"]:
        flags.append("MOCK")
    flag_str = f" [{', '.join(flags)}]" if flags else ""
    lines.append(f"## Day {day['day']} — {day['title']}{flag_str}")
    lines.append(f"_Topic: {day['topic']}_")
    lines.append("")
    for item in day["items"]:
        kind = item["kind"]
        if kind == "learn_group":
            for b in item["bullets"]:
                lines.append(f"- Learn: {b}")
        elif kind == "exercise":
            lines.append(f"- Exercise: {item['title']}")
        elif kind == "leetcode":
            note = f" ({item['note']})" if item.get("note") else ""
            lines.append(f"- LC {item['leetcode_number']} — {item['title']}{note}")
        elif kind == "revision":
            lines.append(f"- Revision: LC {item['leetcode_number']} — {item['title']}")
        elif kind == "concept":
            lines.append(f"- Core CS: {item['title']} ({'; '.join(item.get('bullets', []))})")
        elif kind == "repair":
            lines.append(f"- {item['title']}: {item.get('note', '')}")
        elif kind == "oa":
            probs = ", ".join(f"LC {p['leetcode_number']} {p['title']}" for p in item["problems"])
            lines.append(f"- **OA** ({item['minutes']} min): {probs}")
        elif kind == "mock":
            for entry in item["items"]:
                p = entry.get("problem")
                if p:
                    lines.append(f"- **Mock**: LC {p['leetcode_number']} {p['title']} (~{entry.get('target_minutes','?')} min)")
    lines.append("")

(HERE / "CURRICULUM.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {HERE / 'CURRICULUM.md'}")
