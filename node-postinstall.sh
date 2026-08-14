#!/bin/bash
# Guild-A Proxmox Post-Installation Script
# Run this on any new node added to the cluster to configure it identically to existing nodes.
# Usage: bash node-postinstall.sh [--skip-reboot]
#
# This script is IDEMPOTENT — safe to run multiple times.
# It assumes:
#   - Fresh Proxmox VE 9.2+ installation
#   - Node is already joined to the cluster (pvecm status returns data)
#   - SSH key proxmox_guild_a exists on the admin machine

set -e
exec > >(tee -a /root/node-postinstall.log)
exec 2>&1
echo "[$(date)] Guild-A Node Post-Installation Starting"

SKIP_REBOOT="${1:-}"
CLUSTER_ID="guild-a"
TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}"  # set via environment or prompt

# ============================================================================
# 1. SYSTEM UPDATES & KERNEL
# ============================================================================
echo "[$(date)] === System Updates ==="
apt-get update
apt-get dist-upgrade -y

# ============================================================================
# 2. TAILSCALE INTEGRATION
# ============================================================================
echo "[$(date)] === Tailscale Setup ==="
if ! command -v tailscale &>/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

if ! tailscale status &>/dev/null; then
  if [ -z "$TAILSCALE_AUTH_KEY" ]; then
    echo "Tailscale not connected. To auto-connect, set TAILSCALE_AUTH_KEY environment variable:"
    echo "  export TAILSCALE_AUTH_KEY='tskey-...'"
    echo "  bash node-postinstall.sh"
  else
    tailscale up --authkey="$TAILSCALE_AUTH_KEY" --hostname="$(hostname)"
    echo "Tailscale connected"
  fi
else
  echo "Tailscale already connected: $(tailscale status --self 2>/dev/null | grep -oE '100\.[0-9.]+')"
fi

# ============================================================================
# 3. VLAN 50 BRIDGE (if this is nodeC — the VLAN gateway)
# ============================================================================
echo "[$(date)] === Network Bridge Setup ==="
NODE_NAME=$(hostname)

# Detect if this is nodeC (based on typical naming or ask)
# For now, we'll create the vmbr0.50 interface on all nodes but only set static IP on nodeC
if [ "$NODE_NAME" = "nodeC" ] || grep -q "nodeC" /etc/hostname 2>/dev/null; then
  echo "Detected nodeC — configuring VLAN 50 gateway"
  cat >> /etc/network/interfaces <<'EOF'

# VLAN 50 Bridge (Guild-A segmented network)
auto vmbr0.50
iface vmbr0.50 inet static
	address 192.168.50.250/24
	post-up bridge vlan add dev vmbr0 vid 50 self || true
EOF
fi

# Ensure VLAN-aware bridge on vmbr0 (all nodes)
if ! grep -q "bridge_vlan_aware 1" /etc/network/interfaces.new 2>/dev/null; then
  if [ -f /etc/network/interfaces.new ]; then
    sed -i '/auto vmbr0/,/iface vmbr0/{/iface vmbr0/a\	bridge_vlan_aware 1
    }' /etc/network/interfaces.new
  fi
fi

# ============================================================================
# 4. REQUIRED PACKAGES
# ============================================================================
echo "[$(date)] === Installing Dependencies ==="
PACKAGES=(
  "libguestfs-tools"         # virt-customize for VM images
  "qemu-guest-agent"         # Proxmox guest agent
  "chrony"                   # NTP time sync
  "unattended-upgrades"      # Automatic security updates
  "ca-certificates"
  "curl"
  "wget"
  "git"
  "jq"
  "htop"
  "tmux"
  "vim"
  "rsync"
  "net-tools"
  "bind9-dnsutils"           # dig, nslookup
  "nmap"                     # network troubleshooting
)

for pkg in "${PACKAGES[@]}"; do
  if ! dpkg -l | grep -q "^ii  $pkg "; then
    apt-get install -y "$pkg" || echo "Warning: failed to install $pkg"
  fi
done

