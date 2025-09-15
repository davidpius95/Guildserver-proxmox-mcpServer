"""
Tool descriptions for Proxmox MCP tools.
"""

# Node tool descriptions
GET_NODES_DESC = """List all nodes in the Proxmox cluster with their status, CPU, memory, and role information.

Example:
{"node": "pve1", "status": "online", "cpu_usage": 0.15, "memory": {"used": "8GB", "total": "32GB"}}"""

GET_NODE_STATUS_DESC = """Get detailed status information for a specific Proxmox node.

Parameters:
node* - Name/ID of node to query (e.g. 'pve1')

Example:
{"cpu": {"usage": 0.15}, "memory": {"used": "8GB", "total": "32GB"}}"""

# VM tool descriptions
GET_VMS_DESC = """List all virtual machines across the cluster with their status and resource usage.

Example:
{"vmid": "100", "name": "ubuntu", "status": "running", "cpu": 2, "memory": 4096}"""

CREATE_VM_DESC = """Create a new virtual machine with specified configuration.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - New VM ID number (e.g. '200', '300')
name* - VM name (e.g. 'my-new-vm', 'web-server')
cpus* - Number of CPU cores (e.g. 1, 2, 4)
memory* - Memory size in MB (e.g. 2048 for 2GB, 4096 for 4GB)
disk_size* - Disk size in GB (e.g. 10, 20, 50)
storage - Storage name (optional, will auto-detect if not specified)
ostype - OS type (optional, default: 'l26' for Linux)

Examples:
- Create VM with 1 CPU, 2GB RAM, 10GB disk: node='pve', vmid='200', name='test-vm', cpus=1, memory=2048, disk_size=10
- Create VM with 2 CPUs, 4GB RAM, 20GB disk: node='pve', vmid='201', name='web-server', cpus=2, memory=4096, disk_size=20"""

EXECUTE_VM_COMMAND_DESC = """Execute commands in a VM via QEMU guest agent.

Parameters:
node* - Host node name (e.g. 'pve1')
vmid* - VM ID number (e.g. '100')
command* - Shell command to run (e.g. 'uname -a')

Example:
{"success": true, "output": "Linux vm1 5.4.0", "exit_code": 0}"""

# VM Power Management tool descriptions
START_VM_DESC = """Start a virtual machine.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')

Example:
Power on VPN-Server with ID 101 on node pve"""

STOP_VM_DESC = """Stop a virtual machine (force stop).

Parameters:
node* - Host node name (e.g. 'pve')  
vmid* - VM ID number (e.g. '101')

Example:
Force stop VPN-Server with ID 101 on node pve"""

SHUTDOWN_VM_DESC = """Shutdown a virtual machine gracefully.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')

Example:
Gracefully shutdown VPN-Server with ID 101 on node pve"""

RESET_VM_DESC = """Reset (restart) a virtual machine.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')

Example:
Reset VPN-Server with ID 101 on node pve"""

DELETE_VM_DESC = """Delete/remove a virtual machine completely.

⚠️ WARNING: This operation permanently deletes the VM and all its data!

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '998')
force - Force deletion even if VM is running (optional, default: false)

This will permanently remove:
- VM configuration
- All virtual disks
- All snapshots
- Cannot be undone!

Example:
Delete test VM with ID 998 on node pve"""

# Container tool descriptions
GET_CONTAINERS_DESC = """List LXC containers across the cluster (or filter by node).

Parameters:
- node (optional): Node name to filter (e.g. 'pve1')
- include_stats (bool, default true): Include live CPU/memory stats
- include_raw (bool, default false): Include raw Proxmox API payloads for debugging
- format_style ('pretty'|'json', default 'pretty'): Pretty text or raw JSON list

Notes:
- Live stats from /nodes/{node}/lxc/{vmid}/status/current.
- If maxmem is 0 (unlimited), memory limit falls back to /config.memory (MiB).
- If live returns zeros, the most recent RRD sample is used as a fallback.
- Fields provided: cores (CPU cores/cpulimit), memory (MiB limit), cpu_pct, mem_bytes, maxmem_bytes, mem_pct, unlimited_memory.
"""

START_CONTAINER_DESC = """Start one or more LXC containers.
selector: '123' | 'pve1:123' | 'pve1/name' | 'name' | comma list
Example: start_container selector='pve1:101,pve2/web'
"""

STOP_CONTAINER_DESC = """Stop LXC containers. graceful=True uses shutdown; otherwise force stop.
selector: same grammar as start_container
timeout_seconds: 10 (default)
"""

RESTART_CONTAINER_DESC = """Restart LXC containers (reboot).
selector: same grammar as start_container
"""

# Storage tool descriptions
GET_STORAGE_DESC = """List storage pools across the cluster with their usage and configuration.

Example:
{"storage": "local-lvm", "type": "lvm", "used": "500GB", "total": "1TB"}"""

# Cluster tool descriptions
GET_CLUSTER_STATUS_DESC = """Get overall Proxmox cluster health and configuration status.

Example:
{"name": "proxmox", "quorum": "ok", "nodes": 3, "ha_status": "active"}"""

