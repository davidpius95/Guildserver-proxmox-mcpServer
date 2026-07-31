# Guild-A VM templates (VMID 9000 Ubuntu / 9001 Debian)

Two templates, built the same way and sharing every convention (cloud-init, `guildvm`
user, VLAN 50, shared `ceph-vm` storage, guest agent, resizable disk):

| VMID | OS | Use for |
| ---- | -- | ------- |
| **9000** | Ubuntu 26.04 LTS | general workloads |
| **9001** | Debian 13 (Trixie) | Proxmox-ecosystem software (PDM, PBS) — those ship Debian-only packages |

Everything below describes 9000; **9001 is identical apart from the OS**, except that
`software-properties-common` is omitted (it does not exist in Debian) and Debian's
image has no `qemu-guest-agent` until it is installed (baked into 9001).

---

## 0. Ubuntu template (VMID 9000)

A cloud-init Ubuntu template that clones onto **any node** in the cluster, boots in
about a minute with a working guest agent and DHCP address, and resizes cleanly.

Built and verified 2026-07-24.

---

## 1. What it is

| | |
| --- | --- |
| VMID / name | `9000` / `ubuntu-2604-guildvm-template` |
| OS | Ubuntu 26.04 LTS (official cloud image, fully updated) |
| Storage | **`ceph-vm` (shared)** — this is what lets any node clone it |
| Disk | 16 GiB, `discard=on,ssd=1` (thin + TRIM), resizable |
| CPU / RAM | 2 cores / 2048 MB — `x86-64-v2-AES` |
| Machine / firmware | `q35`, SeaBIOS |
| NIC | `virtio` on `vmbr0`, **VLAN tag 50** |
| Console | `serial0` (works with `qm terminal`) |
| Guest agent | enabled, with `fstrim_cloned_disks=1` |
| Login | user **`guildvm`**, password **`guildserver`**, plus the `proxmox_guild_a` SSH key |

`x86-64-v2-AES` is deliberate rather than `cpu: host` — it keeps clones **live-migratable**
across nodes. `host` would pin a VM to identical CPU models.

### Baked in

`qemu-guest-agent`, `cloud-init`, `cloud-guest-utils` (growpart), `openssh-server`,
`chrony`, `unattended-upgrades`, `ca-certificates`, `curl`, `wget`, `gnupg`, `git`,
`jq`, `vim`, `htop`, `tmux`, `unzip`, `rsync`, `net-tools`, `bind9-dnsutils`,
`python3`, `python3-pip`, `software-properties-common`. 732 packages, **0 pending
updates** at build time.

### Prepared for cloning

- SSH **host keys removed** → each clone regenerates its own
- `/etc/machine-id` **truncated** → each clone gets a unique ID
- cloud-init state cleared → it re-runs fresh on every clone

> Without those last two, every clone presents the same DHCP identity and they fight
> over one lease. It is a genuinely confusing failure — do not skip it if you rebuild.

---

## 2. Using it

### Proxmox UI

Right-click template **9000 → Clone**. Choose target node, VMID, name, and
**Mode: Linked Clone** (fast, space-efficient) or **Full Clone** (independent).
Adjust CPU/RAM/disk on the new VM, then Start.

### CLI

```bash
# clone to any node — shared storage makes --target work
qm clone 9000 120 --name my-new-vm --target nodeB

# optional: size it before first boot
qm set 120 --cores 4 --memory 4096
qm resize 120 scsi0 +20G

qm start 120
```

Get the address once it is up (the guest agent answers this):

```bash
qm agent 120 network-get-interfaces | grep -oE '192\.168\.50\.[0-9]+'
```

Then:

```bash
ssh guildvm@<ip>          # key auth if you hold proxmox_guild_a; password otherwise
```

### Resizing

Grow the disk from Proxmox and the guest expands itself on next boot — `growpart` +
`resize2fs` run from cloud-init:

```bash
qm resize 120 scsi0 +8G
qm reboot 120
```

Verified: 16 GiB → 24 GiB disk, root filesystem 15 GiB → 23 GiB, no manual steps.
Shrinking is **not** supported — size up only.

CPU and RAM can be changed any time in the UI or with `qm set`; both take effect on
next boot (or live, if hotplug is enabled).

---

## 3. Credentials and the security trade-off

Login is `guildvm` / `guildserver`, and SSH **password authentication is enabled**
(the stock Ubuntu cloud image ships with it off — see §5.2).

> ⚠️ Every clone ships with the same known password, and password auth is open to
> anything that can reach the VM. That is fine for a lab; it is not fine for anything
> exposed. Mitigations, cheapest first:
>
> ```bash
> # per-clone password, set before first boot
> qm set 120 --cipassword 'a-different-one'
>
> # or drop password auth entirely and rely on the SSH key
> sudo rm /etc/ssh/sshd_config.d/00-guild-auth.conf && sudo systemctl restart ssh
> ```
>
> The `proxmox_guild_a` public key is already installed, so key auth works without the
> password. Prefer it.

