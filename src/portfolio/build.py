"""Build the portfolio site.

Reads manifest.json, then each project's portfolio.json card. Every number shown on
the site is resolved at build time from the project's own results ledger (a cairn
numbers.json, a nested results.json, or an aggregate over run files); the card holds
keys, never values. Markdown documents are converted and embedded. Output is a plain
static site in site/.
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_.\-/]+)(?::([^}]+))?\}\}")


class Ledger:
    """Resolve numeric references against a project's recorded results."""

    def __init__(self, project_dir: Path, spec: dict[str, Any]):
        self.dir = project_dir
        self.spec = spec
        self.kind = spec.get("type", "none")
        self.data: Any = None
        self.provenance: dict[str, str] = {}
        if self.kind in {"cairn", "json"}:
            self.data = json.loads((project_dir / spec["path"]).read_text())

    def resolve(self, ref: str | dict[str, Any]) -> tuple[Any, str]:
        """Return (value, provenance string)."""
        if isinstance(ref, dict):
            return self._resolve_custom(ref)
        if self.kind == "cairn":
            entry = self.data[ref]
            prov = f"{self.spec['path']} key {ref} (from {entry.get('source', '?')})"
            return entry["value"], prov
        if self.kind == "json":
            node = self.data
            for part in ref.split("."):
                node = node[part]
            return node, f"{self.spec['path']} path {ref}"
        raise KeyError(f"no default ledger for reference {ref!r}")

    def _resolve_custom(self, ref: dict[str, Any]) -> tuple[Any, str]:
        src = ref["source"]
        if src == "glob_json":
            files = sorted(glob.glob(str(self.dir / ref["glob"])))
            vals = []
            for f in files:
                node = json.loads(Path(f).read_text())
                for part in ref["path"].split("."):
                    node = node[part]
                vals.append(node)
            op = ref.get("op", "sum")
            if op == "sum":
                total = sum(vals)
                value = round(total, ref.get("round", 6)) if isinstance(total, float) else total
            elif op == "count":
                value = len(vals)
            elif op == "count_true":
                value = sum(1 for v in vals if v)
            else:
                raise ValueError(op)
            return value, f"{op} of {ref['path']} over {len(files)} files matching {ref['glob']}"
        if src == "count_files":
            matches = glob.glob(str(self.dir / ref["glob"]), recursive=True)
            files = [f for f in matches if Path(f).is_file()]
            return len(files), f"count of files matching {ref['glob']}"
        if src == "regex_count":
            pat = re.compile(ref["pattern"], re.M)
            n = 0
            files = sorted(glob.glob(str(self.dir / ref["glob"]), recursive=True))
            for f in files:
                n += len(pat.findall(Path(f).read_text()))
            return n, f"count of /{ref['pattern']}/ over {len(files)} files matching {ref['glob']}"
        if src == "csv":
            import csv

            rows = list(csv.DictReader((self.dir / ref["path"]).open()))
            for k, v in ref.get("where", {}).items():
                rows = [r for r in rows if r.get(k) == v]
            col = ref["column"]
            op = ref.get("op", "first")
            if op == "first":
                value: Any = rows[0][col]
                value = int(value) if re.fullmatch(r"-?\d+", value) else float(value)
            elif op == "sum":
                value = sum(float(r[col]) for r in rows)
                value = int(value) if value.is_integer() else value
            elif op == "count":
                value = len(rows)
            else:
                raise ValueError(op)
            return value, f"{ref['path']} column {col} ({op}, where {ref.get('where', {})})"
        if src == "json_file":
            node = json.loads((self.dir / ref["path"]).read_text())
            for part in ref["key"].split("."):
                node = node[part]
            return node, f"{ref['path']} path {ref['key']}"
        raise ValueError(f"unknown source {src}")


def fmt_value(value: Any, spec: str | None) -> str:
    if spec is None:
        if isinstance(value, float):
            return f"{value:g}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)
    if spec == "money":
        return f"${value:,.2f}"
    if spec == "pct_signed":
        return f"{value:+.0f}%"
    return f"{value:{spec}}"


def substitute(text: str, ledger: Ledger, used: list[dict[str, Any]]) -> str:
    """Replace {{key}} and {{key:fmt}} with resolved, formatted values."""

    def repl(m: re.Match[str]) -> str:
        key, spec = m.group(1), m.group(2)
        value, prov = ledger.resolve(key)
        shown = fmt_value(value, spec)
        used.append({"key": key, "value": value, "shown": shown, "provenance": prov})
        return (
            f'<span class="num" title="{html.escape(prov)}" data-key="{html.escape(key)}">'
            f"{html.escape(shown)}</span>"
        )

    return PLACEHOLDER.sub(repl, text)


def md_to_html(text: str) -> str:
    return markdown.markdown(
        text, extensions=["tables", "fenced_code", "toc", "sane_lists"], output_format="html5"
    )


