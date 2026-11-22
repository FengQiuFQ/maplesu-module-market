import json
from pathlib import Path
import tempfile
import unittest
from check_maintainers import check


class MaintainerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "index.json").write_text('[{"id":"fixture"}]', encoding="utf-8")

    def record(self, value):
        (self.root / "maintainers.json").write_text(json.dumps({"schema_version": 1, "entries": {"fixture": value}}), encoding="utf-8")

    def test_pending_import_passes_structure_but_blocks_release(self):
        self.record(dict(maintainers=[], status="pending"))
        self.assertEqual(["fixture"], check(self.root)["pending"])
        with self.assertRaises(ValueError):
            check(self.root, release=True)

    def test_reviewed_entry_requires_source_evidence(self):
        value = dict(maintainers=["ExampleAuthor"], status="ready", origin="https://example.org/source", license="MIT", evidence=["source.json"])
        self.record(value)
        with self.assertRaises(ValueError):
            check(self.root, release=True)
        (self.root / "source.json").write_text('{}', encoding="utf-8")
        self.assertEqual(1, check(self.root, release=True)["ready"])
        value["evidence"] = ["../outside"]
        self.record(value)
        with self.assertRaises(ValueError):
            check(self.root)

    def test_catalog_and_maintenance_ids_must_match(self):
        self.record(dict(maintainers=[], status="pending"))
        (self.root / "index.json").write_text('[{"id":"new-id"}]', encoding="utf-8")
        with self.assertRaises(ValueError):
            check(self.root)


if __name__ == "__main__":
    unittest.main()
