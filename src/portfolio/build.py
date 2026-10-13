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
import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[2]
GF = "https://fonts.googleapis.com/css2?"
FONTS = {
    "style.css": GF
    + "family=Lora:ital,wght@0,400;0,600;0,700;1,400&family=Nunito+Sans:wght@400;600"
    "&family=JetBrains+Mono:wght@400&display=swap",
    "a-manuscript.css": GF
    + "family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400"
    "&family=Source+Code+Pro:wght@400;500&display=swap",
    "b-datasheet.css": GF + "family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;500"
    "&display=swap",
    "c-catalogue.css": GF + "family=Source+Sans+3:wght@400;600;700&family=Source+Code+Pro:wght@400"
    "&display=swap",
    "d-slate.css": GF + "family=Inter+Tight:wght@400;600&family=JetBrains+Mono:wght@400;500"
    "&display=swap",
    "e-classic.css": GF
    + "family=Sora:wght@400;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;"
    "0,8..60,600;1,8..60,400&family=JetBrains+Mono:wght@400&display=swap",
    "f-warm.css": GF
    + "family=Lora:ital,wght@0,400;0,600;0,700;1,400&family=Nunito+Sans:wght@400;600"
    "&family=JetBrains+Mono:wght@400&display=swap",
    "g-clean.css": GF
    + "family=Figtree:wght@400;600;700&family=JetBrains+Mono:wght@400&display=swap",
    "h-magazine.css": GF
    + "family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Nunito+Sans:wght@400;600"
    "&family=JetBrains+Mono:wght@400&display=swap",
}
PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_.\-/]+)(?::([^}]+))?\}\}")


class Ledger:
    """Resolve numeric references against a project's recorded results."""

    def __init__(
        self, project_dir: Path, spec: dict[str, Any], sources: dict[str, Any] | None = None
    ):
        self.dir = project_dir
        self.spec = spec
        self.kind = spec.get("type", "none")
        self.data: Any = None
        self.provenance: dict[str, str] = {}
        self.sources = sources or {}
        if self.kind in {"cairn", "json"}:
            self.data = json.loads((project_dir / spec["path"]).read_text())

    def resolve(self, ref: str | dict[str, Any]) -> tuple[Any, str]:
        """Return (value, provenance string)."""
        if isinstance(ref, dict):
            return self._resolve_custom(ref)
        if ref in self.sources:
            return self._resolve_custom(self.sources[ref])
        if self.kind == "cairn":
            entry = self.data[ref]
            prov = f"{self.spec['path']} key {ref} (from {entry.get('source', '?')})"
            return entry["value"], prov
        if self.kind == "json":
            node = self.data
            for part in ref.split("."):
                if isinstance(node, list):
                    node = node[int(part)]
                else:
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

    parts = []
    end = 0
    for match in PLACEHOLDER.finditer(text):
        parts.append(html.escape(text[end : match.start()]))
        parts.append(repl(match))
        end = match.end()
    parts.append(html.escape(text[end:]))
    rendered = "".join(parts)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError(f"unresolved or malformed result placeholder: {text!r}")
    return rendered


def git_revision(project_dir: Path) -> tuple[str, bool]:
    """Use Git itself so packed refs and linked worktrees work too."""
    try:
        head = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(project_dir), "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return head, bool(dirty)
    except (OSError, subprocess.CalledProcessError):
        return "", False


