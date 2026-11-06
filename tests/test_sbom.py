"""The SBOM must describe mixed licensing, not declare the GPL skills as MIT."""
from __future__ import annotations

import unittest

from scripts import validate_repository as validator


class SbomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = validator.manifest()
        cls.sbom = validator.build_sbom(cls.manifest)
        cls.files = {entry["fileName"]: entry for entry in cls.sbom["files"]}
        cls.contains = {rel["relatedSpdxElement"] for rel in cls.sbom["relationships"]
                        if rel["relationshipType"] == "CONTAINS"}

    def test_document_and_packages_have_the_required_spdx_fields(self) -> None:
        self.assertEqual(self.sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(self.sbom["dataLicense"], "CC0-1.0")
        for key in ("SPDXID", "name", "documentNamespace", "creationInfo", "packages", "files", "relationships"):
            self.assertIn(key, self.sbom)
        self.assertRegex(self.sbom["creationInfo"]["created"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        for package in self.sbom["packages"]:
            for key in ("SPDXID", "name", "downloadLocation", "filesAnalyzed", "licenseConcluded",
                        "licenseDeclared", "copyrightText", "licenseInfoFromFiles", "packageVerificationCode"):
                self.assertIn(key, package)

    def test_licences_match_the_notices(self) -> None:
        licenses = {package["SPDXID"]: package["licenseDeclared"] for package in self.sbom["packages"]}
        self.assertEqual(licenses["SPDXRef-Package-Forge"], "MIT")
        self.assertEqual(licenses["SPDXRef-Package-HouseCARL-Skills"], "GPL-3.0-only")
        gpl = [name for name in self.files if "/skills/housecarl/" in name]
        self.assertTrue(gpl)
        self.assertEqual(self.files[gpl[0]]["licenseConcluded"], "GPL-3.0-only")
        self.assertEqual(self.files["./skyrim_forge/vfs_sandbox.py"]["licenseConcluded"], "MIT")

    def test_every_file_is_contained_once_and_hashed(self) -> None:
        self.assertEqual(len(self.files), len(self.manifest["files"]))
        self.assertEqual(len(self.contains), len(self.files))
        hashes = {entry["fileName"]: entry["checksums"][0]["checksumValue"] for entry in self.sbom["files"]}
        for row in self.manifest["files"]:
            self.assertEqual(hashes["./" + row["path"]], row["sha256"])

    def test_namespace_is_unique_per_commit(self) -> None:
        self.assertIn(validator.VERSION, self.sbom["documentNamespace"])
        self.assertNotIn("example.invalid", self.sbom["documentNamespace"])


if __name__ == "__main__":
    unittest.main()
