#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Dict
import unittest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from gen_version_json import compute_sha256, generate_manifest
from publish_android_apk import KNOWN_APPS, publish_app


class TestEndToEndManifest(unittest.TestCase):
    """End-to-end integration and qualification tests for manifest generation,

    multi-app catalog orchestration, static portal HTML rendering, and schema conformance.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.workspace_root = self.temp_path / "workspace"
        self.web_root = self.temp_path / "web_root"
        self.workspace_root.mkdir(parents=True)
        self.web_root.mkdir(parents=True)

        self.gen_script = _SCRIPTS_DIR / "gen_version_json.py"
        self.publish_script = _SCRIPTS_DIR / "publish_android_apk.py"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_synthetic_apk(
        self,
        rel_path: str,
        content: bytes,
        app_id: str,
        version_code: int,
        version_name: str,
        min_sdk: int = 24,
    ) -> Path:
        apk_path = self.workspace_root / rel_path
        apk_path.parent.mkdir(parents=True, exist_ok=True)
        apk_path.write_bytes(content)

        meta_path = apk_path.parent / "output-metadata.json"
        meta_path.write_text(
            json.dumps(
                {
                    "version": 3,
                    "applicationId": app_id,
                    "elements": [
                        {
                            "versionCode": version_code,
                            "versionName": version_name,
                        }
                    ],
                    "minSdkVersionForDexing": min_sdk,
                }
            ),
            encoding="utf-8",
        )
        return apk_path

    def test_single_app_gen_version_json_cli(self):
        """Verify gen_version_json.py CLI emits all required fields with verified SHA-256."""
        apk_content = b"Synthetic APK payload for standalone manifest verification"
        apk = self._create_synthetic_apk(
            rel_path="octi/app/release/octi-release.apk",
            content=apk_content,
            app_id="com.selfso.octi",
            version_code=20002,
            version_name="2.0.2",
            min_sdk=24,
        )
        expected_sha = hashlib.sha256(apk_content).hexdigest().lower()
        out_json = self.temp_path / "output_single.json"

        cmd = [
            sys.executable,
            str(self.gen_script),
            "--apk",
            str(apk),
            "--output",
            str(out_json),
            "--slug",
            "octi",
            "--title",
            "OCTI Strategy Game",
            "--release-notes",
            "End-to-end test release notes for OCTI.",
            "--published-at",
            "2026-10-22T09:30:00Z",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, f"gen_version_json failed: {proc.stderr}")
        self.assertTrue(out_json.is_file())

        with open(out_json, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        required_fields = [
            "slug",
            "title",
            "applicationId",
            "versionCode",
            "versionName",
            "minSdk",
            "targetSdk",
            "apkUrl",
            "pageUrl",
            "sha256",
            "sizeBytes",
            "publishedAt",
            "releaseNotes",
        ]
        for field in required_fields:
            self.assertIn(field, manifest, f"Missing required field: {field}")

        self.assertEqual(manifest["slug"], "octi")
        self.assertEqual(manifest["title"], "OCTI Strategy Game")
        self.assertEqual(manifest["applicationId"], "com.selfso.octi")
        self.assertEqual(manifest["versionCode"], 20002)
        self.assertEqual(manifest["versionName"], "2.0.2")
        self.assertEqual(manifest["minSdk"], 24)
        self.assertEqual(manifest["targetSdk"], 35)
        self.assertEqual(manifest["sha256"], expected_sha)
        self.assertEqual(manifest["sizeBytes"], len(apk_content))
        self.assertEqual(manifest["publishedAt"], "2026-10-22T09:30:00Z")
        self.assertEqual(manifest["releaseNotes"], "End-to-end test release notes for OCTI.")
        self.assertTrue(re.match(r"^[0-9a-f]{64}$", manifest["sha256"]))

    def test_multi_app_staging_and_portal_publishing(self):
        """Verify publish_android_apk.py stages all 4 apps into temporary web root,

        updates master catalog, and renders valid HTML5 portal and app pages.
        """
        apps_data = {
            "octi": {
                "rel_path": "octi/android/app/build/outputs/apk/release/app-release.apk",
                "content": b"OCTI Android Binary Bytes v2.0.2",
                "app_id": "com.selfso.octi",
                "version_code": 20002,
                "version_name": "2.0.2",
                "min_sdk": 24,
            },
            "robohero": {
                "rel_path": "robohero/app/android/app/build/outputs/apk/release/RoboHero-v2.1.22.apk",
                "content": b"RoboHero Humanoid Controller Binary Bytes v2.1.22",
                "app_id": "com.selfso.robohero",
                "version_code": 20122,
                "version_name": "2.1.22",
                "min_sdk": 26,
            },
            "aimon": {
                "rel_path": "aimon/third_party/antimatter/android/app/build/outputs/apk/release/app-release.apk",
                "content": b"AIMon Companion AI Quota Monitor Bytes v1.8.4",
                "app_id": "dev.saifmukhtar.antimatter",
                "version_code": 10804,
                "version_name": "1.8.4",
                "min_sdk": 24,
            },
            "nigosh": {
                "rel_path": "nigosh/mobile/android/app/build/outputs/apk/release/app-release.apk",
                "content": b"Nigosh Two-Wheeled Robot Controller Bytes v1.0.3",
                "app_id": "com.selfso.nigosh",
                "version_code": 10003,
                "version_name": "1.0.3",
                "min_sdk": 24,
            },
        }

        apks: Dict[str, Path] = {}
        expected_hashes: Dict[str, str] = {}
        for slug, spec in apps_data.items():
            apk_file = self._create_synthetic_apk(
                rel_path=spec["rel_path"],
                content=spec["content"],
                app_id=spec["app_id"],
                version_code=spec["version_code"],
                version_name=spec["version_name"],
                min_sdk=spec["min_sdk"],
            )
            apks[slug] = apk_file
            expected_hashes[slug] = hashlib.sha256(spec["content"]).hexdigest().lower()

        # Publish all 4 apps via publish_app programmatic API or CLI
        for slug, apk_file in apks.items():
            cmd = [
                sys.executable,
                str(self.publish_script),
                "--slug",
                slug,
                "--apk",
                str(apk_file),
                "--web-root",
                str(self.web_root),
                "--workspace-root",
                str(self.workspace_root),
                "--no-extra-copy",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, f"publish failed for {slug}: {proc.stderr}")

        # 1. Verify master catalog <web-root>/version.json
        master_catalog_file = self.web_root / "version.json"
        self.assertTrue(master_catalog_file.is_file(), "Master version.json not generated")
        with open(master_catalog_file, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        self.assertEqual(catalog.get("schemaVersion"), 1)
        self.assertEqual(catalog.get("baseUrl"), "https://www.selfso.com/software/android/")
        self.assertIn("apps", catalog)
        master_apps = catalog["apps"]
        self.assertEqual(len(master_apps), 4)

        for slug, spec in apps_data.items():
            app_id = spec["app_id"]
            self.assertIn(app_id, master_apps, f"{app_id} missing in master apps catalog")
            app_entry = master_apps[app_id]
            self.assertEqual(app_entry["slug"], slug)
            self.assertEqual(app_entry["versionCode"], spec["version_code"])
            self.assertEqual(app_entry["versionName"], spec["version_name"])
            self.assertEqual(app_entry["sha256"], expected_hashes[slug])
            self.assertEqual(app_entry["sizeBytes"], len(spec["content"]))
            self.assertEqual(app_entry["minSdk"], spec["min_sdk"])

        # 2. Verify per-app staged artifacts: APK, single-app version.json, and index.html
        for slug, spec in apps_data.items():
            slug_dir = self.web_root / slug
            self.assertTrue(slug_dir.is_dir(), f"Slug directory {slug} missing")

            meta = KNOWN_APPS[slug]
            staged_apk = slug_dir / meta["apkFilename"]
            self.assertTrue(staged_apk.is_file(), f"Staged APK missing: {staged_apk}")
            self.assertEqual(staged_apk.read_bytes(), spec["content"])

            single_version_file = slug_dir / "version.json"
            self.assertTrue(single_version_file.is_file(), f"Single-app version.json missing for {slug}")
            with open(single_version_file, "r", encoding="utf-8") as f:
                single_manifest = json.load(f)

            self.assertEqual(single_manifest["applicationId"], spec["app_id"])
            self.assertEqual(single_manifest["versionCode"], spec["version_code"])
            self.assertEqual(single_manifest["versionName"], spec["version_name"])
            self.assertEqual(single_manifest["sha256"], expected_hashes[slug])
            self.assertEqual(single_manifest["sizeBytes"], len(spec["content"]))

            # Verify HTML5 app detail page
            app_html_file = slug_dir / "index.html"
            self.assertTrue(app_html_file.is_file(), f"App HTML page missing for {slug}")
            html_text = app_html_file.read_text(encoding="utf-8")
            self.assertTrue(html_text.startswith("<!DOCTYPE html>"))
            self.assertIn(expected_hashes[slug], html_text)
            self.assertIn(spec["version_name"], html_text)
            self.assertIn(str(spec["version_code"]), html_text)
            self.assertIn(meta["apkFilename"], html_text)
            self.assertIn("download", html_text)

        # 3. Verify main portal HTML5 page <web-root>/index.html
        portal_html_file = self.web_root / "index.html"
        self.assertTrue(portal_html_file.is_file(), "Main portal index.html missing")
        portal_html = portal_html_file.read_text(encoding="utf-8")
        self.assertTrue(portal_html.startswith("<!DOCTYPE html>"))
        for slug, spec in apps_data.items():
            self.assertIn(expected_hashes[slug], portal_html)
            self.assertIn(spec["version_name"], portal_html)
            self.assertIn(str(spec["version_code"]), portal_html)
            self.assertIn(spec["app_id"], portal_html)
            meta = KNOWN_APPS[slug]
            self.assertIn(f"{slug}/{meta['apkFilename']}", portal_html)


if __name__ == "__main__":
    unittest.main()
