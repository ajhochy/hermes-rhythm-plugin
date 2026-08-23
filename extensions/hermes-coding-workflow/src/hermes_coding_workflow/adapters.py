"""Hermes v0.20 and git argv-only adapters."""
from __future__ import annotations
import hashlib, json, os, re, subprocess, unicodedata
from pathlib import Path
from typing import Callable, Sequence
from .contracts import STAGES, full_sha
from .safety import safe_relative
Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
def _run(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]: return subprocess.run(list(argv), cwd=cwd, text=True, capture_output=True, check=False, timeout=30)
class GitAdapter:
 def __init__(self, repo: Path, runner: Runner=_run)->None:self.repo,self.runner=repo.resolve(),runner
 def call(self,*args:str)->str:
  r=self.runner(("git","-C",str(self.repo),*args),self.repo)
  if r.returncode: raise RuntimeError("git_failed:"+r.stderr[:256])
  return r.stdout.strip()
 def head(self)->str:
  value=self.call("rev-parse","HEAD")
  if not full_sha(value): raise RuntimeError("invalid_git_sha")
  return value
 def paths(self,base:str)->set[str]:
  raw=(self.call("diff","-z","--name-only",f"{base}..HEAD"),self.call("diff","-z","--name-only"),self.call("diff","--cached","-z","--name-only"),self.call("ls-files","-z","--others","--exclude-standard"))
  return {str(safe_relative(self.repo,p)) for group in raw for p in group.split("\0") if p and not p.startswith(".hermes/workflows/") and p != ".hermes/hcw-run.json"}
 def dirty(self)->bool:return bool(self.paths(self.head()))
class KanbanAdapter:
 def __init__(self,repo:Path,board:str,runner:Runner=_run,home:Path|None=None)->None:
  if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}",board):raise ValueError("invalid_board")
  self.repo,self.board,self.runner,self.home=repo.resolve(),board,runner,home.resolve() if home else None
 def call(self,*args:str,json_output:bool=True)->dict:
  argv=("hermes","kanban","--board",self.board,*args,*(("--json",) if json_output else ()))
  if self.home and self.runner is _run:
   r=subprocess.run(list(argv),cwd=self.repo,text=True,capture_output=True,check=False,timeout=30,env={**os.environ,"HERMES_HOME":str(self.home)})
  else:r=self.runner(argv,self.repo)
  if r.returncode:raise RuntimeError("kanban_failed")
  if not json_output:return {"output":r.stdout}
  payload=json.loads(r.stdout or "{}")
  if not isinstance(payload,dict):raise RuntimeError("kanban_invalid_json")
  return payload
 def ensure_board(self)->dict:
  try:return self.call("boards","create",self.board,"--default-workdir",str(self.repo),json_output=False)
  except RuntimeError:
   found=self.call("boards","list").get("boards",[])
   if any(isinstance(x,dict) and x.get("slug")==self.board for x in found):return {"board":self.board,"existing":True}
   raise
 def _card_title(self,stage:str,goal:str)->str:
  actions={"design":"Design","plan":"Plan","red":"Write failing tests","green":"Implement","spec-review":"Review requirements","quality-review":"Review code quality","verify":"Verify","live":"Test live","complete":"Complete"}
  normalized=unicodedata.normalize("NFKC",goal) if isinstance(goal,str) else ""
  visible="".join(" " if unicodedata.category(char).startswith("C") else char for char in normalized)
  subject=re.sub(r"\s+"," ",visible).strip(" .")[:100] or "requested change"
  return f"{actions.get(stage,'Work on')}: {subject}"
 def graph(self,run_id:str,branch:str,workspace:Path,profiles:dict[str,str],*,attempt:int=1,scope:list[str]|None=None,goal:str="unspecified",base_sha:str="") -> dict[str,str]:
  made={};previous=None;self.last_briefs={}
  for stage in STAGES:
   brief={"run_id":run_id,"stage":stage,"role":profiles[stage],"attempt":attempt,"branch":branch,"worktree":str(workspace),"scope":scope or [],"goal":goal,"depends_on":previous,"source_artifacts":[".hermes/hcw-run.json",f".hermes/workflows/{run_id}/run.json"],"public_command_skeleton":{"launcher":"<installed-hcw-launcher>","argv":["<installed-hcw-launcher>","<public-subcommand>","<repo>",run_id]},"completion_transition":"record authoritative HCW evidence"}
   body=json.dumps(brief,sort_keys=True,separators=(",",":"));self.last_briefs[stage]={"body":body,"sha256":hashlib.sha256(body.encode()).hexdigest()}
   task=self.call("create",self._card_title(stage,goal),"--body",body,"--workspace",f"worktree:{workspace}","--branch",branch,"--assignee",profiles[stage],"--idempotency-key",f"hcw:{run_id}:attempt-{attempt}:{stage}")
   ident=str(task.get("id",""))
   if not ident:raise RuntimeError("kanban_missing_task_id")
   if previous:self.call("link",previous,ident,json_output=False)
   made[stage]=ident;previous=ident
  return made
 def comment(self,task_id:str,body:str)->str:
  self.call("comment",task_id,body,"--author","hcw",json_output=False)
  return hashlib.sha256(body.encode()).hexdigest()
 def complete(self,task_id:str,stage:str)->None:
  shown=self.call("show",task_id)
  task=shown.get("task")
  if not isinstance(task,dict) or not isinstance(task.get("status"),str):raise RuntimeError("kanban_invalid_task")
  if task["status"]=="done":return
  if task["status"] not in {"ready","running"}:
   promote_args=("promote",task_id,"--allow-triage") if task["status"]=="triage" else ("promote",task_id)
   self.call(*promote_args,json_output=False);shown=self.call("show",task_id);task=shown.get("task")
   if not isinstance(task,dict) or task.get("status") not in {"ready","running","done"}:raise RuntimeError("kanban_invalid_task")
   if task["status"]=="done":return
  summary=f"HCW stage {stage} accepted"
  self.call("complete",task_id,"--result",summary,"--summary",summary,json_output=False)
 def delete(self,task_id:str)->None:
  try:self.call("delete",task_id,json_output=False)
  except RuntimeError:pass
