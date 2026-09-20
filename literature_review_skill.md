---
name: literature-review
description: Five-step literature review around anchor papers the user has read. Use when the user names anchor papers or a topic and asks for related work, a search sweep, tiering, or a diff of a paper against the anchors.
---

# Literature review

The user reads. You search, fetch, count, sort, and diff. Every step ends with one artifact and one check. Run the check yourself; if it fails, fix the artifact and rerun the check before the next step. The user does not confirm steps.

## Rules

1. **Do the step asked.** "Read" means read, not install, clone, or run. "Investigate" is not "write a report". "Search" is not "summarise".
2. **Source over analogy.** A number about a paper comes from that paper's text. Never fill a gap from a similar paper.
3. **Notes are selections, not summaries.** The user's notes record what they chose to keep. When cross-referencing, correct an error or a misfiling. Never add content the user left out.
4. **Abstracts only means abstracts only.** When a step is based on abstracts, say so at the top of the artifact, and every claim in it traces to an abstract.
5. **Say what was not verified.** Rate limits, unreadable PDFs, papers arXiv does not know: list them in a Caveats section of the artifact.
6. **Repositories only when named.** Answer questions about a method from the paper. Open a repository only when the user names it.
7. **Closed means closed.** When the user closes a decision, record it and stop raising it.

## Tools

The `arxiv` MCP server. Use nothing else for arXiv.

| Tool | Use it for |
|---|---|
| `search_papers(query, max_results, start, sort_by, category)` | Step 1 Option A survey query; Step 3 index-term sweep. Query syntax: `ti:`, `au:`, `abs:`, `cat:`, `all:`, with AND/OR/ANDNOT and quoted phrases. Returns counts and a compact id-and-title list; the full results with abstracts are written to the `results_file` it names. Build the Step 4 abstract dump from those files. |
| `list_categories()` | Category codes for `cat:` clauses. |
| `get_index_terms(arxiv_id)` | Step 3 index-term direction. Returns the paper's own keywords line if it has one, else the title's phrases and words, plus ready-made `queries`. Use the queries verbatim. |
| `extract_references(arxiv_id)` | Step 3 backward direction, inspection only. Splits the bibliography into entries, detects the reference style deterministically, and parses each entry into authors, title and year, with its arXiv id or DOI if it carries one. |
| `resolve_references(arxiv_id)` | Step 3 backward direction, the call that produces the list. Takes identifiers as given and looks up identifier-less entries by exact normalised title. Returns `resolved_ids` for `get_papers`, and `unresolved` with reasons. No judgement by the assistant: the server's answer is the answer. |
| `find_citations_in_text(candidate_ids, target_id, target_aliases)` | Step 3 forward direction. Full-text scan of candidates for the anchor's id or short name. Slow; one throttled download per candidate. |
| `get_papers(arxiv_ids)` | Metadata and full abstracts for a list, 100 per call. Step 3 lists and Step 4 abstracts. Report `missing` in Caveats. |
| `get_paper_text(arxiv_id, pages)` | Step 5 only. Writes the page-marked full text, with the reference list removed, to a file and returns its path. Read the pages you need from that file with `Read` and offsets; do not pull whole papers into the conversation. Every claim from the text cites its page. |
| `download_pdf(arxiv_id)` | Local copy when the user asks for one. |

## Step 1. Anchors

The user chooses the anchors. Two ways in:

- **Option A, topic.** The user names a topic and asks for the last N surveys. Write one `search_papers` query with `ti:survey OR ti:review OR abs:"we survey"` ANDed to the topic terms, sorted by `submittedDate` descending. Return the N results as a table: id, title, date, first sentence of the abstract. The user picks. Do not recommend.
- **Option B, papers.** The user names the papers. They are the anchors. Do not expand the set.

Artifact: none. The table or the confirmed list is the reply.
Check: the user names the anchors.

## Step 2. The user reads

The user reads the anchors in full and writes notes. You are not in this step. If asked to fetch text for the user to read, use `get_paper_text` and return it without commentary. If asked to cross-reference the notes against the paper, apply Rule 3.

Artifact: the user's notes, given as a file path or pasted into the prompt. If pasted, save them verbatim to `notes/anchor_notes.md`. If neither is given, ask once for them. You need the file in Steps 4 and 5.
Check: the notes exist as a file.

## Step 3. Search space

Three directions and no more. Every paper carries the direction it came from, and a paper may appear under more than one.

**Preferred form: one call.** `build_search_space(arxiv_id, out_dir, short_name)` performs all three directions below deterministically and writes the artifact, the abstract dump and the union file. Use it, report its totals, and stop. The direction-by-direction procedure that follows is what the tool does, kept here so the method is readable and so a direction can be rerun by hand if needed.

