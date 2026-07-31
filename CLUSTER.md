# Guild-A cluster — source of truth

Single reference for the Proxmox cluster: what exists, how it is wired, how to reach
it, what has been changed, and the traps that have already cost time.

Detail docs are linked per section rather than duplicated — this file is the index and
the current-state record.

**Last verified against the live cluster: 2026-07-24.**

---

## 1. At a glance

| | |
| --- | --- |
| Cluster name | `Guild-A` |
| Proxmox VE | 9.2.2 (release 9.2) |
| Nodes | 5, all online, **quorate** |
| Guests | 5 VMs (4 workload + PDM, all on VLAN 50), 4 LXC containers (on the main LAN) |
| Templates | 9000 Ubuntu 26.04 · 9001 Debian 13 — both on shared storage |
| Management | Proxmox Datacenter Manager at **https://datacenter.guildserver.io** |
| Shared storage | Ceph RBD pool `ceph-vm`, **HEALTH_OK** |
| Management LAN | `192.168.8.0/24`, gateway `192.168.8.1` (GL-MT6000) |
| Guest VLAN | VLAN 50 → `192.168.50.0/24`, gateway `192.168.50.1` |
| Remote access | Tailscale to all 5 nodes; SSH key `~/.ssh/proxmox_guild_a` |

---

## 2. Nodes

| Node | ID | LAN IP | Tailscale IP | CPU | RAM | Ceph OSD |
| ---- | -- | ------ | ------------ | --- | --- | -------- |
| nodeA | 3 | 192.168.8.112 | 100.73.229.110 | 4 | 16 GB | osd.0 (ssd) |
| nodeB | 5 | 192.168.8.155 | 100.93.64.97 | 4 | 16 GB | osd.1 (ssd) |
| nodeC | 4 | 192.168.8.156 | 100.100.168.81 | 4 | 8 GB | osd.2 (ssd) |
| nodeD | 2 | 192.168.8.195 | 100.111.121.55 | 4 | 16 GB | osd.3 (ssd) |
| nodeE | 1 | 192.168.8.125 | 100.118.149.95 | 4 | 16 GB | — |

Hardware is Ubuntu-class ThinkPads; each has an unused `nic1` and a `wlp58s0` Wi-Fi
interface that is **not** used for cluster traffic.

> **Naming quirk:** nodeE's Ceph monitor is still named **`mon.pve`** (legacy name from
> before the nodes were renamed). It is at `192.168.8.125`. Do not be confused when
> `ceph -s` reports a leader called `pve` — that is nodeE. Likewise the Proxmox API
> reports each node's local name as `pve` in some contexts.

See [NODES.md](NODES.md).

---

## 3. Storage

| Storage | Type | Shared | Content |
| ------- | ---- | ------ | ------- |
| `ceph-vm` | RBD (Ceph pool `ceph-vm`) | **yes** | images, rootdir |
| `local-lvm` | LVM-thin (`pve/data`) | no | images, rootdir |
| `local` | dir (`/var/lib/vz`) | no | templates, ISO, backups, import |

Ceph: `HEALTH_OK` — 3 mons (nodeE/`pve`, nodeB, nodeA), 2 mgr (nodeE active, nodeB
standby), 4 OSDs all up/in, 2 pools / 33 PGs, 33 `active+clean`, ~9.5 GiB used of
943 GiB.

Only VM 101 currently sits on `ceph-vm`; the rest are on each node's `local-lvm`.
Live migration requires shared storage, so guests on `local-lvm` cannot migrate
without a disk move first.

See [CEPH.md](CEPH.md).

---

## 4. Networking

### 4.1 Layout

```
GL-MT6000 router  192.168.8.1  (VLAN1 untagged)  +  192.168.50.1 (VLAN 50)
        │  lan2 = trunk: VLAN 1 untagged (PVID) + VLAN 50 tagged
        │
   [switch fan-out]
        │
   nic0 on each node ── vmbr0 (VLAN-aware bridge)
                          ├── node management IP  (untagged / native VLAN 1)
                          ├── container taps      (untagged, VLAN 1)
                          └── VM taps             (PVID 50 untagged → VLAN 50)
```

