from typing import List, Optional
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class AdminTools(ProxmoxTool):
    """Node administrative wrappers: services, network, apt, certificates, disks."""

    # Services
    def list_services(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).services.get()
        return [Content(type="text", text=json.dumps(result))]

    def service_action(self, node: str, service: str, action: str) -> List[Content]:
        endpoint = getattr(self.proxmox.nodes(node).services(service), action)
        result = endpoint.post()
        return [Content(type="text", text=json.dumps({"task": result}))]

    # Network
    def network_get(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).network.get()
        return [Content(type="text", text=json.dumps(result))]

    def network_apply(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).network.apply.post()
        return [Content(type="text", text=json.dumps(result))]

    # APT
    def list_updates(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).apt.update.get()
        return [Content(type="text", text=json.dumps(result))]

    def list_repositories(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).apt.repositories.get()
        return [Content(type="text", text=json.dumps(result))]

    # Certificates
    def get_certificates(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).certificates.info.get()
        return [Content(type="text", text=json.dumps(result))]

    # Disks
    def list_disks(self, node: str) -> List[Content]:
        result = self.proxmox.nodes(node).disks.list.get()
        return [Content(type="text", text=json.dumps(result))]


