# Hermes Setup — Implementation Plan (for Claude Opus 4.8 / GLM-5.2 executor)

**Companion to `AUDIT_REPORT.md` (v2, 2026-07-05). This is the step-by-step runbook. Follow phases in order. Do not skip verification steps.**

---

## How to use this document

- **You are the executor.** The auditor (Fable 5) analyzed; you implement. Each task has: **Goal · Preconditions · Steps · Verify · Pitfalls · Rollback.** Do them in the listed order — later tasks assume earlier ones are done and verified.
- **Verify before moving on.** If a Verify step fails, stop and fix it; do not proceed with an unverified change stacked under it.
- **Ask nothing you can check.** All paths, keys, and commands are given. Where a command's exact flags may vary by version, the step says "run `--help` first" — do that, don't guess.
- **Environment:** Hermes home is `~/.hermes`. Config is `~/.hermes/config.yaml`. Hermes source repo is `~/.hermes/hermes-agent` (git-tracked — see the update-safety warning in Phase 0). Ollama is at `http://localhost:11434`. The user runs `sudo -v` in their own terminal to open a sudo window when you need it; do not assume passwordless sudo.

---

## Phase 0 — Preconditions & safety (do this first, once)

### 0.1 Snapshot current state so every change is reversible
**Steps:**
```bash
# Timestamped backup of the whole config + env (values stay local; never print them)
cp -p ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-impl-$(date +%Y%m%d_%H%M%S)
# Record the current gateway pid and Hermes version for later comparison
cat ~/.hermes/gateway.pid; hermes --version
# Turn ON pre-update backups so a future `hermes update` cannot wipe MEMORY.md/skills (incident #48200)
```
In `~/.hermes/config.yaml`, set:
```yaml
updates:
  pre_update_backup: true
  backup_keep: 5
```
**Verify:** `grep -A2 '^updates:' ~/.hermes/config.yaml` shows `pre_update_backup: true`.
**Pitfall:** make **one config change per edit** and keep a backup per change — the last person batched four unrelated changes under no backup.

### 0.2 Understand update-safety before you patch any source
Two tasks below (effort override, supermemory hardening) touch behavior in `~/.hermes/hermes-agent`, which is a **git repo**. `hermes update` runs `git pull --ff-only`; if that fails it runs `git reset --hard origin/main`, which **discards local commits**. Therefore:
- **Never** commit changes inside `~/.hermes/hermes-agent`.
- Implement provider/behavior overrides as **user plugins** under `~/.hermes/plugins/…` (these are NOT in the repo and survive updates), which is exactly what Tasks 4.2 and 8.2 do.
- If you must edit a repo file directly, keep it as an **uncommitted** working-tree change (stash-mode preserves uncommitted changes across updates) and record the diff in `~/.hermes/local-patches/` so it can be re-applied.

### 0.3 Confirm the tools you'll rely on exist
```bash
ollama --version        # must be >= 0.12.7 for qwen3-vl (you have 0.30.x — OK)
docker --version        # needed for Langfuse/LiteLLM (Phase 5); if missing, install rootless docker
python3 -c "import PIL; print('pillow ok')"   # for the deterministic vision tool (Task 2.3)
hermes gateway --help   # learn the exact restart verb for your build
hermes cron --help      # learn cron add syntax for your build
```
**Pitfall:** if `docker` is missing, that only blocks Phase 5/6 (observability, sandbox) — do the MUST phases first.

---

## Phase 1 — Restart the stale gateway (MUST · 5 min)

### 1.1
**Goal:** Load the config the running gateway (pid 115777, ~30h old) never read, so Playwright launches with the correct `--browser chromium` args.
**Steps:**
```bash
# Use the restart verb shown by `hermes gateway --help`. Typically one of:
hermes gateway restart
# …or if there is no restart verb:
hermes gateway stop && sleep 3 && hermes gateway start
```
**Verify (all three):**
```bash
# 1) New pid, different from 115777:
ss -tlnp | grep 127.0.0.1:8642
# 2) The playwright MCP child now carries the chromium flag:
NEWPID=$(cat ~/.hermes/gateway.pid); \
  pgrep -f 'playwright-mcp' | while read p; do tr '\0' ' ' < /proc/$p/cmdline; echo; done
#    → must include: --browser chromium  --isolated
# 3) Drive one navigation in a Hermes CLI session and confirm no "chrome is not found":
#    hermes chat  →  ask it to browser_navigate to https://example.com  → expect success
```
**Pitfall:** MCP args are read **only at process spawn**. From now on, **any** edit to `mcp_servers:` or `plugins:` in config.yaml requires a gateway restart to take effect. Make this a standing rule.
**Rollback:** none needed; restart is safe.

