"""
Storage-related tools for Proxmox MCP.

This module provides tools for managing and monitoring Proxmox storage:
- Listing all storage pools across the cluster
- Retrieving detailed storage information including:
  * Storage type and content types
  * Usage statistics and capacity
  * Availability status
  * Node assignments

The tools implement fallback mechanisms for scenarios where
detailed storage information might be temporarily unavailable.
"""
from typing import List
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool
from .definitions import GET_STORAGE_DESC

class StorageTools(ProxmoxTool):
    """Tools for managing Proxmox storage.
    
    Provides functionality for:
    - Retrieving cluster-wide storage information
    - Monitoring storage pool status and health
    - Tracking storage utilization and capacity
    - Managing storage content types
    
    Implements fallback mechanisms for scenarios where detailed
    storage information might be temporarily unavailable.
    """

    def get_storage(self) -> List[Content]:
        """List storage pools across the cluster with detailed status.

        Retrieves comprehensive information for each storage pool including:
        - Basic identification (name, type)
        - Content types supported (VM disks, backups, ISO images, etc.)
        - Availability status (online/offline)
        - Usage statistics:
          * Used space
          * Total capacity
          * Available space
        
        Implements a fallback mechanism that returns basic information
        if detailed status retrieval fails for any storage pool.

        Returns:
            List of Content objects containing formatted storage information:
            {
                "storage": "storage-name",
                "type": "storage-type",
                "content": ["content-types"],
                "status": "online/offline",
                "used": bytes,
                "total": bytes,
                "available": bytes
            }

        Raises:
            RuntimeError: If the cluster-wide storage query fails
        """
        try:
            result = self.proxmox.storage.get()
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error("get storage", e)

    def get_storage_content(self, node: str, storage: str) -> List[Content]:
        """List storage content (images, iso, backups).

        Maps to: GET /nodes/{node}/storage/{storage}/content
        """
        try:
            result = self.proxmox.nodes(node).storage(storage).content.get()
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"get storage content for {storage} on node {node}", e)

    def delete_storage_content(self, node: str, storage: str, volume: str) -> List[Content]:
        """Delete content from storage.

        Maps to: DELETE /nodes/{node}/storage/{storage}/content/{volume}
        """
        try:
            result = self.proxmox.nodes(node).storage(storage).content(volume).delete()
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"delete storage content {volume} on {storage}@{node}", e)

    def upload_storage_content(self, node: str, storage: str, content: str, file_path: str, filename: str) -> List[Content]:
        """Upload a file to storage (iso, vztmpl, backup).

        Maps to: POST /nodes/{node}/storage/{storage}/upload
        """
        try:
            with open(file_path, "rb") as fh:
                # proxmoxer supports passing file handle as 'filename'
                result = self.proxmox.nodes(node).storage(storage).upload.post(
                    content=content,
                    filename=(filename, fh),
                )
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"upload storage content to {storage}@{node}", e)
