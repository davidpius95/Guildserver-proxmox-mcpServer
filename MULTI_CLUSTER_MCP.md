# Multi-Cluster MCP

This repo runs one MCP server that can route requests to multiple Proxmox
clusters. `proxmox-config/nodes.json` stores non-secret cluster metadata and
`.env` stores API token secrets.

## Proxmox API Coverage

The MCP exposes the Proxmox API in two layers:

- `pve_call` is the generic API gateway. It can call every request/response
  endpoint in the bundled Proxmox schema.
- `pve_find_endpoint` and `pve_describe_endpoint` search and describe the
  bundled schema before calling an endpoint.
- `pve_list_clusters` lists the configured cluster names available to
  `pve_call`.
- Hand-written tools such as `get_nodes`, `start_vm`, and `ceph_status` are
  convenience wrappers for common operations and use the default cluster.

The bundled schema is from `pve.proxmox.com/pve-docs/api-viewer/apidoc.js` for
PVE `9.2.2` and contains `675` method endpoints across `444` unique paths:

- `GET`: `340`
- `POST`: `173`
- `PUT`: `83`
- `DELETE`: `79`

Use `pve_call` for full coverage instead of expecting one named MCP tool per
Proxmox endpoint.

## Source Of Truth

Edit `proxmox-config/nodes.json`. Despite the filename, each item in `nodes`
is one Proxmox cluster API endpoint.

Minimal non-secret entry:

```json
{
  "name": "guild-b",
  "host": "192.168.9.125",
  "token_name": "guildb",
  "token_env": "PROXMOX_MCP_TOKEN_GUILD_B",
  "http_port": 8812
}
```

Store the token secret in `.env`:

```bash
PROXMOX_MCP_TOKEN_GUILD_B=GENERATED_TOKEN_SECRET
```

Then regenerate and restart:

```bash
./scripts/nodes.py sync
docker compose up -d --build --remove-orphans
```

The generated config writes token values as `${ENV_VAR}` references. The MCP
config loader resolves those references from the container environment.

## CLI Add

You can also add a cluster with:

```bash
./scripts/nodes.py add \
  --name guild-b \
  --host 192.168.9.125 \
  --token-name guildb \
  --token-value GENERATED_TOKEN_SECRET \
  --http-port 8812
```

`add` writes the secret to `.env` and stores only `token_env` in
`proxmox-config/nodes.json`.

## Guild-B Details Needed

To add Guild-B cleanly, provide:

- Cluster name, for example `guild-b`
- Reachable Proxmox API host/IP for one node in that cluster
- API port, usually `8006`
- API user, usually `root@pam`
- API token name, for example `guildb`
- API token secret/value shown once by Proxmox
- SSL mode, usually `verify_ssl: false` for self-signed LAN certs

## Using The MCP

List configured clusters:

```json
{
  "tool": "pve_list_clusters"
}
```

Call the default cluster:

```json
{
  "tool": "pve_call",
  "method": "GET",
  "path": "cluster/status"
}
```

Call a specific cluster:

```json
{
  "tool": "pve_call",
  "cluster": "guild-b",
  "method": "GET",
  "path": "cluster/status"
}
```

## Important Behavior

The hand-written tools use the default cluster. Use `pve_call` with the
`cluster` argument for non-default clusters.

`pve_find_endpoint` and `pve_describe_endpoint` are schema tools; they do not
need a cluster because they describe the Proxmox API itself.

## Creating Tokens

Proxmox generates API token secrets. It does not accept a caller-provided token
secret. On the target cluster, create a token like this:

```bash
pveum user token add root@pam guildb --privsep 0 --expire 0 \
  --comment "Cluster-wide MCP token guildb" --output-format json
```

Store the returned `value` in `.env`. It is shown only once.
