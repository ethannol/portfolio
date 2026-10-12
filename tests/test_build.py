"""The builder resolves every number from a ledger and refuses unknown keys."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jinja2 import TemplateSyntaxError

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


def edit_card(pdir: Path, **changes: object) -> None:
    path = pdir / "portfolio.json"
    card = json.loads(path.read_text())
    card.update(changes)
    path.write_text(json.dumps(card))


def test_all_prose_can_reference_named_sources(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    (pdir / "supplement.json").write_text('{"precision": 0.28}')
    edit_card(
        pdir,
        sources={
            "transfer.precision": {
                "source": "json_file",
                "path": "supplement.json",
                "key": "precision",
            }
        },
        conclusion="Precision {{transfer.precision:.0%}} over {{n}} cells.",
        not_claimed=["No claim outside {{n}} cells."],
        aim="Compare {{auc.mean:.3f}} with a reference.",
    )
    project = b.load_project({"path": str(pdir)}, manifest())
    assert "28%" in project["conclusion"]
    assert "5,707" in project["not_claimed"][0]
    assert "0.638" in project["aim"]
    assert any(item["key"] == "transfer.precision" for item in project["numbers_used"])


def test_malformed_placeholders_and_unescaped_html_fail_safely(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    edit_card(pdir, conclusion="<script>alert('x')</script> {{n}}")
    project = b.load_project({"path": str(pdir)}, manifest())
    assert "<script>" not in project["conclusion"]
    assert "&lt;script&gt;" in project["conclusion"]
    edit_card(pdir, conclusion="{{n:unfinished")
    with pytest.raises(ValueError, match="placeholder"):
        b.load_project({"path": str(pdir)}, manifest())


def test_literal_result_audit_distinguishes_declared_constants(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    edit_card(
        pdir,
        conclusion="AUC 0.638 in 2020.",
        numeric_constants={"2020": "study year"},
        strict_numbers=True,
    )
    with pytest.raises(ValueError, match="0.638"):
        b.load_project({"path": str(pdir)}, manifest())
    edit_card(pdir, conclusion="AUC {{auc.mean:.3f}} in 2020.")
    assert b.load_project({"path": str(pdir)}, manifest())["literal_numbers"] == []


def test_static_pass_and_test_definitions_are_not_execution_evidence(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    (pdir / "tests").mkdir()
    (pdir / "tests" / "test_a.py").write_text("def test_a():\n    pass\n")
    edit_card(
        pdir,
        verification={
            "verify": "pass",
            "tests": {"source": "regex_count", "glob": "tests/test_*.py", "pattern": "^def test_"},
        },
    )
    evidence = b.load_project({"path": str(pdir)}, manifest())["verification"]
    assert evidence["verify"] == "not evidenced"
    assert evidence["tests_n"] == 1
    assert evidence["tests_label"] == "test definitions"


@pytest.mark.parametrize(
    "dirty,commit,expected",
    [
        (False, "abc", "pass at this revision"),
        (False, "old", "historical evidence; source has changed"),
        (True, "abc", "historical evidence; source has changed"),
    ],
)
def test_verification_is_bound_to_revision_and_tracked_source(
    tmp_path: Path, dirty: bool, commit: str, expected: str
) -> None:
    pdir = make_project(tmp_path)
    (pdir / "check.json").write_text(
        json.dumps({"ok": True, "source_commit": commit, "checked_at": "2026-10-12T20:00:00Z"})
    )
    ledger = b.Ledger(pdir, {"type": "none"})
    result = b.verification_evidence(pdir, {"artifact": "check.json"}, ledger, "abc", dirty)
    assert result["verify"] == expected


def test_git_revision_handles_worktrees_and_packed_refs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    commands = [
        ["init", "-b", "main"],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.test",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
        ["pack-refs", "--all"],
        ["worktree", "add", "--detach", str(tmp_path / "worktree"), "HEAD"],
    ]
    for command in commands:
        subprocess.run(["git", "-C", str(repo), *command], check=True, capture_output=True)
    assert b.git_revision(repo)[0] == b.git_revision(tmp_path / "worktree")[0]
    assert len(b.git_revision(repo)[0]) == 40


def build_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    source = tmp_path / "builder"
    source.mkdir()
    shutil.copytree(b.ROOT / "templates", source / "templates")
    pdir = make_project(tmp_path)
    spec = manifest()
    spec["projects"] = [{"path": str(pdir)}]
    (source / "manifest.json").write_text(json.dumps(spec))
    monkeypatch.setattr(b, "ROOT", source)
    return source, pdir


def test_output_rejects_sources_and_unmarked_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, pdir = build_fixture(tmp_path, monkeypatch)
    out = tmp_path / "personal"
    out.mkdir()
    (out / "keep.txt").write_text("keep")
    for path in [source, pdir, tmp_path, out, source / "templates" / "generated"]:
        with pytest.raises(ValueError):
            b.build(path)
    assert (out / "keep.txt").read_text() == "keep"


def test_failed_rebuild_preserves_last_successful_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = build_fixture(tmp_path, monkeypatch)
    out = tmp_path / "published"
    b.build(out)
    original = (out / "index.html").read_bytes()
    (source / "templates" / "project.html").write_text("{{ malformed")
    with pytest.raises(TemplateSyntaxError):
        b.build(out)
    assert (out / "index.html").read_bytes() == original
    assert (out / b.OUTPUT_MARKER).read_text() == b.OUTPUT_VERSION


def test_hash_mismatch_cannot_fall_back_to_matching_commit(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    (pdir / "source.py").write_text("actual source")
    (pdir / "check.json").write_text(
        json.dumps(
            {
                "ok": True,
                "source_commit": "abc",
                "checked_at": "2026-10-12T20:00:00Z",
                "source_files": {"source.py": "incorrect digest"},
            }
        )
    )
    result = b.verification_evidence(
        pdir, {"artifact": "check.json"}, b.Ledger(pdir, {"type": "none"}), "abc", False
    )
    assert result["verify"] == "source hash mismatch; evidence invalid"


def test_analysis_output_hash_is_verified(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    (pdir / "source.py").write_text("source")
    digest = hashlib.sha256((pdir / "source.py").read_bytes()).hexdigest()
    (pdir / "output.txt").write_text("altered transcript")
    (pdir / "check.json").write_text(
        json.dumps(
            {
                "source_commit": "abc",
                "finished_at": "2026-10-12T20:00:00Z",
                "source_files": {"source.py": digest},
                "analyses": {
                    "source.py": {
                        "exit_code": 0,
                        "output": "output.txt",
                        "output_sha256": "incorrect digest",
                    }
                },
            }
        )
    )
    result = b.verification_evidence(
        pdir, {"artifact": "check.json"}, b.Ledger(pdir, {"type": "none"}), "abc", False
    )
    assert result["verify"] == "output hash mismatch; evidence invalid"


def test_embedded_document_links_resolve_against_document_location(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    rendered = b.md_to_html(
        "[Code](../analyses/example.py#section) [External](https://example.com) [Here](#local)",
        pdir,
        "docs/walk.md",
        "https://github.com/owner/project",
        "abc",
    )
    assert (
        'href="https://github.com/owner/project/blob/abc/analyses/example.py#section"' in rendered
    )
    assert 'href="https://example.com"' in rendered
    assert 'href="#local"' in rendered


def test_symlinked_parent_cannot_escape_output_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, pdir = build_fixture(tmp_path, monkeypatch)
    (source / "site").symlink_to(pdir, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        b.build(source / "site" / "new-directory")
    assert not (pdir / "new-directory").exists()


def test_slug_cannot_escape_staging_directory(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    edit_card(pdir, slug="../../escape")
    with pytest.raises(ValueError, match="slug"):
        b.load_project({"path": str(pdir)}, manifest())


def test_strict_audit_covers_limitations_and_data(tmp_path: Path) -> None:
    pdir = make_project(tmp_path)
    edit_card(
        pdir,
        not_claimed=["Only 22 observations."],
        data=["Data contained 99 rows."],
        strict_numbers=True,
    )
    with pytest.raises(ValueError, match="22"):
        b.load_project({"path": str(pdir)}, manifest())
