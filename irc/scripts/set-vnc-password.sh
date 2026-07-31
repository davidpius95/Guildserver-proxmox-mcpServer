#!/usr/bin/env bash
# Set (or regenerate) the noVNC password and PROVE it took.
#
#   pct exec 911 -- bash /root/irc/scripts/set-vnc-password.sh            # random
#   pct exec 911 -- env VNC_PASSWORD=hunter22 bash .../set-vnc-password.sh
#
# Why this exists: the install script wrote the password blob and the plaintext
# record in two separate steps, and they drifted apart — the record said one
# thing and the server accepted another. This writes both and then verifies by
# re-encoding, so a mismatch is impossible to miss.
set -euo pipefail

IRC_USER="${IRC_USER:-irc-user}"
IRC_HOME="/home/${IRC_USER}"
PWFILE="${IRC_HOME}/.vnc/passwd"
RECORD=/root/irc-vnc-password

# The RFB protocol truncates to 8 characters. Generate exactly 8 so what is
# recorded is exactly what the server will accept — no silent truncation.
if [ -n "${VNC_PASSWORD:-}" ]; then
  if [ "${#VNC_PASSWORD}" -gt 8 ]; then
    echo "NOTE: VNC truncates to 8 chars; '${VNC_PASSWORD}' will act as '${VNC_PASSWORD:0:8}'" >&2
    VNC_PASSWORD="${VNC_PASSWORD:0:8}"
  fi
else
  VNC_PASSWORD="$(head -c 64 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c1-8)"
fi

install -d -o "$IRC_USER" -g "$IRC_USER" -m 700 "${IRC_HOME}/.vnc"
printf '%s' "$VNC_PASSWORD" | vncpasswd -f > "$PWFILE"
chown "$IRC_USER:$IRC_USER" "$PWFILE"
chmod 600 "$PWFILE"
printf '%s\n' "$VNC_PASSWORD" > "$RECORD"
chmod 600 "$RECORD"

# Verify. VNC obfuscation uses a fixed key, so the same plaintext always encodes
# to the same 8 bytes — a byte comparison is a real check, not a formality.
tmp="$(mktemp)"
printf '%s' "$VNC_PASSWORD" | vncpasswd -f > "$tmp"
if ! cmp -s "$PWFILE" "$tmp"; then
  rm -f "$tmp"
  echo "FAILED: password file does not match '${VNC_PASSWORD}'" >&2
  exit 1
fi
rm -f "$tmp"

echo "Password set and verified: ${VNC_PASSWORD}"
echo "Restarting session to clear TigerVNC's connection blacklist ..."
systemctl restart irc-desktop.service
echo "Done."
