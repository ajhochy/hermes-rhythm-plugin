"""State transitions; command results and actor authority are derived locally."""
from __future__ import annotations
import fnmatch,hashlib,json,os,shutil,subprocess,uuid
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from .adapters import GitAdapter,KanbanAdapter
from .contracts import PROFILES,SCHEMA_VERSION,STAGES,full_sha,valid_run_id,validate_design,validate_plan,validate_review
from .safety import redact
from .store import RunStore
def now()->str:return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def full_sha_hash(value:object)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
class WorkflowError(RuntimeError):
 def __init__(self,code:str)->None:self.code=code;super().__init__(code)
@dataclass(frozen=True)
class ActorContext:
 profile:str;task_id:str;session_id:str="unavailable";model:str="unavailable";provider:str="unavailable"
 def record(self)->dict[str,str]:return {"profile":self.profile,"task_id":self.task_id,"session_id":self.session_id,"model":self.model,"provider":self.provider}
 @classmethod
 def from_env(cls)->"ActorContext":
  p,t=os.getenv("HERMES_PROFILE"),os.getenv("HERMES_KANBAN_TASK")
  if not p or not t:raise WorkflowError("unauthenticated_actor")
  return cls(p,t,os.getenv("HERMES_SESSION_ID","unavailable"),os.getenv("HERMES_MODEL","unavailable"),os.getenv("HERMES_PROVIDER","unavailable"))
