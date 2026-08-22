"""TDD: per-attempt repair baseline (attempt_base_sha) — must FAIL before implementation."""
from __future__ import annotations
import hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
import pytest
from hermes_coding_workflow.contracts import CLAUDE_BACKEND,CLAUDE_TIER_MODELS,PROFILES,SCHEMA_VERSION
from hermes_coding_workflow.service import ActorContext,WorkflowError,WorkflowService,_valid_repair_context,full_sha_hash
from hermes_coding_workflow.store import RunStore

ROOT=Path(__file__).resolve().parents[2]

def git(repo:Path,*args:str)->str:
 return subprocess.check_output(["git","-C",str(repo),*args],text=True).strip()

@pytest.fixture()
def repo(tmp_path:Path)->Path:
 subprocess.run(["git","init",str(tmp_path)],check=True,capture_output=True)
 git(tmp_path,"config","user.email","a@b.invalid");git(tmp_path,"config","user.name","t")
 (tmp_path/"app.txt").write_text("old\n");git(tmp_path,"add",".");git(tmp_path,"commit","-m","base")
 return tmp_path

def act(stage:str)->ActorContext:return ActorContext(PROFILES[stage],"task-"+stage)

def payloads():
 cmd=[sys.executable,"-c","import pathlib;raise SystemExit(0 if pathlib.Path('app.txt').read_text()=='new\\n' else 1)"]
 return({"observable_outcome":"new behavior","requirements":[{"id":"R1","description":"change app"}],"acceptance_criteria":["green"],"approved":True},{"tasks":[{"id":"one","description":"change it","paths":["app.txt"],"test_command":cmd,"requirement_ids":["R1"]}],"commands":{"red":{"argv":cmd,"requirement_ids":["R1"]},"green":{"argv":cmd,"requirement_ids":["R1"]},"full":{"argv":[sys.executable,"-c","pass"],"requirement_ids":["R1"]},"security":{"argv":[sys.executable,"-c","pass"],"requirement_ids":["R1"]},"live":{"argv":[sys.executable,"-c","pass"],"requirement_ids":["R1"]}},"approved":True})

def board(repo:Path,calls:list,home:Path|None=None):
 from hermes_coding_workflow.adapters import KanbanAdapter
 statuses:dict[str,str]={}
 def run_cmd(argv,cwd):
  calls.append(tuple(argv))
  if "create" in argv:
   stage=argv[argv.index("create")+1].split(": ")[-1];ident="task-"+stage;statuses[ident]="todo"
   return subprocess.CompletedProcess(argv,0,json.dumps({"id":ident}) if "--json" in argv else "","")
  if "show" in argv:
   ident=argv[argv.index("show")+1];return subprocess.CompletedProcess(argv,0,json.dumps({"task":{"id":ident,"status":statuses.get(ident,"todo")}}),"")
  if "promote" in argv:statuses[argv[argv.index("promote")+1]]="ready";return subprocess.CompletedProcess(argv,0,"","")
  if "complete" in argv:statuses[argv[argv.index("complete")+1]]="done"
  return subprocess.CompletedProcess(argv,0,"","")
 return KanbanAdapter(repo,"hcw-test",run_cmd,home=home)

