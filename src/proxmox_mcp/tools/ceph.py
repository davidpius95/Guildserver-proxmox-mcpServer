from typing import List
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class CephTools(ProxmoxTool):
    def status(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).ceph.status.get()
        return [Content(type="text", text=json.dumps(result))]

    def df(self, node: str) -> List[Content]:
        """Per-pool Ceph usage.

        Maps to: GET /nodes/{node}/ceph/pool -- the API has no 'ceph/df' endpoint,
        and this is where the usage figures `ceph df` prints actually come from.
        """
        result = self.proxmox.nodes(node).ceph.pool.get()
        return [Content(type="text", text=json.dumps(result))]


