"""
Module for managing LXC container console operations.

Unlike VMs -- which expose a real exec endpoint through the QEMU guest agent --
the Proxmox API has **no LXC exec endpoint**. ``pct exec`` is CLI-only and has
no REST equivalent. This module therefore provides two backends and picks
between them:

1. **ssh** -- SSH to the node hosting the container and run
   ``pct exec <vmid> -- /bin/sh -c '<command>'``. Gives real exit codes and
   cleanly separated stdout/stderr. Requires SSH access to the node.

2. **termproxy** -- ``POST /nodes/{node}/lxc/{vmid}/termproxy`` followed by
   ``GET .../vncwebsocket``, which is exactly how the Proxmox web UI attaches
   a console. Pure API, no SSH and no in-container agent, but it is a PTY:
   there is no out-of-band exit status, so the command is wrapped in sentinel
   markers and its output is base64-framed to survive terminal mangling.

The default backend is ``auto``: try ssh, fall back to termproxy when the SSH
layer itself is unavailable (auth, routing, missing key). A command that runs
and *fails* is a result, not a fallback trigger.
"""

import asyncio
import base64
import logging
import os
import re
import secrets
import shlex
import ssl
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from ...config.models import AuthConfig, ProxmoxConfig, SSHConfig

# stderr fragments that mean "the SSH transport never got us to a shell", as
# opposed to "the remote command ran and exited non-zero".
_SSH_LAYER_ERRORS = (
    "permission denied",
    "connection refused",
    "connection timed out",
    "connection closed by remote host",
    "could not resolve hostname",
    "host key verification failed",
    "no route to host",
    "network is unreachable",
    "ssh: connect to host",
    "too many authentication failures",
    "operation timed out",
    "broken pipe",
    "no such identity",
    "identity file",
    "bad configuration option",
    "kex_exchange_identification",
)


class ContainerExecError(RuntimeError):
    """Raised when a container command cannot be executed by any backend."""


class _SSHUnavailable(Exception):
    """Internal: the SSH transport failed before the command could run."""


