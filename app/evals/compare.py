import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_fingerprint = before.get("case_fingerprint")
    after_fingerprint = after.get("case_fingerprint")
    if before_fingerprint != after_fingerprint:
        raise ValueError("reports have different case fingerprints or only one has a fingerprint")
    if before.get("data_fingerprint") != after.get("data_fingerprint"):
        raise ValueError("reports have different demo data fingerprints")
    previous = {row["id"]: row for row in before["cases"]}
    current = {row["id"]: row for row in after["cases"]}
    if len(previous) != len(before["cases"]) or len(current) != len(after["cases"]):
        raise ValueError("duplicate case ids")
    if previous.keys() != current.keys():
        raise ValueError("reports must contain the same case ids")

    transitions: Counter[str] = Counter()
    checks: dict[str, Counter[str]] = {}
    gained = []
    regressed = []
    paired = 0
    for case_id in previous:
        old = previous[case_id]
        new = current[case_id]
        if old["kind"] != new["kind"]:
            raise ValueError(f"{case_id}: kind changed")
        old_availability = old["availability"]
        new_availability = new["availability"]
        transitions[f"{old_availability}_to_{new_availability}"] += 1
        if old_availability != "ok" or new_availability != "ok":
            continue
        paired += 1
        old_checks = old["checks"]
        new_checks = new["checks"]
        if old_checks.keys() != new_checks.keys():
            raise ValueError(f"{case_id}: check names changed")
        for name, passed_before in old_checks.items():
            passed_after = new_checks[name]
            if not isinstance(passed_before, bool) or not isinstance(passed_after, bool):
                raise ValueError(f"{case_id}: checks must be boolean")
            bucket = checks.setdefault(name, Counter())
            bucket["paired"] += 1
            bucket["before_passed"] += int(passed_before)
            bucket["after_passed"] += int(passed_after)
            if not passed_before and passed_after:
                gained.append({"id": case_id, "check": name})
            elif passed_before and not passed_after:
                regressed.append({"id": case_id, "check": name})

    before_available = sum(row["availability"] == "ok" for row in previous.values())
    after_available = sum(row["availability"] == "ok" for row in current.values())
    if not paired:
        signal = "insufficient_paired_cases"
    elif after_available < before_available or regressed:
        signal = "regressed"
    elif after_available > before_available or gained:
        signal = "improved_candidate"
    else:
        signal = "no_automated_change"
    return {
        "case_content_verified": before_fingerprint is not None,
        "data_content_verified": before.get("data_fingerprint") is not None,
        "case_count": len(previous),
        "before_available": before_available,
        "after_available": after_available,
        "paired_available": paired,
        "availability_transitions": dict(sorted(transitions.items())),
        "paired_checks": {
            name: {
                "paired": counts["paired"],
                "before_passed": counts["before_passed"],
                "after_passed": counts["after_passed"],
            }
            for name, counts in sorted(checks.items())
        },
        "gained_checks": gained,
        "regressed_checks": regressed,
        "automated_signal": signal,
        "manual_review_required": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two reports on the same fixed cases")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    comparison = compare_reports(before, after)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
