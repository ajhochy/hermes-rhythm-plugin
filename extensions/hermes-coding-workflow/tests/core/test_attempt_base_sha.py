"""TDD: per-attempt repair baseline (attempt_base_sha) — must FAIL before implementation."""
from __future__ import annotations
import hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
import pytest
from hermes_coding_workflow.contracts import CLAUDE_BACKEND,CLAUDE_TIER_MODELS,PROFILES,SCHEMA_VERSION,validate_record
from hermes_coding_workflow.service import ActorContext,MAX_WORKER_ATTEMPTS,WorkflowError,WorkflowService,_valid_repair_context,full_sha_hash
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
 record={"schema_version":"hcw/v1","kind":"worker","id":f"worker-run-1-{stage}-{attempt}-{worker_attempt}","created_at":stamp,"updated_at":stamp,"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS[stage],"attempt":attempt,"worker_attempt":worker_attempt,"brief_hash":dispatch["brief_hash"],"worktree_path":run["worktree_path"],"pid":None,"state":"failed","stdout_path":None,"stderr_path":None,"stdout_sha256":None,"stderr_sha256":None,"exit_code":1,"note":"forced_failure","design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"attempt":attempt,"brief_hash":dispatch["brief_hash"]}),"repair_context_sha256":full_sha_hash(rc),"process_identity":None}
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


# ── helpers shared by crash-boundary and P2 tests ────────────────────────────

def _setup_attempt2_exhausted(repo:Path):
 """Return (svc, orig_run, candidate_sha) with attempt-2 exhausted (3 failed RED workers)."""
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 s.repair("run-1",act("spec-review"),board(repo,[]))
 for _ in range(MAX_WORKER_ATTEMPTS):seed_failed_worker(repo,"red")
 return s,run,candidate_sha

def _compute_force_context(repo:Path)->tuple[dict,dict,dict,int]:
 """Compute (run, internal, force_context, new_attempt) for the current attempt-2 exhausted state."""
 store=RunStore(repo,"run-1");run=store.read();attempt=run["attempt"]
 internal=store.read("internal.json") if store._path("internal.json").exists() else {}
 existing_ctx=store.read("repair-context.json")
 source_review=existing_ctx["review"];force_base_sha=run.get("attempt_base_sha") or run["base_sha"]
 force_ctx={"schema_version":SCHEMA_VERSION,"kind":"repair_context","from_attempt":attempt,"source_stage":existing_ctx.get("source_stage","spec-review"),"review_sha256":full_sha_hash(source_review),"review":source_review}
 return run,internal,force_ctx,attempt+1


# ── 11. crash at intent boundary — replay succeeds ────────────────────────────

