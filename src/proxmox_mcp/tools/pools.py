from typing import List, Optional
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class PoolTools(ProxmoxTool):
    def list_pools(self) -> List[Content]:
        result = self.proxmox.pools.get()
        return [Content(type="text", text=json.dumps(result))]

    def create_pool(self, poolid: str, comment: Optional[str] = None) -> List[Content]:
        payload = {"poolid": poolid}
        if comment:
            payload["comment"] = comment
        result = self.proxmox.pools.post(**payload)
        return [Content(type="text", text=json.dumps(result))]

    def delete_pool(self, poolid: str) -> List[Content]:
        result = self.proxmox.pools(poolid).delete()
        return [Content(type="text", text=json.dumps(result))]


