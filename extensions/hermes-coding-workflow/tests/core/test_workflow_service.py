from __future__ import annotations
import json,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
import hermes_coding_workflow.service as service_module
from hermes_coding_workflow.adapters import KanbanAdapter
from hermes_coding_workflow.contracts import CLAUDE_BACKEND,CLAUDE_TIER_MODELS,PROFILES
from hermes_coding_workflow.service import ActorContext,WorkflowError,WorkflowService,full_sha_hash
from hermes_coding_workflow.store import RunStore
def git(repo:Path,*args:str)->str:return subprocess.check_output(["git","-C",str(repo),*args],text=True).strip()
@pytest.fixture()
def repo(tmp_path:Path)->Path:
 subprocess.run(["git","init",str(tmp_path)],check=True,capture_output=True);git(tmp_path,"config","user.email","a@b.invalid");git(tmp_path,"config","user.name","t");(tmp_path/"app.txt").write_text("old\n");git(tmp_path,"add",".");git(tmp_path,"commit","-m","base");return tmp_path
def board(repo:Path,calls:list[tuple[str,...]],home:Path|None=None,fail_complete:bool=False)->KanbanAdapter:
 statuses:dict[str,str]={}; failed=False
 def run(argv,cwd):
  nonlocal failed
  calls.append(tuple(argv))
  if "create" in argv and "--body" in argv:
   stage=json.loads(argv[argv.index("--body")+1])["stage"];ident="task-"+stage;statuses[ident]="todo";return subprocess.CompletedProcess(argv,0,json.dumps({"id":ident}) if "--json" in argv else "","")
  if "show" in argv:
   ident=argv[argv.index("show")+1];return subprocess.CompletedProcess(argv,0,json.dumps({"task":{"id":ident,"status":statuses.get(ident,"todo")}}),"")
  if "promote" in argv:
   statuses[argv[argv.index("promote")+1]]="ready";return subprocess.CompletedProcess(argv,0,"","")
  if "complete" in argv:
   if fail_complete and not failed:failed=True;return subprocess.CompletedProcess(argv,1,"","temporary")
   statuses[argv[argv.index("complete")+1]]="done"
  return subprocess.CompletedProcess(argv,0,"","")
 return KanbanAdapter(repo,"hcw-test",run,home=home)

def test_kanban_complete_promotes_triage_before_completion(repo:Path)->None:
 calls=[];status="triage"
 def runner(argv,cwd):
  nonlocal status;calls.append(tuple(argv))
  if "show" in argv:return subprocess.CompletedProcess(argv,0,json.dumps({"task":{"id":"task-red","status":status}}),"")
  if "promote" in argv:status="ready";return subprocess.CompletedProcess(argv,0,"","")
  if "complete" in argv:
   if status!="ready":return subprocess.CompletedProcess(argv,1,"","not ready")
   status="done";return subprocess.CompletedProcess(argv,0,"","")
  return subprocess.CompletedProcess(argv,0,"","")
 KanbanAdapter(repo,"hcw-test",runner).complete("task-red","red")
 assert status=="done" and ["promote" in call for call in calls].count(True)==1
 assert any("promote" in call and "--allow-triage" in call for call in calls)

def act(stage:str)->ActorContext:return ActorContext(PROFILES[stage],"task-"+stage)
def payloads():
 command=[sys.executable,"-c","import pathlib; raise SystemExit(0 if pathlib.Path('app.txt').read_text() == 'new\\n' else 1)"]
 return ({"observable_outcome":"new behavior","requirements":[{"id":"R1","description":"change app"}],"acceptance_criteria":["green"],"approved":True},{"tasks":[{"id":"one","description":"change it","paths":["app.txt"],"test_command":command,"requirement_ids":["R1"]}],"commands":{"red":{"argv":command,"requirement_ids":["R1"]},"green":{"argv":command,"requirement_ids":["R1"]},"full":{"argv":[sys.executable,"-c","pass"],"requirement_ids":["R1"]},"security":{"argv":[sys.executable,"-c","pass"],"requirement_ids":["R1"]},"live":{"argv":[sys.executable,"-c","pass"],"requirement_ids":["R1"]}},"approved":True})
def ready(repo:Path):
 calls=[];s=WorkflowService(repo);run=s.create_run("pkg",["app.txt"],"run-1","hcw-test",board(repo,calls));d,p=payloads();s.approve_design("run-1",act("design"),d);s.approve_plan("run-1",act("plan"),p);return s,run,calls
