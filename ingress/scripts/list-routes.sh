#!/usr/bin/env bash
# Show the configured subdomain -> backend routes.
#
# Usage: ./list-routes.sh
#
# Reads the on-disk source of truth (which is also what Caddy is running, since
# add/remove regenerate and hot-load it).
#
# Env overrides:
#   ROUTES_DIR  (default: /etc/caddy/routes)
set -euo pipefail

ROUTES_DIR="${ROUTES_DIR:-/etc/caddy/routes}"

shopt -s nullglob
files=("${ROUTES_DIR}"/*.json)
if [ ${#files[@]} -eq 0 ]; then
  echo "(no routes configured)"
  exit 0
fi

jq -r '"\(.match[0].host[0])  ->  \(.handle[0].upstreams[0].dial)"' "${files[@]}" | sort
