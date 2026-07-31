# IRC — HexChat on the cluster

A **persistent HexChat session** running in its own LXC, reachable from any
browser. Because the X session never stops, HexChat stays connected to IRC
whether or not anything is attached — it is effectively its own bouncer, with
scrollback intact when you come back.

```
   Browser (LAN / Tailscale)
        │  http :6080
┌───────▼─────────────────────────────┐
│  irc LXC 911 — 192.168.8.11         │
│                                     │
│  websockify ── 0.0.0.0:6080  (noVNC)│
│       │                             │
│  Xtigervnc ── 127.0.0.1:5901        │  ← never leaves the container
│       │                             │
│  openbox ──> hexchat  (relaunched   │
│              if you close it)       │
└─────────────────────────────────────┘
```

| | |
|---|---|
| **URL** | http://192.168.8.11:6080/vnc.html |
| **VNC password** | in `/root/irc-vnc-password` inside the container |
| **Container** | CT **911** `irc`, nodeB, rootfs on `ceph-vm` (shared → migratable) |
| **Resources** | 2 cores / 2 GB / 8 GB disk, unprivileged, `onboot=1` |
| **HexChat** | 2.16.2 from the Debian 13 archive |

Get the password:

```bash
ssh nodeB 'pct exec 911 -- cat /root/irc-vnc-password'
```

Change it (verifies the bytes actually took, then restarts the session):

```bash
ssh nodeB 'pct exec 911 -- env VNC_PASSWORD=newpass1 bash /root/irc/scripts/set-vnc-password.sh'
```

---

## Day-to-day

```bash
ssh nodeB 'pct exec 911 -- systemctl status irc-desktop irc-novnc'   # state
ssh nodeB 'pct exec 911 -- systemctl restart irc-desktop'            # restart session
ssh nodeB 'pct enter 911'                                            # root shell
```

**Change your nick** in HexChat itself: the Network List dialog is the first
thing you see (Nick name / Second choice / User name). It defaults to
`irc-user`. Networks are saved to
`/home/irc-user/.config/hexchat/servlist.conf` and persist across restarts.

To have HexChat skip the network dialog and auto-connect on boot, tick
**"Skip network list on startup"** and mark your network with **Favor** →
*Auto connect to this network at startup*.

---

## Files

| Path | What it is |
|------|------------|
| `scripts/provision-lxc.sh` | Creates the LXC (run on a Proxmox node). |
| `scripts/install-irc.sh` | Installs the X session, HexChat, noVNC + systemd units. |
| `scripts/customize.sh` | Wallpaper, tint2 panel, nick, Libera/OFTC autoconnect. |
| `scripts/set-vnc-password.sh` | Sets the noVNC password and verifies the bytes took. |

All three are idempotent — re-running `install-irc.sh` keeps the existing VNC
password, and `customize.sh` can be re-run to change the nick:

```bash
ssh nodeB 'pct exec 911 -- env NICK=yournick bash /root/irc/scripts/customize.sh'
```

Networks are pre-seeded: **Libera.Chat** (SSL, autoconnect on boot) and **OFTC**
(SSL, listed but manual). The startup network dialog and the post-connect
"join a channel" dialog are both suppressed, so it lands straight in the server
tab.

### Rebuild from scratch

```bash
scp -r irc nodeB:/root/
ssh nodeB 'bash /root/irc/scripts/provision-lxc.sh'
ssh nodeB 'tar -C /root -cf - irc | pct exec 911 -- tar -C /root -xf -'
ssh nodeB 'pct exec 911 -- bash /root/irc/scripts/install-irc.sh'
```

Like the ingress box, `pct push` has no `-r`, so pipe a tar. The container is
created with `--nameserver 1.1.1.1`; without it apt cannot resolve.

---

## How the session stays up

`irc-desktop.service` runs `/usr/local/bin/irc-session`, which starts
`Xtigervnc` on `:1` bound to loopback, waits for the socket to appear, then
execs `openbox-session`. Openbox's `autostart` runs HexChat in a `while` loop,
so closing the HexChat window brings it straight back rather than ending the
session. `Restart=always` covers the case where the whole session dies.