# ============================================================================
# 5. SSH CONFIGURATION
# ============================================================================
echo "[$(date)] === SSH Setup ==="
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Add known_hosts entries for cluster nodes
if ! grep -q "nodeE" /root/.ssh/known_hosts 2>/dev/null; then
  cat >> /root/.ssh/known_hosts <<'EOF'
nodeA ssh-ed25519 ...  # placeholder: add real keys from existing nodes
nodeB ssh-ed25519 ...
nodeC ssh-ed25519 ...
nodeD ssh-ed25519 ...
nodeE ssh-ed25519 ...
EOF
fi

# Enable SSH key-based auth if not already
if ! grep -q "^PubkeyAuthentication yes" /etc/ssh/sshd_config; then
  sed -i 's/#PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
  systemctl reload ssh
fi

# ============================================================================
# 6. CEPH INTEGRATION (if not already a cluster node)
# ============================================================================
echo "[$(date)] === Ceph Status Check ==="
if pveceph status &>/dev/null; then
  echo "Node is part of Ceph cluster"
else
  echo "Node is not a Ceph node (expected for non-storage nodes)"
fi

# ============================================================================
# 7. FIREWALL & SECURITY
# ============================================================================
echo "[$(date)] === Firewall Rules ==="
# Enable ufw if not already
if ! ufw status | grep -q "Status: active"; then
  ufw --force enable
fi

# Proxmox API port (cluster communication)
ufw allow 8006/tcp comment "Proxmox API"
ufw allow 3478/udp comment "Corosync cluster"
ufw allow 5405/udp comment "Corosync cluster"

# ============================================================================
# 8. KERNEL PARAMETERS & TUNING
# ============================================================================
echo "[$(date)] === System Tuning ==="
# Increase file descriptors for heavy I/O
if ! grep -q "fs.file-max" /etc/sysctl.conf; then
  cat >> /etc/sysctl.conf <<'EOF'
# Guild-A cluster tuning
fs.file-max = 2097152
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
EOF
  sysctl -p
fi

# ============================================================================
# 9. LOGGING & MONITORING SETUP
# ============================================================================
echo "[$(date)] === Logging ==="
# Ensure Proxmox services log to journal
journalctl --set-limit=200M

# ============================================================================
# 10. CLUSTER VERIFICATION
# ============================================================================
echo "[$(date)] === Cluster Verification ==="
if pvecm status 2>/dev/null | grep -q "Quorate"; then
  echo "✓ Node is part of a quorate cluster"
  pvecm nodes | head -10
else
  echo "⚠ Node does not see a quorate cluster yet (may need to wait for corosync sync)"
fi

if pveversion &>/dev/null; then
  echo "✓ Proxmox API is running: $(pveversion | grep version | cut -d_ -f1)"
fi

# ============================================================================
# 11. TEMPLATE IMAGE SETUP
# ============================================================================
echo "[$(date)] === Prepare for VM Templates ==="
mkdir -p /root/templates
chmod 755 /root/templates

# ============================================================================
# 12. FINAL STATUS
# ============================================================================
echo "[$(date)] === Post-Install Complete ==="
echo "Node: $(hostname)"
echo "Proxmox: $(pveversion 2>/dev/null | grep -oE 'pve.+' || echo 'running')"
echo "Tailscale: $(tailscale status --self 2>/dev/null | grep -oE '100\.[0-9.]+' || echo 'connecting...')"
echo "Cluster: $(pvecm nodes 2>/dev/null | tail -1 || echo 'joining...')"

echo ""
echo "[$(date)] Next steps:"
echo "  1. Verify networking: ip link show vmbr0.50 (should exist on all nodes)"
echo "  2. Verify Ceph: ceph status"
echo "  3. Verify cluster: pvecm nodes"
echo "  4. Add to SSH config on admin machine (~/.ssh/config)"

if [ "$SKIP_REBOOT" != "--skip-reboot" ]; then
  echo ""
  echo "Rebooting in 10 seconds... (run with --skip-reboot to skip)"
  sleep 10
  reboot
fi