def seed_worker_success(repo:Path,stage:str)->dict:
 store=RunStore(repo,"run-1");run=store.read();attempt=run["attempt"]
 worker_attempt=store.latest_worker_attempt(stage,attempt)+1;dispatch=run["dispatches"][stage]
 artifact_root=store.root/"artifacts";artifact_root.mkdir(exist_ok=True)
 stdout=artifact_root/f"{stage}-{attempt}-{worker_attempt}.stdout";stderr=artifact_root/f"{stage}-{attempt}-{worker_attempt}.stderr"
 stdout.write_text("fixture success\n");stderr.write_text("");stamp="2026-08-22T00:00:00Z"
 rel_stdout=str(stdout.relative_to(repo));rel_stderr=str(stderr.relative_to(repo))
 rc=store.read("repair-context.json") if store._path("repair-context.json").exists() else None
 record={"schema_version":"hcw/v1","kind":"worker","id":f"worker-run-1-{stage}-{attempt}-{worker_attempt}","created_at":stamp,"updated_at":stamp,"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS[stage],"attempt":attempt,"worker_attempt":worker_attempt,"brief_hash":dispatch["brief_hash"],"worktree_path":run["worktree_path"],"pid":None,"state":"succeeded","stdout_path":rel_stdout,"stderr_path":rel_stderr,"stdout_sha256":hashlib.sha256(stdout.read_bytes()).hexdigest(),"stderr_sha256":hashlib.sha256(stderr.read_bytes()).hexdigest(),"exit_code":0,"note":None,"design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"attempt":attempt,"brief_hash":dispatch["brief_hash"]}),"repair_context_sha256":full_sha_hash(rc) if rc else None,"process_identity":None}
 store.write_worker(stage,attempt,worker_attempt,record);return record

def seed_failed_worker(repo:Path,stage:str)->dict:
 """Seed a terminal-failed worker (no artifacts, valid schema)."""
 store=RunStore(repo,"run-1");run=store.read();attempt=run["attempt"]
 worker_attempt=store.latest_worker_attempt(stage,attempt)+1;dispatch=run["dispatches"][stage];stamp="2026-08-22T00:00:00Z"
 rc=store.read("repair-context.json") if store._path("repair-context.json").exists() else None
 record={"schema_version":"hcw/v1","kind":"worker","id":f"worker-run-1-{stage}-{attempt}-{worker_attempt}","created_at":stamp,"updated_at":stamp,"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS[stage],"attempt":attempt,"worker_attempt":worker_attempt,"brief_hash":dispatch["brief_hash"],"worktree_path":run["worktree_path"],"pid":None,"state":"failed","stdout_path":None,"stderr_path":None,"stdout_sha256":None,"stderr_sha256":None,"exit_code":1,"note":"forced_failure","design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"attempt":attempt,"brief_hash":dispatch["brief_hash"]}),"repair_context_sha256":full_sha_hash(rc) if rc else None,"process_identity":None}
 store.write_worker(stage,attempt,worker_attempt,record);return record

def ready(repo:Path):
 calls=[];s=WorkflowService(repo);run=s.create_run("pkg",["app.txt"],"run-1","hcw-test",board(repo,calls))
 d,p=payloads();s.approve_design("run-1",act("design"),d);s.approve_plan("run-1",act("plan"),p)
 return s,run,calls

def _do_attempt1_through_review(repo:Path):
 """Complete attempt 1 RED→commit→GREEN then submit changes_requested review. Returns (svc, attempt1_run, candidate_sha)."""
 s,run,_=ready(repo);plan=payloads()[1];worktree=Path(run["worktree_path"])
 seed_worker_success(repo,"red");s.check("run-1",act("red"),"red",plan["commands"]["red"]["argv"])
 (worktree/"app.txt").write_text("new\n");seed_worker_success(repo,"green")
 s.commit("run-1",act("green"),"implement fix");s.check("run-1",act("green"),"green",plan["commands"]["green"]["argv"])
 candidate_sha=git(worktree,"rev-parse","HEAD")
 assert candidate_sha!=run["base_sha"],"test requires a commit to have happened"
 finding={"id":"F1","severity":"blocker","description":"repair required"}
 s.review("run-1",act("spec-review"),{"reviewed_sha":candidate_sha,"decision":"changes_requested","findings":[finding],"dispositions":[{"finding_id":"F1","disposition":"accepted"}]})
 return s,run,candidate_sha


# ── 1. create_run must initialize attempt_base_sha ────────────────────────────

def test_create_run_initializes_attempt_base_sha_equal_to_base_sha(repo:Path)->None:
 s,run,_=ready(repo)
 store=RunStore(repo,"run-1");saved=store.read()
 assert "attempt_base_sha" in saved,"create_run must set attempt_base_sha"
 assert saved["attempt_base_sha"]==saved["base_sha"]