`irc-novnc.service` runs websockify, serving the noVNC web UI on `:6080` and
proxying to `127.0.0.1:5901`.

The two units are wired with **`PartOf=` on the proxy plus `Wants=` on the
desktop**, which is fussier than it looks:

- `Requires=` was the first attempt. It propagates *stop* but **not** *restart* —
  so `systemctl restart irc-desktop` tore noVNC down and left it down, and the
  web UI just stopped answering while HexChat carried on fine.
- `PartOf=` propagates both, but it cannot **start** a unit that is already
  stopped. On its own it never recovered from the state above.
- `Wants=irc-novnc.service` on the desktop unit covers that last case.

Both are enabled, and the container is `onboot=1` — verified by rebooting it:
all four processes and both listeners returned with no intervention.

### Why the unit does not use `PAMName=login`

It did at first, and it caused a real bug. `PAMName=login` moves the session's
processes into a PAM session scope **outside** the service cgroup, so
`systemctl stop` never reaped the backgrounded HexChat respawn loop. The orphan
survived, reattached to the *new* `:1` display on restart, and you ended up with
two HexChats on Libera — the second one bumped to `nick_` because the first
already held the nick.

`KillMode=control-group` plus `ExecStopPost=pkill -9 -u irc-user` fixes it.
Verified by restarting the unit twice in a row: still exactly one HexChat
process and one connection to `:6697`.

---

## Troubleshooting

**"Authentication failed" in noVNC.** Two independent causes, both hit during
the build:

1. **The plaintext record drifted from the password blob.** The install script
   wrote `~/.vnc/passwd` and `/root/irc-vnc-password` in separate steps, so the
   file could say one thing while the server accepted another. Use
   `set-vnc-password.sh`, which re-encodes and byte-compares afterwards. To check
   the current state without changing it — VNC obfuscation uses a fixed key, so
   the same plaintext always encodes to the same 8 bytes:

   ```bash
   ssh nodeB 'pct exec 911 -- bash -c "printf %s \$(cat /root/irc-vnc-password) \
     | vncpasswd -f | cmp - /home/irc-user/.vnc/passwd && echo MATCH || echo MISMATCH"'
   ```

2. **TigerVNC blacklisted `127.0.0.1`.** Every client reaches the VNC server
   through websockify, so they all appear as loopback. The per-IP brute-force
   blacklist therefore treats *all* users as one identity: a few typos lock out
   everybody, and the correct password then fails too — which looks exactly like
   a wrong password. The unit now runs with `-BlacklistThreshold=100
   -BlacklistTimeout=30`. Restarting `irc-desktop` clears an active blacklist.

   The blacklist buys little here regardless: it cannot distinguish an attacker
   from a legitimate user when both are loopback. The real controls are LAN-only
   exposure and the note below.

**Console `login:` rejects everything.** `root` and `irc-user` are locked
(`passwd -S` shows `L`) — there is no password to get wrong, and `guildserver`
is an IRC nick, not a Unix account. Use `pct enter 911` from the node, or set a
password with `pct exec 911 -- passwd root`.

---

## Security — read before exposing this

**This is currently LAN-only, and that is deliberate.** It is *not* wired into
the `*.guildserver.io` ingress.

The only thing in front of the session is the RFB password, and **the VNC
protocol truncates passwords to 8 characters**. That is fine on a trusted LAN.
It is not fine on the public internet, where it is a remote desktop behind an
8-character secret.

Reach it from off-LAN over **Tailscale** instead — the nodes are already on the
tailnet:

```bash
ssh -N -L 6080:192.168.8.11:6080 nodeB
# then open http://localhost:6080/vnc.html
```

If you do want it on a subdomain, put **Cloudflare Access** in front of the
hostname *first* (Zero Trust → Access → Applications), so Cloudflare
authenticates before traffic ever reaches the tunnel — then:

```bash
./ingress/route add irc 192.168.8.11:6080
```

Order matters. Adding the route first publishes the desktop to the internet in
the window before the Access policy exists.
