# Error-Log Triage Recipe

How to answer "Hermes has errors lately — what are they?" without drowning in
log noise. This is the concrete recipe behind Section 9 of SKILL.md.

## The noise problem

`~/.hermes/logs/errors.log` contains WARNING-level lines that fire on every API
call — the `[zai-override] reasoning_effort=max` line (see Section 7 of
SKILL.md) logs once per request as a WARNING. A busy session generates dozens
of these per minute. A bare `tail` shows a wall of them and hides the real
errors.

## Triage pipeline (run in order)

### Step 1 — ERROR-level only

```bash
grep " ERROR " ~/.hermes/logs/errors.log | tail -40
```

This single filter is the highest-value move: it discards the
reasoning_effort WARNING flood and the per-retry 429 attempts, surfacing only
terminal failures and exceptions.

### Step 2 — categorize by message signature

Group the ERROR lines into the known recurring categories. A one-shot
count-by-category (adjust the pattern list as new signatures appear):

```bash
grep " ERROR " ~/.hermes/logs/errors.log | sed -E 's/^[0-9:, -]+//' | sed -E 's/\[(api_|[0-9])[^]]*\] //' | awk '{
  if ($0 ~ /429/) cat="HTTP 429 Z.ai overload";
  else if ($0 ~ /exceed_context_size/) cat="vision context overflow";
  else if ($0 ~ /trafilatura/) cat="web fetch 403/404";
  else if ($0 ~ /aiohttp.server/) cat="aiohttp SSE disconnect";
  else if ($0 ~ /mem0/) cat="mem0 JSON parse";
  else cat="other";
  count[cat]++;
} END { for (c in count) printf "%5d  %s\n", count[c], c }' | sort -rn
```

Then list the unbucketed "other" tail to catch anything new:

```bash
grep " ERROR " ~/.hermes/logs/errors.log | grep -v -E "429|exceed_context_size|trafilatura|aiohttp.server|mem0" | tail -20
```

### Step 3 — upstream vs actionable

For each category, decide whether the user can fix it:

| Category | Upstream / Actionable | Fix (if actionable) |
|---|---|---|
| HTTP 429 Z.ai overload | UPSTREAM (code 1305, capacity) | none — report + wait |
| homeassistant.local:8123 connect error | ACTIONABLE | start HA, or disable HA plugin |
| mem0 JSON parse | NON-FATAL (extraction skipped) | none — cosmetic |
| aiohttp ClientConnectionResetError | EXPECTED (client disconnect) | none — normal SSE behavior |
| vision exceed_context_size_error | ACTIONABLE config | raise local model `num_ctx` (Section 2) |
| trafilatura 403/404 | EXPECTED (dead URL) | none — retry with a live source |

Lead the user-facing answer with the upstream/actionable split so they know
what's in their control before diving into individual tracebacks.

## Pitfalls

- **Don't `tail` the raw log to answer "what are the errors."** The
  reasoning_effort WARNING flood makes ERROR entries invisible without grep.
  This was the first instinct on 2026-07-06 and it showed only noise.
- **Don't treat each traceback as novel.** Most ERROR entries collapse into a
  handful of recurring categories — match the signature first, read the full
  traceback only if the category is unfamiliar.
- **Per-retry 429 WARNING lines are not the terminal failure.** Only the final
  ERROR after 3 retries matters for triage; the intermediate WARNINGs are
  expected backoff.
- **A category appearing once is not a trend.** Report counts and time spans
  (first/last occurrence) so the user can tell a spike from a one-off.

## Extending the taxonomy

When a genuinely new ERROR signature appears that isn't in the table above,
add it here with its root cause and upstream/actionable verdict. This file is
the living index — SKILL.md Section 9 is the summary pointer.

---

Origin: 2026-07-06 "check Hermes errors" session. Raw errors.log tail showed
~60 lines of `[zai-override] reasoning_effort=max` WARNING noise; the actual
ERROR entries (75 Z.ai 429s, 44 HA connection failures, vision context
overflows) only surfaced after `grep " ERROR "`.
