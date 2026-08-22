from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
from .service import ActorContext,WorkflowError,WorkflowService
from .store import RunStore
def _json(x:object)->None:print(json.dumps(x,sort_keys=True))
def _payload(path:str)->dict:
 value=json.loads(Path(path).read_text())
 if not isinstance(value,dict):raise ValueError("malformed_json")
 return value
def _repo_and_run(repo:Path,run_id:str)->tuple[Path,str]:
 locator=repo.resolve()/".hermes"/"hcw-run.json"
 if locator.exists():
  value=json.loads(locator.read_text());
  if value.get("run_id")!=run_id or value.get("repo_root") is None:raise WorkflowError("locator_mismatch")
  return Path(value["repo_root"]),run_id
 return repo.resolve(),run_id
def main(argv:list[str]|None=None)->int:
 p=argparse.ArgumentParser(prog="hcw");s=p.add_subparsers(dest="command",required=True)
 create=s.add_parser("create-run");create.add_argument("repo");create.add_argument("--run-id",required=True);create.add_argument("--package",required=True);create.add_argument("--scope",action="append",required=True);create.add_argument("--board",required=True);create.add_argument("--goal",required=True)
 for name in ("approve-design","approve-plan","check","commit","review","verify","complete","repair","show","dispatch-worker","worker-status"):
  q=s.add_parser(name);q.add_argument("repo");q.add_argument("run_id")
  if name in {"approve-design","approve-plan","review"}:q.add_argument("--json",required=True)
  if name=="check":q.add_argument("type",choices=["red","green","full","security","live"]);q.add_argument("--timeout",type=int,default=60);q.add_argument("command_argv",nargs=argparse.REMAINDER)
  if name=="commit":q.add_argument("--message",required=True)
  if name in {"dispatch-worker","worker-status"}:q.add_argument("stage")
  if name=="dispatch-worker":q.add_argument("--retry-succeeded",action="store_true")
 a=p.parse_args(argv)
 try:
  if a.command=="create-run":out=WorkflowService(Path(a.repo)).create_run(a.package,a.scope,a.run_id,a.board,goal=a.goal)
  else:
   repo,rid=_repo_and_run(Path(a.repo),a.run_id);svc=WorkflowService(repo)
   if a.command=="show":out=svc.show(rid)
   elif a.command=="dispatch-worker":out=svc.dispatch_worker(rid,a.stage,retry_succeeded=a.retry_succeeded)
   elif a.command=="worker-status":out=svc.worker_status(rid,a.stage)
   else:
    svc.reconcile(rid)
    actor=ActorContext.from_env()
    if a.command=="approve-design":out=svc.approve_design(rid,actor,_payload(a.json))
    elif a.command=="approve-plan":out=svc.approve_plan(rid,actor,_payload(a.json))
    elif a.command=="check":
     if not a.command_argv:raise WorkflowError("invalid_check")
     out=svc.check(rid,actor,a.type,a.command_argv,a.timeout)
    elif a.command=="review":out=svc.review(rid,actor,_payload(a.json))
    elif a.command=="commit":out=svc.commit(rid,actor,a.message)
    elif a.command=="verify":out=svc.verify(rid,actor)
    elif a.command=="repair":out=svc.repair(rid,actor)
    else:out=svc.complete(rid,actor)
  _json(out);return 0
 except (WorkflowError,ValueError,RuntimeError,json.JSONDecodeError) as e:_json({"error":getattr(e,"code",str(e))});return 2
if __name__=="__main__":raise SystemExit(main())
