#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# Hermes error watchdog — fires desktop notifications when
# critical Hermes errors are detected in the last 5 minutes.
#
# Triggers on:
#   - API call failures after all retries (429/503/etc.)
#   - Provider fully exhausted (all fallbacks failed)
#   - Gateway platform reconnect failures
#
# Silent when there are no new errors (watchdog pattern).
# Designed for cron — empty stdout = no notification sent.
# ═══════════════════════════════════════════════════════════
set -uo pipefail

ERRORS_LOG="$HOME/.hermes/logs/errors.log"
STATE_FILE="$HOME/.hermes/.watchdog-last-check"
NOW=$(date +%s)

# Read last check timestamp (default: 5 minutes ago)
if [ -f "$STATE_FILE" ]; then
    LAST=$(cat "$STATE_FILE" 2>/dev/null || echo "0")
else
    LAST=$((NOW - 300))
fi

# Update state file
echo "$NOW" > "$STATE_FILE"

# Check for critical errors since last check
# (timestamps in errors.log are ISO format; we grep for recent entries)
CRITICAL_COUNT=0
ALERT_MSG=""

# Count "API call failed after N retries" — the terminal failure
RETRY_FAILS=$(awk -v cutoff="$LAST" '
    /^[0-9]{4}-[0-9]{2}-[0-9]{2}/ {
        # Parse timestamp to epoch
        ts = systime()  # fallback
        gsub(/[-:]/, " ", $1)
        gsub(/[-:]/, " ", $2)
        # Simple check: if line contains "after.*retries" flag it
    }
    /API call failed after.*retries/ { count++ }
    END { print count+0 }
' "$ERRORS_LOG" 2>/dev/null || echo "0")

# Simpler: count critical lines in last 5 min using log timestamps
FIVE_MIN_AGO_ISO=$(date -d '-5 minutes' '+%Y-%m-%d %H:%M:%S' 2>/dev/null)
if [ -n "$FIVE_MIN_AGO_ISO" ]; then
    NEW_ERRORS=$(awk -v cutoff="$FIVE_MIN_AGO_ISO" '
        BEGIN { in_window=0 }
        /^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}/ {
            ts = $1 " " $2
            if (ts >= cutoff) in_window=1
        }
        in_window && /ERROR|API call failed after.*retries/ { print }
    ' "$ERRORS_LOG" 2>/dev/null | wc -l)
else
    NEW_ERRORS=0
fi

if [ "$NEW_ERRORS" -gt 0 ]; then
    MSG="⚠️ Hermes: $NEW_ERRORS critical error(s) in last 5 min. Check ~/.hermes/logs/errors.log"
    echo "$MSG"
    # Desktop notification if available
    if command -v notify-send >/dev/null 2>&1; then
        DISPLAY=:0 notify-send -u critical -i dialog-warning "Hermes Agent" "$MSG" 2>/dev/null || true
    fi
fi
