"""
Main server implementation for Proxmox MCP.

This module implements the core MCP server for Proxmox integration, providing:
- Configuration loading and validation
- Logging setup
- Proxmox API connection management
- MCP tool registration and routing
- Signal handling for graceful shutdown

The server exposes a set of tools for managing Proxmox resources including:
- Node management
- VM operations
- Storage management
- Cluster status monitoring
"""
import logging
import os
import sys
import signal
from typing import Optional, List, Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools import Tool
from mcp.types import TextContent as Content
from pydantic import Field, BaseModel

from .config.loader import load_config
from .core.logging import setup_logging
from .core.proxmox import ProxmoxManager
from .tools.node import NodeTools
from .tools.vm import VMTools
from .tools.storage import StorageTools
from .tools.cluster import ClusterTools
from .tools.containers import ContainerTools
from .tools.generic import GenericTools
from .tools.access import AccessTools
from .tools.firewall import FirewallTools
from .tools.pools import PoolTools
from .tools.backups import BackupTools
from .tools.admin import AdminTools
from .tools.ha import HATools
from .tools.replication import ReplicationTools
from .tools.sdn import SDNTools
from .tools.ceph import CephTools
from .tools.definitions import (
    GET_NODES_DESC,
    GET_NODE_STATUS_DESC,
    GET_VMS_DESC,
    CREATE_VM_DESC,
    EXECUTE_VM_COMMAND_DESC,
    START_VM_DESC,
    STOP_VM_DESC,
    SHUTDOWN_VM_DESC,
    RESET_VM_DESC,
    DELETE_VM_DESC,
    GET_CONTAINERS_DESC,
    START_CONTAINER_DESC,
    STOP_CONTAINER_DESC,
    RESTART_CONTAINER_DESC,
    GET_STORAGE_DESC,
    GET_CLUSTER_STATUS_DESC,
    # Added detailed descriptions
    GET_VM_STATUS_DESC,
    GET_VM_SNAPSHOTS_DESC,
    CREATE_VM_SNAPSHOT_DESC,
    DELETE_VM_SNAPSHOT_DESC,
    ROLLBACK_VM_SNAPSHOT_DESC,
    CLONE_VM_DESC,
    MIGRATE_VM_DESC,
    UPDATE_VM_CONFIG_DESC,
    RESIZE_VM_DISK_DESC,
    GET_CONTAINER_STATUS_DESC,
    CREATE_CONTAINER_DESC,
    UPDATE_CONTAINER_CONFIG_DESC,
    LIST_CONTAINER_SNAPSHOTS_DESC,
    CREATE_CONTAINER_SNAPSHOT_DESC,
    DELETE_CONTAINER_SNAPSHOT_DESC,
    ROLLBACK_CONTAINER_SNAPSHOT_DESC,
    GET_TASK_STATUS_DESC,
    GET_TASK_LOG_DESC,
    GET_CLUSTER_RESOURCES_DESC,
    GET_VERSION_DESC,
    LIST_USERS_DESC,
    CREATE_USER_DESC,
    UPDATE_USER_DESC,
    DELETE_USER_DESC,
    LIST_GROUPS_DESC,
    CREATE_GROUP_DESC,
    DELETE_GROUP_DESC,
    LIST_ROLES_DESC,
    CREATE_ROLE_DESC,
    DELETE_ROLE_DESC,
    GET_ACL_DESC,
    SET_ACL_DESC,
    LIST_DC_FW_RULES_DESC,
    ADD_DC_FW_RULE_DESC,
    DELETE_DC_FW_RULE_DESC,
    LIST_POOLS_DESC,
    CREATE_POOL_DESC,
    DELETE_POOL_DESC,
    VZDUMP_DESC,
    LIST_SERVICES_DESC,
    SERVICE_ACTION_DESC,
    NETWORK_GET_DESC,
    NETWORK_APPLY_DESC,
    LIST_UPDATES_DESC,
    LIST_REPOS_DESC,
    GET_CERTS_DESC,
    LIST_DISKS_DESC,
    HA_LIST_GROUPS_DESC,
    HA_CREATE_GROUP_DESC,
    HA_LIST_RESOURCES_DESC,
    HA_ADD_RESOURCE_DESC,
    HA_DELETE_RESOURCE_DESC,
    REPL_LIST_JOBS_DESC,
    REPL_CREATE_JOB_DESC,
    REPL_DELETE_JOB_DESC,
    SDN_LIST_ZONES_DESC,
    SDN_LIST_VNETS_DESC,
    CEPH_STATUS_DESC,
    CEPH_DF_DESC,
    DELETE_STORAGE_CONTENT_DESC,
    UPLOAD_STORAGE_CONTENT_DESC,
    VM_VNCPROXY_DESC,
    VM_SPICEPROXY_DESC,
    VM_MOVE_DISK_DESC,
    VM_IMPORT_DISK_DESC,
    VM_ATTACH_DISK_DESC,
    VM_DETACH_DISK_DESC,
    PROXMOX_REQUEST_DESC,
)

