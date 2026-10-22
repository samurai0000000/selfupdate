#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from scripts.publish_windows_app import (
    KNOWN_WINDOWS_APPS,
    detect_slug_from_cwd,
    find_candidate_package,
    publish_app,
)
from tests.test_gen_windows_version_json import create_synthetic_pe


class TestPublishWindowsApp(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.web_root = self.tmp_path / "web"
        self.ws_root = self.tmp_path / "work"
        self.web_root.mkdir(parents=True, exist_ok=True)
        self.ws_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_mock_exe(
        self,
        rel_path: str,
        slug: str = "octi",
        version_str: str = "2.0.3",
        file_version=(2, 0, 3, 0),
        mtime: float = None,
    ) -> Path:
        full_path = self.ws_root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        meta = KNOWN_WINDOWS_APPS.get(slug, {})
        title = meta.get("title", slug.capitalize())
        pe_bytes = create_synthetic_pe(
            version_strings=[
                ("ProductName", title),
                ("ProductVersion", f"{version_str}.0" if len(version_str.split(".")) == 3 else version_str),
                ("FileVersion", version_str),
                ("CompanyName", "Charles Chiou"),
                ("OriginalFilename", meta.get("executableName", f"{slug}.exe")),
            ],
            file_version=file_version,
            product_version=file_version,
            machine=0x8664,
        )
        with open(full_path, "wb") as f:
            f.write(pe_bytes)

        if mtime is not None:
            os.utime(full_path, (mtime, mtime))

        return full_path

    def test_publish_single_app(self):
        src_exe = self._create_mock_exe(
            "octi/desktop/build/windows/octi-setup-2.0.3.exe",
            slug="octi",
            version_str="2.0.3",
            file_version=(2, 0, 3, 0),
        )

        manifest = publish_app(
            slug="octi",
            package_path=src_exe,
            web_root=self.web_root,
            workspace_root=self.ws_root,
            base_url="https://www.selfso.com/software/windows/",
        )

        self.assertEqual(manifest["slug"], "octi")
        self.assertEqual(manifest["versionName"], "2.0.3")
        self.assertEqual(manifest["versionCode"], 20003)
        self.assertEqual(manifest["installType"], "installer")
        self.assertEqual(manifest["installerArgs"], "/S")
        self.assertEqual(manifest["packageFilename"], "octi-setup.exe")

        # Verify staged package exists
        staged_pkg = self.web_root / "octi" / "octi-setup.exe"
        self.assertTrue(staged_pkg.is_file())
        self.assertEqual(staged_pkg.stat().st_size, src_exe.stat().st_size)

        # Verify per-app version.json
        per_app_json = self.web_root / "octi" / "version.json"
        self.assertTrue(per_app_json.is_file())
        with open(per_app_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["applicationId"], "com.selfso.octi")
        self.assertEqual(data["versionName"], "2.0.3")

        # Verify master catalog version.json
        master_json = self.web_root / "version.json"
        self.assertTrue(master_json.is_file())
        with open(master_json, "r", encoding="utf-8") as f:
            master = json.load(f)
        self.assertEqual(master["schemaVersion"], 1)
        self.assertIn("com.selfso.octi", master["apps"])
        self.assertEqual(master["apps"]["com.selfso.octi"]["versionCode"], 20003)

        # Verify per-app HTML and master portal HTML
        per_app_html = self.web_root / "octi" / "index.html"
        self.assertTrue(per_app_html.is_file())
        html_content = per_app_html.read_text(encoding="utf-8")
        self.assertIn("OCTI Desktop Player", html_content)
        self.assertIn("octi-setup.exe", html_content)
        self.assertIn(manifest["sha256"], html_content)

        portal_html = self.web_root / "index.html"
        self.assertTrue(portal_html.is_file())
        portal_content = portal_html.read_text(encoding="utf-8")
        self.assertIn("OCTI Desktop Player", portal_content)
        self.assertIn("/software/android/", portal_content)

    def test_non_destructive_master_catalog_update(self):
        # 1. Publish octi
        octi_exe = self._create_mock_exe(
            "octi/desktop/build/windows/octi-setup-2.0.3.exe",
            slug="octi",
            version_str="2.0.3",
            file_version=(2, 0, 3, 0),
        )
        publish_app(
            slug="octi",
            package_path=octi_exe,
            web_root=self.web_root,
            workspace_root=self.ws_root,
        )

        # 2. Publish aimon
        aimon_exe = self._create_mock_exe(
            "aimon/build/windows/aimon-setup-1.2.3.exe",
            slug="aimon",
            version_str="1.2.3",
            file_version=(1, 2, 3, 0),
        )
        publish_app(
            slug="aimon",
            package_path=aimon_exe,
            web_root=self.web_root,
            workspace_root=self.ws_root,
        )

        master_json = self.web_root / "version.json"
        with open(master_json, "r", encoding="utf-8") as f:
            master = json.load(f)

        # Both apps must be present in catalog
        self.assertIn("com.selfso.octi", master["apps"])
        self.assertIn("com.selfso.aimon", master["apps"])
        self.assertEqual(master["apps"]["com.selfso.octi"]["versionName"], "2.0.3")
        self.assertEqual(master["apps"]["com.selfso.aimon"]["versionName"], "1.2.3")

        # 3. Update octi to 2.0.4 non-destructively
        octi_new = self._create_mock_exe(
            "octi/desktop/build/windows/octi-setup-2.0.4.exe",
            slug="octi",
            version_str="2.0.4",
            file_version=(2, 0, 4, 0),
        )
        publish_app(
            slug="octi",
            package_path=octi_new,
            web_root=self.web_root,
            workspace_root=self.ws_root,
        )

        with open(master_json, "r", encoding="utf-8") as f:
            updated_master = json.load(f)

        # octi updated to 2.0.4, aimon remains 1.2.3
        self.assertEqual(updated_master["apps"]["com.selfso.octi"]["versionName"], "2.0.4")
        self.assertEqual(updated_master["apps"]["com.selfso.octi"]["versionCode"], 20004)
        self.assertEqual(updated_master["apps"]["com.selfso.aimon"]["versionName"], "1.2.3")

    def test_candidate_selection_by_mtime(self):
        now = time.time()
        old_exe = self._create_mock_exe(
            "octi/desktop/build/windows/octi-setup-2.0.2.exe",
            slug="octi",
            version_str="2.0.2",
            file_version=(2, 0, 2, 0),
            mtime=now - 100,
        )
        new_exe = self._create_mock_exe(
            "octi/desktop/build/windows/octi-setup-2.0.3.exe",
            slug="octi",
            version_str="2.0.3",
            file_version=(2, 0, 3, 0),
            mtime=now,
        )

        chosen = find_candidate_package("octi", workspace_root=self.ws_root)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.resolve(), new_exe.resolve())

    def test_detect_slug_from_cwd(self):
        orig_cwd = Path.cwd()
        try:
            octi_dir = self.ws_root / "octi" / "desktop"
            octi_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(octi_dir)
            self.assertEqual(detect_slug_from_cwd(self.ws_root), "octi")

            aimon_dir = self.ws_root / "aimon" / "build"
            aimon_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(aimon_dir)
            self.assertEqual(detect_slug_from_cwd(self.ws_root), "aimon")

            teleop_dir = self.ws_root / "robohero" / "app" / "teleop"
            teleop_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(teleop_dir)
            self.assertEqual(detect_slug_from_cwd(self.ws_root), "robohero-teleop")

            motion_dir = self.ws_root / "robohero" / "app" / "motion"
            motion_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(motion_dir)
            self.assertEqual(detect_slug_from_cwd(self.ws_root), "robohero-motion")
        finally:
            os.chdir(orig_cwd)

    def test_dry_run(self):
        src_exe = self._create_mock_exe(
            "aimon/build/windows/aimon-setup-1.2.3.exe",
            slug="aimon",
            version_str="1.2.3",
            file_version=(1, 2, 3, 0),
        )

        manifest = publish_app(
            slug="aimon",
            package_path=src_exe,
            web_root=self.web_root,
            workspace_root=self.ws_root,
            dry_run=True,
        )

        self.assertEqual(manifest["slug"], "aimon")
        # Ensure no files written in dry run mode
        self.assertFalse((self.web_root / "aimon").exists())
        self.assertFalse((self.web_root / "version.json").exists())


if __name__ == "__main__":
    unittest.main()
