# Obol DVT operator (Rocklogic Hoodi cluster) — readiness and plan

Joining Rocklogic's Obol DVT cluster on **Hoodi** as a 7th operator, so one key share runs
in our region. This file records what our side can offer, what is missing, and the proposed
split of responsibilities. Draft reply to Rocklogic at the end.

> Cluster source of truth: **[CLUSTER.md](CLUSTER.md)** · Capacity: **[CAPACITY.md](CAPACITY.md)**
> · Remote access: **[TAILSCALE.md](TAILSCALE.md)** · Monitoring: **[MONITORING.md](MONITORING.md)**

> **This repo is public.** No ENRs, charon keys, keystore files, WireGuard private keys,
> peer endpoints or live IPs go in here. Keep them on the VM and in the private notes.

**Status:** pre-onboarding — answering Rocklogic's infra questions. Nothing deployed yet.

---

## 1. What Rocklogic asked, and our honest answers

| Question | Answer | Source |
| --- | --- | --- |
| Bare metal, VMs or cloud? | **Self-hosted bare metal running Proxmox VE 9.2**; the operator would be a **VM** | [CLUSTER.md](CLUSTER.md) |
| Where is it hosted? | **TODO** — city/country of the rack | not documented |
| WAN bandwidth | **TODO** — ISP plan, measured up/down, data cap | not documented |
| Public IP | **TODO** — static, dynamic, or CGNAT? | not documented |
| Port forwarding | Router is a **GL-MT6000 (OpenWrt)** — forwarding is possible if we are not behind CGNAT | [VLAN50.md](VLAN50.md) |
| Power / uptime | **TODO** — UPS? outage history? | not documented |

The three TODO rows decide the network design (§4), so fill them before replying.

---

## 2. Where the VM should live

**Guild-B, on the node with 62 GB RAM.** Not Guild-A.

| | Guild-A | Guild-B |
| --- | --- | --- |
| RAM | 8–16 GB per node, nodeD already ~75 % | one node **62 GB at ~19 %** |
| Storage | ~140–340 G local thin pools; Ceph ~122 GiB free | **~13.7 TB thin pool, <3 % used** |
| Shared storage / HA | Ceph, but over a 100 Mb link | none — node-local only |

An EL + CL + charon + VC stack is RAM- and disk-heavy and wants low-latency local storage.
Ceph `size=3` over the 100 Mb switch is the wrong place for chain data. Guild-B's lack of HA
does not matter here: DVT itself tolerates one operator being down, which is the point of
the cluster.

**Before committing, verify on that node:**

- [ ] Disk type behind the thin pool — **must be SSD/NVMe**. Execution clients on spinning
      disks fall behind.
- [ ] Thin pool real size vs allocated (`lvs -o lv_size,data_percent,lv_attr`) — see the
      over-allocation trap in [BACKUPS.md](BACKUPS.md).
- [ ] Node's NIC link speed (`ethtool`) — see §3.

### Sizing (starting point, confirm against Rocklogic's client pair)

| Resource | Ask |
| --- | --- |
| vCPU | 4–8 |
| RAM | 32 GB |
| Disk | 1 TB on local SSD thin pool (Hoodi chain + growth headroom) |
| Template | 9001 Debian 13 or 9000 Ubuntu 26.04 ([TEMPLATE.md](TEMPLATE.md)) — **override the shared template password** at clone time |

---

## 3. Blockers and risks on our side

1. **100 Mb/s switch.** Every node negotiates 100 Mb ([CAPACITY.md](CAPACITY.md)). A single
   operator's charon + client traffic fits, but it shares that link with backups and
   everything else. Fixing the switch is already the highest-value open item — do it before
   this goes live, and certainly before mainnet.
2. **Backups contend for the same link.** Exclude the chain-data disk from vzdump (it is
   re-syncable) and back up only the VM's config + charon/VC state.
3. **Tailscale + SDN routing quirk.** Guild-B hosts carry the priority-5100 `local` rule
   ([TAILSCALE.md](TAILSCALE.md)). Run Rocklogic's WireGuard **inside the VM**, not on the
   Proxmox host, so it never interacts with host policy routing.
