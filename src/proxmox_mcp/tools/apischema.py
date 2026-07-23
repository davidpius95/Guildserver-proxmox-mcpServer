"""Schema-driven access to the complete Proxmox VE API.

The hand-written tools in this package wrap ~75 of the API's 675 endpoint+method
pairs. This module covers the rest without adding 600 tool definitions to every
client's context: it ships the official API schema (scraped from the PVE API
viewer) and exposes three tools over it --

    pve_find_endpoint    search all 675 endpoints by keyword
    pve_describe_endpoint  parameters, types, required flags, permissions
    pve_call             call any endpoint, with parameters validated first

`pve_call` differs from `proxmox_request` in that it checks the request against
the schema before it leaves the machine: unknown path, wrong method, missing
required parameter, or unknown parameter all fail locally with a useful message
rather than as an opaque 400/501 from Proxmox.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import TextContent as Content

from .base import ProxmoxTool

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "pve_api_schema.json"


@lru_cache(maxsize=1)
def _schema() -> Dict[str, Any]:
    with SCHEMA_PATH.open() as fh:
        return json.load(fh)


def _endpoints() -> List[Dict[str, Any]]:
    return _schema()["endpoints"]


def _norm(path: str) -> str:
    """Strip api2/json prefix and surrounding slashes."""
    p = (path or "").strip().lstrip("/")
    if p.startswith("api2/json/"):
        p = p[len("api2/json/"):]
    return p.rstrip("/")


def _template_regex(template: str) -> re.Pattern:
    """/nodes/{node}/qemu/{vmid} -> matches nodes/pve/qemu/100"""
    parts = [
        r"[^/]+" if seg.startswith("{") and seg.endswith("}") else re.escape(seg)
        for seg in _norm(template).split("/")
    ]
    return re.compile("^" + "/".join(parts) + "$")


def _match(path: str, method: Optional[str] = None) -> List[Dict[str, Any]]:
    """Find schema entries whose template matches a concrete or templated path."""
    target = _norm(path)
    want = (method or "").upper()
    exact, wildcard = [], []
    for e in _endpoints():
        if want and e["method"] != want:
            continue
        if _norm(e["path"]) == target:
            exact.append(e)
        elif _template_regex(e["path"]).match(target):
            wildcard.append(e)
    return exact or wildcard


def _fmt_params(params: Dict[str, Any]) -> List[str]:
    lines = []
    for name, spec in sorted(params.items(), key=lambda kv: (not kv[1].get("req"), kv[0])):
        flag = "*" if spec.get("req") else " "
        bits = [f"  {flag} {name} ({spec.get('t', 'string')})"]
        if spec.get("enum"):
            bits.append("    values: " + ", ".join(map(str, spec["enum"])))
        if spec.get("d"):
            bits.append(f"    {spec['d']}")
        lines.extend(bits)
    return lines


class ApiSchemaTools(ProxmoxTool):
    """Discovery and validated invocation across the whole PVE API."""

    def find_endpoint(
        self, query: str, method: Optional[str] = None, limit: int = 25
    ) -> List[Content]:
        terms = [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]
        if not terms:
            raise ValueError("query must not be empty")
        want = (method or "").upper()

        scored = []
        for e in _endpoints():
            if want and e["method"] != want:
                continue
            hay = f"{e['path']} {e['desc']}".lower()
            if not all(t in hay for t in terms):
                continue
            # prefer matches in the path over matches in prose, and shallow paths
            path_hits = sum(t in e["path"].lower() for t in terms)
            scored.append((-path_hits, e["path"].count("/"), e["path"], e["method"], e))

        scored.sort()
        total = len(scored)
        rows = [f"{total} endpoint(s) match {terms}" + (f" [{want}]" if want else "")]
        if total > limit:
            rows[0] += f" -- showing first {limit}"
        for *_, e in scored[:limit]:
            desc = e["desc"][:110]
            rows.append(f"  {e['method']:<6} {e['path']}")
            if desc:
                rows.append(f"         {desc}")
        if not total:
            rows.append("  (nothing matched -- try fewer or more general terms)")
        return [Content(type="text", text="\n".join(rows))]

    def describe_endpoint(self, path: str, method: Optional[str] = None) -> List[Content]:
        hits = _match(path, method)
        if not hits:
            return [Content(
                type="text",
                text=f"No endpoint matches '{path}'"
                     + (f" [{method}]" if method else "")
                     + ".\nUse pve_find_endpoint to search by keyword.",
            )]
        out = []
        for e in hits:
            out.append(f"{e['method']} {e['path']}")
            if e.get("desc"):
                out.append(f"  {e['desc']}")
            if e.get("perm"):
                out.append(f"  permissions: {e['perm']}")
            params = e.get("params") or {}
            if params:
                req = sum(1 for s in params.values() if s.get("req"))
                out.append(f"  parameters ({len(params)}, {req} required, * = required):")
                out.extend(_fmt_params(params))
            else:
                out.append("  parameters: none")
            out.append("")
        return [Content(type="text", text="\n".join(out).rstrip())]

    def call(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        skip_validation: bool = False,
    ) -> List[Content]:
        want = (method or "").upper()
        if want not in ("GET", "POST", "PUT", "DELETE"):
            raise ValueError("method must be GET, POST, PUT or DELETE")
        params = params or {}
        norm = _norm(path)

        if not skip_validation:
            hits = _match(norm, want)
            if not hits:
                any_method = _match(norm)
                if any_method:
                    offered = sorted({h["method"] for h in any_method})
                    raise ValueError(
                        f"{want} {norm} is not in the API. That path offers: {', '.join(offered)}."
                    )
                raise ValueError(
                    f"No API endpoint matches '{norm}'. "
                    "Use pve_find_endpoint to search, or pass skip_validation=True to send anyway."
                )
            spec = hits[0]
            declared = spec.get("params") or {}
            # Path placeholders are supplied in the URL, not the body.
            placeholders = set(re.findall(r"\{(\w+)\}", spec["path"]))
            missing = [
                n for n, s in declared.items()
                if s.get("req") and n not in params and n not in placeholders
            ]
            if missing:
                raise ValueError(
                    f"{want} {spec['path']} is missing required parameter(s): {', '.join(sorted(missing))}. "
                    "Run pve_describe_endpoint for the full signature."
                )
            # Proxmox declares repeatable parameters as 'net[n]', 'scsi[n]', 'ide[n]'
            # and so on; the caller sends the concrete 'net0' / 'scsi1'.
            indexed = [k[:-3] for k in declared if k.endswith("[n]")]
            def _known(name: str) -> bool:
                if name in declared:
                    return True
                return any(
                    name.startswith(prefix) and name[len(prefix):].isdigit()
                    for prefix in indexed
                )

            unknown = [n for n in params if not _known(n)]
            if unknown:
                raise ValueError(
                    f"{want} {spec['path']} does not accept: {', '.join(sorted(unknown))}. "
                    f"Accepted: {', '.join(sorted(declared)) or '(none)'}."
                )

        try:
            if want == "GET":
                result = self.proxmox.get(norm, **params)
            elif want == "POST":
                result = self.proxmox.post(norm, **params)
            elif want == "PUT":
                result = self.proxmox.put(norm, **params)
            else:
                result = self.proxmox.delete(norm, **params)
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"pve_call {want} {norm}", e)

    def coverage(self) -> List[Content]:
        """Summarise the bundled schema -- useful for sanity checks."""
        s = _schema()
        by_section: Dict[str, int] = {}
        for e in _endpoints():
            sec = e["path"].strip("/").split("/")[0]
            by_section[sec] = by_section.get(sec, 0) + 1
        lines = [
            f"Bundled PVE API schema: {s['count']} endpoint+method pairs (PVE {s['pve_version']})",
            f"source: {s['source']}",
            "",
            "by section:",
        ]
        lines += [f"  /{k:<10} {v}" for k, v in sorted(by_section.items(), key=lambda kv: -kv[1])]
        return [Content(type="text", text="\n".join(lines))]
