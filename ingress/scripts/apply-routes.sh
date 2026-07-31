#!/usr/bin/env bash
# Rebuild /etc/caddy/caddy.json from the route files and hot-load it.
#
# Source of truth: /etc/caddy/routes/<sub>.json  (one Caddy route object each)
#
# This writes the FULL config to disk AND pushes it to the admin API, which is
# what makes routes survive a reboot: the systemd unit starts Caddy with
# --config /etc/caddy/caddy.json, so the on-disk file is always the live set.
# (The old admin-API-delta approach lost routes on restart.)
#
# Run as root INSIDE the ingress container.
set -euo pipefail

ROUTES_DIR="${ROUTES_DIR:-/etc/caddy/routes}"
CONFIG="${CONFIG:-/etc/caddy/caddy.json}"
ADMIN="${CADDY_ADMIN:-http://127.0.0.1:2019}"

mkdir -p "$ROUTES_DIR"

# Collect every route file into one array (empty array if none).
# NB: don't pipe `cat glob | jq -s` here — under `set -o pipefail` an empty glob
# makes cat fail while jq still prints "[]", so a `|| echo '[]'` fallback would
# concatenate two arrays and produce invalid JSON.
shopt -s nullglob
route_files=("$ROUTES_DIR"/*.json)
if [ ${#route_files[@]} -eq 0 ]; then
  routes='[]'
else
  routes="$(jq -s '.' "${route_files[@]}")"
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

jq -n --argjson routes "$routes" '{
  admin: { listen: "127.0.0.1:2019" },
  apps: {
    http: {
      servers: {
        ingress: {
          listen: [":80"],
          automatic_https: { disable: true },
          routes: $routes
        }
      }
    }
  }
}' >"$tmp"

# Validate before we overwrite anything live.
caddy validate --config "$tmp" >/dev/null 2>&1 || {
  echo "ERROR: generated config failed validation; leaving current config alone" >&2
  exit 1
}

install -m 0644 "$tmp" "$CONFIG"

# Hot-load. If Caddy isn't up yet (e.g. first install), that's fine — it will
# read the file we just wrote when it starts.
if curl -fsS -m 5 -X POST "${ADMIN}/load" \
     -H 'Content-Type: application/json' \
     --data-binary "@${CONFIG}" >/dev/null 2>&1; then
  echo "applied $(jq 'length' <<<"$routes") route(s) (live)"
else
  echo "applied $(jq 'length' <<<"$routes") route(s) (written to disk; Caddy not running)"
fi
