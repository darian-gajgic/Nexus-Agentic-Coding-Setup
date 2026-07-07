---
title: Root cause — intermittently failing reminder scheduler test
specialist: debugger
notes: exercises evidence-based debugging, minimal-fix discipline, regression-test design
---
Diagnose the failing test below: deliver the ROOT CAUSE (with the exact line(s) and the
mechanism), the minimal fix, why the fix is minimal, and the regression test that pins it.
Reproduce the reasoning from the evidence given — if the evidence is insufficient for
certainty, say what experiment would settle it and what result each hypothesis predicts.

CODE (fixed — scheduler.py):
```python
import datetime

def due_reminders(invoices, now=None):
    "Return invoices due for a reminder: 3, 14, 30 days after due_date, once per stage."
    now = now or datetime.datetime.utcnow()
    out = []
    for inv in invoices:
        days = (now.date() - inv["due_date"]).days
        for stage, offset in enumerate((3, 14, 30)):
            if days >= offset and inv["last_stage"] < stage + 1:
                out.append((inv["id"], stage + 1))
                break
    return out
```

TEST (fails ~once in 30 CI runs, always between 00:00 and 02:00 UTC):
```python
def test_stage1_exactly_3_days():
    inv = {"id": 1, "due_date": (datetime.datetime.now() - datetime.timedelta(days=3)).date(),
           "last_stage": 0}
    assert due_reminders([inv]) == [(1, 1)]
```

CI log excerpt of a failure (Europe/Berlin runner, 00:40 local):
  AssertionError: assert [] == [(1, 1)]

Deliverable: root-cause analysis, the minimal diff, the regression test, and one paragraph on
what in the ORIGINAL design invited the bug (API-shape critique, not blame).
