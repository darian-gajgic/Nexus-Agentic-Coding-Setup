I need a small command-line tool for work, written in Python (3.10+ is fine, but no external libraries please — it has to run anywhere).

We keep little "grid" files around — text files that work like a mini spreadsheet. Example:

```
# monthly numbers

A1=40
B1=2.5
C1=widgets
A2==A1*2+1
B2==SUM(A1:B1, 10)
C2==IF(A1>3, CONCAT(C1, ": ", A1), "few")
```

Cells are named like in Excel (A1, B7, ...). Whatever comes after the first `=` is the cell's content: if it starts with another `=`, it's a formula, otherwise it's just a number or a piece of text. Lines starting with `#` and blank lines don't count.

Formulas should support the usual stuff: `+ - * /` with normal precedence, parentheses, comparisons (`=`, `<>`, `<`, `<=`, `>`, `>=`), references to other cells, ranges like `A1:B3` inside functions, and at least these functions: SUM, MIN, MAX, COUNT, AVG, IF, LEN, CONCAT, ROUND.

I want to use it like this:

```
python3 gridcalc.py eval FILE      # prints every defined cell as CELL=VALUE, one per line
python3 gridcalc.py get FILE CELL  # prints just that one cell's value
```

For the example above, A2 should come out as 81 and B2 as 52.5. Whole numbers should print without a trailing .0 (so 81, not 81.0).

Important: this must not crash or hang on weird input. Division by zero, formulas that reference themselves in a circle, garbage formulas, missing files — handle all of that gracefully. Excel-style error values in the output (#DIV/0! and friends) would be ideal.

Deliverables, in the current directory:

- `gridcalc.py`
- `test_gridcalc.py` — proper unit tests I can run with `python3 -m unittest`
- `README.md` — short: usage, the file format, and every decision you made yourself because I didn't specify it

I'll be away while you work, so don't ask questions — where something is unclear, pick something sensible and write it down in the README. When you're done, run your tests, make sure the example above works, clean up any scratch files (only those three files should remain), and give me a short summary.
