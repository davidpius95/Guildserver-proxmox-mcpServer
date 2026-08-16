#!/bin/sh
# tailscale-watchdog.sh  (v2 -- 2026-08-16)
#
# Restarts tailscaled ONLY when it is genuinely stuck out of contact with the
# coordination server for a sustained period.
#
# v1 (2026-08-09) restarted on *any* non-empty .Health array. That was wrong:
# Tailscale reports transient and purely cosmetic warnings there (DERP hiccups,
# "SSH enabled but ACLs don't allow anyone"), all of which it recovers from on
# its own. The result was 1200-3100 restarts/day per host -- tailscaled never
# stayed up long enough to hold a session, so every host looked permanently
# offline to its peers. The watchdog was causing the outage it was meant to fix.
#
# v2 rules:
#   - only specific "lost the control connection" warnings count as failure
#   - failure must persist for NEED_FAILS consecutive checks before acting
#   - at most one restart per MIN_INTERVAL seconds
#
# See memory: tailscale-coordination-flap.md

LOG=/var/log/tailscale-watchdog.log
STATE=/var/lib/tailscale-watchdog
FAILFILE="$STATE/consecutive_failures"
LASTFILE="$STATE/last_restart"
KEYFILE=/etc/pve/priv/tailscale/authkey

NEED_FAILS=3      # consecutive bad checks required (x5min timer = ~15 min)
MIN_INTERVAL=1800 # never restart more than once per 30 minutes

mkdir -p "$STATE"
log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" >> "$LOG"; }

now=$(date +%s)
fails=$(cat "$FAILFILE" 2>/dev/null || echo 0)
case "$fails" in ''|*[!0-9]*) fails=0 ;; esac

STATUS_JSON=$(tailscale status --json 2>/dev/null)

if [ -z "$STATUS_JSON" ]; then
    BAD=1; REASON="tailscale CLI unreachable (daemon down?)"
else
    BAD=$(echo "$STATUS_JSON" | python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(1); sys.exit()

state = d.get("BackendState", "")
# Hard-broken backend states.
if state in ("NeedsLogin", "NeedsMachineAuth", "Stopped", "NoState"):
    print(1); sys.exit()
if state != "Running":
    print(1); sys.exit()

# Running: only these health warnings mean we actually lost the control plane.
# Everything else (DERP blips, the cosmetic SSH/ACL notice, etc.) is ignored --
# tailscaled recovers from those without help.
FATAL = (
    "unable to connect to the tailscale coordination server",
    "not in map poll",
    "control server",
    "you are logged out",
)
health = [str(h).lower() for h in (d.get("Health") or [])]
print(1 if any(f in h for h in health for f in FATAL) else 0)
' 2>/dev/null)
    case "$BAD" in ''|*[!0-9]*) BAD=0 ;; esac
    REASON="BackendState/health indicates lost coordination-server session"
fi

if [ "$BAD" = "0" ]; then
    # Healthy. Clear the counter silently; keep the log signal-only.
    [ "$fails" -ne 0 ] && : > "$FAILFILE"
    exit 0
fi

fails=$((fails + 1))
echo "$fails" > "$FAILFILE"

if [ "$fails" -lt "$NEED_FAILS" ]; then
    log "unhealthy ($fails/$NEED_FAILS): $REASON -- waiting, not restarting yet"
    exit 0
fi

last=$(cat "$LASTFILE" 2>/dev/null || echo 0)
case "$last" in ''|*[!0-9]*) last=0 ;; esac
since=$((now - last))
if [ "$since" -lt "$MIN_INTERVAL" ]; then
    log "unhealthy ($fails) but last restart was ${since}s ago (<${MIN_INTERVAL}s) -- holding off"
    exit 0
fi

log "unhealthy for $fails consecutive checks: $REASON -- restarting tailscaled"
systemctl restart tailscaled
echo "$now" > "$LASTFILE"
: > "$FAILFILE"
sleep 5

# Pods only: if a shared reusable key exists and we are genuinely logged out
# (not just a coordination-server hiccup), re-auth automatically -- same
# mechanism as the boot-time autojoin.sh, just also running on a timer.
# No-op on hosts without the keyfile.
if [ -f "$KEYFILE" ]; then
    if tailscale status 2>/dev/null | head -1 | grep -q "Logged out"; then
        log "logged out with keyfile present -- re-authenticating via $KEYFILE"
        tailscale up --auth-key="file:$KEYFILE" --ssh --accept-dns=false
    fi
fi
