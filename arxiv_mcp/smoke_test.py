import asyncio, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ARXIV_MCP_CACHE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache"))
import server as s

async def main():
    r = await s.search_papers("ti:\"attention is all you need\"", max_results=3)
    print("search total", r["total_results"], "returned", r["returned"])
    print(" first:", r["papers"][0]["id"], "|", r["papers"][0]["title"][:60])

    p = await s.get_paper("arXiv:1706.03762")
    print("get_paper", p["id"], "|", len(p["abstract"]), "chars abstract")

    b = await s.get_papers(["1706.03762", "https://arxiv.org/abs/1810.04805v2", "9999.99999", "not-an-id"])
    print("get_papers found", b["found"], "missing", b["missing"], "invalid", b["invalid"])

    t = await s.get_paper_text("1706.03762", pages="1-2", max_chars=3000)
    print("text pages", t["page_count"], t["pages_returned"], "truncated", t["truncated"])
    print(" head:", t["text"][:120].replace("\n", " "))

    refs = await s.extract_references("1706.03762")
    print("refs arxiv", refs["arxiv_count"], "strict", refs["strict_count"], "dois", len(refs["dois"]),
          "recovered", refs["recovered_by_tolerant_pattern"])

    c = await s.find_citations_in_text(["1810.04805", "1706.03762"], "1706.03762", ["Transformer"])
    print("citations", json.dumps({k: c[k] for k in ("scanned","citing","not_citing","failed")}))

asyncio.run(main())
