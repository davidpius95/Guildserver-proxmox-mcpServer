# VLAN 50 on Guild-A — setup, verification, and troubleshooting

How VLAN 50 is wired across the Proxmox cluster, how to put a guest on it, how to
prove it works at each layer, and the traps that cost time the first time around.

Last verified: 2026-07-24.

> Cluster-wide source of truth (inventory, storage, access, change log, open items):
> **[CLUSTER.md](CLUSTER.md)**. This file is the VLAN-specific detail.

---

## 1. The topology

| Layer | Setting |
| ----- | ------- |
| Subnet | `192.168.50.0/24` |
| Gateway + DHCP | `192.168.50.1` (GL-MT6000, LAN-side MAC `94:83:c4:a5:f5:1b`) |
| Router trunk | VLAN 50 **tagged** on `lan2` (the port feeding the nodes) |
| Native / untagged | VLAN 1 = the main LAN `192.168.8.0/24` — this carries node management IPs |
| Node bridge | `vmbr0` is VLAN-aware on **all 5 nodes** (`bridge-vlan-aware yes`, `bridge-vids 2-4094`) |
| Node uplink | `nic0` is a trunk: VLAN 1 untagged (PVID) + VLANs 2-4094 tagged |

Node management IPs stay on the **untagged** native VLAN. That is why making the
bridge VLAN-aware does not knock the nodes offline.

### Current VLAN-50 members

| Host | Address | Notes |
| ---- | ------- | ----- |
| Router | `192.168.50.1` | gateway + DHCP |
| VM 101 `ubuntu-vm-test` | `192.168.50.146` | nodeC |
| VM 103 `ubuntu-vm-c` | `192.168.50.140` | nodeC |
| VM 105 `ubuntu-vm-d` | `192.168.50.144` | nodeD |
| VM 107 `ubuntu-vm-e` | `192.168.50.152` | nodeE |
| nodeC | `192.168.50.250` | `vmbr0.50`, admin jump path (see §5) |

All four VMs carry `net0 ...,tag=50`. The four **containers** (100/102/104/106) remain
untagged on the main LAN. All VMs are reached with `ssh vm101|vm103|vm105|vm107`,
which `ProxyJump`s through nodeC.

---

## 2. Putting a guest on a VLAN

**Proxmox UI:** VM → **Hardware** → Network Device → **Edit** → set **VLAN Tag** = `50`.

**CLI:**

```bash
qm set 103 -net0 virtio=BC:24:11:C6:57:6A,bridge=vmbr0,tag=50   # VM
pct set 102 -net0 name=eth0,bridge=vmbr0,tag=50,ip=dhcp          # container
```

> **The two traps that will bite you.** See §4 — a running guest does *not* move to
> the VLAN just because you tagged it, and after it moves its OS still will not use
> the NIC until rebooted.

---

## 3. Verifying it works — the ladder

Work bottom-up. Each rung isolates one layer, so the first failure tells you where
the problem is.

### 3.1 Is the bridge actually VLAN-aware? (config vs reality)

The API and GUI happily show a **pending** config that is not live. Always check the
kernel:

```bash
cat /sys/class/net/vmbr0/bridge/vlan_filtering   # 1 = live, 0 = NOT applied
ls /etc/network/interfaces.new                   # exists = unapplied pending change
```

This is the single most misleading thing in the whole stack: `bridge_vlan_aware: 1`
from the API while the kernel says `0`.

### 3.2 Is the uplink trunking the VLAN?

```bash
bridge vlan show dev nic0 | grep -w 50    # must be present, and NOT "Egress Untagged"
```

Tagged (no `Untagged` flag) is correct for a trunk to the router.

### 3.3 Is the guest's tap an access port on the VLAN?

```bash
bridge vlan show dev tap103i0             # want: 50 PVID Egress Untagged
ip -o link show tap103i0 | grep master    # want: master vmbr0
```

