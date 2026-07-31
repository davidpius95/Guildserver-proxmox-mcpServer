# Proxmox Datacenter Manager — `datacenter.guildserver.io`

PDM deployment for the Guild-A cluster: what runs where, how to reach it, and the
remaining Cloudflare step.

Deployed 2026-07-24.

---

## 1. The VM

| | |
| --- | --- |
| VMID / name | `200` / `pdm-datacenter` |
| Node | **nodeB** (chosen: zero other guests, 15 GB RAM free) |
| OS | **Debian 13 (Trixie)** |
| Resources | 2 cores / 4096 MB / 32 GB — PDM's minimum is 1 core / 1 GiB / 10 GB |
| Storage | `ceph-vm` (shared) — can migrate to any node |
| Network | `vmbr0` **VLAN 50**, DHCP → `192.168.50.197` |
| Autostart | `onboot=1` |
| PDM version | 1.1.7 (`pdm-no-subscription` repo) |
| Web UI | `https://192.168.50.197:8443` |
| PDM login | **`root@pam`** — the *Linux root password* on this VM |
| SSH login | `guildvm` / `guildserver`, or the `proxmox_guild_a` key |

```bash
ssh pdm        # alias in ~/.ssh/config
```

> **Why Debian and not the Ubuntu template.** PDM ships only as Debian Trixie packages
> (`http://download.proxmox.com/debian/pdm trixie pdm-no-subscription`). Installing them
> on Ubuntu 26.04 is unsupported and fragile. This VM was therefore built from the
> Debian 13 cloud image using the same cloud-init conventions as the templates.
> The reusable Debian template is **9001** — see [TEMPLATE.md](TEMPLATE.md).

---

## 2. Reaching it today

On the LAN (or anything that can route to VLAN 50):

```
https://192.168.50.197:8443
```

Login `root@pam` with the root password. The certificate is self-signed, so the
browser will warn — expected.

---

## 3. Publishing it at datacenter.guildserver.io

`guildserver.io` is on Cloudflare (`sergi`/`gemma.ns.cloudflare.com`), so a **Cloudflare
Tunnel** is the right mechanism — no port-forwarding, no inbound firewall holes, and
the VM keeps no public IP.

**Status: LIVE.** `https://datacenter.guildserver.io` serves PDM over the tunnel —
verified HTTP 200 across repeated requests (0.5–1.3 s), with a valid Let's Encrypt
certificate from Cloudflare's edge (no browser warning, unlike hitting `:8443` directly).

`cloudflared` 2026.7.3 runs as a systemd service on the VM, enabled at boot.

The steps that produced this, for reference / rebuild:

### Step 1 — connect the tunnel (on the VM)

```bash
ssh pdm
```

Then paste the command from the Cloudflare dashboard **directly into that terminal**:

```bash
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
```

Verify:

```bash
systemctl is-active cloudflared
```

> The token grants tunnel access — treat it as a secret. Paste it only on the VM.

### Step 2 — route the hostname (Cloudflare dashboard)

Tunnel → **Public Hostnames** → Add:

| Field | Value |
| ----- | ----- |
| Subdomain | `datacenter` |
| Domain | `guildserver.io` |
| Type | **HTTPS** |
| URL | `localhost:8443` |
| Additional settings → **No TLS Verify** | **enabled** |

**`No TLS Verify` is required.** PDM serves a self-signed certificate; without this
flag the tunnel returns `502` and looks broken when it is not.

> ⚠️ `datacenter.guildserver.io` **already resolves** to Cloudflare proxy IPs
> (`104.21.15.93`, `172.67.205.172`), so a record already exists. The tunnel route will
> conflict with it — replace the existing record rather than adding another.

### Step 3 (strongly recommended) — put Access in front

PDM holds credentials to the **entire cluster**. A public URL where the only thing
between the internet and five nodes is PDM's own login is a large exposure.

Zero Trust → **Access → Applications** → Add → Self-hosted:
- Domain `datacenter.guildserver.io`
- Policy: Allow → Emails → your address

That turns a public admin panel into one only you can open, and costs nothing.

---

## 4. Connecting the cluster to PDM

In the PDM UI, add each PVE node as a remote (Remotes → Add). Use an API token rather
than a root password. PDM reaches the nodes on `192.168.8.x` — verified working from
VLAN 50, because VLAN 50 currently sits in the router's `lan` firewall zone.

> **Dependency worth knowing:** if you ever isolate VLAN 50 into its own firewall zone
> (as [VLAN50.md](VLAN50.md) §5 describes), PDM loses access to the node management
> network and you must explicitly allow VLAN 50 → LAN on port 8006.

