"""Dependency-free static HTML; all recorded strings are escaped."""
import html
import json
from pathlib import Path


def pretty(value):
    return html.escape(json.dumps(value, indent=2, ensure_ascii=False))


def render_html(data: dict) -> str:
    is_run = "run_id" in data
    title = f"Agent Chaos · {data['scenario']['name']}" if is_run else "Agent Chaos · trial results"
    result = data["result"] if is_run else data.get("summary", data)
    sections = [("Outcome", result)]
    if is_run:
        sections += [("Failure count / total trials", data["trial_summary"]),
                     ("Reproduce by scenario rerun", data["reproduction_command"]),
                     ("Injected fault schedule", data["fault_schedule"]),
                     ("Tool evidence: authoritative result and observed result", data["tool_events"]),
                     ("Initial authoritative state", data["initial_state"]),
                     ("Final authoritative state", data["final_state"]),
                     ("Customer messages", data["messages"]), ("Agent responses", data["responses"]),
                     ("Model, prompt, configuration and versions", {k: data[k] for k in
                      ("agent", "configuration", "package_version", "source_commit", "scenario_sha256")})]
    else:
        sections.append(("Full trial evidence", data))
    body = "".join(f"<section><h2>{html.escape(label)}</h2><pre>{pretty(value)}</pre></section>"
                   for label, value in sections)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{font:16px system-ui;background:#f4f6fa;color:#182238;margin:0 auto;padding:32px;max-width:1100px}}
h1{{letter-spacing:-1px}}section{{background:white;border:1px solid #dce2ed;border-radius:10px;
padding:20px;margin:18px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.5}}
small{{color:#516078}}</style></head><body><h1>{html.escape(title)}</h1>
<small>Simulated payments only · authoritative business evidence · trace format v1</small>
{body}</body></html>"""


def write_html(path: str | Path, data: dict):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(data))