---

## 4. Rebuilding from scratch

Build artifacts live on **nodeD** in `/root/templates/` (`ubuntu-26.04-…-cloudimg-amd64.img`
plus the build scripts). Requires `libguestfs-tools`.

```bash
export LIBGUESTFS_BACKEND=direct        # required on Proxmox
cd /root/templates

# 1. expand the image — the stock cloud image root fs is only 2.2G and will
#    run out of space during apt upgrade + package install
qemu-img create -f qcow2 guildvm-template.qcow2 16G
virt-resize --expand /dev/sda1 ubuntu-26.04-server-cloudimg-amd64.img guildvm-template.qcow2

# 2. REQUIRED after virt-resize — see §5.1
virt-customize -a guildvm-template.qcow2 \
  --run-command 'grub-install --target=i386-pc --recheck /dev/sda && update-grub'

# 3. update + install deps, enable services
virt-customize -a guildvm-template.qcow2 --update --install <package list> \
  --run-command 'systemctl enable qemu-guest-agent chrony ssh'

# 4. enable password auth (00- sorts BEFORE the vendor 60- file; see §5.2)
virt-customize -a guildvm-template.qcow2 \
  --run-command 'printf "PasswordAuthentication yes\nKbdInteractiveAuthentication yes\n" > /etc/ssh/sshd_config.d/00-guild-auth.conf'

# 5. de-personalise so clones are unique
virt-customize -a guildvm-template.qcow2 \
  --run-command 'cloud-init clean --logs' \
  --run-command 'rm -f /etc/ssh/ssh_host_*' \
  --truncate /etc/machine-id
```

Then create the VM, import to **shared** storage, and template it:

```bash
qm create 9000 --name ubuntu-2604-guildvm-template --ostype l26 --machine q35 \
  --cpu x86-64-v2-AES --sockets 1 --cores 2 --memory 2048 \
  --scsihw virtio-scsi-single --net0 virtio,bridge=vmbr0,tag=50 \
  --serial0 socket --vga serial0 --agent enabled=1,fstrim_cloned_disks=1 --onboot 0
qm set 9000 --scsi0 ceph-vm:0,import-from=/root/templates/guildvm-template.qcow2,discard=on,ssd=1
qm set 9000 --ide2 ceph-vm:cloudinit
qm set 9000 --boot order=scsi0 --ipconfig0 ip=dhcp
qm set 9000 --sshkeys /root/templates/authorized_key.pub
qm set 9000 --ciuser guildvm --cipassword guildserver
qm template 9000
```

The Ceph import takes several minutes. Run it detached (`systemd-run --unit=… --collect`)
rather than in an SSH foreground session that can time out mid-write.

---

## 5. Traps hit while building this

### 5.1 `virt-resize` breaks BIOS boot

After `virt-resize`, the VM powered on and stopped dead at
`Booting from Hard Disk...` with no GRUB. Relocating partitions invalidates the GRUB
core embedded in the BIOS boot partition, which still points at old sector offsets.

**Always run `grub-install --target=i386-pc /dev/sda` after `virt-resize`.**

Symptom to recognise: VM "running" but using ~40 MB RAM, no network traffic at all,
guest agent absent. That is a VM that never reached the kernel.

### 5.2 Ubuntu cloud images disable SSH password auth

`/etc/ssh/sshd_config.d/60-cloudimg-settings.conf` ships `PasswordAuthentication no`,
so setting `--cipassword` alone gives you a password that cannot be used over SSH.

And sshd uses **first-obtained-value-wins**, so a `99-` drop-in does **not** override a
`60-` one. The override must sort earlier — hence `00-guild-auth.conf`.

### 5.3 SSH is socket-activated — "timed out" right after boot is normal

Ubuntu starts `ssh.service` on demand via `ssh.socket`. Immediately after boot,
`ssh.service` reads `inactive` and the first connection can time out during banner
exchange while it spins up. Retry before assuming a fault; check `ssh.socket` (not
`ssh.service`) for the real state.

### 5.4 The stock cloud image is too small to customise

3.5 GiB disk / 2.2 GiB root. `--update` plus ~20 packages fails with
`No space left on device` partway through, leaving a half-built image. Expand first.

### 5.5 Clone addresses drift

A clone's DHCP address changed across a reboot during testing (`.137` → `.138`). There
are no DHCP reservations on the GL-MT6000. Get the address from the guest agent rather
than assuming it is stable.

---

## 6. Related

- [CLUSTER.md](CLUSTER.md) — cluster source of truth
- [VLAN50.md](VLAN50.md) — the VLAN the template's NIC is tagged onto
- [CLUSTER_SSH.md](CLUSTER_SSH.md) — SSH access patterns
