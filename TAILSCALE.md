# Tailscale on Guild-A / Guild-B — remote access, known bugs, and fixes

How the Proxmox hosts reach the tailnet, what was broken, and how to diagnose it if
it breaks again.

> SSH usage and `~/.ssh/config` patterns: **[CLUSTER_SSH.md](CLUSTER_SSH.md)**.
> Cluster inventory: **[CLUSTER.md](CLUSTER.md)**.
> New-node bootstrap: **[NODE_POSTINSTALL.md](NODE_POSTINSTALL.md)**.

**Last verified 2026-08-16** — all 11 hosts accept keyless `ssh root@<tailscale-ip>`
from an off-LAN machine.

---

## Current state

**Guild-A** = nodeA–E (5 nodes). **Guild-B** = podA–F (6 nodes, quorate).
All 11 carry `tag:guildcloud-mgmt`.

> Live addresses are deliberately not listed here — this repo is public. The current
> LAN ↔ Tailscale mapping is in **[CLUSTER.md](CLUSTER.md)** and the private cluster
> notes. Get it at any time with `tailscale status`, or from the admin console.

Connect with no key at all — authentication is by tailnet identity:

```bash
ssh root@<node-ts-ip>          # or: ssh root@<node>.<tailnet>.ts.net
```

**Naming note:** podE registers as **`pode-1`**, because a stale `pode` device (a
decommissioned box, last seen 2026-08-07) still holds the name. To reclaim it: admin
console → **Machines** → remove that device — check the Tailscale IP against your
inventory so you remove the dead one and **not** the live podE — then re-register:

```bash
tailscale up --auth-key="file:/etc/pve/priv/tailscale/authkey" --ssh \
  --accept-dns=false --hostname=podE --advertise-tags=tag:guildcloud-mgmt
```

Re-registering will likely assign a **new Tailscale IP**, so update anything pinned to
podE's current one. This is cosmetic — podE is fully reachable as `pode-1`.

---

## Bug 1 — Proxmox SDN/EVPN breaks Tailscale (the root cause)

**Symptom:** hosts are reachable from their own LAN but from nowhere else. `tailscale
netcheck` reports `UDP: false` and "no response to latency probes". tailscaled logs
repeated `PollNetMap: ... context deadline exceeded` and
`fetch control key: ... connection timed out`, while plain `curl` to the *same* URL from
the *same* host returns `200` in under half a second.

**Cause:** Proxmox SDN (EVPN/VRF) moves the `local` routing table from its default
priority 0 down to 32765. Tailscale installs its policy rules assuming `local` is still
at 0:

```
1000:   from all lookup [l3mdev-table]
5210:   from all fwmark 0x80000/0xff0000 lookup main
5230:   from all fwmark 0x80000/0xff0000 lookup default
5250:   from all fwmark 0x80000/0xff0000 unreachable   <-- reply dropped here
5270:   from all lookup 52
32765:  from all lookup local                          <-- 15000 priorities too late
```

tailscaled marks its own traffic with fwmark `0x80000`, and mangle PREROUTING
(`CONNMARK restore mask 0xff0000`) restores that mark onto **incoming replies**. Each
reply does an input route lookup, misses `main` and `default`, and hits
`5250: unreachable` long before `local` is ever consulted — so the kernel discards it as
unroutable.

Because only *outbound-initiated* flows carry the mark, inbound connections from LAN
peers still worked. That is why the hosts looked perfectly healthy when tested from a
machine on `192.168.8.0/24` and were invisible from everywhere else.

**Fix** — consult `local` before Tailscale's unreachable rule. Priority 5100 keeps the
l3mdev rule at 1000 evaluated first, so VRF/EVPN behaviour is unchanged:

```bash
ip rule add from all lookup local priority 5100
```

Made permanent by `scripts/cluster-bootstrap/fix-localrule.sh` +
`tailscale-localrule.service` (oneshot, `Before=tailscaled.service`, enabled on all 11
hosts).

**Any new Proxmox node running SDN/EVPN needs this or it will look permanently
"offline".**

Only **podF** is currently unaffected — it runs no SDN VRF, so its `local` table is
still at priority 0. That is not a coincidence: podF was the one host that stayed online
and remotely reachable throughout the outage, which is independent confirmation of the
root cause.

### The fix validated end-to-end

podE also had no SDN when it was onboarded (2026-08-16), then had FRR enabled and SDN
applied. This exercised the whole failure mode deliberately:

```
before SDN:  ip rule → local at 0            netcheck → UDP: true
after SDN:   ip rule → 5100, 32765           netcheck → UDP: true   <-- still fine
```

SDN moved `local` to 32765 exactly as expected, the priority-5100 rule survived the
reboot via `tailscale-localrule.service`, and remote reachability was unaffected. So a
host can carry the exact condition that broke every other node and still work, provided
the unit is installed.

