# Connecting to the Remote Proxmox MCP Server

How any MCP client — this Mac, another device you own, or someone else you grant
access to — connects to the hosted Proxmox MCP server on cluster Guild-A, once
they're on the tailnet.

---

## Architecture

`proxmox_mcp.server` speaks **stdio only** — there is no native network transport
(no SSE/HTTP MCP endpoint) built into the Python process itself
([server.py:842](src/proxmox_mcp/server.py:842), `run_stdio_async`). "Remote" access
works by tunneling that stdio pipe over SSH into the container:

```
MCP client  --stdio-->  ssh  --(Tailscale)-->  guildvm@100.64.198.100
                                                  --> docker exec -i proxmox-mcp-guild-a
                                                        --> python -m proxmox_mcp.server (stdio)
```

The container also exposes port **8811** — that's `mcpo` wrapping the same stdio
process as a plain REST/OpenAPI bridge (what `curl .../pve_call` hits). It answers
anyone who can reach it over Tailscale, **no authentication**. Fine for scripts you
run yourself; do not treat it as access-controlled if you widen who's on the tailnet.
See [HOSTED_MCP_ON_GUILD_A.md](HOSTED_MCP_ON_GUILD_A.md) for where that port lives
and the (not yet applied) `mcpo --api-key` option to lock it down.

### The hosted instance

| | |
| - | - |
| VM | `proxmox-mcp` (VMID 300, nodeD) |
| Tailscale IP | `100.64.198.100` |
| SSH user | `guildvm` |
| Container | `proxmox-mcp-guild-a` (docker) |

**`guildvm` is in the `docker` and `sudo` groups.** Unrestricted SSH access to that
account is full root on the hosted VM, not "just MCP access" — keep that in mind
before handing out a key. See **Granting access to someone else** below for how to
avoid that.

---

## This Mac

Already configured to use the remote instance (switched over, both places):

- **Claude Desktop app** — `~/Library/Application Support/Claude/claude_desktop_config.json`, server `ProxmoxMCP-Plus`
- **This repo** — `.mcp.json`, server `proxmox-guild-a`

Both now run:

```json
{
  "command": "ssh",
  "args": [
    "-i", "~/.ssh/proxmox_guild_a",
    "guildvm@100.64.198.100",
    "docker", "exec", "-i", "proxmox-mcp-guild-a",
    "/bin/bash", "-c", "cd /app && source .venv/bin/activate && python -m proxmox_mcp.server"
  ]
}
```

Restart the Claude Desktop app / Claude Code for the change to take effect.

---

## Another device you own (phone, laptop)

1. Install Tailscale, sign into the same tailnet, confirm you see `nodeA`–`nodeE`
   and `proxmox-mcp-guild-a` in `tailscale status`.
2. Copy `~/.ssh/proxmox_guild_a` (private key) to the new device yourself — USB,
   password manager, `scp` from a machine you trust. Never paste a private key
   into chat. `chmod 600` it there.
3. Add the same MCP server block above to that device's Claude config.

This reuses the one shared infra key ([CLUSTER_SSH.md](CLUSTER_SSH.md) already
documents this pattern for host/guest SSH) — appropriate for devices you control,
since you already hold full access to everything that key can do.

---

## Granting access to someone else

Do **not** hand them a copy of `proxmox_guild_a` — that key also opens root shells
on all five Proxmox nodes and sudo/docker on this VM. Instead, scope a new key down
to *only* running the MCP process, using SSH's forced-command feature.

**They do this:**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/proxmox_mcp_client -C "their-name-or-device"
# send you only the .pub file — never the private half
```

**You do this**, appending their public key to `guildvm`'s `authorized_keys` with a
forced command so that key can never do anything else, regardless of what the
client asks it to run:

```bash
ssh -i ~/.ssh/proxmox_guild_a guildvm@100.64.198.100 bash -c '
cat >> ~/.ssh/authorized_keys <<EOF
command="docker exec -i proxmox-mcp-guild-a /bin/bash -c \"cd /app && source .venv/bin/activate && python -m proxmox_mcp.server\"",no-pty,no-agent-forwarding,no-X11-forwarding,no-port-forwarding <PASTE THEIR PUBLIC KEY LINE>
EOF
'
```

**They configure their client** with their own private key — same shape as above,
just pointing at their key file instead of yours:

```json
{
  "command": "ssh",
  "args": ["-i", "~/.ssh/proxmox_mcp_client", "guildvm@100.64.198.100"]
}
```

Because of the forced command, the trailing `docker exec ...` args they'd normally
need to specify don't matter — the server always runs the one command you fixed in
`authorized_keys`, no matter what the client sends. Give them **full MCP control of
your Proxmox cluster** either way (the token behind it is `root@pam`) — this only
prevents them from getting a shell on the VM itself.

**To revoke:** delete their line from `authorized_keys` on the VM. Nothing else to
clean up.

**Current state:** only one key is installed today — the shared, unrestricted
`proxmox_guild_a` (comment `proxmox-cluster-guild-a`). No one outside you has been
granted access yet.

---

## Verifying a connection works

Test the stdio handshake directly, without a full MCP client:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}' \
  | ssh -i ~/.ssh/proxmox_guild_a guildvm@100.64.198.100 \
      'docker exec -i proxmox-mcp-guild-a /bin/bash -c "cd /app && source .venv/bin/activate && python -m proxmox_mcp.server"'
```

A healthy reply looks like:

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05", ..., "serverInfo":{"name":"ProxmoxMCP","version":"1.14.1"}}}
```
