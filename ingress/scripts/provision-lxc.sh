#!/usr/bin/env bash
# Create the ingress LXC on a Proxmox node.
#
# Run this ON a Proxmox node as root, or from your Mac:
#   scp -r ingress nodeA:/root/ && ssh nodeA 'bash /root/ingress/scripts/provision-lxc.sh'
set -euo pipefail

CTID="${CTID:-910}"                 # container id (must be free cluster-wide)
CT_HOSTNAME="${CT_HOSTNAME:-ingress}"
STORAGE="${STORAGE:-ceph-vm}"       # shared, so the CT can migrate between nodes
BRIDGE="${BRIDGE:-vmbr0}"           # LAN bridge (untagged 192.168.8.0/24)
IP="${IP:-192.168.8.10/24}"         # static, outside the DHCP pool
GW="${GW:-192.168.8.1}"
CORES="${CORES:-2}"
MEMORY="${MEMORY:-1024}"            # MB — Caddy is light
DISK="${DISK:-8}"                   # GB

# Whatever standard template is already staged on `local`.
TEMPLATE="${TEMPLATE:-local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst}"

echo "Creating CT ${CTID} (${CT_HOSTNAME}) at ${IP} on ${BRIDGE}, rootfs ${STORAGE}:${DISK}G ..."

pct create "$CTID" "$TEMPLATE" \
  --hostname "$CT_HOSTNAME" \
  --cores "$CORES" \
  --memory "$MEMORY" \
  --rootfs "${STORAGE}:${DISK}" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=${IP},gw=${GW}" \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --start 1

echo
echo "Done. CT ${CTID} is up at ${IP%/*}."
echo "Next:"
echo "  pct push ${CTID} -r /root/ingress /root/ingress   # or: pct exec ... after copying"
echo "  pct exec ${CTID} -- bash /root/ingress/scripts/install-ingress.sh"
