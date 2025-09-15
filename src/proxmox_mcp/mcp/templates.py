from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


@dataclass
class TemplateConfig:
    base_url: str
    mode: str
    auth_type: str
    api_key: Optional[str]
    templates: Dict[str, str]
    fragments: Dict[str, str]


def load_template_config(path: str = "config/mcp_integration.yaml") -> TemplateConfig:
    data = yaml.safe_load(Path(path).read_text())
    server = data.get("mcp_server", {})
    templates = data.get("command_templates", {})
    fragments = data.get("fragments", {})
    auth = server.get("authentication", {})
    return TemplateConfig(
        base_url=server.get("base_url", "http://localhost:8811"),
        mode=server.get("mode", "openapi"),
        auth_type=auth.get("type", "none"),
        api_key=auth.get("api_key"),
        templates=templates,
        fragments=fragments,
    )


def render_prompt(template_key: str, params: Dict[str, Any], cfg: Optional[TemplateConfig] = None) -> str:
    if cfg is None:
        cfg = load_template_config()
    tpl = cfg.templates.get(template_key)
    if not tpl:
        # Fallback: generic description
        return f"Execute {template_key} with parameters: {params}"

    # Build optional fragments
    fragments: Dict[str, str] = {}
    for name, frag_tpl in cfg.fragments.items():
        try:
            filled = frag_tpl.format(**params)
        except Exception:
            filled = frag_tpl
        # include only if all referenced keys exist and are truthy
        keys_present = all(k in params and params[k] not in (None, "") for k in _extract_placeholders(frag_tpl))
        fragments[name] = (filled if keys_present else "")

    # Merge params and fragments for final formatting
    merged = {**params, **fragments}
    try:
        return tpl.format(**merged)
    except Exception:
        # Best-effort fallback
        return f"{tpl} | Params: {merged}"


def _extract_placeholders(s: str) -> set[str]:
    import string

    formatter = string.Formatter()
    names = set()
    for literal_text, field_name, format_spec, conversion in formatter.parse(s):
        if field_name:
            names.add(field_name)
    return names


