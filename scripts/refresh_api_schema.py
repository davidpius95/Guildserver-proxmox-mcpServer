#!/usr/bin/env python3
"""Regenerate the bundled Proxmox API schema from the official API viewer.

The schema backs pve_find_endpoint / pve_describe_endpoint / pve_call. Re-run it
after a Proxmox upgrade so the validator knows about new endpoints:

    ./scripts/refresh_api_schema.py                 # fetch and rewrite
    ./scripts/refresh_api_schema.py --diff-only     # report changes, write nothing

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

SOURCE = "https://pve.proxmox.com/pve-docs/api-viewer/apidoc.js"
OUT = Path(__file__).resolve().parent.parent / "src" / "proxmox_mcp" / "data" / "pve_api_schema.json"


def fetch(url: str) -> str:
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, timeout=60, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


def parse(js: str) -> list[dict]:
    """Pull the apiSchema array out of the JS file and flatten it."""
    start = js.index("[")
    depth = 0
    end = None
    for i, ch in enumerate(js[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        sys.exit("could not find the end of the apiSchema array -- upstream format changed?")
    tree = json.loads(js[start:end])

    def clean(s, n=400):
        return re.sub(r"\s+", " ", s).strip()[:n] if s else ""

    out: list[dict] = []

    def walk(nodes):
        for n in nodes:
            path, info = n.get("path"), n.get("info")
            if path and info:
                for method, spec in info.items():
                    props = (spec.get("parameters") or {}).get("properties") or {}
                    params = {}
                    for k, v in props.items():
                        if not isinstance(v, dict):
                            continue
                        entry = {"t": v.get("type", "string")}
                        if not v.get("optional"):
                            entry["req"] = 1
                        if desc := clean(v.get("description"), 180):
                            entry["d"] = desc
                        if v.get("enum"):
                            entry["enum"] = v["enum"][:12]
                        params[k] = entry
                    out.append({
                        "path": path,
                        "method": method,
                        "desc": clean(spec.get("description")),
                        "params": params,
                        "perm": clean((spec.get("permissions") or {}).get("description"), 120) or None,
                    })
            if n.get("children"):
                walk(n["children"])

    walk(tree)
    out.sort(key=lambda e: (e["path"], e["method"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diff-only", action="store_true", help="report changes without writing")
    ap.add_argument("--source", default=SOURCE)
    args = ap.parse_args()

    print(f"fetching {args.source} ...")
    endpoints = parse(fetch(args.source))
    new_keys = {(e["method"], e["path"]) for e in endpoints}
    print(f"parsed {len(endpoints)} endpoint+method pairs")

    if OUT.exists():
        old = json.loads(OUT.read_text())
        old_keys = {(e["method"], e["path"]) for e in old["endpoints"]}
        added, removed = sorted(new_keys - old_keys), sorted(old_keys - new_keys)
        print(f"current bundle: {old['count']} pairs  ->  +{len(added)} / -{len(removed)}")
        for m, p in added[:20]:
            print(f"  + {m:<6} {p}")
        for m, p in removed[:20]:
            print(f"  - {m:<6} {p}")
        if len(added) + len(removed) > 40:
            print("  ... (truncated)")
    else:
        print("no existing bundle -- writing a fresh one")

    if args.diff_only:
        print("\n--diff-only: nothing written")
        return

    version = "unknown"
    for e in endpoints:
        if e["path"] == "/version":
            version = "see /version endpoint"
            break
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"source": args.source, "pve_version": version, "count": len(endpoints), "endpoints": endpoints},
        separators=(",", ":"),
    ))
    print(f"\nwrote {OUT.relative_to(OUT.parent.parent.parent.parent)} ({OUT.stat().st_size / 1024:.0f} KB)")
    print("rebuild the containers to pick it up:  docker compose up -d --build --force-recreate")


if __name__ == "__main__":
    main()