def test_force_repair_crash_at_intent_boundary_is_replayable(repo:Path)->None:
 """Crash after writing force_repair_intent but before writing repair-context.json.
 The old context remains; replay must detect the intent hash mismatch and resume."""
 s,orig_run,candidate_sha=_setup_attempt2_exhausted(repo)
 run,internal,force_ctx,new_attempt=_compute_force_context(repo)
 branch=f"hcw/run-1/attempt-{new_attempt}"
 worktree=repo/".worktrees"/f"hcw-run-1-{new_attempt}"
 force_base_sha=run.get("attempt_base_sha") or run["base_sha"]
 # Simulate crash: write force_repair_intent but NOT repair-context.json
 force_intent={"operation":"force_repair","status":"pending","from_attempt":run["attempt"],"attempt":new_attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":force_base_sha,"board":run["kanban_board"],"repair_context_sha256":full_sha_hash(force_ctx)}
 internal["force_repair_intent"]=force_intent
 RunStore._atomic(RunStore(repo,"run-1")._path("internal.json"),internal)
 # repair-context.json is still the OLD context (not overwritten)
 result=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert result["attempt"]==new_attempt
 assert result["attempt_base_sha"]==candidate_sha


# ── 12. crash at context boundary — replay succeeds (the P1 crash replay bug) ─

def test_force_repair_crash_at_context_boundary_is_replayable(repo:Path)->None:
 """Crash after writing new repair-context.json but before creating worktree.
 The old context is gone; replay must detect the context hash match and skip
 _valid_repair_context (which would fail since repair_intent is still for old attempt)."""
 s,orig_run,candidate_sha=_setup_attempt2_exhausted(repo)
 run,internal,force_ctx,new_attempt=_compute_force_context(repo)
 branch=f"hcw/run-1/attempt-{new_attempt}"
 worktree=repo/".worktrees"/f"hcw-run-1-{new_attempt}"
 force_base_sha=run.get("attempt_base_sha") or run["base_sha"]
 # Simulate crash: write intent AND new repair-context.json, but no worktree
 force_intent={"operation":"force_repair","status":"pending","from_attempt":run["attempt"],"attempt":new_attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":force_base_sha,"board":run["kanban_board"],"repair_context_sha256":full_sha_hash(force_ctx)}
 store=RunStore(repo,"run-1");internal["force_repair_intent"]=force_intent
 RunStore._atomic(store._path("internal.json"),internal)
 RunStore._atomic(store._path("repair-context.json"),force_ctx)  # OLD context overwritten
 result=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert result["attempt"]==new_attempt
 assert result["attempt_base_sha"]==candidate_sha


# ── 13. crash at worktree/graph boundary — replay succeeds ───────────────────

def test_force_repair_crash_at_graph_boundary_is_replayable(repo:Path)->None:
 """Crash after graph creation (force_repair_intent.status='graph_created') but before run.json
 update. Replay must reuse cached tasks and transition run.json correctly."""
 s,orig_run,candidate_sha=_setup_attempt2_exhausted(repo)
 # Run force_repair to completion to get a graph_created state captured mid-way
 attempt3=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert attempt3["attempt"]==3
 # Now simulate the crash-at-graph-boundary for a second force_repair cycle:
 # exhaust attempt-3 workers, then partially write intent+graph_created state
 for _ in range(MAX_WORKER_ATTEMPTS):seed_failed_worker(repo,"red")
 run2,internal2,force_ctx2,new_attempt2=_compute_force_context(repo)
 branch2=f"hcw/run-1/attempt-{new_attempt2}"
 worktree2=repo/".worktrees"/f"hcw-run-1-{new_attempt2}"
 force_base_sha2=run2.get("attempt_base_sha") or run2["base_sha"]
 # Create the worktree manually (simulates graph creation having happened)
 subprocess.run(["git","-C",str(repo),"worktree","add","-b",branch2,str(worktree2),force_base_sha2],check=True,capture_output=True)
 (worktree2/".hermes").mkdir(parents=True,exist_ok=True)
 (worktree2/".hermes"/"hcw-run.json").write_text(json.dumps({"schema_version":SCHEMA_VERSION,"run_id":"run-1","repo_root":str(repo),"worktree_path":str(worktree2.resolve())})+"\n")
 store2=RunStore(repo,"run-1")
 # Write graph_created intent with dummy tasks (force_repair will reuse them)
 tasks={st:"task-"+st for st in ["design","plan","red","green","spec-review","quality-review","verify","live","complete"]}
 brief_hashes={st:"a"*64 for st in tasks}
 force_ctx_sha=full_sha_hash(force_ctx2)
 force_intent2={"operation":"force_repair","status":"graph_created","from_attempt":run2["attempt"],"attempt":new_attempt2,"branch":branch2,"worktree_path":str(worktree2),"base_sha":force_base_sha2,"board":run2["kanban_board"],"repair_context_sha256":force_ctx_sha,"task_ids":tasks,"brief_hashes":brief_hashes}
 repair_intent2={"operation":"repair","status":"graph_created","from_attempt":run2["attempt"],"attempt":new_attempt2,"branch":branch2,"worktree_path":str(worktree2),"base_sha":force_base_sha2,"board":run2["kanban_board"],"repair_context_sha256":force_ctx_sha,"task_ids":tasks,"brief_hashes":brief_hashes}
 internal2["force_repair_intent"]=force_intent2;internal2["repair_intent"]=repair_intent2
 RunStore._atomic(store2._path("internal.json"),internal2)
 RunStore._atomic(store2._path("repair-context.json"),force_ctx2)
 # run.json is still at attempt 3 (not yet bumped)
 result=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert result["attempt"]==new_attempt2,"replay must advance to the correct new attempt"
 assert result["attempt_base_sha"]==candidate_sha


# ── 14. crash at run-finalization — state is already correct ─────────────────

def test_force_repair_crash_at_run_finalization_leaves_correct_state(repo:Path)->None:
 """Crash after run.json is updated but before force_repair_intent.status='completed'.
 Calling force_repair again must fail (run is already at new attempt with 0 workers);
 the run is in the correct awaiting_red state for dispatch_worker."""
 s,orig_run,candidate_sha=_setup_attempt2_exhausted(repo)
 attempt3=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert attempt3["attempt"]==3
 # Simulate incomplete finalization: reset force_repair_intent to graph_created
 store=RunStore(repo,"run-1");internal=store.read("internal.json")
 internal["force_repair_intent"]["status"]="graph_created"
 RunStore._atomic(store._path("internal.json"),internal)
 # Calling force_repair again must fail — run is already at attempt 3, no workers yet
 with pytest.raises(WorkflowError,match="force_repair_not_authorized"):
  s.force_repair("run-1",act("red"),"red",board(repo,[]))
 # Run must be in valid awaiting_red state at attempt 3
 run_final=store.read()
 assert run_final["attempt"]==3 and run_final["status"]=="awaiting_red"
 # repair_intent for attempt 3 must be valid (dispatch_worker can proceed)
 internal_final=store.read("internal.json")
 assert internal_final.get("repair_intent",{}).get("attempt")==3


# ── 15. P2 exact ceiling: >=MAX rejected, <MAX rejected ──────────────────────

def test_force_repair_requires_exactly_max_worker_attempts(repo:Path)->None:
 """force_repair must require latest==MAX_WORKER_ATTEMPTS, reject over- and under-limit."""
 s,orig_run,candidate_sha=_do_attempt1_through_review(repo)
 s.repair("run-1",act("spec-review"),board(repo,[]))
 # Under-limit: only MAX-1 failed workers
 for _ in range(MAX_WORKER_ATTEMPTS-1):seed_failed_worker(repo,"red")
 with pytest.raises(WorkflowError,match="force_repair_not_authorized"):
  s.force_repair("run-1",act("red"),"red",board(repo,[]))
 # Exactly MAX: should pass
 seed_failed_worker(repo,"red")
 result=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert result["attempt"]==3
 # Over-limit: seed one more failed worker on attempt 3, now latest==1 not MAX
 # Actually, test that if we had 4 workers for some attempt, force_repair rejects.
 # We test this via the existing run's workers: after force_repair, attempt is 3.
 # Seed MAX+1 workers for attempt 3 to create an over-limit scenario.
 for _ in range(MAX_WORKER_ATTEMPTS):seed_failed_worker(repo,"red")  # workers 1..3 for attempt 3
 # Add a 4th worker directly via store (simulating over-limit scenario)
 store=RunStore(repo,"run-1");run3=store.read();dispatch3=run3["dispatches"]["red"]
 rc3=store.read("repair-context.json") if store._path("repair-context.json").exists() else None
 extra={"schema_version":"hcw/v1","kind":"worker","id":"worker-run-1-red-3-4","created_at":"2026-08-22T00:00:00Z","updated_at":"2026-08-22T00:00:00Z","run_id":"run-1","stage":"red","task_id":run3["kanban_task_ids"]["red"],"profile":PROFILES["red"],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS["red"],"attempt":3,"worker_attempt":4,"brief_hash":dispatch3["brief_hash"],"worktree_path":run3["worktree_path"],"pid":None,"state":"failed","stdout_path":None,"stderr_path":None,"stdout_sha256":None,"stderr_sha256":None,"exit_code":1,"note":"over_limit","design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":"red","task_id":run3["kanban_task_ids"]["red"],"profile":PROFILES["red"],"attempt":3,"brief_hash":dispatch3["brief_hash"]}),"repair_context_sha256":full_sha_hash(rc3) if rc3 else None,"process_identity":None}
 store.write_worker("red",3,4,extra)
 with pytest.raises(WorkflowError,match="force_repair_not_authorized"):
  s.force_repair("run-1",act("red"),"red",board(repo,[]))


