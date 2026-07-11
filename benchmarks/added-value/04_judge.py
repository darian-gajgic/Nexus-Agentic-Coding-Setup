#!/usr/bin/env python3
"""Stage 4 — blind judging. Reads ONLY packets/ (never private/mapping.json).

Absolute: every packet deliverable × two judge families (Claude CLI + GLM API),
sentinel-fenced JSON (gates, dims 0-4, kill hits, grounding check, verdict).
Pairwise: Claude judge, jobs prepared by 03 (both presentation orders); the
prompt sees only two file paths labeled ONE/TWO — no arm names, no job ids.

Resumable per score file. Usage:
  python3 04_judge.py --run run1 [--only absolute|pairwise] [--pause 3]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_lib as bl

STYLE = Path(bl.CFG["knowledge_dir"]) / "STYLE-VOICE.md"

ABS_CONTRACT = f"""
Score the deliverable against the rubric. Stance: refute by default — the
deliverable's own assertions are not evidence.

Then END your reply with exactly one JSON object between these sentinel lines
(nothing after the closing sentinel):
{bl.SENT_BEGIN}
{{"gates": [{{"id": "G1", "pass": true, "reason": "<=120 chars"}}],
 "dims": [{{"name": "D1 <label from rubric>", "score": 0, "why": "<=120 chars"}}],
 "kill_hits": ["verbatim phrase"],
 "grounding": {{"checked_claims": [{{"claim": "<=160 chars",
   "verdict": "consistent|contradicted|unverifiable"}}],
   "unsupported_load_bearing": 0}},
 "verdict": "SHIP|REVISE|REWRITE"}}
{bl.SENT_END}

