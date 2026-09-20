Use the /literature-review skill. If it is not loaded, read .claude/skills/literature-review/SKILL.md first.

Steps 1 to 4 are done. Anchor: arXiv {ANCHOR} ({SHORT}). The user's notes are in {NOTES}. This process handles exactly one Tier 1 paper: arXiv {PAPER}. The diff target is the user's notes.

Run Step 5 for {PAPER} only.

- Call get_paper_text("{PAPER}"). It writes the page-marked text, references removed, to a file and returns the path. Read that file with Read, in sections, until you have covered every page. Do not call any other arXiv tool.
- Write diffs/{PAPER}.md with the five headings: Skip, Read, Numbers, Disagreements, Reading order. Each heading has content or the word "none". Every claim carries a page number. Name garbled figures or tables instead of reading from them. Record in-paper inconsistencies rather than resolving them.

Reply with the file path, the page count, and any pages you could not read. Then stop.