def verification_evidence(
    project_dir: Path, spec: dict[str, Any], ledger: Ledger, head: str, dirty: bool
) -> dict[str, Any]:
    """A definition count or a literal card label is not an execution result."""
    result = {"harness": spec.get("harness", ""), "verify": "not evidenced"}
    if "frozen" in spec:
        frozen = json.loads((project_dir / spec["frozen"]).read_text())
        result["frozen_at"] = frozen.get("frozen_at", "")
    if "tests" in spec:
        n, provenance = ledger.resolve(spec["tests"])
        result.update(tests_n=n, tests_prov=provenance, tests_label="recorded test count")
        ref = spec["tests"]
        if isinstance(ref, dict) and ref.get("source") == "regex_count":
            result["tests_label"] = "test definitions"
    if "verify" in spec:
        result["reported_status"] = str(spec["verify"])
    artifact = spec.get("artifact")
    if not artifact:
        return result
    path = (project_dir / artifact).resolve()
    if not path.is_relative_to(project_dir.resolve()):
        raise ValueError("verification artifact must be inside its project")
    if not path.is_file():
        result["verify"] = "artifact missing"
        return result
    evidence = json.loads(path.read_text())
    result.update(
        artifact=artifact,
        checked_commit=evidence.get("source_commit", ""),
        checked_at=evidence.get("checked_at", evidence.get("finished_at", "")),
    )
    source_files = evidence.get("source_files", {})
    hashes_match = bool(source_files) and all(
        (project_dir / name).resolve().is_relative_to(project_dir.resolve())
        and (project_dir / name).is_file()
        and hashlib.sha256((project_dir / name).read_bytes()).hexdigest() == digest
        for name, digest in source_files.items()
    )
    analyses = evidence.get("analyses", {})
    successful = evidence.get("ok") is True
    outputs_match = True
    if analyses:
        successful = all(item.get("exit_code") == 0 for item in analyses.values())
        for item in analyses.values():
            output = (path.parent / item.get("output", "")).resolve()
            outputs_match &= (
                output.is_relative_to(project_dir.resolve())
                and output.is_file()
                and hashlib.sha256(output.read_bytes()).hexdigest() == item.get("output_sha256")
            )
        result["execution_label"] = "worked-example execution"
        result["analyses_n"] = len(analyses)
    if not result["checked_commit"] or not result["checked_at"]:
        result["verify"] = "artifact lacks revision or time"
    elif source_files and not hashes_match:
        result["verify"] = "source hash mismatch; evidence invalid"
    elif not outputs_match:
        result["verify"] = "output hash mismatch; evidence invalid"
    elif hashes_match:
        result["verify"] = (
            "pass; recorded source hashes match"
            if successful
            else "failed; recorded source hashes match"
        )
    elif dirty or result["checked_commit"] != head:
        result["verify"] = "historical evidence; source has changed"
    elif successful:
        result["verify"] = "pass at this revision"
    else:
        result["verify"] = "failed at this revision"
    if isinstance(evidence.get("tests"), dict):
        result["test_execution"] = evidence["tests"]
    if spec.get("test_artifact"):
        result["tests_evidence"] = verification_evidence(
            project_dir, {"artifact": spec["test_artifact"]}, ledger, head, dirty
        )
    return result


def literal_result_numbers(card: dict[str, Any], enforce: bool = True) -> list[dict[str, str]]:
    """Audit result-bearing prose; declared constants are dates, thresholds, etc."""
    constants = card.get("numeric_constants", {})
    fields = [
        (field, card.get(field, ""))
        for field in ("conclusion", "aim", "hypothesis", "scope", "question", "one_liner")
    ]
    fields.extend(
        (field, text) for field in ("not_claimed", "data", "stack") for text in card.get(field, [])
    )
    fields.extend(("finding", text) for text in card.get("finding", []))
    fields.append(("story", card.get("_story_text", "")))
    summary = card.get("summary", {})
    fields.append(("summary.question", summary.get("question", "")))
    fields.append(("summary.result", summary.get("result", "")))
    fields.extend(("summary.techniques", t) for t in summary.get("techniques", []))
    fields.extend(
        ("summary.pitfalls", t["text"] if isinstance(t, dict) else t)
        for t in summary.get("pitfalls", [])
    )
    fields.extend(("headline.label", item["label"]) for item in card.get("headline", []))
    fields.extend(("headline.note", item.get("note", "")) for item in card.get("headline", []))
    fields.extend(("traps.how", item["how"]) for item in card.get("traps", []))
    fields.extend(("figures.caption", item["caption"]) for item in card.get("figures", []))
    literals = []
    for field, text in fields:
        plain = PLACEHOLDER.sub("", text)
        for match in re.finditer(r"(?<![\w])[-+]?\d+(?:[.,]\d+)*(?![\w])", plain):
            number = match.group()
            if not constants.get(number):
                literals.append({"field": field, "number": number})
    if literals and enforce and card.get("strict_numbers"):
        raise ValueError(f"{card['slug']}: undeclared literal result numbers: {literals}")
    return literals


