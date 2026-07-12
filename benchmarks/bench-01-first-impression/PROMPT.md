# Build `gridcalc` — a mini spreadsheet engine (single-file CLI)

You are in an empty working directory. Build the tool specified below, verify it, then stop.

## Deliverables — exactly these three files, in the current directory

1. `gridcalc.py` — the complete implementation. Python 3.10+, **standard library only**, a single file, no network access.
2. `test_gridcalc.py` — your own unit tests (at least 15 meaningful cases), all passing via `python3 -m unittest test_gridcalc -v`.
3. `README.md` — concise usage documentation (CLI, file format, supported functions, error values, and any decisions you made where the spec is silent).

Do not create any other files or directories. Do not ask the user questions: this spec is the contract; where it is silent, decide reasonably and record the decision in the README. An automated acceptance suite will run `gridcalc.py` as a subprocess — **exact output text and exit codes matter**.

## 1. Sheet files

- UTF-8 text. Each line is either: empty (ignored), a comment starting with `#` (ignored), or a cell definition `CELL=CONTENT`.
- `CELL` is one column letter `A`–`Z` followed by a row number `1`–`999` (e.g. `A1`, `Z999`). Uppercase only.
- `CONTENT` is everything after the FIRST `=` on the line, verbatim (it may be empty or contain further `=` characters).
- If the same cell is defined more than once, the last definition wins.
- Any other line is invalid: print a message containing `invalid line N` (N = 1-based line number in the file) to stderr and exit with code 4.

## 2. Cell content

- If CONTENT starts with `=`, the rest (after that first `=`) is a **formula** (§3).
- Otherwise, if CONTENT is an integer or decimal number (optional leading `-`, digits, optional `.` followed by digits — no scientific notation), it is a **number**.
- Otherwise it is a **string** (taken verbatim). `A1=` defines the empty string — that is a string value, NOT an empty cell.
- Cells never defined in the file are **EMPTY**.

## 3. Formulas

Value kinds: number, string, boolean (only produced by comparisons), error, EMPTY.

Grammar (whitespace between tokens is ignored):

- Number literals: `12`, `3.5` (no sign — negation is the unary operator; no scientific notation).
- String literals: double-quoted, e.g. `"hello"`. No escape sequences; a string literal cannot contain `"`. An unterminated string is a parse error.
- Cell references: `B12` (same shape as §1). References like `A0` or `AA1` are parse errors.
- Ranges `A1:B3` (top-left `:` bottom-right). Ranges are allowed ONLY as direct function arguments. A range whose start column is right of its end column, or whose start row is below its end row, is a parse error. A range anywhere else in an expression is a parse error.
- Operators, tightest-binding first: unary `-`; then `*`, `/`; then binary `+`, `-`; then comparisons `=`, `<>`, `<`, `<=`, `>`, `>=` (lowest precedence; chaining comparisons like `1<2<3` is a parse error).
- Parentheses for grouping.
- Function calls: `NAME(arg, arg, ...)` — names are uppercase and case-sensitive.

Functions (a wrong number of arguments is a parse error):

- `SUM`, `MIN`, `MAX`, `COUNT`, `AVG` — 1 or more args, each an expression or a range.
- `IF(cond, a, b)` — exactly 3 args.
- `LEN(s)` — exactly 1 arg.
- `CONCAT(a, ...)` — 1 or more args.
- `ROUND(x, n)` — exactly 2 args.

## 4. Evaluation semantics

1. **Arithmetic** (`+ - * /`, unary `-`): operands must be numbers. EMPTY counts as `0`. A string or boolean operand makes the result `#VALUE!`. Division by zero makes it `#DIV/0!`.
2. **Comparisons**: allowed between two numbers or between two strings (strings compare like Python `str` ordering). Any other combination (number vs string, anything vs boolean or EMPTY) is `#VALUE!`. `=` is equality, `<>` inequality. The result is a boolean.
3. **Aggregates** (`SUM`/`MIN`/`MAX`/`COUNT`/`AVG`): collect the numbers from all arguments. Inside a RANGE, cells holding strings, booleans, or EMPTY are skipped. A direct (non-range) argument that evaluates to a string or boolean makes the result `#VALUE!`; a direct argument that is EMPTY is skipped.
   - `SUM` of no collected numbers is `0`; `COUNT` of none is `0`; `AVG` of none is `#DIV/0!`; `MIN`/`MAX` of none is `#VALUE!`.
   - `COUNT` returns how many numbers were collected. `AVG` = sum / count.
