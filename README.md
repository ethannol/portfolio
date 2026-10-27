# Portfolio

[Read the portfolio](https://ethannol.github.io/portfolio/) · [GitHub profile](https://github.com/ethannol)

A static portfolio of environmental data studies, analysis tools, and worked statistical
examples. Study pages put the question and conclusion before the detailed investigation.
The default design uses system fonts, a white background, and simple text links; plots
and their captions carry the visual detail.

The builder reads the side-projects portfolio. It reads each project's `portfolio.json`
card and resolves result placeholders from that project's own ledger at build time:
a cairn `artifacts/numbers.json`, a nested `reports/results.json`, or aggregates over
run files. Conclusions, aims, findings, notes, limitations, data descriptions and captions
all support placeholders. Named supplementary sources allow frozen primary ledgers to
remain unchanged. Literal result numbers are audited in `numbers.json`; use
`--strict-numbers` to reject undeclared literals before publishing any output.

```bash
uv sync --extra dev
uv run portfolio-build          # writes site/
uv run pytest
```

`manifest.json` lists the project checkouts (sibling directories) and the cross-cutting
failure-mode taxonomy that cards reference. `site/` is generated and not committed.

## Card schema

```json
{
  "slug": "...", "title": "...", "kind": "study | harness | reference", "status": "...",
  "question": "...", "one_liner": "...",
  "ledger": {"type": "cairn | json | none", "path": "..."},
  "headline": [{"label": "...", "value": "<ledger key> | {source: ...}", "fmt": "...", "lo": "...", "hi": "..."}],
  "finding": ["prose with {{ledger.key:fmt}} placeholders"],
  "traps": [{"id": "<taxonomy id>", "how": "..."}],
  "figures": [{"path": "...", "caption": "..."}],
  "not_claimed": ["..."], "documents": [{"title": "...", "path": "..."}],
  "sources": {"supplement.precision": {"source": "json_file", "path": "reports/supplement.json", "key": "precision"}},
  "numeric_constants": {"2015": "pre-registered intervention year"},
  "verification": {"frozen": ".cairn/frozen.json", "tests": "<key or source>", "harness": "cairn", "artifact": "reports/check-evidence.json"},
  "data": ["..."], "stack": ["..."], "links": {"Repository": "..."}
}
```

Custom value sources: `glob_json` (sum, count or count_true of a path over files), `count_files`,
`regex_count`, `csv` (first, sum or count of a column with an optional filter), `json_file`.

## Check evidence

Source counts are labelled **test definitions**, and ledger counts **recorded test count**.
Neither establishes that tests pass now. A literal `verify: pass` in a card is not accepted
as evidence. An optional JSON artifact records the actual execution:

```json
{
  "source_commit": "<full checked Git commit>",
  "checked_at": "<UTC timestamp>",
  "ok": true,
  "tests": {"passed": 12, "failed": 0, "command": "uv run pytest tests/test_example.py"}
}
```

The builder compares the artifact revision to Git HEAD and checks for tracked source
changes. Older results remain visible as historical evidence. Git itself resolves HEAD,
including linked worktrees and packed refs. Actual verification artifacts, revision and
time are included in `numbers.json`; missing evidence is labelled accordingly.

Artifacts may also supply `source_files`, mapping relative source paths to SHA-256
digests. The renderer checks every recorded digest before accepting evidence, even at
a matching commit. This permits report-only commits after a checked source revision:
the label explicitly says the **recorded source hashes match**, rather than claiming
the new revision was executed. Worked-example manifests also have their output digests
checked. They record analysis execution separately from test execution; `test_artifact`
can attach the latter alongside an analysis artifact. Input snapshots remain documented
in each project's data manifest; the portfolio does not re-execute the analyses.

`scripts/record_evidence.py --project <checkout> -- <explicit check command>` executes a
selected check and records its revision, source hashes, timestamps, exit status and
transcript. Heavy checks belong on the Mac mini or CI. The recorder fails if checked
source changes during execution. Source counts remain separate from recorded test runs.
Embedded document links resolve against each document's location and point to repository
files at the recorded checkout revision, so chooser and transcript links work in the site.

## Output safety

Rendering happens in a staging directory. A failed build leaves the previous successful
site intact. Existing output can only be replaced if it carries this builder's
`.portfolio-output` marker. Source directories, their ancestors, other Git checkouts and
symlink outputs are rejected. The default `site/` is allowed inside this checkout.
An older unmarked generated site must be moved aside before the first new build.

## Publishing

The Pages workflow builds the site from this repository and the public studies on their
main branches. It resolves recorded results without rerunning analyses or making model
calls. Pushes to main and manual workflow runs deploy to GitHub Pages.
