#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import json
from pathlib import Path
import sys
import tempfile
import unittest

# Ensure scripts directory is on sys.path
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from publish_android_apk import (
    KNOWN_APPS,
    find_candidate_apk,
    format_min_sdk,
    format_size_bytes,
    main,
    publish_all,
    publish_app,
    render_app_html,
    render_portal_html,
)


class TestPublishAndroidApk(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.web_root = self.temp_path / "web_root"
        self.workspace_root = self.temp_path / "workspace"
        self.web_root.mkdir(parents=True)
        self.workspace_root.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_format_helpers(self):
        self.assertEqual(format_min_sdk(24), "Android 7.0 (Nougat)+ (API 24)")
        self.assertEqual(format_min_sdk(33), "Android 13+ (API 33)")
        self.assertEqual(format_size_bytes(500), "500 B")
        self.assertEqual(format_size_bytes(1024 * 150), "150.0 KB")
        self.assertEqual(format_size_bytes(1024 * 1024 * 5 + 500000), "5.5 MB")

    def test_find_candidate_apk(self):
        # Create candidate path for octi
        octi_apk = self.workspace_root / "octi/android/app/build/outputs/apk/release/app-release.apk"
        octi_apk.parent.mkdir(parents=True)
        octi_apk.write_bytes(b"octi apk")

        cand = find_candidate_apk("octi", workspace_root=self.workspace_root)
        self.assertIsNotNone(cand)
        self.assertEqual(cand, octi_apk)

        # Create glob candidate for robohero
        robo_apk = self.workspace_root / "robohero/app/android/app/build/outputs/apk/release/RoboHero-v2.1.22.apk"
        robo_apk.parent.mkdir(parents=True)
        robo_apk.write_bytes(b"robohero apk")

        cand_robo = find_candidate_apk("robohero", workspace_root=self.workspace_root)
        self.assertIsNotNone(cand_robo)
        self.assertEqual(cand_robo, robo_apk)

        # Missing app returns None
        self.assertIsNone(find_candidate_apk("nonexistent_app", workspace_root=self.workspace_root))

    def test_publish_single_app(self):
        dummy_apk = self.workspace_root / "test_octi.apk"
        dummy_apk.write_bytes(b"octi package binary bytes")

        meta_file = dummy_apk.parent / "output-metadata.json"
        meta_file.write_text(
            json.dumps(
                {
                    "version": 3,
                    "applicationId": "com.selfso.octi",
                    "elements": [{"versionCode": 20002, "versionName": "2.0.2"}],
                    "minSdkVersionForDexing": 24,
                }
            ),
            encoding="utf-8",
        )

        manifest = publish_app(
            slug="octi",
            apk_path=dummy_apk,
            web_root=self.web_root,
            workspace_root=self.workspace_root,
            release_notes="OCTI strategy game release notes.",
            no_extra_copy=True,
            aapt2_bin="",
            published_at="2026-10-22T09:00:00Z",
        )

        self.assertEqual(manifest["slug"], "octi")
        self.assertEqual(manifest["applicationId"], "com.selfso.octi")
        self.assertEqual(manifest["versionCode"], 20002)

        # 1. Staged APK exists
        staged_apk = self.web_root / "octi/octi.apk"
        self.assertTrue(staged_apk.is_file())
        self.assertEqual(staged_apk.read_bytes(), b"octi package binary bytes")

        # 2. Per-app version.json exists and matches single-app schema
        per_app_json = self.web_root / "octi/version.json"
        self.assertTrue(per_app_json.is_file())
        with open(per_app_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["slug"], "octi")
        self.assertEqual(data["applicationId"], "com.selfso.octi")
        self.assertEqual(data["versionCode"], 20002)

        # 3. Master catalog version.json exists and matches master schema
        master_json = self.web_root / "version.json"
        self.assertTrue(master_json.is_file())
        with open(master_json, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        self.assertEqual(catalog["schemaVersion"], 1)
        self.assertIn("apps", catalog)
        self.assertIn("com.selfso.octi", catalog["apps"])
        self.assertEqual(catalog["apps"]["com.selfso.octi"]["versionCode"], 20002)

        # 4. Per-app index.html exists
        app_html = self.web_root / "octi/index.html"
        self.assertTrue(app_html.is_file())
        html_content = app_html.read_text(encoding="utf-8")
        self.assertIn("OCTI Strategy Game", html_content)
        self.assertIn("v2.0.2", html_content)
        self.assertIn("com.selfso.octi", html_content)
        self.assertIn("octi.apk", html_content)
        self.assertIn("site-header", html_content)
        self.assertIn("site-footer", html_content)
        self.assertIn("terminal-box", html_content)

        # 5. Master portal index.html exists
        portal_html = self.web_root / "index.html"
        self.assertTrue(portal_html.is_file())
        portal_content = portal_html.read_text(encoding="utf-8")
        self.assertIn("OCTI Strategy Game", portal_content)
        self.assertIn("OTA Self-Update Architecture", portal_content)
        self.assertIn("curl -s https://www.selfso.com/software/android/version.json", portal_content)

    def test_multi_app_merging_and_catalog_update(self):
        # Publish octi
        apk_octi = self.workspace_root / "app-octi.apk"
        apk_octi.write_bytes(b"octi")
        (apk_octi.parent / "output-metadata.json").write_text(
            json.dumps(
                {
                    "version": 3,
                    "applicationId": "com.selfso.octi",
                    "elements": [{"versionCode": 20002, "versionName": "2.0.2"}],
                }
            )
        )
        publish_app(
            slug="octi",
            apk_path=apk_octi,
            web_root=self.web_root,
            workspace_root=self.workspace_root,
            no_extra_copy=True,
            aapt2_bin="",
        )

        # Publish aimon
        apk_aimon = self.workspace_root / "app-aimon.apk"
        apk_aimon.write_bytes(b"aimon")
        (apk_aimon.parent / "output-metadata.json").write_text(
            json.dumps(
                {
                    "version": 3,
                    "applicationId": "dev.saifmukhtar.antimatter",
                    "elements": [{"versionCode": 7, "versionName": "2.0.5"}],
                }
            )
        )
        publish_app(
            slug="aimon",
            apk_path=apk_aimon,
            web_root=self.web_root,
            workspace_root=self.workspace_root,
            no_extra_copy=True,
            aapt2_bin="",
        )

        # Read master catalog
        master_json = self.web_root / "version.json"
        with open(master_json, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        self.assertEqual(len(catalog["apps"]), 2)
        self.assertIn("com.selfso.octi", catalog["apps"])
        self.assertIn("dev.saifmukhtar.antimatter", catalog["apps"])

        # Check master index.html has both apps
        portal_content = (self.web_root / "index.html").read_text(encoding="utf-8")
        self.assertIn("OCTI Strategy Game", portal_content)
        self.assertIn("AIMon Companion", portal_content)

        # Update octi with newer build
        (apk_octi.parent / "output-metadata.json").write_text(
            json.dumps(
                {
                    "version": 3,
                    "applicationId": "com.selfso.octi",
                    "elements": [{"versionCode": 20003, "versionName": "2.0.3"}],
                }
            )
        )
        publish_app(
            slug="octi",
            apk_path=apk_octi,
            web_root=self.web_root,
            workspace_root=self.workspace_root,
            no_extra_copy=True,
            aapt2_bin="",
        )

        with open(master_json, "r", encoding="utf-8") as f:
            updated_catalog = json.load(f)

        self.assertEqual(len(updated_catalog["apps"]), 2)
        self.assertEqual(updated_catalog["apps"]["com.selfso.octi"]["versionCode"], 20003)
        self.assertEqual(updated_catalog["apps"]["com.selfso.octi"]["versionName"], "2.0.3")
        self.assertEqual(
            updated_catalog["apps"]["dev.saifmukhtar.antimatter"]["versionCode"], 7
        )

    def test_missing_source_apk_error(self):
        missing = self.workspace_root / "nonexistent.apk"
        with self.assertRaises(FileNotFoundError):
            publish_app(
                slug="octi",
                apk_path=missing,
                web_root=self.web_root,
                workspace_root=self.workspace_root,
                no_extra_copy=True,
            )

    def test_cli_invocation_single_app(self):
        dummy_apk = self.workspace_root / "cli_test.apk"
        dummy_apk.write_bytes(b"cli test apk data")
        (dummy_apk.parent / "output-metadata.json").write_text(
            json.dumps(
                {
                    "version": 3,
                    "applicationId": "com.selfso.octi",
                    "elements": [{"versionCode": 20002, "versionName": "2.0.2"}],
                }
            )
        )

        argv = [
            "--slug",
            "octi",
            "--apk",
            str(dummy_apk),
            "--web-root",
            str(self.web_root),
            "--workspace-root",
            str(self.workspace_root),
            "--no-extra-copy",
        ]
        ret = main(argv)
        self.assertEqual(ret, 0)
        self.assertTrue((self.web_root / "octi/octi.apk").is_file())
        self.assertTrue((self.web_root / "version.json").is_file())


if __name__ == "__main__":
    unittest.main()
