"""Configuration models for the Proxmox MCP server."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SSHConfig(BaseModel):
    """SSH access to the Proxmox nodes themselves.

    Used by ``execute_container_command`` to run ``pct exec`` on the node
    hosting a container -- the Proxmox API has no LXC exec endpoint, so this
    is the only way to get real exit codes and clean stdout/stderr.

    ``hosts`` overrides the address for a given node name; when a node is not
    listed the address is resolved from ``GET /cluster/status``.
    """

    enabled: bool = True
    user: str = "root"
    port: int = 22
    key_file: Optional[str] = None
    connect_timeout: int = 10
    strict_host_key_checking: str = "accept-new"
    known_hosts_file: Optional[str] = None
    hosts: Dict[str, str] = Field(default_factory=dict)


class ProxmoxConfig(BaseModel):
    """Proxmox API connection settings."""

    host: str
    port: int = 8006
    verify_ssl: bool = True
    service: str = "PVE"


class AuthConfig(BaseModel):
    """Proxmox API token authentication settings."""

    user: str
    token_name: str
    token_value: str


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None


class ClusterConfig(BaseModel):
    """A named Proxmox cluster connection."""

    name: str
    proxmox: ProxmoxConfig
    auth: AuthConfig


class Config(BaseModel):
    """Complete MCP server configuration."""

    proxmox: ProxmoxConfig
    auth: AuthConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    ssh: SSHConfig = Field(default_factory=SSHConfig)
    default_cluster: Optional[str] = None
    clusters: List[ClusterConfig] = Field(default_factory=list)