# ── 16. P2 exact ceiling: missing, queued, running, succeeded workers rejected ─

@pytest.mark.parametrize("bad_state", ["queued","running","succeeded",None])
def test_force_repair_rejects_non_failed_and_missing_worker_records(repo:Path,bad_state:str|None)->None:
 """All MAX worker records must exist, be schema-valid, and be terminal failed."""
 s,_,_=_do_attempt1_through_review(repo)
 s.repair("run-1",act("spec-review"),board(repo,[]))
 # Seed MAX-1 correct failed workers
 for _ in range(MAX_WORKER_ATTEMPTS-1):seed_failed_worker(repo,"red")
 if bad_state is None:
  # missing record: just don't seed the last one
  pass
 else:
  # Seed a worker with the bad state
  store=RunStore(repo,"run-1");run=store.read();attempt=run["attempt"]
  dispatch=run["dispatches"]["red"];wa=MAX_WORKER_ATTEMPTS;stamp="2026-08-22T00:00:00Z"
  rc=store.read("repair-context.json") if store._path("repair-context.json").exists() else None
  record={"schema_version":"hcw/v1","kind":"worker","id":f"worker-run-1-red-{attempt}-{wa}","created_at":stamp,"updated_at":stamp,"run_id":"run-1","stage":"red","task_id":run["kanban_task_ids"]["red"],"profile":PROFILES["red"],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS["red"],"attempt":attempt,"worker_attempt":wa,"brief_hash":dispatch["brief_hash"],"worktree_path":run["worktree_path"],"pid":None,"state":bad_state,"stdout_path":None,"stderr_path":None,"stdout_sha256":None,"stderr_sha256":None,"exit_code":None,"note":None,"design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":"red","task_id":run["kanban_task_ids"]["red"],"profile":PROFILES["red"],"attempt":attempt,"brief_hash":dispatch["brief_hash"]}),"repair_context_sha256":full_sha_hash(rc) if rc else None,"process_identity":None}
  store.write_worker("red",attempt,wa,record)
 with pytest.raises(WorkflowError,match="force_repair_not_authorized"):
  s.force_repair("run-1",act("red"),"red",board(repo,[]))


