# Evals — stop tuning blind

> **This protocol is AUTOMATED now (2026-07-08).** The living corpus moved to
> `domains/<domain>/evals/*.md` (format: `domains/EVALS-README.md`), and Nexus runs +
> scores it end-to-end: **Specialists → 📏 Evals** — pick the domain, press ▶ Run evals;
> the frontier judge scores every case against the domain RUBRIC and the run history
> keeps score trends per config fingerprint. The three cases that used to live in
> `cases/` are ported into the per-domain corpus. This folder stays as the manual
> protocol description + baseline archive.

Purpose: every time you change the setup (SOUL.md, a playbook, a specialist, a model setting),
run 2–3 of these fixed tasks and compare against the saved baseline. If outputs didn't get
better, the change didn't help — revert it. 30 minutes of eval beats a week of vibes.

## Protocol

1. Pick 2–3 cases relevant to what you changed (`cases/`).
2. Run each case's **Run** command. Save the output next to the case file as
   `<case>-YYYY-MM-DD.md`.
3. Judge it: `cjudge <output-file> <domain>` (the case says which domain).
4. Compare verdict + rubric scores against the last saved run. Better / same / worse → keep /
   keep / revert.
5. First time through: today's outputs ARE the baseline. Commit them.

## Adding cases (do this constantly)

Every REAL task that mattered becomes an eval case: copy the actual prompt you used into a new
file in `cases/` using the same format. Real failures make the best cases — if the system got
something wrong once, the case proves it stays fixed.

Keep the set small and real: 10–20 cases across your domains is plenty.
