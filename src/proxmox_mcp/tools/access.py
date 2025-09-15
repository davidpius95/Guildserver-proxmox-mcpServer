from typing import List, Optional
import json
from mcp.types import TextContent as Content
from .base import ProxmoxTool


class AccessTools(ProxmoxTool):
    """Wrappers for /access API (users, groups, roles, ACL)."""

    # Users
    def list_users(self) -> List[Content]:
        result = self.proxmox.access.users.get()
        return [Content(type="text", text=json.dumps(result))]

    def create_user(
        self,
        user: str,
        password: Optional[str] = None,
        comment: Optional[str] = None,
        expire: Optional[int] = None,
        enable: Optional[bool] = True,
    ) -> List[Content]:
        payload = {"userid": user}
        if password is not None:
            payload["password"] = password
        if comment is not None:
            payload["comment"] = comment
        if expire is not None:
            payload["expire"] = expire
        if enable is not None:
            payload["enable"] = int(bool(enable))
        result = self.proxmox.access.users.post(**payload)
        return [Content(type="text", text=json.dumps(result))]

    def update_user(self, user: str, changes: dict) -> List[Content]:
        result = self.proxmox.access.users(user).put(**(changes or {}))
        return [Content(type="text", text=json.dumps(result))]

    def delete_user(self, user: str) -> List[Content]:
        result = self.proxmox.access.users(user).delete()
        return [Content(type="text", text=json.dumps(result))]

    # Groups
    def list_groups(self) -> List[Content]:
        result = self.proxmox.access.groups.get()
        return [Content(type="text", text=json.dumps(result))]

    def create_group(self, groupid: str, comment: Optional[str] = None) -> List[Content]:
        payload = {"groupid": groupid}
        if comment is not None:
            payload["comment"] = comment
        result = self.proxmox.access.groups.post(**payload)
        return [Content(type="text", text=json.dumps(result))]

    def delete_group(self, groupid: str) -> List[Content]:
        result = self.proxmox.access.groups(groupid).delete()
        return [Content(type="text", text=json.dumps(result))]

    # Roles
    def list_roles(self) -> List[Content]:
        result = self.proxmox.access.roles.get()
        return [Content(type="text", text=json.dumps(result))]

    def create_role(self, roleid: str, privs: str) -> List[Content]:
        result = self.proxmox.access.roles.post(roleid=roleid, privs=privs)
        return [Content(type="text", text=json.dumps(result))]

    def delete_role(self, roleid: str) -> List[Content]:
        result = self.proxmox.access.roles(roleid).delete()
        return [Content(type="text", text=json.dumps(result))]

    # ACL
    def get_acl(self) -> List[Content]:
        result = self.proxmox.access.acl.get()
        return [Content(type="text", text=json.dumps(result))]

    def set_acl(
        self,
        path: str,
        roles: Optional[str] = None,
        users: Optional[str] = None,
        groups: Optional[str] = None,
        propagate: Optional[bool] = True,
        delete: Optional[bool] = None,
    ) -> List[Content]:
        payload = {"path": path}
        if roles is not None:
            payload["roles"] = roles
        if users is not None:
            payload["users"] = users
        if groups is not None:
            payload["groups"] = groups
        if propagate is not None:
            payload["propagate"] = int(bool(propagate))
        if delete is not None:
            payload["delete"] = int(bool(delete))
        result = self.proxmox.access.acl.put(**payload)
        return [Content(type="text", text=json.dumps(result))]


