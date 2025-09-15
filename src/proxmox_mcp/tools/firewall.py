from typing import List
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class FirewallTools(ProxmoxTool):
    """Minimal wrappers for DC-level firewall rules (example subset)."""

    def list_dc_rules(self) -> List[Content]:
        result = self.proxmox.cluster.firewall.rules.get()
        return [Content(type="text", text=json.dumps(result))]

    def add_dc_rule(self, rule: dict) -> List[Content]:
        result = self.proxmox.cluster.firewall.rules.post(**(rule or {}))
        return [Content(type="text", text=json.dumps(result))]

    def delete_dc_rule(self, pos: int) -> List[Content]:
        result = self.proxmox.cluster.firewall.rules(pos).delete()
        return [Content(type="text", text=json.dumps(result))]


