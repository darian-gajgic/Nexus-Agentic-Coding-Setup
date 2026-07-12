#!/usr/bin/env python3
"""Bench-01 core acceptance suite (hidden from contestants).

The brief (../PROMPT.md) is deliberately loose and human-written — the point
of the benchmark is how each system plans and fills the gaps. So this suite
only scores behavior that ANY reasonable reading of the brief pins down:

  - the named CLI (gridcalc.py eval/get), CELL=VALUE output lines
  - unambiguous arithmetic / precedence / function results
  - the explicitly pinned whole-number formatting (81, not 81.0)
  - graceful handling of div-by-zero, cycles, garbage formulas, missing files
    (no crash, no hang, some recognizable error marker in cell values)

Matching is tolerant: eval output is parsed order-independently, numbers are
compared as floats (except the pinned no-trailing-.0 rule for whole numbers),
and any Excel-ish error marker is accepted (#..., or err/div/cycle/... words).
Genuinely ambiguous semantics (empty cells, ROUND tie-breaking, boolean
printing, string comparisons, eval ordering, duplicate definitions, exit
codes) are deliberately NOT scored here — the blind judge (Phase F) assesses
those decisions and their documentation.

Usage:  python3 acceptance_test.py <solution_dir>
Final line:  SCORE <passed>/<total> (<pct>%)
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

H1 = """\
# happy-path sheet

