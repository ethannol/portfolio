"""The builder resolves every number from a ledger and refuses unknown keys."""

import json
from pathlib import Path

import pytest

from portfolio import build as b


def make_project(tmp_path: Path) -> Path:
    pdir = tmp_path / "proj"
    (pdir / "artifacts").mkdir(parents=True)
    (pdir / "figs").mkdir()
    (pdir / "figs" / "f.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (pdir / "artifacts" / "numbers.json").write_text(
        json.dumps(
            {
                "auc.mean": {"value": 0.6384, "source": "50_cv.py"},
                "auc.min": {"value": 0.6273, "source": "50_cv.py"},
                "auc.max": {"value": 0.6486, "source": "50_cv.py"},
                "n": {"value": 5707, "source": "20_prep.py"},
                "tests.n": {"value": 19, "source": "90_tests.py"},
            }
        )
    )
    (pdir / "walk.md").write_text("# Walk\n\nSome *text*.\n")
    (pdir / "portfolio.json").write_text(
        json.dumps(
            {
                "slug": "proj",
                "title": "Proj",
                "question": "Q?",
                "ledger": {"type": "cairn", "path": "artifacts/numbers.json"},
                "headline": [
                    {
                        "label": "AUC",
                        "value": "auc.mean",
                        "fmt": ".3f",
                        "lo": "auc.min",
                        "hi": "auc.max",
                    },
                    {"label": "Cells", "value": "n"},
                ],
                "finding": ["Over {{n}} cells the AUC was {{auc.mean:.2f}}."],
                "traps": [{"id": "spatial-leakage", "how": "AUC {{auc.mean:.3f}}."}],
                "figures": [{"path": "figs/f.png", "caption": "A figure."}],
                "documents": [{"title": "Walk", "path": "walk.md"}],
                "verification": {"tests": "tests.n"},
            }
        )
    )
    return pdir


def manifest() -> dict:
    return json.loads((b.ROOT / "manifest.json").read_text())


def test_numbers_come_from_ledger(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    p = b.load_project({"path": str(pdir)}, manifest())
    assert p["headline"][0]["shown"] == "0.638"
    assert p["headline"][0]["spread"] == "0.627 to 0.649"
    assert p["headline"][1]["shown"] == "5,707"
    assert "5,707" in p["finding"][0] and "0.64" in p["finding"][0]
    assert 'data-key="auc.mean"' in p["finding"][0]
    assert p["verification"]["tests_n"] == 19
    assert p["documents"][0]["html"].startswith("<h1")


def test_unknown_key_fails(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    card = json.loads((pdir / "portfolio.json").read_text())
    card["finding"] = ["{{does.not.exist}}"]
    (pdir / "portfolio.json").write_text(json.dumps(card))
    with pytest.raises(KeyError):
        b.load_project({"path": str(pdir)}, manifest())


def test_unknown_trap_fails(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    card = json.loads((pdir / "portfolio.json").read_text())
    card["traps"] = [{"id": "not-a-trap", "how": "x"}]
    (pdir / "portfolio.json").write_text(json.dumps(card))
    with pytest.raises(KeyError):
        b.load_project({"path": str(pdir)}, manifest())


def test_missing_figure_fails(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    card = json.loads((pdir / "portfolio.json").read_text())
    card["figures"] = [{"path": "figs/missing.png", "caption": "x"}]
    (pdir / "portfolio.json").write_text(json.dumps(card))
    with pytest.raises(FileNotFoundError):
        b.load_project({"path": str(pdir)}, manifest())


def test_custom_sources(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    (pdir / "runs" / "a").mkdir(parents=True)
    (pdir / "runs" / "b").mkdir()
    (pdir / "runs" / "a" / "score.json").write_text(json.dumps({"summary": {"passed": 10}}))
    (pdir / "runs" / "b" / "score.json").write_text(json.dumps({"summary": {"passed": 5}}))
    (pdir / "log.csv").write_text("step,rows_removed\nmedium,1553\nunits,10\n")
    led = b.Ledger(pdir, {"type": "none"})
    gj = {"source": "glob_json", "glob": "runs/*/score.json", "path": "summary.passed"}
    assert led.resolve(gj)[0] == 15
    assert led.resolve({**gj, "op": "count"})[0] == 2
    assert led.resolve({"source": "count_files", "glob": "figs/*.png"})[0] == 1
    csv_ref = {
        "source": "csv",
        "path": "log.csv",
        "where": {"step": "medium"},
        "column": "rows_removed",
    }
    assert led.resolve(csv_ref)[0] == 1553


def test_fmt() -> None:
    assert b.fmt_value(0.1837, ".0%") == "18%"
    assert b.fmt_value(4.33, "money") == "$4.33"
    assert b.fmt_value(-19.9, "pct_signed") == "-20%"
    assert b.fmt_value(-65, "+d") == "-65"
    assert b.fmt_value(12345, None) == "12,345"
