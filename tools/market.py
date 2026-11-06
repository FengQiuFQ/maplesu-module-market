#!/usr/bin/env python3
"""Import and publish MapleSU's independent static market. Downloaded code is never run."""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://abcz316.github.io/SKRoot-linuxKernelRoot/skroot_pro_app/module_market.json"
HEADERS = {"User-Agent": "MapleSU-Market-Importer/1", "Accept": "application/vnd.github+json"}
MAX_DOWNLOAD = 512 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(path: Path, value: object) -> None:
    write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    temporary = path.with_name(path.name + ".download-tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def path_for(root: Path, relative: str) -> Path:
    parsed = urllib.parse.urlsplit(relative)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "\\" in relative:
        raise ValueError(f"expected relative static path: {relative}")
    decoded = urllib.parse.unquote(parsed.path)
    parts = PurePosixPath(decoded).parts
    if not parts or decoded.startswith("/") or any(part in (".", "..") for part in parts):
        raise ValueError(f"invalid static path: {relative}")
    target = (root / decoded).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"path leaves static root: {relative}")
    return target


def fetch(url: str, *, limit: int = MAX_DOWNLOAD) -> tuple[bytes, dict]:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError(f"HTTPS required: {url}")
    last = None
    for attempt in range(3):
        started = time.monotonic()
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=60) as response:
                chunks, size = [], 0
                while chunk := response.read(128 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ValueError(f"download exceeds {limit} bytes: {url}")
                    chunks.append(chunk)
                data = b"".join(chunks)
                return data, {
                    "url": url, "final_url": response.url, "http_status": response.status,
                    "bytes": size, "sha256": digest(data), "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "observed_at": now(), "etag": response.headers.get("ETag"),
                }
        except (OSError, urllib.error.URLError) as error:
            last = error
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(f"download failed: {url}: {last}")


def inspect_zip(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if not names:
            raise ValueError("empty ZIP")
        for entry in archive.infolist():
            name = entry.filename.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in PurePosixPath(name).parts:
                raise ValueError(f"unsafe ZIP entry: {name}")
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failed: {bad}")
        return names


def safe_component(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._+-]{1,128}", value) or value in (".", ".."):
        raise ValueError(f"invalid module id/version path component: {value}")
    return value


def module_release(module: dict) -> dict:
    return {key: module[key] for key in (
        "ver", "update_date", "chn_name", "author", "type", "compatibility", "package",
        "source_url", "source_index", "changelog_url", "upstream") if key in module}


def refresh_module_indexes(root: Path, catalog: dict) -> None:
    pinned = {identity: position for position, identity in enumerate(catalog.get("pinned_module_ids", []))}
    catalog["module_list"].sort(key=lambda module: pinned.get(module["id32"], len(pinned)))
    for module in catalog["module_list"]:
        source_bytes = path_for(root, module["source_url"]).read_bytes()
        module["source_index"] = {"path": module["source_url"], "sha256": digest(source_bytes), "size": len(source_bytes)}
        relative = f"modules/{safe_component(module['id32'])}/module.json"
        path = path_for(root, relative)
        index = json.loads(path.read_bytes()) if path.exists() else {
            "schema_version": 1, "id32": module["id32"], "releases": []}
        current = module_release(module)
        existing = next((release for release in index["releases"] if release["ver"] == module["ver"]), None)
        if existing and existing["package"] != current["package"]:
            raise ValueError(f"release version already has different bytes: {module['id32']} {module['ver']}")
        if not existing:
            index["releases"].append(current)
        else:
            index["releases"][index["releases"].index(existing)] = current
        index.update({"name": module["chn_name"], "latest_version": module["ver"],
                      "compatibility": module["compatibility"]})
        dump(path, index)
        payload = path.read_bytes()
        module["module_index"] = {"path": relative, "sha256": digest(payload), "size": len(payload)}


def add_local(root: Path, package_path: Path, native_id: str | None, native_member: str | None, release_date: str) -> dict:
    if bool(native_id) != bool(native_member):
        raise ValueError("native id and library member must be supplied together")
    datetime.strptime(release_date, "%Y-%m-%d")
    package = package_path.read_bytes()
    members = inspect_zip(package)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        native = archive.read(native_member) if native_member else None
        if native is not None and native_id.encode("ascii") + b"\0" not in native:
            raise ValueError("native module identity not present in selected library")
        prop_path = "payload/module.prop" if native_member else "module.prop"
        prop_bytes = archive.read(prop_path)
        prop_text = prop_bytes.decode("utf-8-sig")
        source = archive.read("webroot/source.zip") if "webroot/source.zip" in members else None
    props = dict(line.split("=", 1) for line in prop_text.splitlines() if "=" in line and not line.startswith("#"))
    for required in ("name", "version", "author"):
        if not props.get(required):
            raise ValueError(f"module.prop missing {required}")
    native_id = safe_component(native_id or props.get("id", ""))
    version = props["version"]
    version_path = safe_component(re.sub(r"[^A-Za-z0-9._+-]+", "_", version).strip("_"))
    relative = f"packages/{native_id}/{version_path}/module.zip"
    destination = path_for(root, relative)
    if destination.exists() and destination.read_bytes() != package:
        raise ValueError("same module id/version already has different ZIP bytes")
    catalog = json.loads((root / "market.json").read_bytes())
    existing = next((module for module in catalog["module_list"] if module["id32"] == native_id), None)
    if existing and existing["ver"] != version:
        raise ValueError("existing module has another version; archive it and explicitly select latest before importing")
    origin = {"kind": "user-supplied-package", "file_name": package_path.name,
              "sha256": digest(package), "size": len(package),
              "payload_module_prop" if native_member else "module_prop": props,
              "module_prop_path": prop_path, "release_date_basis": "maintainer-supplied release date"}
    if native is not None:
        origin["native_identity"] = {"id32": native_id, "member": native_member, "sha256": digest(native)}
    original = {"chn_name": props["name"], "eng_name": props["name"], "ver": version,
                "author": props["author"], "desc": props.get("description", ""), "id32": native_id,
                "update_date": release_date, "origin": origin}
    snapshot_bytes = (json.dumps({"module_list": [original]}, ensure_ascii=False, indent=2) + "\n").encode()
    snapshot_path = f"upstream/local-{digest(snapshot_bytes)}.json"
    write(root / snapshot_path, snapshot_bytes)
    snapshots = catalog.setdefault("additional_snapshots", [])
    snapshot = {"kind": "user-supplied-package", "path": snapshot_path, "sha256": digest(snapshot_bytes)}
    if snapshot not in snapshots:
        snapshots.append(snapshot)
    source_id = digest(("user-supplied-package:" + digest(package)).encode())[:24]
    source_url = f"sources/{source_id}/index.json"
    source_archive = None
    if source is not None:
        inspect_zip(source)
        source_path = f"sources/{source_id}/source.zip"
        write(root / source_path, source)
        source_archive = {"path": source_path, "sha256": digest(source), "size": len(source)}
    dump(root / source_url, {"kind": "user-supplied-package", "archive": source_archive,
                            "source_available": source is not None, "origin": origin,
                            "note": "对应源码随原始模块包提供。" if source is not None else
                                    "用户提供此模块 ZIP；未提供可对应此包的源码归档。"})
    changelog_url = f"changelogs/{native_id}/{version_path}.md"
    write(root / changelog_url, (f"# {props['name']} {version}\n\n作者：{props['author']}\n\n"
                               f"来源：用户提供 `{package_path.name}`。\n\n"
                               f"收录日期：{release_date}。\n\n"
                               "本条仅记录用户提供版本，未附独立实现变更说明。\n").encode())
    write(destination, package)
    item = {**original, "type": "SKROOT_PRO" if native_member else "KERNEL_SU",
            "compatibility": {"modes": ["MapleSU_Ultra"], "normal_supported": False, "device_validation": "pending"},
            "download_url": relative, "sha256": digest(package), "size": len(package),
            "package": {"path": relative, "sha256": digest(package), "size": len(package)},
            "source_url": source_url, "changelog_url": changelog_url,
            "mirrors": {"primary": relative, "backup": relative}, "upstream": original,
            "archive_entry_count": len(members)}
    if existing:
        catalog["module_list"][catalog["module_list"].index(existing)] = item
    else:
        catalog["module_list"].append(item)
    refresh_module_indexes(root, catalog)
    catalog["generated_at"] = now()
    dump(root / "market.json", catalog)
    (root / "market.json.sig").unlink(missing_ok=True)
    return {"added_id32": native_id, "version": version, "sha256": digest(package),
            "size": len(package), "module_count": len(catalog["module_list"])}


def github_source(url: str, root: Path, observations: list[dict]) -> tuple[bytes, dict]:
    parsed = urllib.parse.urlsplit(url)
    parts = urllib.parse.unquote(parsed.path).strip("/").split("/")
    if parsed.netloc != "github.com" or len(parts) < 5 or parts[2] != "tree":
        raise ValueError(f"unsupported source tree URL: {url}")
    owner, repo, _, branch, *subpath = parts
    cache = root / "upstream" / "github" / owner / repo
    ref_file = cache / f"{branch}.commit.json"
    if ref_file.exists():
        commit = json.loads(ref_file.read_text(encoding="utf-8"))
    else:
        payload, observation = fetch(f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}", limit=8 * 1024 * 1024)
        observations.append(observation)
        commit = json.loads(payload)
        dump(ref_file, commit)
    revision = commit["sha"]
    tree_file = cache / f"{revision}.tree.json"
    if tree_file.exists():
        tree = json.loads(tree_file.read_text(encoding="utf-8"))
    else:
        payload, observation = fetch(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{revision}?recursive=1", limit=32 * 1024 * 1024)
        observations.append(observation)
        tree = json.loads(payload)
        if tree.get("truncated"):
            raise ValueError("GitHub recursive tree truncated; source import incomplete")
        dump(tree_file, tree)
    prefix = "/".join(subpath) + "/"
    blobs = [item for item in tree["tree"] if item["type"] == "blob" and item["path"].startswith(prefix)]
    if not blobs:
        raise ValueError(f"source subtree missing: {url}")

    def read_blob(item: dict) -> tuple[dict, bytes]:
        cached = cache / "blobs" / item["sha"]
        if cached.exists():
            content = cached.read_bytes()
        else:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{revision}/" + urllib.parse.quote(item["path"], safe="/")
            content, observation = fetch(raw_url)
            observations.append(observation)
            if hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest() != item["sha"]:
                raise ValueError(f"Git blob checksum mismatch: {item['path']}")
            write(cached, content)
        return item, content

    output, file_index = io.BytesIO(), []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            downloaded = list(pool.map(read_blob, blobs))
        for item, content in sorted(downloaded, key=lambda pair: pair[0]["path"]):
            relative = item["path"][len(prefix):]
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
            file_index.append({"path": relative, "size": len(content), "sha256": digest(content), "git_blob": item["sha"]})
    return output.getvalue(), {"kind": "github-tree", "upstream_url": url, "commit": revision, "path": prefix.rstrip("/"), "files": file_index}


def import_upstream(root: Path, url: str, report_path: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    previous_path = root / "market.json"
    previous = json.loads(previous_path.read_bytes()) if previous_path.exists() else {}
    payload, observation = fetch(url, limit=8 * 1024 * 1024)
    upstream = json.loads(payload)
    modules = upstream["module_list"]
    ids = [module["id32"] for module in modules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate upstream module id32")
    snapshot = f"upstream/catalog-{digest(payload)}.json"
    write(root / snapshot, payload)
    observations = [observation]
    overrides_path = root / "upstream-overrides.json"
    overrides = json.loads(overrides_path.read_bytes()) if overrides_path.exists() else {}
    sources = {}
    imported = []
    for number, original in enumerate(modules, 1):
        resolution = overrides.get(original["id32"], {})
        module_id, version = safe_component(original["id32"]), safe_component(original["ver"])
        package_path = f"packages/{module_id}/{version}/module.zip"
        destination = root / package_path
        if destination.exists():
            package = destination.read_bytes()
        else:
            package, observed = fetch(resolution.get("download_url", original["download_url"]))
            observations.append(observed)
            inspect_zip(package)
            write(destination, package)
        members = inspect_zip(package)
        if resolution:
            member = resolution["evidence"]["package_member"]
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                if original["id32"].encode() not in archive.read(member):
                    raise ValueError(f"resolved package identity mismatch: {module_id}")
        source_url = resolution.get("source_url", original.get("source_url", ""))
        if source_url not in sources:
            source_id = digest(source_url.encode())[:24]
            source_directory = root / "sources" / source_id
            source_index = source_directory / "index.json"
            if source_index.exists():
                index = json.loads(source_index.read_text(encoding="utf-8"))
            else:
                if not source_url:
                    index = {"kind": "not-supplied", "upstream_url": "", "archive": None}
                elif urllib.parse.urlsplit(source_url).netloc == "github.com":
                    source_data, index = github_source(source_url, root, observations)
                    inspect_zip(source_data)
                    write(source_directory / "source.zip", source_data)
                    index["archive"] = {"path": f"sources/{source_id}/source.zip", "sha256": digest(source_data), "size": len(source_data)}
                else:
                    source_data, observed = fetch(source_url)
                    observations.append(observed)
                    inspect_zip(source_data)
                    write(source_directory / "source.zip", source_data)
                    index = {"kind": "upstream-archive", "upstream_url": source_url,
                             "archive": {"path": f"sources/{source_id}/source.zip", "sha256": digest(source_data), "size": len(source_data)}}
                dump(source_index, index)
            sources[source_url] = f"sources/{source_id}/index.json"
        changelog_path = f"changelogs/{module_id}/{version}.md"
        upstream_changelog = original.get("changelog_url", "")
        if upstream_changelog:
            change_bytes, observed = fetch(upstream_changelog, limit=4 * 1024 * 1024)
            observations.append(observed)
            change_text = change_bytes.decode("utf-8-sig", errors="replace")
            write(root / f"changelogs/{module_id}/{version}.upstream.txt", change_bytes)
        else:
            change_text = "上游清单未提供独立更新记录。\n\n本次版本说明（原文）：\n\n" + original.get("desc", "")
        changelog = f"# {original['chn_name']} {version}\n\n作者：{original['author']}\n\n上游更新日期：{original['update_date']}\n\n{change_text}\n"
        write(root / changelog_path, changelog.encode())
        item = dict(original)
        item.update({
            "type": "SKROOT_PRO", "compatibility": {"modes": ["MapleSU_Ultra"], "normal_supported": False, "device_validation": "pending"},
            "download_url": package_path, "sha256": digest(package), "size": len(package),
            "package": {"path": package_path, "sha256": digest(package), "size": len(package)},
            "source_url": sources[source_url], "changelog_url": changelog_path,
            "mirrors": {"primary": package_path, "backup": package_path}, "upstream": original,
            "archive_entry_count": len(members),
        })
        if resolution:
            item["upstream_resolution"] = resolution
        imported.append(item)
        print(f"[{number}/{len(modules)}] {original['chn_name']} {version} ({len(package)} bytes)", flush=True)
    catalog = {
        "schema_version": 1, "catalog_id": "maplesu", "generated_at": now(),
        "official_mirrors": {
            "primary": {"base_url": "https://fengqiufq.github.io/maplesu-module-market/", "published": False},
            "backup": {"base_url": "https://raw.githubusercontent.com/FengQiuFQ/maplesu-module-market/main/", "published": False}},
        "signature": {"algorithm": "SHA256withECDSA", "encoding": "base64-der", "curve": "P-256", "path": "market.json.sig", "required": True},
        "upstream_snapshot": {"url": url, "path": snapshot, "sha256": digest(payload)},
        "module_list": imported,
    }
    local_modules = [module for module in previous.get("module_list", [])
                     if module.get("origin", {}).get("kind") == "user-supplied-package"]
    if {module["id32"] for module in local_modules} & set(ids):
        raise ValueError("upstream module id collides with a user-provided module; select latest explicitly")
    catalog["module_list"].extend(local_modules)
    if previous.get("additional_snapshots"):
        catalog["additional_snapshots"] = previous["additional_snapshots"]
    if previous.get("pinned_module_ids"):
        catalog["pinned_module_ids"] = previous["pinned_module_ids"]
    refresh_module_indexes(root, catalog)
    dump(root / "market.json", catalog)
    # A changed import always invalidates an old release signature.
    (root / "market.json.sig").unlink(missing_ok=True)
    report = {"observed_at": now(), "module_count": len(imported), "source_count": len(sources),
              "upstream": observation, "observations": observations,
              "official_deployment": "official-mirrors-configured-pending-publication", "network_scope": "current-workstation-only"}
    dump(report_path, report)
    return report


def verify(root: Path, public_key: Path | None = None, allow_unsigned: bool = False) -> dict:
    payload = (root / "market.json").read_bytes()
    catalog = json.loads(payload)
    if catalog.get("schema_version") != 1 or catalog.get("catalog_id") != "maplesu":
        raise ValueError("unsupported catalog identity/schema")
    signature_policy = catalog.get("signature", {})
    if signature_policy.get("algorithm") != "SHA256withECDSA" or signature_policy.get("curve") != "P-256" or signature_policy.get("encoding") != "base64-der":
        raise ValueError("unsupported catalog signature policy")
    if public_key:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        key = serialization.load_pem_public_key(public_key.read_bytes())
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError("P-256 EC public key required")
        signature = base64.b64decode(path_for(root, catalog["signature"]["path"]).read_bytes().strip(), validate=True)
        key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
    elif not allow_unsigned:
        raise ValueError("trusted --public-key required; use --allow-unsigned only for local import checks")
    seen, checked_sources = set(), set()

    def verify_release(release: dict, identity: str) -> None:
        package = release["package"]
        data = path_for(root, package["path"]).read_bytes()
        if len(data) != package["size"] or digest(data) != package["sha256"]:
            raise ValueError(f"package digest/size mismatch: {identity}")
        inspect_zip(data)
        path_for(root, release["changelog_url"]).read_bytes()
        if release["source_url"] not in checked_sources:
            raw_source_index = path_for(root, release["source_url"]).read_bytes()
            if release.get("source_index"):
                metadata = release["source_index"]
                if metadata["path"] != release["source_url"] or len(raw_source_index) != metadata["size"] or digest(raw_source_index) != metadata["sha256"]:
                    raise ValueError(f"source index digest/size mismatch: {identity}")
            index = json.loads(raw_source_index)
            archive = index.get("archive")
            if archive:
                source = path_for(root, archive["path"]).read_bytes()
                if len(source) != archive["size"] or digest(source) != archive["sha256"]:
                    raise ValueError(f"source archive digest/size mismatch: {identity}")
                inspect_zip(source)
            checked_sources.add(release["source_url"])

    for module in catalog["module_list"]:
        identity = module["id32"]
        if identity in seen:
            raise ValueError(f"duplicate id32: {identity}")
        seen.add(identity)
        package = module["package"]
        verify_release(module, identity)
        if module["sha256"] != package["sha256"] or module["size"] != package["size"] or module["download_url"] != package["path"]:
            raise ValueError(f"inconsistent package fields: {identity}")
        if module.get("module_index"):
            metadata = module["module_index"]
            raw = path_for(root, metadata["path"]).read_bytes()
            if len(raw) != metadata["size"] or digest(raw) != metadata["sha256"]:
                raise ValueError(f"module index digest/size mismatch: {identity}")
            index = json.loads(raw)
            if index["id32"] != identity or index["latest_version"] != module["ver"]:
                raise ValueError(f"module index identity/latest mismatch: {identity}")
            versions = set()
            for release in index["releases"]:
                if release["ver"] in versions:
                    raise ValueError(f"duplicate release version: {identity}")
                versions.add(release["ver"])
                verify_release(release, identity)
            current = next((release for release in index["releases"] if release["ver"] == module["ver"]), None)
            if current != module_release(module):
                raise ValueError(f"module index latest release mismatch: {identity}")
        for mirror_path in module["mirrors"].values():
            if mirror_path != package["path"]:
                raise ValueError(f"mirror package mismatch: {identity}")
        if module["type"] not in ("SKROOT_PRO", "KERNEL_SU") or module["compatibility"]["modes"] != ["MapleSU_Ultra"]:
            raise ValueError(f"unexpected imported module compatibility: {identity}")
    snapshot = catalog["upstream_snapshot"]
    snapshot_bytes = path_for(root, snapshot["path"]).read_bytes()
    if digest(snapshot_bytes) != snapshot["sha256"]:
        raise ValueError("upstream snapshot digest mismatch")
    original_modules = json.loads(snapshot_bytes)["module_list"]
    for additional in catalog.get("additional_snapshots", []):
        raw = path_for(root, additional["path"]).read_bytes()
        if digest(raw) != additional["sha256"]:
            raise ValueError("additional source snapshot digest mismatch")
        original_modules.extend(json.loads(raw)["module_list"])
    if {module["id32"] for module in original_modules} != seen:
        raise ValueError("imported module set differs from complete upstream snapshot")
    for original in original_modules:
        imported = next(module for module in catalog["module_list"] if module["id32"] == original["id32"])
        if imported["upstream"] != original:
            raise ValueError(f"upstream metadata changed: {original['id32']}")
    return {"modules_verified": len(seen), "sources_verified": len(checked_sources), "catalog_signature_verified": public_key is not None}


def sign(root: Path, private_key: Path) -> None:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    if private_key.resolve().is_relative_to(ROOT):
        raise ValueError("release private key must be stored outside the market tree")
    key = serialization.load_pem_private_key(private_key.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("P-256 EC private key required")
    signature = key.sign((root / "market.json").read_bytes(), ec.ECDSA(hashes.SHA256()))
    write(root / "market.json.sig", base64.b64encode(signature) + b"\n")


def keygen(private_key: Path, public_key: Path, spki_out: Path) -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    if private_key.resolve().is_relative_to(ROOT):
        raise ValueError("release private key must be outside the market tree")
    if any(path.exists() for path in (private_key, public_key, spki_out)):
        raise ValueError("key generation never replaces an existing key")
    key = ec.generate_private_key(ec.SECP256R1())
    private_key.parent.mkdir(parents=True, exist_ok=True)
    with private_key.open("xb") as output:
        output.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    os.chmod(private_key, 0o600)
    public = key.public_key()
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    write(public_key, public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    write(spki_out, base64.b64encode(der) + b"\n")
    return {"public_key": str(public_key), "spki_der_base64": str(spki_out), "key_id_sha256": digest(der),
            "private_key": str(private_key), "private_key_content": "never printed or published"}


def probe(base_url: str, report_path: Path) -> dict:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("official probe requires a real HTTPS base URL")
    observations = []
    for attempt in range(3):
        _, observed = fetch(base_url.rstrip("/") + "/market.json", limit=8 * 1024 * 1024)
        observations.append(observed)
    report = {"base_url": base_url, "observations": observations, "network_scope": "current-workstation-only",
              "china_network_verified": False, "note": "Single workstation result; carrier/region must be independently recorded."}
    dump(report_path, report)
    return report


def export_static(root: Path, output: Path, public_key: Path) -> dict:
    verify(root, public_key)
    if output.exists():
        raise ValueError("static export output must be a new directory")
    output.mkdir(parents=True)
    for directory in ("packages", "sources", "changelogs", "upstream", "modules"):
        shutil.copytree(root / directory, output / directory,
                        ignore=shutil.ignore_patterns("blobs") if directory == "upstream" else None)
    for name in ("market.json", "market.json.sig"):
        shutil.copy2(root / name, output / name)
    write(output / ".nojekyll", b"")
    result = verify(output, public_key)
    result.update({"deployment": "exported-with-original-signature", "output": str(output),
                   "catalog_sha256": digest((output / "market.json").read_bytes())})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import")
    importer.add_argument("--upstream", default=UPSTREAM)
    importer.add_argument("--report", type=Path, default=ROOT / "import-report.json")
    local = commands.add_parser("add-local")
    local.add_argument("--package", type=Path, required=True)
    local.add_argument("--native-id")
    local.add_argument("--native-member")
    local.add_argument("--release-date", required=True)
    validator = commands.add_parser("verify")
    validator.add_argument("--public-key", type=Path)
    validator.add_argument("--allow-unsigned", action="store_true")
    signer = commands.add_parser("sign")
    signer.add_argument("--private-key", type=Path, required=True)
    generator = commands.add_parser("keygen")
    generator.add_argument("--private-key", type=Path, required=True)
    generator.add_argument("--public-key", type=Path, required=True)
    generator.add_argument("--spki-out", type=Path, required=True)
    publisher = commands.add_parser("publish")
    publisher.add_argument("--private-key", type=Path, required=True)
    publisher.add_argument("--public-key", type=Path, required=True)
    publisher.add_argument("--primary-base", required=True)
    publisher.add_argument("--backup-base", required=True)
    publisher.add_argument("--out", type=Path, required=True)
    exporter = commands.add_parser("export")
    exporter.add_argument("--public-key", type=Path, required=True)
    exporter.add_argument("--out", type=Path, required=True)
    network = commands.add_parser("probe")
    network.add_argument("--base-url", required=True)
    network.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "import":
        result = import_upstream(root, args.upstream, args.report)
    elif args.command == "add-local":
        result = add_local(root, args.package, args.native_id, args.native_member, args.release_date)
    elif args.command == "verify":
        result = verify(root, args.public_key, args.allow_unsigned)
    elif args.command == "sign":
        verify(root, allow_unsigned=True)
        sign(root, args.private_key)
        result = {"signature_written": "market.json.sig"}
    elif args.command == "keygen":
        result = keygen(args.private_key, args.public_key, args.spki_out)
    elif args.command == "export":
        result = export_static(root, args.out, args.public_key)
    elif args.command == "publish":
        verify(root, allow_unsigned=True)
        if args.out.exists():
            raise ValueError("publish output must be a new directory")
        for base in (args.primary_base, args.backup_base):
            parsed = urllib.parse.urlsplit(base)
            if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
                raise ValueError("official mirrors require explicit HTTPS base URLs")
        args.out.mkdir(parents=True)
        for directory in ("packages", "sources", "changelogs", "upstream", "modules"):
            shutil.copytree(root / directory, args.out / directory, ignore=shutil.ignore_patterns("blobs") if directory == "upstream" else None)
        catalog = json.loads((root / "market.json").read_bytes())
        catalog["official_mirrors"] = {"primary": {"base_url": args.primary_base.rstrip("/") + "/", "published": False},
                                       "backup": {"base_url": args.backup_base.rstrip("/") + "/", "published": False}}
        catalog["generated_at"] = now()
        dump(args.out / "market.json", catalog)
        sign(args.out, args.private_key)
        result = verify(args.out, args.public_key)
        result["deployment"] = "staged-not-uploaded"
    else:
        result = probe(args.base_url, args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
