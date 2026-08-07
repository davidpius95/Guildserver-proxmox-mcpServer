"""
Tests for LXC container command execution.

Covers the ssh (`pct exec`) backend, the sentinel framing used by the
termproxy PTY backend, and the auto-fallback decision between them.
"""

import base64
from unittest.mock import AsyncMock, Mock, patch

import pytest

from proxmox_mcp.config.models import AuthConfig, ProxmoxConfig, SSHConfig
from proxmox_mcp.tools.console.container_manager import (
    ContainerExecError,
    LXCConsoleManager,
    _SSHUnavailable,
)


@pytest.fixture
def mock_proxmox():
    mock = Mock()
    mock.nodes.return_value.lxc.return_value.status.current.get.return_value = {
        "status": "running"
    }
    mock.cluster.status.get.return_value = [
        {"type": "cluster", "name": "Guild-A"},
        {"type": "node", "name": "nodeA", "ip": "192.168.8.112"},
        {"type": "node", "name": "nodeB", "ip": "192.168.8.155"},
    ]
    return mock


@pytest.fixture
def manager(mock_proxmox):
    return LXCConsoleManager(
        mock_proxmox,
        ssh_config=SSHConfig(key_file="/app/ssh/id_node"),
        proxmox_config=ProxmoxConfig(host="192.168.8.125", verify_ssl=False),
        auth_config=AuthConfig(user="root@pam", token_name="nodeE", token_value="secret"),
    )


def _fake_proc(stdout=b"", stderr=b"", rc=0):
    proc = Mock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = rc
    return proc


# ---------------------------------------------------------------- ssh backend


@pytest.mark.asyncio
async def test_ssh_success(manager):
    with patch("asyncio.create_subprocess_exec", return_value=_fake_proc(b"active\n")) as spawn:
        result = await manager.execute_command("nodeA", "910", "systemctl is-active nginx")

    assert result["success"] is True
    assert result["output"] == "active\n"
    assert result["exit_code"] == 0
    assert result["backend"] == "ssh"
    assert result["fallback_reason"] is None

    argv = spawn.call_args[0]
    assert argv[0] == "ssh"
    assert "root@192.168.8.112" in argv  # resolved from /cluster/status
    assert argv[-1] == "pct exec 910 -- /bin/sh -c 'systemctl is-active nginx'"


@pytest.mark.asyncio
async def test_ssh_honours_host_override(mock_proxmox):
    manager = LXCConsoleManager(
        mock_proxmox,
        ssh_config=SSHConfig(hosts={"nodeA": "100.73.229.110"}),
    )
    with patch("asyncio.create_subprocess_exec", return_value=_fake_proc(b"ok")) as spawn:
        await manager.execute_command("nodeA", "910", "true")
    assert "root@100.73.229.110" in spawn.call_args[0]


@pytest.mark.asyncio
async def test_ssh_quotes_command_safely(manager):
    """A command with quotes and semicolons must reach the container intact."""
    nasty = "echo 'a b'; rm -rf $NOPE"
    with patch("asyncio.create_subprocess_exec", return_value=_fake_proc(b"")) as spawn:
        await manager.execute_command("nodeA", "910", nasty)
    remote = spawn.call_args[0][-1]
    assert remote == "pct exec 910 -- /bin/sh -c " + "'echo '\"'\"'a b'\"'\"'; rm -rf $NOPE'"


@pytest.mark.asyncio
async def test_command_failure_is_a_result_not_a_fallback(manager):
    """Non-zero exit from the command must NOT trigger the termproxy fallback."""
    proc = _fake_proc(b"", b"No such file\n", rc=2)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await manager.execute_command("nodeA", "910", "cat /nope")

    assert result["success"] is False
    assert result["exit_code"] == 2
    assert result["backend"] == "ssh"  # did not fall back