# ── 17. P2 exact ceiling: schema-invalid worker record rejected ───────────────

def test_force_repair_rejects_schema_invalid_worker_record(repo:Path)->None:
 """A malformed worker record (fails validate_worker) must block force_repair."""
 s,_,_=_do_attempt1_through_review(repo)
 s.repair("run-1",act("spec-review"),board(repo,[]))
 for _ in range(MAX_WORKER_ATTEMPTS-1):seed_failed_worker(repo,"red")
 store=RunStore(repo,"run-1");run=store.read();attempt=run["attempt"];wa=MAX_WORKER_ATTEMPTS
 # Write a worker with an invalid state value
 rc=store.read("repair-context.json") if store._path("repair-context.json").exists() else None
 dispatch=run["dispatches"]["red"]
 bad={"schema_version":"hcw/v1","kind":"worker","id":f"worker-run-1-red-{attempt}-{wa}","created_at":"2026-08-22T00:00:00Z","updated_at":"2026-08-22T00:00:00Z","run_id":"run-1","stage":"red","task_id":run["kanban_task_ids"]["red"],"profile":PROFILES["red"],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS["red"],"attempt":attempt,"worker_attempt":wa,"brief_hash":dispatch["brief_hash"],"worktree_path":run["worktree_path"],"pid":None,"state":"invalid_state","stdout_path":None,"stderr_path":None,"stdout_sha256":None,"stderr_sha256":None,"exit_code":1,"note":None,"design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":"red","task_id":run["kanban_task_ids"]["red"],"profile":PROFILES["red"],"attempt":attempt,"brief_hash":dispatch["brief_hash"]}),"repair_context_sha256":full_sha_hash(rc) if rc else None,"process_identity":None}
 # Bypass write_worker's validate_record guard to inject the malformed record directly
 RunStore._atomic(store.worker_path("red",attempt,wa),bad)
 with pytest.raises(WorkflowError,match="force_repair_not_authorized"):
  s.force_repair("run-1",act("red"),"red",board(repo,[]))


