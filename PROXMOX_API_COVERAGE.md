## Proxmox API Coverage (ProxmoxMCP-Plus)

Reference: Proxmox API Viewer: [https://pve.proxmox.com/pve-docs/api-viewer/](https://pve.proxmox.com/pve-docs/api-viewer/)

Legend:
- [Implemented]: Exposed by this project as MCP/OpenAPI endpoints today
- [Planned]: Natural next additions (high impact/common)
- [Missing]: Not yet implemented

### Implemented MCP/OpenAPI Endpoints (current)
- [Implemented] POST /get_nodes → Proxmox: GET /nodes
- [Implemented] POST /get_node_status → GET /nodes/{node}/status
- [Implemented] POST /get_vms → GET /nodes/{node}/qemu (+ GET /nodes/{node}/qemu/{vmid}/config)
- [Implemented] POST /get_vm_status → GET /nodes/{node}/qemu/{vmid}/status/current
- [Implemented] POST /get_vm_snapshots → GET /nodes/{node}/qemu/{vmid}/snapshot
- [Implemented] POST /create_vm → POST /nodes/{node}/qemu
- [Implemented] POST /execute_vm_command → POST /nodes/{node}/qemu/{vmid}/agent/exec
- [Implemented] POST /start_vm → POST /nodes/{node}/qemu/{vmid}/status/start
- [Implemented] POST /stop_vm → POST /nodes/{node}/qemu/{vmid}/status/stop
- [Implemented] POST /shutdown_vm → POST /nodes/{node}/qemu/{vmid}/status/shutdown
- [Implemented] POST /reset_vm → POST /nodes/{node}/qemu/{vmid}/status/reset
- [Implemented] POST /delete_vm → DELETE /nodes/{node}/qemu/{vmid}
- [Implemented] POST /get_containers → GET /nodes/{node}/lxc (+ status/current, config)
- [Implemented] POST /get_container_status → GET /nodes/{node}/lxc/{vmid}/status/current
- [Implemented] POST /start_container → POST /nodes/{node}/lxc/{vmid}/status/start
- [Implemented] POST /stop_container → POST /nodes/{node}/lxc/{vmid}/status/{stop|shutdown}
- [Implemented] POST /restart_container → POST /nodes/{node}/lxc/{vmid}/status/reboot
- [Implemented] POST /get_storage → GET /storage (+ per-node storage status)
- [Implemented] POST /get_storage_content → GET /nodes/{node}/storage/{storage}/content
- [Implemented] POST /get_cluster_status → GET /cluster/status
- [Implemented] POST /get_cluster_resources → GET /cluster/resources

---

### VM (QEMU) Management
- [Missing] GET /nodes/{node}/qemu/{vmid}/status/current (expose as endpoint)
- [Planned] POST /nodes/{node}/qemu/{vmid}/migrate
- [Planned] POST /nodes/{node}/qemu/{vmid}/clone
- [Planned] POST /nodes/{node}/qemu/{vmid}/template (convert to template)
- [Planned] POST /nodes/{node}/qemu/{vmid}/resize (disk)
- [Planned] POST /nodes/{node}/qemu/{vmid}/config (update VM config)
- [Planned] POST /nodes/{node}/qemu/{vmid}/monitor, /sendkey
- [Planned] POST /nodes/{node}/qemu/{vmid}/agent/* (beyond exec: fsfreeze/fsthaw, get-time, ping, network-get-interfaces, set-user-password, etc.)
- [Planned] POST /nodes/{node}/qemu/{vmid}/spiceproxy, /vncproxy, /vncwebsocket
- [Planned] POST /nodes/{node}/qemu/{vmid}/snapshot (create), GET (list), DELETE (remove), POST rollback
- [Planned] POST /nodes/{node}/qemu (restore from backup) with restore params
- [Missing] POST /nodes/{node}/qemu/{vmid}/move_disk, /importdisk, attach/detach disk
- [Missing] Cloud-Init helpers (set ciuser, cipassword, ssh keys via config)

### Container (LXC) Management
- [Missing] GET /nodes/{node}/lxc/{vmid}/status/current (expose directly)
- [Planned] POST /nodes/{node}/lxc (create), DELETE /nodes/{node}/lxc/{vmid}
- [Planned] GET/POST /nodes/{node}/lxc/{vmid}/config (update)
- [Planned] Snapshot ops: /nodes/{node}/lxc/{vmid}/snapshot (list/create/rollback/delete)
- [Planned] Console/VNC where supported

### Storage
- [Planned] GET /nodes/{node}/storage/{storage}/content (list)
- [Planned] POST /nodes/{node}/storage/{storage}/upload, DELETE content
- [Missing] GET /nodes/{node}/storage/{storage}/status, rrd/rrddata (expose directly)
- [Missing] Storage scans/probes, volume management helpers

### Cluster
- [Implemented] GET /cluster/status
- [Planned] GET /cluster/resources, /cluster/tasks
- [Planned] HA: /cluster/ha (groups/resources/fencing)
- [Planned] Replication: /cluster/replication
- [Planned] Firewall (DC): /cluster/firewall/*
- [Planned] ACME: /cluster/acme
- [Planned] SDN: /cluster/sdn/*
- [Planned] Ceph (cluster-level): /cluster/ceph/*

### Node
- [Planned] GET /nodes (already used internally) and /nodes/{node}
- [Planned] Node power: POST /nodes/{node}/status (reboot/shutdown)
- [Planned] Services: /nodes/{node}/services (start/stop/restart)
- [Planned] Network: /nodes/{node}/network (list/apply bridges/bonds/VLANs)
- [Planned] Updates/APT: /nodes/{node}/apt (update/upgrade/repos)
- [Planned] Certificates: /nodes/{node}/certificates/*
- [Planned] Tasks: /nodes/{node}/tasks/{upid}/status, /log
- [Planned] Metrics: /nodes/{node}/rrd, /rrddata
- [Planned] Disks & ZFS/LVM tools: /nodes/{node}/disks/*
- [Planned] Ceph (node-level): /nodes/{node}/ceph/*

### Access Control & Identity
- [Missing] Users: /access/users (list/create/update/delete)
- [Missing] Groups: /access/groups
- [Missing] Roles: /access/roles
- [Missing] ACLs: /access/acl
- [Missing] Tokens/API keys: /access/users/{user}/token/*
- [Missing] TFA: /access/tfa/*

### Pools
- [Missing] /pools (list/create/delete, add/remove members)

### Backups (VZDump)
- [Planned] /nodes/{node}/vzdump (create), and job scheduling endpoints

### Version & Misc
- [Planned] GET /version (already used internally for connectivity check; can expose)

---

## Summary
- Implemented today: Nodes listing/status; VMs listing/create/power/delete; VM agent exec; LXC listing/start/stop/restart; Storage listing & content; Cluster status & resources; VM status & snapshots; Container status.
- Phase 2 generic coverage: Any remaining Proxmox API endpoint can be called via `proxmox_request`.

For details of every parameter and response, see the official API viewer: [https://pve.proxmox.com/pve-docs/api-viewer/](https://pve.proxmox.com/pve-docs/api-viewer/)


