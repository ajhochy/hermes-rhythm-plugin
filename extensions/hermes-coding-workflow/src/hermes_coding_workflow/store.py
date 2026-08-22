from __future__ import annotations
import fcntl, hashlib, json, os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from .contracts import valid_run_id, validate_record
from .safety import atomic_write_bytes, digest_json, redact
class RevisionConflict(RuntimeError): pass
class RunStore:
 _NAMES={"run.json","evidence.jsonl","reviews.json","verification.json","handoff.json","approved-design.json","plan.json","internal.json","repair-context.json"}
 def __init__(self,repo:Path,run_id:str)->None:
  self.repo=repo.resolve()
  if not valid_run_id(run_id):raise ValueError("invalid_run_id")
  for controlled in (self.repo/".hermes", self.repo/".hermes"/"workflows"):
   if controlled.is_symlink():raise ValueError("path_scope_violation")
  self.root=self.repo/".hermes"/"workflows"/run_id
  if self.root.exists() and self.root.is_symlink():raise ValueError("path_scope_violation")
  self.root.mkdir(parents=True,exist_ok=True)
  if self.root.resolve().parent != (self.repo/".hermes"/"workflows").resolve():raise ValueError("path_scope_violation")
 def _path(self,name:str)->Path:
  if name not in self._NAMES:raise ValueError("invalid_artifact")
  return self.root/name
 @contextmanager
 def locked(self)->Iterator[None]:
  with (self.root/".lock").open("a+") as f:
   fcntl.flock(f.fileno(),fcntl.LOCK_EX)
   try:yield
   finally:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
 def read(self,name="run.json")->dict[str,Any]:return json.loads(self._path(name).read_text())
 def write_run(self,record:dict[str,Any],expected:int|None)->None:
  if validate_record(record):raise ValueError("malformed_schema")
  with self.locked():
   if self._path("run.json").exists() and (expected is None or self.read()["revision"]!=expected):raise RevisionConflict("revision_conflict")
   self._atomic(self._path("run.json"),record)
 def write_json(self,name:str,record:dict[str,Any])->None:
  if validate_record(record):raise ValueError("malformed_schema")
  self._atomic(self._path(name),record)
 def worker_dir(self)->Path:
  d=self.root/"workers"
  if d.exists() and d.is_symlink():raise ValueError("path_scope_violation")
  d.mkdir(exist_ok=True)
  if d.is_symlink() or d.resolve().parent!=self.root.resolve():raise ValueError("path_scope_violation")
  return d
 def worker_path(self,stage:str,attempt:int,worker_attempt:int)->Path:
  return self.worker_dir()/f"{stage}-{attempt}-{worker_attempt}.json"
 def read_worker(self,stage:str,attempt:int,worker_attempt:int)->dict[str,Any]|None:
  path=self.worker_path(stage,attempt,worker_attempt)
  return json.loads(path.read_text()) if path.is_file() and not path.is_symlink() else None
 def latest_worker_attempt(self,stage:str,attempt:int)->int:
  prefix=f"{stage}-{attempt}-";nums=[int(p.stem[len(prefix):]) for p in self.worker_dir().glob(prefix+"*.json") if p.stem[len(prefix):].isdigit()]
  return max(nums) if nums else 0
 def write_worker(self,stage:str,attempt:int,worker_attempt:int,record:dict[str,Any])->None:
  if validate_record(record):raise ValueError("malformed_schema")
  self._atomic(self.worker_path(stage,attempt,worker_attempt),record)
 def append_evidence(self,record:dict[str,Any],artifact:Path)->dict[str,Any]:
  with self.locked():return self._append_evidence_locked(record,artifact)
 def _append_evidence_locked(self,record:dict[str,Any],artifact:Path)->dict[str,Any]:
  if artifact.is_symlink() or not artifact.is_file() or not artifact.resolve().is_relative_to(self.repo):raise ValueError("artifact_hash_mismatch")
  saved=dict(record); saved["artifact_path"]=str(artifact.resolve().relative_to(self.repo));saved["artifact_sha256"]=hashlib.sha256(artifact.read_bytes()).hexdigest()
  saved.pop("summary",None);saved.pop("raw_args",None)
  path=self._path("evidence.jsonl");previous=None
  if path.exists():
   lines=path.read_text().splitlines();previous=json.loads(lines[-1])["evidence_hash"] if lines else None
  saved["previous_evidence_hash"]=previous;saved["evidence_hash"]=digest_json(json.dumps(saved,sort_keys=True,separators=(",",":" )).encode())
  if validate_record(saved):raise ValueError("malformed_schema")
  with path.open("a") as f:f.write(json.dumps(saved,sort_keys=True,separators=(",",":"))+"\n");f.flush();os.fsync(f.fileno())
  return saved
 def evidence(self)->list[dict[str,Any]]:
  p=self._path("evidence.jsonl")
  if not p.exists():return []
  previous=None;out=[]
  for line in p.read_text().splitlines():
   r=json.loads(line);known=r.pop("evidence_hash",None)
   if r.get("previous_evidence_hash")!=previous or known!=digest_json(json.dumps(r,sort_keys=True,separators=(",",":" )).encode()):raise ValueError("evidence_chain_mismatch")
   artifact=self.repo/r.get("artifact_path","")
   if not artifact.is_file() or artifact.is_symlink() or hashlib.sha256(artifact.read_bytes()).hexdigest()!=r.get("artifact_sha256"):raise ValueError("artifact_hash_mismatch")
   r["evidence_hash"]=known;previous=known;out.append(r)
  return out
 @staticmethod
 def _atomic(path:Path,record:dict[str,Any])->None:
  atomic_write_bytes(path,(json.dumps(record,sort_keys=True,separators=(",",":"))+"\n").encode())
