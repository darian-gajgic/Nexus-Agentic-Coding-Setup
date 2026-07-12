#!/usr/bin/env python3
"""Bench-01 hidden acceptance suite (NOT shown to contestants).

Usage:  python3 acceptance_test.py <solution_dir>

Runs <solution_dir>/gridcalc.py as a subprocess against fixture sheets and
checks values, ordering, exit codes and stderr messages against the spec in
../PROMPT.md. Prints one line per check and a final machine-greppable line:

    SCORE <passed>/<total> (<pct>%)
"""
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- fixtures

S1 = """\
# bench sheet 1 — literals, arithmetic, empties

A1=5
B1=3.5
C1=hello world
D1=
E1==A1+B1
F1==A1*2-3
G1==-A1+10
H1==A1/2
A2==(A1+B1)*2
B2==A1/0
C2==A1+C1
D2==A1+D1
E2==A1+Z9
F2=42
G2=-7
H2=3.0
"""

S2 = """\
A1=1
A2=2
A3=3
B1=10
B2=x
B3=20
C1==SUM(A1:A3)
C2==SUM(A1:B3)
C3==SUM(A1:A3, 100)
C4==SUM(1, "a")
D1==AVG(A1:A3)
D2==AVG(B2:B2)
D3==MIN(A1:B3)
D4==MAX(A1:B3)
D5==COUNT(A1:B3)
E1==AVG(A1, A2)
E2==ROUND(2.5, 0)
E3==ROUND(-2.5, 0)
E4==ROUND(3.14159, 2)
F1==LEN(B2)
F2==LEN(A1)
F3==CONCAT("a", 1, B2)
F4==CONCAT("v=", A1+A2)
"""

S3 = """\
A1=5
A2=abc
B1==A1>3
B2==A1<=4
B3==A2="abc"
B4==A2<>"abc"
B5==A1="5"
C1==IF(A1>3, "big", "small")
C2==IF(A1>10, 1/0, 99)
C3==IF(A1, 1, 2)
C4==IF(A1>0, 1/0, 5)
D1==A2<"b"
"""

S4 = """\
A1==B1
B1==A1
C1==A1+1
D1==D1
E1=7
F1==E1+1
"""

S5 = """\
A1==SUM(
A2==FOO(1)
A3==A1:B2
A4==1 +
A5==IF(1>0, 2)
A6==A0+1
A7==SUM(B3:A1)
A8=="oops
"""

S6 = """\
C2=3
A1=1
B1=2
A2=9
A1=10
D1==A1*2
"""

BAD1 = "hello\n"
BAD2 = "A1=1\n1A=5\n"

SHEETS = {
    "s1.grid": S1, "s2.grid": S2, "s3.grid": S3,
    "s4.grid": S4, "s5.grid": S5, "s6.grid": S6,
    "bad1.grid": BAD1, "bad2.grid": BAD2,
}

# ------------------------------------------------------------------ checks
# (id, argv, expect_exit, expect_stdout_stripped_or_None, stderr_substring_or_None)

def g(sheet, cell):
    return ["get", sheet, cell]

