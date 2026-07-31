#!/usr/bin/env bash
# Drive the Cloudflare side of a subdomain: DNS record + tunnel ingress rule.
#
#   cf-sync.sh bootstrap          Fix/ensure the wildcard: *.guildserver.io DNS -> tunnel,
#                                 and ingress rule *.guildserver.io -> http://<CADDY>
#   cf-sync.sh add <sub>          Ensure <sub>.guildserver.io CNAME -> tunnel (proxied)
#   cf-sync.sh rm  <sub>          Delete that DNS record
#   cf-sync.sh show               Print the tunnel's ingress config + guildserver.io CNAMEs
#
# Add --dry-run to any command to print intended changes without applying them.
#
# ---------------------------------------------------------------------------
# CREDENTIALS — you create these; this script only reads them.
#
#   Make a Cloudflare API token at
#     dash.cloudflare.com -> My Profile -> API Tokens -> Create Token
#   with exactly these permissions:
#     Account | Cloudflare Tunnel | Edit
#     Zone    | DNS               | Edit    (zone: guildserver.io)
#
#   Then:
#     mkdir -p ~/.config/guildserver
#     printf '%s' '<paste-token>' > ~/.config/guildserver/cf-api-token
#     chmod 600 ~/.config/guildserver/cf-api-token
#
#   This is NOT the tunnel connector token in /etc/cloudflared/token on the PDM
#   VM. That one is never read or written by this tooling.
# ---------------------------------------------------------------------------
#
# Env overrides:
#   CF_API_TOKEN        token value (takes precedence over the file)
#   CF_TOKEN_FILE       default: ~/.config/guildserver/cf-api-token
#   DOMAIN              default: guildserver.io
#   CADDY_ORIGIN        default: http://192.168.8.10:80   (must be http://)
#   CF_ACCOUNT_ID       skip account autodiscovery
#   CF_TUNNEL_ID        skip tunnel autodiscovery
set -euo pipefail

DOMAIN="${DOMAIN:-guildserver.io}"
CADDY_ORIGIN="${CADDY_ORIGIN:-http://192.168.8.10:80}"
CF_TOKEN_FILE="${CF_TOKEN_FILE:-$HOME/.config/guildserver/cf-api-token}"
API="https://api.cloudflare.com/client/v4"
DRY_RUN=0

# --- arg parsing -----------------------------------------------------------
args=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    *) args+=("$a") ;;
  esac
done
set -- "${args[@]:-}"

usage() {
  sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 2
}

# --- token -----------------------------------------------------------------
if [ -z "${CF_API_TOKEN:-}" ]; then
  if [ -r "$CF_TOKEN_FILE" ]; then
    CF_API_TOKEN="$(tr -d '\r\n' <"$CF_TOKEN_FILE")"
  else
    cat >&2 <<EOF
ERROR: no Cloudflare API token found.

Create one (Account>Cloudflare Tunnel>Edit, Zone>DNS>Edit for ${DOMAIN}) and save it:

  mkdir -p ~/.config/guildserver
  printf '%s' '<paste-token>' > ${CF_TOKEN_FILE}
  chmod 600 ${CF_TOKEN_FILE}
EOF
    exit 3
  fi
fi
[ -n "$CF_API_TOKEN" ] || { echo "ERROR: token file ${CF_TOKEN_FILE} is empty" >&2; exit 3; }

# --- api helper ------------------------------------------------------------
# Token goes in a header, never in the URL.
cf_api() {
  local method="$1" path="$2" body="${3:-}"
  local resp
  if [ -n "$body" ]; then
    resp="$(curl -sS -X "$method" "${API}${path}" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      --data "$body")"
  else
    resp="$(curl -sS -X "$method" "${API}${path}" \
      -H "Authorization: Bearer ${CF_API_TOKEN}")"
  fi
  if [ "$(jq -r '.success' <<<"$resp")" != "true" ]; then
    echo "Cloudflare API error on ${method} ${path}:" >&2
    jq -r '.errors[]? | "  [\(.code)] \(.message)"' <<<"$resp" >&2
    return 1
  fi
  printf '%s' "$resp"
}

