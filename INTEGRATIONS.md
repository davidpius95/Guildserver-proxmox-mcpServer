## Integrations: Claude Desktop, Cursor, and OpenAPI

This guide shows how to connect ProxmoxMCP-Plus to common AI tools with the correct configuration.

### Prerequisites

- A working virtualenv for this repo and `proxmox-config/config.json` filled in
- Recommended environment flags for stable stdio operation:
  - PROXMOX_MCP_SKIP_CONNECT_TEST=1
  - PROXMOX_MCP_DISABLE_FILE_LOG=1
  - PROXMOX_VERIFY_SSL=false (if using self-signed certs)

### Claude Desktop (direct MCP over stdio)

1) Open Claude Desktop settings and edit your MCP servers configuration JSON.

2) Add both the Proxmox MCP server and a separate filesystem server (optional but useful):

```json
{
  "mcpServers": {
    "ProxmoxMCP-Plus": {
      "command": "/Users/user/Desktop/ProxmoxMCP-Plus/.venv/bin/python",
      "args": ["-m", "proxmox_mcp.server"],
      "cwd": "/Users/user/Desktop/ProxmoxMCP-Plus",
      "transport": "stdio",
      "env": {
        "PYTHONPATH": "/Users/user/Desktop/ProxmoxMCP-Plus/src",
        "PROXMOX_MCP_CONFIG": "/Users/user/Desktop/ProxmoxMCP-Plus/proxmox-config/config.json",
        "PROXMOX_VERIFY_SSL": "false",
        "PROXMOX_MCP_SKIP_CONNECT_TEST": "1",
        "PROXMOX_MCP_DISABLE_FILE_LOG": "1"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/user/Desktop", "/Users/user/Downloads"],
      "cwd": "/Users/user/Desktop/ProxmoxMCP-Plus",
      "transport": "stdio",
      "env": {}
    }
  }
}
```

#### Field-by-field explanation (Claude Desktop)

- **mcpServers**: Map of server name → config. Use a friendly name like `"ProxmoxMCP-Plus"`.
- **command**: Absolute path to your venv’s Python. Ensures correct dependencies.
  - Example: `/Users/user/Desktop/ProxmoxMCP-Plus/.venv/bin/python`
- **args**: Program arguments. `-m proxmox_mcp.server` runs the MCP server module.
  - Example: `["-m", "proxmox_mcp.server"]`
- **cwd**: Working directory for the server process. Relative paths resolve from here.
  - Example: `/Users/user/Desktop/ProxmoxMCP-Plus`
- **transport**: Must be `"stdio"` so Claude can speak MCP over stdin/stdout.
- **env**: Environment variables passed to the server:
  - **PYTHONPATH**: Include `src` so `proxmox_mcp` is importable.
    - Example: `/Users/user/Desktop/ProxmoxMCP-Plus/src`
  - **PROXMOX_MCP_CONFIG**: Absolute path to your JSON config.
    - Example: `/Users/user/Desktop/ProxmoxMCP-Plus/proxmox-config/config.json`
  - **PROXMOX_VERIFY_SSL**: `false` to allow self-signed certs; `true` for strict.
  - **PROXMOX_MCP_SKIP_CONNECT_TEST**: `1` to skip initial API probe; prevents early disconnects if PVE is momentarily unreachable.
  - **PROXMOX_MCP_DISABLE_FILE_LOG**: `1` to avoid file writes in sandboxed/read-only environments; logs still go to stderr.
  - Optional:
    - **PROXMOX_MCP_LOG_FILE**: Set a writable log file to enable file logging instead of disabling it.
    - You can alternatively provide `PROXMOX_HOST`, `PROXMOX_USER`, `PROXMOX_TOKEN_NAME`, `PROXMOX_TOKEN_VALUE`, `PROXMOX_PORT`, `PROXMOX_SERVICE` to run without a config file.

#### Minimal alternative (env-only, no config.json)

```json
{
  "mcpServers": {
    "ProxmoxMCP-Plus": {
      "command": "/Users/user/Desktop/ProxmoxMCP-Plus/.venv/bin/python",
      "args": ["-m", "proxmox_mcp.server"],
      "cwd": "/Users/user/Desktop/ProxmoxMCP-Plus",
      "transport": "stdio",
      "env": {
        "PYTHONPATH": "/Users/user/Desktop/ProxmoxMCP-Plus/src",
        "PROXMOX_HOST": "192.168.8.228",
        "PROXMOX_USER": "root@pam",
        "PROXMOX_TOKEN_NAME": "terraform",
        "PROXMOX_TOKEN_VALUE": "<secret-token>",
        "PROXMOX_PORT": "8006",
        "PROXMOX_SERVICE": "PVE",
        "PROXMOX_VERIFY_SSL": "false",
        "PROXMOX_MCP_SKIP_CONNECT_TEST": "1",
        "PROXMOX_MCP_DISABLE_FILE_LOG": "1"
      }
    }
  }
}
```

### Cursor (via OpenAPI proxy)

Cursor connects best through an OpenAPI server. Use the included `mcpo` proxy to expose all MCP tools as REST endpoints.

1) Start the OpenAPI service:

```bash
cd /Users/user/Desktop/ProxmoxMCP-Plus
source .venv/bin/activate
export PYTHONPATH=/Users/user/Desktop/ProxmoxMCP-Plus/src
export PROXMOX_MCP_CONFIG=/Users/user/Desktop/ProxmoxMCP-Plus/proxmox-config/config.json
export PROXMOX_VERIFY_SSL=false
export PROXMOX_MCP_SKIP_CONNECT_TEST=1
export PROXMOX_MCP_DISABLE_FILE_LOG=1
./start_openapi.sh
```

#### Field-by-field explanation (OpenAPI env)