# ── 18. P2 exact ceiling: wrong binding fields in worker record ───────────────

@pytest.mark.parametrize("bad_field,bad_value",[
 ("run_id","wrong-run"),
 ("stage","green"),
 ("attempt",99),
 ("worker_attempt",99),
 ("task_id","wrong-task"),
 ("profile","wrong-profile"),
])
def test_force_repair_rejects_worker_with_wrong_bindings(repo:Path,bad_field:str,bad_value:object)->None:
 """Worker records with wrong run/attempt/stage/task/profile bindings must be rejected."""
 s,_,_=_do_attempt1_through_review(repo)
 s.repair("run-1",act("spec-review"),board(repo,[]))
 for _ in range(MAX_WORKER_ATTEMPTS-1):seed_failed_worker(repo,"red")
 store=RunStore(repo,"run-1");run=store.read();attempt=run["attempt"];wa=MAX_WORKER_ATTEMPTS
 rc=store.read("repair-context.json") if store._path("repair-context.json").exists() else None
 dispatch=run["dispatches"]["red"]
 correct_attempt=attempt if bad_field!="attempt" else run["attempt"]
 correct_wa=wa if bad_field!="worker_attempt" else wa
 base={"schema_version":"hcw/v1","kind":"worker","id":f"worker-run-1-red-{correct_attempt}-{correct_wa}","created_at":"2026-08-22T00:00:00Z","updated_at":"2026-08-22T00:00:00Z","run_id":"run-1","stage":"red","task_id":run["kanban_task_ids"]["red"],"profile":PROFILES["red"],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS["red"],"attempt":correct_attempt,"worker_attempt":correct_wa,"brief_hash":dispatch["brief_hash"],"worktree_path":run["worktree_path"],"pid":None,"state":"failed","stdout_path":None,"stderr_path":None,"stdout_sha256":None,"stderr_sha256":None,"exit_code":1,"note":None,"design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":"red","task_id":run["kanban_task_ids"]["red"],"profile":PROFILES["red"],"attempt":attempt,"brief_hash":dispatch["brief_hash"]}),"repair_context_sha256":full_sha_hash(rc) if rc else None,"process_identity":None}
 bad={**base,bad_field:bad_value}
 store.write_worker("red",wa,wa,bad)
 with pytest.raises(WorkflowError,match="force_repair_not_authorized"):
  s.force_repair("run-1",act("red"),"red",board(repo,[]))


# ── 19. P2 run relationships: sequential attempt history enforced ─────────────

def test_contracts_reject_attempt_history_wrong_length(repo:Path)->None:
 """validate_record rejects runs where len(attempt_history) != attempt - 1."""
 s,run,_=ready(repo);store=RunStore(repo,"run-1");saved=dict(store.read())
 # attempt=1 with a spurious history entry
 saved["attempt_history"]=[{"attempt":1,"worktree_path":"/tmp/x","head_sha":"a"*40}]
 assert validate_record(saved)=="malformed_schema","extra history entry on attempt=1 must be rejected"
 # attempt=2 with no history
 saved2=dict(store.read());saved2["attempt"]=2;saved2["attempt_history"]=[]
 saved2["dispatches"]={st:{**v,"attempt":2} for st,v in saved2["dispatches"].items()}
 assert validate_record(saved2)=="malformed_schema","empty history on attempt=2 must be rejected"


