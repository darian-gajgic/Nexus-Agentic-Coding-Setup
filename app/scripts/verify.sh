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
chk "engine detects, never rewrites" "! grep -E 'replan/(draft|apply)' loop_engine.py | grep -q ."
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

echo ""
echo -e "${YELLOW}══════════════════════════════════════${NC}"
if [ $FAIL -eq 0 ]; then
  echo -e "  ${GREEN}ALL CHECKS PASSED: $PASS/$PASS${NC}"
  exit 0
else
  echo -e "  ${RED}$FAIL FAILED, $PASS passed${NC}"
  exit 1
fi
