import base64
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

spec = importlib.util.spec_from_file_location("market", Path(__file__).with_name("market.py"))
market = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market)


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="maplesu-market-test-")
        self.root = Path(self.temporary.name)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("module.prop", "id=sample\nname=Sample\n")
        data = output.getvalue()
        market.write(self.root / "packages/sample/1/module.zip", data)
        self.original = {"id32": "sample", "chn_name": "原名称", "ver": "1", "download_url": "https://upstream.example/module.zip"}
        snapshot = json.dumps({"module_list": [self.original]}).encode()
        market.write(self.root / "upstream/input.json", snapshot)
        market.dump(self.root / "sources/source/index.json", {"archive": None})
        market.write(self.root / "changelogs/sample/1.md", b"original change")
        package = {"path": "packages/sample/1/module.zip", "sha256": market.digest(data), "size": len(data)}
        self.catalog = {
            "schema_version": 1, "catalog_id": "maplesu",
            "signature": {"algorithm": "SHA256withECDSA", "encoding": "base64-der", "curve": "P-256", "path": "market.json.sig", "required": True},
            "upstream_snapshot": {"path": "upstream/input.json", "sha256": market.digest(snapshot)},
            "module_list": [{**self.original, "type": "SKROOT_PRO", "compatibility": {"modes": ["MapleSU_Ultra"]},
                             "package": package, "download_url": package["path"], "sha256": package["sha256"], "size": package["size"],
                             "source_url": "sources/source/index.json", "changelog_url": "changelogs/sample/1.md",
                             "mirrors": {"primary": package["path"], "backup": package["path"]}, "upstream": self.original}],
        }
        market.dump(self.root / "market.json", self.catalog)
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.root / "trusted-public.pem"
        self.public_key.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.signature()

    def tearDown(self):
        self.temporary.cleanup()

    def signature(self):
        signature = self.key.sign((self.root / "market.json").read_bytes(), ec.ECDSA(hashes.SHA256()))
        (self.root / "market.json.sig").write_bytes(base64.b64encode(signature) + b"\n")

    def test_valid_signed_manifest_and_package_are_both_verified(self):
        result = market.verify(self.root, self.public_key)
        self.assertEqual(1, result["modules_verified"])
        self.assertTrue(result["catalog_signature_verified"])

    def test_package_tampering_fails_even_when_manifest_signature_is_valid(self):
        path = self.root / "packages/sample/1/module.zip"
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaisesRegex(ValueError, "package digest/size"):
            market.verify(self.root, self.public_key)

    def test_manifest_tampering_fails_even_when_package_hash_is_valid(self):
        self.catalog["module_list"][0]["chn_name"] = "tampered"
        market.dump(self.root / "market.json", self.catalog)
        with self.assertRaises(Exception):
            market.verify(self.root, self.public_key)

    def test_untrusted_public_key_cannot_replace_pinned_key(self):
        wrong = self.root / "wrong-public.pem"
        wrong.write_bytes(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        with self.assertRaises(Exception):
            market.verify(self.root, wrong)

    def test_unsigned_is_rejected_without_explicit_local_override(self):
        with self.assertRaisesRegex(ValueError, "trusted --public-key"):
            market.verify(self.root)
        self.assertFalse(market.verify(self.root, allow_unsigned=True)["catalog_signature_verified"])

    def test_source_archive_hash_is_checked_independently(self):
        path = self.root / "sources/source/source.zip"
        path.write_bytes(b"tampered")
        market.dump(self.root / "sources/source/index.json", {"archive": {"path": "sources/source/source.zip", "sha256": "0" * 64, "size": 8}})
        with self.assertRaisesRegex(ValueError, "source archive digest/size"):
            market.verify(self.root, self.public_key)

    def test_import_cannot_silently_drop_an_upstream_module(self):
        self.catalog["module_list"] = []
        market.dump(self.root / "market.json", self.catalog)
        self.signature()
        with self.assertRaisesRegex(ValueError, "module set differs"):
            market.verify(self.root, self.public_key)

    def test_paths_must_stay_under_static_root(self):
        for path in ("../private.pem", "/private.pem", "https://upstream.example/private.pem", "%2e%2e/private.pem", "C:\\private.pem"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                market.path_for(self.root, path)

    def test_archive_inspection_never_extracts_traversal_entries(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("../outside", "bad")
        with self.assertRaisesRegex(ValueError, "unsafe ZIP entry"):
            market.inspect_zip(output.getvalue())

    def test_signature_cannot_be_replaced_with_a_package_digest(self):
        (self.root / "market.json.sig").write_bytes(base64.b64encode(bytes.fromhex(self.catalog["module_list"][0]["sha256"])))
        with self.assertRaises(Exception):
            market.verify(self.root, self.public_key)

    def test_signature_algorithm_cannot_be_downgraded_by_catalog(self):
        self.catalog["signature"]["algorithm"] = "SHA-256"
        market.dump(self.root / "market.json", self.catalog)
        self.signature()
        with self.assertRaisesRegex(ValueError, "signature policy"):
            market.verify(self.root, self.public_key)

    def test_module_index_is_authenticated_by_catalog(self):
        market.refresh_module_indexes(self.root, self.catalog)
        market.dump(self.root / "market.json", self.catalog)
        self.signature()
        self.assertTrue(market.verify(self.root, self.public_key)["catalog_signature_verified"])
        index = self.root / self.catalog["module_list"][0]["module_index"]["path"]
        index.write_bytes(index.read_bytes() + b"tampered")
        with self.assertRaisesRegex(ValueError, "module index digest/size"):
            market.verify(self.root, self.public_key)

    def test_source_index_itself_is_authenticated_by_catalog(self):
        market.refresh_module_indexes(self.root, self.catalog)
        market.dump(self.root / "market.json", self.catalog)
        self.signature()
        market.dump(self.root / "sources/source/index.json", {"archive": None, "origin": "tampered"})
        with self.assertRaisesRegex(ValueError, "source index digest/size"):
            market.verify(self.root, self.public_key)

    def local_package(self, *, native_id="local-module", suffix=b""):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("payload/module.prop", "id=payload-id\nname=Local\nversion=1.0.0\nauthor=Tester\n")
            archive.writestr("libmodule_local.so", b"metadata fixture\0" + native_id.encode() + b"\0" + suffix)
        path = self.root / "input.zip"
        path.write_bytes(output.getvalue())
        return path

    def test_user_package_preserves_bytes_and_is_added_without_dropping_upstream(self):
        path = self.local_package()
        original = path.read_bytes()
        result = market.add_local(self.root, path, "local-module", "libmodule_local.so", "2026-11-01")
        self.assertEqual(2, result["module_count"])
        self.assertEqual(original, (self.root / "packages/local-module/1.0.0/module.zip").read_bytes())
        self.signature()
        self.assertEqual(2, market.verify(self.root, self.public_key)["modules_verified"])

    def test_user_package_native_id_must_match_selected_library(self):
        path = self.local_package()
        with self.assertRaisesRegex(ValueError, "native module identity"):
            market.add_local(self.root, path, "wrong-id", "libmodule_local.so", "2026-11-01")

    def test_existing_release_bytes_cannot_be_silently_replaced(self):
        path = self.local_package()
        market.add_local(self.root, path, "local-module", "libmodule_local.so", "2026-11-01")
        path = self.local_package(suffix=b"changed bytes")
        with self.assertRaisesRegex(ValueError, "same module id/version"):
            market.add_local(self.root, path, "local-module", "libmodule_local.so", "2026-11-01")

    def test_script_package_preserves_identity_version_and_original_bytes(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("module.prop", "id=zygisk_lsposed\nname=LSPosed\nversion=v2.1.1 (7790)\nauthor=LSPosed Developers\n")
        path = self.root / "script.zip"
        path.write_bytes(output.getvalue())
        market.add_local(self.root, path, None, None, "2026-11-06")
        catalog = json.loads((self.root / "market.json").read_bytes())
        module = catalog["module_list"][-1]
        self.assertEqual("KERNEL_SU", module["type"])
        self.assertEqual("zygisk_lsposed", module["id32"])
        self.assertEqual("v2.1.1 (7790)", module["ver"])
        self.assertEqual(path.read_bytes(), (self.root / module["package"]["path"]).read_bytes())
        self.signature()
        self.assertEqual(2, market.verify(self.root, self.public_key)["modules_verified"])

    def test_bundled_corresponding_source_is_exported_and_authenticated(self):
        path = self.local_package()
        source = io.BytesIO()
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("src/main.c", "/* Corresponding source fixture. */")
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("webroot/source.zip", source.getvalue())
        market.add_local(self.root, path, "local-module", "libmodule_local.so", "2026-11-06")
        catalog = json.loads((self.root / "market.json").read_bytes())
        index = json.loads((self.root / catalog["module_list"][-1]["source_url"]).read_bytes())
        self.assertTrue(index["source_available"])
        self.assertEqual(source.getvalue(), (self.root / index["archive"]["path"]).read_bytes())
        self.signature()
        self.assertEqual(2, market.verify(self.root, self.public_key)["modules_verified"])

    def test_pinned_order_survives_index_refresh_and_keeps_other_order(self):
        path = self.local_package()
        market.add_local(self.root, path, "local-module", "libmodule_local.so", "2026-11-06")
        catalog = json.loads((self.root / "market.json").read_bytes())
        catalog["pinned_module_ids"] = ["local-module", "sample"]
        market.refresh_module_indexes(self.root, catalog)
        self.assertEqual(["local-module", "sample"], [module["id32"] for module in catalog["module_list"]])
        market.refresh_module_indexes(self.root, catalog)
        self.assertEqual(["local-module", "sample"], [module["id32"] for module in catalog["module_list"]])

    def test_static_export_preserves_catalog_and_signature_bytes(self):
        market.refresh_module_indexes(self.root, self.catalog)
        market.dump(self.root / "market.json", self.catalog)
        self.signature()
        original = {name: (self.root / name).read_bytes() for name in ("market.json", "market.json.sig")}
        cache = self.root / "upstream/github/owner/repo/blobs/cache"
        market.write(cache, b"download cache")
        output = self.root / "_site"
        result = market.export_static(self.root, output, self.public_key)
        self.assertTrue(result["catalog_signature_verified"])
        for name, expected in original.items():
            self.assertEqual(expected, (output / name).read_bytes())
        self.assertFalse((output / "upstream/github/owner/repo/blobs").exists())
        self.assertFalse((output / "trusted-public.pem").exists())


if __name__ == "__main__":
    unittest.main()
