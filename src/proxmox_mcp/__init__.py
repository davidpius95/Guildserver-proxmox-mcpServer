"""
Proxmox MCP Server - A Model Context Protocol server for interacting with Proxmox hypervisors.
"""

from typing import TYPE_CHECKING

__version__ = "0.1.0"
__all__ = ["ProxmoxMCPServer"]

# Provide ProxmoxMCPServer lazily to avoid importing `server` at package import time,
# which can cause a RuntimeWarning when running `python -m proxmox_mcp.server`.
if TYPE_CHECKING:  # for type checkers only
    from .server import ProxmoxMCPServer  # pragma: no cover

def __getattr__(name):
    if name == "ProxmoxMCPServer":
        from .server import ProxmoxMCPServer as _ProxmoxMCPServer
        return _ProxmoxMCPServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
