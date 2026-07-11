#!/usr/bin/env python3
"""Stage 5 — unblind, apply the pre-registered criteria, write RESULTS.md.

Also: --sample prints 5 seeded packets for the human blind review (mapping
withheld) — do this BEFORE reading RESULTS.md.

Usage: python3 05_report.py --run run1 [--sample]
"""
import argparse
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_lib as bl

ARM_LABEL = {"A": "Nexus", "B": "Plain Claude Code", "C": "Raw GLM-5.2"}


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(st.mean(xs), 3) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run1")
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()
    rd = bl.run_dir(args.run)
    mapping = json.loads((rd / "private" / "mapping.json").read_text())
    cases = sorted(mapping.keys())

    if args.sample:
        rng = random.Random(bl.CFG["shuffle_seed"] + 1)
        picks = rng.sample(cases, min(5, len(cases)))
        print("HUMAN BLIND REVIEW — read each packet, note your ranking "
              "(1/2/3) per case BEFORE opening RESULTS.md or mapping.json:")
        for c in picks:
            print(f"  {rd / 'packets' / c}")
        return

    briefs = {b["case_id"]: b for b in bl.load_briefs(args.run)}
    th = bl.CFG["thresholds"]

    # metas (cost/time) per case×arm
    metas = defaultdict(dict)
    for c in cases:
        for arm in bl.ARMS:
            m = bl.done_marker(args.run, arm, c)
            if m.exists():
                metas[c][arm] = json.loads(m.read_text())

    # absolute scores → per case×arm×judge
    absd = defaultdict(dict)   # (case, arm) -> {judge: parsed}
    for f in (rd / "scores" / "absolute").glob("*.json"):
        p = json.loads(f.read_text())
        case, n, judge = p.get("_case"), p.get("_n"), p.get("_judge")
        if not case or case not in mapping or p.get("error"):
            continue
        arm = mapping[case].get(str(n))
        if arm:
            absd[(case, arm)][judge] = p

    def pooled_dim_mean(case, arm):
        vals = [bl.dims_mean(p) for p in absd.get((case, arm), {}).values()]
        return mean(vals)

    def grounding_flags(case, arm):
        contra = unsup = 0
        for p in absd.get((case, arm), {}).values():
            g = p.get("grounding") or {}
            contra += sum(1 for c in (g.get("checked_claims") or [])
                          if c.get("verdict") == "contradicted")
            u = g.get("unsupported_load_bearing")
            unsup += int(u) if isinstance(u, (int, float)) else 0
        return contra, unsup

    def gates_failed(case, arm):
        per_judge = []
        for p in absd.get((case, arm), {}).values():
            gs = p.get("gates") or []
            per_judge.append(sum(1 for g in gs if g.get("pass") is False))
        return mean(per_judge)

    # pairwise → consistent winners
    pair_raw = defaultdict(dict)   # (case, "AvB") -> {"fwd": arm|"tie", "rev": ...}
    for f in (rd / "scores" / "pairwise").glob("*.json"):
        p = json.loads(f.read_text())
        job = p.get("_job") or {}
        jid = job.get("job_id", "")
        if p.get("error") or "::" not in jid:
            continue
        case, pair, order = jid.split("::")
        one_n = job["one"].split("_")[-1].split(".")[0]
        two_n = job["two"].split("_")[-1].split(".")[0]
        num2arm = mapping.get(case, {})
        w = (p.get("winner") or "").upper()
        winner = ("tie" if w == "TIE"
                  else num2arm.get(one_n) if w == "ONE"
                  else num2arm.get(two_n) if w == "TWO" else None)
        if winner:
            pair_raw[(case, pair)][order] = {"winner": winner,
                                             "margin": p.get("margin")}

    def win_rate(pair_key, champ):
        """champ's consistent-win rate over cases with both orders judged."""
        wins = ties = n = 0
        for (case, pk), orders in pair_raw.items():
            if pk != pair_key or "fwd" not in orders or "rev" not in orders:
                continue
            n += 1
            a, b = orders["fwd"]["winner"], orders["rev"]["winner"]
            if a == b == champ:
                wins += 1
            elif a != b or a == "tie":
                ties += 1
        return ((wins + 0.5 * ties) / n if n else None), wins, ties, n

    # per-dimension story (pooled judges), keyed by dim name per domain
    dim_by_arm = defaultdict(lambda: defaultdict(list))
    for (case, arm), judges in absd.items():
        for p in judges.values():
            for d in (p.get("dims") or []):
                if isinstance(d.get("score"), (int, float)):
                    dim_by_arm[arm][d.get("name", "?")[:60]].append(d["score"])

    # aggregates
    agg = {}
    for arm in bl.ARMS:
        dmeans = [pooled_dim_mean(c, arm) for c in cases]
        costs = [(metas[c].get(arm) or {}).get("cost_usd_list") for c in cases]
        secs = [(metas[c].get(arm) or {}).get("seconds") for c in cases]
        gf = [gates_failed(c, arm) for c in cases]
        contra = sum(grounding_flags(c, arm)[0] for c in cases)
        unsup = sum(grounding_flags(c, arm)[1] for c in cases)
        agg[arm] = {"dim_mean": mean(dmeans), "cost": mean(costs),
                    "seconds": mean(secs), "gates_failed": mean(gf),
                    "contradicted": contra, "unsupported": unsup}

    ab_rate, ab_w, ab_t, ab_n = win_rate("AvB", "A")
    ac_rate, ac_w, ac_t, ac_n = win_rate("AvC", "A")
    b_rate, b_w, b_t, b_n = win_rate("AvB", "B")

    # pre-registered verdicts
    iso_quality = (agg["A"]["dim_mean"] is not None
                   and agg["B"]["dim_mean"] is not None
                   and abs(agg["A"]["dim_mean"] - agg["B"]["dim_mean"])
                   <= th["iso_quality_dim_delta"]
                   and agg["A"]["cost"] and agg["B"]["cost"]
                   and agg["A"]["cost"] <= th["iso_quality_cost_ratio"] * agg["B"]["cost"])
    added_vs_claude = ((ab_rate is not None and ab_rate >= th["a_vs_b_win_rate_yes"])
                       or iso_quality)
    harness_value = ac_rate is not None and ac_rate >= th["a_vs_c_win_rate_yes"]
    falsified = b_rate is not None and b_rate > th["falsified_b_win_rate"]

    excluded = json.loads((rd / "private" / "excluded.json").read_text()) \
        if (rd / "private" / "excluded.json").exists() else []
    void = len(excluded) > th["max_excluded_briefs"]
    arm_a_mode = next((m.get("mode") for c in cases
                       for m in [metas[c].get("A", {})] if m.get("mode")), "?")

    L = []
    L.append("# RESULTS — Does Nexus add value?")
    L.append(f"Run `{args.run}` · {len(cases)} judged briefs · Arm A mode: "
             f"`{arm_a_mode}` · excluded: {len(excluded)}"
             + (" · **RUN VOID (too many exclusions)**" if void else ""))
    L.append("")
    L.append("## Verdicts (pre-registered thresholds — PREREGISTRATION.md)")
    L.append(f"- **Added value vs plain Claude Code: "
             f"{'YES' if added_vs_claude else 'NO'}** — A-vs-B win rate "
             f"{ab_rate if ab_rate is not None else 'n/a'} "
             f"({ab_w} wins / {ab_t} ties / n={ab_n}); iso-quality-cheaper: "
             f"{'yes' if iso_quality else 'no'}")
    L.append(f"- **Harness adds value over raw GLM-5.2: "
             f"{'YES' if harness_value else 'NO'}** — A-vs-C win rate "
             f"{ac_rate if ac_rate is not None else 'n/a'} "
             f"({ac_w} wins / {ac_t} ties / n={ac_n}; threshold "
             f"{th['a_vs_c_win_rate_yes']})")
    L.append(f"- **Falsified (B beats A > {th['falsified_b_win_rate']}): "
             f"{'YES — pipeline subtracts value' if falsified else 'no'}** "
             f"(B rate {b_rate if b_rate is not None else 'n/a'})")
    L.append("")
    L.append("## Per-arm aggregates (pooled over both judge families)")
    L.append("| Arm | Dim mean (0-4) | Gates failed/case | List cost/case | "
             "Seconds/case | Contradicted claims | Unsupported load-bearing |")
    L.append("|---|---|---|---|---|---|---|")
    for arm in bl.ARMS:
        a = agg[arm]
        L.append(f"| {ARM_LABEL[arm]} | {a['dim_mean']} | {a['gates_failed']} "
                 f"| ${a['cost']} | {a['seconds']} | {a['contradicted']} "
                 f"| {a['unsupported']} |")
    if agg["A"]["cost"] and agg["A"]["dim_mean"] and agg["B"]["cost"] \
            and agg["B"]["dim_mean"]:
        L.append("")
        L.append(f"Cost per rubric point: A ${round(agg['A']['cost']/agg['A']['dim_mean'], 3)}"
                 f" vs B ${round(agg['B']['cost']/agg['B']['dim_mean'], 3)}"
                 + (f" vs C ${round(agg['C']['cost']/agg['C']['dim_mean'], 3)}"
                    if agg["C"]["cost"] and agg["C"]["dim_mean"] else "")
                 + "  *(B's marginal cost on subscription is $0 — this is the "
                   "list-price equivalence; both views are valid, say which "
                   "you're arguing.)*")

    L.append("")
    L.append("## WHAT improves — top dimension deltas (A − B and A − C)")
    common = set(dim_by_arm["A"]) & set(dim_by_arm["B"])
    deltas = sorted(((mean(dim_by_arm['A'][d]) or 0) - (mean(dim_by_arm['B'][d]) or 0), d)
                    for d in common)
    for delta, d in (deltas[-3:][::-1] + deltas[:3]):
        ac = (mean(dim_by_arm['A'].get(d, [])) or 0) - \
             (mean(dim_by_arm['C'].get(d, [])) or 0)
        L.append(f"- `{d}`: A−B {round(delta, 2):+} · A−C {round(ac, 2):+}")
    L.append("")
    L.append("## Judge-family agreement")
    agree = tot = 0
    for c in cases:
        cl = {}
        gl = {}
        for arm in ("A", "B"):
            js = absd.get((c, arm), {})
            if "claude" in js:
                cl[arm] = bl.dims_mean(js["claude"])
            if "glm" in js:
                gl[arm] = bl.dims_mean(js["glm"])
        if len(cl) == 2 and len(gl) == 2 and None not in (*cl.values(), *gl.values()):
            tot += 1
            if (cl["A"] - cl["B"]) * (gl["A"] - gl["B"]) >= 0:
                agree += 1
    L.append(f"- Same A-vs-B direction on {agree}/{tot} briefs "
             f"({round(100*agree/tot) if tot else 'n/a'}%). Low agreement = "
             "treat absolute scores with suspicion; lean on pairwise + the "
             "human sample.")
    if excluded:
        L.append("")
        L.append("## Excluded briefs")
        for e in excluded:
            L.append(f"- {e['case_id']}: {e['reason']}")
    L.append("")
    L.append("## Caveats (from PREREGISTRATION.md)")
    L.append("- n=1 per brief/arm; business-deliverable corpus only; judge "
             "families overlap generator families; Arm B has no business "
             "brain by design; grounding = internal consistency, not web "
             "verification. Run `05_report.py --sample` human review before "
             "trusting close calls.")
    out = rd / "RESULTS.md"
    out.write_text("\n".join(L) + "\n")
    (rd / "summary.json").write_text(json.dumps({
        "arm_a_mode": arm_a_mode, "agg": agg,
        "ab": {"rate": ab_rate, "wins": ab_w, "ties": ab_t, "n": ab_n},
        "ac": {"rate": ac_rate, "wins": ac_w, "ties": ac_t, "n": ac_n},
        "b_rate": b_rate, "added_vs_claude": added_vs_claude,
        "harness_value": harness_value, "falsified": falsified,
        "void": void, "excluded": len(excluded)}, indent=2))
    bl.log(f"wrote {out}")
    print("\n".join(L[:14]))


if __name__ == "__main__":
    main()