### PDM must be able to resolve the node *names*

When you add a remote, PDM queries the cluster for its members and gets back **node
names** (`nodeA`…`nodeE`), not IPs. There is no DNS for those short names on this
network, so every entry except a literally-typed IP fails with:

```
api error (status = 400: connection failed: client error (Connect))
```

Fixed with static entries in `/etc/hosts` on the PDM VM:

```
192.168.8.112 nodeA
192.168.8.155 nodeB
192.168.8.156 nodeC
192.168.8.195 nodeD
192.168.8.125 nodeE
```

Prefer this over replacing the names with IPs in the PDM UI — PDM re-reads cluster
membership and will use the names again. **If you renumber a node, update this file.**

### Authentication gotchas

- `root@pam` + `guildserver` **fails** — `guildserver` is the *PDM VM's* password. The
  remote authenticates against the *PVE node's* PAM, i.e. your Proxmox install password.
- Using a token instead: create it with **privilege separation off**
  (`pveum user token add root@pam pdm --privsep 0`), or PDM connects but every action
  returns 401.
- Don't reuse the existing `root@pam!nodeE` token — that one belongs to the MCP server;
  revoking it would break both consumers.

---

## 5. Problems hit during deployment

### 5.1 `grub-pc` left dpkg broken

Installing PDM pulled `pve-firmware` and a Proxmox kernel, and `grub-pc` failed to
configure because `grub-pc/install_devices` was **empty** on a cloud image. dpkg was
left in a broken state — future `apt` runs would fail, and the bootloader was not
properly updated.

```bash
echo "grub-pc grub-pc/install_devices multiselect /dev/sda" | sudo debconf-set-selections
sudo DEBIAN_FRONTEND=noninteractive dpkg --configure -a
```

Verified afterwards by rebooting: comes back on kernel `7.0.14-6-pve` with PDM
running. **Check this on any cloud image where a Proxmox kernel gets installed.**

### 5.2 The enterprise repo 401s

The PDM packages add `https://enterprise.proxmox.com/debian/pdm`, which returns
**401 Unauthorized** without a subscription and makes every `apt update` noisy/failing.
Disabled: `/etc/apt/sources.list.d/pdm-enterprise.sources.disabled`. The
`pdm-no-subscription` repo remains active.

### 5.3 The guest agent is not in the Debian cloud image

Unlike the Ubuntu template, the stock Debian genericcloud image has no
`qemu-guest-agent`, so `qm agent 200 …` returned nothing and the VM's IP was invisible
to Proxmox. Installed explicitly. (Template 9001 has it baked in.)

### 5.4 Tunnel diagnostics: what the error codes mean

- **`530` / `error code: 1033`** — Cloudflare has the hostname routed to a tunnel but
  **no connector is connected**. This is the *good* failure: it proves the dashboard
  side (tunnel + public hostname) is correct and only the VM-side connector is missing.
  Fix by running `sudo cloudflared service install <token>` on the VM.
- **`502`** — connector is up but cannot reach the origin. Usually the missing
  **No TLS Verify** flag against PDM's self-signed cert, or the wrong port.
- **`HEAD` returns `400`, `GET` returns `200`** — normal. PDM rejects HEAD requests;
  it does so on a direct connection too, so it is not a tunnel fault. Browsers use GET.

Connector health: `cloudflared` opens **4** QUIC connections for redundancy. This
deployment settles on **3 of 4** — connIndex 3 fails to establish at startup
(`control stream encountered a failure while serving`) and stops retrying. Three
connections is still redundant and stable (zero errors once settled), so this is left
as-is. If all four are ever wanted, forcing the HTTP/2 transport usually does it:

```bash
sudo systemctl edit cloudflared    # add: Environment=TUNNEL_TRANSPORT_PROTOCOL=http2
```

Useful checks:

```bash
systemctl is-active cloudflared
sudo journalctl -u cloudflared -n 30 --no-pager
curl -s -o /dev/null -w '%{http_code}\n' https://datacenter.guildserver.io/
```

### 5.5 `software-properties-common` does not exist in Debian Trixie

It is an Ubuntu package. Carrying the Ubuntu template's package list straight over
failed the whole `virt-customize` run with `Unable to locate package`. Dropped.

---

## 6. Related

- [CLUSTER.md](CLUSTER.md) — cluster source of truth
- [TEMPLATE.md](TEMPLATE.md) — VM templates 9000 (Ubuntu) / 9001 (Debian)
- [VLAN50.md](VLAN50.md) — the VLAN this VM sits on
