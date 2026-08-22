"""State transitions; command results and actor authority are derived locally."""
from __future__ import annotations
import fnmatch,hashlib,json,os,shutil,subprocess,sys,uuid
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from .adapters import GitAdapter,KanbanAdapter
from .contracts import CLAUDE_BACKEND,CLAUDE_STAGES,CLAUDE_TIER_MODELS,PROFILES,SCHEMA_VERSION,STAGES,full_sha,valid_run_id,validate_design,validate_plan,validate_record,validate_review
from . import process
from .safety import open_nofollow_write_fd,redact,validate_controlled_worktree
from .store import RunStore
def now()->str:return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def full_sha_hash(value:object)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _attempt_base_sha(run:dict[str,Any])->str:
 value=run.get("attempt_base_sha",run["base_sha"])
 if not full_sha(value):raise WorkflowError("malformed_run_state")
 return value
MAX_WORKER_ATTEMPTS=3
REPAIR_CONTEXT_FIELDS={"schema_version","kind","from_attempt","source_stage","review_sha256","review"}
def _valid_repair_context(value:object,run:dict[str,Any],internal:dict[str,Any])->bool:
 if run.get("attempt")==1:return value is None
 intent=internal.get("repair_intent") if isinstance(internal,dict) else None
 if value is None:
  return isinstance(intent,dict) and "repair_context_sha256" not in intent and intent.get("status") in {"completed","graph_created"} and intent.get("from_attempt")==run.get("attempt",0)-1 and intent.get("attempt")==run.get("attempt")
 if not isinstance(value,dict) or set(value)!=REPAIR_CONTEXT_FIELDS or value.get("schema_version")!=SCHEMA_VERSION or value.get("kind")!="repair_context" or value.get("from_attempt")!=run.get("attempt",0)-1 or value.get("source_stage") not in {"spec-review","quality-review"}:return False
 review=value.get("review");stage=value["source_stage"]
 if not isinstance(review,dict) or validate_record(review) or review.get("decision")!="changes_requested" or review.get("reviewer",{}).get("profile")!=PROFILES[stage] or value.get("review_sha256")!=full_sha_hash(review):return False
 history=run.get("attempt_history");previous=history[-1] if isinstance(history,list) and history else None
 if not isinstance(previous,dict) or previous.get("attempt")!=value["from_attempt"] or review.get("reviewed_sha")!=previous.get("head_sha"):return False
 intent=internal.get("repair_intent") if isinstance(internal,dict) else None
 return isinstance(intent,dict) and intent.get("from_attempt")==value["from_attempt"] and intent.get("attempt")==run.get("attempt") and intent.get("repair_context_sha256")==full_sha_hash(value) and intent.get("base_sha")==review.get("reviewed_sha")
def _runner_pythonpath(existing:str|None)->str:
 """Build the `worker_runner` subprocess's PYTHONPATH from the authoritative
 package site -- the directory containing this very `hermes_coding_workflow`
 package, whether that is a source checkout's `src/` or an installed
 `runtime/site/` (see `scripts/install.py`'s `_build_plugin`). The installed
 `runtime/bin/hcw` launcher only mutates its own process's `sys.path`; a
 freshly spawned `python -m hermes_coding_workflow.worker_runner` inherits no
 such thing, so the site must be derived here, not assumed from the caller's
 environment.
 """
 package_site=str(Path(__file__).resolve().parent.parent)
 entries=[package_site]
 if existing:
  entries+=[p for p in existing.split(os.pathsep) if p and os.path.isdir(p)]
 seen:list[str]=[]
 for entry in entries:
  absolute=os.path.abspath(entry)
  if absolute not in seen:seen.append(absolute)
 return os.pathsep.join(seen)
def _open_runner_log_fd(path:Path)->int:
 """Open the runner log relative to one verified parent directory handle."""
 return open_nofollow_write_fd(path)
def _authoritative_intent(internal:dict[str,Any],attempt:int)->dict[str,Any]:
 """The authoritative source of task identity for `attempt`: `create_intent`
 for attempt 1, or `repair_intent` when it matches the current attempt.
 Dispatch never trusts `run.json`'s own `kanban_task_ids`/`dispatches`
 fields against themselves -- both must agree with this durable, orchestrator-
 written intent recorded before the graph was ever created.
 """
 if attempt==1:
  intent=internal.get("create_intent")
  return intent if isinstance(intent,dict) else {}
 intent=internal.get("repair_intent")
 return intent if isinstance(intent,dict) and intent.get("attempt")==attempt else {}