CHECKS = [
    # --- S1: literals, arithmetic, empty vs empty-string (15)
    ("S1-01 add",              g("s1.grid", "E1"), 0, "8.5", None),
    ("S1-02 precedence",       g("s1.grid", "F1"), 0, "7", None),
    ("S1-03 unary minus",      g("s1.grid", "G1"), 0, "5", None),
    ("S1-04 float div",        g("s1.grid", "H1"), 0, "2.5", None),
    ("S1-05 parens",           g("s1.grid", "A2"), 0, "17", None),
    ("S1-06 div by zero",      g("s1.grid", "B2"), 0, "#DIV/0!", None),
    ("S1-07 num+string",       g("s1.grid", "C2"), 0, "#VALUE!", None),
    ("S1-08 num+emptystring",  g("s1.grid", "D2"), 0, "#VALUE!", None),
    ("S1-09 num+EMPTY=num",    g("s1.grid", "E2"), 0, "5", None),
    ("S1-10 int literal",      g("s1.grid", "F2"), 0, "42", None),
    ("S1-11 negative literal", g("s1.grid", "G2"), 0, "-7", None),
    ("S1-12 3.0 prints 3",     g("s1.grid", "H2"), 0, "3", None),
    ("S1-13 string verbatim",  g("s1.grid", "C1"), 0, "hello world", None),
    ("S1-14 empty string",     g("s1.grid", "D1"), 0, "", None),
    ("S1-15 EMPTY cell",       g("s1.grid", "Q5"), 0, "", None),
    # --- S2: functions (17)
    ("S2-01 SUM range",        g("s2.grid", "C1"), 0, "6", None),
    ("S2-02 SUM rect skip str",g("s2.grid", "C2"), 0, "36", None),
    ("S2-03 SUM mixed args",   g("s2.grid", "C3"), 0, "106", None),
    ("S2-04 SUM direct str",   g("s2.grid", "C4"), 0, "#VALUE!", None),
    ("S2-05 AVG",              g("s2.grid", "D1"), 0, "2", None),
    ("S2-06 AVG none DIV0",    g("s2.grid", "D2"), 0, "#DIV/0!", None),
    ("S2-07 MIN",              g("s2.grid", "D3"), 0, "1", None),
    ("S2-08 MAX",              g("s2.grid", "D4"), 0, "20", None),
    ("S2-09 COUNT",            g("s2.grid", "D5"), 0, "5", None),
    ("S2-10 AVG args",         g("s2.grid", "E1"), 0, "1.5", None),
    ("S2-11 ROUND half-away",  g("s2.grid", "E2"), 0, "3", None),
    ("S2-12 ROUND neg half",   g("s2.grid", "E3"), 0, "-3", None),
    ("S2-13 ROUND 2dp",        g("s2.grid", "E4"), 0, "3.14", None),
    ("S2-14 LEN",              g("s2.grid", "F1"), 0, "1", None),
    ("S2-15 LEN of number",    g("s2.grid", "F2"), 0, "#VALUE!", None),
    ("S2-16 CONCAT mixed",     g("s2.grid", "F3"), 0, "a1x", None),
    ("S2-17 CONCAT expr",      g("s2.grid", "F4"), 0, "v=3", None),
    # --- S3: comparisons & IF (10)
    ("S3-01 gt",               g("s3.grid", "B1"), 0, "TRUE", None),
    ("S3-02 le",               g("s3.grid", "B2"), 0, "FALSE", None),
    ("S3-03 str eq",           g("s3.grid", "B3"), 0, "TRUE", None),
    ("S3-04 str neq",          g("s3.grid", "B4"), 0, "FALSE", None),
    ("S3-05 mixed cmp",        g("s3.grid", "B5"), 0, "#VALUE!", None),
    ("S3-06 IF then",          g("s3.grid", "C1"), 0, "big", None),
    ("S3-07 IF lazy",          g("s3.grid", "C2"), 0, "99", None),
    ("S3-08 IF non-bool cond", g("s3.grid", "C3"), 0, "#VALUE!", None),
    ("S3-09 IF chosen error",  g("s3.grid", "C4"), 0, "#DIV/0!", None),
    ("S3-10 str lt",           g("s3.grid", "D1"), 0, "TRUE", None),
    # --- S4: cycles (5)
    ("S4-01 cycle A",          g("s4.grid", "A1"), 0, "#CYCLE!", None),
    ("S4-02 cycle B",          g("s4.grid", "B1"), 0, "#CYCLE!", None),
    ("S4-03 depends on cycle", g("s4.grid", "C1"), 0, "#CYCLE!", None),
    ("S4-04 self cycle",       g("s4.grid", "D1"), 0, "#CYCLE!", None),
    ("S4-05 untainted cell",   g("s4.grid", "F1"), 0, "8", None),
    # --- S5: parse errors (8)
    ("S5-01 unclosed call",    g("s5.grid", "A1"), 0, "#ERR!", None),
    ("S5-02 unknown func",     g("s5.grid", "A2"), 0, "#ERR!", None),
    ("S5-03 bare range",       g("s5.grid", "A3"), 0, "#ERR!", None),
    ("S5-04 dangling op",      g("s5.grid", "A4"), 0, "#ERR!", None),
    ("S5-05 IF arity",         g("s5.grid", "A5"), 0, "#ERR!", None),
    ("S5-06 ref A0",           g("s5.grid", "A6"), 0, "#ERR!", None),
    ("S5-07 reversed range",   g("s5.grid", "A7"), 0, "#ERR!", None),
    ("S5-08 unterminated str", g("s5.grid", "A8"), 0, "#ERR!", None),
    # --- S6: eval ordering + last-definition-wins (1, full output)
    ("S6-01 eval order+redefine", ["eval", "s6.grid"], 0,
     "A1=10\nB1=2\nD1=20\nA2=9\nC2=3", None),
    # --- CLI behavior (7)
    ("CLI-01 missing file",    ["eval", "nofile.grid"], 3, None, None),
    ("CLI-02 invalid line 1",  ["eval", "bad1.grid"], 4, None, "invalid line 1"),
    ("CLI-03 invalid line 2",  ["eval", "bad2.grid"], 4, None, "invalid line 2"),
    ("CLI-04 no args",         [], 2, None, None),
    ("CLI-05 unknown subcmd",  ["frobnicate", "s1.grid"], 2, None, None),
    ("CLI-06 invalid cell",    g("s1.grid", "A0"), 2, None, None),
    ("CLI-07 get missing arg", ["get", "s1.grid"], 2, None, None),
]