4. **VLAN 50 is not isolated** from the LAN ([VLAN50.md](VLAN50.md) §5). A validator VM
   should get its own firewall zone, or at least a Proxmox VM firewall allowing only the
   ports in §4.
5. **Guest addresses are DHCP and drift.** Give the validator VM a static address or a
   reservation — WireGuard peers and port forwards depend on it.

---

## 4. Network design (depends on §1 answers)

| Our WAN situation | Design |
| --- | --- |
| Public IP, forwarding possible | Forward Rocklogic's WireGuard UDP port to the VM; charon peers over the mesh. Optionally forward charon's p2p port (default **3610/tcp**) for direct connectivity. |
| Behind CGNAT / no forwarding | Outbound-only WireGuard to their peers + their self-hosted relays. Works, but we cannot be dialled directly — confirm with Rocklogic that relay-only is acceptable for one operator. |

Either way the Proxmox hosts stay off their mesh; only the operator VM joins it.

---

## 5. Proposed responsibility split

Of Rocklogic's three options, recommend **"work out a ready-to-go setup together, we run
it"**, with two additions:

| Area | Owner |
| --- | --- |
| Hardware, Proxmox, network, VM lifecycle, backups | Guild |
| docker compose stack (charon + VC + EL/CL), client choice | Rocklogic provides, Guild runs |
| WireGuard config | Rocklogic provides, Guild installs in the VM |
| DKG ceremony, key share custody | Guild operator (never leaves the VM) |
| Monitoring | Rocklogic's integration **plus** our own Uptime Kuma / Prometheus ([MONITORING.md](MONITORING.md)) |
| Break-glass access | Optional: Rocklogic SSH key on **the VM only**, never the Proxmox hosts |

Why not hand over full SSH: the hosts hold root-level API tokens and PDM credentials for
the whole estate ([CLUSTER.md](CLUSTER.md) §9). Scoping their access to the one VM keeps the
blast radius at one key share.

Why not "own tooling, just give us cluster details": it drops their client-diversity plan
and monitoring, and we have no existing Ethereum tooling to bring.

---

## 6. Onboarding checklist

- [ ] Fill §1 TODOs (location, WAN speed, public IP / CGNAT, power)
- [ ] Verify the Guild-B target node (§2)
- [ ] Reply to Rocklogic (draft below)
- [ ] Agree client pair and receive compose stack + WireGuard config
- [ ] Clone VM, static IP, VM firewall, WireGuard up, clients syncing
- [ ] DKG ceremony with the other 6 operators
- [ ] Monitoring wired to both sides; Kuma monitor for the VM
- [ ] Fix the 100 Mb switch before mainnet discussion

---

## 7. Draft reply to Rocklogic

> hey dave, thanks for the warm welcome and the detailed rundown! 🙌
>
> quick picture of our side:
>
> - **infra:** self-hosted bare metal running Proxmox VE, two clusters (5 + 6 nodes). the
>   operator would run as a dedicated VM on the node with the most headroom (62 GB RAM,
>   multi-TB local storage), so it's not competing with anything heavy.
> - **location:** <city, country>
> - **connectivity:** <ISP, measured up/down>, <static public IP / dynamic / CGNAT>.
>   router is OpenWrt, so port forwarding is no problem <if not CGNAT>.
> - one honest caveat: our internal switching is currently 100 Mb, and upgrading it is
>   already at the top of our list. fine for a single hoodi operator, but we'll have it
>   sorted well before any mainnet talk.
>
> on the approach, the middle option suits us best: we'd love to take your prepared
> charon + VC compose setup, wireguard configs and recommended client pair, and run it
> ourselves. happy to plug into your monitoring too, and we'd run our own alongside.
> if it helps you debug, we can also give you an SSH key on the operator VM itself; we'd
> just rather keep the hypervisors on our side.
>
> a couple of questions back:
> - which client pair would you like us on, and what resources do you usually give an
>   operator (RAM / disk)?
> - which ports does the wireguard mesh need open, and is relay-only ok if we can't
>   accept inbound?
> - how do you usually run the DKG, all operators live on a call?
>
> looking forward to it!
