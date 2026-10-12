"""Dependency-free static HTML; all recorded strings are escaped."""

import html
import json
from pathlib import Path


def pretty(value):
    return html.escape(json.dumps(value, indent=2, ensure_ascii=False))


def table(headers, rows):
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def overview(data):
    if "run_id" in data:
        result = data["result"]
        status = html.escape(result["status"].replace("_", " "))
        violations = result["violations"]
        rules = table(
            ["Violated rule", "Expected", "Observed"],
            [(v["rule"], json.dumps(v["expected"]), json.dumps(v["observed"])) for v in violations],
        )
        timeline = table(
            ["Event", "Tool", "Fault", "Backend", "Agent observed"],
            [
                (
                    e["index"],
                    e["tool"],
                    (e["fault"] or {}).get("kind", "—"),
                    "committed"
                    if any(b["kind"] == "refund_committed" for b in e["backend_events"])
                    else "idempotent replay"
                    if e["backend_events"]
                    else "read / no write",
                    json.dumps(e["observed"]),
                )
                for e in data["tool_events"]
            ],
        )
        return f"<section><h2 class='status'>{status}</h2><p>Run {html.escape(data['run_id'])}</p>{rules}</section><section class='timeline'><h2>Tool timeline</h2>{timeline}</section>"
    summary = data.get("summary", {})
    groups = (
        {"trials": summary}
        if "by_scenario" in summary
        else {k: v for k, v in summary.items() if isinstance(v, dict) and "by_scenario" in v}
    )
    return "".join(
        f"<section><h2>{html.escape(name)} · {group['failure_count']} failures / {group['total_trials']} trials</h2>"
        + table(
            ["Scenario", "Trials", "Pass", "Agent failure", "Harness error", "Inconclusive"],
            [
                (
                    r["scenario"],
                    r["total_trials"],
                    r["pass"],
                    r["agent_failure"],
                    r["harness_error"],
                    r["inconclusive"],
                )
                for r in group["by_scenario"]
            ],
        )
        + "</section>"
        for name, group in groups.items()
    )


def render_html(data: dict) -> str:
    is_run = "run_id" in data
    title = f"Agent Chaos · {data['scenario']['name']}" if is_run else "Agent Chaos · trial results"
    result = data["result"] if is_run else data.get("summary", data)
    sections = [("Outcome", result)]
    if is_run:
        if data["configuration"].get("execution_limits"):
            sections.append(
                (
                    "Execution limits and stop evidence",
                    {
                        "limits": data["configuration"]["execution_limits"],
                        "stop": data.get("execution_stop"),
                    },
                )
            )
        sections += [
            ("Failure count / total trials", data["trial_summary"]),
            ("Reproduce by scenario rerun", data["reproduction_command"]),
            ("Injected fault schedule", data["fault_schedule"]),
            ("Tool evidence: authoritative result and observed result", data["tool_events"]),
            ("Initial authoritative state", data["initial_state"]),
            ("Final authoritative state", data["final_state"]),
            ("Customer messages", data["messages"]),
            ("Agent responses", data["responses"]),
            (
                "Model, prompt, configuration and versions",
                {
                    k: data[k]
                    for k in (
                        "agent",
                        "configuration",
                        "package_version",
                        "source_commit",
                        "scenario_sha256",
                    )
                },
            ),
        ]
    else:
        sections.append(("Full trial evidence", data))
    body = "".join(
        f"<section><h2>{html.escape(label)}</h2><pre>{pretty(value)}</pre></section>"
        for label, value in sections
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{font:16px system-ui;background:#f4f6fa;color:#182238;margin:0 auto;padding:32px;max-width:1100px}}
h1{{letter-spacing:-1px}}section{{background:white;border:1px solid #dce2ed;border-radius:10px;
padding:20px;margin:18px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.5}}
small{{color:#516078}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:12px;border-bottom:1px solid #dce2ed;vertical-align:top;overflow-wrap:anywhere}}
th{{background:#eef2f8}}.scroll{{overflow-x:auto}}.status{{text-transform:uppercase;font-size:22px}}
.timeline table{{min-width:750px}}.timeline th,.timeline td:nth-child(-n+4){{white-space:nowrap}}</style></head><body><h1>{html.escape(title)}</h1>
<small>Simulated payments only · authoritative business evidence · trace format v1</small>
{overview(data)}{body}</body></html>"""


def write_html(path: str | Path, data: dict):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(data))
