from typing import List
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class ReplicationTools(ProxmoxTool):
    def list_jobs(self) -> List[Content]:
        result = self.proxmox.cluster.replication.get()
        return [Content(type="text", text=json.dumps(result))]

    def create_job(self, job: dict) -> List[Content]:
        result = self.proxmox.cluster.replication.post(**(job or {}))
        return [Content(type="text", text=json.dumps(result))]

    def delete_job(self, jobid: str) -> List[Content]:
        result = self.proxmox.cluster.replication(jobid).delete()
        return [Content(type="text", text=json.dumps(result))]


