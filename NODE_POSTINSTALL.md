# Guild-A Node Post-Installation Script

Automated configuration for new Proxmox nodes joining the cluster. This script brings a fresh node into the exact same state as all existing cluster members — network, security, Tailscale, packages, monitoring, etc.

**Built 2026-07-24.**

---

## Quick start

### On the new node (manual SSH)

```bash
# 1. SSH to the new node (from the admin machine or the LAN)
ssh root@<new-node-ip>

# 2. Download and run the script
curl -fsSL https://raw.githubusercontent.com/.../ProxmoxMCP-Plus/main/node-postinstall.sh | bash
# OR (if the repo is private):
scp root@<existing-node>:/root/node-postinstall.sh /tmp/
bash /tmp/node-postinstall.sh
```

The script will:
- Update the OS and Proxmox
- Connect to Tailscale (if auth key is provided)
- Configure VLAN 50 bridge on all nodes
- Install all required packages
- Set up SSH keys and firewall rules
- Verify cluster membership

Then it **reboots** to apply kernel and network changes.

### Keeping it in sync (before reboot)

To skip the auto-reboot and check everything first:

```bash
bash node-postinstall.sh --skip-reboot
# verify settings, then:
reboot
```

---

## Where to store it

### Option 1: On an existing node (simple)

```bash
# Copy to all existing nodes in a shared location
for node in nodeA nodeB nodeC nodeD nodeE; do
  scp node-postinstall.sh root@$node:/root/
  ssh root@$node chmod +x /root/node-postinstall.sh
done
```

New nodes can fetch it from any cluster member:

```bash
ssh root@<new-node> "scp root@nodeE:/root/node-postinstall.sh /tmp/ && bash /tmp/node-postinstall.sh"
```

### Option 2: On a central web server (for automation)

Store it in a location accessible from any node without auth:

```bash
# Example: on the ingress/Caddy VM
scp node-postinstall.sh guildvm@192.168.50.197:/var/www/guild-a/
# Access it at: https://datacenter.guild-technologies.com/scripts/node-postinstall.sh
```

Then new nodes fetch it:

```bash
curl -fsSL https://datacenter.guild-technologies.com/scripts/node-postinstall.sh | bash
```

### Option 3: Baked into Proxmox cloud-init (advanced)

When cloning a Proxmox ISO, embed the script in cloud-init so it runs automatically on first boot. (This requires custom ISO creation — not covered here.)

---

## Tailscale auto-connection

The script checks if Tailscale is connected. If not, it requires an auth key. To auto-connect on run:

```bash
export TAILSCALE_AUTH_KEY='tskey-yourtoken'
bash node-postinstall.sh
```

Get a reusable key from the Tailscale admin console:
- **Tailscale admin** → **Settings → Keys** → **Auth Keys** → Create auth key with:
  - **Reusable**: ✓ (so it works for future nodes)
  - **Expiry**: 90 days (or your preference)
  - **Preapproved**: ✓ (skip auth flow)

Then paste it into your deployment automation.

### Required for SDN/EVPN nodes — read this

A node running Proxmox SDN (EVPN/VRF) **will look permanently "offline" on the tailnet**
unless it also gets the policy-routing fix. SDN moves the `local` route table to
priority 32765; Tailscale's fwmark-`0x80000` `unreachable` rule at 5250 then drops every
reply to a tailscaled-initiated flow. The node stays reachable from its own LAN, which
makes the fault easy to miss.

Install alongside the post-install script:

```bash
install -m755 scripts/cluster-bootstrap/fix-localrule.sh /usr/local/sbin/
install -m644 scripts/cluster-bootstrap/tailscale-localrule.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now tailscale-localrule.service
```

Verify: `tailscale netcheck` must report `UDP: true`. Full explanation and diagnostics:
**[TAILSCALE.md](TAILSCALE.md)**.

The script enables Tailscale SSH (`--ssh` plus an idempotent `tailscale set --ssh=true`),
so hosts accept keyless `ssh root@<tailscale-ip>` by tailnet identity. Also deploy
`scripts/cluster-bootstrap/tailscale-watchdog.sh` — and use **v2**; the original
restarted tailscaled on any health warning and produced 1200–3100 restarts/day.

### Fresh nodes may have unusable apt

A newly installed node ships with only the Proxmox **enterprise** repos, which return
`401 Unauthorized` without a subscription — `apt-get update` fails and package installs
(including Tailscale) die. Disable them and add the no-subscription equivalents before
anything else:

```
/etc/apt/sources.list.d/proxmox.sources              pve-no-subscription
/etc/apt/sources.list.d/ceph-no-subscription.sources no-subscription
/etc/apt/sources.list.d/pve-enterprise.sources       Enabled: false
/etc/apt/sources.list.d/ceph.sources                 Enabled: false
```

---

## What gets configured

| Item | Details |
|------|---------|
| **OS & Kernel** | `apt-get dist-upgrade`, latest Proxmox kernel |
| **Networking** | VLAN-aware bridge on `vmbr0`, VLAN 50 tagged on all nodes, nodeC gets static `192.168.50.250` |
| **Tailscale** | Installed and connected to the cluster tailnet (requires auth key or manual approval) |
| **Packages** | libguestfs, qemu-guest-agent, chrony, unattended-upgrades, curl, git, jq, htop, tmux, vim, rsync, nmap, bind9-utils |
| **SSH** | Public key auth enabled; known_hosts seeded (run with real keys from existing nodes) |
| **Firewall** | ufw enabled; Proxmox (8006), Corosync (3478, 5405) ports open |
| **Ceph** | Status checked (node joins if cluster has shared storage) |
| **Sysctl tuning** | File descriptors, TCP backlog, etc. for heavy I/O |
| **Logging** | Journal buffer set to 200 MB |
| **Cluster** | Pvecm status verified; node joins existing cluster automatically |

---

## For a completely new cluster (bootstrap)

If you're building Guild-A from scratch and want to deploy N fresh nodes identically:

```bash
# 1. Install Proxmox on all nodes normally (they'll be standalone)
# 2. Create the cluster on nodeA (or your chosen first node)
#    From nodeA: pvecm create guild-a

# 3. Add other nodes to the cluster
#    From nodeB/C/D/E: pvecm add <nodeA-ip>

# 4. Run the post-install script on all nodes
for node in nodeA nodeB nodeC nodeD nodeE; do
  echo "=== $node ==="
  ssh root@$node "curl -fsSL <url-to-script> | TAILSCALE_AUTH_KEY='...' bash"
done

# 5. All nodes reboot and are now configured identically
```

---

## Idempotence & re-running

The script is **safe to run multiple times**:

- Package installation skips already-installed packages
- Network config checks for existing entries before adding
- SSH keys are only added if missing
- Firewall rules use `ufw allow` (idempotent)
- Sysctl changes check before adding

You can re-run the script to:
- Update packages
- Repair a broken configuration
- Add new settings in future versions

**Just don't run it concurrently on the same node** — the reboot at the end will interrupt other operations.

---

## Monitoring the run

The script logs to `/root/node-postinstall.log` on the node:

```bash
# On the target node:
tail -f /root/node-postinstall.log

# From an admin machine:
ssh root@<new-node> tail -f /root/node-postinstall.log
```

---

## Troubleshooting

### "Tailscale not connected"

The script detects this but won't block. Either:
- Provide `TAILSCALE_AUTH_KEY` via environment
- Manually connect after the script: `tailscale up` and approve in the admin console

### "Node does not see a quorate cluster"

Fresh nodes take ~30 seconds to sync with Corosync. Wait and check:

```bash
pvecm nodes           # watch this until quorate
sleep 5 && pvecm nodes
```

If still not quorate after 1 minute, check corosync status:

```bash
corosync-cfgtool -s   # should show all nodes
systemctl status corosync
```

### Network interface `vmbr0.50` not showing

Run the network apply step manually:

```bash
ifreload -a
ip link show vmbr0.50   # should appear
```

Then verify VLAN awareness on vmbr0:

```bash
bridge vlan show dev vmbr0   # should list vid 50
```

### Packages fail to install

Ensure the node has internet access:

```bash
curl -I https://deb.debian.org/   # should return 200
```

If behind a proxy, update `/etc/apt/apt.conf.d/` before running the script.

---

## Customizing the script

The script is designed for **Guild-A cluster specifics**. To adapt it for:

- **Different VLAN ID**: change `192.168.50.0/24` and `vid 50`
- **Different gateway node**: change the `nodeC` detection
- **Different Tailscale tailnet**: it will auto-detect from `tailscale status`
- **Extra packages**: add to the `PACKAGES=()` array
- **Custom Sysctl settings**: add to the sysctl block

Edit `node-postinstall.sh` directly; no compilation needed.

---

## Related

- **[CLUSTER.md](CLUSTER.md)** — cluster source of truth; see §7 change log for any updates to post-install procedures
- **[CLUSTER_SSH.md](CLUSTER_SSH.md)** — SSH setup for new PCs; uses the same keys as post-install
- **[VLAN50.md](VLAN50.md)** — detailed VLAN 50 configuration; post-install script handles the basics
