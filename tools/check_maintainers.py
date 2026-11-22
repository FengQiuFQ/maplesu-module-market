#!/usr/bin/env python3
"""Validate contributor ownership and provenance records; --release requires completed review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HANDLE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")


def check(root: Path, release: bool = False) -> dict:
    root = root.resolve()
    catalog_file = root / ("market.json" if (root / "market.json").is_file() else "index.json")
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    entries = catalog["module_list"] if isinstance(catalog, dict) else catalog
    ids = {str(item.get("id32", item.get("id"))) for item in entries}
    document = json.loads((root / "maintainers.json").read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not isinstance(document.get("entries"), dict):
        raise ValueError("maintainers.json requires schema_version=1 and an entries object")
    records = document["entries"]
    if set(records) != ids:
        raise ValueError(f"Maintenance records must match the catalog: missing={sorted(ids-set(records))}, extra={sorted(set(records)-ids)}")
    pending = []
    for identity, record in records.items():
        people = record.get("maintainers")
        status = record.get("status")
        if not isinstance(people, list) or any(not isinstance(p, str) or not HANDLE.fullmatch(p) for p in people):
            raise ValueError(f"Invalid GitHub maintainer handles: {identity}")
        if len(set(people)) != len(people) or status not in {"pending", "ready"}:
            raise ValueError(f"Invalid maintenance status or duplicate handles: {identity}")
        if status == "pending":
            pending.append(identity)
            continue
        if not people or not all(isinstance(record.get(k), str) and record[k].strip() for k in ("origin", "license")):
            raise ValueError(f"Reviewed entry requires maintainer, origin and actual license: {identity}")
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"Reviewed entry requires a versioned provenance evidence file: {identity}")
        for name in evidence:
            if not isinstance(name, str):
                raise ValueError(f"Invalid evidence path: {identity}")
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError(f"Missing or outside provenance evidence: {identity}: {name}")
    if release and pending:
        raise ValueError(f"Release review pending for {len(pending)} entries: {', '.join(sorted(pending))}")
    return dict(entries=len(ids), ready=len(ids)-len(pending), pending=sorted(pending))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.root, args.release), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, OSError) as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
