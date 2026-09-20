Use the /literature-review skill. If it is not loaded, read .claude/skills/literature-review/SKILL.md first.

Steps 1 and 2 are done. Anchor (Option B): arXiv {ANCHOR}, short name {SHORT}. A local copy of the PDF is in anchor/. The user's notes are in {NOTES}.

Run Step 3 only, and do it with one tool call: build_search_space(arxiv_id="{ANCHOR}", out_dir="{EXP}", short_name="{SHORT}"). It resolves the references, builds or loads queries.json, runs the sweep, runs or skips the citation scan by the age rule, and writes {ANCHOR}_search_space.md, scratch/abstracts.md and scratch/union.json. Do not run any other arXiv tool, do not write scripts, do not rank or cut anything.

Then reply with the tool's totals, reference counts, forward status and per-query table, verbatim, and stop.

If build_search_space fails with a rate-limit or 429 error, do not end your turn: run `sleep 240` with Bash, then call build_search_space again with the same arguments. Repeat up to three times. Only give up after the third failure, and then say so plainly.