# --- discovery -------------------------------------------------------------
ZONE_ID=""; ACCOUNT_ID="${CF_ACCOUNT_ID:-}"; TUNNEL_ID="${CF_TUNNEL_ID:-}"

discover() {
  local r
  r="$(cf_api GET "/zones?name=${DOMAIN}")"
  ZONE_ID="$(jq -r '.result[0].id // empty' <<<"$r")"
  [ -n "$ZONE_ID" ] || { echo "ERROR: zone ${DOMAIN} not visible to this token" >&2; exit 4; }

  if [ -z "$ACCOUNT_ID" ]; then
    ACCOUNT_ID="$(jq -r '.result[0].account.id // empty' <<<"$r")"
  fi
  [ -n "$ACCOUNT_ID" ] || { echo "ERROR: could not determine account id; set CF_ACCOUNT_ID" >&2; exit 4; }

  if [ -z "$TUNNEL_ID" ]; then
    local tuns ids id cfg
    tuns="$(cf_api GET "/accounts/${ACCOUNT_ID}/cfd_tunnel?is_deleted=false")"
    ids="$(jq -r '.result[].id' <<<"$tuns")"
    # Prefer the tunnel that already serves a hostname in this zone — that is
    # the one with a live connector. Guessing wrong here is exactly how traffic
    # ends up at a stale tunnel.
    for id in $ids; do
      cfg="$(cf_api GET "/accounts/${ACCOUNT_ID}/cfd_tunnel/${id}/configurations" || true)"
      if jq -e --arg d "$DOMAIN" '[.result.config.ingress[]?.hostname // ""]
            | map(select(endswith($d))) | length > 0' <<<"$cfg" >/dev/null 2>&1; then
        TUNNEL_ID="$id"; break
      fi
    done
    if [ -z "$TUNNEL_ID" ]; then
      if [ "$(wc -w <<<"$ids")" -eq 1 ]; then
        TUNNEL_ID="$(tr -d ' \n' <<<"$ids")"
      else
        echo "ERROR: could not pick a tunnel automatically. Candidates:" >&2
        jq -r '.result[] | "  \(.id)  \(.name)"' <<<"$tuns" >&2
        echo "Set CF_TUNNEL_ID to the right one." >&2
        exit 4
      fi
    fi
  fi
}

# --- dns -------------------------------------------------------------------
ensure_cname() {
  local name="$1" target="${TUNNEL_ID}.cfargotunnel.com"
  local existing rec_id cur_content cur_proxied body

  existing="$(cf_api GET "/zones/${ZONE_ID}/dns_records?name=$(printf '%s' "$name" | sed 's/\*/%2A/g')&type=CNAME")"
  rec_id="$(jq -r '.result[0].id // empty' <<<"$existing")"
  cur_content="$(jq -r '.result[0].content // empty' <<<"$existing")"
  cur_proxied="$(jq -r '.result[0].proxied // empty' <<<"$existing")"

  if [ -n "$rec_id" ] && [ "$cur_content" = "$target" ] && [ "$cur_proxied" = "true" ]; then
    echo "  dns   ${name} -> ${target} (proxied)  [already correct]"
    return 0
  fi

  body="$(jq -n --arg n "$name" --arg c "$target" \
    '{type:"CNAME", name:$n, content:$c, proxied:true, ttl:1}')"

  if [ "$DRY_RUN" = 1 ]; then
    if [ -n "$rec_id" ]; then
      echo "  dns   WOULD REPOINT ${name}: ${cur_content} (proxied=${cur_proxied}) -> ${target} (proxied)"
    else
      echo "  dns   WOULD CREATE  ${name} -> ${target} (proxied)"
    fi
    return 0
  fi

  if [ -n "$rec_id" ]; then
    cf_api PUT "/zones/${ZONE_ID}/dns_records/${rec_id}" "$body" >/dev/null
    echo "  dns   ${name} -> ${target} (proxied)  [repointed from ${cur_content}]"
  else
    cf_api POST "/zones/${ZONE_ID}/dns_records" "$body" >/dev/null
    echo "  dns   ${name} -> ${target} (proxied)  [created]"
  fi
}