# ── 2. repair() must start the new worktree at the reviewed candidate ─────────

def test_repair_starts_worktree_at_reviewed_candidate_not_original_base(repo:Path)->None:
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 repaired=s.repair("run-1",act("spec-review"),board(repo,[]))
 worktree2=Path(repaired["worktree_path"])
 head2=git(worktree2,"rev-parse","HEAD")
 assert head2==candidate_sha,f"attempt-2 worktree must start at candidate {candidate_sha[:8]}, got {head2[:8]}"


# ── 3. base_sha immutable + attempt_base_sha set to candidate ─────────────────

def test_base_sha_preserved_and_attempt_base_sha_set_after_repair(repo:Path)->None:
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 original_base=run["base_sha"]
 repaired=s.repair("run-1",act("spec-review"),board(repo,[]))
 assert repaired["base_sha"]==original_base,"base_sha must be immutable provenance anchor"
 assert repaired.get("attempt_base_sha")==candidate_sha,"attempt_base_sha must equal reviewed candidate"


# ── 4. attempt_history entry must include attempt_base_sha ───────────────────

def test_attempt_history_entry_includes_attempt_base_sha(repo:Path)->None:
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 original_base=run["base_sha"]
 repaired=s.repair("run-1",act("spec-review"),board(repo,[]))
 history=repaired["attempt_history"]
 assert len(history)==1
 entry=history[0]
 assert "attempt_base_sha" in entry,f"attempt_history entry must include attempt_base_sha, got keys: {set(entry)}"
 assert entry["attempt_base_sha"]==original_base,"attempt 1 started at original base"
 assert entry["head_sha"]==candidate_sha,"attempt 1 ended at candidate"


# ── 5. validate_record must accept run with attempt_base_sha ─────────────────

def test_validate_record_accepts_run_with_attempt_base_sha(repo:Path)->None:
 from hermes_coding_workflow.contracts import validate_record
 s,run,_=ready(repo);store=RunStore(repo,"run-1");saved=dict(store.read())
 saved["attempt_base_sha"]=saved["base_sha"]
 assert validate_record(saved) is None,"validate_record must accept run with attempt_base_sha"


# ── 6. validate_record must accept legacy run WITHOUT attempt_base_sha ────────
# (backward-compat: validator must accept old records that predate attempt_base_sha)

def test_validate_record_accepts_legacy_run_without_attempt_base_sha(repo:Path)->None:
 from hermes_coding_workflow.contracts import validate_record
 s,run,_=ready(repo);store=RunStore(repo,"run-1");saved=dict(store.read())
 saved.pop("attempt_base_sha",None)  # simulate a legacy record created before this feature
 assert "attempt_base_sha" not in saved
 assert validate_record(saved) is None,"legacy run without attempt_base_sha must remain valid"


# ── 7. validate_record must reject malformed attempt_history entries ──────────

def test_validate_record_rejects_malformed_attempt_history_entries(repo:Path)->None:
 from hermes_coding_workflow.contracts import validate_record
 s,run,_=ready(repo);store=RunStore(repo,"run-1")
 def check_bad_history(history):
  saved=dict(store.read());saved["attempt_history"]=history
  return validate_record(saved)
 assert check_bad_history([{"attempt":0,"worktree_path":"/tmp/x","head_sha":"a"*40}])=="malformed_schema","attempt<1 invalid"
 assert check_bad_history([{"attempt":1,"worktree_path":"","head_sha":"a"*40}])=="malformed_schema","empty worktree_path invalid"
 assert check_bad_history([{"attempt":1,"worktree_path":"/tmp/x","head_sha":"short"}])=="malformed_schema","bad head_sha invalid"
 assert check_bad_history([{"attempt":1,"worktree_path":"/tmp/x","head_sha":"a"*40,"attempt_base_sha":"bad"}])=="malformed_schema","bad attempt_base_sha invalid"


# ── 8. native _verified_red must check attempt_base_sha not only base_sha ─────

