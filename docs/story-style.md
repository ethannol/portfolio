# Writing a study as a story

Each study page opens with a story: a first-person walk through the investigation, in the
manner of a well-written analysis post, where the reader follows the author's thinking from
the first question to the conclusion. The structured material (aim, hypothesis, conclusion,
quantities, pitfalls, limitations, documents) follows the story under "At a glance".

## Who it is for

A technically literate reader who is not a specialist in this field: a hiring manager or a
senior engineer at a company that runs mines and plants on data. Not dumbed down. Nothing
that a careful colleague would call clever or salesy.

## Voice

- First person singular. Past tense for what I did ("I pulled the snapshot", "I fitted"),
  present tense for what the data show ("the pooled median falls").
- Plain English. Short paragraphs, three to five sentences. One idea per paragraph.
- No exclamation marks, no jokes, no rhetorical questions stacked for effect, no "let's",
  no "worth noting", no colon-then-reveal sentences, no em-dashes.
- Technical terms are fine when they are the right word. Use the glossary's wording
  (`portfolio/glossary.json`) so the site stays consistent, and give a half-sentence of
  plain meaning the first time a term appears.

## Structure

The story is a chain. Every section does four things in order:

1. What I wanted to know at that point, and why it mattered.
2. What I did about it, in plain terms. Name the method; say in a clause what it does.
3. What came back: a figure, or a number from the ledger, placed right there.
4. What that changed. Either it answered the question, or it raised the next one. Say which.

The next section starts from that. The reader should never meet a method before meeting
the question it answers.

Open with the question in the first paragraph, and with why I cared about it. No heading
before the opening. Then plain headings that name the step ("Finding out what one row means",
"The pooled comparison and why I did not trust it", "Choosing the block size before fitting").
Not clever headings.

Close with three short parts: what I concluded, in two or three sentences; what I would not
claim from this; and what I would do next with another week.

Length: 1,800 to 2,800 words.

## Model sentences, in the register wanted

- "Before I computed anything I wrote down what would count as a decline, because I knew the
  choice of comparison would otherwise drift toward whatever looked interesting."
- "The pooled medians moved in opposite directions for the two constituents. That was the
  first sign that the pooled comparison was answering a different question from the one I
  had asked."
- "That raised a question I had not planned for: were the two laboratories measuring the
  same thing?"
- "Holding out one laboratory at a time is a harsher test than random folds, and it is the
  right one here, because the question is whether the model learned chemistry or learned
  which lab did the assay."
- "I had decided the block size in advance from the autocorrelation range, so the drop in
  AUC at 100 km is the pre-registered result, not the most dramatic one I could find."
- "This part is exploratory. I decided to do it after seeing the primary result, and I
  report it as such."

## Honesty rules

- Say which decisions were made before seeing data and which after. The pre-registration
  (`docs/prereg.md`) and the decisions log (`docs/decisions.md`) are the record; read them
  first and follow them. Anything the log marks post-freeze is "exploratory" in the story.
- Where the study was built from a brief that anticipated something (for example, that the
  treatment plant would confound the spill), write "I expected", not "I discovered".
- Do not invent any number, date, event, source or figure. Every number in the story is a
  `{{ledger.key:fmt}}` placeholder resolved from the project's ledger at build time
  (`artifacts/numbers.json`, or the JSON file named in the card's `ledger`). If the number
  you want is not in the ledger, describe the result in words instead.
- Literal digits are allowed only for fixed constants already declared in the card's
  `numeric_constants` (years that define periods, thresholds chosen in advance). Add a new
  constant only if it is genuinely fixed in advance; never for a result. The check script
  reports anything undeclared.
- Figures: embed with `![caption](reports/figures/<file>.png)` using a file that exists, and
  discuss what the figure shows in the paragraph right after it. Captions are plain
  descriptions.
- The projects were built in Claude Code sessions from the author's briefs; the story is the
  author's account of the investigation and its reasoning, not a narration of agent
  keystrokes. Do not mention the agent or the tooling unless the step genuinely depended on
  it (for example, the pre-registration freeze).

## Mechanics

- Write `docs/story.md` in the project directory. Markdown. Placeholders as above.
- Add `"story": "docs/story.md"` to the project's `portfolio.json`. Do not change any other
  field except `numeric_constants` when a genuine constant is needed.
- Check with `uv run python scripts/check_card.py <project dir>` from the `portfolio`
  directory. It resolves every placeholder, confirms every figure exists, and lists undeclared
  literal numbers. It must pass.
- Commit `docs/story.md` and `portfolio.json` in the project repository with a message ending
  in the project's usual Co-Authored-By line. Do not push.