---

## Phase 2 — Fix + upgrade vision (MUST · 20 min)

### 2.1 Pull the new local vision model
**Goal:** Replace `gemma3:4b` (mid-pack, confabulates text) with `qwen3-vl:8b` (reads UI labels/structure/OCR reliably).
```bash
ollama pull qwen3-vl:8b      # 6.1GB; fits the 12GB GPU with headroom
```
**Verify:** `ollama list | grep qwen3-vl` shows `qwen3-vl:8b`. Smoke-test it directly:
```bash
# Confirms the model answers vision prompts at all (use any local PNG):
curl -s http://localhost:11434/api/chat -d '{
  "model":"qwen3-vl:8b","stream":false,
  "messages":[{"role":"user","content":"Reply with the single word OK.","images":[]}]}' | head -c 300
```

### 2.2 Point Hermes' auxiliary vision at Ollama (this is the actual bug fix)
**Goal:** `auxiliary.vision` currently has no `base_url`, and `provider: ollama` is **not** a valid enum value (`auto|openrouter|nous|codex|custom`), so images silently route to text-only GLM-5.2 and fail. Setting `base_url` fixes resolution (it takes precedence over `provider`).
In `~/.hermes/config.yaml`, replace the `auxiliary.vision` block with:
```yaml
auxiliary:
  vision:
    base_url: http://localhost:11434/v1   # OpenAI-compatible Ollama endpoint; takes precedence over provider
    model: qwen3-vl:8b
    timeout: 120
    download_timeout: 30
```
Then **restart the gateway** (Task 1.1) — auxiliary config is snapshotted at startup.
**Verify:** paste/point an image at a Hermes session and confirm `~/.hermes/logs/agent.log` shows the ollama endpoint being used, **not** `Vision auto-detect: zai` or `Vision provider ollama unavailable`:
```bash
tail -n 50 ~/.hermes/logs/agent.log | grep -i vision
```
**Pitfall:** do not set `provider: ollama` and expect it to work without `base_url` — the enum doesn't include `ollama`; `base_url` is what makes it resolve. Leave `provider` unset or `custom`; `base_url` wins regardless.
**Rollback:** restore the config backup from 0.1 and restart.

### 2.3 Add the deterministic color/diff tool (the ONLY correct source for exact colors)
**Goal:** No VLM (local or frontier) reads exact hex reliably — ship a tiny deterministic tool instead. Create it as a script the agent can call.
```bash
mkdir -p ~/.hermes/scripts
cat > ~/.hermes/scripts/pixel_qa.py <<'PY'
#!/usr/bin/env python3
"""Deterministic pixel QA: exact color read + perceptual diff. No VLM guessing.
Usage:
  pixel_qa.py color <img.png> <x> <y>              -> prints exact #RRGGBB
  pixel_qa.py deltae <hexA> <hexB>                 -> prints CIEDE2000 (<2 == identical)
  pixel_qa.py diff <a.png> <b.png> [out.png]       -> prints changed-pixel count + %
"""
import sys
from PIL import Image
def _hex(rgb): return "#%02X%02X%02X" % rgb[:3]
def color(p,x,y): print(_hex(Image.open(p).convert("RGB").getpixel((int(x),int(y)))))
def deltae(a,b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    import numpy as np
    def to_lab(h):
        h=h.lstrip("#"); rgb=np.array([[[int(h[i:i+2],16)/255 for i in (0,2,4)]]])
        return rgb2lab(rgb)
    print(round(float(deltaE_ciede2000(to_lab(a),to_lab(b))[0][0]),3))
def diff(a,b,out=None):
    ia=Image.open(a).convert("RGB"); ib=Image.open(b).convert("RGB")
    if ia.size!=ib.size: print(f"SIZE MISMATCH {ia.size} vs {ib.size}"); sys.exit(2)
    import numpy as np
    da=np.array(ia); db=np.array(ib); mask=(da!=db).any(axis=2)
    n=int(mask.sum()); tot=mask.size
    print(f"changed={n} pixels ({100*n/tot:.3f}%)")
    if out:
        vis=da.copy(); vis[mask]=[255,0,0]; Image.fromarray(vis).save(out)
if __name__=="__main__":
    c=sys.argv[1]
    {"color":lambda:color(*sys.argv[2:5]),
     "deltae":lambda:deltae(*sys.argv[2:4]),
     "diff":lambda:diff(*sys.argv[2:5])}[c]()
PY
chmod +x ~/.hermes/scripts/pixel_qa.py
pip install --user pillow scikit-image numpy   # skimage only needed for the deltae subcommand
```
**Verify:**
```bash
python3 ~/.hermes/scripts/pixel_qa.py deltae "#3B82F6" "#007bff"   # prints a ΔE > 2 (they differ)
python3 ~/.hermes/scripts/pixel_qa.py deltae "#3B82F6" "#3B82F6"   # prints 0.0
```
**Pitfall:** never let the agent report a color it "read" from a screenshot with a VLM — it will confidently hallucinate the nearest famous color (e.g. Bootstrap `#007bff`). Route every exact-color/geometry check to this script.

