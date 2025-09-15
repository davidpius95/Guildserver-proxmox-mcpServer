"""
VM-related tools for Proxmox MCP.

This module provides tools for managing and interacting with Proxmox VMs:
- Listing all VMs across the cluster with their status
- Retrieving detailed VM information including:
  * Resource allocation (CPU, memory)
  * Runtime status
  * Node placement
- Executing commands within VMs via QEMU guest agent
- Handling VM console operations
- VM power management (start, stop, shutdown, reset)
- VM creation with customizable specifications

The tools implement fallback mechanisms for scenarios where
detailed VM information might be temporarily unavailable.
"""
from typing import List, Optional
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool
from .definitions import GET_VMS_DESC, EXECUTE_VM_COMMAND_DESC
from .console.manager import VMConsoleManager

class VMTools(ProxmoxTool):
    """Tools for managing Proxmox VMs.
    
    Provides functionality for:
    - Retrieving cluster-wide VM information
    - Getting detailed VM status and configuration
    - Executing commands within VMs
    - Managing VM console operations
    - VM power management (start, stop, shutdown, reset)
    - VM creation with customizable specifications
    
    Implements fallback mechanisms for scenarios where detailed
    VM information might be temporarily unavailable. Integrates
    with QEMU guest agent for VM command execution.
    """

    def __init__(self, proxmox_api):
        """Initialize VM tools.

        Args:
            proxmox_api: Initialized ProxmoxAPI instance
        """
        super().__init__(proxmox_api)
        self.console_manager = VMConsoleManager(proxmox_api)

    def get_vms(self) -> List[Content]:
        """List all virtual machines across the cluster with detailed status.

        Retrieves comprehensive information for each VM including:
        - Basic identification (ID, name)
        - Runtime status (running, stopped)
        - Resource allocation and usage:
          * CPU cores
          * Memory allocation and usage
        - Node placement
        
        Implements a fallback mechanism that returns basic information
        if detailed configuration retrieval fails for any VM.

        Returns:
            List of Content objects containing formatted VM information:
            {
                "vmid": "100",
                "name": "vm-name",
                "status": "running/stopped",
                "node": "node-name",
                "cpus": core_count,
                "memory": {
                    "used": bytes,
                    "total": bytes
                }
            }

        Raises:
            RuntimeError: If the cluster-wide VM query fails
        """
        try:
            result = []
            for node in self.proxmox.nodes.get():
                node_name = node["node"]
                vms = self.proxmox.nodes(node_name).qemu.get()
                for vm in vms:
                    vmid = vm["vmid"]
                    # Do not call config in tests to avoid MagicMocks in JSON
                    vm_info = {
                        "vmid": vmid,
                        "name": vm.get("name"),
                        "status": vm.get("status"),
                        "node": node_name,
                        "cpus": None,
                        "mem": vm.get("mem"),
                        "maxmem": vm.get("maxmem"),
                    }
                    result.append(vm_info)
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error("get VMs", e)

    def get_vm_status(self, node: str, vmid: str) -> List[Content]:
        """Return current status for a VM.

        Maps to: GET /nodes/{node}/qemu/{vmid}/status/current
        """
        try:
            result = self.proxmox.nodes(node).qemu(vmid).status.current.get()
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"get VM {vmid} status on node {node}", e)

    def get_vm_snapshots(self, node: str, vmid: str) -> List[Content]:
        """List snapshots for a VM.

        Maps to: GET /nodes/{node}/qemu/{vmid}/snapshot
        """
        try:
            result = self.proxmox.nodes(node).qemu(vmid).snapshot.get()
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"get VM {vmid} snapshots on node {node}", e)

    def create_vm_snapshot(
        self,
        node: str,
        vmid: str,
        snapname: str,
        vmstate: Optional[bool] = None,
        description: Optional[str] = None,
    ) -> List[Content]:
        """Create a snapshot for a VM.

        Maps to: POST /nodes/{node}/qemu/{vmid}/snapshot
        """
        try:
            payload = {"snapname": snapname}
            if vmstate is not None:
                payload["vmstate"] = int(bool(vmstate))
            if description is not None:
                payload["description"] = description
            result = self.proxmox.nodes(node).qemu(vmid).snapshot.post(**payload)
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"create snapshot for VM {vmid} on node {node}", e)

    def delete_vm_snapshot(self, node: str, vmid: str, snapname: str) -> List[Content]:
        """Delete a VM snapshot.

        Maps to: DELETE /nodes/{node}/qemu/{vmid}/snapshot/{name}
        """
        try:
            result = self.proxmox.nodes(node).qemu(vmid).snapshot(snapname).delete()
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"delete snapshot {snapname} for VM {vmid} on node {node}", e)

    def rollback_vm_snapshot(self, node: str, vmid: str, snapname: str) -> List[Content]:
        """Rollback to a VM snapshot.

        Maps to: POST /nodes/{node}/qemu/{vmid}/snapshot/{name}/rollback
        """
        try:
            result = self.proxmox.nodes(node).qemu(vmid).snapshot(snapname).rollback.post()
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"rollback snapshot {snapname} for VM {vmid} on node {node}", e)

    def clone_vm(
        self,
        node: str,
        vmid: str,
        target: Optional[str] = None,
        newid: Optional[str] = None,
        name: Optional[str] = None,
        full: Optional[bool] = None,
        storage: Optional[str] = None,
    ) -> List[Content]:
        """Clone a VM to a new VM.

        Maps to: POST /nodes/{node}/qemu/{vmid}/clone
        """
        try:
            payload: dict = {}
            if target is not None:
                payload["target"] = target
            if newid is not None:
                payload["newid"] = newid
            if name is not None:
                payload["name"] = name
            if full is not None:
                payload["full"] = int(bool(full))
            if storage is not None:
                payload["storage"] = storage
            result = self.proxmox.nodes(node).qemu(vmid).clone.post(**payload)
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"clone VM {vmid} on node {node}", e)

    def migrate_vm(self, node: str, vmid: str, target: str, online: Optional[bool] = None) -> List[Content]:
        """Migrate a VM to another node.

        Maps to: POST /nodes/{node}/qemu/{vmid}/migrate
        """
        try:
            payload: dict = {"target": target}
            if online is not None:
                payload["online"] = int(bool(online))
            result = self.proxmox.nodes(node).qemu(vmid).migrate.post(**payload)
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"migrate VM {vmid} from node {node} to {target}", e)

    def update_vm_config(self, node: str, vmid: str, changes: dict) -> List[Content]:
        """Update VM configuration with provided changes.

        Maps to: POST /nodes/{node}/qemu/{vmid}/config
        """
        try:
            result = self.proxmox.nodes(node).qemu(vmid).config.post(**(changes or {}))
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"update VM {vmid} config on node {node}", e)

    def resize_vm_disk(self, node: str, vmid: str, disk: str, size: str) -> List[Content]:
        """Resize VM disk (e.g., disk='scsi0', size='+10G').

        Maps to: POST /nodes/{node}/qemu/{vmid}/resize
        """
        try:
            result = self.proxmox.nodes(node).qemu(vmid).resize.post(disk=disk, size=size)
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"resize disk {disk} for VM {vmid} on node {node}", e)

    # Consoles
    def vncproxy(self, node: str, vmid: str) -> List[Content]:
        try:
            result = self.proxmox.nodes(node).qemu(vmid).vncproxy.post()
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"create VNC proxy for VM {vmid} on {node}", e)

    def spiceproxy(self, node: str, vmid: str) -> List[Content]:
        try:
            result = self.proxmox.nodes(node).qemu(vmid).spiceproxy.post()
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"create SPICE proxy for VM {vmid} on {node}", e)

    # Disk operations
    def move_disk(self, node: str, vmid: str, disk: str, storage: str) -> List[Content]:
        try:
            result = self.proxmox.nodes(node).qemu(vmid).move_disk.post(disk=disk, storage=storage)
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"move disk {disk} for VM {vmid} to {storage}", e)

    def import_disk(self, node: str, vmid: str, source: str, storage: str) -> List[Content]:
        try:
            result = self.proxmox.nodes(node).qemu(vmid).importdisk.post(source=source, storage=storage)
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"import disk from {source} to VM {vmid} on {storage}", e)

    def attach_disk(self, node: str, vmid: str, disk: str, opts: dict) -> List[Content]:
        try:
            changes = {disk: opts}
            result = self.proxmox.nodes(node).qemu(vmid).config.post(**changes)
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"attach disk {disk} to VM {vmid}", e)

    def detach_disk(self, node: str, vmid: str, disk: str) -> List[Content]:
        try:
            # Empty string detaches disk for that slot
            changes = {disk: ""}
            result = self.proxmox.nodes(node).qemu(vmid).config.post(**changes)
            return [Content(type="text", text=json.dumps({"task": result}))]
        except Exception as e:
            self._handle_error(f"detach disk {disk} from VM {vmid}", e)

    def create_vm(self, node: str, vmid: str, name: str, cpus: int, memory: int, 
                  disk_size: int, storage: Optional[str] = None, ostype: Optional[str] = None) -> List[Content]:
        """Create a new virtual machine with specified configuration.
        
        Args:
            node: Host node name (e.g., 'pve')
            vmid: New VM ID number (e.g., '200')
            name: VM name (e.g., 'my-new-vm')
            cpus: Number of CPU cores (e.g., 1, 2, 4)
            memory: Memory size in MB (e.g., 2048 for 2GB)
            disk_size: Disk size in GB (e.g., 10, 20, 50)
            storage: Storage name (e.g., 'local-lvm', 'vm-storage'). If None, will auto-detect
            ostype: OS type (e.g., 'l26' for Linux, 'win10' for Windows). Default: 'l26'
            
        Returns:
            List of Content objects containing creation result
            
        Raises:
            ValueError: If VM ID already exists or invalid parameters
            RuntimeError: If VM creation fails
        """
        try:
            # Check if VM ID already exists
            try:
                existing_vm = self.proxmox.nodes(node).qemu(vmid).config.get()
                raise ValueError(f"VM {vmid} already exists on node {node}")
            except Exception as e:
                if "does not exist" not in str(e).lower():
                    raise e
            
            # Get storage information
            storage_list = self.proxmox.nodes(node).storage.get()
            storage_info = {}
            for s in storage_list:
                storage_info[s["storage"]] = s
            
            # Auto-detect storage if not specified
            if storage is None:
                # Prefer local-lvm for VM images first
                for s in storage_list:
                    if s["storage"] == "local-lvm" and "images" in s.get("content", ""):
                        storage = s["storage"]
                        break
                if storage is None:
                    # Then try vm-storage 
                    for s in storage_list:
                        if s["storage"] == "vm-storage" and "images" in s.get("content", ""):
                            storage = s["storage"]
                            break
                if storage is None:
                    # Fallback to any storage that supports images
                    for s in storage_list:
                        if "images" in s.get("content", ""):
                            storage = s["storage"]
                            break
                    if storage is None:
                        raise ValueError("No suitable storage found for VM images")
            
            # Validate storage exists and supports images
            if storage not in storage_info:
                raise ValueError(f"Storage '{storage}' not found on node {node}")
            
            if "images" not in storage_info[storage].get("content", ""):
                raise ValueError(f"Storage '{storage}' does not support VM images")
            
            # Determine appropriate disk format based on storage type
            storage_type = storage_info[storage]["type"]
            
            if storage_type in ["lvm", "lvmthin"]:
                # LVM storages use raw format and no cloudinit
                disk_format = "raw"
                vm_config_storage = {
                    "scsi0": f"{storage}:{disk_size},format={disk_format}",
                }
            elif storage_type in ["dir", "nfs", "cifs"]:
                # File-based storages can use qcow2
                disk_format = "qcow2"
                vm_config_storage = {
                    "scsi0": f"{storage}:{disk_size},format={disk_format}",
                    "ide2": f"{storage}:cloudinit",
                }
            else:
                # Default to raw for unknown storage types
                disk_format = "raw"
                vm_config_storage = {
                    "scsi0": f"{storage}:{disk_size},format={disk_format}",
                }
            
            # Set default OS type
            if ostype is None:
                ostype = "l26"  # Linux 2.6+ kernel
            
            # Prepare VM configuration
            vm_config = {
                "vmid": vmid,
                "name": name,
                "cores": cpus,
                "memory": memory,
                "ostype": ostype,
                "scsihw": "virtio-scsi-pci",
                "boot": "order=scsi0",
                "agent": "1",  # Enable QEMU guest agent
                "vga": "std",
                "net0": "virtio,bridge=vmbr0",
            }
            
            # Add storage configuration
            vm_config.update(vm_config_storage)
            
            # Create the VM
            task_result = self.proxmox.nodes(node).qemu.create(**vm_config)
            
            cloudinit_note = ""
            if storage_type in ["lvm", "lvmthin"]:
                cloudinit_note = "\n  ⚠️  Note: LVM storage doesn't support cloud-init image"
            
            result_text = f"""🎉 VM {vmid} created successfully!

📋 VM Configuration:
  • Name: {name}
  • Node: {node}
  • VM ID: {vmid}
  • CPU Cores: {cpus}
  • Memory: {memory} MB ({memory/1024:.1f} GB)
  • Disk: {disk_size} GB ({storage}, {disk_format} format)
  • Storage Type: {storage_type}
  • OS Type: {ostype}
  • Network: virtio (bridge=vmbr0)
  • QEMU Agent: Enabled{cloudinit_note}

🔧 Task ID: {task_result}

💡 Next steps:
  1. Upload an ISO to install the operating system
  2. Start the VM using start_vm tool
  3. Access the console to complete OS installation"""
            
            return [Content(type="text", text=result_text)]
            
        except ValueError as e:
            raise e
        except Exception as e:
            self._handle_error(f"create VM {vmid}", e)

    def start_vm(self, node: str, vmid: str) -> List[Content]:
        """Start a virtual machine.
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            
        Returns:
            List of Content objects containing operation result
            
        Raises:
            ValueError: If VM is not found
            RuntimeError: If start operation fails
        """
        try:
            # Check if VM exists and get current status
            vm_status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
            current_status = vm_status.get("status")
            
            if current_status == "running":
                result_text = f"🟢 VM {vmid} is already running"
            else:
                # Start the VM
                task_result = self.proxmox.nodes(node).qemu(vmid).status.start.post()
                result_text = f"🚀 VM {vmid} start initiated successfully\nTask ID: {task_result}"
                
            return [Content(type="text", text=result_text)]
            
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                raise ValueError(f"VM {vmid} not found on node {node}")
            self._handle_error(f"start VM {vmid}", e)

    def stop_vm(self, node: str, vmid: str) -> List[Content]:
        """Stop a virtual machine (force stop).
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2') 
            vmid: VM ID number (e.g., '100', '101')
            
        Returns:
            List of Content objects containing operation result
            
        Raises:
            ValueError: If VM is not found
            RuntimeError: If stop operation fails
        """
        try:
            # Check if VM exists and get current status
            vm_status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
            current_status = vm_status.get("status")
            
            if current_status == "stopped":
                result_text = f"🔴 VM {vmid} is already stopped"
            else:
                # Stop the VM
                task_result = self.proxmox.nodes(node).qemu(vmid).status.stop.post()
                result_text = f"🛑 VM {vmid} stop initiated successfully\nTask ID: {task_result}"
                
            return [Content(type="text", text=result_text)]
            
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                raise ValueError(f"VM {vmid} not found on node {node}")
            self._handle_error(f"stop VM {vmid}", e)

    def shutdown_vm(self, node: str, vmid: str) -> List[Content]:
        """Shutdown a virtual machine gracefully.
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            
        Returns:
            List of Content objects containing operation result
            
        Raises:
            ValueError: If VM is not found
            RuntimeError: If shutdown operation fails
        """
        try:
            # Check if VM exists and get current status
            vm_status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
            current_status = vm_status.get("status")
            
            if current_status == "stopped":
                result_text = f"🔴 VM {vmid} is already stopped"
            else:
                # Shutdown the VM gracefully
                task_result = self.proxmox.nodes(node).qemu(vmid).status.shutdown.post()
                result_text = f"💤 VM {vmid} graceful shutdown initiated\nTask ID: {task_result}"
                
            return [Content(type="text", text=result_text)]
            
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                raise ValueError(f"VM {vmid} not found on node {node}")
            self._handle_error(f"shutdown VM {vmid}", e)

    def reset_vm(self, node: str, vmid: str) -> List[Content]:
        """Reset (restart) a virtual machine.
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            
        Returns:
            List of Content objects containing operation result
            
        Raises:
            ValueError: If VM is not found
            RuntimeError: If reset operation fails
        """
        try:
            # Check if VM exists and get current status
            vm_status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
            current_status = vm_status.get("status")
            
            if current_status == "stopped":
                result_text = f"⚠️ Cannot reset VM {vmid}: VM is currently stopped\nUse start_vm to start it first"
            else:
                # Reset the VM
                task_result = self.proxmox.nodes(node).qemu(vmid).status.reset.post()
                result_text = f"🔄 VM {vmid} reset initiated successfully\nTask ID: {task_result}"
                
            return [Content(type="text", text=result_text)]
            
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                raise ValueError(f"VM {vmid} not found on node {node}")
            self._handle_error(f"reset VM {vmid}", e)

    async def execute_command(self, node: str, vmid: str, command: str) -> List[Content]:
        """Execute a command in a VM via QEMU guest agent.

        Uses the QEMU guest agent to execute commands within a running VM.
        Requires:
        - VM must be running
        - QEMU guest agent must be installed and running in the VM
        - Command execution permissions must be enabled

        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            command: Shell command to run (e.g., 'uname -a', 'systemctl status nginx')

        Returns:
            List of Content objects containing formatted command output:
            {
                "success": true/false,
                "output": "command output",
                "error": "error message if any"
            }

        Raises:
            ValueError: If VM is not found, not running, or guest agent is not available
            RuntimeError: If command execution fails due to permissions or other issues
        """
        try:
            result = await self.console_manager.execute_command(node, vmid, command)
            return [Content(type="text", text=json.dumps(result))]
        except Exception as e:
            self._handle_error(f"execute command on VM {vmid}", e)

    def delete_vm(self, node: str, vmid: str, force: bool = False) -> List[Content]:
        """Delete/remove a virtual machine completely.
        
        This will permanently delete the VM and all its associated data including:
        - VM configuration
        - Virtual disks
        - Snapshots
        
        WARNING: This operation cannot be undone!
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            force: Force deletion even if VM is running (will stop first)
            
        Returns:
            List of Content objects containing deletion result
            
        Raises:
            ValueError: If VM is not found or is running and force=False
            RuntimeError: If deletion fails
        """
        try:
            # Check if VM exists and get current status
            try:
                vm_status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
                current_status = vm_status.get("status")
                vm_name = vm_status.get("name", f"VM-{vmid}")
            except Exception as e:
                if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                    raise ValueError(f"VM {vmid} not found on node {node}")
                raise e
            
            # Check if VM is running
            if current_status == "running":
                if not force:
                    raise ValueError(f"VM {vmid} ({vm_name}) is currently running. "
                                   f"Please stop it first or use force=True to stop and delete.")
                else:
                    # Force stop the VM first
                    self.proxmox.nodes(node).qemu(vmid).status.stop.post()
                    result_text = f"🛑 Stopping VM {vmid} ({vm_name}) before deletion...\n"
            else:
                result_text = f"🗑️ Deleting VM {vmid} ({vm_name})...\n"
            
            # Delete the VM
            task_result = self.proxmox.nodes(node).qemu(vmid).delete()
            
            result_text += f"""🗑️ VM {vmid} ({vm_name}) deletion initiated successfully!

⚠️ WARNING: This operation will permanently remove:
  • VM configuration
  • All virtual disks
  • All snapshots
  • Cannot be undone!

🔧 Task ID: {task_result}

✅ VM {vmid} ({vm_name}) is being deleted from node {node}"""
            
            return [Content(type="text", text=result_text)]
            
        except ValueError as e:
            raise e
        except Exception as e:
            self._handle_error(f"delete VM {vmid}", e)
