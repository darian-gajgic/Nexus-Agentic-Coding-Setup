#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# NEXUS — VERIFY GATE
# Run this before any commit. Non-zero exit = DO NOT COMMIT.
# ═══════════════════════════════════════════════════════════
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

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
chk "video avatar in app.js"         "grep -q 'jAvatarVideo' static/app.js"
chk "lipsync clip fetch in app.js"   "grep -q 'jarvisFetchClip' static/app.js"
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
chk "JARVIS history ownership"       "grep -qE 'session_id != _jarvis_sid_for' server.py"
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

echo ""
echo -e "${YELLOW}══════════════════════════════════════${NC}"
if [ $FAIL -eq 0 ]; then
  echo -e "  ${GREEN}ALL CHECKS PASSED: $PASS/$PASS${NC}"
  exit 0
else
  echo -e "  ${RED}$FAIL FAILED, $PASS passed${NC}"
  exit 1
fi
