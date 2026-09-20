Use the /literature-review skill. If it is not loaded, read .claude/skills/literature-review/SKILL.md first.

Steps 1 to 3 are done. Anchor: arXiv {ANCHOR} ({SHORT}). The user's notes are in {NOTES}. The Step 3 artifact is {ANCHOR}_search_space.md; the user has accepted the search space as it stands. The abstracts of every paper in it are in scratch/abstracts.md and the id list with directions is in scratch/union.json.

Run Step 4 only.

- Read scratch/abstracts.md in full and the notes before sorting anything. Do not call any arXiv tool; everything you need is on disk.
- Selection from the sweep (direction 3 papers) is your reading judgement: keep at most 25 whose title and abstract bear on the notes. Cited (D1) and citing (D2) papers are all kept.
- Default tier table. Tier all kept papers by proximity to the notes, one line each on why, naming the closest note.
- Artifact: {ANCHOR}_tiers.md, first line "Based on abstracts only.", with the tier tables and a final table of every sweep paper cut (id and title).
- Write scratch/check_tiers.py and run it: every id in union.json appears exactly once across the tier tables and the cut table; sweep papers kept is at most 25; heading counts equal rows. Paste its output in your reply.

Reply with the tier sizes, the kept and cut counts, the check output, and the Tier 1 ids. Then stop. Do not start Step 5.
