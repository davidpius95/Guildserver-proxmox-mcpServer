# guildserver.io ingress

Give **any service you deploy on the cluster its own subdomain** under
`*.guildserver.io`, reachable from the internet through the existing **Cloudflare
Tunnel** — no port-forwarding, no exposed home IP, TLS terminated at Cloudflare's
edge.

```
                Internet
                   │  TLS (Cloudflare edge cert: *.guildserver.io)
          ┌────────▼─────────┐
          │  Cloudflare edge │   DNS: *.guildserver.io  CNAME → <uuid>.cfargotunnel.com  (proxied)
          └────────┬─────────┘
                   │  Cloudflare Tunnel (outbound-only)
        ┌──────────▼────────────┐
        │  PDM VM 200            │   cloudflared (token-managed connector)
        │  192.168.50.197        │   public hostname: *.guildserver.io → http://192.168.8.10:80
        └──────────┬────────────┘
                   │
        ┌──────────▼────────────┐
        │  ingress LXC 910       │   Caddy — routes by Host header
        │  192.168.8.10          │
        └──────────┬────────────┘
   ┌───────────────┼─────────────────┐
   ▼               ▼                 ▼
jellyfin.guildserver  app2.guildserver  db.guildserver
 → 192.168.8.244:8096  → .51:3000        → .52:5432
```

**The key idea:** the tunnel wildcards `*.guildserver.io` onto Caddy **once**.
After that, a new subdomain is just one Caddy route — **no dashboard visit, ever
again**. Adding a service is one command, and `scripts/cf-sync.sh` drives the
Cloudflare side over the API so even the one-time wildcard setup is scripted.

## Day-to-day

From your Mac, in the repo root:

```bash
./ingress/route add jellyfin 192.168.8.244:8096   # jellyfin.guildserver.io
./ingress/route add grafana  192.168.8.60:3000    # grafana.guildserver.io
./ingress/route ls
./ingress/route rm grafana
```

That's the whole workflow. The wrapper finds whichever node currently hosts CT
910 (its rootfs is on shared Ceph, so it can migrate) and runs the route scripts
inside it. Caddy's admin API stays bound to `127.0.0.1` in the container and is
never exposed.

---

## Files

| Path | What it is |
|------|------------|
| `route` | **Mac-side wrapper — the thing you actually run.** `add` / `rm` / `ls`. |
| `caddy/caddy-ingress.service` | systemd unit running Caddy from `/etc/caddy/caddy.json`. |
| `scripts/provision-lxc.sh` | Creates the ingress LXC (run on a Proxmox node). |
| `scripts/install-ingress.sh` | Installs Caddy inside the LXC and the route scripts. |
| `scripts/apply-routes.sh` | Regenerates `/etc/caddy/caddy.json` from route files + hot-loads it. |
| `scripts/add-route.sh` | Add/update a subdomain → backend route. |
| `scripts/remove-route.sh` | Remove a subdomain route. |
| `scripts/list-routes.sh` | List configured routes. |
| `scripts/cf-sync.sh` | Cloudflare API: wildcard bootstrap, per-subdomain DNS, ingress rules. |

There is no `caddy/caddy.json` in the repo: it is **generated** on the box by
`apply-routes` and would only go stale here.

---

## How persistence works

`/etc/caddy/routes/<sub>.json` is the source of truth — one Caddy route object
per subdomain. Every `add`/`rm` rewrites the **complete** `/etc/caddy/caddy.json`
from that directory and hot-loads it through the admin API.

Because the on-disk config is always the full live route set, and the systemd
unit starts Caddy with `--config /etc/caddy/caddy.json`, **routes survive reboots
for free** — no `--resume`, no replay service, no external state.

