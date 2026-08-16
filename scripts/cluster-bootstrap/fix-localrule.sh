#!/bin/sh
# Installs the policy-routing fix that Tailscale needs on Proxmox SDN/EVPN hosts.
#
# Problem: Proxmox SDN (EVPN/VRF) moves the `local` routing table from its
# default priority 0 down to 32765. Tailscale installs its own rules at
# 5210/5230/5250 assuming `local` is still at 0. The result is that any reply
# to a tailscaled-initiated flow -- which carries fwmark 0x80000, restored by
# mangle PREROUTING CONNMARK -- does an input route lookup, misses `main` and
# `default`, and hits `5250: unreachable` ~15000 priorities before `local` is
# ever consulted. The packet is dropped as unroutable.
#
# Symptom: SYN-ACK visibly arrives on the wire but never reaches the socket.
# tailscaled cannot reach the control plane, STUN, or DERP, so the host is only
# ever reachable by peers on its own LAN. Plain curl/ssh are unaffected because
# they carry no fwmark.
#
# Fix: consult `local` before Tailscale's unreachable rule. Priority 5100 keeps
# the l3mdev rule at 1000 evaluated first, so VRF/EVPN behaviour is unchanged.

PRIO=5100

add_rule() {
    if ! ip rule show | grep -qE "^${PRIO}:.*lookup local"; then
        ip rule add from all lookup local priority "$PRIO"
        return 0
    fi
    return 1
}

add_rule && echo "added: ip rule from all lookup local priority $PRIO" \
         || echo "already present: priority $PRIO lookup local"