The guest sends untagged frames; the tap tags them. `PVID 50 untagged` is right.

### 3.4 Does the VLAN reach the router? (host-side probe)

A VLAN interface stacked on the bridge only works if the **bridge self port** is a
member of that VLAN — PVE does not add this. Without it the probe fails even when
everything else is perfect:

```bash
bridge vlan add dev vmbr0 vid 50 self          # REQUIRED for host-side testing
ip link add link vmbr0 name vmbr0.50 type vlan id 50
ip link set vmbr0.50 up
ip addr add 192.168.50.250/24 dev vmbr0.50
ping -c2 192.168.50.1                           # gateway should answer
# teardown
ip addr del 192.168.50.250/24 dev vmbr0.50; ip link del vmbr0.50
bridge vlan del dev vmbr0 vid 50 self
```

**DHCP probe without wrecking the node's routing** — `-sf /bin/true` replaces
dhclient-script so the lease is negotiated but *nothing* is configured (no IP, no
default route stolen):

```bash
timeout 20 dhclient -1 -v -sf /bin/true vmbr0.50
# success looks like: DHCPOFFER of 192.168.50.x from 192.168.50.1 / bound to ...
```

### 3.5 What is the guest actually doing?

The most direct evidence — watch its NIC:

```bash
tcpdump -i tap103i0 -n -e "udp port 67 or udp port 68 or arp"
```

A healthy boot shows `BOOTP/DHCP Request` → `Reply` → the guest ARPing for its
gateway → the router ARPing back for the guest. Silence means the guest OS is not
using the interface (see §4.2).

---

## 4. The traps

### 4.1 A running guest does not move to the VLAN-aware bridge

`ifreload -a` does **not** re-attach a running VM's NIC. If the bridge was in classic
mode when the guest started, Proxmox built classic plumbing — `vmbr0v50` (a side
bridge) and `nic0.50` (a raw subinterface) — and the guest is still on it.

Worse: **`nic0.50` intercepts all inbound tagged-50 frames before the VLAN-aware
bridge sees them.** So while it exists, any *other* VLAN-50 guest gets nothing, and
host-side probes silently fail.

Fix — hot-replug the NIC (PVE-native, keeps its bookkeeping consistent):

```bash
qm set 103 -delete net0
qm set 103 -net0 virtio=BC:24:11:C6:57:6A,bridge=vmbr0,tag=50   # same MAC
```

Then remove any leftovers PVE did not clean up:

```bash
ip link set nic0.50 down && ip link del nic0.50
ip link del vmbr0v50
```

### 4.2 After a replug, the guest OS needs a reboot

A live NIC hot-remove/add leaves a cloud-init guest's `eth0` half-initialized — it
holds no lease and transmits nothing. The replug moves the *tap*; it does not make
the *OS* use it.

```bash
qm reboot 103        # graceful (warns if guest agent absent — harmless)
qm reset 103         # hard, if the guest is unresponsive
```

Or from the console, without rebooting: `sudo netplan apply` / `sudo dhclient eth0`.

### 4.3 Applying network changes remotely without locking yourself out

Never run a bare `ifreload -a` over SSH on a remote node. Use a detached script that
auto-reverts unless you confirm — it survives your SSH/Tailscale connection dying:

```bash
systemd-run --unit=vlan-apply --collect /bin/bash /root/vlan_apply.sh
```

where the script backs up `/etc/network/interfaces`, activates `interfaces.new`,
runs `ifreload -a`, then waits ~5 minutes for `/root/VLAN_COMMIT_OK` to appear —
reverting and reloading if it never does. Verify from a *new* connection, then
`touch /root/VLAN_COMMIT_OK`. Pre-change backups live at `/root/interfaces.bak.*`.

After applying, delete `/etc/network/interfaces.new` (once byte-identical to the
applied file) or the UI keeps showing a "pending changes" banner.

---

## 5. Reaching VLAN 50 from your LAN

