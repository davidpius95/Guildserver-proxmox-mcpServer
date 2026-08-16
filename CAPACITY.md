# Capacity — network, storage and workload placement

Where the real limits are, and what the platform can and cannot do about them.

> Cluster source of truth: **[CLUSTER.md](CLUSTER.md)** · Backups: **[BACKUPS.md](BACKUPS.md)**
> · Monitoring: **[MONITORING.md](MONITORING.md)**

**Last verified 2026-08-16.**

---

## The binding constraint is the network, not the hardware

**Every node in both clusters negotiates 100 Mb/s — on NICs that support gigabit or better.**

```
Supported link modes:     10baseT … 100baseT … 1000baseT/Full   ← NIC can do gigabit
Advertised link modes:    10baseT … 100baseT … 1000baseT/Full   ← NIC is asking for it
Link partner advertised:  10baseT … 100baseT/Full               ← far end offers none
```

The NICs advertise gigabit; the far end does not. One node advertises **2500baseT/Full** and
still lands at 100 Mb — running at **1/25th** of capability.

Because *every* port across both clusters shows the identical pattern, this is almost
certainly **the switch being a 10/100 unit**, not a batch of bad cables. (A single bad cable
does cause this — gigabit needs all four pairs and a 2-pair cable negotiates 100 Mb max — but
not on eleven ports at once.)

### Why it matters more than it looks

That **~12.5 MB/s ceiling carries everything**:

- Ceph replication — the pool is `size=3`, so every write crosses the wire multiple times
- corosync — latency-sensitive; saturation risks cluster instability
- vzdump backups to PBS
- Tailscale, and all service traffic

It is the most likely explanation for the recorded Ceph/etcd iowait fragility, and it is why
migrating a 200 GiB disk took **6 h 28 m** instead of roughly 25 minutes.

### Check and verify

```bash
ethtool nic0 | grep -A4 "Link partner advertised"
```

Success looks like `1000baseT/Full` appearing in the **link partner** block. After that,
raise the backup `bwlimit` well above 5000 KiB/s — it was chosen for a 100 Mb link.

**Fixing this switch is the single highest-value change available.** Roughly 10× network
capacity estate-wide.

---

## There is no automatic workload distribution

**Proxmox has no DRS equivalent.** Nothing rebalances guests based on load. Both clusters
have empty `/etc/pve/ha/resources.cfg` and `groups.cfg`, and `datacenter.cfg` carries no
bwlimit or migration settings.

What is actually achievable:

| Want | Reality |
| --- | --- |
| Auto-rebalancing by load | Not available. Would need PDM-driven scheduled migrations or custom scripting. |
| Failover placement | HA groups with priorities — **requires shared storage** |
| Even placement | Deliberate manual placement, informed by the headroom table below |
| Not overwhelming a node | Staggered + throttled jobs (see BACKUPS.md), plus alerting before saturation |

**Guild-B has no shared storage at all** — `local`, `local-lvm` and the PBS entry only. No
Ceph. That means **no live migration and no HA on Guild-B**, whatever gets configured. Its
storage is abundant but node-local, so guests cannot move without a full disk copy.

Guild-A has Ceph (`ceph-vm`, size=3), so HA is possible there for Ceph-backed guests.

---

## Headroom

CPU is not the constraint anywhere — it ran 1–7% across both clusters. **RAM is the binding
resource on Guild-A; storage is abundant on Guild-B.**

### Guild-A — RAM is tight, storage is not

| Node | RAM used | Notes |
| --- | --- | --- |
| nodeA | ~49 % | |
| nodeB | ~33 % | most RAM headroom |
| nodeC | ~46 % | **only half the RAM of the others**; now hosts PBS |
| nodeD | ~75 % | highest — avoid adding here |
| nodeE | ~57 % | |

Local thin pools: nodeA/B/D ~141–144 G each at ~0 %, **nodeC 338 G**, nodeE 152 G (freed when
PBS moved off). Ceph `ceph-vm` had ~122 GiB `MAX AVAIL`.

### Guild-B — storage is abundant

~**13.7 TB of thin pool across six nodes, under 3 % used.** RAM varies widely: one node has
62 GB at ~19 %, another 31 GB at ~60 %, the rest 15 GB at 12–55 %.

This is the inverse of Guild-A, and worth remembering when placing anything storage-heavy.

---

## Traps already paid for

**A thin volume can be larger than the pool backing it.** PBS ran a 200 G volume on a 137 G
pool; when the pool filled, QEMU paused the VM with `io-error` and it went unnoticed for
36 hours. Always check `lvs -o lv_size,data_percent,lv_attr` before assuming a guest's disk
size is real capacity. Full write-up in [BACKUPS.md](BACKUPS.md).

**Version skew accumulates silently when apt is broken.** A node whose only Proxmox repos
were the enterprise ones (401 without a subscription) quietly missed 141 updates and drifted
behind its peers. Check `apt-get -s upgrade | grep -c '^Inst'` on any node that has been
quiet.

**Storage capacity and storage mobility are different problems.** Guild-B has terabytes free
and cannot move a guest without copying it; Guild-A can live-migrate Ceph-backed guests but
has far less room. Place workloads against the constraint that actually binds.
