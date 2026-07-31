# netboot.xyz on Guild-A

Production runbook for the Cluster A netboot.xyz service deployed on 2026-07-30.

## Topology

| Component | Value |
| --- | --- |
| Service VM | VM 220 `netboot-xyz` on nodeE |
| Operating system | Debian 13 |
| Resources | 2 cores, 2 GiB RAM, 16 GiB Ceph disk |
| Main LAN | `192.168.8.20/24`, gateway `192.168.8.1` |
| VLAN 50 | `192.168.50.20/24`, no default gateway |
| Web dashboard | `http://192.168.8.20:3000` |
| TFTP | `192.168.8.20:69/udp` |
| Local asset HTTP | `http://192.168.8.20:8080` |
| Compose source | `netboot-xyz/compose.yaml` |
| Remote deployment | `/opt/netbootxyz` on VM 220 |

The VM has two NICs so the working management LAN can provide PXE while the
pre-existing VLAN 50 fan-out issue is investigated separately.

## Router DHCP

The GL-MT6000 advertises:

```text
boot file: netboot.xyz.kpxe
TFTP server name: netbootxyz
next server: 192.168.8.20
```

LuCI path:

```text
Network > DHCP and DNS > TFTP Settings
```

The saved `Network boot image` value is:

```text
netboot.xyz.kpxe,netbootxyz,192.168.8.20
```

LuCI 21.02 only persists that dependent field while `Enable TFTP server` is
enabled. The router therefore advertises the external next-server while VM 220
serves the requested file.

This configuration matches the video's legacy BIOS/SeaBIOS Proxmox flow. The
single LuCI boot field is not architecture-aware; add dnsmasq architecture
matches before enabling UEFI PXE clients cluster-wide.

## Deployment

```bash
ssh -i ~/.ssh/proxmox_guild_a guildvm@192.168.8.20
cd /opt/netbootxyz
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps
```

Persistent data:

```text
/opt/netbootxyz/config
/opt/netbootxyz/assets
```

The container uses TFTP single-port mode so only UDP 69 is required.

## Offline Assets

The web dashboard's `Local Assets` screen has cached the Breakin hardware
diagnostic utility:

```text
asset-mirror/releases/download/4.26.1-f22abf78/vmlinuz
asset-mirror/releases/download/4.26.1-f22abf78/initrd
```

The cached initrd is 68,915,588 bytes and is available through the local asset
HTTP service. Add operating-system assets selectively because VM 220 currently
has a 16 GiB disk.

Windows appears in the boot menu, but unattended Windows installation still
requires separately supplied WinPE/installation media. No licensed Windows
image was provided or copied during this deployment.

## Verification

VM 101 `netboot-pxe-test` is a diskless, stopped-by-default SeaBIOS regression
VM on nodeE.

Observed end-to-end:

1. Router DHCP offered `192.168.8.127` to the test VM.
2. DHCP option 66 identified `netbootxyz`.
3. DHCP option 67 identified `netboot.xyz.kpxe`.
4. DHCP `siaddr`/next-server was `192.168.8.20`.
5. VM 220 sent the complete 410,421-byte iPXE image.
6. The test VM displayed the netboot.xyz 3.0.2 menu.
7. The dashboard, local asset HTTP endpoint, and container health checks passed.

Visual evidence:

```text
netboot-xyz/evidence/netboot-menu.png
```

Repeat the PXE check:

```bash
ssh nodeE 'qm start 101'
ssh nodeE "pvesh create /nodes/nodeE/qemu/101/monitor --command 'screendump /tmp/netboot-pxe.ppm'"
ssh nodeE 'qm stop 101'
```

Service checks:

```bash
curl -f http://192.168.8.20:3000/
curl -f http://192.168.8.20:8080/
tftp 192.168.8.20 -c get netboot.xyz.kpxe
ssh -i ~/.ssh/proxmox_guild_a guildvm@192.168.8.20 \
  'cd /opt/netbootxyz && sudo docker compose config -q && sudo docker compose ps'
```

## Recovery

Restart the service:

```bash
ssh -i ~/.ssh/proxmox_guild_a guildvm@192.168.8.20 \
  'cd /opt/netbootxyz && sudo docker compose restart'
```

Disable network boot without affecting normal DHCP:

1. Open LuCI `Network > DHCP and DNS > TFTP Settings`.
2. Clear `Network boot image`.
3. Disable `Enable TFTP server`.
4. Select `Save & Apply`.

Remove the deployment while retaining data:

```bash
ssh -i ~/.ssh/proxmox_guild_a guildvm@192.168.8.20 \
  'cd /opt/netbootxyz && sudo docker compose down'
```

Do not delete `/opt/netbootxyz/config` or `/opt/netbootxyz/assets` unless the
menus and cached assets are intentionally being discarded.

## VLAN 50 Status

VLAN 50 is configured correctly on the router's `lan2` trunk and on Proxmox
`vmbr0`. Packet capture proved VM 220's tagged ARP frames leave nodeE, but the
same broadcast is not visible on nodeC and the router does not answer it. The
remaining fault is therefore in the physical fan-out switch or its port VLAN
configuration, not in netboot.xyz. PXE is currently served on the working
`192.168.8.0/24` LAN.