@pytest.mark.asyncio
async def test_ssh_transport_failure_falls_back(manager):
    proc = _fake_proc(b"", b"ssh: connect to host 192.168.8.112 port 22: Connection refused\n", rc=255)
    with patch("asyncio.create_subprocess_exec", return_value=proc), \
         patch.object(manager, "_exec_via_termproxy", new=AsyncMock(return_value={
             "success": True, "output": "hi", "error": "", "exit_code": 0,
             "backend": "termproxy", "node": "nodeA", "vmid": "910",
         })):
        result = await manager.execute_command("nodeA", "910", "echo hi")

    assert result["backend"] == "termproxy"
    assert "connection refused" in result["fallback_reason"].lower()


@pytest.mark.asyncio
async def test_exit_255_from_command_is_not_a_transport_failure(manager):
    """255 is ssh's own code, but a command may return it legitimately."""
    proc = _fake_proc(b"out", b"", rc=255)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await manager.execute_command("nodeA", "910", "exit 255")
    assert result["backend"] == "ssh"
    assert result["exit_code"] == 255


@pytest.mark.asyncio
async def test_missing_ssh_binary_falls_back(manager):
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()), \
         patch.object(manager, "_exec_via_termproxy", new=AsyncMock(return_value={
             "success": True, "output": "", "error": "", "exit_code": 0,
             "backend": "termproxy", "node": "nodeA", "vmid": "910",
         })):
        result = await manager.execute_command("nodeA", "910", "true")
    assert result["backend"] == "termproxy"


@pytest.mark.asyncio
async def test_backend_ssh_does_not_fall_back(manager):
    proc = _fake_proc(b"", b"Permission denied (publickey).\n", rc=255)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(ContainerExecError, match="SSH backend unavailable"):
            await manager.execute_command("nodeA", "910", "true", backend="ssh")


# ------------------------------------------------------------ pre-flight


@pytest.mark.asyncio
async def test_stopped_container_rejected(manager, mock_proxmox):
    mock_proxmox.nodes.return_value.lxc.return_value.status.current.get.return_value = {
        "status": "stopped"
    }
    with pytest.raises(ValueError, match="not running"):
        await manager.execute_command("nodeA", "9002", "true")


@pytest.mark.asyncio
async def test_missing_container_rejected(manager, mock_proxmox):
    mock_proxmox.nodes.return_value.lxc.return_value.status.current.get.side_effect = (
        Exception("Configuration file does not exist")
    )
    with pytest.raises(ValueError, match="not found"):
        await manager.execute_command("nodeA", "404", "true")


@pytest.mark.asyncio
async def test_invalid_backend_rejected(manager):
    with pytest.raises(ValueError, match="Invalid backend"):
        await manager.execute_command("nodeA", "910", "true", backend="carrier-pigeon")


@pytest.mark.asyncio
async def test_empty_command_rejected(manager):
    with pytest.raises(ValueError, match="non-empty"):
        await manager.execute_command("nodeA", "910", "   ")


# ------------------------------------------------------ termproxy framing


def test_sentinel_roundtrip():
    nonce = "cafe1234"
    payload = base64.b64encode(b"hello\nworld\n").decode()
    buf = f"__B{nonce}__\r\n{payload}\r\n__E{nonce}__:0\r\n"
    assert LXCConsoleManager._parse_sentinels(buf, nonce) == ("hello\nworld\n", 0)


def test_sentinel_ignores_echoed_input():
    """The PTY echoes the command line, which itself contains the markers."""
    nonce = "cafe1234"
    payload = base64.b64encode(b"real output").decode()
    echoed = LXCConsoleManager._wrap_for_sentinels("echo hi", nonce)
    buf = f"{echoed}\r\n__B{nonce}__\r\n{payload}\r\n__E{nonce}__:0\r\n"
    output, rc = LXCConsoleManager._parse_sentinels(buf, nonce)
    assert output == "real output"
    assert rc == 0


def test_sentinel_incomplete_returns_none():
    nonce = "cafe1234"
    assert LXCConsoleManager._parse_sentinels(f"__B{nonce}__\r\nQUJD", nonce) is None


def test_sentinel_preserves_nonzero_exit():
    nonce = "beef5678"
    payload = base64.b64encode(b"boom").decode()
    buf = f"__B{nonce}__\r\n{payload}\r\n__E{nonce}__:42\r\n"
    assert LXCConsoleManager._parse_sentinels(buf, nonce) == ("boom", 42)
