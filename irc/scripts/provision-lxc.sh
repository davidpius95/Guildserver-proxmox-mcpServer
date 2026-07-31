#!/usr/bin/env bash
# Create the IRC LXC on a Proxmox node.
#
# Run this ON a Proxmox node as root, or from your Mac:
#   scp -r irc nodeB:/root/ && ssh nodeB 'bash /root/irc/scripts/provision-lxc.sh'
set -euo pipefail

CTID="${CTID:-911}"                 # container id (must be free cluster-wide)
CT_HOSTNAME="${CT_HOSTNAME:-irc}"
STORAGE="${STORAGE:-ceph-vm}"       # shared, so the CT can migrate between nodes
BRIDGE="${BRIDGE:-vmbr0}"           # LAN bridge (untagged 192.168.8.0/24)
IP="${IP:-192.168.8.11/24}"         # static, outside the DHCP pool, next to ingress .10
GW="${GW:-192.168.8.1}"
CORES="${CORES:-2}"
MEMORY="${MEMORY:-2048}"            # MB — X + HexChat is light, but not Caddy-light
DISK="${DISK:-8}"                   # GB
NAMESERVER="${NAMESERVER:-1.1.1.1}" # provision without this and apt cannot resolve

TEMPLATE="${TEMPLATE:-local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst}"

echo "Creating CT ${CTID} (${CT_HOSTNAME}) at ${IP} on ${BRIDGE}, rootfs ${STORAGE}:${DISK}G ..."

pct create "$CTID" "$TEMPLATE" \
  --hostname "$CT_HOSTNAME" \
  --cores "$CORES" \
  --memory "$MEMORY" \
  --rootfs "${STORAGE}:${DISK}" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=${IP},gw=${GW}" \
  --nameserver "$NAMESERVER" \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --start 1

echo
echo "Done. CT ${CTID} is up at ${IP%/*}."
echo "Next:"
echo "  tar -C /root -cf - irc | pct exec ${CTID} -- tar -C /root -xf -"
echo "  pct exec ${CTID} -- bash /root/irc/scripts/install-irc.sh"