def test_native_verified_red_uses_attempt_base_sha(repo:Path)->None:
 spec=importlib.util.spec_from_file_location("hcw_plugin",ROOT/"plugins"/"hermes-coding-workflow"/"__init__.py")
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 attempt_base="b"*40;original_base=git(repo,"rev-parse","HEAD")
 ev_dir=repo/".hermes"/"workflows"/"run-1";ev_dir.mkdir(parents=True,exist_ok=True)
 ev={"schema_version":SCHEMA_VERSION,"kind":"evidence","id":"EV-1","created_at":"2026-08-22T00:00:00Z","run_id":"run-1","type":"red","actor":{"profile":"dev-contract","task_id":"task-red"},"commit_sha":attempt_base,"command":["python","-c","pass"],"exit_code":1,"artifact_path":"artifacts/red.log","artifact_sha256":"a"*64,"previous_evidence_hash":None}
 ev["evidence_hash"]=hashlib.sha256(json.dumps(ev,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 (ev_dir/"evidence.jsonl").write_text(json.dumps(ev)+"\n")
 run_data={"id":"run-1","base_sha":original_base,"attempt_base_sha":attempt_base,"repo_root":str(repo)}
 assert mod._verified_red(run_data)==True,"RED evidence at attempt_base_sha must unlock GREEN"
 run_legacy={"id":"run-1","base_sha":original_base,"repo_root":str(repo)}
 assert mod._verified_red(run_legacy)==False,"legacy run: RED at attempt_base≠base_sha must fail (not at base)"


# ── 9. _valid_repair_context must reject when intent base != reviewed_sha ──────

def test_repair_context_rejects_intent_base_mismatch(repo:Path)->None:
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 store=RunStore(repo,"run-1")
 reviewer=act("spec-review").record()
 review={"schema_version":SCHEMA_VERSION,"kind":"review","id":"RV-test","created_at":"2026-08-22T00:00:00Z","run_id":"run-1","reviewer":reviewer,"reviewed_sha":candidate_sha,"decision":"changes_requested","findings":[{"id":"F1","severity":"blocker","description":"test"}],"dispositions":[{"finding_id":"F1","disposition":"accepted"}]}
 ctx={"schema_version":SCHEMA_VERSION,"kind":"repair_context","from_attempt":1,"source_stage":"spec-review","review_sha256":full_sha_hash(review),"review":review}
 state=store.read();state["attempt"]=2;state["attempt_history"]=[{"attempt":1,"worktree_path":state["worktree_path"],"head_sha":candidate_sha}]
 RunStore._atomic(store._path("run.json"),state)
 internal={"repair_intent":{"operation":"repair","status":"completed","from_attempt":1,"attempt":2,"base_sha":run["base_sha"],"repair_context_sha256":full_sha_hash(ctx),"branch":"hcw/run-1/attempt-2","worktree_path":"/tmp/fake","board":"hcw-test"}}
 RunStore._atomic(store._path("internal.json"),internal)
 # intent.base_sha == original_base != candidate_sha == review.reviewed_sha → must reject
 result=_valid_repair_context(ctx,state,internal)
 assert result==False,"must reject when intent base_sha != review reviewed_sha"


# ── 10. force_repair creates new attempt from exhausted workers ───────────────

def test_force_repair_creates_attempt_from_exhausted_workers(repo:Path)->None:
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 repaired=s.repair("run-1",act("spec-review"),board(repo,[]))
 assert repaired["attempt"]==2
 # Exhaust all 3 RED workers in attempt 2
 for _ in range(3):seed_failed_worker(repo,"red")
 with pytest.raises(WorkflowError,match="worker_retry_exhausted"):
  s.dispatch_worker("run-1","red")
 # force_repair should create attempt 3
 attempt3=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert attempt3["attempt"]==3,"force_repair must create attempt 3"
 assert attempt3["base_sha"]==run["base_sha"],"base_sha must remain immutable original provenance"
 assert attempt3.get("attempt_base_sha")==candidate_sha,"attempt 3 must start at same candidate as attempt 2"
