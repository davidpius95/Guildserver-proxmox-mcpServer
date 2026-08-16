# Monitoring — Uptime Kuma, Prometheus/Grafana, Home Assistant

What watches what, and the failure modes already paid for.

> Cluster source of truth: **[CLUSTER.md](CLUSTER.md)** · Backups: **[BACKUPS.md](BACKUPS.md)**
> · Remote access: **[TAILSCALE.md](TAILSCALE.md)**

**Last verified 2026-08-16.**

---

## Two independent stacks

| Stack | Where | Watches |
| --- | --- | --- |
| **Uptime Kuma** | CT 101 on podC | Host/service reachability across both clusters — 35 monitors |
| **kube-prometheus-stack** | k8s `monitoring` ns | Cluster metrics, node exporters, Proxmox exporters, Home Assistant |
| **Grafana** | k8s, LoadBalancer IP **port 80** (not 3000) | Dashboards over Prometheus + Loki |

Home Assistant feeds Prometheus via `/api/prometheus` (job `home-assistant-external`).

---

## Uptime Kuma

Kuma is deliberately blocked from the Proxmox API on Guild-B by the **G-19** firewall rule
(ipset `guildb-workloads` DROPs 8006/22). So **PVE web-UI monitors pointed at Guild-B pods
can never pass** — don't recreate them. Host ping monitors cover pod liveness instead.

### Trap — monitors that alert on the wrong thing

Eight monitors still pointed at the **old domain** after the migration to
`guild-technologies.com`. All eight flipped **DOWN → UP** the moment the URLs were
corrected — they were false alarms, not outages, and had been training everyone to ignore
the dashboard.

When renaming a domain, grep the monitor list for the old one. Kuma stores monitors in
SQLite at `/opt/uptime-kuma/data/kuma.db`; stop the service before editing, and back the
file up first:

```bash
systemctl stop uptime-kuma
sqlite3 /opt/uptime-kuma/data/kuma.db "select id,name,url from monitor;"
systemctl start uptime-kuma
```

Also removed: monitors for a VM that no longer existed, and for a stopped service. A monitor
that can never go green is worse than no monitor.

---

## Prometheus

### Trap — a pod stuck `Terminating` takes every dashboard down silently

**This blanked all dashboards for 4.5 days.**

```
prometheus-…-prometheus-0
  deletionTimestamp = 2026-08-12T01:04:18Z
  finalizers        = (none)
```

The pod was stuck Terminating, so the StatefulSet could not recreate it. There is no alert
for "my monitoring is gone" — the thing that would have told you was the thing that was down.

A normal `kubectl delete pod` does nothing; it is already deleting. It needs:

```bash
kubectl -n monitoring delete pod <pod> --force --grace-period=0
```

Check first with `-o jsonpath="{.metadata.deletionTimestamp}{.metadata.finalizers}"`. If a
finalizer is present, remove that instead — force-deleting a pod holding an RWO volume can
leave the volume attached to the old node.

### Gotchas when querying Prometheus

- **The Prometheus image is distroless.** `kubectl exec … -- wget` returns *nothing* —
  no shell, no wget — which reads identically to "no data". Curl the **ClusterIP from a
  node** instead, or `kubectl run` a curl pod.
- **`kube-etcd` shows down** (`:2381` connection refused). Separate cosmetic scrape-config
  issue, unrelated to dashboards.
- **All Longhorn volumes are `attached` but `degraded`** — replicas were lost with the
  deleted worker node. The cluster runs 2 nodes against a 3-replica default. Degraded still
  serves I/O, so it is not the cause when something breaks; don't chase it first.

---

## Grafana

Dashboards loaded by the sidecar from ConfigMaps labelled `grafana_dashboard: 1` are
**read-only in the UI** — the API returns `Cannot save provisioned dashboard`.

Edit the ConfigMap instead, then the sidecar reloads within ~1 minute. **Check ownership
first:**

```bash
kubectl -n monitoring get cm <name> -o json | python3 -c "import sys,json; m=json.load(sys.stdin)['metadata']; print(m.get('labels'), m.get('ownerReferences'))"
```

If it carries an ArgoCD instance label or ownerReferences, edit the **source repo** — a
direct edit will be reverted on next sync. If it has neither (hand-applied via `kubectl`),
editing the ConfigMap persists.

> ⚠ The Home Assistant dashboard is currently hand-applied and **not in the GitOps repo**,
> so it is not version-controlled and a cluster rebuild loses it. It belongs in
> `guildserver-k8s` alongside the other manifests.

### Trap — metric names that look right but aren't

Two panels queried `homeassistant_sensor_unit_percent`; Home Assistant publishes those
particular entities as `homeassistant_sensor_battery_percent`. The panels were blank even
when everything upstream was healthy.

Before assuming a data problem, confirm the series actually exists:

```
{__name__=~"homeassistant_sensor_.*", entity=~".*<device>.*"}
```

Note the metric prefix here is **`homeassistant_*`**, not the `hass_*` that many community
dashboards assume.

---

## Home Assistant — Growatt solar

The `growatt_server` integration is **cloud-based** and re-authenticates on *every* poll:

```
coordinator.py  self.api.login(user, pass)  →  POST newTwoLoginAPI.do
                →  ConnectionResetError(104, 'Connection reset by peer')
```

That is Growatt rate-limiting. `SCAN_INTERVAL` (5 min) and `DEVICE_SCAN_INTERVAL` (1 h) are
**hardcoded** and the integration has **no options flow**, so the poll rate cannot be tuned
— roughly 288 logins/day. **Expect recurrence.**

The real damage is not the hiccup but that the device coordinator can die and **never
self-recover** — it stayed dead 11 days. Unavailable entities are dropped from
`/api/prometheus` entirely, so panels go blank rather than flat-lining.

**A Home Assistant Core restart clears it.** Guard installed:

- `automation.growatt_auto_reload_when_inverter_data_goes_stale` — if inverter sensors are
  `unavailable` for 45 min, reload the config entry and raise a notification. Bounds the
  failure at ~45 min.

Diagnose availability with:

```
count(homeassistant_entity_available{entity=~".*<serial>.*"} == 0)
```

> **`curl /api/prometheus` without a bearer token returns nothing**, which looks exactly
> like "no data". Query Prometheus itself, not the HA endpoint, when checking whether
> entities are live.

### Local polling (Grott) — built and parked

Modbus is **impossible on this hardware**: the datalogger answers ping but every inbound
port is closed (502, 5279, 80, 8000, 23, 8080). It is an outbound-only dongle, so
`growatt_local` and all Modbus integrations are ruled out by the device.

Proxy interception was built and works end-to-end — LXC running Grott 2.8.3, Mosquitto
broker on HA with a dedicated MQTT user, dongle intercepted and forwarded upstream
correctly. Two findings worth keeping:

- The dongle uses port **7006**, not Grott's default 5279.
- **DNS override does nothing** — it reconnects to a hardcoded IP with no DNS query at all.
  Interception requires **DNAT plus a hairpin MASQUERADE** (same-subnet redirection).

**Rolled back** because Grott could not decode this dongle's records
(*"Invalid data record received"*, nothing published). In that state it added a single point
of failure — if the container died, the DNAT would send the dongle to a dead host and cost
the cloud feed too. The container and broker remain in place; resuming needs only the two
firewall rules re-applied, plus record-layout debugging against the newer protocol.