Key point: **node management IPs ride the untagged native VLAN.** That is why making
`vmbr0` VLAN-aware does not knock the nodes offline.

### 4.2 Bridges

| Bridge | Where | State |
| ------ | ----- | ----- |
| `vmbr0` | all 5 nodes | VLAN-aware (`bridge-vlan-aware yes`, `bridge-vids 2-4094`), uplink `nic0`, holds the node IP |
| `vmbr0.50` | **nodeC only** | `192.168.50.250/24` — admin foothold on VLAN 50 (see §6.3) |
| `vmbr1` | nodeE | VLAN-aware but **no ports and no IP** — inert, unused |

### 4.3 VLAN 50

`192.168.50.0/24`, gateway + DHCP at `192.168.50.1`, tagged on the router's `lan2`
trunk. The VLAN-50 interface is a member of the router's **`lan` firewall zone**, so
LAN hosts reach `192.168.50.x` directly.

> That means VLAN 50 is a **separate subnet, not a security boundary** — anything on
> the LAN can reach it. For real isolation it needs its own firewall zone with an
> explicit `Allow forward from source zones: lan`.

Full setup, verification ladder, and troubleshooting: **[VLAN50.md](VLAN50.md)**.

---

## 5. Guests

### VMs — all on VLAN 50

| VM | Name | Node | IP (VLAN 50) | MAC | Storage | Guest agent |
| -- | ---- | ---- | ------------ | --- | ------- | ----------- |
| 101 | `ubuntu-vm-test` | nodeC¹ | 192.168.50.146 | `BC:24:11:4A:E7:4C` | ceph-vm | ✅ |
| 103 | `ubuntu-vm-c` | nodeC | 192.168.50.140 | `BC:24:11:C6:57:6A` | local-lvm | ✅ |
| 105 | `ubuntu-vm-d` | nodeD | 192.168.50.144 | `BC:24:11:64:7A:86` | local-lvm | ✅ |
| 107 | `ubuntu-vm-e` | nodeE | 192.168.50.152 | `BC:24:11:8D:25:98` | local-lvm | ✅ |

¹ VM 101 was live-migrated from nodeB to nodeC.

All are Ubuntu 26.04 cloud images, user `ubuntu`, `net0 ...,bridge=vmbr0,tag=50`,
`serial0` console, 2 cores / 2 GB.

### Templates

| VMID | Name | Storage | Notes |
| ---- | ---- | ------- | ----- |
| 9000 | `ubuntu-2604-guildvm-template` | `ceph-vm` (shared) | Ubuntu 26.04 LTS cloud-init, user `guildvm`, clonable from **any** node |
| 9001 | `debian-13-guildvm-template` | `ceph-vm` (shared) | Debian 13 Trixie, same conventions — use this for Proxmox-ecosystem software |

Clone with `qm clone <9000|9001> <newid> --target <node>`. Full usage, resizing, rebuild
recipe, and the traps hit while building them: **[TEMPLATE.md](TEMPLATE.md)**.

### Services

| VMID | Name | Node | Address | Service |
| ---- | ---- | ---- | ------- | ------- |
| 200 | `pdm-datacenter` | nodeB | `192.168.50.197` | Proxmox Datacenter Manager 1.1.7, UI on `:8443` |
| 220 | `netboot-xyz` | nodeE | `192.168.8.20`, `192.168.50.20` | netboot.xyz 3.0.2, dashboard on `:3000`, TFTP on `:69/udp`, local assets on `:8080` |

**Live at https://datacenter.guildserver.io** via Cloudflare Tunnel (`cloudflared`
systemd service on the VM, enabled at boot; valid Let's Encrypt edge certificate).

The Guild-A cluster is **enrolled** as PDM remote `guild-a`, authenticating with the
PVE API token `root@pam!pdm` (privilege separation off), covering all 5 nodes with
pinned TLS fingerprints.

> PDM resolves the remote by **node name**, so `/etc/hosts` on the PDM VM maps
> `nodeA`–`nodeE` to their IPs. Without it, four of five nodes fail to connect.
> **Update that file if a node is ever renumbered.**

