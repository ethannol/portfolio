"""Execution evidence must identify the checked code and reject source drift."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

RECORDER = Path(__file__).resolve().parents[1] / "scripts" / "record_evidence.py"


@pytest.mark.parametrize("change_source", [False, True])
def test_recorder_rejects_source_changes_during_successful_command(
    tmp_path: Path, change_source: bool
) -> None:
    repo = tmp_path / "checked"
    repo.mkdir()
    (repo / "source.py").write_text("# original\n")
    body = "from pathlib import Path\nprint('1 passed in 0.01s')\n"
    if change_source:
        body += "Path('source.py').write_text('# changed\\n')\n"
    (repo / "check.py").write_text(body)
    for args in [
        ["init", "-b", "main"],
        ["add", "."],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.test",
            "commit",
            "-m",
            "fixture",
        ],
    ]:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    result = subprocess.run(
        [sys.executable, str(RECORDER), "--project", str(repo), "--", sys.executable, "check.py"],
        capture_output=True,
        text=True,
    )
    artifact = json.loads((repo / "reports" / "check-evidence.json").read_text())
    assert artifact["ok"] is (not change_source)
    assert result.returncode == int(change_source)
    assert len(artifact["source_commit"]) == 40
    assert "source.py" in artifact["source_files"]
    assert artifact["tests"]["passed"] == 1
