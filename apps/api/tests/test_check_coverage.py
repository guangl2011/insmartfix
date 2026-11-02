"""The coverage gate itself must be correct, or TEST_PLAN §4 isn't really enforced."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_coverage.py"
    spec = importlib.util.spec_from_file_location("check_coverage", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_coverage"] = mod
    spec.loader.exec_module(mod)
    return mod


cc = _load()


def summary(lines: int, covered: int, branches: int = 0, cbranches: int = 0) -> dict[str, int]:
    return {
        "num_statements": lines,
        "covered_lines": covered,
        "num_branches": branches,
        "covered_branches": cbranches,
    }


def report(files: dict[str, dict[str, int]]) -> dict[str, Any]:
    t = cc.Tally()
    for s in files.values():
        t.add(s)
    totals = summary(t.lines, t.covered_lines, t.branches, t.covered_branches)
    return {"totals": totals, "files": {p: {"summary": s} for p, s in files.items()}}


def test_passes_skeleton_with_pending_modules(capsys: pytest.CaptureFixture[str]) -> None:
    assert cc.check(report({"app/main.py": summary(10, 10, 2, 2)})) == []
    assert "pending" in capsys.readouterr().out


def test_fails_overall_branch_threshold() -> None:
    assert cc.check(report({"app/main.py": summary(10, 10, 10, 7)})) == ["apps/api (overall)"]


def test_enforces_critical_module_once_it_exists() -> None:
    files = {
        "app/main.py": summary(100, 100, 10, 10),
        "app/dispatch/service.py": summary(20, 18, 10, 10),  # 90% < 95%
    }
    assert cc.check(report(files)) == ["app.dispatch"]


def test_module_of() -> None:
    assert cc.module_of("app/identity_gate.py") == "identity_gate"
    assert cc.module_of("app/calibration/labeler.py") == "calibration"
    assert cc.module_of("scripts/x.py") is None
    assert cc.module_of("app") is None


def test_main_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "coverage.json"
    p.write_text(json.dumps(report({"app/main.py": summary(1, 0)})))
    assert cc.main([str(p)]) == 1
    p.write_text(json.dumps(report({"app/main.py": summary(1, 1)})))
    assert cc.main([str(p)]) == 0


def test_empty_totals_count_as_full() -> None:
    assert cc.Tally().line_pct == 100.0