**Status: SOLVED.** The VLAN-50 interface is now in the router's **`lan` firewall
zone**, so LAN hosts reach `192.168.50.x` directly. Verified from a LAN Mac: ping and
SSH to all four VMs succeed with no jump host.

### How it was fixed (and why the first attempts failed)

LuCI → **Network → Firewall → Zones** → edit the **`lan`** zone → add the VLAN-50
network to **"Covered networks"** → Save & Apply.

The trap: the initial attempts added a *Traffic Rule* (src `lan` → dst `vlan50`,
port 22). That can never work while the VLAN-50 interface is **not covered by any
zone** — OpenWrt drops traffic for zoneless interfaces, and a rule referencing a zone
that does not contain the interface never matches. The rule looks correct and does
nothing. Symptom was zero packets arriving at the guest, actively *rejected* (TCP RST
→ "Connection refused", not a timeout).

So: fix **zone membership** first; only then do traffic rules mean anything.

> Trade-off: putting VLAN 50 in the `lan` zone means it is **not** isolated from the
> LAN any more — it is a separate subnet, not a security boundary. To restore
> isolation, instead give it its own zone (input `reject`, forward `reject`) plus
> **Allow forward from source zones: lan**, and narrow rules from there.

Re-check after applying — GL.iNet's vendor layer can revert LuCI firewall edits.

### Option B — jump through a node (kept, because it also works off-LAN)

nodeC holds `192.168.50.250` on `vmbr0.50`, persisted in `/etc/network/interfaces`:

```
auto vmbr0.50
iface vmbr0.50 inet static
	address 192.168.50.250/24
	post-up bridge vlan add dev vmbr0 vid 50 self || true
```

The `post-up` is what makes the bridge self-membership survive a reload (§3.4).
nodeC keeps its own IP and default route — it is *not* a router, it just has a foot
in both segments. `~/.ssh/config` then does the rest:

```
Host vm103 ubuntu-vm-c
    HostName 192.168.50.140
    User ubuntu
    IdentityFile ~/.ssh/proxmox_guild_a
    ProxyJump nodeC
```

```bash
ssh vm103        # works from anywhere, since nodeC is on the tailnet
```

**Keep this even though Option A now works.** On the LAN you can hit `192.168.50.x`
directly, but **from outside the LAN you cannot** — Tailscale reaches the nodes
(`100.x`), not the `192.168.50.0/24` subnet, because no subnet route is advertised.
The `ProxyJump nodeC` entries therefore work in *both* situations, which is why the
`vm101|vm103|vm105|vm107` aliases still use them.

Trade-off: anyone who can reach nodeC can reach VLAN 50. That is a deliberate admin
path, not a blanket firewall hole.

---

## 6. Fast triage

| Symptom | Most likely cause |
| ------- | ----------------- |
| API says `bridge_vlan_aware: 1` but VLANs do not work | Change is **pending**; check `/sys/.../vlan_filtering` (§3.1) |
| Guest tagged, gets no IP, `vmbr0vNN`/`nicX.NN` exist | Guest still on classic plumbing — replug (§4.1) |
| Tap is correct but guest transmits nothing | Guest OS did not re-init after replug — reboot (§4.2) |
| Host-side `vmbr0.50` probe dead, everything else fine | Missing `bridge vlan add dev vmbr0 vid 50 self` (§3.4) |
| "Connection refused" from the LAN | Router firewall REJECT — VLAN interface not covered by any zone (§5) |
| A firewall Traffic Rule "does nothing" | Its zone does not cover the VLAN interface — fix zone membership first (§5) |
| "Connection timed out" from the LAN | Silent DROP or wrong route, not a REJECT rule |
| Guest reaches internet but LAN cannot reach guest | Working as designed; inbound needs §5 |

---

## 7. Related

- [CLUSTER_SSH.md](CLUSTER_SSH.md) — SSH access to nodes and guests
- [NODES.md](NODES.md) — node inventory