# Additional detailed descriptions for newly added wrappers
GET_VM_STATUS_DESC = """Get current VM status (maps to /nodes/{node}/qemu/{vmid}/status/current).

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')

Example:
{"status": "running", "maxmem": 4294967296, "name": "vm-100"}
"""

GET_VM_SNAPSHOTS_DESC = """List VM snapshots (maps to /nodes/{node}/qemu/{vmid}/snapshot).

Parameters:
node* - Host node name
vmid* - VM ID number
"""

CREATE_VM_SNAPSHOT_DESC = """Create VM snapshot.

Parameters:
node* - Host node name
vmid* - VM ID number
snapname* - Snapshot name (e.g. 'pre-upgrade')
vmstate - Include RAM state (true/false)
description - Optional description
"""

DELETE_VM_SNAPSHOT_DESC = """Delete VM snapshot.

Parameters:
node* - Host node name
vmid* - VM ID number
snapname* - Snapshot name
"""

ROLLBACK_VM_SNAPSHOT_DESC = """Rollback VM snapshot.

Parameters:
node* - Host node name
vmid* - VM ID number
snapname* - Snapshot name
"""

CLONE_VM_DESC = """Clone VM (maps to /nodes/{node}/qemu/{vmid}/clone).

Parameters:
node* - Source node
vmid* - Source VM ID
target - Target node
newid - New VM ID
name - New VM name
full - Full clone (true/false)
storage - Target storage
"""

MIGRATE_VM_DESC = """Migrate VM to another node (maps to /nodes/{node}/qemu/{vmid}/migrate).

Parameters:
node* - Source node
vmid* - VM ID
target* - Target node
online - Online migration (true/false)
"""

UPDATE_VM_CONFIG_DESC = """Update VM configuration (maps to /nodes/{node}/qemu/{vmid}/config).

Parameters:
node* - Node
vmid* - VM ID
changes* - Object of config keys to update (e.g., {"cores": 2, "memory": 4096})
"""

RESIZE_VM_DISK_DESC = """Resize VM disk (maps to /nodes/{node}/qemu/{vmid}/resize).

Parameters:
node* - Node
vmid* - VM ID
disk* - Disk name (e.g. 'scsi0')
size* - Resize string (e.g. '+10G')
"""

GET_CONTAINER_STATUS_DESC = """Get container status (maps to /nodes/{node}/lxc/{vmid}/status/current).

Parameters:
node* - Host node name
vmid* - Container ID
"""

CREATE_CONTAINER_DESC = """Create LXC container (maps to /nodes/{node}/lxc).

Parameters:
node* - Host node name
config* - Create params (e.g., {"vmid": 200, "hostname": "ct-200", "rootfs": "local-lvm:8"})
"""

UPDATE_CONTAINER_CONFIG_DESC = """Update LXC configuration (maps to /nodes/{node}/lxc/{vmid}/config).

Parameters:
node* - Host node name
vmid* - Container ID
changes* - Config changes object
"""

LIST_CONTAINER_SNAPSHOTS_DESC = """List LXC snapshots (maps to /nodes/{node}/lxc/{vmid}/snapshot)."""
CREATE_CONTAINER_SNAPSHOT_DESC = """Create LXC snapshot."""
DELETE_CONTAINER_SNAPSHOT_DESC = """Delete LXC snapshot."""
ROLLBACK_CONTAINER_SNAPSHOT_DESC = """Rollback LXC snapshot."""

GET_TASK_STATUS_DESC = """Get node task status by UPID (maps to /nodes/{node}/tasks/{upid}/status)."""
GET_TASK_LOG_DESC = """Get node task log by UPID (maps to /nodes/{node}/tasks/{upid}/log)."""

GET_CLUSTER_RESOURCES_DESC = """Get cluster resources (maps to /cluster/resources)."""
GET_VERSION_DESC = """Get Proxmox API version info (maps to /version)."""

LIST_USERS_DESC = """List users (maps to /access/users)."""
CREATE_USER_DESC = """Create user (POST /access/users).

Parameters:
user* - userid (e.g. 'user@pve')
password - password (optional)
comment - comment
expire - expiry epoch
enable - enable (true/false)
"""
UPDATE_USER_DESC = """Update user (PUT /access/users/{userid})."""
DELETE_USER_DESC = """Delete user (DELETE /access/users/{userid})."""

LIST_GROUPS_DESC = """List groups (GET /access/groups)."""
CREATE_GROUP_DESC = """Create group (POST /access/groups)."""
DELETE_GROUP_DESC = """Delete group (DELETE /access/groups/{groupid})."""

LIST_ROLES_DESC = """List roles (GET /access/roles)."""
CREATE_ROLE_DESC = """Create role (POST /access/roles).

Parameters:
roleid* - Role ID
privs* - Privilege string (comma-separated)
"""
DELETE_ROLE_DESC = """Delete role (DELETE /access/roles/{roleid})."""

