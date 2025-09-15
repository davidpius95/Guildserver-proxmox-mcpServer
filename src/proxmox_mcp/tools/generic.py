"""
Generic Proxmox API proxy tool.

Provides a single endpoint to call any Proxmox API path with a method and payload.
Useful to cover the entire Proxmox API surface without bespoke wrappers for each.
"""
from typing import Any, Dict, List, Optional
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class GenericTools(ProxmoxTool):
    """Generic Proxmox API proxy methods."""

    def proxmox_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> List[Content]:
        """Call a Proxmox API endpoint.

        Args:
            method: HTTP method: GET | POST | PUT | DELETE
            path: API path like 'nodes', 'nodes/pve/qemu/100/status/current'
            params: Query/body parameters
            data: Additional body parameters (merged with params for writes)

        Returns:
            List[Content] containing JSON string of response
        """
        try:
            if not isinstance(path, str) or not path:
                raise ValueError("path must be a non-empty string")

            # Normalize path (strip leading slashes or api2/json prefix if given)
            norm = path.lstrip("/")
            if norm.startswith("api2/json/"):
                norm = norm[len("api2/json/") :]

            method_upper = (method or "").upper()
            params = params or {}
            data = data or {}

            # Merge params+data for write operations; GET keeps params only
            write_payload = {**params, **data}

            if method_upper == "GET":
                result = self.proxmox.get(norm, **params)
            elif method_upper == "POST":
                result = self.proxmox.post(norm, **write_payload)
            elif method_upper == "PUT":
                result = self.proxmox.put(norm, **write_payload)
            elif method_upper == "DELETE":
                result = self.proxmox.delete(norm, **params)
            else:
                raise ValueError("Unsupported method. Use GET, POST, PUT or DELETE")

            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"generic request {method} {path}", e)