class ProxmoxMCPServer:
    """Main server class for Proxmox MCP."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the server.

        Args:
            config_path: Path to configuration file
        """
        self.config = load_config(config_path)
        self.logger = setup_logging(self.config.logging)
        
        # Initialize core components
        self.proxmox_manager = ProxmoxManager(self.config.proxmox, self.config.auth)
        self.proxmox = self.proxmox_manager.get_api()
        
        # Initialize tools
        self.node_tools = NodeTools(self.proxmox)
        self.vm_tools = VMTools(self.proxmox)
        self.storage_tools = StorageTools(self.proxmox)
        self.cluster_tools = ClusterTools(self.proxmox)
        self.container_tools = ContainerTools(self.proxmox)
        self.generic_tools = GenericTools(self.proxmox)
        self.access_tools = AccessTools(self.proxmox)
        self.firewall_tools = FirewallTools(self.proxmox)
        self.pool_tools = PoolTools(self.proxmox)
        self.backup_tools = BackupTools(self.proxmox)
        self.admin_tools = AdminTools(self.proxmox)
        self.ha_tools = HATools(self.proxmox)
        self.repl_tools = ReplicationTools(self.proxmox)
        self.sdn_tools = SDNTools(self.proxmox)
        self.ceph_tools = CephTools(self.proxmox)

        
        # Initialize MCP server
        self.mcp = FastMCP("ProxmoxMCP")
        self._setup_tools()

    def _setup_tools(self) -> None:
        """Register MCP tools with the server.
        
        Initializes and registers all available tools with the MCP server:
        - Node management tools (list nodes, get status)
        - VM operation tools (list VMs, execute commands, power management)
        - Storage management tools (list storage)
        - Cluster tools (get cluster status)
        
        Each tool is registered with appropriate descriptions and parameter
        validation using Pydantic models.
        """
        
        # Node tools
        @self.mcp.tool(description=GET_NODES_DESC)
        def get_nodes():
            return self.node_tools.get_nodes()

        @self.mcp.tool(description=GET_NODE_STATUS_DESC)
        def get_node_status(
            node: Annotated[str, Field(description="Name/ID of node to query (e.g. 'pve1', 'proxmox-node2')")]
        ):
            return self.node_tools.get_node_status(node)

        # Tasks (node-level)
        @self.mcp.tool(description=GET_TASK_STATUS_DESC)
        def get_task_status(
            node: Annotated[str, Field(description="Node name")],
            upid: Annotated[str, Field(description="Task UPID")]
        ):
            return self.node_tools.get_task_status(node, upid)

        @self.mcp.tool(description=GET_TASK_LOG_DESC)
        def get_task_log(
            node: Annotated[str, Field(description="Node name")],
            upid: Annotated[str, Field(description="Task UPID")]
        ):
            return self.node_tools.get_task_log(node, upid)

        # VM tools
        @self.mcp.tool(description=GET_VMS_DESC)
        def get_vms():
            return self.vm_tools.get_vms()

        # Phase 1: Additional VM read-only endpoints
        @self.mcp.tool(description=GET_VM_STATUS_DESC)
        def get_vm_status(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
            vmid: Annotated[str, Field(description="VM ID number (e.g. '100')")]
        ):
            return self.vm_tools.get_vm_status(node, vmid)

        @self.mcp.tool(description=GET_VM_SNAPSHOTS_DESC)
        def get_vm_snapshots(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
            vmid: Annotated[str, Field(description="VM ID number (e.g. '100')")]
        ):
            return self.vm_tools.get_vm_snapshots(node, vmid)

        @self.mcp.tool(description=CREATE_VM_DESC)
        def create_vm(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
            vmid: Annotated[str, Field(description="New VM ID number (e.g. '200', '300')")],
            name: Annotated[str, Field(description="VM name (e.g. 'my-new-vm', 'web-server')")],
            cpus: Annotated[int, Field(description="Number of CPU cores (e.g. 1, 2, 4)", ge=1, le=32)],
            memory: Annotated[int, Field(description="Memory size in MB (e.g. 2048 for 2GB)", ge=512, le=131072)],
            disk_size: Annotated[int, Field(description="Disk size in GB (e.g. 10, 20, 50)", ge=5, le=1000)],
            storage: Annotated[Optional[str], Field(description="Storage name (optional, will auto-detect)", default=None)] = None,
            ostype: Annotated[Optional[str], Field(description="OS type (optional, default: 'l26' for Linux)", default=None)] = None
        ):
            return self.vm_tools.create_vm(node, vmid, name, cpus, memory, disk_size, storage, ostype)

        @self.mcp.tool(description=EXECUTE_VM_COMMAND_DESC)
        async def execute_vm_command(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve1', 'proxmox-node2')")],
            vmid: Annotated[str, Field(description="VM ID number (e.g. '100', '101')")],
            command: Annotated[str, Field(description="Shell command to run (e.g. 'uname -a', 'systemctl status nginx')")]
        ):
            return await self.vm_tools.execute_command(node, vmid, command)

        # VM Power Management tools
        @self.mcp.tool(description=START_VM_DESC)
        def start_vm(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
            vmid: Annotated[str, Field(description="VM ID number (e.g. '101')")]
        ):
            return self.vm_tools.start_vm(node, vmid)

        @self.mcp.tool(description=STOP_VM_DESC)
        def stop_vm(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
            vmid: Annotated[str, Field(description="VM ID number (e.g. '101')")]
        ):
            return self.vm_tools.stop_vm(node, vmid)

        @self.mcp.tool(description=SHUTDOWN_VM_DESC)
        def shutdown_vm(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
            vmid: Annotated[str, Field(description="VM ID number (e.g. '101')")]
        ):
            return self.vm_tools.shutdown_vm(node, vmid)

        @self.mcp.tool(description=RESET_VM_DESC)
        def reset_vm(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
            vmid: Annotated[str, Field(description="VM ID number (e.g. '101')")]
        ):
            return self.vm_tools.reset_vm(node, vmid)

        @self.mcp.tool(description=DELETE_VM_DESC)
        def delete_vm(
            node: Annotated[str, Field(description="Host node name (e.g. 'pve')")],
            vmid: Annotated[str, Field(description="VM ID number (e.g. '998')")],
            force: Annotated[bool, Field(description="Force deletion even if VM is running", default=False)] = False
        ):
            return self.vm_tools.delete_vm(node, vmid, force)

        # VM snapshots / clone / migrate / config / resize
        @self.mcp.tool(description=CREATE_VM_SNAPSHOT_DESC)
        def create_vm_snapshot(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[str, Field(description="VM ID")],
            snapname: Annotated[str, Field(description="Snapshot name")],
            vmstate: Annotated[Optional[bool], Field(description="Include RAM state", default=None)] = None,
            description: Annotated[Optional[str], Field(description="Snapshot description", default=None)] = None,
        ):
            return self.vm_tools.create_vm_snapshot(node, vmid, snapname, vmstate, description)

        @self.mcp.tool(description=DELETE_VM_SNAPSHOT_DESC)
        def delete_vm_snapshot(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[str, Field(description="VM ID")],
            snapname: Annotated[str, Field(description="Snapshot name")]
        ):
            return self.vm_tools.delete_vm_snapshot(node, vmid, snapname)

        @self.mcp.tool(description=ROLLBACK_VM_SNAPSHOT_DESC)
        def rollback_vm_snapshot(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[str, Field(description="VM ID")],
            snapname: Annotated[str, Field(description="Snapshot name")]
        ):
            return self.vm_tools.rollback_vm_snapshot(node, vmid, snapname)

        @self.mcp.tool(description=CLONE_VM_DESC)
        def clone_vm(
            node: Annotated[str, Field(description="Source node")],
            vmid: Annotated[str, Field(description="Source VM ID")],
            target: Annotated[Optional[str], Field(description="Target node", default=None)] = None,
            newid: Annotated[Optional[str], Field(description="New VM ID", default=None)] = None,
            name: Annotated[Optional[str], Field(description="New VM name", default=None)] = None,
            full: Annotated[Optional[bool], Field(description="Full clone", default=None)] = None,
            storage: Annotated[Optional[str], Field(description="Target storage", default=None)] = None,
        ):
            return self.vm_tools.clone_vm(node, vmid, target, newid, name, full, storage)

        @self.mcp.tool(description=MIGRATE_VM_DESC)
        def migrate_vm(
            node: Annotated[str, Field(description="Source node")],
            vmid: Annotated[str, Field(description="VM ID")],
            target: Annotated[str, Field(description="Target node")],
            online: Annotated[Optional[bool], Field(description="Online migration", default=None)] = None,
        ):
            return self.vm_tools.migrate_vm(node, vmid, target, online)

        @self.mcp.tool(description=UPDATE_VM_CONFIG_DESC)
        def update_vm_config(
            node: Annotated[str, Field(description="Node")],
            vmid: Annotated[str, Field(description="VM ID")],
            changes: Annotated[dict, Field(description="Config changes")]
        ):
            return self.vm_tools.update_vm_config(node, vmid, changes)

        @self.mcp.tool(description=RESIZE_VM_DISK_DESC)
        def resize_vm_disk(
            node: Annotated[str, Field(description="Node")],
            vmid: Annotated[str, Field(description="VM ID")],
            disk: Annotated[str, Field(description="Disk name (e.g. 'scsi0')")],
            size: Annotated[str, Field(description="Resize (e.g. '+10G')")]
        ):
            return self.vm_tools.resize_vm_disk(node, vmid, disk, size)

        # VM console proxies
        @self.mcp.tool(description=VM_VNCPROXY_DESC)
        def vm_vncproxy(
            node: Annotated[str, Field(description="Node")],
            vmid: Annotated[str, Field(description="VM ID")]
        ):
            return self.vm_tools.vncproxy(node, vmid)

        @self.mcp.tool(description=VM_SPICEPROXY_DESC)
        def vm_spiceproxy(
            node: Annotated[str, Field(description="Node")],
            vmid: Annotated[str, Field(description="VM ID")]
        ):
            return self.vm_tools.spiceproxy(node, vmid)

        # VM disk ops
        @self.mcp.tool(description=VM_MOVE_DISK_DESC)
        def vm_move_disk(
            node: Annotated[str, Field(description="Node")],
            vmid: Annotated[str, Field(description="VM ID")],
            disk: Annotated[str, Field(description="Disk (e.g. 'scsi0')")],
            storage: Annotated[str, Field(description="Target storage")]
        ):
            return self.vm_tools.move_disk(node, vmid, disk, storage)

        @self.mcp.tool(description=VM_IMPORT_DISK_DESC)
        def vm_import_disk(
            node: Annotated[str, Field(description="Node")],
            vmid: Annotated[str, Field(description="VM ID")],
            source: Annotated[str, Field(description="Source path")],
            storage: Annotated[str, Field(description="Target storage")]
        ):
            return self.vm_tools.import_disk(node, vmid, source, storage)

        @self.mcp.tool(description=VM_ATTACH_DISK_DESC)
        def vm_attach_disk(
            node: Annotated[str, Field(description="Node")],
            vmid: Annotated[str, Field(description="VM ID")],
            disk: Annotated[str, Field(description="Slot (e.g. 'scsi1')")],
            opts: Annotated[dict, Field(description="Disk options (e.g., 'local-lvm:10,format=raw')")]
        ):
            return self.vm_tools.attach_disk(node, vmid, disk, opts)

        @self.mcp.tool(description=VM_DETACH_DISK_DESC)
        def vm_detach_disk(
            node: Annotated[str, Field(description="Node")],
            vmid: Annotated[str, Field(description="VM ID")],
            disk: Annotated[str, Field(description="Slot (e.g. 'scsi1')")]
        ):
            return self.vm_tools.detach_disk(node, vmid, disk)

        # Storage tools
        @self.mcp.tool(description=GET_STORAGE_DESC)
        def get_storage():
            return self.storage_tools.get_storage()

        # Phase 1: Storage content
        @self.mcp.tool(description=GET_STORAGE_DESC)
        def get_storage_content(
            node: Annotated[str, Field(description="Host node name")],
            storage: Annotated[str, Field(description="Storage ID (e.g. 'local', 'local-lvm')")]
        ):
            return self.storage_tools.get_storage_content(node, storage)

        # Cluster tools
        @self.mcp.tool(description=GET_CLUSTER_STATUS_DESC)
        def get_cluster_status():
            return self.cluster_tools.get_cluster_status()

        # Phase 1: Cluster resources
        @self.mcp.tool(description=GET_CLUSTER_RESOURCES_DESC)
        def get_cluster_resources():
            return self.cluster_tools.get_cluster_resources()

        @self.mcp.tool(description=GET_VERSION_DESC)
        def get_version():
            return self.cluster_tools.get_version()

        # Access control wrappers
        @self.mcp.tool(description=LIST_USERS_DESC)
        def list_users():
            return self.access_tools.list_users()

        @self.mcp.tool(description=CREATE_USER_DESC)
        def create_user(
            user: Annotated[str, Field(description="userid, e.g. 'user@pve'")],
            password: Annotated[Optional[str], Field(description="password", default=None)] = None,
            comment: Annotated[Optional[str], Field(description="comment", default=None)] = None,
            expire: Annotated[Optional[int], Field(description="expiry epoch", default=None)] = None,
            enable: Annotated[Optional[bool], Field(description="enable user", default=True)] = True,
        ):
            return self.access_tools.create_user(user, password, comment, expire, enable)

        @self.mcp.tool(description=UPDATE_USER_DESC)
        def update_user(user: Annotated[str, Field(description="userid")], changes: Annotated[dict, Field(description="changes")]):
            return self.access_tools.update_user(user, changes)

        @self.mcp.tool(description=DELETE_USER_DESC)
        def delete_user(user: Annotated[str, Field(description="userid")]):
            return self.access_tools.delete_user(user)

        @self.mcp.tool(description=LIST_GROUPS_DESC)
        def list_groups():
            return self.access_tools.list_groups()

        @self.mcp.tool(description=CREATE_GROUP_DESC)
        def create_group(groupid: Annotated[str, Field(description="group id")], comment: Annotated[Optional[str], Field(description="comment", default=None)] = None):
            return self.access_tools.create_group(groupid, comment)

        @self.mcp.tool(description=DELETE_GROUP_DESC)
        def delete_group(groupid: Annotated[str, Field(description="group id")]):
            return self.access_tools.delete_group(groupid)

        @self.mcp.tool(description=LIST_ROLES_DESC)
        def list_roles():
            return self.access_tools.list_roles()

        @self.mcp.tool(description=CREATE_ROLE_DESC)
        def create_role(roleid: Annotated[str, Field(description="role id")], privs: Annotated[str, Field(description="privilege string")]):
            return self.access_tools.create_role(roleid, privs)

        @self.mcp.tool(description=DELETE_ROLE_DESC)
        def delete_role(roleid: Annotated[str, Field(description="role id")]):
            return self.access_tools.delete_role(roleid)

        @self.mcp.tool(description=GET_ACL_DESC)
        def get_acl():
            return self.access_tools.get_acl()

        @self.mcp.tool(description=SET_ACL_DESC)
        def set_acl(
            path: Annotated[str, Field(description="ACL path, e.g. '/vms/100'")],
            roles: Annotated[Optional[str], Field(description="roles csv", default=None)] = None,
            users: Annotated[Optional[str], Field(description="users csv", default=None)] = None,
            groups: Annotated[Optional[str], Field(description="groups csv", default=None)] = None,
            propagate: Annotated[Optional[bool], Field(description="propagate flag", default=True)] = True,
            delete: Annotated[Optional[bool], Field(description="delete flag", default=None)] = None,
        ):
            return self.access_tools.set_acl(path, roles, users, groups, propagate, delete)

        # Datacenter firewall (subset)
        @self.mcp.tool(description=LIST_DC_FW_RULES_DESC)
        def list_dc_firewall_rules():
            return self.firewall_tools.list_dc_rules()

        @self.mcp.tool(description=ADD_DC_FW_RULE_DESC)
        def add_dc_firewall_rule(rule: Annotated[dict, Field(description="rule payload")]):
            return self.firewall_tools.add_dc_rule(rule)

        @self.mcp.tool(description=DELETE_DC_FW_RULE_DESC)
        def delete_dc_firewall_rule(pos: Annotated[int, Field(description="rule position")]):
            return self.firewall_tools.delete_dc_rule(pos)

        # Pools
        @self.mcp.tool(description=LIST_POOLS_DESC)
        def list_pools():
            return self.pool_tools.list_pools()

        @self.mcp.tool(description=CREATE_POOL_DESC)
        def create_pool(poolid: Annotated[str, Field(description="pool id")], comment: Annotated[Optional[str], Field(description="comment", default=None)] = None):
            return self.pool_tools.create_pool(poolid, comment)

        @self.mcp.tool(description=DELETE_POOL_DESC)
        def delete_pool(poolid: Annotated[str, Field(description="pool id")]):
            return self.pool_tools.delete_pool(poolid)

        # Backups (vzdump)
        @self.mcp.tool(description=VZDUMP_DESC)
        def vzdump(node: Annotated[str, Field(description="node")], params: Annotated[dict, Field(description="vzdump params")]):
            return self.backup_tools.vzdump(node, params)

        # Node admin
        @self.mcp.tool(description=LIST_SERVICES_DESC)
        def list_services(node: Annotated[str, Field(description="node")]):
            return self.admin_tools.list_services(node)

        @self.mcp.tool(description=SERVICE_ACTION_DESC)
        def service_action(
            node: Annotated[str, Field(description="node")],
            service: Annotated[str, Field(description="service name")],
            action: Annotated[str, Field(description="start|stop|restart")]
        ):
            return self.admin_tools.service_action(node, service, action)

        @self.mcp.tool(description=NETWORK_GET_DESC)
        def network_get(node: Annotated[str, Field(description="node")]):
            return self.admin_tools.network_get(node)

        @self.mcp.tool(description=NETWORK_APPLY_DESC)
        def network_apply(node: Annotated[str, Field(description="node")]):
            return self.admin_tools.network_apply(node)

        @self.mcp.tool(description=LIST_UPDATES_DESC)
        def list_updates(node: Annotated[str, Field(description="node")]):
            return self.admin_tools.list_updates(node)

        @self.mcp.tool(description=LIST_REPOS_DESC)
        def list_repositories(node: Annotated[str, Field(description="node")]):
            return self.admin_tools.list_repositories(node)

        @self.mcp.tool(description=GET_CERTS_DESC)
        def get_certificates(node: Annotated[str, Field(description="node")]):
            return self.admin_tools.get_certificates(node)

        @self.mcp.tool(description=LIST_DISKS_DESC)
        def list_disks(node: Annotated[str, Field(description="node")]):
            return self.admin_tools.list_disks(node)

        # HA wrappers
        @self.mcp.tool(description=HA_LIST_GROUPS_DESC)
        def ha_list_groups():
            return self.ha_tools.list_groups()

        @self.mcp.tool(description=HA_CREATE_GROUP_DESC)
        def ha_create_group(group: Annotated[str, Field(description="group id")], nodes: Annotated[str, Field(description="nodes csv")], comment: Annotated[Optional[str], Field(description="comment", default=None)] = None):
            return self.ha_tools.create_group(group, nodes, comment)

        @self.mcp.tool(description=HA_LIST_RESOURCES_DESC)
        def ha_list_resources():
            return self.ha_tools.list_resources()

        @self.mcp.tool(description=HA_ADD_RESOURCE_DESC)
        def ha_add_resource(sid: Annotated[str, Field(description="service id (e.g. 'vm:100')")], group: Annotated[str, Field(description="group")]):
            return self.ha_tools.add_resource(sid, group)

        @self.mcp.tool(description=HA_DELETE_RESOURCE_DESC)
        def ha_delete_resource(sid: Annotated[str, Field(description="service id")]):
            return self.ha_tools.delete_resource(sid)

        # Replication wrappers
        @self.mcp.tool(description=REPL_LIST_JOBS_DESC)
        def replication_list_jobs():
            return self.repl_tools.list_jobs()

        @self.mcp.tool(description=REPL_CREATE_JOB_DESC)
        def replication_create_job(job: Annotated[dict, Field(description="job payload")]):
            return self.repl_tools.create_job(job)

        @self.mcp.tool(description=REPL_DELETE_JOB_DESC)
        def replication_delete_job(jobid: Annotated[str, Field(description="job id")]):
            return self.repl_tools.delete_job(jobid)

        # SDN wrappers
        @self.mcp.tool(description=SDN_LIST_ZONES_DESC)
        def sdn_list_zones():
            return self.sdn_tools.list_zones()

        @self.mcp.tool(description=SDN_LIST_VNETS_DESC)
        def sdn_list_vnets():
            return self.sdn_tools.list_vnets()

        # Ceph wrappers
        @self.mcp.tool(description=CEPH_STATUS_DESC)
        def ceph_status(node: Annotated[str, Field(description="node")]):
            return self.ceph_tools.status(node)

        @self.mcp.tool(description=CEPH_DF_DESC)
        def ceph_df(node: Annotated[str, Field(description="node")]):
            return self.ceph_tools.df(node)

        # Storage content ops
        @self.mcp.tool(description=DELETE_STORAGE_CONTENT_DESC)
        def delete_storage_content(
            node: Annotated[str, Field(description="node")],
            storage: Annotated[str, Field(description="storage id")],
            volume: Annotated[str, Field(description="volume id")]
        ):
            return self.storage_tools.delete_storage_content(node, storage, volume)

        @self.mcp.tool(description=UPLOAD_STORAGE_CONTENT_DESC)
        def upload_storage_content(
            node: Annotated[str, Field(description="node")],
            storage: Annotated[str, Field(description="storage id")],
            content: Annotated[str, Field(description="content type: iso|vztmpl|backup")],
            file_path: Annotated[str, Field(description="local file path")],
            filename: Annotated[str, Field(description="target filename")]
        ):
            return self.storage_tools.upload_storage_content(node, storage, content, file_path, filename)

        # Containers (LXC)
        @self.mcp.tool(description=GET_CONTAINERS_DESC)
        def get_containers():
            return self.container_tools.get_containers(format_style="json")

        # Phase 1: Container read-only
        @self.mcp.tool(description=GET_CONTAINER_STATUS_DESC)
        def get_container_status(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[str, Field(description="Container ID")]
        ):
            return self.container_tools.get_container_status(node, vmid)

        # LXC create/config/snapshots
        @self.mcp.tool(description=CREATE_CONTAINER_DESC)
        def create_container(
            node: Annotated[str, Field(description="Host node name")],
            config: Annotated[dict, Field(description="Container create parameters")]
        ):
            return self.container_tools.create_container(node, config)

        @self.mcp.tool(description=UPDATE_CONTAINER_CONFIG_DESC)
        def update_container_config(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[int, Field(description="Container ID")],
            changes: Annotated[dict, Field(description="Config changes")]
        ):
            return self.container_tools.update_container_config(node, vmid, changes)

        @self.mcp.tool(description=LIST_CONTAINER_SNAPSHOTS_DESC)
        def list_container_snapshots(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[int, Field(description="Container ID")]
        ):
            return self.container_tools.list_container_snapshots(node, vmid)

        @self.mcp.tool(description=CREATE_CONTAINER_SNAPSHOT_DESC)
        def create_container_snapshot(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[int, Field(description="Container ID")],
            snapname: Annotated[str, Field(description="Snapshot name")]
        ):
            return self.container_tools.create_container_snapshot(node, vmid, snapname)

        @self.mcp.tool(description=DELETE_CONTAINER_SNAPSHOT_DESC)
        def delete_container_snapshot(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[int, Field(description="Container ID")],
            snapname: Annotated[str, Field(description="Snapshot name")]
        ):
            return self.container_tools.delete_container_snapshot(node, vmid, snapname)

        @self.mcp.tool(description=ROLLBACK_CONTAINER_SNAPSHOT_DESC)
        def rollback_container_snapshot(
            node: Annotated[str, Field(description="Host node name")],
            vmid: Annotated[int, Field(description="Container ID")],
            snapname: Annotated[str, Field(description="Snapshot name")]
        ):
            return self.container_tools.rollback_container_snapshot(node, vmid, snapname)

        # Container controls
        @self.mcp.tool(description=START_CONTAINER_DESC)
        def start_container(
            selector: Annotated[str, Field(description="CT selector: '123' | 'pve1:123' | 'pve1/name' | 'name' | comma list")],
            format_style: Annotated[str, Field(description="'pretty' or 'json'", pattern="^(pretty|json)$")] = "pretty",
        ):
            return self.container_tools.start_container(selector=selector, format_style=format_style)

        @self.mcp.tool(description=STOP_CONTAINER_DESC)
        def stop_container(
            selector: Annotated[str, Field(description="CT selector (see start_container)")],
            graceful: Annotated[bool, Field(description="Graceful shutdown (True) or forced stop (False)", default=True)] = True,
            timeout_seconds: Annotated[int, Field(description="Timeout for stop/shutdown", ge=1, le=600)] = 10,
            format_style: Annotated[Literal["pretty","json"], Field(description="Output format")] = "pretty",
        ):
            return self.container_tools.stop_container(
               selector=selector, graceful=graceful, timeout_seconds=timeout_seconds, format_style=format_style
            )
        @self.mcp.tool(description=RESTART_CONTAINER_DESC)
        def restart_container(
            selector: Annotated[str, Field(description="CT selector (see start_container)")],
            timeout_seconds: Annotated[int, Field(description="Timeout for reboot", ge=1, le=600)] = 10,
            format_style: Annotated[str, Field(description="'pretty' or 'json'", pattern="^(pretty|json)$")] = "pretty",
        ):
            return self.container_tools.restart_container(
               selector=selector, timeout_seconds=timeout_seconds, format_style=format_style
            )

        # Generic Proxmox proxy (Phase 2)
        class ProxmoxRequest(BaseModel):
            method: Literal["GET", "POST", "PUT", "DELETE"]
            path: str
            params: Optional[dict] = None
            data: Optional[dict] = None

        @self.mcp.tool(description=PROXMOX_REQUEST_DESC)
        def proxmox_request(payload: ProxmoxRequest):
            return self.generic_tools.proxmox_request(
                method=payload.method,
                path=payload.path,
                params=payload.params,
                data=payload.data,
            )


    def start(self) -> None:
        """Start the MCP server.
        
        Initializes the server with:
        - Signal handlers for graceful shutdown (SIGINT, SIGTERM)
        - Async runtime for handling concurrent requests
        - Error handling and logging
        
        The server runs until terminated by a signal or fatal error.
        """
        import anyio

        def signal_handler(signum, frame):
            self.logger.info("Received signal to shutdown...")
            sys.exit(0)

        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            self.logger.info("Starting MCP server...")
            anyio.run(self.mcp.run_stdio_async)
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            sys.exit(1)

def main() -> None:
    config_path = os.getenv("PROXMOX_MCP_CONFIG")

    try:
        # If config_path is None, loader will fall back to environment variables
        server = ProxmoxMCPServer(config_path)
        server.start()
    except KeyboardInterrupt:
        # Never write to stdout, MCP uses stdout for JSON-RPC
        print("\nShutting down gracefully...", file=sys.stderr, flush=True)
        sys.exit(0)
    except Exception as e:
        # Helpful guidance for missing config
        msg = (
            "Error: No config file set. Either set PROXMOX_MCP_CONFIG to a JSON config path, "
            "or set env vars PROXMOX_HOST, PROXMOX_USER, PROXMOX_TOKEN_NAME, PROXMOX_TOKEN_VALUE."
            if "PROXMOX_MCP_CONFIG" in str(e)
            else f"Error: {e}"
        )
        # Never write to stdout, MCP uses stdout for JSON-RPC
        print(msg, file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
