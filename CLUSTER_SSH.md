# Remote SSH into Guild-A (nodes, VMs, containers)

How to reach the Proxmox hosts and their guests from any machine, on or off the LAN.

> Cluster-wide source of truth (inventory, storage, networking, change log, open
> items): **[CLUSTER.md](CLUSTER.md)**. This file is the SSH-specific detail.

---

## The shape of the problem

| Target | Address | Reachable from outside the LAN? |
| ------ | ------- | ------------------------------- |
| Proxmox nodes | Tailscale `100.x` | **Yes** — all 5 nodes are on the tailnet |
| VMs / containers | LAN `192.168.8.x` | **Not directly** — no subnet route is advertised |

So: nodes are directly reachable from anywhere via Tailscale; guests are reached by
**jumping through a node** (`ProxyJump`). One `~/.ssh/config` makes both transparent.

### Tailscale addresses

| Node | Tailscale IP | LAN IP |
| ---- | ------------ | ------ |
| nodeA | 100.73.229.110 | 192.168.8.112 |
| nodeB | 100.93.64.97 | 192.168.8.155 |
| nodeC | 100.100.168.81 | 192.168.8.156 |
| nodeD | 100.111.121.55 | 192.168.8.195 |
| nodeE | 100.118.149.95 | 192.168.8.125 |

---

## Setting up another PC

**1. Install Tailscale** on that PC and sign into the same tailnet
(`tailscale up`). Confirm it sees the nodes: `tailscale status`.

**2. Copy the private key** to the new PC — move it yourself over a trusted channel
(USB, password manager, `scp` from a machine you already trust). Never paste a private
key into a chat or e-mail.

```bash
# on the new PC, after copying the file in:
chmod 600 ~/.ssh/proxmox_guild_a
```

**3. Copy the SSH config block** from this Mac's `~/.ssh/config` (the
`Proxmox cluster Guild-A` section) into the new PC's `~/.ssh/config`, then
`chmod 600 ~/.ssh/config`.

**4. Use it:**

```bash
ssh nodeC          # a Proxmox host, from anywhere
ssh vm103          # a VM  (jumps through nodeE automatically)
ssh ct104          # a container
```

Logins: **VMs use `ubuntu@`**, **containers and nodes use `root@`** — the config
already sets the right user per host.

---

## Without an SSH config (one-liners)

```bash
# Proxmox host directly over Tailscale
ssh -i ~/.ssh/proxmox_guild_a root@100.118.149.95

# A guest, jumping through a node — note BOTH hops need the key,
# which is why -J alone fails; use the config, or:
ssh -i ~/.ssh/proxmox_guild_a \
    -o ProxyCommand="ssh -i ~/.ssh/proxmox_guild_a -W %h:%p root@100.118.149.95" \
    ubuntu@192.168.8.140
```

`ssh -i key -J host dest` does **not** pass `-i` to the jump hop — that's the usual
"Permission denied on the jump host" trap. The config form avoids it.

---

## Better: advertise the LAN subnet (removes the jump)

If you advertise `192.168.8.0/24` from one node, every tailnet device can hit guest
IPs directly — no `ProxyJump`, and it also covers any future guest.

```bash
ssh nodeE 'tailscale up --advertise-routes=192.168.8.0/24 --accept-routes'
```

Then approve the route in the Tailscale admin console (Machines → nodeE → Route
settings). On client machines, `tailscale up --accept-routes`.

Trade-off: it exposes the whole LAN subnet to every device on your tailnet. The
ProxyJump approach exposes only what you explicitly hop to.

---

## Current guest addresses

