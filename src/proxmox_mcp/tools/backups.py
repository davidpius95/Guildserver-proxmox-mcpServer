from typing import List
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class BackupTools(ProxmoxTool):
    def vzdump(self, node: str, params: dict) -> List[Content]:
        """Trigger a VZDump backup job.

        Maps to: POST /nodes/{node}/vzdump
        """
        result = self.proxmox.nodes(node).vzdump.post(**(params or {}))
        return [Content(type="text", text=json.dumps({"task": result}))]


