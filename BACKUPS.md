# Backups — Proxmox Backup Server & vzdump jobs

How both clusters back up, where PBS lives, and the failure modes already paid for.

> Cluster source of truth: **[CLUSTER.md](CLUSTER.md)** · Monitoring: **[MONITORING.md](MONITORING.md)**
> · Network constraint behind the timings here: **[CAPACITY.md](CAPACITY.md)**

**Last verified 2026-08-16.**

---

## Shape

One PBS instance backs up **both** clusters.

| | |
| --- | --- |
| PBS | VM 400 `guild-pbs`, **on nodeC** (moved from nodeE 2026-08-16) |
| Web UI | `https://<pbs-ip>:8007` — self-signed cert |
| Login | `root@pam` — **PAM realm**, so it is the VM's Linux root password |
| Datastore | `guild-a-standard` at `/mnt/datastore/guild-a`, 7-day retention |
| Disk | `local-lvm:vm-400-disk-0`, 200 G, `discard=on` — **not Ceph** |
| Version | PBS 4.2.5 |

Accounts: only `root@pam` (Superuser) and `backup@pbs` (service account).
API tokens `backup@pbs!pve-cluster` and `backup@pbs!guild-b-cluster` —
**API tokens cannot log into the web UI.**

### Backup jobs

| Job | Schedule | bwlimit | Excludes |
| --- | --- | --- | --- |
| `guild-a-standard-daily` | 02:00 | 5000 KiB/s | static templates 9000–9020 |
| `guild-b-standard-daily` | 04:00 | 5000 KiB/s | 300, 400 (see `docs/decisions/2026-08-08-g18-pbs-capacity.md`) |

`bwlimit 5000` ≈ 40 Mb/s, roughly a third of the 100 Mb link, deliberately leaving headroom
for Ceph and corosync. **Raise it once the network is gigabit** — see CAPACITY.md.

---

## Trap 1 — thin-pool exhaustion pauses the VM (`io-error`)

**This took PBS down for ~36 h unnoticed on 2026-08-15.**

PBS's disk is a **200 G thin volume**. If the host's LVM thin pool is smaller than the
volume, the guest can allocate more than physically exists. When the pool fills, QEMU
pauses the VM:

```
qm status 400   →   status: io-error
pvesm status    →   guild-pbs  inactive
                    error fetching datastores - 500 Can't connect ... (No route to host)
```

Kernel log is unambiguous:

```
device-mapper: thin: reached low water mark for data device: sending event.
device-mapper: thin: switching pool to out-of-data-space (queue IO) mode
device-mapper: thin: switching pool to out-of-data-space (error IO) mode
```

**Diagnose:**

```bash
lvs -o lv_name,lv_size,data_percent,metadata_percent,lv_attr
```

The tell is the **`D`** in `twi-aotzD-` — pool is out of data space. `Data%` reads `100.00`.

**Recover:**

```bash
lvextend -L +15G pve/data     # if the VG has free extents
qm resume 400
```

**Ceph is a red herring here.** It was `HEALTH_OK` throughout — PBS is on local LVM, not Ceph.

### The real fix: stop the overcommit

Moved PBS nodeE → nodeC, which has a 338 G pool and no other guests:

| | before (nodeE) | after (nodeC) |
| --- | --- | --- |
| pool size | 152.11 G | **338.21 G** |
| pool used | 90 % | **39.7 %** |
| overcommit | 200 G volume on 152 G pool | none |

```bash
qm migrate 400 nodeC --with-local-disks --bwlimit 9000
```

Took **6 h 28 m** for 200 GiB at 9.2 MB/s — entirely network-bound. On gigabit it would be
~25 minutes. **Run `qm start` on the target node**, not the source.

**Why not Ceph:** `MAX AVAIL` was 122 GiB against ~137 GiB needed, and backups on 3×
replication would consume 600 GB raw to store 200 GB. Wrong tool for backup data.

---

## Trap 2 — no GC or prune job is configured by default

The datastore was labelled "7-day retention" but **`/etc/proxmox-backup/prune.cfg` did not
exist** and no garbage collection was scheduled. Backups accumulated indefinitely.

```bash
proxmox-backup-manager datastore update guild-a-standard --gc-schedule daily
```

Note GC holds a 24 h grace period on chunks, so the first run reclaims little; the rest
comes on the next run.

**Check whether pruning would even help before assuming it will.** Here it would not have:
all 170 snapshots were inside the 7-day window. Dedup was already excellent —
**6.47 TiB original → 128 GiB on disk, factor 51.79**. It was a capacity problem, not a
retention one.

---

## Trap 3 — both clusters backing up at the same minute

Both jobs shipped with `schedule 02:00`, `all 1` and **no `bwlimit`**, writing to the same
PBS over a 100 Mb link — 11 nodes and ~35 guests simultaneously. That is what filled the
pool. Guild-A additionally had no exclusions and was backing up ten static templates nightly.

Staggered to 02:00 / 04:00 and throttled. Verify with:

```bash
pvesh get /cluster/backup --output-format json
```

---

## Monitoring

PBS had **no monitor at all**, which is why a 36 h outage went unnoticed. Uptime Kuma now
watches both the host and `:8007` — see [MONITORING.md](MONITORING.md).

Worth adding but not yet done: an alert on **LVM thin-pool utilisation** on whichever node
hosts PBS. That is the signal that would have given warning before the outage, rather than
after it.
