"""Enforce TEST_PLAN §4 coverage thresholds from coverage.py's JSON report.

    uv run pytest --cov --cov-report=json && uv run python scripts/check_coverage.py coverage.json

- apps/api overall: lines >= 85%, branches >= 80%.
- modules identity_gate, dispatch, calibration: lines >= 95%, branches >= 90%.
  A module that doesn't exist yet (M0 skeleton) is reported as "pending" and does not fail;
  as soon as its files exist the threshold is enforced.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OVERALL = (85.0, 80.0)
CRITICAL_MODULES = {
    "identity_gate": (95.0, 90.0),
    "dispatch": (95.0, 90.0),
    "calibration": (95.0, 90.0),
}


@dataclass
class Tally:
    lines: int = 0
    covered_lines: int = 0
    branches: int = 0
    covered_branches: int = 0

    def add(self, summary: dict[str, Any]) -> None:
        self.lines += summary["num_statements"]
        self.covered_lines += summary["covered_lines"]
        self.branches += summary.get("num_branches", 0)
        self.covered_branches += summary.get("covered_branches", 0)

    @staticmethod
    def pct(covered: int, total: int) -> float:
        return 100.0 if total == 0 else 100.0 * covered / total

    @property
    def line_pct(self) -> float:
        return self.pct(self.covered_lines, self.lines)

    @property
    def branch_pct(self) -> float:
        return self.pct(self.covered_branches, self.branches)


def module_of(path: str) -> str | None:
    parts = Path(path).parts
    if "app" not in parts:
        return None
    rest = parts[parts.index("app") + 1 :]
    return Path(rest[0]).stem if rest else None


def check(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    total = Tally()
    total.add(report["totals"])
    rows = [("apps/api (overall)", total, OVERALL)]

    per_module: dict[str, Tally] = {}
    for path, data in report["files"].items():
        mod = module_of(path)
        if mod in CRITICAL_MODULES:
            per_module.setdefault(mod, Tally()).add(data["summary"])

    for mod, limits in CRITICAL_MODULES.items():
        if mod in per_module:
            rows.append((f"app.{mod}", per_module[mod], limits))
        else:
            print(
                f"  app.{mod:<14} pending (not implemented yet; "
                f"{limits[0]:.0f}/{limits[1]:.0f} applies once it exists)"
            )

    for name, tally, (min_lines, min_branches) in rows:
        ok = tally.line_pct >= min_lines and tally.branch_pct >= min_branches
        print(
            f"  {name:<20} lines {tally.line_pct:6.2f}% (>= {min_lines:.0f})"
            f"  branches {tally.branch_pct:6.2f}% (>= {min_branches:.0f})  {'OK' if ok else 'FAIL'}"
        )
        if not ok:
            failures.append(name)
    return failures


def main(argv: list[str]) -> int:
    path = Path(argv[0] if argv else "coverage.json")
    print(f"Coverage thresholds (TEST_PLAN §4) from {path}:")
    failures = check(json.loads(path.read_text(encoding="utf-8")))
    if failures:
        print(f"FAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