| Guest | Node | IP | Login |
| ----- | ---- | -- | ----- |
| VM 101 `ubuntu-vm-test` | nodeC* | **192.168.50.146** (VLAN 50) | `ubuntu` — see below |
| VM 103 `ubuntu-vm-c` | nodeC | **192.168.50.140** (VLAN 50) | `ubuntu` — see below |
| VM 105 `ubuntu-vm-d` | nodeD | **192.168.50.144** (VLAN 50) | `ubuntu` — see below |
| VM 107 `ubuntu-vm-e` | nodeE | **192.168.50.152** (VLAN 50) | `ubuntu` — see below |
| CT 100 `ubuntu-ct-test` | nodeA | 192.168.8.228 | **no key installed** |
| CT 102 `ubuntu-ct-c` | nodeC | 192.168.8.214 | `root` |
| CT 104 `ubuntu-ct-d` | nodeD | 192.168.8.238 | `root` |
| CT 106 `ubuntu-ct-e` | nodeE | 192.168.8.120 | `root` |

\* VM 101 was live-migrated from nodeB to nodeC.

### All four VMs are on VLAN 50, not the main LAN

VMs 101/103/105/107 are tagged onto VLAN 50 (`192.168.50.0/24`), so they are **not**
on `192.168.8.x`, and the router does not forward from the LAN into that VLAN. They
are reached by jumping through **nodeC**, which holds `192.168.50.250` on `vmbr0.50`:

```
Host vm103 ubuntu-vm-c
    HostName 192.168.50.140
    User ubuntu
    IdentityFile ~/.ssh/proxmox_guild_a
    ProxyJump nodeC
```

The containers (100/102/104/106) are still untagged on the main LAN and continue to
use `ProxyJump nodeE`.

`ssh vm103` works from anywhere over Tailscale. Full details, verification steps, and
troubleshooting: **[VLAN50.md](VLAN50.md)**.

**These are DHCP leases and will change.** For stable SSH targets, either set DHCP
reservations on your router (GL-MT6000) or give each guest a static IP — for VMs via
cloud-init `ipconfig0=ip=192.168.8.x/24,gw=192.168.8.1`, for containers via the
`net0` config.

---

## Fallback that always works: the host console

If a guest's network is broken or its IP is unknown, get in from its node — no guest
networking required:

```bash
ssh nodeA          # then, on the node:
pct enter 100      # container: root shell, no password
qm terminal 101    # VM serial console (VMs here have serial0 configured)
```

This is how to reach **CT 100**, which has no SSH key installed.

### The console needs a *password* — keys do not apply

Guests here are provisioned **key-only**, and by default every account is locked
(`passwd -S` shows `L`). A console `login:` prompt therefore cannot be satisfied by
anything you type — it is not a wrong password, there is no password. Symptom: you
open the console, see `starting serial terminal on interface serial0` (which is
normal, not an error) and then a login prompt that rejects everything.

Set one per guest so you have a way in when networking breaks:

```bash
ssh -t vm103 sudo passwd ubuntu   # VM  (ubuntu is the cloud-init user)
ssh nodeA 'pct exec 100 -- passwd root'   # container
```

`pct enter <id>` from the node always works without a password and is the escape
hatch when a container has neither key nor password.

### QEMU guest agent

VMs are created with `agent: 1` in their Proxmox config, but the package is **not**
in the cloud image — hence "Guest Agent not running" in the UI, and why
`qm agent <id> network-get-interfaces` returns nothing. Install it in the guest:

```bash
ssh -t vm103 'sudo apt-get update && sudo apt-get install -y qemu-guest-agent && sudo systemctl enable --now qemu-guest-agent'
```

This restores live IP display in the UI and graceful `qm shutdown` / `qm reboot`.
Without it those fall back to ACPI and time out with a harmless warning.

---

## Troubleshooting

- **`Host key verification failed`** — the guest's IP was previously used by another
  machine (DHCP reuse). Clear it: `ssh-keygen -R <ip>`.
- **`Permission denied` on the jump host** — you used `-J` with `-i`; see above.
- **Node unreachable** — check `tailscale status` on both ends; the node must show
  online. Falling back to the LAN IP works only when you're on the LAN.