### 2.4 (Optional, high ROI) Install the Z.AI Vision MCP — included in your GLM Coding Plan
**Goal:** A GLM-4.6V-backed escalation path (`ui_to_artifact`, `ui_diff_check`, `extract_text_from_screenshot`) at zero marginal cost.
```bash
hermes mcp catalog                 # check if it's listed; if so:
hermes mcp install zai-vision      # name per catalog; else follow docs.z.ai/devpack/mcp/vision-mcp-server
# It needs env Z_AI_API_KEY (= your GLM_API_KEY value) and Z_AI_MODE=ZAI
```
Restart the gateway. **Verify:** the new MCP tools appear in a session's tool list. **Pitfall:** still route exact colors to `pixel_qa.py` — GLM-4.6V is a VLM and won't read hex accurately either.

---

## Phase 3 — Fallback & 429 resilience (MUST · 1–2h)

### 3.1 Understand the failure first (do not skip)
The current `fallback_model: ollama/qwen2.5:14b` (a) never fires on the observed 429s and (b) would truncate input to ~4K tokens on a 12GB GPU anyway. Z.AI error **1305 = transient overload** (retry with backoff), distinct from **1302/1308/1310 = rate/quota** (slow down / wait for reset). The right design is: back off on 1305; fail over to a *cloud* model (not a weak local one) on persistent failure.

### 3.2 Quick config-only improvement (do this now)
**Goal:** Make the fallback a real model that returns full-length correct output. Best option: a second GLM-5.2 endpoint on a different provider = byte-identical behavior.
- If you have (or create) an OpenRouter key, set `OPENROUTER_API_KEY` in `~/.hermes/.env` and:
```yaml
fallback_model:
  provider: openrouter
  model: z-ai/glm-5.2
  base_url: https://openrouter.ai/api/v1
```
- If you prefer a cheaper *different* model as fallback: `minimax/minimax-m2.7` ($0.30/$1.20) or `qwen/qwen3-coder-next` ($0.11/$0.80) via OpenRouter.
- Keep a small local model for true offline only — change any local fallback to `qwen3:8b` and set an explicit context so it doesn't silently truncate:
```bash
OLLAMA_CONTEXT_LENGTH=32768 ollama serve   # or set num_ctx in a Modelfile
```
**Verify:** temporarily point `model.base_url` at an invalid host for one test session and confirm the fallback activates and returns a full answer (then revert). Check `agent.log` for a visible fallback notice.
**Pitfall:** the fallback is **silent on success by design** — the user won't be told a weaker model answered. If you keep a non-identical fallback model, add a visible marker (see 3.4).

