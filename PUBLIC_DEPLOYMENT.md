## Public Deployment & Integration Guide

This guide shows how to set up ProxmoxMCP-Plus, expose it securely for remote access, and connect from Claude Desktop and Cursor.

### 1) Install and configure

```bash
# Clone and enter the repo
git clone https://github.com/RekklesNA/ProxmoxMCP-Plus.git
cd ProxmoxMCP-Plus

# Create & activate virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -U pip setuptools wheel
pip install -e ".[dev]"

# Create config directory and copy template
mkdir -p proxmox-config
cp proxmox-config/config.example.json proxmox-config/config.json

# Edit proxmox-config/config.json with your host and token
$EDITOR proxmox-config/config.json
```

Minimal `proxmox-config/config.json` example:

```json
{
  "proxmox": {
    "host": "192.168.8.228",
    "port": 8006,
    "verify_ssl": false,
    "service": "PVE"
  },
  "auth": {
    "user": "root@pam",
    "token_name": "terraform",
    "token_value": "<secret-token>"
  },
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "proxmox_mcp.log"
  }
}
```

Environment flags recommended for stability:

```bash
export PYTHONPATH=$(pwd)/src
export PROXMOX_MCP_CONFIG=$(pwd)/proxmox-config/config.json
export PROXMOX_VERIFY_SSL=false                   # if self-signed certs
export PROXMOX_MCP_SKIP_CONNECT_TEST=1            # avoid early disconnects in MCP stdio
export PROXMOX_MCP_DISABLE_FILE_LOG=1             # avoid read-only FS issues
```

Quick local test (optional):

```bash
python -m proxmox_mcp.server
# Ctrl+C to stop
```

### 2) Expose an OpenAPI server for remote access

Run the included MCP→OpenAPI proxy (`mcpo`) and bind to all interfaces.

```bash
source .venv/bin/activate
export PYTHONPATH=$(pwd)/src
export PROXMOX_MCP_CONFIG=$(pwd)/proxmox-config/config.json
export PROXMOX_VERIFY_SSL=false
export PROXMOX_MCP_SKIP_CONNECT_TEST=1
export PROXMOX_MCP_DISABLE_FILE_LOG=1
export OPENAPI_PORT=8811
./start_openapi.sh
# Serves on 0.0.0.0:8811 → http://<server-ip>:8811/docs
```

Network steps:
- Router/NAT: forward TCP 8811 → this server’s LAN IP
- Host firewall: allow inbound TCP 8811
- Test externally: `http://YOUR_PUBLIC_IP:8811/docs`

### 3) Secure the public endpoint (choose one)

Option A) Nginx reverse proxy with TLS (Let’s Encrypt)

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

Issue certs:

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d mcp.yourdomain.com
```

Optional basic auth:

```nginx
auth_basic "Restricted";
auth_basic_user_file /etc/nginx/.htpasswd;  # create with: htpasswd -c /etc/nginx/.htpasswd youruser
```

Option B) Cloudflare Tunnel (no port-forwarding)

```bash
cloudflared tunnel login
cloudflared tunnel create proxmox-mcp
cloudflared tunnel route dns proxmox-mcp mcp.yourdomain.com
cloudflared tunnel run proxmox-mcp --url http://localhost:8811
```

Option C) SSH reverse tunnel (quick, temporary)

```bash
# On the MCP host (this server)
ssh -N -R 8811:localhost:8811 user@your_vps
# Then access http://your_vps:8811/docs
```

Option D) Docker Compose

```bash
docker compose up -d     # publishes 8811:8811 as defined in docker-compose.yml
```

### 4) Connect clients

Cursor (OpenAPI):
- Base URL: `http://mcp.yourdomain.com` (or your public IP)
- Or import spec: `http://mcp.yourdomain.com/openapi.json`

Open WebUI (OpenAPI):

```json
{
  "name": "Proxmox MCP API Plus",
  "base_url": "http://mcp.yourdomain.com",
  "api_key": "",
  "description": "Enhanced Proxmox Virtualization Management API"
}
```

Claude Desktop (local process on same machine):

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
    }
  }
}
```

Claude Desktop (connect to a remote host via SSH):

```json
{
  "mcpServers": {
    "ProxmoxMCP-Remote": {
      "command": "/usr/bin/ssh",
      "args": [
        "-T", "user@remote-host",
        "bash", "-lc",
        "source /srv/ProxmoxMCP-Plus/.venv/bin/activate && PYTHONPATH=/srv/ProxmoxMCP-Plus/src PROXMOX_MCP_CONFIG=/srv/ProxmoxMCP-Plus/proxmox-config/config.json PROXMOX_VERIFY_SSL=false PROXMOX_MCP_SKIP_CONNECT_TEST=1 PROXMOX_MCP_DISABLE_FILE_LOG=1 python -m proxmox_mcp.server"
      ],
      "cwd": "/",
      "transport": "stdio",
      "env": {}
    }
  }
}
```

Notes:
- This SSH approach runs the MCP server on the remote machine and streams MCP over the SSH stdio channel.
- Ensure the remote host has Python env and this repo installed at the specified paths.

### 5) Test

OpenAPI quick test:

```bash
curl -X POST http://mcp.yourdomain.com/get_nodes -H 'Content-Type: application/json' -d '{}'
```

### 6) Hardening tips

- Restrict Nginx access by IP where possible.
- Keep TLS current; rotate SSH keys and API tokens periodically.
- Limit the Proxmox token’s privileges to only what you need.