See **[PDM.md](PDM.md)**.

The netboot.xyz topology, router DHCP settings, offline cache, PXE test VM, and
recovery procedure are documented in **[NETBOOT_XYZ.md](NETBOOT_XYZ.md)**.

### Containers — untagged on the main LAN

| CT | Name | Node | IP | Login |
| -- | ---- | ---- | -- | ----- |
| 100 | `ubuntu-ct-test` | nodeA | 192.168.8.228 | ⚠️ **no SSH key installed** |
| 102 | `ubuntu-ct-c` | nodeC | 192.168.8.214 | `root` (key) |
| 104 | `ubuntu-ct-d` | nodeD | 192.168.8.238 | `root` (key) |
| 106 | `ubuntu-ct-e` | nodeE | 192.168.8.120 | `root` (key) |

**All addresses above are DHCP leases and will drift.** For stable targets, set
reservations on the GL-MT6000 keyed to the MACs, or assign static addresses.

---

## 6. Access

### 6.1 Key and identity

Single key for everything: `~/.ssh/proxmox_guild_a` (ed25519,
comment `proxmox-cluster-guild-a`). Nodes and containers log in as `root`, VMs as
`ubuntu`.

### 6.2 Aliases

`~/.ssh/config` carries the whole cluster:

```bash
ssh nodeC      # Proxmox host over Tailscale — works from anywhere
ssh vm103      # VM on VLAN 50, via nodeC
ssh ct104      # container on the LAN, via nodeE
```

### 6.3 Why VMs jump through nodeC

nodeC holds `192.168.50.250` on `vmbr0.50`, persisted in `/etc/network/interfaces`:

```
auto vmbr0.50
iface vmbr0.50 inet static
	address 192.168.50.250/24
	post-up bridge vlan add dev vmbr0 vid 50 self || true
```

The `post-up` is required — PVE does not add the bridge **self** VLAN membership, and
without it the interface exists but passes nothing.

**Keep the `ProxyJump nodeC` entries even though direct LAN access now works.** On the
LAN you can reach `192.168.50.x` directly; **from outside you cannot**, because
Tailscale reaches the nodes (`100.x`) but no subnet route is advertised. The jump works
in both situations.

nodeC keeps its own IP and default route — it is *not* acting as a router.

Full SSH reference, including setting up a new PC: **[CLUSTER_SSH.md](CLUSTER_SSH.md)**.

### 6.4 Console fallback

```bash
ssh nodeA
pct enter 100      # container root shell, no password needed
qm terminal 103    # VM serial console
```

⚠️ **Console logins need a password; SSH keys do not apply.** Every guest account is
currently **locked** (`passwd -S` → `L`), so a `login:` prompt cannot be satisfied —
it is not a wrong password, there is no password. `pct enter` is the only
no-password escape hatch, and it works for containers only.

---

## 7. Change log

### 2026-07-24 — VLAN 50 rollout

1. **Discovered the VLAN-aware change was staged but never applied** on all 5 nodes —
   the API reported `bridge_vlan_aware: 1` while the kernel reported
   `vlan_filtering=0`, with the change sitting in `/etc/network/interfaces.new`.
2. **Applied VLAN-aware `vmbr0` to all 5 nodes**, each guarded by a detached
   auto-revert (see §8.3). All committed; no rollback fired; quorum never lost.
3. **Migrated VM 103 off the legacy classic plumbing** (`vmbr0v50` / `nic0.50`) onto
   the VLAN-aware bridge, removed the leftovers, rebooted the guest.
4. **Tagged VMs 101, 105, 107 onto VLAN 50** and rebooted them.
5. **Installed `qemu-guest-agent`** in all four VMs (it is absent from the cloud image
   despite `agent: 1` in the VM config).
6. **Added `vmbr0.50` on nodeC** (`192.168.50.250`) as the admin path to VLAN 50.
7. **Fixed LAN → VLAN 50 forwarding** on the router by adding the VLAN-50 interface to
   the **`lan` firewall zone**.
8. **Updated `~/.ssh/config`** — all four VM entries now point at `192.168.50.x` with
   `ProxyJump nodeC`.
