#!/usr/bin/env bash
# Make the session look like a desktop instead of a void, and pre-seed HexChat
# with Libera.Chat + OFTC so it connects on boot without touching the dialog.
#
# Run INSIDE the IRC LXC:  pct exec 911 -- bash /root/irc/scripts/customize.sh
#
# Safe to re-run. HexChat rewrites its config on exit, so this stops the session
# first — writing these files under a live HexChat would just get overwritten.
set -euo pipefail

IRC_USER="${IRC_USER:-irc-user}"
IRC_HOME="/home/${IRC_USER}"
NICK="${NICK:-guildserver}"

echo "==> Installing panel + wallpaper tools"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends tint2 hsetroot wmctrl >/dev/null

echo "==> Stopping session so HexChat cannot clobber the config on exit"
systemctl stop irc-desktop.service || true
sleep 1

install -d -o "$IRC_USER" -g "$IRC_USER" -m 755 "${IRC_HOME}/.config/tint2"
install -d -o "$IRC_USER" -g "$IRC_USER" -m 755 "${IRC_HOME}/.config/hexchat"

echo "==> Panel (tint2)"
cat > "${IRC_HOME}/.config/tint2/tint2rc" <<'EOF'
panel_items = TSC
panel_monitor = all
panel_position = bottom center horizontal
panel_size = 100% 30
panel_margin = 0 0
panel_padding = 6 2 6
panel_background_id = 1
panel_layer = bottom

# id 1 — panel
rounded = 0
border_width = 0
background_color = #12181f 100
border_color = #12181f 100

# id 2 — inactive task
rounded = 3
border_width = 0
background_color = #2a3644 100

# id 3 — active task
rounded = 3
border_width = 0
background_color = #3d5a7a 100

taskbar_mode = single_desktop
taskbar_padding = 2 0 2
taskbar_background_id = 0

task_text = 1
task_icon = 1
task_maximum_size = 220 24
task_padding = 6 2
task_background_id = 2
task_active_background_id = 3
task_font = Sans 9
task_font_color = #d6dee8 100
task_active_font_color = #ffffff 100

systray_padding = 4 2 4
systray_background_id = 0
systray_icon_size = 18

time1_format = %H:%M
time1_font = Sans 10
clock_font_color = #d6dee8 100
clock_padding = 8 0
clock_background_id = 0
EOF

echo "==> HexChat global config (nick: ${NICK})"
cat > "${IRC_HOME}/.config/hexchat/hexchat.conf" <<EOF
irc_nick1 = ${NICK}
irc_nick2 = ${NICK}_
irc_nick3 = ${NICK}__
irc_user_name = ${NICK}
irc_real_name = ${NICK}
gui_slist_skip = 1
gui_join_dialog = 0
gui_tray = 0
gui_win_state = 1
text_font = Monospace 11
EOF

echo "==> HexChat network list"
# Flag bits: 2=use global user info, 4=SSL, 8=autoconnect, 64=favourite.
#   Libera = 2+4+8+64 = 78  (connects on startup)
#   OFTC   = 2+4+64   = 70  (listed, does not autoconnect)
cat > "${IRC_HOME}/.config/hexchat/servlist.conf" <<'EOF'
v=2.16.2

N=Libera.Chat
E=UTF-8 (Unicode)
F=78
D=0
S=irc.libera.chat/6697

N=OFTC
E=UTF-8 (Unicode)
F=70
D=0
S=irc.oftc.net/6697
EOF

chown -R "$IRC_USER:$IRC_USER" "${IRC_HOME}/.config"

echo "==> Openbox autostart (wallpaper, panel, maximise, HexChat)"
HEXCHAT_CMD="$(command -v hexchat || echo /usr/bin/hexchat)"
cat > "${IRC_HOME}/.config/openbox/autostart" <<EOF
# Background: dark gradient instead of the bare black root window.
hsetroot -add "#0f1419" -add "#1b2733" -gradient 45 &

# Panel: task list, systray, clock.
tint2 &

# Maximise HexChat once it maps. wmctrl respects the tint2 strut, so the panel
# stays visible; xdotool's windowsize would sit on top of it.
( for _ in \$(seq 1 30); do
    wmctrl -x -l 2>/dev/null | grep -qi hexchat && break
    sleep 1
  done
  wmctrl -x -r hexchat.Hexchat -b add,maximized_vert,maximized_horz 2>/dev/null || true
) &

# Keep HexChat running for the life of the session; relaunch if it is closed.
while :; do
  ${HEXCHAT_CMD}
  sleep 2
done &
EOF
chown "$IRC_USER:$IRC_USER" "${IRC_HOME}/.config/openbox/autostart"

echo "==> Restarting session"
systemctl start irc-desktop.service

echo
echo "Done. Nick is '${NICK}' — change it with:"
echo "  pct exec 911 -- env NICK=yournick bash /root/irc/scripts/customize.sh"
