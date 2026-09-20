"""Sum usage and cost per step from the JSON outputs of a pipeline run."""
import glob, json, os, sys

exp = sys.argv[1]
rows = []
tot = {"in": 0, "cw": 0, "cr": 0, "out": 0, "cost": 0.0, "turns": 0, "secs": 0}
for f in sorted(glob.glob(os.path.join(exp, "runs", "*.json"))):
    name = os.path.basename(f)[:-5]
    try:
        o = json.load(open(f, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        rows.append((name, None, str(e)[:60])); continue
    u = o.get("usage", {}) or {}
    r = {"in": u.get("input_tokens", 0) or 0, "cw": u.get("cache_creation_input_tokens", 0) or 0,
         "cr": u.get("cache_read_input_tokens", 0) or 0, "out": u.get("output_tokens", 0) or 0,
         "cost": o.get("total_cost_usd", 0) or 0, "turns": o.get("num_turns", 0) or 0,
         "secs": (o.get("duration_ms", 0) or 0) // 1000, "err": o.get("is_error", False)}
    for k in tot: tot[k] += r[k]
    rows.append((name, r, ""))

def m(n): return f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:.0f}k"
print(f"# Usage per step: {os.path.basename(exp)}\n")
print("| step | turns | fresh input | cache writes | cache reads | output | total | cost USD | seconds | error |")
print("|---|---|---|---|---|---|---|---|---|---|")
for name, r, err in rows:
    if r is None:
        print(f"| {name} | | | | | | | | | {err} |"); continue
    total = r["in"] + r["cw"] + r["cr"] + r["out"]
    print(f"| {name} | {r['turns']} | {m(r['in'])} | {m(r['cw'])} | {m(r['cr'])} | {m(r['out'])} | {m(total)} | {r['cost']:.2f} | {r['secs']} | {r['err']} |")
total = tot["in"] + tot["cw"] + tot["cr"] + tot["out"]
print(f"| **all** | {tot['turns']} | {m(tot['in'])} | {m(tot['cw'])} | {m(tot['cr'])} | {m(tot['out'])} | **{m(total)}** | **{tot['cost']:.2f}** | {tot['secs']} | |")
