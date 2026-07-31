"""Configuration models for the Proxmox MCP server."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


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
    default_cluster: Optional[str] = None
    clusters: List[ClusterConfig] = Field(default_factory=list)
