from typing import List
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class SDNTools(ProxmoxTool):
    def list_zones(self) -> List[Content]:
        result = self.proxmox.cluster.sdn.zones.get()
        return [Content(type="text", text=json.dumps(result))]

    def list_vnets(self) -> List[Content]:
        result = self.proxmox.cluster.sdn.vnets.get()
        return [Content(type="text", text=json.dumps(result))]


