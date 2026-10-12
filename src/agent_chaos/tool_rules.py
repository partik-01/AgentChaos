"""Deterministic policy checks over attempted calls, independent of agent claims."""

import json

from .schema import CallOrderRule, ConsistentArgsRule, ToolRule


def check_tool_rules(rules: list[ToolRule], events: list[dict]) -> list[dict]:
    violations = []

    def fail(rule, expected, observed, indices):
        violations.append(
            {
                "rule": f"tool_rule:{rule.id}",
                "expected": expected,
                "observed": observed,
                "event_indices": sorted(indices),
            }
        )

    def values(rule, event, fields):
        args = event["arguments"]
        missing = [field for field in fields if field not in args]
        if missing:
            fail(
                rule,
                {"kind": rule.kind, "required_arguments": fields},
                {"missing_arguments": missing, "arguments": args},
                [event["index"]],
            )
            return None
        return {field: args[field] for field in fields}

    def signature(data):
        # Invalid tool arguments may contain lists/dicts. JSON keys also avoid
        # treating a boolean and an integer as the same exact argument value.
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    for rule in rules:
        if isinstance(rule, CallOrderRule):
            before = []
            for event in events:
                if event["tool"] not in (rule.before, rule.after):
                    continue
                matched = values(rule, event, rule.match_fields)
                if matched is None:
                    continue
                if event["tool"] == rule.before:
                    before.append((signature(matched), event["index"]))
                elif not any(key == signature(matched) for key, _ in before):
                    fail(
                        rule,
                        {
                            "kind": rule.kind,
                            "before": rule.before,
                            "after": rule.after,
                            "matching_arguments": matched,
                        },
                        {"after_event": event["index"], "earlier_matching_before": []},
                        [event["index"]],
                    )
            continue
        groups = {}
        for event in events:
            if event["tool"] != rule.tool:
                continue
            group = values(rule, event, rule.group_by)
            if group is None:
                continue
            key = signature(group)
            groups.setdefault(key, (group, []))[1].append(event)
        for group, selected in groups.values():
            if isinstance(rule, ConsistentArgsRule):
                compared = []
                for event in selected:
                    fields = values(rule, event, rule.fields)
                    if fields is not None:
                        compared.append((fields, event["index"]))
                if not compared:
                    continue
                original, first_index = compared[0]
                changed = [
                    (fields, index)
                    for fields, index in compared[1:]
                    if signature(fields) != signature(original)
                ]
                if changed:
                    fail(
                        rule,
                        {
                            "kind": rule.kind,
                            "tool": rule.tool,
                            "group": group,
                            "arguments": original,
                            "first_event": first_index,
                        },
                        {
                            "changed_calls": [
                                {"event": index, "arguments": fields} for fields, index in changed
                            ]
                        },
                        [first_index] + [index for _, index in changed],
                    )
            elif len(selected) > rule.max:
                fail(
                    rule,
                    {"kind": rule.kind, "tool": rule.tool, "group": group, "max_calls": rule.max},
                    {"call_count": len(selected)},
                    [e["index"] for e in selected],
                )
    return violations
