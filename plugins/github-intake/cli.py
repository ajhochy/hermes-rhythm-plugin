"""hermes github-intake CLI — operator interface for the github-intake plugin."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


_PLUGIN_DIR = Path(__file__).parent


def _load_dep(name: str):
    key = f"github_intake_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = _PLUGIN_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes github-intake",
        description="GitHub issue intake plugin operator CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # validate-config
    vc = sub.add_parser("validate-config", help="Validate a config file")
    vc.add_argument("config_path", help="Path to config YAML")

    # ingest-fixture
    ig = sub.add_parser("ingest-fixture", help="Ingest a fixture payload")
    ig.add_argument("--config", required=True, help="Config YAML path")
    ig.add_argument("--fixture", required=True, help="Fixture JSON path")
    ig.add_argument("--board", required=True, help="Local board directory")
    ig.add_argument("--event-type", default="issues", help="GitHub event type")
    ig.add_argument("--dry-run", action="store_true", help="Dry-run mode (no writes)")

    # replay
    rp = sub.add_parser("replay", help="Replay a quarantined intake record")
    rp.add_argument("--config", required=True)
    rp.add_argument("--board", required=True)
    rp.add_argument("--intake-id", required=True)

    # quarantine-list
    ql = sub.add_parser("quarantine-list", help="List quarantined records")
    ql.add_argument("--config", required=True)
    ql.add_argument("--board", required=True)

    # audit
    ad = sub.add_parser("audit", help="Show audit entries")
    ad.add_argument("--config", required=True)
    ad.add_argument("--board", required=True, help="Local board directory")
    ad.add_argument("--intake-id", default=None, help="Filter by intake ID")

    # status
    st = sub.add_parser("status", help="Show plugin status")
    st.add_argument("--config", required=True)
    st.add_argument("--board", required=True)

    # dry-run
    dr = sub.add_parser("dry-run", help="Alias for ingest-fixture with --dry-run")
    dr.add_argument("--config", required=True)
    dr.add_argument("--fixture", required=True)
    dr.add_argument("--board", required=True)
    dr.add_argument("--event-type", default="issues")

    return parser


def cmd_validate_config(args) -> int:
    config_mod = _load_dep("config")
    path = Path(args.config_path)
    if not path.exists():
        print(f"Error: config file not found: {path}", file=sys.stderr)
        return 1
    try:
        cfg = config_mod.load_config(path)
        status = "enabled" if cfg.enabled else "disabled"
        print(json.dumps({
            "valid": True,
            "enabled": cfg.enabled,
            "status": status,
            "dry_run": cfg.dry_run,
            "kill_switch": cfg.kill_switch,
        }))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_ingest_fixture(args, dry_run_override: bool = False) -> int:
    config_mod = _load_dep("config")
    intake_mod = _load_dep("intake")
    security_mod = _load_dep("security")

    cfg = config_mod.load_config(Path(args.config))
    fixture_path = Path(args.fixture)

    with open(fixture_path, "rb") as f:
        body = f.read()

    secret = os.environ.get(cfg.webhook.secret_env, "")

    import hmac as _hmac, hashlib as _hashlib
    sig_hex = _hmac.new(secret.encode(), body, _hashlib.sha256).hexdigest()
    signature = f"sha256={sig_hex}"

    dry_run = getattr(args, "dry_run", False) or dry_run_override
    if dry_run:
        cfg = cfg.model_copy(update={"dry_run": True})

    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    board_dir = Path(args.board)

    hcw_adapter_mod = _load_dep("hcw_adapter")
    adapter = hcw_adapter_mod.DryRunSink()

    try:
        result = intake_mod.ingest(
            event_type=args.event_type,
            delivery_id=f"cli-{now.isoformat()}",
            signature=signature,
            body=body,
            config=cfg,
            board_dir=board_dir,
            hcw_adapter=adapter,
            secret=secret,
            now=now,
        )
        output = {
            "dry_run": result.dry_run,
            "intake_id": result.intake_id,
            "outcome": result.outcome,
            "counters": result.counters,
            "correlation_id": result.correlation_id,
        }
        print(json.dumps(output))
        return 0
    except intake_mod.UnsupportedEventAction as exc:
        print(f"Error: unsupported event action: {exc}", file=sys.stderr)
        return 1
    except security_mod.AllowlistViolation as exc:
        print(f"Error: allowlist violation: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_status(args) -> int:
    config_mod = _load_dep("config")
    store_mod = _load_dep("store")

    cfg = config_mod.load_config(Path(args.config))
    board_dir = Path(args.board)

    store = store_mod.IntakeStore(board_dir=board_dir)
    records = store.list_all()
    quarantined = [r for r in records if r.dispatch_state in ("quarantined", "failed")]

    status = "disabled" if not cfg.enabled else "enabled"
    print(json.dumps({
        "status": status,
        "enabled": cfg.enabled,
        "dry_run": cfg.dry_run,
        "kill_switch": cfg.kill_switch,
        "total_records": len(records),
        "quarantined": len(quarantined),
    }))
    return 0


def cmd_audit(args) -> int:
    config_mod = _load_dep("config")
    store_mod = _load_dep("store")
    audit_mod = _load_dep("audit")

    cfg = config_mod.load_config(Path(args.config))
    board_dir = Path(args.board)

    store = store_mod.IntakeStore(board_dir=board_dir)
    audit = audit_mod.AuditLog(store=store)

    intake_id = getattr(args, "intake_id", None)
    if intake_id:
        entries = audit.get_entries(intake_id)
        print(json.dumps([{"event": e.event, "timestamp": e.timestamp} for e in entries]))
    else:
        records = store.list_all()
        all_entries = []
        for r in records:
            for e in audit.get_entries(r.intake_id):
                all_entries.append({"intake_id": r.intake_id, "event": e.event, "timestamp": e.timestamp})
        print(json.dumps(all_entries))
    return 0


def cmd_quarantine_list(args) -> int:
    config_mod = _load_dep("config")
    store_mod = _load_dep("store")
    audit_mod = _load_dep("audit")
    recovery_mod = _load_dep("recovery")

    cfg = config_mod.load_config(Path(args.config))
    board_dir = Path(args.board)

    store = store_mod.IntakeStore(board_dir=board_dir)
    audit = audit_mod.AuditLog(store=store)
    manager = recovery_mod.RecoveryManager(store=store, audit=audit, config=cfg.recovery)

    items = manager.list_quarantined()
    print(json.dumps([{"intake_id": item.intake_id, "reason": item.reason} for item in items]))
    return 0


def cmd_replay(args) -> int:
    config_mod = _load_dep("config")
    store_mod = _load_dep("store")
    audit_mod = _load_dep("audit")
    recovery_mod = _load_dep("recovery")
    hcw_adapter_mod = _load_dep("hcw_adapter")

    cfg = config_mod.load_config(Path(args.config))
    board_dir = Path(args.board)

    store = store_mod.IntakeStore(board_dir=board_dir)
    audit = audit_mod.AuditLog(store=store)
    manager = recovery_mod.RecoveryManager(store=store, audit=audit, config=cfg.recovery)
    adapter = hcw_adapter_mod.DryRunSink()

    result = manager.operator_replay(args.intake_id, adapter=adapter)
    print(json.dumps({"intake_id": result.intake_id, "status": "replayed"}))
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "validate-config":
        return cmd_validate_config(args)
    elif args.command == "ingest-fixture":
        return cmd_ingest_fixture(args)
    elif args.command == "dry-run":
        return cmd_ingest_fixture(args, dry_run_override=True)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "audit":
        return cmd_audit(args)
    elif args.command == "quarantine-list":
        return cmd_quarantine_list(args)
    elif args.command == "replay":
        return cmd_replay(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
