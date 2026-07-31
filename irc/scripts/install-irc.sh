#!/usr/bin/env bash
# Install HexChat on a persistent X session, reachable over noVNC in a browser.
# Run INSIDE the IRC LXC:  pct exec 911 -- bash /root/irc/scripts/install-irc.sh
#
# Layout:
#   Xtigervnc :1  -> 127.0.0.1:5901   (never leaves the container)
#   websockify    -> 0.0.0.0:6080     (noVNC web UI; this is what you connect to)
#   openbox + hexchat inside the session, restarted by systemd if they die
#
# The X session runs continuously, so HexChat stays connected to IRC whether or
# not a browser is attached — it is its own bouncer.
set -euo pipefail

IRC_USER="${IRC_USER:-irc-user}"
IRC_HOME="/home/${IRC_USER}"
GEOMETRY="${GEOMETRY:-1600x900}"
VNC_PORT=5901
WEB_PORT="${WEB_PORT:-6080}"

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  tigervnc-standalone-server tigervnc-common tigervnc-tools \
  openbox xterm dbus-x11 \
  novnc websockify \
  fonts-dejavu-core ca-certificates \
  procps psmisc >/dev/null

# HexChat: upstream development ceased in Feb 2024, so it may have been dropped
# from newer archives. Try apt first, fall back to the still-updated Flathub build.
HEXCHAT_CMD=""
if apt-get install -y --no-install-recommends hexchat >/dev/null 2>&1; then
  HEXCHAT_CMD="/usr/bin/hexchat"
  echo "==> HexChat installed from apt: $(dpkg-query -W -f='${Version}' hexchat 2>/dev/null)"
else
  echo "==> hexchat not in the archive; falling back to Flatpak (Flathub)"
  apt-get install -y --no-install-recommends flatpak >/dev/null
  flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
  flatpak install -y --noninteractive flathub io.github.Hexchat
  HEXCHAT_CMD="/usr/bin/flatpak run io.github.Hexchat"
fi

echo "==> Creating ${IRC_USER}"
id -u "$IRC_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$IRC_USER"
install -d -o "$IRC_USER" -g "$IRC_USER" -m 700 "${IRC_HOME}/.vnc"
install -d -o "$IRC_USER" -g "$IRC_USER" -m 755 "${IRC_HOME}/.config/openbox"
install -d -o "$IRC_USER" -g "$IRC_USER" -m 755 "${IRC_HOME}/.config/hexchat"

echo "==> Setting VNC password"
# NOTE: the RFB VncAuth password is truncated to 8 characters by the protocol.
# This is the only auth in front of the session, which is why the service binds
# to the LAN and is NOT routed publicly without Cloudflare Access in front.
if [ ! -s "${IRC_HOME}/.vnc/passwd" ]; then
  # Read a fixed number of bytes first: piping /dev/urandom straight into
  # `head -c` SIGPIPEs `tr`, which `set -o pipefail` turns into a hard failure.
  VNC_PASSWORD="${VNC_PASSWORD:-$(head -c 64 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c1-8)}"
  printf '%s\n' "$VNC_PASSWORD" | vncpasswd -f > "${IRC_HOME}/.vnc/passwd"
  chown "$IRC_USER:$IRC_USER" "${IRC_HOME}/.vnc/passwd"
  chmod 600 "${IRC_HOME}/.vnc/passwd"
  printf '%s\n' "$VNC_PASSWORD" > /root/irc-vnc-password
  chmod 600 /root/irc-vnc-password
  echo "    generated: ${VNC_PASSWORD}   (also saved to /root/irc-vnc-password)"
else
  echo "    existing password kept"
fi

echo "==> Openbox autostart"
cat > "${IRC_HOME}/.config/openbox/autostart" <<EOF
# Keep HexChat running for the life of the session; relaunch if it is closed.
while :; do
  ${HEXCHAT_CMD}
  sleep 2
done &
EOF
chown "$IRC_USER:$IRC_USER" "${IRC_HOME}/.config/openbox/autostart"

echo "==> Session launcher"
cat > /usr/local/bin/irc-session <<EOF
#!/usr/bin/env bash
# Start Xtigervnc bound to loopback, wait for it, then run the desktop session.
set -euo pipefail
export DISPLAY=:1
export HOME="${IRC_HOME}"

/usr/bin/Xtigervnc :1 \\
  -geometry ${GEOMETRY} -depth 24 \\
  -rfbport ${VNC_PORT} \\
  -rfbauth "${IRC_HOME}/.vnc/passwd" \\
  -SecurityTypes VncAuth \\
  -localhost \\
  -BlacklistThreshold=100 -BlacklistTimeout=30 \\
  -desktop irc &
XPID=\$!

for _ in \$(seq 1 50); do
  [ -S /tmp/.X11-unix/X1 ] && break
  sleep 0.2
done
[ -S /tmp/.X11-unix/X1 ] || { echo "Xtigervnc failed to start" >&2; kill \$XPID 2>/dev/null; exit 1; }

exec dbus-run-session -- openbox-session
EOF
chmod 755 /usr/local/bin/irc-session

echo "==> systemd units"
cat > /etc/systemd/system/irc-desktop.service <<EOF
[Unit]
Description=HexChat on a persistent X session (Xtigervnc + openbox)
After=network-online.target
Wants=network-online.target
# Pull the proxy up with the display. PartOf on the other side handles restarts,
# but it cannot start a unit that is already stopped — this covers that case.
Wants=irc-novnc.service

[Service]
Type=simple
User=${IRC_USER}
ExecStart=/usr/local/bin/irc-session
# Reap the entire session on stop. The openbox autostart backgrounds a HexChat
# respawn loop; if it survives a restart it reconnects to the new :1 display and
# you get two HexChats fighting over the same nick. PAMName=login is deliberately
# NOT set here — it moves processes into a PAM session scope outside the service
# cgroup, which is exactly what let the loop escape.
KillMode=control-group
# Scoped to the X session's own processes. A blanket `pkill -u ${IRC_USER}` also
# takes out websockify, which runs as the same user. (pkill never signals itself,
# so listing Xtigervnc here is safe — unlike pgrep, which does match its own
# command line.)
ExecStopPost=-/usr/bin/pkill -9 -u ${IRC_USER} -f "Xtigervnc|openbox|hexchat|tint2|hsetroot"
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/irc-novnc.service <<EOF
[Unit]
Description=noVNC web front end for the IRC session
After=irc-desktop.service
# PartOf, not Requires: Requires propagates *stop* but not *restart*, so
# `systemctl restart irc-desktop` tore this down and left it down. PartOf
# propagates both, so the proxy follows the display it fronts.
PartOf=irc-desktop.service

[Service]
Type=simple
User=${IRC_USER}
ExecStart=/usr/bin/websockify --web /usr/share/novnc ${WEB_PORT} 127.0.0.1:${VNC_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now irc-desktop.service
sleep 3
systemctl enable --now irc-novnc.service

echo
echo "Done."
echo "  noVNC:  http://$(hostname -I | awk '{print $1}'):${WEB_PORT}/vnc.html"
echo "  status: systemctl status irc-desktop irc-novnc"
