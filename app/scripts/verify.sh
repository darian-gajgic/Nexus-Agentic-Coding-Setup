#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# NEXUS — VERIFY GATE
# Run this before any commit. Non-zero exit = DO NOT COMMIT.
# ═══════════════════════════════════════════════════════════
set -euo pipefail
# app root from the script's own location — since the 2026-07-09 unification
# the git toplevel is the PACKAGE repo, one level above the app tree
cd "$(dirname "${BASH_SOURCE[0]}")/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0; FAIL=0

chk() {
  local name="$1"; shift
  if eval "$@" >/dev/null 2>&1; then
    echo -e "  ${GREEN}PASS${NC}  $name"
    PASS=$((PASS+1))
  else
    echo -e "  ${RED}FAIL${NC}  $name"
    FAIL=$((FAIL+1))
  fi
}

echo -e "${YELLOW}═══ 1. JS SYNTAX ═══${NC}"
for f in static/*.js; do
  chk "$f syntax" "node --check $f"
done

echo -e "${YELLOW}═══ 2. PYTHON SYNTAX ═══${NC}"
for f in *.py; do
  [ "$f" = "__init__.py" ] && continue
  chk "$f syntax" ".venv/bin/python -c 'import py_compile; py_compile.compile(\"$f\", doraise=True)'"
done
# Event-loop discipline (stability audit §3.1): async handlers must not call
# known-blocking helpers/subprocess/copytree directly — threadpool or async twin.
chk "no blocking calls in async handlers" ".venv/bin/python scripts/check_async_blocking.py"

echo -e "${YELLOW}═══ 3. HTML/CSS REFS ═══${NC}"
chk "index.html references exist" '
  for f in $(grep -oP "src=\"\K/static/[^\"]+" static/index.html; grep -oP "href=\"\K/static/[^\"]+" static/index.html); do
    [ -f ".${f%%\?*}" ] || false
  done
'
chk "no duplicate function defs in app.js" '
  COUNT=$(grep -c "^function " static/app.js)
  UNIQUE=$(grep "^function " static/app.js | sort -u | wc -l)
  [ "$COUNT" -eq "$UNIQUE" ]
'
chk "no console.log/debugger left in app.js" '
  ! grep -nE "console\.(log|debug)|debugger" static/app.js | grep -v "//.*console" | grep -vE "debugger.\]"
'

echo -e "${YELLOW}═══ 5. JARVIS FUNCTION INTEGRITY ═══${NC}"
chk "renderJarvisView exists"        "grep -q 'function renderJarvisView' static/app.js"
chk "jarvisStreamChat exists"        "grep -q 'function jarvisStreamChat' static/app.js"
chk "jarvisSpeak exists"             "grep -q 'function jarvisSpeak' static/app.js"
chk "jarvisStartRecording exists"    "grep -q 'function jarvisStartRecording' static/app.js"
chk "particle avatar mounted (v2)"   "grep -q 'Jarvis3D.mount' static/app.js"
chk "WS TTS client (v2)"             "grep -q '/ws/jarvis/tts' static/app.js"
chk "avatar animations toggle (v2)"  "grep -q 'setAnimations' static/jarvis3d.js"
chk "tts fallback fetch in app.js"   "grep -q 'jarvisFetchClip' static/app.js"
chk "conversation toggle in app.js"  "grep -q 'jConvToggle' static/app.js"
chk "conversation auto-listen"       "grep -q 'jarvisMaybeAutoListen' static/app.js"
chk "avatar.js deleted"              "! [ -f static/avatar.js ]"
chk "no JARVISAvatar references"     "! grep -q 'JARVISAvatar' static/app.js"
chk "no three.js in index.html"      "! grep -q 'three' static/index.html"

echo ""
echo -e "${YELLOW}═══ 6. AGENTIC CAPABILITIES INTEGRITY ═══${NC}"
# Backend modules exist
chk "watchdog.py exists"             "[ -f watchdog.py ]"
chk "scheduler.py exists"            "[ -f scheduler.py ]"
chk "worktree.py exists"             "[ -f worktree.py ]"
# Key endpoints defined in server.py
chk "claim endpoint"                 "grep -q '/api/tasks/{task_id}/claim' server.py"
chk "verify endpoint"                "grep -q '/api/verify' server.py"
chk "approvals endpoint"             "grep -q '/api/approvals' server.py"
chk "watchdog status endpoint"       "grep -q '/api/watchdog/status' server.py"
chk "worktree endpoint"              "grep -q '/api/agents/{agent_id}/worktree' server.py"
chk "memory endpoint"                "grep -q '/api/agents/{agent_id}/memory' server.py"
chk "scheduler endpoint"             "grep -q '/api/scheduler' server.py"
chk "cost endpoint"                  "grep -q '/api/agents/{agent_id}/cost' server.py"
chk "messaging endpoint"             "grep -q '/api/agents/{agent_id}/message' server.py"
# Startup wires the background threads
chk "watchdog wired in startup"      "grep -q 'watchdog_loop' server.py"
chk "scheduler wired in startup"     "grep -q 'scheduler_loop' server.py"
# DB tables + migrations present
chk "verify_runs table"              "grep -q 'CREATE TABLE IF NOT EXISTS verify_runs' database.py"
chk "approvals table"                "grep -q 'CREATE TABLE IF NOT EXISTS approvals' database.py"
chk "memory table"                   "grep -q 'CREATE TABLE IF NOT EXISTS memory' database.py"
chk "scheduled_jobs table"           "grep -q 'CREATE TABLE IF NOT EXISTS scheduled_jobs' database.py"
chk "messages table"                 "grep -q 'CREATE TABLE IF NOT EXISTS messages' database.py"
chk "task claim migration"           "grep -q 'claimed_by' database.py"
chk "agent worktree migration"       "grep -q 'worktree_path' database.py"
# Real dispatch (v2 — SPEC-REAL-AGENTS.md)
chk "hermes_dispatch.py exists"      "[ -f hermes_dispatch.py ]"
chk "dispatch endpoint"              "grep -q '/api/tasks/{task_id}/dispatch' server.py"
chk "transcript endpoint"            "grep -q '/api/tasks/{task_id}/transcript' server.py"
chk "dispatches table"               "grep -q 'CREATE TABLE IF NOT EXISTS dispatches' database.py"
chk "settings endpoint"              "grep -q '/api/settings' server.py"
chk "claim CAS shared helper"        "grep -q 'def claim_task_cas' database.py"
chk "dispatch feature flag"          "grep -q 'dispatch.enabled' server.py"
# The simulation is DEAD (S2 — definition of done: no fake work anywhere)
chk "worker has no random tokens"    "! grep -q 'random.randint' worker.py"
chk "worker has no fake task list"   "! grep -q 'indexing data batch' worker.py"
chk "worker uses real dispatch"      "grep -q 'hermes_dispatch' worker.py"
chk "no demo seed data"              "! grep -q 'Scrape product catalog' database.py"
chk "no simulated metrics"           "! grep -q 'simulate plausible metrics' agent_manager.py"
chk "retire lifecycle exists"        "grep -q 'def retire_agent' agent_manager.py"
chk "retire endpoint"                "grep -q '/api/agents/{agent_id}/retire' server.py"
chk "migration script exists"        "[ -f scripts/migrate_real_agents.py ]"
chk "resume path implemented"        "grep -q '_try_harvest' hermes_dispatch.py"
# S3: judge, files, WIN/LESSON, retry (SPEC R4-R6, X6)
chk "judge endpoint"                 "grep -q '/api/tasks/{task_id}/judge' server.py"
chk "files endpoints"                "grep -q '/api/tasks/{task_id}/files' server.py"
chk "feedback endpoint"              "grep -q '/api/tasks/{task_id}/feedback' server.py"
chk "retry endpoint"                 "grep -q '/api/tasks/{task_id}/retry' server.py"
chk "judge stub exists"              "[ -f scripts/judge_stub.sh ]"
chk "approval drives deliverable"    "grep -q \"action_type.*deliverable\" server.py"
chk "judge UI wired"                 "grep -q 'runJudgeUI' static/app.js"
chk "win/lesson UI wired"            "grep -q 'logFeedbackUI' static/app.js"
# S4: health panel, quota, templates, onboarding, notifications
chk "health-full endpoint"           "grep -q '/api/health/full' server.py"
chk "quota endpoint"                 "grep -q '/api/quota' server.py"
chk "templates endpoint"             "grep -q '/api/templates' server.py"
chk "templates.json valid"           ".venv/bin/python -c 'import json; json.load(open(\"templates.json\"))'"
chk "onboarding endpoint"            "grep -q '/api/onboarding-status' server.py"
chk "desktop notify hook"            "grep -q 'def notify_desktop' hermes_dispatch.py"
chk "quota banner wired"             "grep -q 'updateQuotaBanner' static/app.js"
chk "health card wired"              "grep -q 'healthRowsHTML' static/app.js"
# Round-2 user feedback features
chk "per-task model select"          "grep -q 'm-task-model' static/app.js"
chk "user templates endpoint"        "grep -q 'templates.user.json' server.py"
chk "follow-up chaining"             "grep -q 'followUpTaskUI' static/app.js"
chk "worktree sends repo_path"       "grep -q 'repo_path: repo.trim()' static/app.js"
chk "specialist wizard endpoint"     "grep -q '/api/specialists/wizard' server.py"
chk "specialist wizard UI"           "grep -q 'runSpecialistWizard' static/app.js"
# v2.1: workflows, deliverables, skill wizard, concurrency slots
chk "workflows endpoints"            "grep -q '/api/workflows' server.py"
chk "workflows table"                "grep -q 'CREATE TABLE IF NOT EXISTS workflows' database.py"
chk "dependency gating"              "grep -q 'def deps_satisfied' hermes_dispatch.py"
chk "dep deliverables injected"      "grep -q 'task_dependencies(task)' hermes_dispatch.py"
chk "deliverables endpoint"          "grep -q '/api/deliverables' server.py"
chk "skill wizard endpoint"          "grep -q '/api/hermes-skills/wizard' server.py"
chk "skill wizard UI"                "grep -q 'newSkillUI' static/app.js"
chk "concurrency slot gate"          "grep -q 'def slot_available' hermes_dispatch.py"
chk "worker respects slots"          "grep -q '_slot_ok' worker.py"
chk "orphan-dispatch reconciler"     "grep -q 'def reconcile_stalled_dispatches' hermes_dispatch.py"
chk "reconciler swept by watchdog"   "grep -q 'reconcile_stalled_dispatches' watchdog.py"
chk "reconciler run at boot"         "grep -q 'reconcile_stalled_dispatches' server.py"
chk "workflows view wired"           "grep -q 'function viewWorkflows' static/app.js"
chk "deliverables view wired"        "grep -q 'function viewDeliverables' static/app.js"
chk "session title collision retry"  "grep -q 'invalid_title' hermes_dispatch.py"
chk "task wizard endpoint"           "grep -q '/api/tasks/wizard' server.py"
chk "task wizard UI"                 "grep -q 'describeTaskUI' static/app.js"
chk "wizard workflow proposal"       "grep -q 'proposeWorkflowModal' static/app.js"
# Frontend integration
chk "viewAgentic function"           "grep -q 'function viewAgentic' static/app.js"
chk "agentic nav item"               "grep -q 'data-view=\"agentic\"' static/index.html"
chk "agentic CSS present"            "grep -q 'agentic-grid' static/style.css"
chk "kanban shows claimed_by"        "grep -q 'claimed_by' static/app.js"
chk "approval badge element"         "grep -q 'apprBadge' static/index.html"

# ═══ Block 1: multi-user auth + isolation (docs/SPEC-MULTIUSER.md) ═══
chk "auth module present"            "grep -q 'def try_login' auth.py"
chk "passwords scrypt-hashed"        "grep -q 'hashlib.scrypt' auth.py"
chk "session tokens stored hashed"   "grep -q 'sha256(token' auth.py"
chk "cookie is HttpOnly"             "grep -q 'httponly=True' server.py"
chk "auth middleware wired"          "grep -q 'add_middleware(AuthMiddleware)' server.py"
chk "users table in schema"          "grep -q 'CREATE TABLE IF NOT EXISTS users' database.py"
chk "auth_sessions table in schema"  "grep -q 'CREATE TABLE IF NOT EXISTS auth_sessions' database.py"
chk "legacy rows backfilled"         "grep -q \"SET user_id='u_owner' WHERE user_id IS NULL\" database.py"
chk "task list user-scoped"          "grep -q 'FROM tasks WHERE user_id=?' server.py"
chk "workflow list user-scoped"      "grep -q 'FROM workflows WHERE user_id=? ORDER BY' server.py"
chk "ownership chokepoint (tasks)"   "grep -q 'def _owned_task' server.py"
chk "ownership chokepoint (wf)"      "grep -q 'def _owned_workflow' server.py"
chk "WS broadcast user-targeted"     "grep -q 'if user_id is not None and owner != user_id' server.py"
chk "WS handshake authenticated"     "grep -q 'ws.close(code=4401)' server.py"
chk "per-user JARVIS sessions"       "grep -q '_jarvis_sid_for' server.py"
chk "JARVIS history ownership"       "grep -qE 'session_id not in own' server.py"
chk "user scope published (dispatch)" "grep -q 'publish_session_scope' hermes_dispatch.py"
chk "dispatch publishes task owner"  "grep -q 'user=task.get(\"user_id\")' hermes_dispatch.py"
chk "mem0 plugin user filter"        "grep -q '_session_user_map' ~/.hermes/plugins/mem0-client/__init__.py"
chk "mem0 plugin stamps user"        "grep -q 'md\\[\"user\"\\] = user' ~/.hermes/plugins/mem0-client/__init__.py"
chk "memory galaxy user-filtered"    "grep -q '.get(\"user\", me)' server.py"
chk "loop engine acts as owner"      "grep -q 'INTERNAL_USER_HEADER' loop_engine.py"
chk "login screen in frontend"       "grep -q 'renderLoginScreen' static/app.js"
chk "boot goes through auth gate"    "grep -q '^bootAuth();' static/app.js"
chk "focus is per-user"              "grep -q \"'nexusFocus:' +\" static/app.js"
chk "users admin panel"              "grep -q 'loadUsersPanel' static/app.js"
chk "mobile nav (hamburger)"         "grep -q 'menuBtn' static/index.html && grep -q 'closeMobileNav' static/app.js"
chk "mobile media queries"           "grep -q 'Block 1: Mobile layout pass' static/style.css"
chk "single-user default preserved"  "grep -q 'def auth_required' auth.py && grep -q 'len(rows) >= 2' auth.py"

echo -e "${YELLOW}═══ 12. BLOCK 3: PLAN EDITOR + REPLANNING + EVALS (SPEC-BLOCK3) ═══${NC}"
chk "revalidate endpoint"            "grep -q '\"/api/tasks/wizard/revalidate\"' server.py"
chk "light specialist roster"        "grep -q '\"/api/specialists/names\"' server.py"
chk "repair accepts edited plans"    "grep -q 'max_raw: int = 5' server.py"
chk "replan column migration"        "grep -q '\"replan\" not in existing_wf_cols' database.py"
chk "replan endpoints (3 gates)"     "grep -q 'replan/draft' server.py && grep -q 'replan/apply' server.py && grep -q 'replan/dismiss' server.py"
chk "replan detection in engine"     "grep -q '_sweep_replan_detection' loop_engine.py && grep -A4 'def loop_sweep' loop_engine.py | grep -q '_sweep_replan_detection'"
chk "engine may draft, never applies" "! grep -E 'replan/apply' loop_engine.py | grep -q ."
chk "boot resets orphaned drafts"    "grep -q \"draft interrupted by server restart\" server.py"
chk "archived out of rollup"         "grep -q \"status != 'archived'\" server.py"
chk "archived out of loop engine"    "grep -q \"status != 'archived'\" loop_engine.py"
chk "apply expires stale approvals"  "grep -q 'superseded by replan' server.py"
chk "eval tables migrated"           "grep -q 'CREATE TABLE IF NOT EXISTS eval_runs' database.py && grep -q 'CREATE TABLE IF NOT EXISTS eval_results' database.py"
chk "evals module contract"          "grep -q 'def start_run' evals.py && grep -q 'def parse_judge_metrics' evals.py && grep -q 'def run_judge_cmd' evals.py"
chk "task judge shares eval runner"  "grep -q '_ev.run_judge_cmd' server.py"
chk "eval endpoints"                 "grep -q '\"/api/evals/run\"' server.py && grep -q '\"/api/evals/runs/{run_id}/cancel\"' server.py"
chk "eval runs user-scoped"          "grep -q 'FROM eval_runs WHERE id=? AND user_id=?' server.py"
chk "eval corpus present (>=20)"     "[ \$(ls ~/knowledge/domains/*/evals/*.md 2>/dev/null | wc -l) -ge 20 ]"
chk "eval corpus parses"             ".venv/bin/python -c 'import evals; c=evals.list_corpus(); assert sum(len(d[\"cases\"]) for d in c) >= 20'"
chk "plan editor in frontend"        "grep -q 'function planEdRender' static/app.js && grep -q 'function planEdFinalTasks' static/app.js"
chk "editor deps stay earlier-index" "grep -q 'tasks.slice(0, i)' static/app.js"
chk "replan UI (review modal)"       "grep -q 'function replanReviewModal' static/app.js && grep -q 'replanChipHTML' static/app.js"
chk "evals UI tab"                   "grep -q 'function evalsTabHTML' static/app.js && grep -q 'data-spectab' static/app.js"
chk "cache-buster bumped (v51+)"     "grep -oP 'app.js\?v=\\K[0-9]+' static/index.html | awk '\$1>=51{ok=1} END{exit !ok}'"
chk "block3 spec committed"          "[ -f docs/SPEC-BLOCK3.md ]"

echo -e "${YELLOW}═══ 13. BLOCK 2: REVIEW V2 + GALAXY EDIT + PR (SPEC-BLOCK2) ═══${NC}"
chk "diff lines carry file positions" "grep -q '\"n\": new_no' review.py && grep -q '\"o\": old_no' review.py"
chk "pygments highlighter wired"     "grep -q 'def highlight_file' review.py && [ \$(grep -c 'highlight_files(files)' review.py) -eq 2 ]"
chk "highlight is per-side per-hunk" "grep -q 'context lines keep the new-side highlight' review.py"
chk "review_comments table"          "grep -q 'CREATE TABLE IF NOT EXISTS review_comments' database.py"
chk "comment endpoints (CRUD)"       "grep -q 'review/comments\"' server.py && grep -q 'review/comments/{comment_id}' server.py"
chk "comments feed _retry_task"      "grep -q 'Reviewer LINE COMMENTS (address EVERY one)' server.py"
chk "comments consumed, not deleted" "grep -q \"SET status='consumed', consumed_at=\" server.py"
chk "retry feedback cap raised"      "grep -q 'fb\[:16000\]' server.py"
chk "memory mutation endpoints"      "grep -q '@app.patch(\"/api/memory/{point_id}\")' server.py && grep -q '\"/api/memory/merge\"' server.py"
chk "memory ownership fail-closed"   "grep -q 'def _memory_access' server.py && grep -q 'auth.is_admin()' server.py"
chk "mutations clear galaxy cache"   "grep -q '_MEM3D_CACHE.clear()' server.py"
chk "curate update via mem0 backend" "grep -q 'p._backend.update' ~/.hermes/scripts/mem0_curate.py"
chk "guardian golden synced"         "cmp -s ~/.hermes/scripts/mem0_curate.py ~/hermes-guardian/golden/mem0_curate.py"
chk "pr endpoint + stub hook"        "grep -q '\"/api/tasks/{task_id}/pr\"' server.py && grep -q 'pr.cmd' server.py"
chk "pr_url column migrated"         "grep -q '(\"pr_url\", \"TEXT\")' database.py"
chk "code map in repo framing"       "grep -q 'def _code_map' hermes_dispatch.py && grep -q 'CODE MAP (repository layout)' hermes_dispatch.py"
chk "review UI v2 (split + toggle)"  "grep -q 'function splitHunkHTML' static/app.js && grep -q 'function setReviewMode' static/app.js"
chk "comment UI + retry button"      "grep -q 'function rcSave' static/app.js && grep -q 'function reviewRetryUI' static/app.js"
chk "raw HTML only from pygments"    "grep -q 'const dlHTML = l => l.h !== undefined' static/app.js"
chk "memory modal + merge flow"      "grep -q 'function openMemoryNodeModal' static/app.js && grep -q 'function memMergeConfirm' static/app.js"
chk "galaxy click-select"            "grep -q 'onSelect' static/memory3d.js && grep -q 'onSelect: openMemoryNodeModal' static/app.js"
chk "create-PR button"               "grep -q 'function createPrUI' static/app.js"
chk "review v2 styles"               "grep -q '.split-cell' static/style.css && grep -q '.rc-composer' static/style.css && grep -q '.mem-merge-row' static/style.css"
chk "cache-busters bumped (52/13/6)" "grep -oP 'app.js\?v=\\K[0-9]+' static/index.html | awk '\$1>=52{ok=1} END{exit !ok}' && grep -oP 'style.css\?v=\\K[0-9]+' static/index.html | awk '\$1>=13{ok=1} END{exit !ok}' && grep -oP 'memory3d.js\?v=\\K[0-9]+' static/index.html | awk '\$1>=6{ok=1} END{exit !ok}'"
chk "block2 spec committed"          "[ -f docs/SPEC-BLOCK2.md ]"
chk "block2 gates present"           "[ -f scripts/verify_block2_e2e.py ] && [ -f scripts/verify_block2_ui.py ]"

echo -e "${YELLOW}═══ 14. IN-APP ONBOARDING (SPEC-ONBOARDING) ═══${NC}"
chk "onboarding module contract"     "grep -q 'def schema' onboarding.py && grep -q 'def apply_for' onboarding.py && grep -q 'def status_for' onboarding.py && grep -q 'def _real_slots' onboarding.py"
chk "templates snapshotted"          "[ -f ~/knowledge/templates/BUSINESS-CONTEXT.template.md ] && [ -f ~/knowledge/templates/STYLE-VOICE.template.md ]"
chk "37-slot schema parses"          ".venv/bin/python -c 'import onboarding as ob; s=ob.schema(); assert sum(len(x[\"questions\"]) for x in s)==37 and len(s)==11'"
chk "every section explained"        ".venv/bin/python -c 'import onboarding as ob; assert all(x[\"explain\"].strip() and x[\"file_intro\"].strip() for x in ob.schema())'"
chk "answer tables migrated"         "grep -q 'CREATE TABLE IF NOT EXISTS onboarding_answers' database.py && grep -q 'CREATE TABLE IF NOT EXISTS onboarding_state' database.py"
chk "wizard endpoints"               "grep -q '\"/api/onboarding\"' server.py && grep -q '\"/api/onboarding/answers\"' server.py && grep -q '\"/api/onboarding/apply\"' server.py"
chk "status endpoint per-user"       "grep -q 'ob.status_for(auth.current_user_id())' server.py"
chk "terminal CTA is gone"           "! grep -q 'cd ~/knowledge && claude' server.py"
chk "apply is git-safe"              "grep -q 'pre-onboarding snapshot' onboarding.py"
chk "per-user framing paths"         "grep -q 'def _knowledge_paths' hermes_dispatch.py && grep -q '_knowledge_paths(task)' hermes_dispatch.py"
chk "wizard UI functions"            "grep -q 'function openOnboardingWizard' static/app.js && grep -q 'function renderOnbWizard' static/app.js && grep -q 'function onbApply' static/app.js"
chk "wizard auto-saves (resumable)"  "grep -q 'async function onbCollectSave' static/app.js"
chk "settings entry point"           "grep -q 'Open the guided onboarding' static/app.js"
chk "onboarding styles"              "grep -q '.onb-explain' static/style.css && grep -q '.onb-progress' static/style.css"
chk "cache-busters bumped (53/14)"   "grep -oP 'app.js\?v=\\K[0-9]+' static/index.html | awk '\$1>=53{ok=1} END{exit !ok}' && grep -oP 'style.css\?v=\\K[0-9]+' static/index.html | awk '\$1>=14{ok=1} END{exit !ok}'"
chk "onboarding spec + gates"        "[ -f docs/SPEC-ONBOARDING.md ] && [ -f scripts/verify_onboarding_e2e.py ] && [ -f scripts/verify_onboarding_ui.py ]"

echo -e "${YELLOW}═══ 15. SETTINGS V2 (SPEC-SETTINGS-V2) ═══${NC}"
chk "settings registry module"       "[ -f settings_registry.py ] && grep -q 'def conf' settings_registry.py && grep -q 'def validate' settings_registry.py"
chk "secrets store module"           "[ -f secrets_store.py ] && grep -q 'Fernet' secrets_store.py && grep -q 'def resolve_key' secrets_store.py"
chk "secret.key gitignored"          "grep -qx 'secret.key' .gitignore"
chk "cryptography pinned"            "grep -q 'cryptography' requirements.txt"
chk "settings v2 tables"             "grep -q 'CREATE TABLE IF NOT EXISTS credentials' database.py && grep -q 'CREATE TABLE IF NOT EXISTS user_models' database.py && grep -q 'CREATE TABLE IF NOT EXISTS model_assignments' database.py"
chk "opus 4.8 judge seeded"          "grep -q 'claude-opus-4-8' database.py && grep -q 'frontier_judge' database.py"
chk "schema endpoint"                "grep -q '/api/settings/schema' server.py"
chk "credentials endpoints"          "grep -q '\"/api/credentials\"' server.py && grep -q '/api/credentials/{cred_id}' server.py"
chk "model registry endpoints"       "grep -q '\"/api/models\"' server.py && grep -q '/api/models/{mid}' server.py && grep -q '\"/api/models/assignments\"' server.py"
chk "prefixes derived from registry" "grep -q '_SETTINGS_PREFIXES = sreg.PREFIXES' server.py"
chk "model helpers in db layer"      "grep -q 'def task_models_for' database.py && grep -q 'def resolve_assignment' database.py && grep -q 'def default_task_model' database.py"
chk "dispatch resolves owner model"  "grep -q 'def resolve_task_model' hermes_dispatch.py && grep -q 'resolve_task_model(task)' worker.py"
chk "session-keys bridge"            "grep -q 'def publish_session_key' hermes_dispatch.py && grep -q 'def remove_session_key' hermes_dispatch.py && grep -q 'session-keys.json' hermes_dispatch.py"
chk "judge model plumbing"           "grep -q 'def judge_model_for' evals.py && grep -q 'JUDGE_MODEL' evals.py && grep -q 'judge_model_for(owner)' server.py"
chk "task model validated v registry" "grep -qc 'not in db.task_models_for' server.py"
chk "wizard guidance from registry"  "grep -q 'def _model_guidance' server.py && grep -q '_model_guidance(uid)' server.py"
chk "no hardcoded model list in UI"  "! grep -q 'KNOWN_MODELS' static/app.js"
chk "dynamic model options"          "grep -q 'function taskModelOptions' static/app.js && grep -q 'function ensureModels' static/app.js"
chk "settings v2 UI functions"       "grep -q 'function modelsCardHTML' static/app.js && grep -q 'function credentialsCardHTML' static/app.js && grep -q 'function settingsRegistryHTML' static/app.js && grep -q 'async function saveCredential' static/app.js"
chk "credential input write-only"    "grep -q 'id=\"credValue\" type=\"password\"' static/app.js"
chk "machine default keys (admin)"   "grep -q '/api/credentials/defaults' server.py && grep -q 'def set_default_key' secrets_store.py && grep -q 'def default_key_status' secrets_store.py && grep -q 'DEFAULT_PROVIDERS' secrets_store.py"
chk "default-keys UI"                "grep -q 'function machineDefaultsHTML' static/app.js && grep -q 'async function saveDefaultKey' static/app.js"
chk "cache-buster bumped (55)"       "grep -oP 'app.js\?v=\\K[0-9]+' static/index.html | awk '\$1>=55{ok=1} END{exit !ok}'"
chk "settings v2 spec + gate"        "[ -f docs/SPEC-SETTINGS-V2.md ] && [ -f scripts/verify_settings_e2e.py ]"

echo ""
echo -e "${YELLOW}═══ 16. PROJECT APP PREVIEW (v3.6 — run the whole project, any state) ═══${NC}"
chk "project_preview module"         "[ -f project_preview.py ]"
chk "pp list_states + materialize"   "grep -q 'def list_states' project_preview.py && grep -q 'def materialize' project_preview.py && grep -q 'def app_key' project_preview.py"
chk "pp git + workspace modes"       "grep -q '\"mode\": \"git\"' project_preview.py && grep -q '\"mode\": \"workspace\"' project_preview.py"
chk "pp git archive (read-only)"     "grep -q 'git.*archive' project_preview.py"
chk "pp membership injection gate"   "grep -q 'any(s\\[.key.\\] == key for s in info' project_preview.py"
chk "app_runner instances() helper"  "grep -q 'def instances' app_runner.py"
chk "workflow app endpoints"         "grep -q '/api/workflows/{wf_id}/app/start' server.py && grep -q '/api/workflows/{wf_id}/app/stop' server.py && grep -q '/api/workflows/{wf_id}/app/log' server.py"
chk "project preview UI"             "grep -q 'function projectAppUI' static/app.js && grep -q 'function projectAppModal' static/app.js && grep -q 'function projAppStart' static/app.js"
chk "Test project button wired"      "grep -q 'Test project' static/app.js"

echo ""
echo -e "${YELLOW}═══ 17. SUPER RESULT (grounded critic loop — SUPER-RESULT-PLAN-2026-07-09) ═══${NC}"
chk "critic task columns migrated"   "grep -q '\"critic_verdict\"' database.py && grep -q '\"critic_json\"' database.py && grep -q '\"critic_keys\"' database.py && grep -q '\"deliverable_type\"' database.py"
chk "super_result columns (task+wf)" "[ \$(grep -c '\"super_result\", \"INTEGER DEFAULT 0\"\\|super_result INTEGER DEFAULT 0' database.py) -ge 2 ]"
chk "review_comments.source column"  "grep -q \"ADD COLUMN source TEXT NOT NULL DEFAULT 'user'\" database.py"
chk "super.critic_cmd seeded"        "grep -q 'super.critic_cmd' database.py && grep -q 'super.critic_cmd' settings_registry.py"
chk "critic engine in evals"         "grep -q 'def run_critic_cmd' evals.py && grep -q 'def parse_critic_json' evals.py && grep -q 'def build_critic_sandbox' evals.py && grep -q 'def detect_deliverable_type' evals.py"
chk "critic sandbox isolation"       "grep -q 'git.*clone.*--local' evals.py && grep -q 'remote.*remove.*origin' evals.py && grep -q 'def _scrubbed_env' evals.py"
chk "critic endpoints + thread"      "grep -q '/api/tasks/{task_id}/critic' server.py && grep -q 'def _critic_thread' server.py && grep -q 'def _insert_critic_comments' server.py"
chk "supersede-then-insert (§4.4)"   "grep -q \"status='open' AND source=?\" server.py"
chk "retry: SR approval expiry+tags" "grep -q \"'deliverable','super_result'\" server.py && grep -q '\"CRITIC\"' server.py"
chk "boot reset of orphaned critic"  "grep -q \"WHERE critic_verdict='running'\" server.py"
chk "flag plumbing + sync"           "grep -q 'def _sync_super_result_loop' server.py && grep -q 'super_result: bool = False' server.py"
chk "loop trigger + sweep"           "grep -q '\"id\": \"super_result\"' loop_engine.py && grep -q 'def _sweep_super_result' loop_engine.py"
chk "sweep escalation + helpers"     "grep -q 'def _escalate_super' loop_engine.py && grep -q 'def bump_super_round' loop_engine.py && grep -q 'def mark_super_done' loop_engine.py"
chk "wizard fan-out + reconciler"    "grep -q 'SUPER RESULT FAN-OUT' server.py && grep -q 'def _reconciler_gate_task' server.py"
chk "cverify vendored + installed"   "[ -f ../setup/bin/cverify ] && [ -f \$HOME/.local/bin/cverify ]"
chk "cverify sentinel contract"      "grep -q 'NEXUS_CRITIC_JSON_BEGIN' ../setup/bin/cverify && grep -q 'learning_note' ../setup/bin/cverify"
chk "cjudge N2 structured tail"      "grep -q 'NEXUS_JUDGE_JSON_BEGIN' ../setup/bin/cjudge && grep -q 'JUDGE_TYPE_RUBRIC' ../setup/bin/cjudge"
chk "INVESTIGATION rubric vendored"  "[ -f ../setup/knowledge/rubrics/INVESTIGATION.md ] && grep -q 'A1 VERIFIED-NOT-INFERRED' ../setup/knowledge/rubrics/INVESTIGATION.md"
chk "frontend: chips + critic UI"    "grep -q 'function superChip' static/app.js && grep -q 'function criticSectionHTML' static/app.js && grep -q 'function rvLoadCritic' static/app.js"
chk "frontend: SR toggles"           "grep -q 'id=\"wf-super\"' static/app.js && grep -q 'id=\"m-task-super\"' static/app.js && grep -q 'id=\"td-super\"' static/app.js && grep -q 'id=\"pe-super\"' static/app.js"
chk "SR e2e gate exists"             "[ -f scripts/verify_super_result_e2e.py ]"

echo ""
echo -e "${YELLOW}═══ 18. STT CONSOLIDATION + DICTATION (one whisper for the machine) ═══${NC}"
chk "stt worker exists"              "[ -f stt_worker.py ] && grep -q 'def op_transcribe' stt_worker.py"
chk "voice.py has NO in-process whisper" "! grep -q 'from faster_whisper' voice.py"
chk "voice worker client"            "grep -q 'def _ask_stt_sync' voice.py && grep -q 'def transcribe_pcm' voice.py && grep -q 'def warm_stt' voice.py"
chk "STT/TTS idle timers decoupled"  "grep -q '_last_stt_use' voice.py && grep -q '_last_tts_use' voice.py"
chk "worker holds gpu_lock + evicts" "grep -q 'gpu_section(\"stt\"' stt_worker.py && grep -q 'def _ensure_vram' stt_worker.py"
chk "no adaptive CPU demote (audit#1)" "! grep -q '_asr_monitor\\|_demote_to_cpu' dictation.py"
chk "stt warm endpoint"              "grep -q '/api/jarvis/stt/warm' server.py && grep -q 'stt/warm' static/app.js"
chk "voice settings registered"      "grep -q 'voice.stt_compute' settings_registry.py && grep -q 'voice.stt_idle_timeout' settings_registry.py && grep -q 'vision.idle_timeout' settings_registry.py"
chk "dictation modules exist"        "[ -f dictation.py ] && [ -f dictation_layout.py ] && [ -f dictation_overlay.py ] && [ -f dictation_meeting.py ]"
chk "dictation settings section"     "grep -q '\"id\": \"dictation\"' settings_registry.py && grep -q 'dictation.max_seconds' settings_registry.py"
chk "segmented recording (audit#2)"  "grep -q 'def _record_segments' dictation.py && grep -q 'segment boundary' dictation.py"
chk "LLM word-cap guard (audit#10)"  "grep -q 'llm_max_words' dictation.py"
chk "meeting supervision (audit#3)"  "grep -q 'channel lost' dictation_meeting.py && grep -q 'def _target_for' dictation_meeting.py"
chk "meeting temporal dedup (audit#4)" "grep -q 'def _overlap' dictation_meeting.py"
chk "dictation server wiring"        "grep -q '_dictation.manager.start()' server.py && grep -q '_dictation.manager.shutdown()' server.py"
chk "meetings API"                   "grep -q '/api/meetings' server.py && grep -q '/api/dictation/status' server.py && grep -q '/api/dictation/meeting' server.py"
chk "meetings tab frontend"          "grep -q 'function viewMeetings' static/app.js && grep -q 'function previewMeeting' static/app.js && grep -q 'data-view=\"meetings\"' static/index.html"
chk "STT e2e gate exists"            "[ -f scripts/verify_stt_e2e.py ]"

echo ""
echo -e "${YELLOW}═══ 19. QUALITY AUTOPILOT (QUALITY-AUTOPILOT-PLAN-2026-07-10) ═══${NC}"
# Q4 — project decision log + running brief
chk "Q4 decisions harvest"           "grep -q 'def harvest_decisions' hermes_dispatch.py && grep -q 'def parse_decisions_section' hermes_dispatch.py"
chk "Q4 decisions contract in framing" "grep -q 'END your deliverable with a .## Decisions' hermes_dispatch.py"
chk "Q4 decision log injected"        "grep -q 'PROJECT DECISION LOG' hermes_dispatch.py"
chk "Q4 harvest called on finalize"   "grep -q 'harvest_decisions(task, content)' hermes_dispatch.py"
chk "Q4 brief_mode setting"           "grep -q 'framing.brief_mode' settings_registry.py"
# Q5 — uncertainty tagging
chk "Q5 framing contract"            "grep -q 'UNCERTAINTY TAGGING' hermes_dispatch.py && grep -q 'UNSURE: reason' hermes_dispatch.py"
chk "Q5 cverify UNSURE-first"        "grep -q 'UNSURE' ../setup/bin/cverify && grep -q 'UNSURE' \$HOME/.local/bin/cverify"
chk "Q5 cjudge UNSURE line"          "grep -q 'UNSURE' ../setup/bin/cjudge && grep -q 'UNSURE' \$HOME/.local/bin/cjudge"
chk "Q5 INVESTIGATION rubric note"   "grep -q 'UNSURE' ../setup/knowledge/rubrics/INVESTIGATION.md"
chk "Q5 UI amber highlight"          "grep -q 'function highlightUnsure' static/app.js && grep -q 'unsure-tag' static/style.css"
# Q3 — acceptance-tests-first
chk "Q3 tests_first setting"         "grep -q 'pipeline.tests_first' settings_registry.py"
chk "Q3 repair enforcement"          "grep -q 'def _apply_tests_first' server.py && grep -q '_apply_tests_first(tasks, impl' server.py"
chk "Q3 acceptance contract text"    "grep -q 'ACCEPTANCE-TESTS-FIRST' server.py"
chk "Q3 verifier hash-check"         "grep -q 'sha256sum -c acceptance' server.py"
# N5/N6/N7 — tier-2 setting-gated automations
chk "N5 auto_scope setting+engine"   "grep -q 'judge.auto_scope' settings_registry.py && grep -q 'all_quality' loop_engine.py"
chk "N6 auto_draft setting+sweep"    "grep -q 'replan.auto_draft' settings_registry.py && grep -q 'replan/draft' loop_engine.py"
chk "N7 blind-reject judge gate"     "grep -q 'judge.on_blind_reject' settings_registry.py && grep -q 'def _blind_reject_judge_if_wanted' server.py"
# Q1 — golden-exemplar retrieval (+ L3 lifecycle)
chk "Q1 exemplar selection"          "grep -q 'def golden_exemplars' hermes_dispatch.py && grep -q \"judge_verdict='SHIP'\" hermes_dispatch.py"
chk "Q1 exemplar injection"          "grep -q 'QUALITY BAR' hermes_dispatch.py && grep -q 'golden_exemplars(task)' hermes_dispatch.py"
chk "Q1 exemplar settings"           "grep -q 'exemplars.enabled' settings_registry.py && grep -q 'exemplars.min_score' settings_registry.py && grep -q 'exemplars.max' settings_registry.py"
chk "L3 exemplar age-out"            "grep -q 'exemplars.max_age_months' settings_registry.py && grep -q 'max_age_days' hermes_dispatch.py"
chk "P10a attach after preds, before retry" "awk '/atts = _attachment_lines/{a=NR} /deps = \[d for d in task_dependencies/{d=NR} /if task.get\(.retry_feedback.\):/{r=NR} END{exit !(d&&a&&r&&d<a&&a<r)}' hermes_dispatch.py"
# Q2 — operator-edit distillation (N8 upgraded) + L2
chk "Q2 edit_evidence table"         "grep -q 'CREATE TABLE IF NOT EXISTS edit_evidence' database.py"
chk "Q2 lessons module"              "[ -f lessons.py ] && grep -q 'def run_distillation' lessons.py && grep -q 'def apply_deltas' lessons.py && grep -q 'def gather_evidence_text' lessons.py"
chk "Q2 accept-diff capture"         "grep -q 'def _capture_accept_diff' server.py && grep -q \"record_evidence.*feedback\" server.py"
chk "Q2 lesson_deltas approval"      "grep -q '\"lesson_deltas\"' server.py && grep -q 'lesson_deltas' lessons.py"
chk "Q2 distill endpoint"            "grep -q '/api/lessons/distill' server.py && grep -q '/api/lessons/evidence' server.py"
chk "Q2 distillation sweep hook"     "grep -q 'sweep_distillation' loop_engine.py && grep -q 'def sweep_distillation' lessons.py"
chk "Q2 settings"                    "grep -q 'lessons.auto_distill' settings_registry.py && grep -q 'lessons.min_evidence' settings_registry.py && grep -q 'lessons.cmd' settings_registry.py"
chk "Q2 cdistill vendored+installed" "[ -f ../setup/bin/cdistill ] && [ -f \$HOME/.local/bin/cdistill ] && grep -q 'NEXUS_LESSONS_JSON_BEGIN' ../setup/bin/cdistill"
# [R3] ONE frontier-hook cmd resolver: the shlex+per-token-replace+PATH-fallback
# block must exist exactly once (evals.resolve_cmd_tokens) — no inline copies.
chk "R3 one cmd-token resolver"      "grep -q 'def resolve_cmd_tokens' evals.py && grep -q 'resolve_cmd_tokens' lessons.py && [ \$(grep -c 'local/bin/{tokens\[0\]}' evals.py) = 1 ] && ! grep -q 'local/bin/{tokens\[0\]}' lessons.py && [ \$(grep -c 'shlex\.split' evals.py) = 1 ] && ! grep -q 'shlex\.split' lessons.py && ! grep -q 'local/bin/{tokens\[0\]}' server.py && ! grep -q 'shlex\.split' server.py"
chk "P7 approvals scope column"      "grep -q \"ADD COLUMN scope TEXT NOT NULL DEFAULT 'user'\" database.py"
chk "L2 overlay-vs-canonical"        "grep -q 'user_overlay' lessons.py && grep -q 'def _delta_path' lessons.py"
# Q7a — autopilot presets (two axes) + guardrail rules
chk "Q7a autopilot module"           "[ -f autopilot.py ] && grep -q 'def derive' autopilot.py && grep -q 'INVOLVEMENTS' autopilot.py && grep -q 'SPEND_PROFILES' autopilot.py"
chk "Q7a task+wf columns"            "grep -q '(\"autopilot\", \"TEXT\")' database.py && grep -q 'ADD COLUMN autopilot TEXT' database.py && grep -q 'ADD COLUMN spend_profile TEXT' database.py"
chk "Q7a settings defaults"          "grep -q 'autopilot.default_involvement' settings_registry.py && grep -q 'autopilot.default_spend' settings_registry.py"
chk "Q7a defaults wired (not dead)"  "grep -q '/api/autopilot/defaults' server.py && grep -q '/api/autopilot/defaults' static/app.js && grep -q 'AUTOPILOT_DEFAULTS.involvement =' static/app.js"
chk "Q7a design_loop derivation"     "grep -q 'import autopilot as _ap' loop_engine.py && grep -q 'round_cap' loop_engine.py"
chk "rule1 preference absorbed"      "grep -q 'spend absorbs' loop_engine.py || grep -q \"preference = .speed. if sp == .eco\" autopilot.py"
chk "rule2 risk hard floor"          "grep -q 'risk hard floor' loop_engine.py && grep -q 'risk_floor' autopilot.py"
chk "rule4 budget multiplier"        "grep -q 'def _autopilot_fields' server.py && grep -q 'budget_mult' autopilot.py"
chk "rule5 pipeline depth"           "grep -q 'pipeline_depth' server.py && grep -q 'eco_collapse' server.py"
chk "rule6 smart cap 3"              "grep -q 'round_cap = 3' autopilot.py"
chk "rule8 early-exit not a dead flag" "! grep -q 'early_exit' autopilot.py && grep -q 'rule 8 early-exit' server.py && grep -q 'Stops on SHIP' loop_engine.py"
chk "P2 staged forward-deps"         "grep -q 'def _feature_present' autopilot.py && grep -q 'staged' autopilot.py"
chk "Q7a create/patch plumbing"      "grep -q 'ap_inv, ap_spend' server.py && grep -q '_regen_loop_for_profile' server.py"
chk "Q7a workflow cascade"           "grep -q 'UPDATE tasks SET autopilot=? WHERE workflow_id=?' server.py && grep -q 'UPDATE tasks SET spend_profile=? WHERE workflow_id=?' server.py"
chk "Q7a UI card rows + expander"    "grep -q 'function autopilotCardsHTML' static/app.js && grep -q 'function selectedAutopilot' static/app.js"
# Q7b — Decision Inbox
chk "Q7b decisions endpoint"         "grep -q '/api/decisions' server.py && grep -q 'def _decision_card_from_approval' server.py"
chk "Q7b producers attach fields"    "grep -q '\"recommendation\":' hermes_dispatch.py && grep -q 'payload\[.recommendation.\]' loop_engine.py"
chk "Q7b decisions view + badge"     "grep -q 'function viewDecisions' static/app.js && grep -q 'function updateDecisionBadge' static/app.js && grep -q 'decBadge' static/index.html"
chk "Q7b one badge + deck + briefing" "grep -q \"loadDecisions(currentView === 'decisions')\" static/app.js && grep -q 'const decisionsSec' static/app.js && grep -q 'def _collect_decision_cards' server.py && grep -q '_collect_decision_cards(uid' server.py"
chk "Q7b decisions nav item"         "grep -q 'data-view=\"decisions\"' static/index.html"
chk "Q7b auto-approve-ship guard"    "grep -q 'def _sweep_auto_approve_ship' loop_engine.py && grep -q 'auto_approve_ship_hours' loop_engine.py"
chk "Q7b P7 admin scope in decisions" "grep -q \"scope='admin'\" server.py"
# L1/L4 — routing telemetry + fingerprint-tagged params + rule 9 collapse monitor
chk "L1 routing_outcomes table"      "grep -q 'CREATE TABLE IF NOT EXISTS routing_outcomes' database.py"
chk "L1 outcome capture wired"       "grep -q 'def record_outcome' routing.py && grep -q '_routing.record_outcome' hermes_dispatch.py && grep -q '_record_routing_outcome' server.py"
chk "L1 stats job (no LLM)"          "grep -q 'def sweep_stats' routing.py && grep -q '_routing.sweep_stats' loop_engine.py"
chk "L4 learned_params + fingerprint" "grep -q 'CREATE TABLE IF NOT EXISTS learned_params' database.py && grep -q 'def config_fingerprint' routing.py && grep -q 'def learned_param' routing.py"
chk "rule9 collapse monitor"         "grep -q 'ROUTER COLLAPSE WARNING' routing.py"
# B4 — scheduler template passthrough (+ rule 7)
chk "B4 task_template column"        "grep -q 'ADD COLUMN task_template TEXT' database.py"
chk "B4 scheduler applies template"  "grep -q 'task_template' scheduler.py && grep -q 'spend_profile' scheduler.py && grep -q '_sync_super_result_loop' scheduler.py"
chk "B4 endpoint stores template"    "grep -q 'task_template' server.py"
chk "B4 job UI template fields"      "grep -q 'jbSuper' static/app.js && grep -q 'jbSpend' static/app.js"
# Q7c — plain-language layer
chk "Q7c explainers + handler"       "grep -q 'const EXPLAINERS' static/app.js && grep -q 'function showExplainer' static/app.js && grep -q 'qmark' static/style.css"
chk "Q7c house metaphor"             "grep -q 'the house metaphor' static/app.js && grep -q 'you are the client' static/app.js"
chk "Q7c manual autopilot section"   "grep -q 'Autopilot — two simple dials' static/app.js && grep -q 'Your Decisions inbox' static/app.js"
chk "rule3/10 Eco unvalidated caveat" "grep -q 'not yet benchmark-validated' static/app.js && grep -q 'raises Eco' static/app.js"
# Rule 11 — specialist sweep (18 defs aligned to the [UNSURE] contract, in sync)
chk "rule11 specialists use [UNSURE]"  "[ \$(grep -rl '\[UNSURE: reason\]' \$HOME/.hermes/agents/*.md | wc -l) -eq 18 ] && [ \$(grep -rl 'mark anything unchecked as' \$HOME/.hermes/agents/*.md | wc -l) -eq 0 ]"
chk "rule11 vendored copies synced"    "for f in ../setup/hermes/agents/*.md; do cmp -s \"\$f\" \"\$HOME/.hermes/agents/\$(basename \$f)\" || exit 1; done"
# Rule 12 — JARVIS stays current (advisor stance + new endpoints/fields in framing)
chk "rule12 JARVIS advisor stance"   "grep -q 'PROACTIVE ADVISOR' server.py && grep -q 'INSPECTOR' server.py"
chk "rule12 JARVIS knows decisions"  "grep -q 'DECISIONS INBOX: GET /api/decisions' server.py"
chk "rule12 JARVIS knows presets"    "grep -q 'spend_profile.*eco|optimal|smart' server.py"
# P9 — ops hardening (busy_timeout + critic-sandbox age-out at startup + scheduler)
chk "P9 busy_timeout set explicitly"  "grep -q 'PRAGMA busy_timeout' database.py"
chk "P9 critic-sandbox sweep helper"  "grep -q 'def sweep_critic_sandboxes' evals.py"
chk "P9 sandbox swept at startup+cron" "grep -q 'sweep_critic_sandboxes' server.py && grep -q 'sweep_critic_sandboxes' scheduler.py"
chk "autopilot e2e gate exists"      "[ -f scripts/verify_autopilot_e2e.py ]"
chk "autopilot UI gate exists"       "[ -f scripts/verify_autopilot_ui.py ]"
chk "autopilot module + routing/lessons" "[ -f autopilot.py ] && [ -f routing.py ] && [ -f lessons.py ]"

echo ""
echo -e "${YELLOW}═══ 20. DEEP PLAN (conversational planning — DEEP-PLAN-MODE-PLAN-2026-07-10) ═══${NC}"
# Step 1 — DB / settings / purpose seed
chk "plan_sessions table"            "grep -q 'CREATE TABLE IF NOT EXISTS plan_sessions' database.py"
chk "spec_model purpose seeded+whitelisted" "grep -q '\"spec_model\"' database.py && grep -q 'migrated.spec_model' database.py && grep -q 'spec_model' settings_registry.py && grep -q 'MODEL_PURPOSES = ' database.py"
chk "CLI_PURPOSES gate (judge+spec)" "grep -q 'CLI_PURPOSES' settings_registry.py && grep -q 'sreg.CLI_PURPOSES' server.py"
chk "plan.* settings section"        "grep -q 'plan.deep_enabled' settings_registry.py && grep -q 'plan.recommend' settings_registry.py && grep -q 'plan.triage_samples' settings_registry.py && grep -q 'plan.critique_enabled' settings_registry.py && grep -q 'plan.stub' settings_registry.py"
# Step 2 — triage
chk "plan_engine module + triage"    "[ -f plan_engine.py ] && grep -q 'def triage_heuristics' plan_engine.py && grep -q 'def divergence' plan_engine.py && grep -q 'def recommend' plan_engine.py"
chk "family→deliverable_type map"    "grep -q 'FAMILY_DELIVERABLE_TYPE' plan_engine.py && grep -q '\"code_change\"' plan_engine.py"
chk "triage wired into wizard"       "grep -q 'def _wizard_triage' server.py && grep -q '_wizard_triage(instruction' server.py && grep -q 'out\[.triage.\] = triage' server.py"
chk "triage sampling non-blocking"   "grep -q 'def _triage_sample' server.py && grep -q 'threading.Thread(target=_triage_sample' server.py"
# Step 4 — session backend + templates + hygiene
chk "spec templates + stub"          "grep -q 'SPEC_TEMPLATES' plan_engine.py && grep -q 'def stub_turn' plan_engine.py && grep -q 'def render_spec_md' plan_engine.py"
chk "plan session endpoints"         "grep -q '/api/plan/sessions' server.py && grep -q '/api/plan/sessions/{sid}/turn' server.py && grep -q '/api/plan/sessions/{sid}/draft' server.py && grep -q '/api/plan/sessions/{sid}/critique' server.py && grep -q '/api/plan/sessions/{sid}/attach' server.py"
chk "B7 no-block: model work off-loop" "grep -q 'run_in_threadpool(_plan_run_turn' server.py && grep -q 'run_in_threadpool(_plan_draft_raw' server.py && grep -q 'run_in_threadpool(_ev.run_plan_critique' server.py"
chk "plan.stub short-circuits turns" "grep -q \"plan.stub\" server.py && grep -q 'def stub_plan' plan_engine.py"
chk "session hygiene sweep (+drafted)" "grep -q 'def sweep_stale_plan_sessions' server.py && grep -q 'sweep_stale_plan_sessions' scheduler.py && grep -q \"status IN ('active','drafted')\" server.py"
# Step 6 — draft
chk "draft seeds spec block"         "grep -q 'spec_block: str' server.py && grep -q 'SPEC CONTRACT' server.py && grep -q 'def _plan_draft_raw' server.py"
# Step 7 — validators + premortem (external model, frontier gate)
chk "structural validators"          "grep -q 'def _validate_plan' server.py && grep -q 'not covered by any task' server.py"
chk "premortem external + frontier gate" "grep -q 'def run_plan_critique' evals.py && grep -q 'def spec_model_for' evals.py && grep -q 'with _FRONTIER_GATE' evals.py"
chk "premortem parse + advisory"     "grep -q 'def parse_plan_critique' evals.py && grep -q 'PLAN_JSON_BEGIN' evals.py"
# Step 8 — spec travels downstream
chk "spec attach (SPEC.md+spec.json)" "grep -q 'def _write_session_spec' server.py && grep -q 'SPEC.md' server.py && grep -q \"status='created'\" server.py"
chk "spec → critic context"          "grep -q 'spec_ctx' evals.py && grep -q '\"spec\": spec_ctx' evals.py"
chk "spec → judge (JUDGE_SPEC)"       "grep -q 'JUDGE_SPEC' evals.py && grep -q 'JUDGE_SPEC' ../setup/bin/cjudge && grep -q 'JUDGE_SPEC' \$HOME/.local/bin/cjudge"
chk "replan seeds original spec"     "grep -q 'def _workflow_spec_md' server.py && grep -q 'ORIGINAL SPEC' server.py"
# Step 3/5 — UI
chk "deep plan UI"                   "grep -q 'function startDeepPlan' static/app.js && grep -q 'function deepPlanModal' static/app.js && grep -q 'function deepPlanRunCritique' static/app.js && grep -q 'function deepPlanRecommendModal' static/app.js"
chk "premortem annotations in editor" "grep -q 'planEd.annotations' static/app.js && grep -q 'planEd.planSessionId' static/app.js"
chk "Step7 re-run premortem + diff flags" "grep -q 'wfRerunCritique' static/app.js && grep -q 'function planEdComputeDiff' static/app.js && grep -q 'planEd.diff' static/app.js"
# Step 7b — revise loop (findings → corrected plan, 2026-07-12)
chk "revise loop backend"            "grep -q 'def plan_session_revise' server.py && grep -q 'def _plan_revise_raw' server.py && grep -q 'def _distribute_criteria' server.py && grep -q 'def stub_revise' plan_engine.py"
chk "revise loop UI + auto round"    "grep -q 'function deepPlanRevise' static/app.js && grep -q 'function deepPlanRenderQuestions' static/app.js && grep -q 'wfRevisePlan' static/app.js && grep -q 'autoRevised' static/app.js"
chk "validator fuzzy coverage + common-token guard" "grep -q 'def _criterion_covered' server.py && grep -q 'def _sig_toks' server.py && grep -q 'plan.auto_revise' settings_registry.py"
# repo grounding — the plan is a CHANGE to existing work (2026-07-12)
chk "deep plan repo grounding"       "grep -q 'def _plan_repo_block' server.py && grep -q 'plan_sessions ADD COLUMN repo_path' database.py && grep -q 'context=_plan_repo_block' server.py && grep -q 'dpRepoChip' static/app.js"
# Step 9 — JARVIS framing (rule 12)
chk "JARVIS knows Deep Plan (+attach)" "grep -q 'DEEP PLAN:' server.py && grep -q '/api/plan/sessions' server.py && grep -q 'sessions/ID/attach' server.py"
# Step 10 — gates
chk "deep plan e2e gate exists"      "[ -f scripts/verify_deep_plan_e2e.py ]"
chk "deep plan UI gate exists"       "[ -f scripts/verify_deep_plan_ui.py ]"

echo ""
echo -e "${YELLOW}═══ 21. APPENDIX C — cost ledger + escalation + rotation-readiness ═══${NC}"
# C3 — full-cost ledger + JSON-envelope unwrap (contract C-8)
chk "C3: frontier ledger table + task cols" "grep -q 'frontier_ledger' database.py && grep -q '\"frontier_tokens\"' database.py && grep -q '\"frontier_cost_usd\"' database.py"
chk "C3: price table + ledger helpers" "grep -q 'MODEL_PRICES_SEED' database.py && grep -q 'def model_prices' database.py && grep -q 'def task_cost_ledger' database.py && grep -q 'def record_frontier_run' database.py"
chk "C3: price table seeded + setting" "grep -q 'cost.model_prices' database.py && grep -q 'cost.model_prices' settings_registry.py"
chk "C3: envelope unwrap before parse (C-8)" "grep -q 'def _unwrap_frontier_output' evals.py && grep -q '_unwrap_frontier_output(r.stdout' evals.py"
chk "C3: usage_sink plumbed to cmds"  "grep -q 'usage_sink' evals.py && grep -q 'def record_frontier_spend' evals.py"
chk "C3: cverify/cjudge emit JSON envelope" "grep -q -- '--output-format json' ../setup/bin/cverify && grep -q -- '--output-format json' ../setup/bin/cjudge && grep -q -- '--output-format json' \$HOME/.local/bin/cverify && grep -q -- '--output-format json' \$HOME/.local/bin/cjudge"
chk "C3: spend recorded in critic+judge threads" "grep -q 'record_frontier_spend' server.py"
chk "C3: ledger endpoints"            "grep -q '/api/tasks/{task_id}/ledger' server.py && grep -q '/api/workflows/{workflow_id}/ledger' server.py"
# C1a — escalation_model registry purpose (spec_model already landed with Deep Plan)
chk "C1a: escalation_model purpose"   "grep -q 'escalation_model' database.py && grep -q 'escalation_model' settings_registry.py && grep -q 'def escalation_model_for' evals.py"
chk "C1a: purpose seeded + migrated"  "grep -q \"'escalation_model', 'mdl-opus48'\\|('escalation_model', \\\"mdl-opus48\\\")\\|escalation_model.*mdl-opus48\" database.py && grep -q 'migrated.escalation_model' database.py"
chk "C1a: purpose is CLI-route in UI" "grep -q 'escalation_model:' static/app.js"
# C1c — escalated rework (setting-gated super.escalation)
chk "C1c: cexec vendored + installed" "[ -f ../setup/bin/cexec ] && [ -f \$HOME/.local/bin/cexec ] && grep -q -- '--output-format json' ../setup/bin/cexec"
chk "C1c: escalation runner + dossier" "grep -q 'def run_escalation_cmd' evals.py && grep -q 'def build_escalation_dossier' evals.py && grep -q 'with _FRONTIER_GATE' evals.py"
chk "C1c: escalation endpoint + thread" "grep -q '/api/tasks/{task_id}/escalate' server.py && grep -q 'def _escalation_thread' server.py"
chk "C1c: loop hook (REWRITE + round-cap)" "grep -q 'def _try_escalate_super' loop_engine.py && grep -q '_has_open_criticals' loop_engine.py && grep -q '_try_escalate_super(t, trig, per_task, .rewrite.)' loop_engine.py && grep -q 'esc == .wait.' loop_engine.py"
# bugfix campaign 2026-07-12 [21]: an 'interrupted' judge must clear judge_ts,
# or judged_this_version stays true and the auto-judge never re-runs after the
# quota window / a restart. Both writers (deferral branch + boot heal) pinned.
# (anchored per writer — a bare count was satisfiable by the explanatory comment)
chk "[21]: interrupted judge clears judge_ts (both writers)" "grep -q 'judge_ts=NULL WHERE id=?' server.py && grep -q 'judge_ts=NULL \"' server.py"
# bugfix campaign 2026-07-12 D3 [0][1][2]: the restart drain must see escalated
# reworks (busy count + boot heal) and the worker must keep harvesting/waiting
# on orphans while dispatch is paused; prepare/cancel are lock-serialized.
chk "D3b: drain busy + boot heal cover 'escalating'" "grep -q \"critic_verdict IN ('running','escalating')\" server.py && grep -q 'escalation orphaned by restart' server.py"
chk "D3a: drain-harvest resume path in the worker" "grep -q 'dispatch_on or mode == .resume.' worker.py && grep -q 'orphan_run_state(task) != .finished.' worker.py"
chk "D3c: prepare/cancel serialized" "grep -q '_RESTART_PREP_LOCK = threading.Lock()' server.py && [ \$(grep -c 'with _RESTART_PREP_LOCK' server.py) -ge 2 ]"
chk "restart-prep gate committed" "[ -f scripts/verify_restart_prep_e2e.py ]"
# D6/[R1]: loop_config writes are serialized — the lock + the locked mutate
# exist and the escalation thread routes through them (no bare locate/save).
chk "D6: cfg lock + locked mutate"   "grep -q '_CFG_LOCK = threading.RLock()' loop_engine.py && grep -q 'def _mutate_super_cfg' loop_engine.py && grep -q 'def _mutate_cfg_trigger' loop_engine.py && grep -q '_mutate_super_cfg(task_id' server.py && grep -q '_CFG_LOCK' server.py"
# Final-review F1/F2: the client-facing loop_config writers (task/workflow
# PATCH + replan apply) go through the locked graft/fresh-read paths too.
chk "F2: PATCH loop_config grafts"   "grep -q 'def _write_loop_cfg_grafted' server.py && [ \$(grep -c '_write_loop_cfg_grafted' server.py) -ge 3 ]"
# Final-review F5: the _CFG_LOCK-taking helpers are pinned in the async-
# blocking gate's BLOCKING_NAMES, so a direct on-loop call fails verify.sh
# (section 2's 'no blocking calls in async handlers' runs that checker).
chk "F5: cfg helpers in async gate"  "grep -q '_sync_super_result_loop' scripts/check_async_blocking.py && grep -q '_regen_loop_for_profile' scripts/check_async_blocking.py && grep -q '_write_loop_cfg_grafted' scripts/check_async_blocking.py && grep -q '_inherit_super_result' scripts/check_async_blocking.py"
# [R2]: the watchdog counts lane deaths toward the circuit breaker ONLY
# outside the post-boot grace window (clean restarts retired the fleet).
chk "R2: watchdog boot grace"        "grep -q '_BOOT_TS = time.time()' watchdog.py && grep -q 'BOOT_GRACE_S' watchdog.py && grep -q 'boot_respawn' watchdog.py"
chk "C1c: setting-gated + bounded"    "grep -q 'super.escalation' settings_registry.py && grep -q 'super.escalation_max' settings_registry.py && grep -q 'super.escalation' database.py"
chk "C1c: escalation spend to ledger" "grep -q '\"escalation\"' server.py && grep -q 'record_frontier_spend' server.py"
# C1b — critic patch field (CriticGPT: critic-proposed diff, executor applies verbatim)
chk "C1b: cverify emits optional patch" "grep -q '\\\\\"patch\\\\\"' ../setup/bin/cverify && grep -q 'unified-diff hunk' ../setup/bin/cverify && grep -q -- '--output-format json' \$HOME/.local/bin/cverify"
chk "C1b: parse captures patch"       "grep -q '\"patch\": _clip(f.get(\"patch\")' evals.py"
chk "C1b: patch column + retry re-attaches" "grep -q 'ADD COLUMN patch TEXT' database.py && grep -q 'Apply this patch verbatim' server.py"
# C2 — registry-only model references (rotation readiness)
chk "C2: centralized fallback map + helpers" "grep -q 'FALLBACK_MODELS = {' database.py && grep -q 'def fallback_model' database.py && grep -q 'def worker_fallback_models' database.py"
chk "C2: no hardcoded model literal in routing fallbacks" "! grep -qE 'or \"glm-5\.[12]\"|or \"glm-4\.5-air\"' server.py && grep -q 'db.fallback_model(' server.py && grep -q 'db.worker_fallback_models()' server.py"
chk "C2: dispatch DEFAULT_MODEL via registry" "grep -q 'DEFAULT_MODEL = db.fallback_model' hermes_dispatch.py"
chk "C2: L4 fingerprint spans new judgment tiers" "grep -q 'spec_model' routing.py && grep -q 'escalation_model' routing.py"
# rule 3 — Eco model-tier floor (was P2-staged, completed with C2)
chk "rule3: Eco model floor derived + applied" "grep -q '\"eco\": \"easy\"' autopilot.py && grep -q 'Eco model floor' server.py && grep -q 'model_floor: str' server.py"
# C5 — escalation-threshold settings
chk "C5: escalation trigger threshold setting" "grep -q 'super.escalation_trigger' settings_registry.py && grep -q 'def _escalation_mode' loop_engine.py && grep -q 'rewrite_or_cap' loop_engine.py"
# rule 12 — JARVIS framing documents the new OS surface (ledger + escalated rework)
chk "rule12: JARVIS knows the cost ledger + escalated rework" "grep -q 'COST LEDGER (Appendix C3)' server.py && grep -q 'ESCALATED REWORK (Appendix C1c)' server.py && grep -q '/api/tasks/ID/escalate' server.py"

echo ""
echo -e "${YELLOW}══════════════════════════════════════${NC}"
if [ $FAIL -eq 0 ]; then
  echo -e "  ${GREEN}ALL CHECKS PASSED: $PASS/$PASS${NC}"
  exit 0
else
  echo -e "  ${RED}$FAIL FAILED, $PASS passed${NC}"
  exit 1
fi
