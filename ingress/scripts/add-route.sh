#!/usr/bin/env bash
# Add (or update) a subdomain -> backend route.
#
# Usage:
#   ./add-route.sh <subdomain> <backend-host:port>
#
# Example:
#   ./add-route.sh jellyfin 192.168.8.244:8096
#     -> https://jellyfin.guildserver.io  is served from  192.168.8.244:8096
#
# No Cloudflare API call is needed: the tunnel already wildcards *.guildserver.io
# onto this proxy, so a new subdomain is purely a local Caddy route.
#
# Run as root INSIDE the ingress container (or via ../route from your Mac).
#
# Env overrides:
#   DOMAIN      (default: guildserver.io)
#   ROUTES_DIR  (default: /etc/caddy/routes)
set -euo pipefail

DOMAIN="${DOMAIN:-guildserver.io}"
ROUTES_DIR="${ROUTES_DIR:-/etc/caddy/routes}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sub="${1:?usage: add-route.sh <subdomain> <backend-host:port>}"
backend="${2:?usage: add-route.sh <subdomain> <backend-host:port>}"

# Basic sanity so a typo can't write a nonsense route.
[[ "$sub" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] \
  || { echo "ERROR: '$sub' is not a valid subdomain label" >&2; exit 2; }
[[ "$backend" =~ ^[A-Za-z0-9._-]+:[0-9]+$ ]] \
  || { echo "ERROR: backend must be host:port (got '$backend')" >&2; exit 2; }

host="${sub}.${DOMAIN}"
mkdir -p "$ROUTES_DIR"

# X-Forwarded-Proto is pinned to https because every request reaches us through
# the Cloudflare tunnel, where TLS was already terminated at the edge. Without
# this, apps behind the proxy (Jellyfin included) build http:// absolute URLs
# and can redirect-loop.
jq -n \
  --arg id "route-${sub}" \
  --arg host "$host" \
  --arg backend "$backend" \
  '{
    "@id": $id,
    match: [{ host: [$host] }],
    handle: [{
      handler: "reverse_proxy",
      upstreams: [{ dial: $backend }],
      flush_interval: -1,
      headers: {
        request: {
          set: {
            "X-Forwarded-Proto": ["https"],
            "X-Forwarded-Host": ["{http.request.host}"]
          }
        }
      }
    }]
  }' >"${ROUTES_DIR}/${sub}.json"

"${here}/apply-routes.sh"
echo "routed  https://${host}  ->  ${backend}"