9. Backups of every pre-change network config remain at `/root/interfaces.bak.*` on
   each node.

### 2026-07-24 — Ubuntu VM template

10. **Built template VM 9000** (`ubuntu-2604-guildvm-template`) on **shared `ceph-vm`**
    so it clones onto any node. Ubuntu 26.04 LTS, fully updated, dependencies baked in,
    guest agent enabled, cloud-init, user `guildvm`, VLAN 50, 16 GiB resizable disk.
    Build artifacts and scripts on nodeD in `/root/templates/`.
11. Verified end-to-end: linked-cloned to **nodeB**, booted in ~60s, agent up, DHCP
    address on VLAN 50, key **and** password login both working, disk resize
    16→24 GiB with the root filesystem auto-growing. Test clone destroyed after.
12. Two defects found and fixed during the build: `virt-resize` broke BIOS boot
    (GRUB reinstalled), and the cloud image shipped SSH password auth disabled
    (overridden via a `00-` sshd drop-in). See [TEMPLATE.md](TEMPLATE.md) §5.

### 2026-07-24 — Debian template + Proxmox Datacenter Manager

13. **Built Debian 13 template 9001** (`debian-13-guildvm-template`) mirroring 9000 —
    same deps, cloud-init, `guildvm` user, VLAN 50, shared storage. Verified by cloning
    to **nodeA**: booted in 45s, agent up, key + password login both working.
14. **Deployed PDM 1.1.7 as VM 200 `pdm-datacenter` on nodeB** (Debian 13, 2c/4G/32G,
    `192.168.50.197`, `onboot=1`). Web UI live on `:8443`, verified surviving a reboot.
    `cloudflared` 2026.7.3 installed, awaiting the owner's tunnel token.
15. Fixed during deployment: broken `grub-pc` dpkg state (empty `install_devices` on a
    cloud image), a 401ing enterprise repo, and a missing guest agent. Details in
    [PDM.md](PDM.md) §5.
