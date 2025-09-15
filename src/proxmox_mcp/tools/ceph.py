from typing import List
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class CephTools(ProxmoxTool):
    def status(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).ceph.status.get()
        return [Content(type="text", text=json.dumps(result))]

    def df(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).ceph.df.get()
        return [Content(type="text", text=json.dumps(result))]


