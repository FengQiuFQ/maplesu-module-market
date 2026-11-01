from pathlib import Path
import tempfile
import unittest

import check_publish_tree


class PublishTreeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="market-publish-tree-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_pinned_public_key_is_allowed(self):
        self.write("trust/public-key.pem", b"-----BEGIN PUBLIC KEY-----\nfixture\n")
        self.assertEqual([], check_publish_tree.audit_files(self.root, ["trust/public-key.pem"]))

    def test_private_key_content_is_rejected_even_under_json_name(self):
        marker = b"-----BEGIN " + b"PRIVATE KEY-----\nfixture\n"
        self.write("metadata.json", marker)
        self.assertTrue(any("private-key content" in error for error in check_publish_tree.audit_files(self.root, ["metadata.json"])))

    def test_extra_pem_and_private_container_paths_are_rejected(self):
        for relative in ("tools/key.pem", "signing.key", ".private/release.pem", "release-private.pem"):
            with self.subTest(relative=relative):
                self.write(relative, b"fixture")
                self.assertTrue(check_publish_tree.audit_files(self.root, [relative]))

    def test_caches_and_build_outputs_are_excluded(self):
        for relative in ("tools/__pycache__/market.pyc", "upstream/github/owner/repo/blobs/abc", "_site/market.json", "module.zip.download-tmp"):
            with self.subTest(relative=relative):
                self.assertTrue(check_publish_tree.is_cache(relative))
                self.assertTrue(check_publish_tree.audit_files(self.root, [relative]))

    def test_original_module_zip_is_not_interpreted_as_a_text_secret(self):
        self.write("packages/id/1/module.zip", b"-----BEGIN " + b"PRIVATE KEY-----")
        self.assertEqual([], check_publish_tree.audit_files(self.root, ["packages/id/1/module.zip"]))


if __name__ == "__main__":
    unittest.main()
