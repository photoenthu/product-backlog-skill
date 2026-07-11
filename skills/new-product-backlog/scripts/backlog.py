#!/usr/bin/env python3
"""Command-line interface for the new-product-backlog skill. The ONLY supported
way to mutate the backlog JSON file (the local editor server calls the same
`core` functions). Pure stdlib.

Subcommands:
  init <path>
  add <path> --name N [--description D --status S --priority P
       --depends BL-001,BL-002 --dnbb YYYY-MM-DD --notes T
       --artifact label=url (repeatable)]
  edit <path> <id> [same flags as add, plus --clear-dnbb]
  discard <path> <id> [--notes T]
  rm <path> <id> [--force]
  get <path> <id>
  list <path> [--status S --priority P]
  validate <path>
  next-id <path>
  now
  serve <path> [--port N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402


def _parse_depends(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [d.strip() for d in value.split(",") if d.strip()]


def _parse_artifacts(pairs: list[str] | None) -> list[dict] | None:
    if not pairs:
        return None
    out = []
    for pair in pairs:
        if "=" not in pair:
            raise core.BacklogError(f"--artifact must be label=url, got: {pair}")
        label, url = pair.split("=", 1)
        out.append({"label": label.strip(), "url": url.strip()})
    return out


def _add_common_flags(sp, require_name):
    sp.add_argument("--name", required=require_name)
    sp.add_argument("--description")
    sp.add_argument("--status", choices=core.STATUSES)
    sp.add_argument("--priority", choices=core.PRIORITIES)
    sp.add_argument("--depends", help="comma-separated BL-NNN ids")
    sp.add_argument("--dnbb", help="doNotBuildBefore date YYYY-MM-DD")
    sp.add_argument("--notes")
    sp.add_argument("--artifact", action="append", help="label=url (repeatable)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backlog.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init"); sp.add_argument("path")
    sp = sub.add_parser("add"); sp.add_argument("path"); _add_common_flags(sp, True)
    sp = sub.add_parser("edit"); sp.add_argument("path"); sp.add_argument("id")
    _add_common_flags(sp, False); sp.add_argument("--clear-dnbb", action="store_true")
    sp = sub.add_parser("discard"); sp.add_argument("path"); sp.add_argument("id"); sp.add_argument("--notes")
    sp = sub.add_parser("rm"); sp.add_argument("path"); sp.add_argument("id"); sp.add_argument("--force", action="store_true")
    sp = sub.add_parser("get"); sp.add_argument("path"); sp.add_argument("id")
    sp = sub.add_parser("list"); sp.add_argument("path")
    sp.add_argument("--status", choices=core.STATUSES); sp.add_argument("--priority", choices=core.PRIORITIES)
    sp = sub.add_parser("validate"); sp.add_argument("path")
    sp = sub.add_parser("next-id"); sp.add_argument("path")
    sub.add_parser("now")
    sp = sub.add_parser("serve"); sp.add_argument("path"); sp.add_argument("--port", type=int, default=8765)
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    cmd = args.cmd

    try:
        if cmd == "now":
            print(core.now_iso()); return 0

        if cmd == "init":
            created = core.init(Path(args.path))
            print(f"{'created' if created else 'exists'}: {args.path}"); return 0

        if cmd == "serve":
            import server
            server.run_server(Path(args.path), args.port)
            return 0

        path = Path(args.path)

        if cmd == "next-id":
            print(core.next_id(core.load(path))); return 0

        if cmd == "add":
            data = core.load(path)
            item = core.add_item(
                data, name=args.name, description=args.description or "",
                status=args.status or core.DEFAULT_STATUS,
                priority=args.priority or core.DEFAULT_PRIORITY,
                dependencies=_parse_depends(args.depends),
                do_not_build_before=args.dnbb, notes=args.notes or "",
                artifacts=_parse_artifacts(args.artifact),
            )
            core.save(path, data)
            print(item["id"]); return 0

        if cmd == "edit":
            data = core.load(path)
            changes = {}
            if args.name is not None: changes["name"] = args.name
            if args.description is not None: changes["description"] = args.description
            if args.status is not None: changes["status"] = args.status
            if args.priority is not None: changes["priority"] = args.priority
            if args.depends is not None: changes["dependencies"] = _parse_depends(args.depends)
            if args.notes is not None: changes["notes"] = args.notes
            if args.artifact is not None: changes["artifacts"] = _parse_artifacts(args.artifact)
            if args.clear_dnbb: changes["do_not_build_before"] = None
            elif args.dnbb is not None: changes["do_not_build_before"] = args.dnbb
            core.edit_item(data, args.id, **changes)
            core.save(path, data)
            print(f"edited {args.id}"); return 0

        if cmd == "discard":
            data = core.load(path)
            core.discard_item(data, args.id, notes=args.notes)
            core.save(path, data)
            print(f"discarded {args.id}"); return 0

        if cmd == "rm":
            data = core.load(path)
            core.remove_item(data, args.id, force=args.force)
            core.save(path, data)
            print(f"removed {args.id}"); return 0

        if cmd == "get":
            print(json.dumps(core.get_item(core.load(path), args.id), indent=2)); return 0

        if cmd == "list":
            items = core.list_items(core.load(path), status=args.status, priority=args.priority)
            print(json.dumps(items, indent=2)); return 0

        if cmd == "validate":
            problems = core.validate(core.load(path))
            if not problems:
                print(f"ok: {args.path}"); return 0
            for p in problems:
                print(p, file=sys.stderr)
            return 1

    except core.BacklogError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