DELIVERABLES = ["gridcalc.py", "test_gridcalc.py", "README.md"]


def main():
    if len(sys.argv) != 2:
        print("usage: python3 acceptance_test.py <solution_dir>", file=sys.stderr)
        sys.exit(2)
    sol = Path(sys.argv[1]).expanduser().resolve()
    prog = sol / "gridcalc.py"
    passed = 0
    total = len(CHECKS) + len(DELIVERABLES)

    for f in DELIVERABLES:
        if (sol / f).is_file():
            passed += 1
            print(f"PASS FILE {f} present")
        else:
            print(f"FAIL FILE {f} missing")
    extras = [p.name for p in sol.iterdir()
              if p.name not in DELIVERABLES and p.name != "__pycache__"] if sol.is_dir() else []
    if extras:
        print(f"NOTE extra files in solution dir (not scored): {sorted(extras)}")

    if not prog.is_file():
        print(f"SCORE {passed}/{total} ({100.0 * passed / total:.1f}%)  [gridcalc.py missing — functional checks skipped]")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as td:
        for name, content in SHEETS.items():
            (Path(td) / name).write_text(content, encoding="utf-8")
        for cid, argv, want_exit, want_out, want_err in CHECKS:
            try:
                r = subprocess.run(
                    [sys.executable, str(prog)] + argv,
                    cwd=td, capture_output=True, text=True, timeout=15)
            except subprocess.TimeoutExpired:
                print(f"FAIL {cid}: TIMEOUT (>15s — hang, likely on cycles)")
                continue
            problems = []
            if r.returncode != want_exit:
                problems.append(f"exit {r.returncode} != {want_exit}")
            if want_out is not None:
                got = "\n".join(l.rstrip() for l in r.stdout.strip().splitlines())
                if got != want_out:
                    problems.append(f"stdout {got!r} != {want_out!r}")
            if want_err is not None and want_err not in r.stderr:
                problems.append(f"stderr missing {want_err!r} (got {r.stderr.strip()!r})")
            if problems:
                print(f"FAIL {cid}: " + "; ".join(problems))
            else:
                passed += 1
                print(f"PASS {cid}")

    print(f"SCORE {passed}/{total} ({100.0 * passed / total:.1f}%)")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