16. **Cloudflare Tunnel live** — `cloudflared` connected with the owner's token;
    `https://datacenter.guildserver.io` verified serving PDM (HTTP 200, repeated
    requests, valid Let's Encrypt edge cert). Connector settles on 3 of 4 QUIC
    connections — stable and still redundant, left as-is.
17. **Cluster enrolled in PDM** as remote `guild-a` via API token `root@pam!pdm`
    (privsep off), all 5 nodes with pinned fingerprints. Required adding `/etc/hosts`
    entries on the PDM VM, because PDM addresses remotes by **node name** and nothing
    on this network resolves `nodeA`–`nodeE`.

---

## 8. Traps already paid for

Condensed; full versions with commands in [VLAN50.md](VLAN50.md) §4 and its triage
table.

### 8.1 Config shown ≠ config running

The API and GUI happily report a **pending** network config as if it were live.
Always confirm against the kernel:

```bash
cat /sys/class/net/vmbr0/bridge/vlan_filtering   # 1 = live, 0 = NOT applied
ls /etc/network/interfaces.new                   # exists = unapplied change
```

This single mismatch caused the longest detour in the whole VLAN task.

### 8.2 Tagging a running guest is not enough — twice over

- `ifreload` does **not** move a running VM's NIC. If the bridge was classic when the
  guest booted, it stays on `vmbrXvNN`/`nicX.NN` plumbing — and that leftover
  `nicX.NN` **intercepts inbound tagged frames**, silently breaking every other guest
  on that VLAN. Hot-replug the NIC to move it.
- After the replug, the guest OS still will not use the NIC — a cloud-init guest is
  left with a half-initialised `eth0` holding no lease. **It must be rebooted**
  (or `netplan apply`).

### 8.3 Never `ifreload -a` blind over SSH

Apply remote network changes via a detached script that auto-reverts unless
confirmed, so it survives losing your own connection:

```bash
systemd-run --unit=vlan-apply --collect /bin/bash /root/vlan_apply.sh
```

The script backs up `/etc/network/interfaces`, activates `interfaces.new`, runs
`ifreload -a`, then reverts after ~5 minutes unless `/root/VLAN_COMMIT_OK` appears.
Verify from a **new** connection, then commit.

### 8.4 Firewall zones beat firewall rules

A Traffic Rule can never match while its interface belongs to **no zone** — OpenWrt
drops zoneless-interface traffic outright. Fix **zone membership** first. Symptom:
"Connection refused" (TCP RST) rather than a timeout, and zero packets reaching the
guest.

### 8.5 Refused vs timed out

- **Connection refused** → something actively rejected you (a REJECT rule).
- **Connection timed out** → silent drop or a wrong route.

That distinction pointed straight at the router and is the fastest triage signal.

### 8.6 SSH config matches the name you type

`ssh root@192.168.8.238` does **not** pick up a `Host ct104` block — config matches the
typed alias, not the resolved IP, so the `IdentityFile` is skipped. Use the alias, or
load the key into the agent (`ssh-add`).

Also: `ssh -i key -J host dest` does not pass `-i` to the **jump** hop — the classic
"Permission denied on the jump host".

---

## 9. Open items

- [ ] **CT 100 `ubuntu-ct-test`** has no SSH key — reachable only via `pct enter 100`
      from nodeA.
- [ ] **All guest accounts are password-locked**, so no console login is possible.
      Set per guest: `ssh -t vm103 sudo passwd ubuntu`.
- [ ] **Containers are still untagged** on the main LAN — move to VLAN 50 if the goal
      is all guests segmented.
- [ ] **No DHCP reservations** — every guest address can drift on lease renewal.
- [ ] **VLAN 50 is not isolated** (it is in the router's `lan` zone). Needs its own
      zone if segmentation is meant as a security boundary.
- [ ] **`vmbr1` on nodeE** is defined but portless and unused — remove or wire it up.
- [ ] Guests on `local-lvm` cannot live-migrate; only VM 101, VM 200 and templates
      9000/9001 are on shared `ceph-vm`.
- [ ] **Templates ship a shared, known password** (`guildvm`/`guildserver`) with SSH
      password auth enabled. Fine for a lab, not for anything exposed — override per
      clone with `qm set <id> --cipassword`, or disable password auth
      ([TEMPLATE.md](TEMPLATE.md) §3).

### Opened by the PDM deployment

- [ ] **`datacenter.guildserver.io` is publicly reachable** with only PDM's own login in
      front of it — and PDM holds credentials to all 5 nodes. Put **Cloudflare Access**
      on it (Zero Trust → Access → Applications → self-hosted, policy = your email).
      This is the highest-value item on this list.
- [ ] **Rotate the `root@pam!pdm` token secret.** The original was pasted into a chat
      transcript. `pveum user token remove root@pam pdm && pveum user token add
      root@pam pdm --privsep 0`, then update the secret in PDM's remote settings.
- [ ] **PDM depends on `/etc/hosts` on VM 200** to resolve `nodeA`–`nodeE`. Renumbering
      a node silently breaks the remote — update that file, or add real DNS.
- [ ] The `root@pam!pdm` token has **privilege separation off** (full root-equivalent
      API rights). Scope it down to the roles PDM actually needs if you want least
      privilege.

---

## 10. Related docs

| Doc | Covers |
| --- | ------ |
| [VLAN50.md](VLAN50.md) | VLAN 50 topology, verification ladder, traps, triage table |
| [TEMPLATE.md](TEMPLATE.md) | VM templates 9000 / 9001 — cloning, resizing, rebuild recipe |
| [PDM.md](PDM.md) | Proxmox Datacenter Manager at `datacenter.guildserver.io` |
| [CLUSTER_SSH.md](CLUSTER_SSH.md) | SSH access, new-PC setup, console fallback, guest agent |
| [NODES.md](NODES.md) | Node inventory |
| [CEPH.md](CEPH.md) | Ceph storage |
| [PROXMOX_API_COVERAGE.md](PROXMOX_API_COVERAGE.md) | MCP API surface |
| [INTEGRATIONS.md](INTEGRATIONS.md) / [PUBLIC_DEPLOYMENT.md](PUBLIC_DEPLOYMENT.md) | MCP server deployment |