def load_project(entry: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any] | None:
    pdir = (ROOT / entry["path"]).resolve()
    card_path = pdir / "portfolio.json"
    if not card_path.exists():
        if entry.get("optional"):
            return None
        raise FileNotFoundError(card_path)
    card = json.loads(card_path.read_text())
    ledger = Ledger(pdir, card.get("ledger", {"type": "none"}))
    used: list[dict[str, Any]] = []

    headline = []
    for item in card.get("headline", []):
        value, prov = ledger.resolve(item["value"])
        row = {
            "label": item["label"],
            "shown": fmt_value(value, item.get("fmt")),
            "unit": item.get("unit", ""),
            "provenance": prov,
            "key": item["value"] if isinstance(item["value"], str) else "",
            "note": substitute(item.get("note", ""), ledger, used),
        }
        if "lo" in item and "hi" in item:
            lo, _ = ledger.resolve(item["lo"])
            hi, _ = ledger.resolve(item["hi"])
            row["spread"] = f"{fmt_value(lo, item.get('fmt'))} to {fmt_value(hi, item.get('fmt'))}"
            row["spread_kind"] = item.get("spread_kind", "range")
        headline.append(row)

    finding = [substitute(p, ledger, used) for p in card.get("finding", [])]
    traps = []
    for t in card.get("traps", []):
        tid = t["id"]
        if tid not in manifest["traps"]:
            raise KeyError(f"{card['slug']}: unknown trap {tid}")
        traps.append(
            {
                "id": tid,
                "title": manifest["traps"][tid]["title"],
                "how": substitute(t["how"], ledger, used),
            }
        )

    figures = []
    for f in card.get("figures", []):
        src = pdir / f["path"]
        if not src.exists():
            raise FileNotFoundError(src)
        figures.append(
            {
                "src": src,
                "name": Path(f["path"]).name,
                "caption": substitute(f["caption"], ledger, used),
            }
        )

    docs = []
    for d in card.get("documents", []):
        p = pdir / d["path"]
        if not p.exists():
            raise FileNotFoundError(p)
        docs.append({"title": d["title"], "path": d["path"], "html": md_to_html(p.read_text())})

    verification = dict(card.get("verification", {}))
    if "frozen" in verification:
        frozen = json.loads((pdir / verification["frozen"]).read_text())
        verification["frozen_at"] = frozen.get("frozen_at", "")
    if "tests" in verification:
        n, prov = ledger.resolve(verification["tests"])
        verification["tests_n"] = n
        verification["tests_prov"] = prov
    git_head = ""
    head_file = pdir / ".git" / "HEAD"
    if head_file.exists():
        ref = head_file.read_text().strip()
        if ref.startswith("ref: "):
            rf = pdir / ".git" / ref[5:]
            git_head = rf.read_text().strip()[:7] if rf.exists() else ""
        else:
            git_head = ref[:7]

    return {
        "slug": card["slug"],
        "title": card["title"],
        "kind": card.get("kind", "study"),
        "status": card.get("status", "complete"),
        "question": card["question"],
        "one_liner": card.get("one_liner", ""),
        "aim": card.get("aim", ""),
        "hypothesis": card.get("hypothesis", ""),
        "scope": card.get("scope", ""),
        "conclusion": card.get("conclusion", ""),
        "headline": headline,
        "finding": finding,
        "traps": traps,
        "figures": figures,
        "not_claimed": card.get("not_claimed", []),
        "documents": docs,
        "verification": verification,
        "links": card.get("links", {}),
        "data": card.get("data", []),
        "stack": card.get("stack", []),
        "git_head": git_head,
        "numbers_used": used,
        "dir": pdir,
    }


def build(out: Path, artifact_index: bool = True) -> list[dict[str, Any]]:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    projects = [p for p in (load_project(e, manifest) for e in manifest["projects"]) if p]

    if out.exists():
        shutil.rmtree(out)
    (out / "projects").mkdir(parents=True)
    for p in projects:
        adir = out / "assets" / p["slug"]
        adir.mkdir(parents=True, exist_ok=True)
        for f in p["figures"]:
            shutil.copy(f["src"], adir / f["name"])
            f["url"] = f"assets/{p['slug']}/{f['name']}"

    built_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    css = (ROOT / "templates" / "style.css").read_text()
    common = {
        "manifest": manifest,
        "projects": projects,
        "built_at": built_at,
        "css": css,
    }

    traps_index: dict[str, list[dict[str, Any]]] = {tid: [] for tid in manifest["traps"]}
    for p in projects:
        for t in p["traps"]:
            traps_index[t["id"]].append({"project": p, "how": t["how"]})
    trap_rows = [
        {"id": tid, **manifest["traps"][tid], "appearances": traps_index[tid]}
        for tid in manifest["traps"]
        if traps_index[tid]
    ]

    n_numbers = sum(len(p["numbers_used"]) + len(p["headline"]) for p in projects)
    index_html = env.get_template("index.html").render(
        **common, root="", trap_rows=trap_rows, n_numbers=n_numbers, wrapper=True
    )
    (out / "index.html").write_text(index_html)
    if artifact_index:
        (out / "_artifact_index.html").write_text(
            env.get_template("index.html").render(
                **common, root="", trap_rows=trap_rows, n_numbers=n_numbers, wrapper=False
            )
        )
    (out / "failure-modes.html").write_text(
        env.get_template("traps.html").render(**common, root="", trap_rows=trap_rows, wrapper=True)
    )
    for p in projects:
        (out / "projects" / f"{p['slug']}.html").write_text(
            env.get_template("project.html").render(**common, root="../", p=p, wrapper=True)
        )
    (out / "numbers.json").write_text(
        json.dumps(
            {
                p["slug"]: {
                    "headline": [
                        {k: v for k, v in h.items() if k != "note"} for h in p["headline"]
                    ],
                    "inline": p["numbers_used"],
                }
                for p in projects
            },
            indent=1,
            default=str,
        )
    )
    return projects


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "site"))
    args = ap.parse_args()
    projects = build(Path(args.out))
    for p in projects:
        n = len(p["numbers_used"]) + len(p["headline"])
        print(
            f"{p['slug']:28s} {n:3d} numbers  {len(p['figures'])} figures  "
            f"{len(p['documents'])} docs"
        )
    print(f"site written to {args.out}")


if __name__ == "__main__":
    main()