Rules: cover EVERY must-pass gate and EVERY scored dimension the rubric
defines, using the rubric's own ids/labels. For "grounding": pick the 2 most
load-bearing factual claims in the deliverable and judge each strictly from
internal consistency with the brief-facts stated inside the deliverable and
the rubric's honesty rules (no external lookups; browsing is not available);
count how many load-bearing claims rest on nothing shown. Keep every string
short — the JSON is parsed by a machine.
"""

RETRY_NUDGE = ("\n\nREMINDER: your previous reply could not be parsed. Output "
               "ONLY the sentinel-fenced JSON object this time.")


def claude_abs_prompt(deliv: Path, rubric: str) -> str:
    return (f"You are a blind quality judge. Read ONLY these three files and "
            f"nothing else:\n1. Deliverable: {deliv}\n2. Rubric: {rubric}\n"
            f"3. Style guide: {STYLE}\n"
            f"You do not know which system produced the deliverable — judge "
            f"the page, not the author. Do not modify any files."
            + ABS_CONTRACT)


def glm_abs_prompt(deliv_text: str, rubric_text: str, style_text: str) -> str:
    return ("You are a blind quality judge. You do not know which system "
            "produced the deliverable — judge the page, not the author.\n\n"
            "=== RUBRIC ===\n" + rubric_text[:24000] +
            "\n\n=== STYLE GUIDE (voice rules) ===\n" + style_text[:6000] +
            "\n\n=== DELIVERABLE ===\n" + deliv_text[:30000] +
            "\n\n=== END DELIVERABLE ===\n" + ABS_CONTRACT)


def pair_prompt(one: Path, two: Path, rubric: str) -> str:
    return (f"You are a blind quality judge comparing two deliverables written "
            f"for the SAME brief. Read ONLY these three files:\n"
            f"Deliverable ONE: {one}\nDeliverable TWO: {two}\nRubric: {rubric}\n"
            f"You do not know which systems produced them. Decide which better "
            f"satisfies the rubric (gates first, then dimensions, then voice). "
            f"END with exactly one JSON object between the sentinels:\n"
            f"{bl.SENT_BEGIN}\n"
            f'{{"winner": "ONE|TWO|TIE", "margin": 1, '
            f'"why": "<=200 chars"}}\n'
            f"{bl.SENT_END}\n"
            f"margin: 1 = slight, 2 = clear, 3 = decisive. TIE only if truly "
            f"inseparable. Do not modify any files.")


def call_claude_judge(prompt: str, cwd: Path, home: Path):
    ok, res = bl.run_claude(prompt, cwd, bl.CFG["judge_timeout_s"],
                            model=bl.CFG["judge_claude_model"], config_dir=home)
    if not ok:
        return None, str(res)
    parsed = bl.extract_sentinel_json(res.get("result") or "")
    if parsed is None:
        ok, res = bl.run_claude(prompt + RETRY_NUDGE, cwd,
                                bl.CFG["judge_timeout_s"],
                                model=bl.CFG["judge_claude_model"],
                                config_dir=home)
        parsed = bl.extract_sentinel_json((res or {}).get("result") or "") \
            if ok else None
    if parsed is None:
        return None, "unparseable judge output"
    parsed["_judge_cost_usd"] = (res or {}).get("total_cost_usd")
    return parsed, None


def call_glm_judge(prompt: str, key: str):
    ok, res = bl.zai_chat([{"role": "user", "content": prompt}],
                          bl.CFG["judge_glm_model"], 3000,
                          bl.CFG["judge_timeout_s"], key)
    if not ok:
        return None, str(res)
    parsed = bl.extract_sentinel_json(res.get("content") or "")
    if parsed is None:
        ok, res = bl.zai_chat([{"role": "user", "content": prompt + RETRY_NUDGE}],
                              bl.CFG["judge_glm_model"], 3000,
                              bl.CFG["judge_timeout_s"], key)
        parsed = bl.extract_sentinel_json((res or {}).get("content") or "") \
            if ok else None
    return (parsed, None) if parsed is not None else (None, "unparseable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="run1")
    ap.add_argument("--only", choices=["absolute", "pairwise"])
    ap.add_argument("--pause", type=int, default=3)
    args = ap.parse_args()
    rd = bl.run_dir(args.run)
    packets = rd / "packets"
    if not packets.is_dir():
        sys.exit("no packets/ — run 03_blind.py first")
    sdir = rd / "scores"
    (sdir / "absolute").mkdir(parents=True, exist_ok=True)
    (sdir / "pairwise").mkdir(parents=True, exist_ok=True)
    home = bl.ensure_clean_claude_home()
    key = bl.read_glm_key()
    style_text = STYLE.read_text() if STYLE.exists() else ""

    if args.only in (None, "absolute"):
        for pdir in sorted(packets.iterdir()):
            if not pdir.is_dir():
                continue
            case = json.loads((pdir / "case.json").read_text())
            rubric_path = case["rubric_path"]
            rubric_text = Path(rubric_path).read_text()
            for dfile in sorted(pdir.glob("deliverable_*.md")):
                n = dfile.stem.split("_")[-1]
                for judge in ("claude", "glm"):
                    out = sdir / "absolute" / f"{case['case_id']}__{n}__{judge}.json"
                    if out.exists():
                        continue
                    bl.log(f"abs {case['case_id']} #{n} [{judge}]")
                    if judge == "claude":
                        parsed, err = call_claude_judge(
                            claude_abs_prompt(dfile.resolve(), rubric_path),
                            rd, home)
                        if err and "session limit" in err.lower():
                            bl.log("Claude session limit — stop; resume later.")
                            return
                    else:
                        parsed, err = call_glm_judge(
                            glm_abs_prompt(dfile.read_text(), rubric_text,
                                           style_text), key)
                    payload = parsed if parsed else {"error": err}
                    payload["_case"] = case["case_id"]
                    payload["_n"] = n
                    payload["_judge"] = judge
                    out.write_text(json.dumps(payload, indent=2))
                    time.sleep(args.pause)

    if args.only in (None, "pairwise"):
        jobs_f = rd / "private" / "pairwise-jobs.json"
        if not jobs_f.exists():
            sys.exit("no pairwise jobs — run 03_blind.py")
        for job in json.loads(jobs_f.read_text()):
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", job["job_id"])
            out = sdir / "pairwise" / f"{safe}.json"
            if out.exists():
                continue
            pdir = packets / job["case_id"]
            case = json.loads((pdir / "case.json").read_text())
            bl.log(f"pair {job['job_id']}")
            parsed, err = call_claude_judge(
                pair_prompt((pdir / job["one"]).resolve(),
                            (pdir / job["two"]).resolve(),
                            case["rubric_path"]), rd, home)
            if err and "session limit" in err.lower():
                bl.log("Claude session limit — stop; resume later.")
                return
            payload = parsed if parsed else {"error": err}
            payload["_job"] = job
            out.write_text(json.dumps(payload, indent=2))
            time.sleep(args.pause)

    bl.log("stage 4 done — next: 05_report.py")


if __name__ == "__main__":
    main()