### Confirming it in 10 seconds

Same host, same destination, only the socket mark differs (`SO_MARK` = 36):

```python
import socket
s = socket.socket(); s.settimeout(5)
s.setsockopt(socket.SOL_SOCKET, 36, 0x80000)   # broken host: times out
s.connect(("192.200.0.101", 443))
```

`0x40000` (any other mark) connects in ~0.13s. If `0x80000` times out and `0x40000`
does not, you have this bug.

Under `tcpdump` the signature is unmistakable — the SYN-ACK **arrives on the wire** and
never reaches the socket:

```
SYN     out →  192.200.0.101:443    ✓
SYN-ACK in  ←  192.200.0.101:443    ✓ arrives
(no ACK, SYN retransmitted)
```

---

## Bug 2 — the watchdog restart storm

**Symptom:** every host permanently `offline` to peers despite `lastSeen` being recent.

**Cause:** the original `tailscale-watchdog.sh` (v1, 2026-08-09) restarted tailscaled
whenever `.Health` was non-empty — i.e. on **any** warning. Tailscale puts transient and
purely cosmetic messages in that array (DERP blips, "Tailscale SSH enabled, but access
controls don't allow anyone to access this device"), all of which it recovers from
unaided. Measured historical restart counts:

| host | restarts/day |
| ---- | ------------ |
| podA | 3122 |
| nodeA | 3122 |
| podE(old) / others | 1249–1521 |

tailscaled never stayed up long enough to hold a session. On nodeA the triggering
warning was *permanent*, so it was in an unbreakable loop.

**Fix:** v2 (`scripts/cluster-bootstrap/tailscale-watchdog.sh`) only treats specific
"lost the control connection" warnings as failure, requires **3 consecutive** failed
checks, runs on a **5 minute** timer, and restarts **at most once per 30 minutes**.

The pod variant keeps the re-auth branch that uses `/etc/pve/priv/tailscale/authkey`
when genuinely logged out; that branch is a no-op on hosts without the keyfile, so one
script serves both clusters.

**Trap:** the service unit must NOT use `Requisite=tailscaled.service`. The script's own
restart takes tailscaled inactive, and systemd then kills the watchdog itself.
`After=tailscaled.service` alone is correct.

---

## Bug 3 — the SSH ACL never matched the nodes

**Symptom:** `tailscale: tailnet policy does not permit you to SSH to this node`.

**Cause:** the tailnet policy's `ssh` rules used
`dst: ["autogroup:self", "autogroup:tagged"]`. **`autogroup:tagged` does not work as an
SSH `dst`**, and `autogroup:self` never matches a tagged device (tagged devices have no
owner). So no rule covered any cluster node.

**Fix:** name the tags explicitly.

```json
{
  "action": "accept",
  "src":    ["autogroup:member", "autogroup:admin", "tag:guildcloud-mgmt", "tag:operator"],
  "dst":    ["tag:guildcloud-mgmt", "tag:guildcloud-pool", "tag:guildcloud-tenant"],
  "users":  ["root", "autogroup:nonroot"]
}
```

**Gotcha:** the API rejects a tag in `src` when `dst` contains `autogroup:self`
(`"tag:X" is not allowed in src for autogroup:self`). Those must be **separate rules**.

This lives in the Tailscale admin console, not in this repo.

---

## Bug 4 — Tailscale SSH was never enabled

`RunSSH` was `false` on 8 of 9 original hosts. `node-postinstall.sh` brought hosts up
without `--ssh`.

**Fix:** the bootstrap script now passes `--ssh` and calls `tailscale set --ssh=true`
idempotently. `tailscale set` persists in `tailscaled.state` and does **not** trigger
re-auth.

---

## Bug 5 — podE had no working apt

podE's only Proxmox repos were the **enterprise** ones, which return `401 Unauthorized`
without a subscription. `apt-get update` failed, so the Tailscale install script died
before installing anything.

The knock-on effect was larger than it looked: because apt had been broken, podE had
also silently missed **141 updates** and was stranded on PVE 9.2.2 / Ceph 19.2.3 while
its peers had moved on. Proxmox wants matching versions across a cluster, so a host with
broken apt quietly drifts out of support. After the repo fix it went to PVE **9.2.10** /
kernel **7.0.14-12-pve**. Worth checking `apt-get -s upgrade | grep -c '^Inst'` on any
node that has been quiet for a while.

**Fix:** disable the enterprise sources (`Enabled: false`) and add the no-subscription
equivalents, matching every other pod:

```
/etc/apt/sources.list.d/proxmox.sources             pve-no-subscription
/etc/apt/sources.list.d/ceph-no-subscription.sources no-subscription
/etc/apt/sources.list.d/pve-enterprise.sources       Enabled: false
/etc/apt/sources.list.d/ceph.sources                 Enabled: false
```

---

## Diagnosing "I can't reach a node"

Work through these in order. **Do not test from a machine on the cluster LAN** — it
takes a direct path and will succeed even when remote access is completely broken. This
is the single easiest way to fool yourself here.

1. **Is it the host or the network?** Find another device on the same LAN that is
   reachable over Tailscale from outside — a container such as `kuma` is ideal, since
   containers have no SDN VRF and so never hit Bug 1. If that works and the node does
   not, the fault is host-specific.

2. **Is it actually alive?** From a LAN neighbour, check ICMP + `:8006` + `:22`. A host
   can be perfectly healthy and simply absent from the tailnet.

3. **Check the mark test** (Bug 1 above). This is the highest-yield single check on any
   SDN/EVPN node.

4. **Check `lastSeen` from the control plane** rather than local status:
   `mcp__tailscale__list_devices`. If `lastSeen` is minutes old while other devices show
   the current timestamp, the host has dropped its coordination session.

5. **Check the health array** on the host:
   `tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Health"])'`

### Signals that are NOT trustworthy

- **`.Self.Online`** — misreports routinely. It read `False` on hosts that peers were
  actively reaching. Use `tailscale ping` from a peer instead.
- **A same-LAN SSH success** — proves nothing about remote access.
- **`Self.Addrs` / `Relay` being populated** — these come from cached netmap state and do
  not prove the daemon can currently transact with the control plane.
- **Hand-rolled STUN probes to DERP IPs** — Tailscale's DERP servers do not answer
  vanilla STUN binding requests, so these fail even from a known-good host. Judge by
  `tailscale netcheck` instead.

### Recovery pattern worth knowing

After a restart, a host can land in
`You are logged out. The last login error was: fetch control key: ... timed out`.
That error is often **stale** — sweep the 16 control-plane IPs
(`192.200.0.101–116`) and you will usually find all of them reachable. One more
`systemctl restart tailscaled` clears it. Watchdog v2 treats "you are logged out" as
fatal, so it now self-heals within ~15 minutes.

---

## Getting back in when everything is unreachable

If no node is reachable over Tailscale and you are off-LAN, jump through any
non-Proxmox tailnet device on the cluster LAN:

```bash
ssh -o ProxyCommand="ssh -W %h:%p root@<jump-host-ts-ip>" \
    -i ~/.ssh/proxmox_guild_a root@<node-lan-ip>       # e.g. kuma -> nodeB
```

`kuma` is a container, has no SDN VRF, and therefore stayed reachable throughout the
Bug 1 outage. Any LXC on the cluster LAN works as the jump host — that is the reliable
way back in when every Proxmox host has fallen off the tailnet.

---

## Files

| Path | Purpose |
| ---- | ------- |
| `scripts/cluster-bootstrap/fix-localrule.sh` | Bug 1 fix — adds the priority-5100 `local` rule |
| `scripts/cluster-bootstrap/tailscale-localrule.service` | Runs it at boot, before tailscaled |
| `scripts/cluster-bootstrap/tailscale-watchdog.sh` | Watchdog v2 |
| `scripts/cluster-bootstrap/node-postinstall.sh` | New-node bootstrap (now enables `--ssh`) |
| `/etc/pve/priv/tailscale/autojoin.sh` | Boot-time re-join (cluster-shared, Guild-B) |
| `/etc/pve/priv/tailscale/authkey` | Reusable tagged auth key (cluster-shared, Guild-B) |

### Onboarding a Guild-B pod — the full sequence

```bash
# 1. apt must work first (see Bug 5) — enterprise repos 401 without a subscription
# 2. install tailscale
apt-get install -y tailscale && systemctl enable --now tailscaled
# 3. join, tagged, with SSH on
tailscale up --auth-key="file:/etc/pve/priv/tailscale/authkey" --ssh \
  --accept-dns=false --hostname=<podX> --advertise-tags=tag:guildcloud-mgmt
# 4. routing fix + watchdog + autojoin units
install -m755 fix-localrule.sh tailscale-watchdog.sh /usr/local/sbin/
install -m644 tailscale-localrule.service tailscale-watchdog.{service,timer} \
              tailscale-autojoin.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tailscale-localrule.service tailscale-watchdog.timer
systemctl enable tailscale-autojoin.service
```

Verify from an **off-LAN** machine: `ssh root@<tailscale-ip>` with no key, and
`tailscale netcheck` reporting `UDP: true` on the host.

Log: `/var/log/tailscale-watchdog.log` on each host (silent when healthy).
State: `/var/lib/tailscale-watchdog/{consecutive_failures,last_restart}`.