- **PYTHONPATH**: Ensures the proxy can import `proxmox_mcp.server`.
- **PROXMOX_MCP_CONFIG**: Path to your Proxmox + auth JSON config.
- **PROXMOX_VERIFY_SSL**: `false` for self-signed certs in dev.
- **PROXMOX_MCP_SKIP_CONNECT_TEST**: Skip the initial API check to keep stdio stable.
- **PROXMOX_MCP_DISABLE_FILE_LOG**: Avoid file writes in read-only environments.

The OpenAPI proxy exposes:
- Base URL: `http://localhost:8811`
- Docs: `http://localhost:8811/docs`
- Spec: `http://localhost:8811/openapi.json`

2) In Cursor, add an OpenAPI connection:
- Base URL: `http://localhost:8811`
- Or import spec: `http://localhost:8811/openapi.json`

3) Test quickly with curl:

```bash
curl -X POST http://localhost:8811/get_nodes -H 'Content-Type: application/json' -d '{}'
```

### Open WebUI (already supported)

Use the same OpenAPI service as above and configure Open WebUI:

```json
{
  "name": "Proxmox MCP API Plus",
  "base_url": "http://localhost:8811",
  "api_key": "",
  "description": "Enhanced Proxmox Virtualization Management API"
}
```

#### Field-by-field explanation (Open WebUI)

- **name**: Display label in the UI.
- **base_url**: Your OpenAPI proxy address.
- **api_key**: Optional; only if you add auth to the proxy.
- **description**: Optional notes for the integration.

### Troubleshooting

- Server disconnected immediately in Claude:
  - Ensure `PROXMOX_MCP_SKIP_CONNECT_TEST=1` and `PROXMOX_MCP_DISABLE_FILE_LOG=1` are set
  - Verify no prints go to stdout (this repo prints to stderr)

- Read-only filesystem error like `/proxmox_mcp.log`:
  - Set `PROXMOX_MCP_DISABLE_FILE_LOG=1`, or set `PROXMOX_MCP_LOG_FILE` to a writable path

- SSL errors:
  - Set `PROXMOX_VERIFY_SSL=false` for self-signed certs

- Auth 401 or token format issues:
  - Ensure `auth.token_name` is the token ID only (without `user@realm!` prefix)

### Environment variable reference

- **PROXMOX_MCP_CONFIG**: Absolute path to JSON config with `proxmox` and `auth` sections.
- **PROXMOX_HOST / PROXMOX_PORT / PROXMOX_SERVICE**: Proxmox API host, port (default 8006), service (usually `PVE`).
- **PROXMOX_USER / PROXMOX_TOKEN_NAME / PROXMOX_TOKEN_VALUE**: Token auth. Token name should be the token ID only (e.g., `terraform`).
- **PROXMOX_VERIFY_SSL**: `true` or `false`. Set `false` for self-signed dev clusters.
- **PROXMOX_MCP_SKIP_CONNECT_TEST**: `1` skips initial API call to avoid early disconnects.
- **PROXMOX_MCP_DISABLE_FILE_LOG**: `1` disables file logging; stderr logging remains enabled.
- **PROXMOX_MCP_LOG_FILE**: Optional explicit log file path if you want file logs.

---

## Remote access (public exposure)

Make the OpenAPI service reachable from other machines or the internet. Proceed carefully and secure the endpoint.

### Start OpenAPI bound to all interfaces

```bash
cd /Users/user/Desktop/ProxmoxMCP-Plus
source .venv/bin/activate
export PYTHONPATH=/Users/user/Desktop/ProxmoxMCP-Plus/src
export PROXMOX_MCP_CONFIG=/Users/user/Desktop/ProxmoxMCP-Plus/proxmox-config/config.json
export PROXMOX_VERIFY_SSL=false
export PROXMOX_MCP_SKIP_CONNECT_TEST=1
export PROXMOX_MCP_DISABLE_FILE_LOG=1
export OPENAPI_PORT=8811
./start_openapi.sh
# Binds to 0.0.0.0:8811 (all interfaces)
```

### Network access checklist

- Router/NAT: Port forward TCP 8811 → your machine’s LAN IP (e.g., 192.168.x.x)
- Host firewall: Allow inbound TCP 8811
- Test externally: `http://YOUR_PUBLIC_IP:8811/docs`

### Secure it (recommended options)

1) Reverse proxy with TLS (Nginx)

```nginx
server {
  listen 80;
  server_name mcp.yourdomain.com;

  location / {
    proxy_pass http://127.0.0.1:8811;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

Issue certificates (Let’s Encrypt):

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d mcp.yourdomain.com
```

Optional Basic Auth:

```nginx
auth_basic "Restricted";
auth_basic_user_file /etc/nginx/.htpasswd;  # create with: htpasswd -c /etc/nginx/.htpasswd youruser
```

2) Cloudflare Tunnel (no port-forwarding)

```bash
brew install cloudflared   # or apt install cloudflared
cloudflared tunnel login
cloudflared tunnel create proxmox-mcp
cloudflared tunnel route dns proxmox-mcp mcp.yourdomain.com
cloudflared tunnel run proxmox-mcp --url http://localhost:8811
```

3) SSH reverse tunnel (quick, temporary)

```bash
# On the MCP host:
ssh -N -R 8811:localhost:8811 user@your_vps
# Then access: http://your_vps:8811/docs
```

### Docker option

Use the included compose file which publishes port 8811:

```bash
docker compose up -d   # publishes 8811:8811
# Ensure router/firewall allows TCP 8811
```

### Safety notes

- This API can perform powerful Proxmox actions (create/delete VMs, etc.).
- Prefer TLS + auth (Nginx), or keep behind VPN, Cloudflare Tunnel, or SSH.
- Limit exposure to trusted IPs where possible.