class LXCConsoleManager:
    """Executes commands inside LXC containers.

    Args:
        proxmox_api: Initialized ProxmoxAPI instance (used for status checks
            and for issuing termproxy tickets).
        ssh_config: SSH settings for reaching the nodes.
        proxmox_config: Connection settings, needed to build the websocket URL.
        auth_config: API token, needed to authenticate the websocket upgrade.
    """

    def __init__(
        self,
        proxmox_api: Any,
        ssh_config: Optional[SSHConfig] = None,
        proxmox_config: Optional[ProxmoxConfig] = None,
        auth_config: Optional[AuthConfig] = None,
    ):
        self.proxmox = proxmox_api
        self.ssh = ssh_config or SSHConfig()
        self.proxmox_config = proxmox_config
        self.auth_config = auth_config
        self.logger = logging.getLogger("proxmox-mcp.lxc-console")
        self._node_addr_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------
    async def execute_command(
        self,
        node: str,
        vmid: str,
        command: str,
        timeout: int = 60,
        backend: str = "auto",
    ) -> Dict[str, Any]:
        """Run ``command`` inside container ``vmid`` on ``node``.

        Args:
            node: Node hosting the container (e.g. 'nodeA').
            vmid: Container ID (e.g. '910').
            command: Shell command to run inside the container.
            timeout: Seconds to wait before giving up.
            backend: 'auto' (ssh then termproxy), 'ssh', or 'termproxy'.

        Returns:
            {"success": bool, "output": str, "error": str, "exit_code": int|None,
             "backend": str, "node": str, "vmid": str, "fallback_reason": str|None}

        Raises:
            ValueError: If the container is missing, stopped, or `backend` is invalid.
            ContainerExecError: If every eligible backend failed.
        """
        if backend not in ("auto", "ssh", "termproxy"):
            raise ValueError(
                f"Invalid backend '{backend}'. Expected 'auto', 'ssh', or 'termproxy'."
            )
        if not command or not command.strip():
            raise ValueError("command must be a non-empty string")

        self._verify_running(node, vmid)

        fallback_reason: Optional[str] = None

        if backend in ("auto", "ssh") and self.ssh.enabled:
            try:
                result = await self._exec_via_ssh(node, vmid, command, timeout)
                result["fallback_reason"] = None
                return result
            except _SSHUnavailable as e:
                if backend == "ssh":
                    raise ContainerExecError(
                        f"SSH backend unavailable for {node}:{vmid}: {e}"
                    ) from e
                fallback_reason = f"ssh unavailable: {e}"
                self.logger.warning(
                    "SSH exec failed for %s:%s, falling back to termproxy: %s",
                    node, vmid, e,
                )
        elif backend == "ssh" and not self.ssh.enabled:
            raise ContainerExecError(
                "SSH backend requested but disabled in config (ssh.enabled = false)"
            )
        elif backend == "auto":
            fallback_reason = "ssh disabled in config"

        result = await self._exec_via_termproxy(node, vmid, command, timeout)
        result["fallback_reason"] = fallback_reason
        return result

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------
    def _verify_running(self, node: str, vmid: str) -> None:
        """Both backends need a running container; fail early and clearly."""
        try:
            status = self.proxmox.nodes(node).lxc(int(vmid)).status.current.get()
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "does not exist" in msg:
                raise ValueError(f"Container {vmid} not found on node {node}") from e
            raise ContainerExecError(
                f"Could not read status for container {vmid} on {node}: {e}"
            ) from e

        if isinstance(status, dict):
            state = status.get("data", status)
            current = (state or {}).get("status")
            if current and current != "running":
                raise ValueError(
                    f"Container {vmid} on {node} is '{current}', not running. "
                    f"Start it first with start_container."
                )

    @staticmethod
    def _wrap_for_sentinels(command: str, nonce: str) -> str:
        """Wrap a command so its output and exit code survive a shared PTY.

        The captured output is base64-encoded, so it cannot itself contain the
        sentinel markers, and the terminal cannot mangle it with CR/LF or ANSI
        sequences. The input line is echoed back by the PTY before the real
        output arrives, which is why callers match on the *last* marker.
        """
        return (
            f"__o=$( {{ {command} ; }} 2>&1 ); __r=$?; "
            f"echo \"__B{nonce}__\"; "
            f"printf '%s' \"$__o\" | base64 | tr -d '\\n'; echo; "
            f"echo \"__E{nonce}__:$__r\""
        )

    @staticmethod
    def _parse_sentinels(buffer: str, nonce: str) -> Optional[Tuple[str, int]]:
        """Extract (output, exit_code) from PTY text, or None if incomplete."""
        end = re.search(rf"__E{nonce}__:(\d+)", buffer)
        if not end:
            return None
        begin_marker = f"__B{nonce}__"
        begin = buffer.rfind(begin_marker, 0, end.start())
        if begin == -1:
            return None

        payload = buffer[begin + len(begin_marker):end.start()]
        # Strip everything that is not part of the base64 alphabet -- the PTY
        # inserts CR, LF and occasionally ANSI sequences around the payload.
        b64 = re.sub(r"[^A-Za-z0-9+/=]", "", payload)
        try:
            output = base64.b64decode(b64, validate=False).decode("utf-8", "replace")
        except Exception:
            output = payload.strip()
        return output, int(end.group(1))

    # ------------------------------------------------------------------
    # backend 1: ssh -> pct exec
    # ------------------------------------------------------------------
    def _resolve_node_address(self, node: str) -> str:
        """Map a node name to a reachable address.

        Explicit `ssh.hosts` config wins; otherwise the IP is read from
        /cluster/status; otherwise the node name is used as a hostname.
        """
        if node in self.ssh.hosts:
            return self.ssh.hosts[node]
        if node in self._node_addr_cache:
            return self._node_addr_cache[node]

        try:
            entries = self.proxmox.cluster.status.get()
            if isinstance(entries, dict):
                entries = entries.get("data", [])
            for entry in entries or []:
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") == "node" and entry.get("name") and entry.get("ip"):
                    self._node_addr_cache[entry["name"]] = entry["ip"]
        except Exception as e:
            self.logger.debug("Could not resolve node addresses from cluster status: %s", e)

        return self._node_addr_cache.get(node, node)

    def _ssh_argv(self, node: str, vmid: str, command: str) -> List[str]:
        address = self._resolve_node_address(node)
        known_hosts = self.ssh.known_hosts_file or os.devnull
        argv = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.ssh.connect_timeout}",
            "-o", f"StrictHostKeyChecking={self.ssh.strict_host_key_checking}",
            "-o", f"UserKnownHostsFile={known_hosts}",
            "-o", "LogLevel=ERROR",
            "-p", str(self.ssh.port),
        ]
        if self.ssh.key_file:
            argv += ["-i", os.path.expanduser(self.ssh.key_file)]
        argv.append(f"{self.ssh.user}@{address}")
        # One level of quoting: ssh joins argv with spaces and the remote login
        # shell parses the result exactly once.
        argv.append(f"pct exec {int(vmid)} -- /bin/sh -c {shlex.quote(command)}")
        return argv

    async def _exec_via_ssh(
        self, node: str, vmid: str, command: str, timeout: int
    ) -> Dict[str, Any]:
        argv = self._ssh_argv(node, vmid, command)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise _SSHUnavailable("ssh client not installed in this image") from e

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ContainerExecError(
                f"Command timed out after {timeout}s on {node}:{vmid} (ssh backend)"
            )

        stdout = stdout_b.decode("utf-8", "replace")
        stderr = stderr_b.decode("utf-8", "replace")
        rc = proc.returncode

        # 255 is ssh's own failure code, but a remote command may legitimately
        # return it -- only treat it as transport failure if stderr agrees.
        lowered = stderr.lower()
        if rc == 255 and any(frag in lowered for frag in _SSH_LAYER_ERRORS):
            raise _SSHUnavailable(stderr.strip().splitlines()[0] if stderr.strip() else "exit 255")
        if "pct: command not found" in lowered:
            raise _SSHUnavailable("pct not available on node (is this a Proxmox host?)")

        return {
            "success": rc == 0,
            "output": stdout,
            "error": stderr,
            "exit_code": rc,
            "backend": "ssh",
            "node": node,
            "vmid": str(vmid),
        }

    # ------------------------------------------------------------------
    # backend 2: termproxy websocket
    # ------------------------------------------------------------------
    def _termproxy_ticket(self, node: str, vmid: str) -> Dict[str, Any]:
        result = self.proxmox.nodes(node).lxc(int(vmid)).termproxy.post()
        if isinstance(result, dict) and "data" in result and isinstance(result["data"], dict):
            result = result["data"]
        if not isinstance(result, dict) or "ticket" not in result or "port" not in result:
            raise ContainerExecError(f"Unexpected termproxy response for {node}:{vmid}: {result!r}")
        return result

    async def _exec_via_termproxy(
        self, node: str, vmid: str, command: str, timeout: int
    ) -> Dict[str, Any]:
        try:
            import websockets
        except ImportError as e:  # pragma: no cover - dependency is declared
            raise ContainerExecError(
                "termproxy backend requires the 'websockets' package"
            ) from e

        if not self.proxmox_config or not self.auth_config:
            raise ContainerExecError(
                "termproxy backend needs proxmox/auth config; none was supplied"
            )

        ticket_info = self._termproxy_ticket(node, vmid)
        ticket = ticket_info["ticket"]
        term_port = ticket_info["port"]
        ws_user = ticket_info.get("user") or self.auth_config.user

        host = self.proxmox_config.host
        api_port = self.proxmox_config.port
        # The ticket is base64 and contains '+', '/' and '=' -- it MUST be
        # percent-encoded or the server sees a different ticket and 401s.
        query = urllib.parse.urlencode({"port": term_port, "vncticket": ticket})
        url = (
            f"wss://{host}:{api_port}/api2/json/nodes/{node}/lxc/{int(vmid)}"
            f"/vncwebsocket?{query}"
        )

        token_name = self.auth_config.token_name
        prefix = f"{self.auth_config.user}!"
        if token_name.startswith(prefix):
            token_name = token_name[len(prefix):]
        headers = {
            "Authorization": (
                f"PVEAPIToken={self.auth_config.user}!{token_name}"
                f"={self.auth_config.token_value}"
            )
        }

        ssl_ctx = ssl.create_default_context()
        if not self.proxmox_config.verify_ssl:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        nonce = secrets.token_hex(8)
        payload = self._wrap_for_sentinels(command, nonce)

        try:
            return await asyncio.wait_for(
                self._drive_terminal(
                    websockets, url, headers, ssl_ctx, ws_user, ticket, payload, nonce,
                    node, vmid,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise ContainerExecError(
                f"Command timed out after {timeout}s on {node}:{vmid} (termproxy backend)"
            )

    async def _drive_terminal(
        self, websockets, url, headers, ssl_ctx, ws_user, ticket, payload, nonce, node, vmid
    ) -> Dict[str, Any]:
        """Speak the pve-manager termproxy protocol over the websocket.

        Framing, as implemented by the xterm.js console in pve-manager:
          * first message is ``user:ticket\\n`` and the server answers ``OK``
          * keyboard input is ``0:<byte-length>:<data>``
          * ``2`` is a keepalive ping
        """
        connect_kwargs = {"ssl": ssl_ctx, "max_size": None}
        try:
            conn = websockets.connect(url, additional_headers=headers, **connect_kwargs)
        except TypeError:
            # websockets < 14 spells this differently
            conn = websockets.connect(url, extra_headers=headers, **connect_kwargs)

        async with conn as ws:
            await ws.send(f"{ws_user}:{ticket}\n")

            greeting = await ws.recv()
            if isinstance(greeting, bytes):
                greeting = greeting.decode("utf-8", "replace")
            if "OK" not in greeting:
                raise ContainerExecError(
                    f"termproxy authentication rejected for {node}:{vmid}: {greeting!r}"
                )

            data = payload + "\n"
            await ws.send(f"0:{len(data.encode()):d}:{data}")

            buffer = ""
            while True:
                chunk = await ws.recv()
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8", "replace")
                buffer += chunk

                parsed = self._parse_sentinels(buffer, nonce)
                if parsed is not None:
                    output, rc = parsed
                    return {
                        "success": rc == 0,
                        "output": output,
                        # A PTY merges the two streams; say so rather than
                        # inventing an empty stderr.
                        "error": "" if rc == 0 else output,
                        "exit_code": rc,
                        "backend": "termproxy",
                        "node": node,
                        "vmid": str(vmid),
                        "streams_merged": True,
                    }
