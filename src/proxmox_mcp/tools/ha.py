from typing import List, Optional
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class HATools(ProxmoxTool):
    def list_groups(self) -> List[Content]:
        result = self.proxmox.cluster.ha.groups.get()
        return [Content(type="text", text=json.dumps(result))]

    def create_group(self, group: str, nodes: str, comment: Optional[str] = None) -> List[Content]:
        payload = {"group": group, "nodes": nodes}
        if comment:
            payload["comment"] = comment
        result = self.proxmox.cluster.ha.groups.post(**payload)
        return [Content(type="text", text=json.dumps(result))]

    def list_resources(self) -> List[Content]:
        result = self.proxmox.cluster.ha.resources.get()
        return [Content(type="text", text=json.dumps(result))]

    def add_resource(self, sid: str, group: str) -> List[Content]:
        result = self.proxmox.cluster.ha.resources.post(sid=sid, group=group)
        return [Content(type="text", text=json.dumps(result))]

    def delete_resource(self, sid: str) -> List[Content]:
        result = self.proxmox.cluster.ha.resources(sid).delete()
        return [Content(type="text", text=json.dumps(result))]