def test_contracts_reject_nonsequential_attempt_history(repo:Path)->None:
 """validate_record rejects attempt_history with non-sequential or duplicate attempt numbers."""
 s,_,candidate_sha=_do_attempt1_through_review(repo)
 repaired=s.repair("run-1",act("spec-review"),board(repo,[]))
 store=RunStore(repo,"run-1");saved=dict(store.read())
 assert saved["attempt"]==2
 # Replace history with wrong attempt number
 bad_history=[{"attempt":2,"worktree_path":str(Path(saved["worktree_path"]).parent)+"x","head_sha":"b"*40}]
 saved["attempt_history"]=bad_history
 assert validate_record(saved)=="malformed_schema","wrong attempt number in history must be rejected"
 # Duplicate attempt numbers
 dup_history=[{"attempt":1,"worktree_path":"/tmp/a","head_sha":"a"*40},{"attempt":1,"worktree_path":"/tmp/b","head_sha":"b"*40}]
 saved3=dict(store.read());saved3["attempt"]=3;saved3["attempt_history"]=dup_history
 saved3["dispatches"]={st:{**v,"attempt":3} for st,v in saved3["dispatches"].items()}
 assert validate_record(saved3)=="malformed_schema","duplicate attempt numbers must be rejected"


def test_contracts_reject_contradictory_attempt_base_sha_in_history(repo:Path)->None:
 """Populated attempt_base_sha in a history entry must follow the chain rule."""
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 repaired=s.repair("run-1",act("spec-review"),board(repo,[]))
 store=RunStore(repo,"run-1");saved=dict(store.read())
 assert saved["attempt"]==2
 # attempt 1's baseline must equal base_sha — wrong value must be rejected
 saved["attempt_history"][0]["attempt_base_sha"]="c"*40  # wrong: not base_sha
 assert validate_record(saved)=="malformed_schema","wrong attempt_base_sha in history[0] must be rejected"
 # attempt 2's baseline must equal history[0].head_sha — wrong value rejected
 saved2=dict(store.read());saved2["attempt_base_sha"]="d"*40
 assert validate_record(saved2)=="malformed_schema","wrong current run attempt_base_sha must be rejected"


def test_contracts_enforce_attempt1_baseline_equals_base_sha(repo:Path)->None:
 """When attempt=1 and attempt_base_sha is populated, it must equal base_sha."""
 s,run,_=ready(repo);store=RunStore(repo,"run-1");saved=dict(store.read())
 assert saved["attempt"]==1
 # Correct: attempt_base_sha == base_sha
 assert validate_record(saved) is None
 # Wrong: attempt_base_sha != base_sha
 saved["attempt_base_sha"]="e"*40
 assert validate_record(saved)=="malformed_schema","attempt_base_sha != base_sha on attempt=1 must be rejected"


def test_contracts_accept_legacy_history_entries_without_attempt_base_sha(repo:Path)->None:
 """Legacy history entries lacking attempt_base_sha must remain accepted."""
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 repaired=s.repair("run-1",act("spec-review"),board(repo,[]))
 store=RunStore(repo,"run-1");saved=dict(store.read())
 assert saved["attempt"]==2
 # Remove attempt_base_sha from history entry (legacy compatibility)
 saved["attempt_history"][0].pop("attempt_base_sha",None)
 assert validate_record(saved) is None,"legacy history entry without attempt_base_sha must be valid"
 # Remove from current run too
 saved.pop("attempt_base_sha",None)
 assert validate_record(saved) is None,"legacy run without attempt_base_sha must be valid"


# ── P1 RED: attempt-1 force-repair without a review context ──────────────────

