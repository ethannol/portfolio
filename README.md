# portfolio

A static console over the side-projects portfolio. It reads each project's `portfolio.json`
card and resolves every number on the site from that project's own results ledger at build
time: a cairn `artifacts/numbers.json`, a nested `reports/results.json`, or an aggregate over
run files. The cards hold ledger keys, never values, so the console cannot drift from the
projects.

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
  "verification": {"frozen": ".cairn/frozen.json", "tests": "<key or source>", "harness": "cairn", "verify": "pass"},
  "data": ["..."], "stack": ["..."], "links": {"Repository": "..."}
}
```

Custom value sources: `glob_json` (sum, count or count_true of a path over files), `count_files`,
`regex_count`, `csv` (first, sum or count of a column with an optional filter), `json_file`.
