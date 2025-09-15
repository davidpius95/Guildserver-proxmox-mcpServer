## IaC Quickstart

Plan infrastructure changes against your Proxmox cluster using a simple YAML spec.

### 1) Environment file

Edit `iac/dev.yaml` to match your nodes and VMIDs.

```yaml
name: dev
vms:
  - name: dev-web
    node: guildserver
    vmid: 900
    cpus: 2
    memory: 2048
    disk_size: 20
    storage: local-lvm
    ostype: l26
```

### 2) Environment variables

```bash
export PYTHONPATH=$(pwd)/src
export PROXMOX_MCP_CONFIG=$(pwd)/proxmox-config/config.json
export PROXMOX_VERIFY_SSL=false
export PROXMOX_MCP_SKIP_CONNECT_TEST=1
export PROXMOX_MCP_DISABLE_FILE_LOG=1
```

### 3) Run the planner

```bash
proxmox-mcp-plan iac/dev.yaml

# JSON output
proxmox-mcp-plan iac/dev.yaml --json
```

Sample output:

```
Environment: dev
Create: 2, Change: 0, Delete: 0
  + create vm 900 'dev-web' on guildserver (2 CPU, 2048 MB, 20 GB)
  + create vm 901 'dev-db' on guildserver (2 CPU, 4096 MB, 40 GB)
```

### Next steps

- Add an apply step to call `create_vm` for planned creates
- Extend planner to detect diffs and propose updates
- Add snapshot-based rollback before apply