def md_to_html(
    text: str,
    project_dir: Path | None = None,
    document_path: str = "",
    repository: str = "",
    revision: str = "",
) -> str:
    converter = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists"], output_format="html5"
    )
    if project_dir and repository and revision:

        class RepositoryLinks(markdown.treeprocessors.Treeprocessor):
            def run(self, root):
                for element in root.iter():
                    attribute = (
                        "href" if element.tag == "a" else "src" if element.tag == "img" else ""
                    )
                    if not attribute or not element.get(attribute):
                        continue
                    href = element.get(attribute)
                    parts = urlsplit(href)
                    if parts.scheme or parts.netloc or not parts.path:
                        continue
                    target = (
                        project_dir / Path(document_path).parent / unquote(parts.path)
                    ).resolve()
                    target_root, target_repository, target_revision = (
                        project_dir.resolve(),
                        repository,
                        revision,
                    )
                    if not target.is_relative_to(target_root):
                        parent = project_dir.parent.resolve()
                        if not target.is_relative_to(parent):
                            continue
                        neighbor = parent / target.relative_to(parent).parts[0]
                        neighbor_card = neighbor / "portfolio.json"
                        if not neighbor_card.is_file():
                            continue
                        target_repository = (
                            json.loads(neighbor_card.read_text())
                            .get("links", {})
                            .get("Repository", "")
                        )
                        target_revision, _ = git_revision(neighbor)
                        target_root = neighbor.resolve()
                        if not target_repository or not target_revision:
                            continue
                    relative = target.relative_to(target_root).as_posix()
                    relative = "" if relative == "." else "/" + quote(relative)
                    suffix = f"#{parts.fragment}" if parts.fragment else ""
                    view = "tree" if target.is_dir() else "blob"
                    base_url = f"{target_repository.rstrip('/')}/{view}/{target_revision}{relative}"
                    url = base_url + suffix
                    if element.tag == "img":
                        url = base_url + "?raw=true" + suffix
                    element.set(attribute, url)
                return root

        converter.treeprocessors.register(RepositoryLinks(converter), "repository_links", 5)
    return converter.convert(text)


def load_project(entry: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any] | None:
    pdir = (ROOT / entry["path"]).resolve()
    card_path = pdir / "portfolio.json"
    if not card_path.exists():
        if entry.get("optional"):
            return None
        raise FileNotFoundError(card_path)
    card = json.loads(card_path.read_text())
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", card["slug"]):
        raise ValueError(f"invalid project slug: {card['slug']!r}")
    git_head, git_dirty = git_revision(pdir)
    if card.get("story"):
        story_path = pdir / card["story"]
        if not story_path.exists():
            raise FileNotFoundError(story_path)
        card["_story_text"] = story_path.read_text()
    ledger = Ledger(pdir, card.get("ledger", {"type": "none"}), card.get("sources"))
    literal_numbers = literal_result_numbers(card)
    used: list[dict[str, Any]] = []

    headline = []
    for item in card.get("headline", []):
        value, prov = ledger.resolve(item["value"])
        row = {
            "label": substitute(item["label"], ledger, used),
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

    story_html = ""
    story_figures: list[dict[str, Any]] = []
    if card.get("story"):
        story_text = card["_story_text"]

        def embed(m: re.Match[str]) -> str:
            caption, rel = m.group(1), m.group(2)
            src = pdir / rel
            if not src.exists():
                raise FileNotFoundError(f"{card['slug']} story figure: {src}")
            name = Path(rel).name
            if all(f["name"] != name for f in story_figures):
                story_figures.append({"src": src, "name": name})
            alt = re.sub(r"<[^>]+>", "", caption)
            return (
                f'<figure class="figure"><img src="../assets/{card["slug"]}/{name}" '
                f'alt="{html.escape(alt)}" loading="lazy">'
                f"<figcaption>{caption}</figcaption></figure>"
            )

        story_text = substitute(story_text, ledger, used)
        story_text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+\.(?:png|svg|jpg))\)", embed, story_text)
        story_html = md_to_html(
            story_text, pdir, card["story"], card.get("links", {}).get("Repository", ""), git_head
        )

    docs = []
    for d in card.get("documents", []):
        p = pdir / d["path"]
        if not p.exists():
            raise FileNotFoundError(p)
        document = p.read_text()
        if p.suffix in {".json", ".txt", ".csv"}:
            document = "```\n" + document + "\n```"
        docs.append(
            {
                "title": d["title"],
                "path": d["path"],
                "html": md_to_html(
                    document,
                    pdir,
                    d["path"],
                    card.get("links", {}).get("Repository", ""),
                    git_head,
                ),
            }
        )

    verification = verification_evidence(
        pdir, card.get("verification", {}), ledger, git_head, git_dirty
    )

    def prose(field: str) -> str:
        return substitute(card.get(field, ""), ledger, used)

    return {
        "slug": card["slug"],
        "title": card["title"],
        "kind": card.get("kind", "study"),
        "status": card.get("status", "complete"),
        "question": prose("question"),
        "one_liner": prose("one_liner"),
        "aim": prose("aim"),
        "hypothesis": prose("hypothesis"),
        "scope": prose("scope"),
        "conclusion": prose("conclusion"),
        "summary": {
            "question": substitute(card.get("summary", {}).get("question", ""), ledger, used),
            "techniques": [
                substitute(t, ledger, used) for t in card.get("summary", {}).get("techniques", [])
            ],
            "pitfalls": [
                {
                    "id": t["id"] if isinstance(t, dict) else "",
                    "text": substitute(t["text"] if isinstance(t, dict) else t, ledger, used),
                }
                for t in card.get("summary", {}).get("pitfalls", [])
            ]
            or [{"id": t["id"], "text": t["title"]} for t in traps],
            "result": substitute(card.get("summary", {}).get("result", ""), ledger, used),
        },
        "headline": headline,
        "finding": finding,
        "traps": traps,
        "figures": figures,
        "story": story_html,
        "story_figures": story_figures,
        "not_claimed": [substitute(text, ledger, used) for text in card.get("not_claimed", [])],
        "documents": docs,
        "verification": verification,
        "links": card.get("links", {}),
        "data": [substitute(text, ledger, used) for text in card.get("data", [])],
        "stack": [substitute(text, ledger, used) for text in card.get("stack", [])],
        "git_head": git_head[:7],
        "source_commit": git_head,
        "source_dirty": git_dirty,
        "literal_numbers": literal_numbers,
        "numbers_used": used,
        "dir": pdir,
    }