### 3.3 (Recommended, supersedes 3.2) Put a LiteLLM proxy in front of everything
**Goal:** One local proxy that does automatic backoff, cross-provider failover, cost tracking, and (Phase 5) observability — the SOTA pattern. This is a half-day lift but replaces three separate fixes.
```bash
pip install --user 'litellm[proxy]'
mkdir -p ~/.hermes/litellm
cat > ~/.hermes/litellm/config.yaml <<'YAML'
model_list:
  - model_name: glm-5.2
    litellm_params:
      model: openai/glm-5.2
      api_base: https://api.z.ai/api/coding/paas/v4   # your subscription endpoint
      api_key: os.environ/GLM_API_KEY
      input_cost_per_token: 0.0000014
      output_cost_per_token: 0.0000044
  - model_name: glm-5.2-cloud            # same model, different provider = identical behavior
    litellm_params:
      model: openrouter/z-ai/glm-5.2
      api_key: os.environ/OPENROUTER_API_KEY
  - model_name: opus                     # reserved escalation
    litellm_params:
      model: anthropic/claude-opus-4-8
      api_key: os.environ/ANTHROPIC_API_KEY
router_settings:
  routing_strategy: simple-shuffle
  fallbacks: [{"glm-5.2": ["glm-5.2-cloud"]}]
  context_window_fallbacks: [{"glm-5.2": ["glm-5.2-cloud"]}]
  num_retries: 3
  cooldown_time: 30
litellm_settings:
  drop_params: false        # IMPORTANT: keep reasoning_effort/thinking passthrough intact
YAML
litellm --config ~/.hermes/litellm/config.yaml --port 4000 &
```
Then point Hermes at the proxy in `~/.hermes/config.yaml`:
```yaml
model:
  default: glm-5.2
  provider: openai            # proxy speaks OpenAI protocol
  base_url: http://localhost:4000
```
Restart the gateway.
**Verify:** a normal session works; `curl http://localhost:4000/health` is OK; kill the direct Z.AI reachability (or use a bad key on the primary) and confirm requests transparently fall to `glm-5.2-cloud`.
**Pitfall (prompt caching):** Z.AI's implicit prefix caching depends on a byte-stable request. Confirm LiteLLM forwards the body faithfully (`drop_params: false`) and watch cache-hit behavior after switching. If cache hit-rate drops noticeably, keep the direct base_url for the primary and use LiteLLM only for the fallback leg.
**Pitfall:** run LiteLLM under a process manager (systemd user unit) so it survives reboot; a bare `&` dies with the shell.

### 3.4 Make fallback visible (behavioral)
Add a line to `SOUL.md`'s operating rules (edit BEFORE a session, never mid-session — cache): "If you are answering on a fallback model, state so in one line at the top of the reply." This is a cheap guard against a silent quality cliff during client work.

---

## Phase 4 — Effort control & plan hygiene (MUST · 45 min)

### 4.1 Verify your GLM Coding Plan tier and quota posture
**Steps:** log into the Z.AI dashboard; confirm tier (Lite ~400 prompts/wk, Pro ~2000/wk, Max ~8000/wk) against actual usage. Record it in memory (`hermes` memory) so future sessions know the ceiling. Schedule any heavy batch runs (Phase 7 crons, kanban swarms) for **off-peak** hours — quota burns 3× peak / 2× off-peak (1× off-peak via promo through Sept 2026).
**Verify:** the tier and weekly prompt cap are written to `~/.hermes/memories/` or supermemory.