GET_ACL_DESC = """Get ACL (GET /access/acl)."""
SET_ACL_DESC = """Set ACL (PUT /access/acl).

Parameters:
path* - ACL path (e.g. '/vms/100')
roles - CSV of roles
users - CSV of users
groups - CSV of groups
propagate - propagate flag (true/false)
delete - delete flag (true/false)
"""

LIST_DC_FW_RULES_DESC = """List datacenter firewall rules (GET /cluster/firewall/rules)."""
ADD_DC_FW_RULE_DESC = """Add datacenter firewall rule (POST /cluster/firewall/rules)."""
DELETE_DC_FW_RULE_DESC = """Delete datacenter firewall rule by position (DELETE /cluster/firewall/rules/{pos})."""

LIST_POOLS_DESC = """List pools (GET /pools)."""
CREATE_POOL_DESC = """Create pool (POST /pools)."""
DELETE_POOL_DESC = """Delete pool (DELETE /pools/{poolid})."""

VZDUMP_DESC = """Trigger VZDump backup (POST /nodes/{node}/vzdump).

Parameters:
node* - Node
params* - Backup params (e.g., {"mode": "snapshot", "storage": "local", "vmid": "100"})
"""

LIST_SERVICES_DESC = """List node services (GET /nodes/{node}/services)."""
SERVICE_ACTION_DESC = """Node service action (POST /nodes/{node}/services/{service}/{action}) where action is start|stop|restart."""
NETWORK_GET_DESC = """Get node network configuration (GET /nodes/{node}/network)."""
NETWORK_APPLY_DESC = """Apply node network configuration (POST /nodes/{node}/network/apply)."""
LIST_UPDATES_DESC = """List available updates (GET /nodes/{node}/apt/update)."""
LIST_REPOS_DESC = """List APT repositories (GET /nodes/{node}/apt/repositories)."""
GET_CERTS_DESC = """Get node certificates info (GET /nodes/{node}/certificates/info)."""
LIST_DISKS_DESC = """List node disks (GET /nodes/{node}/disks/list)."""

HA_LIST_GROUPS_DESC = """List HA groups (GET /cluster/ha/groups)."""
HA_CREATE_GROUP_DESC = """Create HA group (POST /cluster/ha/groups)."""
HA_LIST_RESOURCES_DESC = """List HA resources (GET /cluster/ha/resources)."""
HA_ADD_RESOURCE_DESC = """Add HA resource (POST /cluster/ha/resources)."""
HA_DELETE_RESOURCE_DESC = """Delete HA resource (DELETE /cluster/ha/resources/{sid})."""

REPL_LIST_JOBS_DESC = """List replication jobs (GET /cluster/replication)."""
REPL_CREATE_JOB_DESC = """Create replication job (POST /cluster/replication)."""
REPL_DELETE_JOB_DESC = """Delete replication job (DELETE /cluster/replication/{jobid})."""

SDN_LIST_ZONES_DESC = """List SDN zones (GET /cluster/sdn/zones)."""
SDN_LIST_VNETS_DESC = """List SDN vnets (GET /cluster/sdn/vnets)."""

CEPH_STATUS_DESC = """Get Ceph status (GET /nodes/{node}/ceph/status)."""
CEPH_DF_DESC = """Get Ceph df (GET /nodes/{node}/ceph/df)."""

DELETE_STORAGE_CONTENT_DESC = """Delete storage content (DELETE /nodes/{node}/storage/{storage}/content/{volume})."""
UPLOAD_STORAGE_CONTENT_DESC = """Upload storage content (POST /nodes/{node}/storage/{storage}/upload).

Parameters:
node* - Node
storage* - Storage ID (e.g., 'local')
content* - Content type (iso|vztmpl|backup)
file_path* - Local file path to upload
filename* - Target file name
"""

VM_VNCPROXY_DESC = """Create VNC proxy for VM (POST /nodes/{node}/qemu/{vmid}/vncproxy)."""
VM_SPICEPROXY_DESC = """Create SPICE proxy for VM (POST /nodes/{node}/qemu/{vmid}/spiceproxy)."""

VM_MOVE_DISK_DESC = """Move VM disk (POST /nodes/{node}/qemu/{vmid}/move_disk)."""
VM_IMPORT_DISK_DESC = """Import raw disk into VM storage (POST /nodes/{node}/qemu/{vmid}/importdisk)."""
VM_ATTACH_DISK_DESC = """Attach disk to VM slot (POST /nodes/{node}/qemu/{vmid}/config)."""
VM_DETACH_DISK_DESC = """Detach disk from VM slot (POST /nodes/{node}/qemu/{vmid}/config with empty value for slot)."""

PROXMOX_REQUEST_DESC = """Generic Proxmox API request proxy.

Parameters:
method* - 'GET' | 'POST' | 'PUT' | 'DELETE'
path* - API path like 'nodes/pve/qemu/100/status/current'
params - Query/body params
data - Extra body params (for writes)
"""