def method_chooser(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Render the method-chooser document (a Markdown file with Mermaid charts kept in one of
    the project checkouts) with its links resolved to that repository at its current
    revision. Returns None when the manifest names no chooser."""
    entry = manifest.get("method_chooser")
    if not entry:
        return None
    pdir = (ROOT / entry["project"]).resolve()
    path = pdir / entry["path"]
    if not (pdir / "portfolio.json").is_file() or not path.is_file():
        print(f"method chooser skipped: {path} is not checked out")
        return None
    card = json.loads((pdir / "portfolio.json").read_text())
    revision, dirty = git_revision(pdir)
    repository = card.get("links", {}).get("Repository", "")
    return {
        "title": entry.get("title", "Choosing a method"),
        "html": md_to_html(path.read_text(), pdir, entry["path"], repository, revision),
        "source_url": f"{repository.rstrip('/')}/blob/{revision}/{entry['path']}"
        if repository and revision
        else "",
        "project": card.get("title", pdir.name),
        "slug": card.get("slug", pdir.name),
        "revision": revision,
        "dirty": dirty,
    }


def _anchor(term: str) -> str:
    return "t-" + re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")


def load_glossary() -> dict[str, Any]:
    """Read glossary.json; every see_also target must be an entry."""
    path = ROOT / "glossary.json"
    if not path.exists():
        return {"letters": [], "grouped": []}
    entries = json.loads(path.read_text())["entries"]
    by_term = {e["term"]: e for e in entries}
    for e in entries:
        e["anchor"] = _anchor(e["term"])
        for target in e.get("see_also", []):
            if target not in by_term:
                raise KeyError(f"glossary: see_also target {target!r} is not an entry")
    for e in entries:
        e["see_also"] = [{"term": t, "anchor": by_term[t]["anchor"]} for t in e.get("see_also", [])]
    entries.sort(key=lambda e: e["term"].lower())
    grouped: list[tuple[str, list[dict[str, Any]]]] = []
    for e in entries:
        first = e["term"][0].upper()
        letter = first if first.isalpha() else "#"
        if not grouped or grouped[-1][0] != letter:
            grouped.append((letter, []))
        grouped[-1][1].append(e)
    return {"letters": [g[0] for g in grouped], "grouped": grouped}


def _render_site(
    out: Path,
    artifact_index: bool = True,
    css_path: Path | None = None,
    strict_numbers: bool = False,
) -> list[dict[str, Any]]:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    projects = [p for p in (load_project(e, manifest) for e in manifest["projects"]) if p]
    if strict_numbers and any(project["literal_numbers"] for project in projects):
        audit = {
            project["slug"]: project["literal_numbers"]
            for project in projects
            if project["literal_numbers"]
        }
        raise ValueError(f"undeclared literal result numbers: {audit}")

    (out / "projects").mkdir(parents=True)
    for p in projects:
        adir = out / "assets" / p["slug"]
        adir.mkdir(parents=True, exist_ok=True)
        for f in p["figures"]:
            shutil.copy(f["src"], adir / f["name"])
            f["url"] = f"assets/{p['slug']}/{f['name']}"
        for f in p["story_figures"]:
            shutil.copy(f["src"], adir / f["name"])

    built_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    css = (css_path or ROOT / "templates" / "style.css").read_text()
    fonts_url = FONTS.get((css_path or Path("style.css")).name, FONTS["style.css"])
    common = {
        "manifest": manifest,
        "projects": projects,
        "built_at": built_at,
        "css": css,
        "fonts_url": fonts_url,
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
    (out / "references.html").write_text(
        env.get_template("references.html").render(**common, root="", wrapper=True)
    )
    chooser = method_chooser(manifest)
    (out / "glossary.html").write_text(
        env.get_template("glossary.html").render(**common, root="", wrapper=True, **load_glossary())
    )
    (out / "methods.html").write_text(
        env.get_template("methods.html").render(**common, root="", chooser=chooser, wrapper=True)
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
                    "source_commit": p["source_commit"],
                    "source_dirty": p["source_dirty"],
                    "verification": p["verification"],
                    "literal_numbers": p["literal_numbers"],
                }
                for p in projects
            },
            indent=1,
            default=str,
        )
    )
    return projects


OUTPUT_MARKER = ".portfolio-output"
OUTPUT_VERSION = "portfolio-output-v1\n"


def validate_output(out: Path) -> Path:
    """Only replace a directory previously generated by this builder."""
    if any(component.is_symlink() for component in (out.absolute(), *out.absolute().parents)):
        raise ValueError("output path may not contain a symlink")
    resolved = out.resolve()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    protected = [ROOT.resolve(), Path.home().resolve()]
    protected.extend((ROOT / item["path"]).resolve() for item in manifest["projects"])
    for source in protected:
        if resolved == source or source.is_relative_to(resolved):
            raise ValueError(f"output would replace a source directory: {resolved}")
    default_site = ROOT.resolve() / "site"
    if not resolved.is_relative_to(default_site):
        for source in protected:
            if source != Path.home().resolve() and resolved.is_relative_to(source):
                raise ValueError(f"output is inside a source directory: {resolved}")
        for parent in (resolved, *resolved.parents):
            if (parent / ".git").exists():
                raise ValueError(f"output is inside another Git checkout: {resolved}")
    if resolved.exists():
        marker = resolved / OUTPUT_MARKER
        if not resolved.is_dir() or not marker.is_file() or marker.read_text() != OUTPUT_VERSION:
            raise ValueError(f"refusing to replace an unmarked output directory: {resolved}")
    return resolved


def build(
    out: Path,
    artifact_index: bool = True,
    css_path: Path | None = None,
    strict_numbers: bool = False,
) -> list[dict[str, Any]]:
    out = validate_output(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out.name}-stage-", dir=out.parent) as directory:
        staging = Path(directory) / "site"
        projects = _render_site(
            staging,
            artifact_index=artifact_index,
            css_path=css_path,
            strict_numbers=strict_numbers,
        )
        (staging / OUTPUT_MARKER).write_text(OUTPUT_VERSION)
        # Revalidate after rendering and preserve the last successful build on failure.
        validate_output(out)
        backup = Path(directory) / "previous"
        if out.exists():
            out.rename(backup)
        try:
            staging.rename(out)
        except OSError:
            if backup.exists():
                backup.rename(out)
            raise
    return projects


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--css", default=None, help="alternative stylesheet (design variant)")
    ap.add_argument(
        "--strict-numbers", action="store_true", help="fail on undeclared literal results"
    )
    ap.add_argument(
        "--audit-only", action="store_true", help="audit card literals without building"
    )
    args = ap.parse_args()
    if args.audit_only:
        manifest = json.loads((ROOT / "manifest.json").read_text())
        failed = False
        for entry in manifest["projects"]:
            path = ROOT / entry["path"] / "portfolio.json"
            if path.exists():
                card = json.loads(path.read_text())
                literals = literal_result_numbers(card, enforce=False)
                print(card["slug"], literals)
                failed |= bool(literals) and (
                    args.strict_numbers or card.get("strict_numbers", False)
                )
        if failed:
            raise SystemExit("undeclared literal result numbers")
        return
    projects = build(
        Path(args.out),
        css_path=Path(args.css) if args.css else None,
        strict_numbers=args.strict_numbers,
    )
    for p in projects:
        n = len(p["numbers_used"]) + len(p["headline"])
        print(
            f"{p['slug']:28s} {n:3d} numbers  {len(p['figures'])} figures  "
            f"{len(p['documents'])} docs"
        )
        if p["literal_numbers"]:
            print(f"  literal-number audit: {p['literal_numbers']}")
    print(f"site written to {args.out}")


if __name__ == "__main__":
    main()