def test_force_repair_attempt1_exhaustion_creates_attempt2(repo:Path)->None:
 """RED: force_repair on attempt 1 (no repair-context.json, 3 failed workers)
 must succeed and produce attempt 2.  Currently fails with force_repair_not_authorized."""
 s,run,_=ready(repo)
 assert run["attempt"]==1,"precondition: we are on attempt 1"
 # Exhaust all 3 RED workers on attempt 1 (no repair() has been called)
 for _ in range(MAX_WORKER_ATTEMPTS):seed_failed_worker(repo,"red")
 store=RunStore(repo,"run-1")
 assert store._path("repair-context.json").exists() is False,"precondition: no repair context on attempt 1"
 result=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert result["attempt"]==2,"force_repair on attempt 1 must produce attempt 2"
 assert result["base_sha"]==run["base_sha"],"base_sha must remain immutable"
 assert result.get("attempt_base_sha")==run["base_sha"],"attempt_base_sha must equal base_sha for attempt-1 force-repair"


def test_force_repair_attempt1_repair_intent_accepted_by_dispatch_worker(repo:Path)->None:
 """RED: after attempt-1 force_repair, dispatch_worker must accept the repair_intent
 (i.e. _valid_repair_context passes for the force_repair_context kind)."""
 s,run,_=ready(repo)
 for _ in range(MAX_WORKER_ATTEMPTS):seed_failed_worker(repo,"red")
 s.force_repair("run-1",act("red"),"red",board(repo,[]))
 store=RunStore(repo,"run-1");run2=store.read()
 assert run2["attempt"]==2
 ctx=store.read("repair-context.json")
 internal=store.read("internal.json") if store._path("internal.json").exists() else {}
 # _valid_repair_context must accept the force_repair_context for attempt 2
 from hermes_coding_workflow.service import _valid_repair_context
 assert _valid_repair_context(ctx,run2,internal) is True,"force_repair_context must be valid for attempt 2"


def test_force_repair_attempt1_adversarial_context_mismatch_rejected(repo:Path)->None:
 """RED: after attempt-1 force_repair, _valid_repair_context must reject contexts
 with wrong from_attempt, wrong force_base_sha, wrong kind, or extra fields."""
 s,run,_=ready(repo)
 for _ in range(MAX_WORKER_ATTEMPTS):seed_failed_worker(repo,"red")
 s.force_repair("run-1",act("red"),"red",board(repo,[]))
 store=RunStore(repo,"run-1");run2=store.read()
 internal=store.read("internal.json") if store._path("internal.json").exists() else {}
 ctx=store.read("repair-context.json")
 from hermes_coding_workflow.service import _valid_repair_context
 from hermes_coding_workflow.contracts import SCHEMA_VERSION as SV
 # Wrong from_attempt
 bad_from={**ctx,"from_attempt":99}
 assert _valid_repair_context(bad_from,run2,internal) is False,"wrong from_attempt must be rejected"
 # Wrong force_base_sha
 bad_base={**ctx,"force_base_sha":"e"*40}
 assert _valid_repair_context(bad_base,run2,internal) is False,"wrong force_base_sha must be rejected"
 # Wrong kind
 bad_kind={**ctx,"kind":"repair_context"}
 assert _valid_repair_context(bad_kind,run2,internal) is False,"wrong kind must be rejected"
 # Extra field injected
 extra_field={**ctx,"injected":"evil"}
 assert _valid_repair_context(extra_field,run2,internal) is False,"extra field must be rejected"


# ── P1 RED: crash-boundary replay for attempt-1 force-repair ─────────────────

