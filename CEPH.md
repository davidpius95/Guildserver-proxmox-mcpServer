# Ceph on Cluster Guild-A

Hyperconverged Ceph storage across the five-node Proxmox cluster **Guild-A**,
configured 2026-07-23. Status at build: **HEALTH_OK**.

---

## 1. What was built

A single Ceph RBD storage pool (`ceph-vm`) usable by every node for VM and
container disks, with 3× replication and self-healing across host failures.

| Component | Count | Where |
| --------- | ----- | ----- |
| Monitors (MON) | 3 | nodeE (`pve`), nodeA, nodeB |
| Managers (MGR) | 2 | nodeE (`pve`, active), nodeB (standby) |
| OSDs | 4 | nodeA, nodeB, nodeC, nodeD — one each |
| Pool | 1 | `ceph-vm` (RBD) |

- **Raw capacity:** ~943 GiB (4 × ~235 GiB SSD/NVMe)
- **Usable:** ~298 GiB (size=3 replication)
- **fsid:** `1a5dc75a-1f86-4467-ac56-1a4fc6ce6510`
- **Networks:** public & cluster both on `192.168.8.0/24` (single flat network)

### OSD → disk map

| OSD | Node | Device | Notes |
| --- | ---- | ------ | ----- |
| osd.0 | nodeA | /dev/nvme0n1 (256 GB) | was `pve-OLD-A322F7F4` (old install) |
| osd.1 | nodeB | /dev/sda (250 GB SSD) | was `pve-OLD-C21C0EF1` |
| osd.2 | nodeC | /dev/nvme0n1 (256 GB) | was `pve-OLD-8BA5A010` |
| osd.3 | nodeD | /dev/sda (250 GB SSD) | was orphaned ZFS pool |

**nodeE contributes no OSD** — it has only its single boot disk. It still runs a
monitor + the active manager, and can run guests on Ceph over the network.

---

## 2. How this was done (history)

1. **Disk audit.** Every node had a live `pve` LVM volume group *and* a leftover
   `pve-OLD-*` group (or orphaned ZFS on nodeD) from a previous install on a second
   disk. Which physical disk held the live OS was **not consistent** — nodeA/C boot
   from `sda`, nodeB/D from `nvme`. Verified per node with `pvs`, and confirmed the
   active UEFI boot partition (`efibootmgr` PARTUUID) sits on the *keep* disk in
   every case.
2. **Wiped the leftover disks** (nodeA nvme, nodeB sda, nodeC nvme, nodeD sda) with a
   guard that aborts if the live `pve` VG or root filesystem is on the target.
3. **Cleaned pre-cluster orphans.** nodeA/C/D each still ran a stale `ceph-mon@pve`
   and `ceph-mgr@pve` from their standalone days, squatting the Ceph ports. Removed
   them (nodeE's real `pve` mon/mgr left untouched, identified by its `.125` bind).
4. **Built Ceph:** added MONs on nodeA/nodeB, a standby MGR on nodeB, created the 4
   OSDs, created the `ceph-vm` pool, registered it as PVE storage, set
   `osd_memory_target=2 GiB` (nodes are 8–16 GB and also run guests), enabled the
   balancer.

---

## 3. Architecture

```
          Cluster Guild-A  (192.168.8.0/24)
 ┌─────────┬─────────┬─────────┬─────────┬─────────┐
 │ nodeA   │ nodeB   │ nodeC   │ nodeD   │ nodeE   │
 │ .112    │ .155    │ .156    │ .195    │ .125    │
 ├─────────┼─────────┼─────────┼─────────┼─────────┤
 │ MON     │ MON     │         │         │ MON     │  3 monitors → quorum
 │         │ MGR(sb) │         │         │ MGR(*)  │  2 managers
 │ OSD.0   │ OSD.1   │ OSD.2   │ OSD.3   │  —      │  4 OSDs
 └─────────┴─────────┴─────────┴─────────┴─────────┘
                    │
              pool: ceph-vm  (size=3, min_size=2)
              PVE storage: ceph-vm (rbd, content=images,rootdir)
```

- **Failure domain = host.** Each object is replicated to 3 different nodes, so the
  cluster tolerates **1 node down** with no data loss and stays read-write
  (`min_size=2`). A 2nd node down pauses writes to affected PGs until recovery.
- **Autoscaler on** — PG count (128) self-tunes as usage grows.
- **Balancer on (upmap)** — evens data across OSDs automatically.

---

## 4. How to use it

### Create a VM on Ceph
In the PVE web UI, pick storage **ceph-vm** for the disk. Or via the MCP:

```bash
# disk on Ceph instead of local-lvm:
pve_call POST nodes/nodeA/qemu   {vmid, scsi0:"ceph-vm:32", ...}   # 32 GB
```

### Create a container on Ceph

```bash
pve_call POST nodes/nodeA/lxc    {vmid, rootfs:"ceph-vm:8", ...}
```

### Move an existing guest onto Ceph
Guests currently live on `local-lvm`. To move one (enables live migration):

```bash
# VM disk:
pve_call POST nodes/<node>/qemu/<vmid>/move_disk   {disk:"scsi0", storage:"ceph-vm", delete:1}
# container volume (must be stopped):
pve_call POST nodes/<node>/lxc/<vmid>/move_volume  {volume:"rootfs", storage:"ceph-vm", delete:1}
```

### Live-migrate a Ceph-backed VM between nodes
Because the disk is shared, migration copies only RAM — seconds, no downtime:

```bash
pve_call POST nodes/nodeA/qemu/<vmid>/migrate   {target:"nodeC", online:1}
```

### Check health

```bash
ssh root@192.168.8.125 ceph -s          # overall
ssh root@192.168.8.125 ceph osd df tree # per-OSD usage
# or over the MCP:
pve_call GET nodes/nodeA/ceph/status
```

---

## 5. Operations

**Expand capacity** — add a disk to a node, then:
```bash
ssh root@<node> pveceph osd create /dev/<newdisk>
```
Adding an OSD on **nodeE** (once it has a spare disk) would also improve balance.

**Replace a failed disk:**
```bash
ssh root@<node> "ceph osd out osd.<id>; systemctl stop ceph-osd@<id>; pveceph osd destroy <id>"
# swap disk, then: pveceph osd create /dev/<newdisk>
```

**Node maintenance (reboot):** set a no-out flag so Ceph doesn't rebalance during a
short reboot:
```bash
ssh root@192.168.8.125 ceph osd set noout   # before
ssh root@192.168.8.125 ceph osd unset noout # after
```

**Tuning already applied:** `osd_memory_target = 2 GiB` (was 4 GiB default) to fit the
8–16 GB nodes. Raise it on RAM-rich nodes if guests are light.

---

## 6. Caveats specific to this cluster

- **No dedicated Ceph network.** Public + cluster traffic share the single
  `192.168.8.0/24` LAN. Fine for a homelab; heavy rebuild traffic will compete with
  VM/LAN traffic. A second NIC for `cluster_network` would isolate it.
- **4 OSDs / 5 nodes, one HDD-era node has no OSD.** Capacity is modest (~298 GiB
  usable). Replication is 3×, so real usable space is a third of raw.
- **nodeC has 8 GB RAM** and runs mon-less but an OSD + guests — the memory tuning
  above matters most there.
- **Monitors are on nodeA/B/E.** If you later rename or reinstall a mon node, recreate
  its mon; keep the count odd (3 or 5) for quorum.
