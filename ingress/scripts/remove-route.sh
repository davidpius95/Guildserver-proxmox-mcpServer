#!/usr/bin/env bash
# Remove a subdomain route.
#
# Usage:
#   ./remove-route.sh <subdomain>
#
# Example:
#   ./remove-route.sh app1        # tears down app1.guildserver.io
#
# Run as root INSIDE the ingress container (or via ../route from your Mac).
#
# Env overrides:
#   ROUTES_DIR  (default: /etc/caddy/routes)
set -euo pipefail

ROUTES_DIR="${ROUTES_DIR:-/etc/caddy/routes}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sub="${1:?usage: remove-route.sh <subdomain>}"
f="${ROUTES_DIR}/${sub}.json"

if [ -f "$f" ]; then
  rm -f "$f"
  "${here}/apply-routes.sh"
  echo "removed  ${sub}.${DOMAIN:-guildserver.io}"
else
  echo "no route found for ${sub} (nothing to do)"
fi