(The earlier design POSTed individual route deltas to the admin API, which meant
routes vanished on restart. That's fixed.)

---

## Cloudflare side — automated (`scripts/cf-sync.sh`)

No dashboard visits. One-time, create a Cloudflare **API token** (this is *not*
the tunnel connector token) at dash.cloudflare.com → My Profile → API Tokens,
with exactly:

- **Account** → Cloudflare Tunnel → **Edit**
- **Zone** → DNS → **Edit** (zone `guildserver.io`)

```bash
mkdir -p ~/.config/guildserver
printf '%s' '<paste-token>' > ~/.config/guildserver/cf-api-token
chmod 600 ~/.config/guildserver/cf-api-token
```

Then bootstrap the wildcard once:

```bash
./ingress/scripts/cf-sync.sh bootstrap --dry-run   # preview
./ingress/scripts/cf-sync.sh bootstrap             # apply
```

`bootstrap` sets `*.guildserver.io` DNS → the tunnel (proxied) **and** the tunnel
ingress rule `*.guildserver.io → http://192.168.8.10:80`. After that,
`./ingress/route add` also creates the per-subdomain CNAME automatically, so a
new service needs nothing in the dashboard.

Other commands:

```bash
./ingress/scripts/cf-sync.sh show     # current ingress rules + tunnel CNAMEs
./ingress/scripts/cf-sync.sh add <sub>
./ingress/scripts/cf-sync.sh rm  <sub>
```

Notes that matter:

- The service **must** be `http://` — Caddy is plaintext on `:80`. An `https://`
  origin gives a 502. `bootstrap` refuses a non-`http://` `CADDY_ORIGIN`.
- Rule order is enforced: **specific hostnames → wildcards → catch-all**, so
  `datacenter.guildserver.io` (PDM, its own HTTPS origin) keeps winning over the
  wildcard.
- Tunnel autodiscovery picks the tunnel that already serves a hostname in this
  zone — i.e. the one with a live connector. Guessing wrong is exactly how
  traffic ends up at a stale tunnel. Override with `CF_TUNNEL_ID` if needed.
- The token is read from the file at runtime; it is never placed in a URL.
- The **connector** token in `/etc/cloudflared/token` on the PDM VM is the
  owner's and is never read or written by this tooling.

### SSL/TLS settings — dashboard, once
- **SSL/TLS → Overview → Full.**
- **Edge Certificates → Always Use HTTPS: On.**
- Universal SSL covers `guildserver.io` and one wildcard level
  `*.guildserver.io`, so every `<app>.guildserver.io` gets a valid cert
  automatically. Deeper names (`a.b.guildserver.io`) would need an Advanced
  Certificate.

### Rebuild the ingress box from scratch
```bash
scp -r ingress nodeA:/root/
ssh nodeA 'bash /root/ingress/scripts/provision-lxc.sh'
ssh nodeA 'tar -C /root -cf - ingress | pct exec 910 -- tar -C /root -xf -'
ssh nodeA 'pct exec 910 -- bash /root/ingress/scripts/install-ingress.sh'
```
Note `pct push` has no `-r`; pipe a tar instead (as above). The container needs a
nameserver — `provision-lxc.sh` does not set one, so if apt can't resolve, run
`pct set 910 --nameserver 1.1.1.1` and reboot it.

---

## Security note

Anything you route this way is on the public internet, protected only by that
app's own login. For admin panels and anything with weak or no auth, put
**Cloudflare Access** in front of the hostname (Zero Trust → Access →
Applications) so Cloudflare authenticates before traffic ever reaches the tunnel.

---

## Next: paas-backend integration

To make subdomains automatic on deploy, add to `paas-backend`:

- An `ingress` module that shells out to `route add` / `route rm` (or calls the
  Caddy admin API over SSH into CT 910).
- A hook in the VM/LXC create + destroy flow: after a service gets an IP, call
  `addRoute(subdomain, ip:port)`; on teardown call `removeRoute(subdomain)`.

No Cloudflare credentials need to live in paas-backend — the tunnel is a fixed
wildcard, so this integration is Caddy-only.