A1=40
B1=2.5
C1=widgets
A2==A1*2+1
B2==SUM(A1:B1, 10)
C2==IF(A1>3, CONCAT(C1, ": ", A1), "few")
D2==A1/B1
E2==(A1+B1)*2
F2==-A1+50
G2==MAX(A1:B1)
H2==MIN(A1:B1)
A3==COUNT(A1:B1)
B3==AVG(A1:B1)
C3==ROUND(3.14159, 2)
D3==LEN(C1)
E3==IF(B1>3, 1, 2)
F3==SUM(A1, B1, 7.5)
G3==A1*2/4-3
H3=hello world
A4=-7
B4=3.0
"""
H1_CELLS = ["A1", "B1", "C1", "A2", "B2", "C2", "D2", "E2", "F2", "G2", "H2",
            "A3", "B3", "C3", "D3", "E3", "F3", "G3", "H3", "A4", "B4"]

R1 = """\
A1=10
B1==A1/0
C1==C1
D1==E1
E1==D1
F1==SUM(
G1==FOO(A1)
H1==A1+
"""

SHEETS = {"h1.grid": H1, "r1.grid": R1}

ERR_WORDS = ("err", "div", "cycle", "circular", "invalid", "unknown", "ref", "name")


def is_err_marker(s):
    s = s.strip()
    if not s:
        return False
    if s.startswith("#"):
        return True
    low = s.lower()
    return any(w in low for w in ERR_WORDS)


def num_ok(out, want):
    s = out.strip()
    try:
        v = float(s)
    except ValueError:
        return False
    if abs(v - want) > 1e-9:
        return False
    if float(want).is_integer():
        # the one formatting rule the brief pins explicitly: 81, not 81.0
        return re.fullmatch(r"-?\d+", s) is not None
    return True


# (id, cell, kind, expected) — kind: num | str (list of accepted) | err
GET_CHECKS = [
    ("H1 A1 int literal",      "h1.grid", "A1", "num", 40),
    ("H1 A2 precedence",       "h1.grid", "A2", "num", 81),
    ("H1 B2 SUM range+arg",    "h1.grid", "B2", "num", 52.5),
    ("H1 C2 IF+CONCAT",        "h1.grid", "C2", "str", ["widgets: 40", "widgets: 40.0"]),
    ("H1 D2 division",         "h1.grid", "D2", "num", 16),
    ("H1 E2 parentheses",      "h1.grid", "E2", "num", 85),
    ("H1 F2 unary minus",      "h1.grid", "F2", "num", 10),
    ("H1 G2 MAX",              "h1.grid", "G2", "num", 40),
    ("H1 H2 MIN",              "h1.grid", "H2", "num", 2.5),
    ("H1 A3 COUNT",            "h1.grid", "A3", "num", 2),
    ("H1 B3 AVG",              "h1.grid", "B3", "num", 21.25),
    ("H1 C3 ROUND 2dp",        "h1.grid", "C3", "num", 3.14),
    ("H1 D3 LEN",              "h1.grid", "D3", "num", 7),
    ("H1 E3 IF false branch",  "h1.grid", "E3", "num", 2),
    ("H1 F3 SUM plain args",   "h1.grid", "F3", "num", 50),
    ("H1 G3 mul/div assoc",    "h1.grid", "G3", "num", 17),
    ("H1 H3 text verbatim",    "h1.grid", "H3", "str", ["hello world"]),
    ("H1 A4 negative literal", "h1.grid", "A4", "num", -7),
    ("H1 B4 3.0 prints 3",     "h1.grid", "B4", "num", 3),
    ("R1 A1 untainted",        "r1.grid", "A1", "num", 10),
    ("R1 B1 div-by-zero",      "r1.grid", "B1", "err", None),
    ("R1 C1 self-cycle",       "r1.grid", "C1", "err", None),
    ("R1 D1 mutual cycle",     "r1.grid", "D1", "err", None),
    ("R1 F1 unclosed call",    "r1.grid", "F1", "err", None),
    ("R1 G1 unknown func",     "r1.grid", "G1", "err", None),
    ("R1 H1 dangling op",      "r1.grid", "H1", "err", None),
]

DELIVERABLES = ["gridcalc.py", "test_gridcalc.py", "README.md"]
results = []


def check(cid, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {cid}" + (f": {detail}" if detail and not ok else ""))


def run(prog, argv, cwd):
    try:
        return subprocess.run([sys.executable, str(prog)] + argv,
                              cwd=cwd, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return None


def parse_eval(stdout):
    """CELL=VALUE lines -> dict (first '=' splits; tolerant of edge spaces)."""
    cells = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        cells[k.strip()] = v.strip()
    return cells


def main():
    if len(sys.argv) != 2:
        print("usage: python3 acceptance_test.py <solution_dir>", file=sys.stderr)
        sys.exit(2)
    sol = Path(sys.argv[1]).expanduser().resolve()
    prog = sol / "gridcalc.py"

    for f in DELIVERABLES:
        check(f"FILE {f} present", (sol / f).is_file())
    extras = [p.name for p in sol.iterdir()
              if p.name not in DELIVERABLES and p.name != "__pycache__"] if sol.is_dir() else []
    if extras:
        print(f"NOTE extra files (cleanup was requested; judge decides weight): {sorted(extras)}")

    if not prog.is_file():
        total = len(results) + len(GET_CHECKS) + 6
        print(f"SCORE {sum(results)}/{total} ({100.0 * sum(results) / total:.1f}%)  [gridcalc.py missing]")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as td:
        for name, content in SHEETS.items():
            (Path(td) / name).write_text(content, encoding="utf-8")

        for cid, sheet, cell, kind, want in GET_CHECKS:
            r = run(prog, ["get", sheet, cell], td)
            if r is None:
                check(cid, False, "TIMEOUT >15s (hang)")
                continue
            if "Traceback" in r.stderr:
                check(cid, False, f"crashed: {r.stderr.strip().splitlines()[-1]}")
                continue
            out = r.stdout.strip()
            if kind == "num":
                check(cid, num_ok(out, want), f"got {out!r}, want {want}")
            elif kind == "str":
                check(cid, out in want, f"got {out!r}, want one of {want}")
            else:
                check(cid, is_err_marker(out), f"got {out!r}, want an error marker")

        # eval contract: runs cleanly, exactly the defined cells, values agree
        r = run(prog, ["eval", "h1.grid"], td)
        if r is None:
            check("EVAL h1 completes", False, "TIMEOUT >15s")
            check("EVAL h1 exact cell set", False)
            check("EVAL h1 A2 value", False)
        else:
            check("EVAL h1 completes", r.returncode == 0 and "Traceback" not in r.stderr,
                  f"exit {r.returncode}, stderr {r.stderr.strip()[:120]!r}")
            cells = parse_eval(r.stdout)
            check("EVAL h1 exact cell set", set(cells) == set(H1_CELLS),
                  f"missing {sorted(set(H1_CELLS) - set(cells))}, extra {sorted(set(cells) - set(H1_CELLS))}")
            check("EVAL h1 A2 value", num_ok(cells.get("A2", ""), 81),
                  f"got {cells.get('A2')!r}")

        r = run(prog, ["eval", "r1.grid"], td)
        check("EVAL r1 no crash/hang on errors+cycles",
              r is not None and "Traceback" not in r.stderr,
              "TIMEOUT" if r is None else f"stderr {r.stderr.strip()[:120]!r}")

        # CLI robustness (pinned by "handle missing files gracefully" + basic sanity)
        r = run(prog, ["eval", "no-such-file.grid"], td)
        check("CLI missing file: clean nonzero exit",
              r is not None and r.returncode != 0 and "Traceback" not in r.stderr,
              "TIMEOUT" if r is None else f"exit {r.returncode}, stderr {r.stderr.strip()[:120]!r}")
        r = run(prog, ["get", "h1.grid"], td)
        check("CLI get without CELL: clean nonzero exit",
              r is not None and r.returncode != 0 and "Traceback" not in r.stderr,
              "TIMEOUT" if r is None else f"exit {r.returncode}")

    total = len(results)
    passed = sum(results)
    print(f"SCORE {passed}/{total} ({100.0 * passed / total:.1f}%)")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