def test_force_repair_attempt1_crash_at_context_boundary_is_replayable(repo:Path)->None:
 """RED: crash after writing force_repair_intent+force_repair_context on attempt 1
 (before worktree creation) must replay cleanly without requiring a review."""
 s,run,_=ready(repo)
 for _ in range(MAX_WORKER_ATTEMPTS):seed_failed_worker(repo,"red")
 store=RunStore(repo,"run-1");run1=store.read()
 internal=store.read("internal.json") if store._path("internal.json").exists() else {}
 force_base_sha=run1.get("attempt_base_sha") or run1["base_sha"]
 new_attempt=run1["attempt"]+1
 branch=f"hcw/run-1/attempt-{new_attempt}"
 worktree=repo/".worktrees"/f"hcw-run-1-{new_attempt}"
 from hermes_coding_workflow.contracts import SCHEMA_VERSION as SV
 # Simulate the force_repair_context that would be written for attempt 1
 force_ctx={"schema_version":SV,"kind":"force_repair_context","from_attempt":run1["attempt"],"force_base_sha":force_base_sha}
 force_intent={"operation":"force_repair","status":"pending","from_attempt":run1["attempt"],"attempt":new_attempt,"branch":branch,"worktree_path":str(worktree),"base_sha":force_base_sha,"board":run1["kanban_board"],"repair_context_sha256":full_sha_hash(force_ctx)}
 internal["force_repair_intent"]=force_intent
 RunStore._atomic(store._path("internal.json"),internal)
 RunStore._atomic(store._path("repair-context.json"),force_ctx)
 result=s.force_repair("run-1",act("red"),"red",board(repo,[]))
 assert result["attempt"]==new_attempt,"crash replay must complete at the expected new attempt"
 assert result["attempt_base_sha"]==force_base_sha


# ── P2 RED: worker authority fields in force_repair failed-worker loop ────────

def _setup_attempt2_exhausted_for_p2(repo:Path):
 """Return (svc, orig_base_sha) with attempt-2 exhausted (3 failed RED workers)."""
 s,run,candidate_sha=_do_attempt1_through_review(repo)
 s.repair("run-1",act("spec-review"),board(repo,[]))
 for _ in range(MAX_WORKER_ATTEMPTS):seed_failed_worker(repo,"red")
 return s,run["base_sha"],candidate_sha


def _seed_failed_worker_with_field_override(repo:Path,stage:str,overrides:dict)->None:
 """Seed a failed worker for the current attempt with specific field overrides."""
 store=RunStore(repo,"run-1");run=store.read();attempt=run["attempt"]
 worker_attempt=store.latest_worker_attempt(stage,attempt)+1
 dispatch=run["dispatches"][stage];stamp="2026-08-22T00:00:00Z"
 rc=store.read("repair-context.json") if store._path("repair-context.json").exists() else None
 base={"schema_version":"hcw/v1","kind":"worker","id":f"worker-run-1-{stage}-{attempt}-{worker_attempt}","created_at":stamp,"updated_at":stamp,"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS[stage],"attempt":attempt,"worker_attempt":worker_attempt,"brief_hash":dispatch["brief_hash"],"worktree_path":run["worktree_path"],"pid":None,"state":"failed","stdout_path":None,"stderr_path":None,"stdout_sha256":None,"stderr_sha256":None,"exit_code":1,"note":"forced_failure","design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"attempt":attempt,"brief_hash":dispatch["brief_hash"]}),"repair_context_sha256":full_sha_hash(rc),"process_identity":None}
 record={**base,**overrides}
 # Use _atomic directly to bypass validate_worker when testing bad field values
 RunStore._atomic(store.worker_path(stage,attempt,worker_attempt),record)


@pytest.mark.parametrize("bad_field,bad_value",[
 ("backend","wrong-backend"),
 ("model","wrong-model"),
 ("design_sha256","a"*64),
 ("plan_sha256","b"*64),
 ("dispatch_sha256","c"*64),
])
def test_force_repair_rejects_worker_with_wrong_authority_field(repo:Path,bad_field:str,bad_value:object)->None:
 """RED: force_repair must reject workers with wrong backend/model/design/plan/dispatch binding.
 Currently force_repair does not check these fields so these tests fail (no error raised)."""
 s,_,_=_do_attempt1_through_review(repo)
 s.repair("run-1",act("spec-review"),board(repo,[]))
 # Seed MAX-1 correct workers
 for _ in range(MAX_WORKER_ATTEMPTS-1):seed_failed_worker(repo,"red")
 # Seed the last worker with the bad field
 _seed_failed_worker_with_field_override(repo,"red",{bad_field:bad_value})
 with pytest.raises(WorkflowError,match="force_repair_not_authorized"):
  s.force_repair("run-1",act("red"),"red",board(repo,[]))