1. **Cited by the anchor.** `resolve_references` on each anchor, then `get_papers` on its `resolved_ids`. That is the whole procedure. Do not search for, accept, or reject any reference yourself: the server resolves identifiers as given and titles by exact normalised match, and anything else is unresolved. List the `unresolved` entries in the artifact with the server's reason for each, so the user can decide. No cap applies to this direction; the anchor's authors already curated it. Report in Caveats: `reference_style`, `entry_count`, how many carried an identifier, how many resolved by title, how many unresolved.
2. **Citing the anchor.** `search_papers` cannot do this; arXiv has no cited-by endpoint. If the anchor was posted less than three months ago, skip this direction, say so in the artifact, and leave the table empty; nothing will have cited it yet in a form the scan can find. Otherwise take the index-term sweep from direction 3, keep the papers posted after the anchor, and run `find_citations_in_text` over them with the anchor's id and short name. A result of zero is a result; record the number of candidates scanned. If the user gives Semantic Scholar or OpenAlex results, merge them and record which source found each paper.
3. **Index terms.** If `queries.json` exists in the working directory, load it and use those queries unchanged; that is how a rerun searches the same space as the run before it. Otherwise call `get_index_terms` on the anchor and use its `queries` list verbatim: one query per term, no rephrasing, no merging, no additions. The terms are the paper's own keywords line when it has one, and otherwise the title's phrases and words; the `source` field says which. Write the terms, their source, and the queries to `queries.json` before running them. Run each query with `search_papers`, 25 results, sorted by relevance, one query at a time. Keep every paper returned, with its full abstract, and record which queries returned it. Do not rank or cut anything in this step: which of these papers matter is a reading judgement, and it is made in Step 4 against the user's notes. If the user wants a term added or removed, they edit `queries.json`; the assistant does not.

Artifact: `<anchor>_search_space.md` with a Method section (the queries verbatim, the date, and a Totals table: the number returned per direction and the union of unique papers across the three directions, which is the set going into Step 4), one table per direction (id as a link, title, authors, date, first sentence of the abstract, and for direction 3 the query count), and a Caveats section (`extract_references` counts, `find_citations_in_text` unreadable PDFs, `get_papers` missing ids, rate limits).

Checks:
- The three tables contain every id returned by the tools, minus the cuts stated in Method.
- Direction 1: the number of rows plus the number of unresolved entries equals `entry_count` from `resolve_references`, allowing for duplicate ids. If not, say which entries are unaccounted for.
- Every direction-2 row names the source that found it, or the direction is marked skipped with the reason.

## Step 4. Tiers

Build one scratch file with the full abstract of every paper in Step 3: the sweep abstracts come from the `results_file` of each query, the cited and citing abstracts from `get_papers`. Read the whole file and the user's notes before sorting anything. Do not tier from titles or first sentences.

**Selection from the index-term sweep.** This is where the cap applies, and it is a judgement made by reading, not a score. From the papers the sweep returned, keep the ones whose title and abstract bear on the user's notes, up to the cap the user set. The cited and citing papers are kept in full and are not subject to the cap. List the sweep papers you cut in the tiers file as a table of id and title, one line each, so the user can see what was left out. Then tier what is kept.

Sort into tiers by function relative to the notes: what the paper is, and what it would do for the work the notes describe. Function decides the tier, not importance. Two rules resolve every overlap:

- Tiers 1 and 2 hold methods. Tiers 3 to 5 hold everything that is not a method. A benchmark the work would be evaluated on is Tier 3 even when it is the most important paper in the set.
- Among methods, Tier 1 is the ones that attempt the same task as the notes, so the work would be compared to them as rivals or predecessors. Tier 2 is the ones that solve a different task with a component the work could take.

Default tiers, which the user may replace:

| Tier | Contents |
|---|---|
| 1 | Rival or predecessor methods: papers that attempt what the notes describe |
| 2 | Methods for another task with a component the work could absorb |
| 3 | Benchmarks, test beds, datasets, empirical studies the work could be evaluated on or against |
| 4 | Background: surveys, analyses, position papers |
| 5 | General frameworks and context |

Artifact: `<anchor>_tiers.md`. First line: "Based on abstracts only." Then one table per tier: id as a link, title, one line on why it sits there, and which note it is closest to. End with where the space is crowded and where it is thin.

Checks, run as a script and not by eye:
- Every paper from Step 3 appears in exactly one tier table or in the cut table, and nowhere else.
- The number of sweep papers kept is at most the cap.
- The count in each tier heading equals the rows under it.
- The abstract file has one abstract per paper in Step 3.

Report the tier sizes and the thin areas. Step 5 then runs on every Tier 1 paper against the notes, unless the user has named other papers or another target.

## Step 5. Diffs

For each Tier 1 paper, call `get_paper_text` to write its full text to disk, read that file section by section with `Read`, and diff it against the target: the user's notes by default, or the anchor's full text if the user asked for that. Output only what differs, under five headings:

- **Skip.** Sections the target already covers, each naming the covering section or note.
- **Read.** Sections that are new, each with the page and one sentence on what is new there.
- **Numbers.** Every quantity the paper reports that bears on the target, with its page.
- **Disagreements.** Where the paper and the target contradict each other, both sides quoted with pages.
- **Reading order.** Which sections to read first, given the target.

Artifact: `diffs/<paper_id>.md`, one per paper.

Checks:
- All five headings present, with content or the word "none".
- Every claim carries a page number. If a figure or table was garbled by extraction, say so instead of guessing.

Then stop. Do not extend the sweep, do not propose next steps, do not start on Tier 2.