### 4.2 Make `reasoning_effort` explicit with an update-safe provider override
**Goal:** Today you get `max` only because Z.AI's *undocumented* server default is `max` and Hermes sends no `reasoning_effort`. Make it explicit (robust to a default change) and unlock a `high` cost-lever — without editing the repo.
**Steps:**
```bash
mkdir -p ~/.hermes/plugins/model-providers/zai
# 1) Read the bundled profile so you copy its EXACT register_provider(...) call:
cat ~/.hermes/hermes-agent/plugins/model-providers/zai/__init__.py
```
Create `~/.hermes/plugins/model-providers/zai/__init__.py` by **copying the bundled file verbatim**, then changing only the class so `build_api_kwargs_extras` emits `reasoning_effort`. The changed method must read:
```python
    def build_api_kwargs_extras(self, *, reasoning_config=None, model=None, **context):
        extra_body, top_level = {}, {}
        if not _model_supports_thinking(model):
            return extra_body, top_level
        _EFFORT_MAP = {"minimal":"high","low":"high","medium":"high",
                       "high":"high","xhigh":"max","max":"max"}
        if isinstance(reasoning_config, dict):
            enabled = reasoning_config.get("enabled") is not False
            extra_body["thinking"] = {"type": "enabled" if enabled else "disabled"}
            if enabled:  # reasoning_effort only applies with thinking on
                extra_body["reasoning_effort"] = _EFFORT_MAP.get(reasoning_config.get("effort"), "max")
        else:  # no preference -> explicit thinking on + max (don't rely on server default)
            extra_body["thinking"] = {"type": "enabled"}
            extra_body["reasoning_effort"] = "max"
        import logging; logging.getLogger(__name__).warning("[zai-override] reasoning_effort=%s", extra_body.get("reasoning_effort"))
        return extra_body, top_level
```
Keep the `register_provider(ZaiProfile(name="zai", ...))` call **identical** to the bundled file (same `name`, `aliases`, `env_vars`, `base_url`, etc.) so it overrides by same-name last-writer-wins. Set your config value to a level that maps to max:
```yaml
agent:
  reasoning_effort: xhigh      # maps to reasoning_effort="max" via the override; valid in Hermes' parser
```
Restart the gateway.
**Verify (two ways):**
```bash
# a) Override loaded — the warning line appears after a turn:
tail -n 100 ~/.hermes/logs/agent.log | grep 'zai-override'
# b) Unit check the mapping without a live call:
cd ~/.hermes/hermes-agent && ./venv/bin/python - <<'PY'
import sys; sys.path.insert(0,'/home/sinep/.hermes/plugins/model-providers/zai')
import importlib.util as u
spec=u.spec_from_file_location('zaio','/home/sinep/.hermes/plugins/model-providers/zai/__init__.py')
m=u.module_from_spec(spec); spec.loader.exec_module(m)
p=m.zai
print(p.build_api_kwargs_extras(reasoning_config={'enabled':True,'effort':'xhigh'}, model='glm-5.2'))
# expect: ({'thinking': {'type': 'enabled'}, 'reasoning_effort': 'max'}, {})
PY
```
**Pitfall:** the API accepts only `high`|`max`. Never send `minimal/low/medium/xhigh` verbatim — the map above is required. **Pitfall:** if the unit check errors on the import of `providers.base`, run it from inside the repo venv (as shown) so the base class resolves.
**Rollback:** delete `~/.hermes/plugins/model-providers/zai/__init__.py` and restart — the bundled profile takes over again.

---

## Phase 5 — Observability & cost tracking (SHOULD · ~1 day)

### 5.1 Stand up Langfuse (self-hosted, free)
**Goal:** See per-call tokens, cost, latency, and traces — you're currently blind while budget-constrained.
```bash
git clone https://github.com/langfuse/langfuse.git ~/langfuse
cd ~/langfuse && docker compose up -d
# UI at http://localhost:3000 → create org/project → copy the public + secret keys
```
**Verify:** `http://localhost:3000` loads and you can create a project.

### 5.2 Wire LLM calls to Langfuse via the LiteLLM proxy (zero app code)
If you did Task 3.3, add the Langfuse callback to `~/.hermes/litellm/config.yaml`:
```yaml
litellm_settings:
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]
```
Set in `~/.hermes/.env`: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST=http://localhost:3000`. Restart LiteLLM.
**Verify:** run one Hermes session; a trace with token counts + cost appears in the Langfuse UI within seconds.
**Pitfall:** if you did NOT do 3.3, use **Helicone** as a drop-in proxy instead (change `model.base_url` to the Helicone gateway and add the Helicone key) — same outcome, no LiteLLM. Do not try to instrument Hermes' source directly; the proxy path is update-safe.

### 5.3 (Optional) A minimal regression eval
Create a 10–20 item golden set of representative prompts + expected properties; run them weekly (Phase 7 cron) through an LLM-as-judge scorer (0–5 rubric) and log scores to Langfuse. Alert if the mean drops >20% vs baseline.

---

## Phase 6 — Delivery quality gate (SHOULD · half-day)

