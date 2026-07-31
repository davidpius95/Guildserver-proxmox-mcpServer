# Hosted Proxmox MCP On Guild-A

## Goal

Run ProxmoxMCP-Plus inside Guild-A instead of Docker Desktop, while keeping it
usable from the user's PC on any network.

## Recommended Architecture

```text
User PC
  -> Cloudflare Access or WARP
  -> Cloudflare Tunnel
  -> CT 910 Caddy ingress
  -> dedicated MCP VM/LXC on Guild-A
  -> Proxmox API for Guild-A and Guild-B
```

Do not expose the MCP HTTP bridge directly to the public internet. It can
control the Proxmox cluster and must be protected by identity-aware access.

## Proposed Workload

- Name: `proxmox-mcp`
- VMID: `300`
- Proxmox node: `nodeD`
- Type: dedicated Ubuntu VM or LXC
- CPU: `2`
- RAM: `4 GiB`
- Disk: `20 GiB`
- LAN IP: `192.168.8.230`
- Tailscale IP: `100.64.198.100`
- Runtime: Docker Compose
- Service port: `8811`
- Tailscale hostname: `proxmox-mcp-guild-a`

## Secrets

Keep secrets on the hosted VM/LXC in `.env` with `0600` permissions:

```bash
PROXMOX_MCP_TOKEN_GUILD_A=...
PROXMOX_MCP_TOKEN_GUILD_B=...
```

`proxmox-config/config.guild-a.json` should reference those values as
`${PROXMOX_MCP_TOKEN_GUILD_A}` and `${PROXMOX_MCP_TOKEN_GUILD_B}`.

## Deployment Steps

1. Create or select the dedicated Ubuntu VM/LXC.
2. Install Docker and Docker Compose plugin.
3. Copy or clone this repository onto the VM/LXC.
4. Create `.env` from the local secrets.
5. Run `./scripts/nodes.py sync`.
6. Run `docker compose up -d --build --remove-orphans`.
7. Verify `curl http://127.0.0.1:8811/openapi.json`.
8. Bind the Docker published port to the VM's Tailscale IP only.
9. Verify from a Tailscale-connected client.

## Current Deployment

The MCP server is deployed on VM `300` and listens only on Tailscale:

```text
http://100.64.198.100:8811
```

Local LAN access to `192.168.8.230:8811` is intentionally closed by binding the
published Docker port to `100.64.198.100`.

To use it as an MCP server from this Mac, use:

```json
{
  "mcpServers": {
    "proxmox-hosted-tailscale": {
      "command": "ssh",
      "args": [
        "-i",
        "~/.ssh/proxmox_guild_a",
        "guildvm@100.64.198.100",
        "docker",
        "exec",
        "-i",
        "proxmox-mcp-guild-a",
        "/bin/bash",
        "-c",
        "cd /app && source .venv/bin/activate && python -m proxmox_mcp.server"
      ]
    }
  }
}
```

This config is saved as `.mcp.hosted-tailscale.json`.

## Current Candidate Hosts

Current live read-only survey showed:

- Existing VM `210` / `coolify` on nodeA has IP `192.168.50.20`.
- Template `9000` / `ubuntu-2604-guildvm-template` exists on nodeD.
- Existing test VMs `103`, `108`, and `200` did not report usable guest-agent
  LAN IPs during survey.

The deployed path is a dedicated VM cloned from template `9000`; Coolify and
PDM were not reused.
