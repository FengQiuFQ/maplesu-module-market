#!/usr/bin/env python3
"""Copy a complete, verified standalone repository without caches or private keys."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import check_publish_tree
import market

DIRECTORIES = {"packages", "sources", "changelogs", "upstream", "modules", "tools", "trust", ".github"}
FILES = {"market.json", "market.json.sig", "README.md", "SCHEMA.md", "PUBLISH.md", "requirements.txt", ".gitignore", ".gitattributes", "upstream-overrides.json"}


def prepare(root: Path, output: Path) -> dict:
    if output.exists() or output.resolve().is_relative_to(root.resolve()):
        raise ValueError("repository output must be a new directory outside the source tree")
    market.verify(root, root / "trust/public-key.pem")
    selected = sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                      if path.is_file() and not check_publish_tree.is_cache(path.relative_to(root).as_posix())
                      and (path.relative_to(root).parts[0] in DIRECTORIES or path.relative_to(root).as_posix() in FILES))
    errors = check_publish_tree.audit_files(root, selected)
    errors.extend(f"missing maintenance file: {name}" for name in sorted(check_publish_tree.REQUIRED - set(selected)))
    if errors:
        raise ValueError("publish tree check failed: " + "; ".join(errors))
    output.mkdir(parents=True)
    for relative in selected:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)
    result = market.verify(output, output / "trust/public-key.pem")
    result.update({"output": str(output), "files": selected, "file_count": len(selected),
                   "total_bytes": sum((output / relative).stat().st_size for relative in selected),
                   "catalog_sha256": market.digest((output / "market.json").read_bytes())})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=market.ROOT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = prepare(args.root.resolve(), args.out.resolve())
    if args.report:
        market.dump(args.report, result)
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
