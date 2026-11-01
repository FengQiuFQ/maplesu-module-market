#!/usr/bin/env python3
"""Check repository paths and text files before publishing the independent market."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "market.json", "market.json.sig", "README.md", "SCHEMA.md", "PUBLISH.md", "requirements.txt", ".gitignore",
    "trust/public-key.pem", "trust/public-key.spki.b64", "tools/market.py",
    ".github/workflows/ci.yml", ".github/workflows/pages.yml", ".github/workflows/sign.yml",
}
CACHE_PARTS = {"__pycache__", ".venv", "node_modules", "blobs", "dist", "_site"}
PRIVATE_MARKER = re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
TEXT_SUFFIXES = {".pem", ".json", ".md", ".txt", ".yml", ".yaml", ".py", ".b64"}


def is_cache(relative: str) -> bool:
    path = Path(relative)
    return bool(set(path.parts) & CACHE_PARTS) or path.suffix == ".pyc" or path.name.endswith(".download-tmp")


def audit_files(root: Path, relatives: list[str]) -> list[str]:
    errors = []
    for relative in relatives:
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            errors.append(f"path leaves publish tree or is a symlink: {relative}")
            continue
        if is_cache(relative):
            errors.append(f"cache/build output: {relative}")
        if ".private" in path.relative_to(root).parts or path.name.startswith("release-private"):
            errors.append(f"private-key path: {relative}")
        if path.suffix.lower() in {".key", ".p12", ".pfx", ".jks"}:
            errors.append(f"private-key container: {relative}")
        if path.suffix.lower() == ".pem" and relative.replace("\\", "/") != "trust/public-key.pem":
            errors.append(f"unexpected PEM file: {relative}")
        if path.is_file() and (path.suffix.lower() in TEXT_SUFFIXES or path.name == ".gitignore"):
            if PRIVATE_MARKER.search(path.read_bytes()):
                errors.append(f"private-key content: {relative}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--all", action="store_true", help="Inspect all files in a prepared tree, instead of Git-tracked files")
    parser.add_argument("--allow-unsigned", action="store_true", help="Only for the signing job before a new signature exists")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.all:
        relatives = [path.relative_to(root).as_posix() for path in root.rglob("*")
                     if path.is_file() and ".git" not in path.relative_to(root).parts]
    else:
        raw = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "."],
                             check=True, stdout=subprocess.PIPE).stdout
        relatives = [name.decode("utf-8") for name in raw.split(b"\0") if name]
    errors = audit_files(root, relatives)
    required = REQUIRED - {"market.json.sig"} if args.allow_unsigned else REQUIRED
    errors.extend(f"missing maintenance file: {name}" for name in sorted(required - set(relatives)))
    print(json.dumps({"files_checked": len(relatives), "errors": errors}, ensure_ascii=False, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
