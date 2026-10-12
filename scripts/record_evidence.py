"""Execute an explicitly selected check and record its source revision and hashes.

Use heavy checks on the Mac mini or CI. Example:
uv run python scripts/record_evidence.py --project ../cairn -- \
    uv run pytest tests/test_harness.py -q
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def git(project: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(project), *args], text=True).strip()


def source_hashes(project: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((project / name).read_bytes()).hexdigest()
        for name in git(project, "ls-files").splitlines()
        if Path(name).suffix in {".py", ".toml", ".lock", ".yml", ".yaml", ".sql", ".lkml"}
        and name != "warehouse/.user.yml"
        and (project / name).is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", default="reports/check-evidence.json")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide an explicit command after --")
    project = args.project.resolve()
    output = (project / args.output).resolve()
    if not output.is_relative_to(project):
        parser.error("evidence must be written inside the checked project")
    revision = git(project, "rev-parse", "HEAD")
    sources = source_hashes(project)
    started = datetime.now(UTC).isoformat()
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    proc = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True)
    print(proc.stdout, end="")
    print(proc.stderr, end="")
    unchanged = revision == git(project, "rev-parse", "HEAD") and sources == source_hashes(project)
    artifact = {
        "kind": "checks",
        "source_commit": revision,
        "source_files": sources,
        "checked_at": datetime.now(UTC).isoformat(),
        "started_at": started,
        "ok": proc.returncode == 0 and unchanged,
        "source_unchanged_during_check": unchanged,
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    summary = re.findall(r"(\d+) (passed|failed|skipped|errors?)", proc.stdout)
    if any(status == "passed" for _, status in summary):
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        for count, status in summary:
            counts["errors" if status in {"error", "errors"} else status] = int(count)
        artifact["tests"] = {**counts, "command": command}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n")
    return proc.returncode or (0 if unchanged else 1)


if __name__ == "__main__":
    raise SystemExit(main())
