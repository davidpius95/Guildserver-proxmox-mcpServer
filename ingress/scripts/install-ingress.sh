#!/usr/bin/env bash
# Install Caddy inside the ingress LXC (Debian or Ubuntu).
# Run as root INSIDE the container.
#
# NOTE: cloudflared is deliberately NOT installed here. The cluster already has
# one dashboard/token-managed connector (on the PDM VM) whose wildcard public
# hostname *.guildserver.io points at this proxy. A second connector would just
# be another thing to keep alive.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y curl gnupg lsb-release ca-certificates apt-transport-https \
  debian-keyring debian-archive-keyring jq

install -d -m 0755 /usr/share/keyrings

# --- Caddy (official cloudsmith repo; same list works on Debian and Ubuntu) ---
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  > /etc/apt/sources.list.d/caddy-stable.list

apt-get update
apt-get install -y caddy

# The packaged unit runs a Caddyfile; we use our own JSON config instead.
systemctl disable --now caddy || true

install -D -m 0644 /root/ingress/caddy/caddy-ingress.service /etc/systemd/system/caddy-ingress.service
install -d -m 0755 /etc/caddy/routes
install -d -m 0755 /var/lib/caddy && chown caddy:caddy /var/lib/caddy

# Install the route management scripts to a stable location.
# add-route/remove-route call "${here}/apply-routes.sh", where `here` resolves to
# /usr/local/bin — so apply-routes.sh MUST keep its .sh name here.
install -D -m 0755 /root/ingress/scripts/apply-routes.sh  /usr/local/bin/apply-routes.sh
install -D -m 0755 /root/ingress/scripts/add-route.sh     /usr/local/bin/add-route
install -D -m 0755 /root/ingress/scripts/remove-route.sh  /usr/local/bin/remove-route
install -D -m 0755 /root/ingress/scripts/list-routes.sh   /usr/local/bin/list-routes
ln -sf /usr/local/bin/apply-routes.sh /usr/local/bin/apply-routes

# Generate the initial (possibly empty) config before starting Caddy.
/usr/local/bin/apply-routes.sh

systemctl daemon-reload
systemctl enable --now caddy-ingress

echo
echo "Caddy is running (admin API on 127.0.0.1:2019, proxy on :80)."
echo "Routes live in /etc/caddy/routes/ and are re-applied automatically on boot."