delete_cname() {
  local name="$1" existing rec_id
  existing="$(cf_api GET "/zones/${ZONE_ID}/dns_records?name=$(printf '%s' "$name" | sed 's/\*/%2A/g')&type=CNAME")"
  rec_id="$(jq -r '.result[0].id // empty' <<<"$existing")"
  if [ -z "$rec_id" ]; then echo "  dns   ${name}  [no record]"; return 0; fi
  if [ "$DRY_RUN" = 1 ]; then echo "  dns   WOULD DELETE ${name}"; return 0; fi
  cf_api DELETE "/zones/${ZONE_ID}/dns_records/${rec_id}" >/dev/null
  echo "  dns   ${name}  [deleted]"
}

# --- tunnel ingress --------------------------------------------------------
# Rule order matters: specific hostnames, then wildcards, then the catch-all.
set_ingress_rule() {
  local host="$1" service="$2" cur new
  cur="$(cf_api GET "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations")"

  new="$(jq --arg h "$host" --arg svc "$service" '
    def isCatch: (has("hostname") | not) or ((.hostname // "") == "");
    def isWild:  ((.hostname // "") | startswith("*"));
    (.result.config // {}) as $cfg
    | ($cfg.ingress // []) as $ing
    | ($ing | map(select((isCatch | not) and (.hostname != $h)))) as $keep
    | ($ing | map(select(isCatch))) as $catch
    | ($keep | map(select(isWild | not))) as $specific
    | ($keep | map(select(isWild)))       as $wild
    | (if ($h | startswith("*"))
       then $specific + $wild + [{hostname:$h, service:$svc, originRequest:{}}]
       else $specific + [{hostname:$h, service:$svc, originRequest:{}}] + $wild
       end) as $rules
    | $cfg + { ingress: ($rules + (if ($catch|length)>0 then $catch else [{service:"http_status:404"}] end)) }
  ' <<<"$cur")"

  if [ "$DRY_RUN" = 1 ]; then
    echo "  tunnel WOULD SET ingress to:"
    jq -r '.ingress[] | "    \(.hostname // "(catch-all)")  ->  \(.service)"' <<<"$new"
    return 0
  fi

  cf_api PUT "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
    "$(jq -n --argjson c "$new" '{config:$c}')" >/dev/null
  echo "  tunnel ingress ${host} -> ${service}"
}

# --- commands --------------------------------------------------------------
cmd="${1:-}"; [ -n "$cmd" ] || usage

case "$cmd" in
  bootstrap)
    discover
    echo "account ${ACCOUNT_ID}  zone ${ZONE_ID}  tunnel ${TUNNEL_ID}"
    case "$CADDY_ORIGIN" in
      http://*) ;;
      *) echo "ERROR: CADDY_ORIGIN must be http:// (Caddy is plaintext on :80), got '${CADDY_ORIGIN}'" >&2; exit 5 ;;
    esac
    ensure_cname "*.${DOMAIN}"
    set_ingress_rule "*.${DOMAIN}" "$CADDY_ORIGIN"
    ;;
  add)
    sub="${2:?usage: cf-sync.sh add <subdomain>}"
    discover
    ensure_cname "${sub}.${DOMAIN}"
    ;;
  rm|remove)
    sub="${2:?usage: cf-sync.sh rm <subdomain>}"
    discover
    delete_cname "${sub}.${DOMAIN}"
    ;;
  show)
    discover
    echo "account ${ACCOUNT_ID}  zone ${ZONE_ID}  tunnel ${TUNNEL_ID}"
    echo "--- tunnel ingress ---"
    cf_api GET "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
      | jq -r '.result.config.ingress[] | "  \(.hostname // "(catch-all)")  ->  \(.service)"'
    echo "--- CNAMEs in ${DOMAIN} pointing at a tunnel ---"
    cf_api GET "/zones/${ZONE_ID}/dns_records?type=CNAME&per_page=100" \
      | jq -r '.result[] | select(.content | endswith("cfargotunnel.com"))
               | "  \(.name)  ->  \(.content)  proxied=\(.proxied)"'
    ;;
  *)
    usage
    ;;
esac
