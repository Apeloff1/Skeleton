from dataclasses import dataclass
@dataclass(frozen=True)
class WorkspaceMember: user_id:str; permissions:tuple[str,...]; revision:int
@dataclass(frozen=True)
class WorkspaceResource: ref:str
@dataclass(frozen=True)
class Workspace:
 workspace_id:str; members:tuple[WorkspaceMember,...]; resources:tuple[WorkspaceResource,...]; revision:int=0
 def link(self,r):
  if not r.ref or any(x.ref==r.ref for x in self.resources):raise ValueError("resource ref must be nonempty and unique")
  return Workspace(self.workspace_id,self.members,self.resources+(r,),self.revision+1)
 def update_member(self,m):
  if not m.user_id or m.revision<=self.revision:raise ValueError("member update must carry a fresh revision")
  return Workspace(self.workspace_id,tuple(x for x in self.members if x.user_id!=m.user_id)+(m,),self.resources,self.revision+1)
 def authorize(self,user,permission,operation_revision):
  if operation_revision!=self.revision:raise PermissionError("workspace changed; active operation must revalidate")
  m=next((x for x in self.members if x.user_id==user),None)
  if not m or permission not in m.permissions:raise PermissionError("workspace permission denied")
  return True