class WorkflowService:
 def __init__(self,repo:Path,git:GitAdapter|None=None)->None:self.repo=repo.resolve();self.git=git or GitAdapter(self.repo);self._boards:dict[str,KanbanAdapter]={}
 def _store(self,rid:str)->RunStore:
  if not valid_run_id(rid):raise WorkflowError("invalid_run_id")
  return RunStore(self.repo,rid)
 def _actor(self,run:dict[str,Any],actor:ActorContext,stage:str)->None:
  if run["stage_profiles"].get(stage)!=actor.profile or run["kanban_task_ids"].get(stage)!=actor.task_id:raise WorkflowError("task_profile_mismatch")
 def _workgit(self,run:dict[str,Any])->GitAdapter:return GitAdapter(Path(run["worktree_path"]))
 def _bump(self,store:RunStore,run:dict[str,Any])->None:run["revision"]+=1;run["updated_at"]=now();store.write_json("run.json",run)
 def _board_for(self,store:RunStore,run:dict[str,Any])->KanbanAdapter:
  internal=store.read("internal.json") if store._path("internal.json").exists() else {}
  home=Path(internal["kanban_home"]) if isinstance(internal.get("kanban_home"),str) else None
  return self._boards.get(run["id"]) or KanbanAdapter(self.repo,run["kanban_board"],home=home)
 def _advance(self,run:dict[str,Any],finished:str,next_stage:str|None)->None:
  run["stage_statuses"][finished]="completed"
  if next_stage:run["stage_statuses"][next_stage]="active"
 def _reconcile(self,store:RunStore,run:dict[str,Any])->None:
  board=self._board_for(store,run)
  for stage in STAGES:
   if run["stage_statuses"].get(stage)=="completed":board.complete(run["kanban_task_ids"][stage],stage)
 def reconcile(self,rid:str)->dict[str,Any]:
  store=self._store(rid)
  with store.locked():
   run=store.read();self._reconcile(store,run);return run
 def show(self,rid:str)->dict[str,Any]:return self.reconcile(rid)
 def create_run(self,package:str,scope:list[str],run_id:str,board_name:str,kanban:KanbanAdapter|None=None,goal:str="unspecified") -> dict[str,Any]:
  if not scope or any(not x or x.startswith("/") or ".." in Path(x).parts for x in scope):raise WorkflowError("path_scope_violation")
  if (self.repo/".worktrees").is_symlink() or (self.repo/".hermes").is_symlink():raise WorkflowError("path_scope_violation")
  store=self._store(run_id)
  if store._path("run.json").exists():raise WorkflowError("run_exists")
  home=Path(os.environ.get("HERMES_HOME", "")).resolve() if os.environ.get("HERMES_HOME") else None;board=kanban or KanbanAdapter(self.repo,board_name,home=home);goal=goal[:4096]
  controlled_worktree=self.repo/".worktrees"/f"hcw-{run_id}-1"
  if controlled_worktree.is_symlink():raise WorkflowError("path_scope_violation")
  requested={"operation":"create","status":"pending","package_id":package,"scope":scope,"board":board.board,"goal":goal,"attempt":1,"branch":f"hcw/{run_id}/attempt-1","worktree_path":str(controlled_worktree)}
  internal=store.read("internal.json") if store._path("internal.json").exists() else {}
  prior=internal.get("create_intent")
  if prior:
   if any(prior.get(key)!=value for key,value in requested.items() if key not in {"status"}):raise WorkflowError("run_exists")
   base=prior.get("base_sha")
   if not isinstance(base,str) or not full_sha(base):raise WorkflowError("setup_failed")
  else:
   if self.git.dirty():raise WorkflowError("dirty_repo")
   base=self.git.head();requested["base_sha"]=base;internal["create_intent"]=requested
   board_home=board.home or home
   if board_home:internal["kanban_home"]=str(board_home)
   RunStore._atomic(store._path("internal.json"),internal)
  branch=str(requested["branch"]);worktree=Path(requested["worktree_path"])
  if worktree.is_symlink():raise WorkflowError("path_scope_violation")
  try:
   if worktree.exists():
    top=subprocess.run(["git","-C",str(worktree),"rev-parse","--show-toplevel"],text=True,capture_output=True);head=subprocess.run(["git","-C",str(worktree),"rev-parse","HEAD"],text=True,capture_output=True);checked_branch=subprocess.run(["git","-C",str(worktree),"branch","--show-current"],text=True,capture_output=True)
    if top.returncode or head.returncode or checked_branch.returncode or Path(top.stdout.strip()).resolve()!=worktree.resolve() or head.stdout.strip()!=base or checked_branch.stdout.strip()!=branch:raise WorkflowError("worktree_exists")
   else:
    r=subprocess.run(["git","-C",str(self.repo),"worktree","add","-b",branch,str(worktree),base],text=True,capture_output=True,check=False)
    if r.returncode:
     branch_head=subprocess.run(["git","-C",str(self.repo),"rev-parse",branch],text=True,capture_output=True,check=False)
     if branch_head.returncode or branch_head.stdout.strip()!=base:raise WorkflowError("worktree_creation_failed")
     r=subprocess.run(["git","-C",str(self.repo),"worktree","add",str(worktree),branch],text=True,capture_output=True,check=False)
    if r.returncode:raise WorkflowError("worktree_creation_failed")
   locator={"schema_version":SCHEMA_VERSION,"run_id":run_id,"repo_root":str(self.repo),"worktree_path":str(worktree.resolve())};loc=worktree/".hermes"/"hcw-run.json";loc.parent.mkdir(parents=True,exist_ok=True);loc.write_text(json.dumps(locator,sort_keys=True)+"\n")
   prior=store.read("internal.json")["create_intent"]
   persisted_tasks=prior.get("task_ids");persisted_hashes=prior.get("brief_hashes")
   if prior.get("status") in {"graph_created","completed"} and isinstance(persisted_tasks,dict) and set(persisted_tasks)==set(STAGES) and all(isinstance(v,str) and v for v in persisted_tasks.values()) and isinstance(persisted_hashes,dict) and set(persisted_hashes)==set(STAGES) and all(isinstance(v,str) and len(v)==64 for v in persisted_hashes.values()):
    tasks=dict(persisted_tasks);brief_hashes=dict(persisted_hashes)
   else:
    board.ensure_board();tasks=board.graph(run_id,branch,worktree.resolve(),PROFILES,attempt=1,scope=scope,goal=goal,base_sha=base);brief_hashes={stage:board.last_briefs[stage]["sha256"] for stage in STAGES}
    internal=store.read("internal.json");internal["create_intent"].update({"status":"graph_created","task_ids":tasks,"brief_hashes":brief_hashes});RunStore._atomic(store._path("internal.json"),internal)
   stamp=now();run={"schema_version":SCHEMA_VERSION,"kind":"run","id":run_id,"revision":0,"created_at":stamp,"updated_at":stamp,"package_id":package,"base_sha":base,"head_sha":base,"branch":branch,"repo_root":str(self.repo),"worktree_path":str(worktree.resolve()),"status":"awaiting_design","scope":scope,"attempt":1,"attempt_history":[],"kanban_board":board.board,"kanban_task_ids":tasks,"stage_profiles":PROFILES,"stage_statuses":{stage:("active" if stage=="design" else "pending") for stage in STAGES},"setup":{"created":["worktree",*tasks.values()]},"goal":goal,"dispatches":{stage:{"stage":stage,"task_id":tasks[stage],"profile":PROFILES[stage],"attempt":1,"brief_hash":brief_hashes[stage],"session_id":"unavailable","model":"unavailable","provider":"unavailable"} for stage in STAGES}}
   self._boards[run_id]=board;store.write_run(run,None)
   internal=store.read("internal.json");internal["create_intent"]["status"]="completed";RunStore._atomic(store._path("internal.json"),internal);return run
  except Exception as exc:
   if isinstance(exc,WorkflowError):raise
   raise WorkflowError("setup_failed")
 def approve_design(self,rid:str,actor:ActorContext,payload:dict[str,Any])->dict[str,Any]:
  s=self._store(rid)
  with s.locked():
   run=s.read();self._actor(run,actor,"design");run["dispatches"]["design"].update(actor.record())
   if run["status"]!="awaiting_design" or not validate_design(payload):raise WorkflowError("malformed_design")
   record={"schema_version":SCHEMA_VERSION,"kind":"approved_design","id":"design-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"actor":actor.record(),"content":payload,"approved":True};RunStore._atomic(s._path("approved-design.json"),record);run["status"]="awaiting_plan";self._advance(run,"design","plan");self._bump(s,run);self._reconcile(s,run);return record
 def _attach_plan_briefs(self,s:RunStore,run:dict[str,Any],k:KanbanAdapter,plan_record:dict[str,Any])->None:
  payload=plan_record["content"];launcher="<installed-hcw-launcher>"
  for stage in STAGES[2:]:
   kinds={"red":["red"],"green":["green"],"verify":["full","security"],"live":["live"]}.get(stage,[])
   body=json.dumps({"run_id":run["id"],"attempt":run["attempt"],"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"launcher":launcher,"declared_commands":{kind:payload["commands"][kind]["argv"] for kind in kinds},"artifact_paths":[str(self.repo/".hermes"/"workflows"/run["id"] / "plan.json"),str(self.repo/".hermes"/"workflows"/run["id"] / "run.json")],"scope":run["scope"],"goal":run["goal"],"dependencies":[] if stage=="red" else [STAGES[STAGES.index(stage)-1]],"transition":"record authoritative HCW evidence","design_sha256":full_sha_hash(s.read("approved-design.json")),"plan_sha256":full_sha_hash(plan_record)},sort_keys=True,separators=(",",":"))
   run["dispatches"][stage]["brief_hash"]=k.comment(run["kanban_task_ids"][stage],body)
 def approve_plan(self,rid:str,actor:ActorContext,payload:dict[str,Any])->dict[str,Any]:
  s=self._store(rid)
  with s.locked():
   run=s.read();self._actor(run,actor,"plan");run["dispatches"]["plan"].update(actor.record())
   design=s.read("approved-design.json")["content"];ids={x["id"] for x in design["requirements"]}
   if run["status"]!="awaiting_plan" or not validate_plan(payload,ids):raise WorkflowError("malformed_plan")
   record={"schema_version":SCHEMA_VERSION,"kind":"plan","id":"plan-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"actor":actor.record(),"content":payload,"approved":True};RunStore._atomic(s._path("plan.json"),record)
   k=self._board_for(s,run)
   self._attach_plan_briefs(s,run,k,record)
   run["status"]="awaiting_red";self._advance(run,"plan","red");self._bump(s,run);self._reconcile(s,run);return record
 def check(self,rid:str,actor:ActorContext,typ:str,argv:list[str],timeout:int=60)->dict[str,Any]:
  if typ not in {"red","green","full","security","live"} or not argv:raise WorkflowError("invalid_check")
  s=self._store(rid)
  with s.locked():
   run=s.read();stage={"red":"red","green":"green","full":"verify","security":"verify","live":"live"}[typ];self._actor(run,actor,stage);g=self._workgit(run);head=g.head();plan=s.read("plan.json")["content"]
   if argv != plan["commands"][typ]["argv"]:raise WorkflowError("planned_command_mismatch")
   expected={"red":"awaiting_red","green":"awaiting_green","full":"awaiting_verify","security":"awaiting_verify","live":"awaiting_live"}[typ]
   if run["status"]!=expected:raise WorkflowError("check_not_ready")
   if typ=="green" and not any(e["type"]=="red" and e["exit_code"]!=0 and e["commit_sha"]==run["base_sha"] for e in s.evidence()):raise WorkflowError("missing_red_evidence")
   try:r=subprocess.run(argv,cwd=Path(run["worktree_path"]),text=True,capture_output=True,timeout=timeout,env={"PATH":os.environ.get("PATH", ""),"PYTHONDONTWRITEBYTECODE":"1","PYTHONPYCACHEPREFIX":os.environ.get("PYTHONPYCACHEPREFIX","/tmp/hcw-pyc")})
   except subprocess.TimeoutExpired as exc:r=subprocess.CompletedProcess(argv,124,exc.stdout or "",exc.stderr or "timeout")
   must_fail=typ=="red"
   if (must_fail and r.returncode==0) or (not must_fail and r.returncode!=0):raise WorkflowError("unexpected_check_exit")
   if typ=="red" and (g.head()!=head or any(not self._test_path(run,p) for p in g.paths(head))):raise WorkflowError("red_mutation_violation")
   if typ=="green":
    if head==run["base_sha"] or g.dirty() or not all(any(fnmatch.fnmatch(p,pat) for pat in run["scope"]) for p in g.paths(run["base_sha"])):raise WorkflowError("path_scope_violation")
    run["head_sha"]=head;run["status"]="awaiting_spec_review";self._advance(run,"green","spec-review")
   elif typ=="red":run["status"]="awaiting_green";self._advance(run,"red","green")
   artifact_dir=s.root/"artifacts"
   if artifact_dir.exists() and artifact_dir.is_symlink():raise WorkflowError("path_scope_violation")
   artifact_dir.mkdir(exist_ok=True)
   if artifact_dir.is_symlink() or artifact_dir.resolve().parent != s.root.resolve():raise WorkflowError("path_scope_violation")
   art=artifact_dir/(typ+"-"+uuid.uuid4().hex+".log");art.write_text(redact((r.stdout or "")+"\n"+(r.stderr or ""))[:4096])
   rec={"schema_version":SCHEMA_VERSION,"kind":"evidence","id":"EV-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"type":typ,"actor":actor.record(),"commit_sha":head,"command":argv,"exit_code":r.returncode};saved=s._append_evidence_locked(rec,art)
   if typ=="live":
    final_head=g.head();verification={"schema_version":SCHEMA_VERSION,"kind":"verification","id":"verify-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"candidate_sha":final_head,"evidence_ids":[x["id"] for x in s.evidence() if x["commit_sha"]==final_head],"status":"passed"};RunStore._atomic(s._path("verification.json"),verification);run["status"]="verified";self._advance(run,"live","complete");self._bump(s,run)
   elif typ in {"red","green"}:self._bump(s,run)
   if typ in {"red","green","live"}:self._reconcile(s,run)
   return saved
 def _test_path(self,run:dict[str,Any],path:str)->bool:
  return bool(__import__("re").search(r"(?:^|/)(?:tests?/|test_|.*(?:test|spec)\\.)",path)) and any(fnmatch.fnmatch(path,p) for p in run["scope"])
 def commit(self,rid:str,actor:ActorContext,message:str)->dict[str,Any]:
  if not message or len(message)>4096:raise WorkflowError("invalid_commit_message")
  s=self._store(rid)
  with s.locked():
   run=s.read();self._actor(run,actor,"green")
   if run["status"]!="awaiting_green":raise WorkflowError("check_not_ready")
   g=self._workgit(run);paths=sorted(g.paths(run["base_sha"]))
   if not paths or not all(any(fnmatch.fnmatch(path,pat) for pat in run["scope"]) for path in paths):raise WorkflowError("path_scope_violation")
   result=subprocess.run(["git","-C",str(run["worktree_path"]),"add","--",*paths],text=True,capture_output=True)
   if result.returncode:raise WorkflowError("commit_failed")
   result=subprocess.run(["git","-C",str(run["worktree_path"]),"commit","--no-verify","-m",message,"--",*paths],text=True,capture_output=True)
   if result.returncode:raise WorkflowError("commit_failed")
   return {"commit_sha":g.head(),"paths":paths}
 def review(self,rid:str,actor:ActorContext,payload:dict[str,Any])->dict[str,Any]:
  s=self._store(rid)
  with s.locked():
   run=s.read();stage="spec-review" if actor.task_id==run["kanban_task_ids"]["spec-review"] else "quality-review";self._actor(run,actor,stage);head=self._workgit(run).head()
   expected="awaiting_spec_review" if stage=="spec-review" else "awaiting_quality_review"
   if run["status"]!=expected or self._workgit(run).dirty() or not validate_review(payload) or payload["reviewed_sha"]!=head:raise WorkflowError("malformed_review")
   rec={"schema_version":SCHEMA_VERSION,"kind":"review","id":"RV-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"reviewer":actor.record(),**payload};reviews=s.read("reviews.json") if s._path("reviews.json").exists() else {"reviews":[]};reviews["reviews"].append(rec);RunStore._atomic(s._path("reviews.json"),reviews)
   if payload["decision"]!="approved":
    run["status"]="repairing";run["stage_statuses"][stage]="blocked";self._bump(s,run);return rec
   run["status"]="awaiting_quality_review" if stage=="spec-review" else "awaiting_verify";self._advance(run,stage,"quality-review" if stage=="spec-review" else "verify");self._bump(s,run);self._reconcile(s,run);return rec
 def verify(self,rid:str,actor:ActorContext)->dict[str,Any]:
  s=self._store(rid)
  with s.locked():
   run=s.read();self._actor(run,actor,"verify");head=self._workgit(run).head();ev=s.evidence();reviews=s.read("reviews.json").get("reviews",[]) if s._path("reviews.json").exists() else []
   if run["status"]!="awaiting_verify" or head!=run["head_sha"] or self._workgit(run).dirty() or not {"full","security"}.issubset({x["type"] for x in ev if x["commit_sha"]==head and x["exit_code"]==0}) or {r["reviewer"]["profile"] for r in reviews if r["reviewed_sha"]==head and r["decision"]=="approved"}!={PROFILES["spec-review"],PROFILES["quality-review"]}:raise WorkflowError("premature_completion")
   rec={"schema_version":SCHEMA_VERSION,"kind":"verification","id":"verify-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"candidate_sha":head,"evidence_ids":[x["id"] for x in ev if x["commit_sha"]==head],"status":"deterministic_passed"};RunStore._atomic(s._path("verification.json"),rec);run["status"]="awaiting_live";self._advance(run,"verify","live");self._bump(s,run);self._reconcile(s,run);return rec
 def complete(self,rid:str,actor:ActorContext)->dict[str,Any]:
  s=self._store(rid)
  with s.locked():
   run=s.read();self._actor(run,actor,"complete");head=self._workgit(run).head();v=s.read("verification.json") if s._path("verification.json").exists() else {}
   try:ev=s.evidence()
   except (ValueError,json.JSONDecodeError,OSError) as exc:raise WorkflowError("evidence_integrity_failure") from exc
   current_ids=[item["id"] for item in ev if item["commit_sha"]==head]
   if run["status"]!="verified" or v.get("candidate_sha")!=head or v.get("evidence_ids")!=current_ids or len(current_ids)!=len(set(current_ids)) or not {"green","full","security","live"}.issubset({item["type"] for item in ev if item["commit_sha"]==head and item["exit_code"]==0}) or self._workgit(run).dirty():raise WorkflowError("premature_completion")
   h={"schema_version":SCHEMA_VERSION,"kind":"handoff","id":"handoff-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"candidate_sha":head,"action":"draft_pr_manual_merge"};RunStore._atomic(s._path("handoff.json"),h);run["status"]="completed";self._advance(run,"complete",None);self._bump(s,run);self._reconcile(s,run);return run
 def repair(self,rid:str,actor:ActorContext,board:KanbanAdapter|None=None)->dict[str,Any]:
  """Archive an attempt and create a fresh, independently bound task graph."""
  s=self._store(rid)
  with s.locked():
   run=s.read()
   recovery_stage="spec-review" if actor.task_id==run["kanban_task_ids"].get("spec-review") else "quality-review"
   self._actor(run,actor,recovery_stage)
   if run["status"]!="repairing" or run["stage_statuses"].get(recovery_stage)!="blocked":raise WorkflowError("repair_not_authorized")
   if (self.repo/".worktrees").is_symlink() or (self.repo/".hermes").is_symlink():raise WorkflowError("path_scope_violation")
   old=Path(run["worktree_path"]);attempt=run["attempt"]+1;branch=f"hcw/{rid}/attempt-{attempt}";worktree=self.repo/".worktrees"/f"hcw-{rid}-{attempt}"
   if worktree.is_symlink():raise WorkflowError("path_scope_violation")
   internal=s.read("internal.json") if s._path("internal.json").exists() else {};k=board or self._boards.get(rid) or KanbanAdapter(self.repo,run["kanban_board"],home=Path(internal["kanban_home"]) if isinstance(internal.get("kanban_home"),str) else None)
   requested={"operation":"repair","status":"pending","from_attempt":run["attempt"],"attempt":attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":run["base_sha"],"board":run["kanban_board"]}
   prior=internal.get("repair_intent")
   if prior and prior.get("status")!="completed":
    if any(prior.get(key)!=value for key,value in requested.items() if key!="status"):raise WorkflowError("repair_setup_failed")
   else:
    internal["repair_intent"]=requested;RunStore._atomic(s._path("internal.json"),internal)
   try:
    if worktree.exists():
     top=subprocess.run(["git","-C",str(worktree),"rev-parse","--show-toplevel"],text=True,capture_output=True);head=subprocess.run(["git","-C",str(worktree),"rev-parse","HEAD"],text=True,capture_output=True);checked_branch=subprocess.run(["git","-C",str(worktree),"branch","--show-current"],text=True,capture_output=True)
     if top.returncode or head.returncode or checked_branch.returncode or Path(top.stdout.strip()).resolve()!=worktree.resolve() or head.stdout.strip()!=run["base_sha"] or checked_branch.stdout.strip()!=branch:raise WorkflowError("repair_setup_failed")
    else:
     result=subprocess.run(["git","-C",str(self.repo),"worktree","add","-b",branch,str(worktree),run["base_sha"]],capture_output=True,text=True)
     if result.returncode:
      branch_head=subprocess.run(["git","-C",str(self.repo),"rev-parse",branch],text=True,capture_output=True)
      if branch_head.returncode or branch_head.stdout.strip()!=run["base_sha"]:raise WorkflowError("repair_setup_failed")
      result=subprocess.run(["git","-C",str(self.repo),"worktree","add",str(worktree),branch],capture_output=True,text=True)
     if result.returncode:raise WorkflowError("repair_setup_failed")
    (worktree/".hermes").mkdir(parents=True,exist_ok=True);(worktree/".hermes"/"hcw-run.json").write_text(json.dumps({"schema_version":SCHEMA_VERSION,"run_id":rid,"repo_root":str(self.repo),"worktree_path":str(worktree.resolve())})+"\n")
    prior=s.read("internal.json")["repair_intent"];persisted_tasks=prior.get("task_ids");persisted_hashes=prior.get("brief_hashes")
    if prior.get("status") in {"graph_created","completed"} and isinstance(persisted_tasks,dict) and set(persisted_tasks)==set(STAGES) and all(isinstance(v,str) and v for v in persisted_tasks.values()) and isinstance(persisted_hashes,dict) and set(persisted_hashes)==set(STAGES) and all(isinstance(v,str) and len(v)==64 for v in persisted_hashes.values()):
     tasks=dict(persisted_tasks);brief_hashes=dict(persisted_hashes)
    else:
     tasks=k.graph(rid,branch,worktree.resolve(),PROFILES,attempt=attempt,scope=run["scope"],goal=run["goal"],base_sha=run["base_sha"]);brief_hashes={stage:k.last_briefs[stage]["sha256"] for stage in STAGES}
     internal=s.read("internal.json");internal["repair_intent"].update({"status":"graph_created","task_ids":tasks,"brief_hashes":brief_hashes});RunStore._atomic(s._path("internal.json"),internal)
    draft=dict(run);draft.update({"attempt":attempt,"kanban_task_ids":tasks,"dispatches":{stage:{"stage":stage,"task_id":tasks[stage],"profile":PROFILES[stage],"attempt":attempt,"brief_hash":brief_hashes[stage],"session_id":"unavailable","model":"unavailable","provider":"unavailable"} for stage in STAGES}})
    self._attach_plan_briefs(s,draft,k,s.read("plan.json"))
   except WorkflowError:raise
   except Exception as exc:raise WorkflowError("repair_setup_failed") from exc
   archive=s.root/"attempts"/str(run["attempt"]);archive.mkdir(parents=True,exist_ok=True)
   for name in ("evidence.jsonl","reviews.json","verification.json","handoff.json"):
    source=s._path(name)
    if source.exists():shutil.move(str(source),str(archive/name))
   run["attempt_history"].append({"attempt":run["attempt"],"worktree_path":str(old),"head_sha":run["head_sha"]});run.update({"attempt":attempt,"branch":branch,"worktree_path":str(worktree.resolve()),"head_sha":run["base_sha"],"kanban_task_ids":tasks,"dispatches":draft["dispatches"],"stage_statuses":{stage:("active" if stage=="red" else "pending") for stage in STAGES},"status":"awaiting_red"});self._bump(s,run)
   internal=s.read("internal.json");internal["repair_intent"]["status"]="completed";RunStore._atomic(s._path("internal.json"),internal);return run