### 6.1 Create an LLM-as-judge delivery-gate skill
**Goal:** Code is already gated (`agent.verify_on_stop: auto` is ON for CLI — verify with `grep verify_on_stop ~/.hermes/config.yaml`; if absent it defaults to auto). But copy, research, and design deliverables are **not** checked. Add a critic gate.
**Steps:**
```bash
mkdir -p ~/.hermes/skills/client-delivery-gate
cat > ~/.hermes/skills/client-delivery-gate/SKILL.md <<'MD'
---
name: client-delivery-gate
description: Critic-gate any client deliverable before sending; block low scores.
metadata:
  hermes:
    category: productivity
---
# Client Delivery Gate Skill

Run BEFORE delivering any client-facing artifact (code, copy, research, design spec, proposal).

## When to Use
Any output that will reach a paying client. Not for internal scratch work.

## Procedure
1. Assemble the near-final artifact + the original client brief/requirements.
2. Send BOTH to a critic pass (use `delegate_task` with a fresh subagent, or an
   auxiliary model) with this rubric. Score each 0-5 (0=unusable, 5=excellent):
   - Requirement coverage (did it do everything asked?)
   - Factual correctness (for research/claims → also run the `claim-verification` skill)
   - Clarity & professionalism (client-ready tone, no placeholders/TODOs)
   - Risk (anything that could embarrass the sender?)
3. Compute the mean. If mean < 3.0 OR any single dimension = 0/1, DO NOT deliver —
   return the critic's specific fixes and revise, then re-run this gate.
4. For code deliverables, ALSO require the runtime verification (tests/build) to pass
   (verify_on_stop already enforces this) before delivery.

## Pitfalls
- Use a 0-5 scale, not 0-10 (0-10 adds noise, worse human alignment).
- The critic must see the ORIGINAL brief, not just the artifact, or it can't judge coverage.
- Do not gate on the critic alone for factual output — pair with claim-verification.
MD
```
**Verify:** `hermes skills list | grep client-delivery-gate` shows it enabled; invoke it on a sample deliverable and confirm it produces a scored verdict.
**Pitfall:** keep the description ≤60 chars (it's truncated in the per-turn index). Route the critic to a capable model — GLM-5.2 at max judging its own max-effort output is acceptable; a different model (Sonnet 5) is stronger for high-stakes deliverables.

### 6.2 Adopt `/goal` completion contracts for multi-step deliverables
**Goal:** Turn "is it done?" into evidence-gated completion (v0.18.0's headline feature).
**Steps (usage, not config):** for any multi-step client task, start with:
```
/goal draft Build and ship the client's landing page per the brief
```
or write the contract inline with `verify:` / `constraints:` / `boundaries:` / `stop when:` lines after the goal. Optionally cap turns and route the judge cheaply:
```yaml
goals:
  max_turns: 30
auxiliary:
  goal_judge:
    base_url: http://localhost:11434/v1
    model: qwen3:8b
```
**Verify:** `/goal show` displays the contract; the judge only marks done when the `verify:` criterion produces concrete evidence.
**Pitfall:** the judge fails **open** (continues) on error — the turn budget is the real backstop, so set `max_turns` sanely.

---

## Phase 7 — Proactive automation (SHOULD · start with one job)

### 7.1 Daily morning brief (highest ROI)
**Goal:** A 07:00 agent that assembles calendar + inbox triage + task/kanban digest and delivers to a channel — "works while you sleep."
**Steps:** first pair a delivery channel (the brief must not use `deliver: local`, which reaches nobody). Then:
```bash
hermes cron --help          # confirm the exact `add` flags for your build
# Intended job (adapt flags to --help output):
hermes cron add \
  --name "morning-brief" \
  --schedule "0 7 * * *" \
  --skills "google-workspace,himalaya" \
  --deliver "<your-paired-channel>" \
  --prompt "Assemble today's brief: (1) today's Google Calendar events; (2) triage unread email into urgent/normal/ignore with one-line summaries and suggested replies; (3) list open kanban tasks and client follow-ups due. Keep it under 400 words."
```
**Verify:** `hermes cron list` shows it; `hermes cron run morning-brief` fires it once and the brief arrives in the channel.
**Pitfall:** `deliver: local` only writes a file — set a real channel. **Pitfall:** cron sessions run with `skip_memory` and a 3-min hard interrupt — keep the job scoped.

### 7.2 Then add (one at a time, verify each)
- **Inbox triage + draft replies** (hourly, business hours) via `himalaya`.
- **Brand/market monitor** for her e-commerce (daily) via `deep-research` + `web`.
- **Weekly client-follow-up digest** (Mon 08:00).
**Pitfall:** don't run both nexus `scheduled_jobs` and Hermes cron as schedulers — pick **one** (Hermes cron). Leave nexus scheduling unused or remove it.

### 7.3 Fix the watchdog's blind spots (reliability)
The existing watchdog runs *inside* the gateway, so it can't detect the gateway being down (there was an 8.5h silent outage). Add an **external** liveness check (a real user crontab entry or systemd user timer) that alerts when `~/.hermes/cron/ticker_heartbeat` is >10 min stale or disk >90%, pushing to a phone (ntfy/Telegram). Point the existing watchdog's `deliver` at a channel too.

---

## Phase 8 — Memory & cost routing (SHOULD)

### 8.1 Route cheap auxiliary tasks off the paid main model
**Goal:** `compression`, `web_extract`, `title_generation`, `approval` all default to GLM-5.2 (paid quota). Point them at a cheap local model.
In `~/.hermes/config.yaml` under `auxiliary:`:
```yaml
auxiliary:
  compression:
    base_url: http://localhost:11434/v1
    model: qwen3:8b
  web_extract:
    base_url: http://localhost:11434/v1
    model: qwen3:8b
  title_generation:
    base_url: http://localhost:11434/v1
    model: qwen3:8b
```
Restart the gateway. **Verify:** trigger a compaction (long session) and confirm `agent.log` shows the ollama endpoint for the compression call, not zai. **Pitfall:** keep `auxiliary.vision` on `qwen3-vl:8b` (Phase 2) — don't overwrite it here. **Pitfall:** compression on a weak local model can be lossy on huge contexts; if quality drops, move `compression` back to the main model and keep the others local.

### 8.2 Harden supermemory ingest (or migrate)
**Goal:** Stop silent whole-session loss. supermemory processing is async — a 2xx POST only means "queued."
**Option A (harden, update-safe):** implement a user override of the supermemory memory plugin under `~/.hermes/plugins/memory/supermemory/` that: (1) captures the returned `docId`; (2) polls `client.documents.get(docId)` until `status=="done"` (retry on `"failed"`); (3) wraps the ingest POST in exponential-backoff-with-jitter; (4) spools unsent sessions to a local queue file and retries on next start. Read the bundled `~/.hermes/hermes-agent/plugins/memory/supermemory/__init__.py` first and override only the ingest method, keeping the same registration.
**Option B (migrate, simpler):** switch `memory.provider` to **Zep Cloud** (temporal graph, SOC2/HIPAA — best for evolving client history) or **mem0** (simplest API). Set the provider's key in `.env` and `memory.provider` in config; run `hermes memory setup` if prompted.
**Behavioral stopgap (do immediately regardless):** for any client-critical decision, call `supermemory_store` explicitly during the session rather than trusting session-end ingest.
**Verify:** kill network to supermemory during a session end and confirm the session is retried/spooled (Option A) or that the new provider persists it (Option B).

### 8.3 Give client work a semantic namespace
Use per-client memory namespacing (a supermemory `container_tag` per client, or a mem0/Zep namespace) so "what did we decide about client X" retrieves the right context. Index past deliverables.

---

## Phase 9 — Housekeeping (SHOULD · 30 min total)

Each is a one-liner; verify with the paired check.
- **Re-enable used/needed skills.** In `config.yaml` `skills.disabled`, remove `local-vision-models`, `parallel-delegated-build`, `github-issues`. Verify: `hermes skills list` shows them enabled.
- **Prune `USER.md`** (`~/.hermes/memories/USER.md`, 92.6% full). Distill the two dated incident entries to 2–3 sentence preference statements; push incident detail to supermemory. Verify: file is <1800 chars.
- **Pin Playwright MCP.** In `config.yaml` `mcp_servers.playwright.args`, change `@playwright/mcp@latest` → `@playwright/mcp@0.0.77`, ensure `--headless --isolated --browser chromium --block-service-workers` are present. Restart gateway. Verify: the child cmdline shows `@0.0.77`.
- **Kill the duplicate ollama daemon** on `:11435` (pid 2948). Verify: `ss -tlnp | grep 11435` returns nothing; Hermes still reaches `:11434`.
- **Fix the hardcoded path** in `~/.hermes/skills/software-development/hermes-agent-skill-authoring/SKILL.md` (lines ~21,27): replace `/home/bb/hermes-agent/` with `~/.hermes/hermes-agent/`.

---

## Phase 10 — Larger capability upgrades (CONSIDER · after the above is stable)

### 10.1 Capability routing (cheap → strong) — the way v0.18.0 supports it
`smart_model_routing` is a **stub** (not implemented) — do not configure it. Instead:
```yaml
delegation:
  model: ""          # leave empty to inherit GLM-5.2 for normal subagents
```
Route only *hard* sub-tasks to a stronger model by passing an explicit model to `delegate_task`, or (via the LiteLLM proxy) add an `opus`/`sonnet` model and escalate in the delegation prompt. Reserve **Claude Sonnet 5** ($2/$10 intro through Aug 31 2026) for hard work, **Opus 4.8** for the hardest. GLM-5.2 handles the bulk.

### 10.2 MoA preset for the genuinely hard problems
```bash
hermes moa list                       # see presets
hermes moa configure hard             # create a preset; set:
#   reference_models: [{provider: zai, model: glm-5.2}, {provider: ollama, model: qwen3:14b}]
#   aggregator: {provider: zai, model: glm-5.2}
#   reference_max_tokens: 600         # cap latency
```
Invoke selectively: `/moa <prompt>` or `/model hard --provider moa`. **Do not** use the shipped default preset (it needs gpt-5.5/deepseek/opus keys you lack). **Pitfall:** MoA multiplies per-turn cost (N references + aggregator) against your GLM quota — scope to rare hard tasks.

### 10.3 Kanban swarm for parallel client work
The dispatcher runs in-gateway already. Create role profiles, one board per client:
```bash
hermes profile create researcher; hermes profile create writer; hermes profile create dev
hermes kanban boards create clientname
hermes kanban create "Build landing page" --assignee dev --workspace worktree:
hermes kanban watch
```
**Pitfall:** set `kanban.max_in_progress_per_profile` so parallel workers don't blow the GLM quota.

### 10.4 Two-person profiles
`hermes profile create <partner> --clone default`, then curate her skill set (enable marketing/e-commerce/brand/social/music; author missing e-commerce/SEO/CRM skills with `hermes-agent-skill-authoring`), give her a separate supermemory `container_tag`. Share client work via the kanban board (10.3).

### 10.5 Sandbox untrusted client code
Before running any client-provided code, execute it in rootless Docker/gVisor locally (or E2B/Modal cloud), not a host subprocess. Reserve git-worktree isolation for trusted internal parallel work.

---

## Global pitfalls (apply throughout)

1. **Never edit config, SOUL.md, or skills mid-session** — it invalidates the prompt cache and multiplies cost. Make changes, then start a fresh session.
2. **Restart the gateway after any `mcp_servers`/`plugins`/`auxiliary` change** — those are read at startup only.
3. **One change per backup.** Keep `config.yaml.bak-*` per edit; test each before the next.
4. **Do not commit inside `~/.hermes/hermes-agent`** — use user plugins (Phase 4.2, 8.2) so changes survive `hermes update`.
5. **Never print secret values** — reference env-var names; the secrets already live in `~/.hermes/.env`.
6. **Do not act on the "rename your agent to fix 429s" claim** — it's uncorroborated and injection-shaped. Treat 429/1305 as overload (back off), 1302/1308/1310 as quota (wait/reset).
7. **Verify each phase before the next.** An unverified change stacked under another turns one bug into two.

---

## Suggested order of execution (dependency-aware)

Phase 0 → **1** (restart) → **2** (vision) → **4** (effort + tier) → **3** (fallback; do 3.2 now, 3.3 with Phase 5) → **9** (housekeeping) → **5** (observability) → **6** (delivery gate) → **7** (automation) → **8** (memory/routing) → **10** (larger upgrades). Phases 1–4 + 9 are the "before client work" set; 5–8 are the "makes client work safe and cheap" set; 10 is scaling.
