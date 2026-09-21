# lit_review

An anchor-and-difference literature review, run by Claude Code. You read one paper and write notes. The assistant builds the search space in three directions, tiers the results against your notes, and diffs the closest papers against them, page by page.

The article that explains the method: https://ibrahimshaer.substack.com/p/a-twelve-dollar-literature-review.

| Folder | What it is |
|---|---|
| `literature_review_skill.md` | The five-step method as a Claude Code skill. Copy to `.claude/skills/literature-review/SKILL.md`. |
| `arxiv_mcp/` | The MCP server that gives the assistant arXiv. Install instructions in its README. |
| `pipeline/` | Runs the skill headlessly, one `claude -p` process per step and per diff, and sums the token and cost usage each process reports. |
| `example/` | One complete run on arXiv 2608.30041 (SkillGuard): notes, queries, search space, tiers, nine diffs, cost per step. |

The skill is the method: what each step does, what file it writes, what check it runs. The pipeline is the harness that runs the method for a known price. Each step and each diff gets a fresh process, so the assistant does not re-read the whole search space on every turn. That split is what the cost figures in the article measure: the same run in one process cost 28.8M tokens and $20.19; split, 6.1M and $12.05. You can run the skill interactively without the pipeline; you cannot reproduce the numbers without it.

Requires Python 3.10+, `pip install "mcp>=1.26" httpx pypdf`, and Claude Code.