def seed_worker_success(repo:Path,stage:str)->dict:
 store=RunStore(repo,"run-1");run=store.read();attempt=run["attempt"];worker_attempt=store.latest_worker_attempt(stage,attempt)+1;dispatch=run["dispatches"][stage]
 artifact_root=store.root/"artifacts";artifact_root.mkdir(exist_ok=True)
 stdout=artifact_root/f"{stage}-{attempt}-{worker_attempt}.stdout";stderr=artifact_root/f"{stage}-{attempt}-{worker_attempt}.stderr";stdout.write_text("fixture success\n");stderr.write_text("")
 rel_stdout=str(stdout.relative_to(repo));rel_stderr=str(stderr.relative_to(repo));stamp="2026-08-21T00:00:00Z"
 record={"schema_version":"hcw/v1","kind":"worker","id":f"worker-run-1-{stage}-{attempt}-{worker_attempt}","created_at":stamp,"updated_at":stamp,"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"backend":CLAUDE_BACKEND,"model":CLAUDE_TIER_MODELS[stage],"attempt":attempt,"worker_attempt":worker_attempt,"brief_hash":dispatch["brief_hash"],"worktree_path":run["worktree_path"],"pid":None,"state":"succeeded","stdout_path":rel_stdout,"stderr_path":rel_stderr,"stdout_sha256":__import__("hashlib").sha256(stdout.read_bytes()).hexdigest(),"stderr_sha256":__import__("hashlib").sha256(stderr.read_bytes()).hexdigest(),"exit_code":0,"note":None,"design_sha256":full_sha_hash(store.read("approved-design.json")),"plan_sha256":full_sha_hash(store.read("plan.json")),"dispatch_sha256":full_sha_hash({"run_id":"run-1","stage":stage,"task_id":run["kanban_task_ids"][stage],"profile":PROFILES[stage],"attempt":attempt,"brief_hash":dispatch["brief_hash"]}),"process_identity":None}
 store.write_worker(stage,attempt,worker_attempt,record);return record
def test_scope_amendment_is_additive_head_bound_and_audited(repo:Path)->None:
 s,run,_=ready(repo);store=RunStore(repo,"run-1");state=store.read();state["status"]="awaiting_green";state["stage_statuses"]["design"]="completed";state["stage_statuses"]["plan"]="completed";state["stage_statuses"]["red"]="completed";state["stage_statuses"]["green"]="active";store.write_json("run.json",state)
 amended=s.amend_scope("run-1",act("green"),["plugins/github_intake/**"],reason="user-approved importable package",expected_revision=state["revision"],expected_head=state["head_sha"])
 replayed=s.amend_scope("run-1",act("green"),["plugins/github_intake/**"],reason="user-approved importable package",expected_revision=state["revision"],expected_head=state["head_sha"])
 assert replayed==amended
 assert amended["scope"]==["app.txt","plugins/github_intake/**"]
 audit=store.read("scope-amendments.json")["amendments"][-1]
 assert audit["attempt"]==1 and audit["added_scope"]==["plugins/github_intake/**"] and audit["reason"]=="user-approved importable package"
 assert audit["actor"]==act("green").record()
 with pytest.raises(WorkflowError,match="scope_amendment_stale"):s.amend_scope("run-1",act("green"),["plugins/other/**"],reason="stale",expected_revision=state["revision"],expected_head=state["head_sha"])

@pytest.mark.parametrize("pattern",["**","../outside/**","/tmp/**","*/anything/**"])
def test_scope_amendment_rejects_broad_or_escaping_patterns(repo:Path,pattern:str)->None:
 s,_,_=ready(repo);store=RunStore(repo,"run-1");state=store.read();state["status"]="awaiting_green";state["stage_statuses"]["green"]="active";store.write_json("run.json",state)
 with pytest.raises(WorkflowError,match="invalid_scope_amendment"):s.amend_scope("run-1",act("green"),[pattern],reason="bad",expected_revision=state["revision"],expected_head=state["head_sha"])

def test_create_graph_uses_actual_workspace_and_exact_profiles(repo:Path)->None:
 s,run,calls=ready(repo)
 assert run["status"]=="awaiting_design" and run["stage_profiles"]==PROFILES
 assert set(run["kanban_task_ids"])==set(PROFILES)
 assert run["stage_statuses"] == {stage: ("active" if stage == "design" else "pending") for stage in PROFILES}
 creates=[x for x in calls if "create" in x and "--idempotency-key" in x]
 assert all(f"worktree:{run['worktree_path']}" in x and "--branch" in x and "--idempotency-key" in x for x in creates)
 assert any(x[x.index("link")+1:x.index("link")+3]==("task-design","task-plan") for x in calls if "link" in x)
 assert json.loads((Path(run["worktree_path"])/".hermes/hcw-run.json").read_text())["run_id"]=="run-1"

def test_create_run_resumes_from_durable_intent_after_graph_before_run_write(monkeypatch,repo:Path)->None:
 calls=[];adapter=board(repo,calls);svc=WorkflowService(repo);original=RunStore.write_run;failed=False
 def fail_once(self,record,expected):
  nonlocal failed
  if not failed:failed=True;raise OSError("injected post-graph crash")
  return original(self,record,expected)
 monkeypatch.setattr(RunStore,"write_run",fail_once)
 with pytest.raises(WorkflowError,match="setup_failed"):
  svc.create_run("pkg",["app.txt"],"run-resume","hcw-test",adapter,goal="resume me")
 store=RunStore(repo,"run-resume");internal=store.read("internal.json")
 assert not store._path("run.json").exists()
 assert internal["create_intent"]["status"]=="graph_created"
 assert Path(internal["create_intent"]["worktree_path"]).is_dir()
 created_before=len([call for call in calls if "create" in call])
 monkeypatch.setattr(RunStore,"write_run",original)
 resumed=svc.create_run("pkg",["app.txt"],"run-resume","hcw-test",adapter,goal="resume me")
 assert resumed["status"]=="awaiting_design"
 assert store.read("internal.json")["create_intent"]["status"]=="completed"
 assert len([call for call in calls if "create" in call])==created_before

def test_create_run_rejects_preexisting_branch_at_wrong_base(repo:Path)->None:
 (repo/"later.txt").write_text("later\n");git(repo,"add","later.txt");git(repo,"commit","-m","later")
 git(repo,"branch","hcw/run-collision/attempt-1","HEAD~1")
 with pytest.raises(WorkflowError,match="worktree_creation_failed"):
  WorkflowService(repo).create_run("pkg",["app.txt"],"run-collision","hcw-test",board(repo,[]))

def test_create_run_rejects_symlinked_attempt_path(repo:Path,tmp_path:Path)->None:
 controlled=repo/".worktrees";controlled.mkdir();(controlled/"hcw-run-link-1").symlink_to(tmp_path/"outside",target_is_directory=True)
 with pytest.raises(WorkflowError,match="path_scope_violation"):
  WorkflowService(repo).create_run("pkg",["app.txt"],"run-link","hcw-test",board(repo,[]))

def test_graph_failure_never_deletes_idempotent_task_ids(repo:Path)->None:
 calls=[];created=0
 def runner(argv,cwd):
  nonlocal created
  calls.append(tuple(argv))
  if "create" in argv and "--body" in argv:created+=1;return subprocess.CompletedProcess(argv,0,json.dumps({"id":f"existing-{created}"}),"")
  if "link" in argv:return subprocess.CompletedProcess(argv,1,"","injected")
  return subprocess.CompletedProcess(argv,0,"","")
 with pytest.raises(RuntimeError,match="kanban_failed"):
  KanbanAdapter(repo,"hcw-test",runner).graph("run-safe","branch",repo,PROFILES)
 assert not any("delete" in call for call in calls)

def test_transition_updates_authoritative_stage_statuses(repo:Path)->None:
 s,run,calls=ready(repo); d,p=payloads()
 # ready() has already approved design and plan; RED is now the sole active task.
 assert RunStore(repo,"run-1").read()["stage_statuses"]["red"] == "active"
 seed_worker_success(repo,"red")
 s.check("run-1",act("red"),"red",payloads()[1]["commands"]["red"]["argv"])
 statuses=RunStore(repo,"run-1").read()["stage_statuses"]
 assert statuses["red"] == "completed" and statuses["green"] == "active"
 completed=[call for call in calls if "complete" in call]
 assert [call[call.index("complete")+1] for call in completed] == ["task-design","task-plan","task-red"]
 assert all("--result" in call and "--summary" in call and "--json" not in call for call in completed)

def test_kanban_reconciles_after_durable_transition_using_persisted_adapter_home(monkeypatch,repo:Path,tmp_path:Path)->None:
 home=tmp_path/"kanban-home";home.mkdir();calls=[];svc=WorkflowService(repo)
 run=svc.create_run("pkg",["app.txt"],"run-sync","hcw-test",board(repo,calls,home=home,fail_complete=True));design,_=payloads()
 with pytest.raises(RuntimeError,match="kanban_failed"):
  svc.approve_design("run-sync",ActorContext(PROFILES["design"],run["kanban_task_ids"]["design"]),design)
 durable=RunStore(repo,"run-sync").read()
 assert durable["status"]=="awaiting_plan" and durable["stage_statuses"]["design"]=="completed"
 assert Path(RunStore(repo,"run-sync").read("internal.json")["kanban_home"])==home.resolve()
 replay_calls=[];replacement=board(repo,replay_calls,home=home);captured={}
 def factory(repo_path,board_name,runner=None,home=None):captured["home"]=home;return replacement
 monkeypatch.setattr(service_module,"KanbanAdapter",factory)
 shown=WorkflowService(repo).show("run-sync")
 assert shown["status"]=="awaiting_plan" and captured["home"]==home.resolve()
 assert any("complete" in call and "task-design" in call for call in replay_calls)
def test_actor_forgery_and_structured_artifacts_rejected(repo:Path)->None:
 s,run,_=ready(repo)
 with pytest.raises(WorkflowError,match="task_profile_mismatch"):s.check("run-1",ActorContext("dev-builder","task-red"),"red",["python","-c","raise SystemExit(1)"])
 with pytest.raises(WorkflowError,match="malformed_design"):WorkflowService(repo).approve_design("run-1",act("design"),{"approved":True})
def test_check_executes_argv_not_forged_exit(repo:Path)->None:
 s,run,_=ready(repo)
 with pytest.raises(WorkflowError,match="planned_command_mismatch"):s.check("run-1",act("red"),"red",["python","-c","pass"])
 seed_worker_success(repo,"red")
 red=s.check("run-1",act("red"),"red",payloads()[1]["commands"]["red"]["argv"])
 assert red["exit_code"]==1 and red["command"]==payloads()[1]["commands"]["red"]["argv"]
 w=Path(run["worktree_path"]);(w/"app.txt").write_text("new\n");git(w,"add","app.txt");git(w,"commit","-m","green")
 seed_worker_success(repo,"green")
 green=s.check("run-1",act("green"),"green",payloads()[1]["commands"]["green"]["argv"]);assert green["exit_code"]==0

def test_check_forwards_home_location_but_not_unrelated_environment(monkeypatch,repo:Path,tmp_path:Path)->None:
 home=tmp_path/"controlled-home";home.mkdir();monkeypatch.setenv("HOME",str(home));monkeypatch.setenv("HCW_UNRELATED_SETTING","must-not-survive")
 s=WorkflowService(repo);run=s.create_run("pkg",["app.txt"],"run-1","hcw-test",board(repo,[]));design,plan=payloads()
 custom=[sys.executable,"-c",f"import os;assert os.environ.get('HOME')=={str(home)!r};assert 'HCW_UNRELATED_SETTING' not in os.environ"]
 plan["commands"]["full"]["argv"]=custom;s.approve_design("run-1",act("design"),design);s.approve_plan("run-1",act("plan"),plan)
 store=RunStore(repo,"run-1");state=store.read();state["status"]="awaiting_verify";state["stage_statuses"]={stage:("active" if stage=="verify" else "completed") for stage in PROFILES};state["revision"]+=1;store.write_run(state,state["revision"]-1)
 checked=s.check("run-1",act("verify"),"full",custom)
 assert checked["exit_code"]==0

def test_check_timeout_with_byte_streams_fails_closed_without_evidence(monkeypatch,repo:Path)->None:
 s,_,_=ready(repo);plan=payloads()[1];seed_worker_success(repo,"red");real_run=subprocess.run
 def timed(argv,*args,**kwargs):
  if argv==plan["commands"]["red"]["argv"]:raise subprocess.TimeoutExpired(argv,1,output=b"partial stdout",stderr=b"partial stderr")
  return real_run(argv,*args,**kwargs)
 monkeypatch.setattr(service_module.subprocess,"run",timed)
 with pytest.raises(WorkflowError,match="check_timeout"):s.check("run-1",act("red"),"red",plan["commands"]["red"]["argv"],1)
 store=RunStore(repo,"run-1");assert store.read()["status"]=="awaiting_red" and store.evidence()==[]

def test_red_rejects_source_mutation_and_evidence_tampering(repo:Path)->None:
 s,run,_=ready(repo)
 plan_path=repo / ".hermes" / "workflows" / "run-1" / "plan.json"
 plan=json.loads(plan_path.read_text());plan["content"]["commands"]["red"]["argv"]=[sys.executable,"-c","open('app.txt','w').write('bad'); raise SystemExit(1)"];plan_path.write_text(json.dumps(plan))
 seed_worker_success(repo,"red")
 with pytest.raises(WorkflowError,match="red_mutation_violation"):
  s.check("run-1",act("red"),"red",[sys.executable,"-c","open('app.txt','w').write('bad'); raise SystemExit(1)"])
 subprocess.run(["git","-C",str(run["worktree_path"]),"checkout","--","app.txt"],check=True)
 plan["content"]["commands"]["red"]["argv"]=payloads()[1]["commands"]["red"]["argv"];plan_path.write_text(json.dumps(plan))
 seed_worker_success(repo,"red")
 s.check("run-1",act("red"),"red",payloads()[1]["commands"]["red"]["argv"])
 # An existing evidence artifact must remain content-addressed when consumed.
 worktree=Path(run["worktree_path"]);(worktree/"app.txt").write_text("new\n");git(worktree,"add","app.txt");git(worktree,"commit","-m","green")
 seed_worker_success(repo,"green")
 green=s.check("run-1",act("green"),"green",payloads()[1]["commands"]["green"]["argv"])
 artifact=repo / green["artifact_path"]
 artifact.write_text("tampered")
 with pytest.raises(ValueError,match="artifact_hash_mismatch"):RunStore(repo,"run-1").evidence()
def test_concurrent_store_has_one_winner(repo:Path)->None:
 s,_,_=ready(repo);store=RunStore(repo,"run-1");snapshot=store.read()
 def f():
  copy=dict(snapshot);copy["revision"]+=1
  try:store.write_run(copy,snapshot["revision"]);return "ok"
  except Exception:return "conflict"
 with ThreadPoolExecutor(max_workers=2) as ex:out=list(ex.map(lambda _:f(),range(2)))
 assert out.count("ok")==1

def test_create_run_rejects_symlinked_controlled_roots(repo:Path, tmp_path:Path)->None:
 (repo/".worktrees").symlink_to(tmp_path / "outside")
 with pytest.raises(WorkflowError,match="path_scope_violation"):
  WorkflowService(repo).create_run("pkg",["app.txt"],"run-escape","hcw-test",board(repo,[]))

def test_completion_rejects_dirty_post_verification_worktree(repo:Path)->None:
 s,run,_=ready(repo);store=RunStore(repo,"run-1");state=store.read();head=git(Path(run["worktree_path"]),"rev-parse","HEAD")
 state["head_sha"]=head;state["status"]="verified";state["revision"]+=1
 state["stage_statuses"]={stage:("active" if stage=="complete" else "completed") for stage in PROFILES}
 store.write_json("run.json",state)
 store.write_json("verification.json",{"schema_version":"hcw/v1","kind":"verification","id":"verify-test","created_at":"2026-08-19T00:00:00Z","run_id":"run-1","candidate_sha":head,"evidence_ids":[],"status":"passed"})
 seed_worker_success(repo,"complete")
 (Path(run["worktree_path"])/"app.txt").write_text("dirty after verification\n")
 with pytest.raises(WorkflowError,match="premature_completion"):s.complete("run-1",act("complete"))

def test_completion_revalidates_live_evidence_artifacts(repo:Path)->None:
 s,run,_=ready(repo);plan=payloads()[1];worktree=Path(run["worktree_path"])
 seed_worker_success(repo,"red")
 s.check("run-1",act("red"),"red",plan["commands"]["red"]["argv"])
 (worktree/"app.txt").write_text("new\n");seed_worker_success(repo,"green");s.commit("run-1",act("green"),"green")
 s.check("run-1",act("green"),"green",plan["commands"]["green"]["argv"]);head=git(worktree,"rev-parse","HEAD")
 approved={"reviewed_sha":head,"decision":"approved","findings":[],"dispositions":[]}
 s.review("run-1",act("spec-review"),approved);seed_worker_success(repo,"quality-review");s.review("run-1",act("quality-review"),approved)
 s.check("run-1",act("verify"),"full",plan["commands"]["full"]["argv"]);s.check("run-1",act("verify"),"security",plan["commands"]["security"]["argv"]);s.verify("run-1",act("verify"))
 live=s.check("run-1",act("live"),"live",plan["commands"]["live"]["argv"])
 seed_worker_success(repo,"complete")
 store=RunStore(repo,"run-1");verification=store.read("verification.json");original_ids=list(verification["evidence_ids"]);verification["evidence_ids"].append(original_ids[0]);store.write_json("verification.json",verification)
 with pytest.raises(WorkflowError,match="premature_completion"):s.complete("run-1",act("complete"))
 verification["evidence_ids"]=original_ids;store.write_json("verification.json",verification)
 (repo/live["artifact_path"]).write_text("tampered after live")
 with pytest.raises(WorkflowError,match="evidence_integrity_failure"):s.complete("run-1",act("complete"))

def test_repair_reuses_original_kanban_home_and_reattaches_plan(monkeypatch,repo:Path)->None:
 home=repo.parent/"kanban-home";home.mkdir();initial_calls=[];s=WorkflowService(repo);run=s.create_run("pkg",["app.txt"],"run-1","hcw-test",board(repo,initial_calls,home=home));design,plan=payloads();s.approve_design("run-1",act("design"),design);s.approve_plan("run-1",act("plan"),plan);worktree=Path(run["worktree_path"])
 seed_worker_success(repo,"red")
 s.check("run-1",act("red"),"red",plan["commands"]["red"]["argv"])
 (worktree/"app.txt").write_text("new\n");seed_worker_success(repo,"green");s.commit("run-1",act("green"),"green");s.check("run-1",act("green"),"green",plan["commands"]["green"]["argv"])
 head=git(worktree,"rev-parse","HEAD");finding={"id":"F1","severity":"blocker","description":"repair required"}
 s.review("run-1",act("spec-review"),{"reviewed_sha":head,"decision":"changes_requested","findings":[finding],"dispositions":[{"finding_id":"F1","disposition":"accepted"}]})
 calls=[];replacement=board(repo,calls);captured={};expected=Path(RunStore(repo,"run-1").read("internal.json")["kanban_home"])
 def factory(repo_path,board_name,runner=None,home=None):captured["home"]=home;return replacement
 monkeypatch.setattr(service_module,"KanbanAdapter",factory)
 reconciled=[];original_reconcile=WorkflowService._reconcile
 def observe_reconcile(self,store,state):reconciled.append(store.read()["attempt"]);return original_reconcile(self,store,state)
 monkeypatch.setattr(WorkflowService,"_reconcile",observe_reconcile)
 repaired=WorkflowService(repo).repair("run-1",act("spec-review"))
 assert reconciled==[2]
 assert repaired["attempt"]==2 and captured["home"]==expected and repaired["stage_statuses"]["red"]=="active"
 assert repaired["stage_statuses"]["design"]=="completed" and repaired["stage_statuses"]["plan"]=="completed"
 context=RunStore(repo,"run-1").read("repair-context.json")
 assert context["from_attempt"]==1 and context["source_stage"]=="spec-review" and context["review"]["findings"]==[finding]
 completed={call[call.index("complete")+1] for call in calls if "complete" in call}
 assert {repaired["kanban_task_ids"]["design"],repaired["kanban_task_ids"]["plan"]}.issubset(completed)
 comments=[call for call in calls if "comment" in call]
 assert len(comments)==len(PROFILES)-2
 payload=json.loads(comments[0][comments[0].index("comment")+2])
 assert payload["attempt"]==2 and payload["declared_commands"]["red"]==plan["commands"]["red"]["argv"]
 context["review"]["findings"][0]["description"]="tampered before dispatch"
 RunStore._atomic(RunStore(repo,"run-1")._path("repair-context.json"),context)
 with pytest.raises(WorkflowError,match="repair_context_invalid"):WorkflowService(repo).dispatch_worker("run-1","red")

def test_repair_resumes_durable_intent_after_graph_failure(monkeypatch,repo:Path)->None:
 s,run,_=ready(repo);plan=payloads()[1];worktree=Path(run["worktree_path"])
 seed_worker_success(repo,"red")
 s.check("run-1",act("red"),"red",plan["commands"]["red"]["argv"])
 (worktree/"app.txt").write_text("new\n");seed_worker_success(repo,"green");s.commit("run-1",act("green"),"green");s.check("run-1",act("green"),"green",plan["commands"]["green"]["argv"])
 head=git(worktree,"rev-parse","HEAD");finding={"id":"F1","severity":"blocker","description":"repair required"}
 s.review("run-1",act("spec-review"),{"reviewed_sha":head,"decision":"changes_requested","findings":[finding],"dispositions":[{"finding_id":"F1","disposition":"accepted"}]})
 calls=[];replacement=board(repo,calls);original=WorkflowService._attach_plan_briefs
 def fail_after_graph(*args,**kwargs):raise OSError("injected post-graph crash")
 monkeypatch.setattr(WorkflowService,"_attach_plan_briefs",fail_after_graph)
 with pytest.raises(WorkflowError,match="repair_setup_failed"):s.repair("run-1",act("spec-review"),replacement)
 store=RunStore(repo,"run-1");intent=store.read("internal.json")["repair_intent"]
 assert store.read()["attempt"]==1 and intent["status"]=="graph_created"
 assert Path(intent["worktree_path"]).is_dir()
 context=store.read("repair-context.json")
 assert intent["repair_context_sha256"]==full_sha_hash(context)
 archive=store.root/"attempts"/"1";archive.mkdir(parents=True,exist_ok=True)
 __import__("shutil").move(str(store._path("reviews.json")),str(archive/"reviews.json"))
 created_before=len([call for call in calls if "create" in call])
 monkeypatch.setattr(WorkflowService,"_attach_plan_briefs",original)
 repaired=s.repair("run-1",act("spec-review"),replacement)
 assert repaired["attempt"]==2 and repaired["status"]=="awaiting_red"
 assert store.read("internal.json")["repair_intent"]["status"]=="completed"
 assert len([call for call in calls if "create" in call])==created_before

def seed_repair_review(repo:Path,store:RunStore,state:dict)->None:
 reviewer=act("spec-review").record();stamp="2026-08-21T00:00:00Z"
 RunStore._atomic(store._path("reviews.json"),{"reviews":[{"schema_version":"hcw/v1","kind":"review","id":"review-fixture","created_at":stamp,"run_id":"run-1","reviewer":reviewer,"reviewed_sha":git(repo,"rev-parse","HEAD"),"decision":"changes_requested","findings":[{"id":"F1","severity":"blocker","description":"repair fixture"}],"dispositions":[{"finding_id":"F1","disposition":"accepted"}]}]})

def test_repair_rejects_symlinked_worktree_root(repo:Path,tmp_path:Path)->None:
 s,_,_=ready(repo);store=RunStore(repo,"run-1");state=store.read();state["status"]="repairing";state["stage_statuses"]["spec-review"]="blocked";store.write_json("run.json",state);seed_repair_review(repo,store,state)
 controlled=repo/".worktrees";outside=tmp_path/"outside-worktrees";controlled.rename(outside);controlled.symlink_to(outside,target_is_directory=True)
 with pytest.raises(WorkflowError,match="path_scope_violation"):s.repair("run-1",act("spec-review"),board(repo,[]))

def test_repair_rejects_preexisting_attempt_branch_at_wrong_base(repo:Path)->None:
 s,_,_=ready(repo);store=RunStore(repo,"run-1");state=store.read();state["status"]="repairing";state["stage_statuses"]["spec-review"]="blocked";store.write_json("run.json",state);seed_repair_review(repo,store,state)
 (repo/"later.txt").write_text("later\n");git(repo,"add","later.txt");git(repo,"commit","-m","later");git(repo,"branch","hcw/run-1/attempt-2","HEAD")
 with pytest.raises(WorkflowError,match="repair_setup_failed"):s.repair("run-1",act("spec-review"),board(repo,[]))

def test_repair_rejects_symlinked_attempt_path(repo:Path,tmp_path:Path)->None:
 s,_,_=ready(repo);store=RunStore(repo,"run-1");state=store.read();state["status"]="repairing";state["stage_statuses"]["spec-review"]="blocked";store.write_json("run.json",state);seed_repair_review(repo,store,state)
 (repo/".worktrees"/"hcw-run-1-2").symlink_to(tmp_path/"outside",target_is_directory=True)
 with pytest.raises(WorkflowError,match="path_scope_violation"):s.repair("run-1",act("spec-review"),board(repo,[]))
