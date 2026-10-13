"""Check one project's card and story without rendering the site.

Usage: uv run python scripts/check_card.py ../groundwater-audit
Reports unresolved placeholders, missing figures and undeclared literal numbers.
"""

import json
import sys
from pathlib import Path

from portfolio.build import ROOT, literal_result_numbers, load_project


def main() -> int:
    pdir = Path(sys.argv[1]).resolve()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    card = json.loads((pdir / "portfolio.json").read_text())
    if card.get("story"):
        card["_story_text"] = (pdir / card["story"]).read_text()
    literals = literal_result_numbers(card, enforce=False)
    project = load_project({"path": str(pdir)}, manifest)
    n = len(project["numbers_used"]) + len(project["headline"])
    nfig = len(project["story_figures"])
    print(f"{project['slug']}: {n} ledger values resolved, {nfig} story figures")
    if literals:
        print("UNDECLARED LITERAL NUMBERS")
        print("(declare in numeric_constants only if fixed constants such as dates, never results)")
        for lit in literals:
            print(f"  {lit['field']}: {lit['number']}")
        return 1
    print("no undeclared literals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