def _worker_process_alive(record:dict[str,Any])->bool:
 """A worker record is only "alive" when its recorded `process_identity`
 matches a live process's current argv suffix and start time. A bare PID
 proves nothing by itself: PIDs are reused, so an unverified match must
 never block a new dispatch or be treated as evidence the original runner
 is still running.
 """
 return process.matches_identity(record.get("pid"),record.get("process_identity"))
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
 def _require_succeeded_worker(self,s:RunStore,run:dict[str,Any],stage:str)->dict[str,Any]:
  attempt=run["attempt"];latest=s.latest_worker_attempt(stage,attempt)
  record=s.read_worker(stage,attempt,latest) if latest else None;dispatch=run["dispatches"].get(stage) or {}
  repair_context=s.read("repair-context.json") if s._path("repair-context.json").exists() else None
  expected_dispatch=full_sha_hash({"run_id":run["id"],"stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"attempt":attempt,"brief_hash":dispatch.get("brief_hash")})
  if not record or validate_record(record) or record.get("state")!="succeeded" or record.get("exit_code")!=0:raise WorkflowError("worker_not_succeeded")
  internal=s.read("internal.json") if s._path("internal.json").exists() else {}
  if not _valid_repair_context(repair_context,run,internal):raise WorkflowError("worker_not_succeeded")
  intent=_authoritative_intent(internal,attempt);intent_tasks=intent.get("task_ids") if isinstance(intent,dict) else None;intent_hashes=intent.get("brief_hashes") if isinstance(intent,dict) else None
  if not isinstance(intent_tasks,dict) or intent_tasks.get(stage)!=run["kanban_task_ids"][stage] or not isinstance(intent_hashes,dict) or intent_hashes.get(stage)!=dispatch.get("brief_hash"):raise WorkflowError("worker_not_succeeded")
  if record.get("run_id")!=run["id"] or record.get("stage")!=stage or record.get("task_id")!=run["kanban_task_ids"][stage] or record.get("profile")!=PROFILES[stage] or record.get("attempt")!=attempt or record.get("worker_attempt")!=latest or record.get("brief_hash")!=dispatch.get("brief_hash") or record.get("backend")!=CLAUDE_BACKEND or record.get("model")!=CLAUDE_TIER_MODELS[stage] or record.get("worktree_path")!=run["worktree_path"]:raise WorkflowError("worker_not_succeeded")
  if record.get("design_sha256")!=full_sha_hash(s.read("approved-design.json")) or record.get("plan_sha256")!=full_sha_hash(s.read("plan.json")) or record.get("dispatch_sha256")!=expected_dispatch:raise WorkflowError("worker_not_succeeded")
  record_context_hash=record.get("repair_context_sha256")
  if (record_context_hash is None and repair_context is not None) or (record_context_hash is not None and record_context_hash!=full_sha_hash(repair_context)):raise WorkflowError("worker_not_succeeded")
  artifact_root=s.root/"artifacts"
  if artifact_root.is_symlink() or not artifact_root.is_dir():raise WorkflowError("worker_not_succeeded")
  for path_key,hash_key in (("stdout_path","stdout_sha256"),("stderr_path","stderr_sha256")):
   relative=record.get(path_key)
   if not isinstance(relative,str):raise WorkflowError("worker_not_succeeded")
   supplied=Path(relative)
   if supplied.is_absolute() or ".." in supplied.parts:raise WorkflowError("worker_not_succeeded")
   artifact=self.repo/supplied
   if artifact.parent!=artifact_root or artifact.is_symlink() or not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest()!=record.get(hash_key):raise WorkflowError("worker_not_succeeded")
  return record
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
   stamp=now();run={"schema_version":SCHEMA_VERSION,"kind":"run","id":run_id,"revision":0,"created_at":stamp,"updated_at":stamp,"package_id":package,"base_sha":base,"head_sha":base,"attempt_base_sha":base,"branch":branch,"repo_root":str(self.repo),"worktree_path":str(worktree.resolve()),"status":"awaiting_design","scope":scope,"attempt":1,"attempt_history":[],"kanban_board":board.board,"kanban_task_ids":tasks,"stage_profiles":PROFILES,"stage_statuses":{stage:("active" if stage=="design" else "pending") for stage in STAGES},"setup":{"created":["worktree",*tasks.values()]},"goal":goal,"dispatches":{stage:{"stage":stage,"task_id":tasks[stage],"profile":PROFILES[stage],"attempt":1,"brief_hash":brief_hashes[stage],"session_id":"unavailable","model":"unavailable","provider":"unavailable"} for stage in STAGES}}
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
 def _persist_authoritative_briefs(self,s:RunStore,run:dict[str,Any])->None:
  internal=s.read("internal.json");intent=_authoritative_intent(internal,run["attempt"])
  if not intent:raise WorkflowError("dispatch_identity_mismatch")
  hashes=dict(intent.get("brief_hashes") or {})
  hashes.update({stage:run["dispatches"][stage]["brief_hash"] for stage in STAGES[2:]})
  intent["brief_hashes"]=hashes;RunStore._atomic(s._path("internal.json"),internal)
 def approve_plan(self,rid:str,actor:ActorContext,payload:dict[str,Any])->dict[str,Any]:
  s=self._store(rid)
  with s.locked():
   run=s.read();self._actor(run,actor,"plan");run["dispatches"]["plan"].update(actor.record())
   design=s.read("approved-design.json")["content"];ids={x["id"] for x in design["requirements"]}
   if run["status"]!="awaiting_plan" or not validate_plan(payload,ids):raise WorkflowError("malformed_plan")
   record={"schema_version":SCHEMA_VERSION,"kind":"plan","id":"plan-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"actor":actor.record(),"content":payload,"approved":True};RunStore._atomic(s._path("plan.json"),record)
   k=self._board_for(s,run)
   self._attach_plan_briefs(s,run,k,record);self._persist_authoritative_briefs(s,run)
   run["status"]="awaiting_red";self._advance(run,"plan","red");self._bump(s,run);self._reconcile(s,run);return record
 def _record_worker_retry_authorization(self,s:RunStore,run:dict[str,Any],stage:str,gate:str,head:str,details:dict[str,Any]|None=None)->None:
  worker=self._require_succeeded_worker(s,run,stage)
  internal=s.read("internal.json") if s._path("internal.json").exists() else {}
  authorizations=internal.setdefault("worker_retry_authorizations",{})
  authorizations[stage]={"attempt":run["attempt"],"worker_id":worker["id"],"head_sha":head,"gate":gate,"details":details or {},"created_at":now(),"consumed_at":None,"retry_worker_attempt":None}
  RunStore._atomic(s._path("internal.json"),internal)
 def check(self,rid:str,actor:ActorContext,typ:str,argv:list[str],timeout:int=60)->dict[str,Any]:
  if typ not in {"red","green","full","security","live"} or not argv:raise WorkflowError("invalid_check")
  s=self._store(rid)
  with s.locked():
   run=s.read();stage={"red":"red","green":"green","full":"verify","security":"verify","live":"live"}[typ];self._actor(run,actor,stage);g=self._workgit(run);head=g.head();plan=s.read("plan.json")["content"]
   if argv != plan["commands"][typ]["argv"]:raise WorkflowError("planned_command_mismatch")
   expected={"red":"awaiting_red","green":"awaiting_green","full":"awaiting_verify","security":"awaiting_verify","live":"awaiting_live"}[typ]
   if run["status"]!=expected:raise WorkflowError("check_not_ready")
   if typ in {"red","green"}:self._require_succeeded_worker(s,run,typ)
   if typ=="green" and not any(e["type"]=="red" and e["exit_code"]!=0 and e["commit_sha"]==_attempt_base_sha(run) for e in s.evidence()):raise WorkflowError("missing_red_evidence")
   check_env={"PATH":os.environ.get("PATH", ""),"PYTHONDONTWRITEBYTECODE":"1","PYTHONPYCACHEPREFIX":os.environ.get("PYTHONPYCACHEPREFIX","/tmp/hcw-pyc")}
   if os.environ.get("HOME"):check_env["HOME"]=os.environ["HOME"]
   try:r=subprocess.run(argv,cwd=Path(run["worktree_path"]),text=True,capture_output=True,timeout=timeout,env=check_env)
   except subprocess.TimeoutExpired as exc:
    if typ in {"red","green"}:self._record_worker_retry_authorization(s,run,typ,"check_timeout",head)
    raise WorkflowError("check_timeout") from exc
   must_fail=typ=="red"
   if (must_fail and r.returncode==0) or (not must_fail and r.returncode!=0):
    if typ in {"red","green"}:self._record_worker_retry_authorization(s,run,typ,"unexpected_check_exit",head)
    raise WorkflowError("unexpected_check_exit")
   if typ=="red" and (g.head()!=head or any(not self._test_path(run,p) for p in g.paths(head))):
    self._record_worker_retry_authorization(s,run,typ,"red_mutation_violation",head)
    raise WorkflowError("red_mutation_violation")
   if typ=="green":
    if head==_attempt_base_sha(run) or g.dirty() or not all(any(fnmatch.fnmatch(p,pat) for pat in run["scope"]) for p in g.paths(_attempt_base_sha(run))):
     self._record_worker_retry_authorization(s,run,typ,"path_scope_violation",head)
     raise WorkflowError("path_scope_violation")
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
   self._require_succeeded_worker(s,run,"green")
   g=self._workgit(run);paths=sorted(g.paths(_attempt_base_sha(run)));head=g.head()
   out_of_scope=[path for path in paths if not any(fnmatch.fnmatch(path,pat) for pat in run["scope"])]
   if not paths or out_of_scope:
    self._record_worker_retry_authorization(s,run,"green","commit",head,{"reason":"path_scope_violation","changed_paths":paths[:200],"out_of_scope_paths":out_of_scope[:200],"allowed_scope":run["scope"]})
    raise WorkflowError("path_scope_violation")
   result=subprocess.run(["git","-C",str(run["worktree_path"]),"add","--",*paths],text=True,capture_output=True)
   if result.returncode:
    self._record_worker_retry_authorization(s,run,"green","commit_failed",head)
    raise WorkflowError("commit_failed")
   result=subprocess.run(["git","-C",str(run["worktree_path"]),"commit","--no-verify","-m",message,"--",*paths],text=True,capture_output=True)
   if result.returncode:
    self._record_worker_retry_authorization(s,run,"green","commit_failed",g.head())
    raise WorkflowError("commit_failed")
   return {"commit_sha":g.head(),"paths":paths}
 def review(self,rid:str,actor:ActorContext,payload:dict[str,Any])->dict[str,Any]:
  s=self._store(rid)
  with s.locked():
   run=s.read();stage="spec-review" if actor.task_id==run["kanban_task_ids"]["spec-review"] else "quality-review";self._actor(run,actor,stage);head=self._workgit(run).head()
   expected="awaiting_spec_review" if stage=="spec-review" else "awaiting_quality_review"
   if run["status"]!=expected:raise WorkflowError("malformed_review")
   if stage=="quality-review":self._require_succeeded_worker(s,run,stage)
   if self._workgit(run).dirty() or not validate_review(payload) or payload["reviewed_sha"]!=head:raise WorkflowError("malformed_review")
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
   if run["status"]=="verified":self._require_succeeded_worker(s,run,"complete")
   current_ids=[item["id"] for item in ev if item["commit_sha"]==head]
   if run["status"]!="verified" or v.get("candidate_sha")!=head or v.get("evidence_ids")!=current_ids or len(current_ids)!=len(set(current_ids)) or not {"green","full","security","live"}.issubset({item["type"] for item in ev if item["commit_sha"]==head and item["exit_code"]==0}) or self._workgit(run).dirty():raise WorkflowError("premature_completion")
   h={"schema_version":SCHEMA_VERSION,"kind":"handoff","id":"handoff-"+uuid.uuid4().hex,"created_at":now(),"run_id":rid,"candidate_sha":head,"action":"draft_pr_manual_merge"};RunStore._atomic(s._path("handoff.json"),h);run["status"]="completed";self._advance(run,"complete",None);self._bump(s,run);self._reconcile(s,run);return run
 def amend_scope(self,rid:str,actor:ActorContext,added_scope:list[str],*,reason:str,expected_revision:int,expected_head:str)->dict[str,Any]:
  """Add narrowly bounded paths to an active GREEN contract with an audit trail."""
  s=self._store(rid)
  with s.locked():
   run=s.read();self._actor(run,actor,"green")
   if run["status"]!="awaiting_green" or run["stage_statuses"].get("green")!="active":raise WorkflowError("scope_amendment_not_authorized")
   if not isinstance(reason,str) or not reason.strip() or len(reason)>512 or not isinstance(added_scope,list) or not added_scope:raise WorkflowError("invalid_scope_amendment")
   validated=[]
   for pattern in added_scope:
    if not isinstance(pattern,str) or "\\" in pattern or pattern.startswith("/"):raise WorkflowError("invalid_scope_amendment")
    parts=pattern.split("/")
    if len(parts)<3 or parts[-1]!="**" or any(part in {"",".",".."} for part in parts) or any(any(ch in part for ch in "*?[") for part in parts[:-1]):raise WorkflowError("invalid_scope_amendment")
    if pattern not in validated:validated.append(pattern)
   if not validated:raise WorkflowError("invalid_scope_amendment")
   internal=s.read("internal.json") if s._path("internal.json").exists() else {}
   prior=internal.get("scope_amendment_intent")
   replay_keys={"operation":"amend_scope","attempt":run["attempt"],"expected_revision":expected_revision,"expected_head":expected_head,"added_scope":validated,"reason":reason.strip(),"actor":actor.record()}
   if isinstance(prior,dict) and prior.get("status")=="pending":
    if any(prior.get(key)!=value for key,value in replay_keys.items()):raise WorkflowError("scope_amendment_stale")
    requested=prior
   else:
    if isinstance(prior,dict) and prior.get("status")=="completed" and all(prior.get(key)==value for key,value in replay_keys.items()) and all(pattern in run["scope"] for pattern in validated):return run
    if run["revision"]!=expected_revision or run["head_sha"]!=expected_head:raise WorkflowError("scope_amendment_stale")
    normalized=[pattern for pattern in validated if pattern not in run["scope"]]
    if not normalized:raise WorkflowError("invalid_scope_amendment")
    requested={**replay_keys,"status":"pending","id":"scope-amendment-"+uuid.uuid4().hex,"old_scope":list(run["scope"]),"added_scope":normalized}
    internal["scope_amendment_intent"]=requested;RunStore._atomic(s._path("internal.json"),internal)
   missing=[pattern for pattern in requested["added_scope"] if pattern not in run["scope"]]
   if missing:run["scope"].extend(missing);self._bump(s,run)
   audit=s.read("scope-amendments.json") if s._path("scope-amendments.json").exists() else {"amendments":[]}
   if not any(item.get("id")==requested["id"] for item in audit.get("amendments",[])):
    audit.setdefault("amendments",[]).append({**requested,"status":"completed","created_at":now(),"new_scope":list(run["scope"])});RunStore._atomic(s._path("scope-amendments.json"),audit)
   internal=s.read("internal.json");internal["scope_amendment_intent"]={**requested,"status":"completed"};RunStore._atomic(s._path("internal.json"),internal)
   return run
 def repair(self,rid:str,actor:ActorContext,board:KanbanAdapter|None=None)->dict[str,Any]:
  """Archive an attempt and create a fresh, independently bound task graph."""
  s=self._store(rid)
  with s.locked():
   run=s.read()
   recovery_stage="spec-review" if actor.task_id==run["kanban_task_ids"].get("spec-review") else "quality-review"
   self._actor(run,actor,recovery_stage)
   if run["status"]!="repairing" or run["stage_statuses"].get(recovery_stage)!="blocked":raise WorkflowError("repair_not_authorized")
   internal=s.read("internal.json") if s._path("internal.json").exists() else {}
   prior=internal.get("repair_intent")
   published_context=s.read("repair-context.json") if s._path("repair-context.json").exists() else None
   if isinstance(prior,dict) and prior.get("status")=="graph_created" and prior.get("attempt")==run.get("attempt") and _valid_repair_context(published_context,run,internal):
    prior["status"]="completed";internal["repair_intent"]=prior;RunStore._atomic(s._path("internal.json"),internal)
   existing_context=published_context
   reviews=s.read("reviews.json").get("reviews",[]) if s._path("reviews.json").exists() else []
   source_review=next((item for item in reversed(reviews) if item.get("decision")=="changes_requested" and item.get("reviewer",{}).get("task_id")==actor.task_id and item.get("reviewed_sha")==run["head_sha"]),None)
   if isinstance(source_review,dict) and not validate_record(source_review):
    repair_context={"schema_version":SCHEMA_VERSION,"kind":"repair_context","from_attempt":run["attempt"],"source_stage":recovery_stage,"review_sha256":full_sha_hash(source_review),"review":source_review}
   elif isinstance(prior,dict) and prior.get("status")!="completed" and isinstance(existing_context,dict) and prior.get("repair_context_sha256")==full_sha_hash(existing_context):
    repair_context=existing_context
   else:raise WorkflowError("repair_not_authorized")
   repair_base_sha=repair_context["review"]["reviewed_sha"]
   if (self.repo/".worktrees").is_symlink() or (self.repo/".hermes").is_symlink():raise WorkflowError("path_scope_violation")
   old=Path(run["worktree_path"]);attempt=run["attempt"]+1;branch=f"hcw/{rid}/attempt-{attempt}";worktree=self.repo/".worktrees"/f"hcw-{rid}-{attempt}"
   if worktree.is_symlink():raise WorkflowError("path_scope_violation")
   k=board or self._boards.get(rid) or KanbanAdapter(self.repo,run["kanban_board"],home=Path(internal["kanban_home"]) if isinstance(internal.get("kanban_home"),str) else None)
   requested={"operation":"repair","status":"pending","from_attempt":run["attempt"],"attempt":attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":repair_base_sha,"board":run["kanban_board"],"repair_context_sha256":full_sha_hash(repair_context)}
   if prior and prior.get("status")!="completed":
    if any(prior.get(key)!=value for key,value in requested.items() if key!="status"):raise WorkflowError("repair_setup_failed")
   else:
    internal["repair_intent"]=requested;RunStore._atomic(s._path("internal.json"),internal)
   RunStore._atomic(s._path("repair-context.json"),repair_context)
   try:
    if worktree.exists():
     top=subprocess.run(["git","-C",str(worktree),"rev-parse","--show-toplevel"],text=True,capture_output=True);head=subprocess.run(["git","-C",str(worktree),"rev-parse","HEAD"],text=True,capture_output=True);checked_branch=subprocess.run(["git","-C",str(worktree),"branch","--show-current"],text=True,capture_output=True)
     if top.returncode or head.returncode or checked_branch.returncode or Path(top.stdout.strip()).resolve()!=worktree.resolve() or head.stdout.strip()!=repair_base_sha or checked_branch.stdout.strip()!=branch:raise WorkflowError("repair_setup_failed")
    else:
     result=subprocess.run(["git","-C",str(self.repo),"worktree","add","-b",branch,str(worktree),repair_base_sha],capture_output=True,text=True)
     if result.returncode:
      branch_head=subprocess.run(["git","-C",str(self.repo),"rev-parse",branch],text=True,capture_output=True)
      if branch_head.returncode or branch_head.stdout.strip()!=repair_base_sha:raise WorkflowError("repair_setup_failed")
      result=subprocess.run(["git","-C",str(self.repo),"worktree","add",str(worktree),branch],capture_output=True,text=True)
     if result.returncode:raise WorkflowError("repair_setup_failed")
    (worktree/".hermes").mkdir(parents=True,exist_ok=True);(worktree/".hermes"/"hcw-run.json").write_text(json.dumps({"schema_version":SCHEMA_VERSION,"run_id":rid,"repo_root":str(self.repo),"worktree_path":str(worktree.resolve())})+"\n")
    prior=s.read("internal.json")["repair_intent"];persisted_tasks=prior.get("task_ids");persisted_hashes=prior.get("brief_hashes")
    if prior.get("status") in {"graph_created","completed"} and isinstance(persisted_tasks,dict) and set(persisted_tasks)==set(STAGES) and all(isinstance(v,str) and v for v in persisted_tasks.values()) and isinstance(persisted_hashes,dict) and set(persisted_hashes)==set(STAGES) and all(isinstance(v,str) and len(v)==64 for v in persisted_hashes.values()):
     tasks=dict(persisted_tasks);brief_hashes=dict(persisted_hashes)
    else:
     tasks=k.graph(rid,branch,worktree.resolve(),PROFILES,attempt=attempt,scope=run["scope"],goal=run["goal"],base_sha=repair_base_sha);brief_hashes={stage:k.last_briefs[stage]["sha256"] for stage in STAGES}
     internal=s.read("internal.json");internal["repair_intent"].update({"status":"graph_created","task_ids":tasks,"brief_hashes":brief_hashes});RunStore._atomic(s._path("internal.json"),internal)
    draft=dict(run);draft.update({"attempt":attempt,"kanban_task_ids":tasks,"dispatches":{stage:{"stage":stage,"task_id":tasks[stage],"profile":PROFILES[stage],"attempt":attempt,"brief_hash":brief_hashes[stage],"session_id":"unavailable","model":"unavailable","provider":"unavailable"} for stage in STAGES}})
    self._attach_plan_briefs(s,draft,k,s.read("plan.json"));self._persist_authoritative_briefs(s,draft)
   except WorkflowError:raise
   except Exception as exc:raise WorkflowError("repair_setup_failed") from exc
   archive=s.root/"attempts"/str(run["attempt"]);archive.mkdir(parents=True,exist_ok=True)
   for name in ("evidence.jsonl","reviews.json","verification.json","handoff.json"):
    source=s._path(name)
    if source.exists():shutil.move(str(source),str(archive/name))
   run["attempt_history"].append({"attempt":run["attempt"],"worktree_path":str(old),"attempt_base_sha":_attempt_base_sha(run),"head_sha":run["head_sha"]});run.update({"attempt":attempt,"branch":branch,"worktree_path":str(worktree.resolve()),"head_sha":repair_base_sha,"attempt_base_sha":repair_base_sha,"kanban_task_ids":tasks,"dispatches":draft["dispatches"],"stage_statuses":{stage:("completed" if stage in {"design","plan"} else "active" if stage=="red" else "pending") for stage in STAGES},"status":"awaiting_red"});self._bump(s,run)
   internal=s.read("internal.json");internal["repair_intent"]["status"]="completed";RunStore._atomic(s._path("internal.json"),internal);self._reconcile(s,run);return run
 def force_repair(self,rid:str,actor:ActorContext,stage:str,board:KanbanAdapter|None=None)->dict[str,Any]:
  """Operator recovery: create a new attempt when all MAX_WORKER_ATTEMPTS for the active stage are terminal failed and no succeeded worker exists."""
  if stage not in {"red","green"}:raise WorkflowError("force_repair_not_authorized")
  s=self._store(rid)
  with s.locked():
   run=s.read()
   self._actor(run,actor,stage)
   stage_status_map={"red":"awaiting_red","green":"awaiting_green"}
   if run["status"]!=stage_status_map[stage] or run["stage_statuses"].get(stage)!="active":raise WorkflowError("force_repair_not_authorized")
   attempt=run["attempt"]
   latest=s.latest_worker_attempt(stage,attempt)
   if not latest or latest<MAX_WORKER_ATTEMPTS:raise WorkflowError("force_repair_not_authorized")
   for wa in range(1,latest+1):
    rec=s.read_worker(stage,attempt,wa)
    if rec is None or rec.get("state")!="failed":raise WorkflowError("force_repair_not_authorized")
   internal=s.read("internal.json") if s._path("internal.json").exists() else {}
   existing_context=s.read("repair-context.json") if s._path("repair-context.json").exists() else None
   if not _valid_repair_context(existing_context,run,internal):raise WorkflowError("force_repair_not_authorized")
   source_review=existing_context["review"] if isinstance(existing_context,dict) else None
   if not isinstance(source_review,dict):raise WorkflowError("force_repair_not_authorized")
   force_base_sha=_attempt_base_sha(run)
   if source_review.get("reviewed_sha")!=force_base_sha:raise WorkflowError("force_repair_not_authorized")
   force_context={"schema_version":SCHEMA_VERSION,"kind":"repair_context","from_attempt":attempt,"source_stage":existing_context.get("source_stage","spec-review"),"review_sha256":full_sha_hash(source_review),"review":source_review}
   if (self.repo/".worktrees").is_symlink() or (self.repo/".hermes").is_symlink():raise WorkflowError("path_scope_violation")
   old=Path(run["worktree_path"]);new_attempt=attempt+1;branch=f"hcw/{rid}/attempt-{new_attempt}";worktree=self.repo/".worktrees"/f"hcw-{rid}-{new_attempt}"
   if worktree.is_symlink():raise WorkflowError("path_scope_violation")
   k=board or self._boards.get(rid) or KanbanAdapter(self.repo,run["kanban_board"],home=Path(internal["kanban_home"]) if isinstance(internal.get("kanban_home"),str) else None)
   force_intent={"operation":"force_repair","status":"pending","from_attempt":attempt,"attempt":new_attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":force_base_sha,"board":run["kanban_board"],"repair_context_sha256":full_sha_hash(force_context)}
   prior_fi=internal.get("force_repair_intent")
   if isinstance(prior_fi,dict) and prior_fi.get("status") not in {"completed",None}:
    if any(prior_fi.get(key)!=value for key,value in force_intent.items() if key!="status"):raise WorkflowError("force_repair_failed")
   else:
    internal["force_repair_intent"]=force_intent;RunStore._atomic(s._path("internal.json"),internal)
   RunStore._atomic(s._path("repair-context.json"),force_context)
   try:
    if worktree.exists():
     top=subprocess.run(["git","-C",str(worktree),"rev-parse","--show-toplevel"],text=True,capture_output=True);whead=subprocess.run(["git","-C",str(worktree),"rev-parse","HEAD"],text=True,capture_output=True);cbranch=subprocess.run(["git","-C",str(worktree),"branch","--show-current"],text=True,capture_output=True)
     if top.returncode or whead.returncode or cbranch.returncode or Path(top.stdout.strip()).resolve()!=worktree.resolve() or whead.stdout.strip()!=force_base_sha or cbranch.stdout.strip()!=branch:raise WorkflowError("force_repair_failed")
    else:
     result=subprocess.run(["git","-C",str(self.repo),"worktree","add","-b",branch,str(worktree),force_base_sha],capture_output=True,text=True)
     if result.returncode:
      bhead=subprocess.run(["git","-C",str(self.repo),"rev-parse",branch],text=True,capture_output=True)
      if bhead.returncode or bhead.stdout.strip()!=force_base_sha:raise WorkflowError("force_repair_failed")
      result=subprocess.run(["git","-C",str(self.repo),"worktree","add",str(worktree),branch],capture_output=True,text=True)
     if result.returncode:raise WorkflowError("force_repair_failed")
    (worktree/".hermes").mkdir(parents=True,exist_ok=True);(worktree/".hermes"/"hcw-run.json").write_text(json.dumps({"schema_version":SCHEMA_VERSION,"run_id":rid,"repo_root":str(self.repo),"worktree_path":str(worktree.resolve())})+"\n")
    pri_int=s.read("internal.json");prior_fi2=pri_int["force_repair_intent"];pt=prior_fi2.get("task_ids");ph=prior_fi2.get("brief_hashes")
    if prior_fi2.get("status") in {"graph_created","completed"} and isinstance(pt,dict) and set(pt)==set(STAGES) and all(isinstance(v,str) and v for v in pt.values()) and isinstance(ph,dict) and set(ph)==set(STAGES) and all(isinstance(v,str) and len(v)==64 for v in ph.values()):
     tasks=dict(pt);brief_hashes=dict(ph)
     if not isinstance(pri_int.get("repair_intent"),dict) or pri_int["repair_intent"].get("attempt")!=new_attempt:
      pri_int["repair_intent"]={"operation":"repair","status":"graph_created","from_attempt":attempt,"attempt":new_attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":force_base_sha,"board":run["kanban_board"],"repair_context_sha256":full_sha_hash(force_context),"task_ids":tasks,"brief_hashes":brief_hashes};RunStore._atomic(s._path("internal.json"),pri_int)
    else:
     tasks=k.graph(rid,branch,worktree.resolve(),PROFILES,attempt=new_attempt,scope=run["scope"],goal=run["goal"],base_sha=force_base_sha);brief_hashes={st:k.last_briefs[st]["sha256"] for st in STAGES}
     internal2=s.read("internal.json");internal2["force_repair_intent"].update({"status":"graph_created","task_ids":tasks,"brief_hashes":brief_hashes})
     internal2["repair_intent"]={"operation":"repair","status":"graph_created","from_attempt":attempt,"attempt":new_attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":force_base_sha,"board":run["kanban_board"],"repair_context_sha256":full_sha_hash(force_context),"task_ids":tasks,"brief_hashes":brief_hashes}
     RunStore._atomic(s._path("internal.json"),internal2)
    draft=dict(run);draft.update({"attempt":new_attempt,"kanban_task_ids":tasks,"dispatches":{st:{"stage":st,"task_id":tasks[st],"profile":PROFILES[st],"attempt":new_attempt,"brief_hash":brief_hashes[st],"session_id":"unavailable","model":"unavailable","provider":"unavailable"} for st in STAGES}})
    self._attach_plan_briefs(s,draft,k,s.read("plan.json"));self._persist_authoritative_briefs(s,draft)
   except WorkflowError:raise
   except Exception as exc:raise WorkflowError("force_repair_failed") from exc
   archive=s.root/"attempts"/str(attempt);archive.mkdir(parents=True,exist_ok=True)
   for name in ("evidence.jsonl","reviews.json","verification.json","handoff.json"):
    src=s._path(name)
    if src.exists():shutil.move(str(src),str(archive/name))
   run["attempt_history"].append({"attempt":attempt,"worktree_path":str(old),"attempt_base_sha":force_base_sha,"head_sha":run["head_sha"]})
   run.update({"attempt":new_attempt,"branch":branch,"worktree_path":str(worktree.resolve()),"head_sha":force_base_sha,"attempt_base_sha":force_base_sha,"kanban_task_ids":tasks,"dispatches":draft["dispatches"],"stage_statuses":{st:("completed" if st in {"design","plan"} else "active" if st=="red" else "pending") for st in STAGES},"status":"awaiting_red"})
   self._bump(s,run)
   internal3=s.read("internal.json")
   internal3["force_repair_intent"]["status"]="completed"
   internal3["repair_intent"]={"operation":"repair","status":"completed","from_attempt":attempt,"attempt":new_attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":force_base_sha,"board":run["kanban_board"],"repair_context_sha256":full_sha_hash(force_context),"task_ids":tasks,"brief_hashes":brief_hashes}
   RunStore._atomic(s._path("internal.json"),internal3)
   self._reconcile(s,run);return run
 def dispatch_worker(self,rid:str,stage:str,*,retry_succeeded:bool=False)->dict[str,Any]:
  """Launch the sole eligible Claude-backed stage as a detached, async worker.

  This is a Hermes control-plane action at the service/CLI layer: unlike
  approve_design/check/commit/review/verify/complete/repair, it takes no
  `ActorContext` and performs no `_actor` binding check itself (like `show`,
  it needs none). The Hermes plugin's `pre_tool_call` guard is a separate,
  outer layer that still restricts which terminal-issuing profile session
  may invoke this at all: only the profile bound to the target stage while
  that stage is active (see `plugins/hermes-coding-workflow/__init__.py`'s
  `_terminal_allowed`). It never runs Claude synchronously: it reserves a
  durable worker record, spawns a fully-detached `worker_runner` process,
  records that process's real pid, and returns immediately. `worker_runner`
  is the one that blocks on the real `claude` subprocess and atomically
  records the terminal state.
  """
  if stage not in CLAUDE_STAGES:raise WorkflowError("unsupported_claude_stage")
  s=self._store(rid)
  with s.locked():
   run=s.read()
   if validate_record(run):raise WorkflowError("malformed_run_state")
   if run["stage_statuses"].get(stage)!="active":raise WorkflowError("stage_not_active")
   if run["stage_profiles"].get(stage)!=PROFILES[stage]:raise WorkflowError("task_profile_mismatch")
   attempt=run["attempt"]
   task_id=run["kanban_task_ids"].get(stage);dispatch=run["dispatches"].get(stage) or {};brief_hash=dispatch.get("brief_hash")
   if not task_id or not brief_hash:raise WorkflowError("malformed_run_state")
   if dispatch.get("task_id")!=task_id or dispatch.get("profile")!=PROFILES[stage] or dispatch.get("attempt")!=attempt:raise WorkflowError("dispatch_identity_mismatch")
   internal=s.read("internal.json") if s._path("internal.json").exists() else {}
   intent=_authoritative_intent(internal,attempt)
   intent_tasks=intent.get("task_ids") if isinstance(intent,dict) else None;intent_hashes=intent.get("brief_hashes") if isinstance(intent,dict) else None
   if not isinstance(intent_tasks,dict) or intent_tasks.get(stage)!=task_id or not isinstance(intent_hashes,dict) or intent_hashes.get(stage)!=brief_hash:raise WorkflowError("dispatch_identity_mismatch")
   try:worktree=validate_controlled_worktree(self.repo,run["worktree_path"],run_id=rid,attempt=attempt,expected_branch=run["branch"])
   except ValueError as exc:raise WorkflowError(str(exc)) from exc
   latest=s.latest_worker_attempt(stage,attempt)
   if latest:
    previous=s.read_worker(stage,attempt,latest)
    if previous and previous.get("state")=="succeeded":
     if not retry_succeeded:return self._require_succeeded_worker(s,run,stage)
     self._require_succeeded_worker(s,run,stage)
     if stage not in {"red","green"}:raise WorkflowError("worker_retry_not_authorized")
     authorization=(internal.get("worker_retry_authorizations") or {}).get(stage)
     current_head=GitAdapter(worktree).head()
     if not isinstance(authorization,dict) or authorization.get("attempt")!=attempt or authorization.get("worker_id")!=previous.get("id") or authorization.get("head_sha")!=current_head or authorization.get("consumed_at") is not None:raise WorkflowError("worker_retry_not_authorized")
     authorization["consumed_at"]=now();authorization["retry_worker_attempt"]=latest+1;RunStore._atomic(s._path("internal.json"),internal)
    if previous and previous["state"] in {"queued","running"} and _worker_process_alive(previous):
     raise WorkflowError("worker_dispatch_in_progress")
    if previous and previous["state"] in {"queued","running"}:
     stale=dict(previous);stale.update(state="failed",note="stale_process_lost",updated_at=now());s.write_worker(stage,attempt,latest,stale)
    if latest>=MAX_WORKER_ATTEMPTS:raise WorkflowError("worker_retry_exhausted")
   worker_attempt=latest+1;stamp=now()
   design_sha256=full_sha_hash(s.read("approved-design.json"));plan_sha256=full_sha_hash(s.read("plan.json"))
   repair_context=s.read("repair-context.json") if s._path("repair-context.json").exists() else None
   if not _valid_repair_context(repair_context,run,internal):raise WorkflowError("repair_context_invalid")
   dispatch_sha256=full_sha_hash({"run_id":rid,"stage":stage,"task_id":task_id,"profile":PROFILES[stage],"attempt":attempt,"brief_hash":brief_hash})
   record={"schema_version":SCHEMA_VERSION,"kind":"worker","id":f"worker-{rid}-{stage}-{attempt}-{worker_attempt}","created_at":stamp,"updated_at":stamp,"run_id":rid,"stage":stage,"task_id":task_id,"profile":PROFILES[stage],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS[stage],"attempt":attempt,"worker_attempt":worker_attempt,"brief_hash":brief_hash,"worktree_path":str(worktree),"pid":None,"state":"queued","stdout_path":None,"stderr_path":None,"stdout_sha256":None,"stderr_sha256":None,"exit_code":None,"note":None,"design_sha256":design_sha256,"plan_sha256":plan_sha256,"dispatch_sha256":dispatch_sha256,"repair_context_sha256":full_sha_hash(repair_context),"process_identity":None}
   s.write_worker(stage,attempt,worker_attempt,record)
   runner_env=dict(os.environ);runner_env["PYTHONPATH"]=_runner_pythonpath(runner_env.get("PYTHONPATH"))
   log=s.worker_dir()/f"{stage}-{attempt}-{worker_attempt}.runner-log"
   try:
    debug_fd=_open_runner_log_fd(log)
   except (OSError,ValueError) as exc:
    failed=dict(record);failed.update(state="failed",note="runner_log_symlink_rejected",updated_at=now());s.write_worker(stage,attempt,worker_attempt,failed)
    raise WorkflowError("runner_log_symlink_rejected") from exc
   runner_argv=[sys.executable,"-m","hermes_coding_workflow.worker_runner",str(self.repo),rid,stage,str(attempt),str(worker_attempt)]
   try:
    with os.fdopen(debug_fd,"wb") as debug:
     proc=subprocess.Popen(runner_argv,cwd=str(self.repo),env=runner_env,stdin=subprocess.DEVNULL,stdout=debug,stderr=debug,start_new_session=True,close_fds=True)
   except BaseException:
    failed=dict(record);failed.update(state="failed",note="runner_launch_failed",updated_at=now());s.write_worker(stage,attempt,worker_attempt,failed)
    raise
   # The expected argv suffix is computed deterministically -- never taken
   # from an observed `ps` snapshot -- because some Python distributions
   # `execve` themselves into a different interpreter path moments after
   # starting (see `process.matches_identity`); only the start time actually
   # needs to be observed.
   snapshot=process.capture_snapshot_with_retry(proc.pid)
   identity={"args_suffix":" ".join(runner_argv[1:]),"start":snapshot.start} if snapshot else None
   record=dict(record);record.update(pid=proc.pid,process_identity=identity,updated_at=now());s.write_worker(stage,attempt,worker_attempt,record)
   return record
 def worker_status(self,rid:str,stage:str)->dict[str,Any]:
  s=self._store(rid)
  with s.locked():
   run=s.read();attempt=run["attempt"];latest=s.latest_worker_attempt(stage,attempt)
   if not latest:raise WorkflowError("worker_not_dispatched")
   record=s.read_worker(stage,attempt,latest)
   if record is None:raise WorkflowError("worker_not_dispatched")
   if record["state"] in {"queued","running"} and not _worker_process_alive(record):
    record=dict(record);record.update(state="failed",note="stale_process_lost",updated_at=now());s.write_worker(stage,attempt,latest,record)
   return record
