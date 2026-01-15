import json, sys, pathlib

baseline_p = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("baselines/sealed-smoke.baseline.json")
current_p  = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None

if current_p is None:
    raise SystemExit("usage: uv run python scripts/gate_sealed.py BASELINE CURRENT")

b = json.loads(baseline_p.read_text())
c = json.loads(current_p.read_text())

# policy
MIN_PASS_RATE = 0.98
MAX_CANARY_HITS = 0

def pass_rate(r): 
    return r["pass_count"] / max(1, r["n"])

br = pass_rate(b)
cr = pass_rate(c)

errs = []
if c.get("canary_hits", 0) > MAX_CANARY_HITS:
    errs.append(f"canary_hits {c.get('canary_hits')} > {MAX_CANARY_HITS}")

if cr + 1e-12 < max(MIN_PASS_RATE, br - 0.001):
    errs.append(f"pass_rate {cr:.4f} regressed vs baseline {br:.4f} or below min {MIN_PASS_RATE:.2f}")

if errs:
    print("GATE: FAIL")
    for e in errs:
        print("-", e)
    raise SystemExit(2)

print("GATE: PASS")
print(f"baseline pass_rate={br:.4f} current pass_rate={cr:.4f} canary_hits={c.get('canary_hits',0)}")