4. **IF(cond, a, b)**: `cond` must be a boolean, otherwise `#VALUE!`. IF is **lazy**: only the chosen branch is evaluated — `IF(1>0, 5, 1/0)` is `5`.
5. **LEN(s)**: `s` must be a string; returns its length as a number. Anything else is `#VALUE!`.
6. **CONCAT(...)**: concatenates all arguments as strings — numbers format per §6, booleans as `TRUE`/`FALSE`, EMPTY as the empty string, strings verbatim. The result is a string.
7. **ROUND(x, n)**: `x` must be a number and `n` a whole number ≥ 0, otherwise `#VALUE!`. Rounds to `n` decimal places, **half away from zero**: `ROUND(2.5, 0)` is `3`, `ROUND(-2.5, 0)` is `-3`.
8. **Errors propagate**: if evaluating any needed operand or argument (including any cell inside a used range) yields an error, the result is that error. IF's laziness still applies — an error in the non-chosen branch is invisible.
9. **References**: a reference to a formula cell uses that cell's evaluated value; errors propagate through references.
10. **Cycles**: if evaluating a cell requires its own value again (directly or transitively), every cell on that cycle evaluates to `#CYCLE!`. Cells that merely depend on a cycle receive `#CYCLE!` through normal error propagation. The program must never hang or crash on cycles.
11. **Parse errors** (bad syntax, unknown or lowercase function name, wrong arity, invalid reference, misplaced or reversed range, unterminated string): the cell's value is `#ERR!`. Parse errors never crash the program.

Error values (exact spellings): `#ERR!`, `#VALUE!`, `#DIV/0!`, `#CYCLE!`.

## 5. Command-line interface

- `python3 gridcalc.py eval FILE` — evaluate the sheet, then print one line per DEFINED cell as `CELL=VALUE`, sorted by row number ascending, then column letter ascending (A1, B1, … then A2, …). Exit code 0.
- `python3 gridcalc.py get FILE CELL` — print the value of CELL on one line (an undefined/EMPTY cell prints an empty line). Exit code 0. An invalid CELL argument is a usage error.
- Usage errors (missing or unknown subcommand, wrong argument count, invalid CELL): message to stderr, exit code 2.
- FILE missing or unreadable: message to stderr, exit code 3.
- Invalid sheet line: message containing `invalid line N` to stderr, exit code 4 (§1).

## 6. Value formatting (stdout)

- Numbers: if the value is mathematically a whole number, print it with no decimal part (`8`, not `8.0`); otherwise print Python's `str()` of the float (`8.5`, `3.14`).
- Strings: verbatim, no quotes.
- Booleans: `TRUE` / `FALSE`.
- Errors: their exact spellings from §4.

## 7. Worked example

`sheet.grid`:

```
# demo
A1=4
B1=2.5
C1=widgets
A2==A1*2+1
B2==SUM(A1:B1, 10)
C2==IF(A1>3, CONCAT(C1, ": ", A1), "few")
D2==A1/(A1-4)
```

`python3 gridcalc.py eval sheet.grid` prints exactly:

```
A1=4
B1=2.5
C1=widgets
A2=9
B2=16.5
C2=widgets: 4
D2=#DIV/0!
```

## 8. Process requirements

- Write the implementation and your tests, run `python3 -m unittest test_gridcalc -v`, and fix failures until green.
- Also create the §7 example file yourself, run `eval` on it, and confirm the output matches §7 exactly (then delete that temp file so only the three deliverables remain).
- Finish with a short summary: what you built, how to run it, the decisions you made where the spec was silent, and known limitations.
