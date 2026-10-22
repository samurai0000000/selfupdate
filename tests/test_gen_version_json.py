#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

# Ensure scripts directory is on sys.path
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from gen_version_json import (
    compute_sha256,
    extract_apk_metadata,
    generate_manifest,
    main,
    parse_aapt2_badging,
    parse_output_metadata,
)


class TestGenVersionJson(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compute_sha256(self):
        # Empty file
        empty_file = self.temp_path / "empty.bin"
        empty_file.write_bytes(b"")
        expected_empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertEqual(compute_sha256(empty_file), expected_empty)

        # File with content
        content = b"Selfso Android Self-Update Unit Test Payload"
        test_file = self.temp_path / "payload.bin"
        test_file.write_bytes(content)
        expected_hash = hashlib.sha256(content).hexdigest().lower()
        self.assertEqual(compute_sha256(test_file), expected_hash)

    def test_parse_aapt2_badging(self):
        sample_output = """package: name='com.selfso.octi' versionCode='20002' versionName='2.0.2' compileSdkVersion='35'
sdkVersion:'24'
targetSdkVersion:'35'
uses-permission: name='android.permission.INTERNET'
application-label:'OCTI Strategy Game'
application-label-af:'OCTI'
"""
        parsed = parse_aapt2_badging(sample_output)
        self.assertEqual(parsed.get("applicationId"), "com.selfso.octi")
        self.assertEqual(parsed.get("versionCode"), 20002)
        self.assertEqual(parsed.get("versionName"), "2.0.2")
        self.assertEqual(parsed.get("minSdk"), 24)
        self.assertEqual(parsed.get("targetSdk"), 35)
        self.assertEqual(parsed.get("title"), "OCTI Strategy Game")

    def test_parse_output_metadata(self):
        meta_file = self.temp_path / "output-metadata.json"
        meta_data = {
            "version": 3,
            "artifactType": {"type": "APK", "kind": "Directory"},
            "applicationId": "com.selfso.testapp",
            "elements": [
                {
                    "type": "SINGLE",
                    "versionCode": 105,
                    "versionName": "1.5.0",
                    "outputFile": "app-debug.apk",
                }
            ],
            "minSdkVersionForDexing": 26,
        }
        meta_file.write_text(json.dumps(meta_data), encoding="utf-8")

        parsed = parse_output_metadata(meta_file)
        self.assertEqual(parsed.get("applicationId"), "com.selfso.testapp")
        self.assertEqual(parsed.get("versionCode"), 105)
        self.assertEqual(parsed.get("versionName"), "1.5.0")
        self.assertEqual(parsed.get("minSdk"), 26)

        # Non-existent file returns empty dict
        self.assertEqual(parse_output_metadata(self.temp_path / "nonexistent.json"), {})

    def test_extract_apk_metadata_strips_debug_suffix(self):
        dummy_apk = self.temp_path / "app-debug.apk"
        dummy_apk.write_bytes(b"dummy apk content")

        meta_file = self.temp_path / "output-metadata.json"
        meta_data = {
            "version": 3,
            "applicationId": "dev.saifmukhtar.antimatter.debug",
            "elements": [{"versionCode": 7, "versionName": "2.0.5"}],
        }
        meta_file.write_text(json.dumps(meta_data), encoding="utf-8")

        # By default keep_debug_suffix is False -> should strip .debug
        res_stripped = extract_apk_metadata(dummy_apk, keep_debug_suffix=False, aapt2_bin="")
        self.assertEqual(res_stripped.get("applicationId"), "dev.saifmukhtar.antimatter")

        # When keep_debug_suffix is True -> preserve .debug
        res_kept = extract_apk_metadata(dummy_apk, keep_debug_suffix=True, aapt2_bin="")
        self.assertEqual(res_kept.get("applicationId"), "dev.saifmukhtar.antimatter.debug")

    def test_missing_apk_error(self):
        missing_apk = self.temp_path / "missing.apk"
        with self.assertRaises(FileNotFoundError):
            extract_apk_metadata(missing_apk)
        with self.assertRaises(FileNotFoundError):
            generate_manifest(missing_apk)

    def test_generate_manifest_full_and_overrides(self):
        dummy_apk = self.temp_path / "octi-release.apk"
        dummy_apk.write_bytes(b"octi test apk binary data")

        manifest = generate_manifest(
            apk_path=dummy_apk,
            slug="octi",
            title="Custom OCTI Title",
            application_id="com.selfso.custom.octi",
            version_code=30001,
            version_name="3.0.1",
            min_sdk=24,
            target_sdk=35,
            apk_url="https://www.selfso.com/software/android/octi/octi-release.apk",
            page_url="https://www.selfso.com/software/android/octi/",
            release_notes="Release notes for testing.",
            published_at="2026-10-22T10:00:00Z",
            keep_debug_suffix=False,
            aapt2_bin="",
        )

        # Check required schema keys
        required_keys = [
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
        for key in required_keys:
            self.assertIn(key, manifest, f"Missing required key {key} in manifest")

        self.assertEqual(manifest["slug"], "octi")
        self.assertEqual(manifest["title"], "Custom OCTI Title")
        self.assertEqual(manifest["applicationId"], "com.selfso.custom.octi")
        self.assertEqual(manifest["versionCode"], 30001)
        self.assertEqual(manifest["versionName"], "3.0.1")
        self.assertEqual(manifest["minSdk"], 24)
        self.assertEqual(manifest["targetSdk"], 35)
        self.assertEqual(manifest["sizeBytes"], len(b"octi test apk binary data"))
        self.assertEqual(manifest["publishedAt"], "2026-10-22T10:00:00Z")
        self.assertEqual(manifest["releaseNotes"], "Release notes for testing.")
        self.assertEqual(len(manifest["sha256"]), 64)

    def test_cli_invocation(self):
        dummy_apk = self.temp_path / "sample.apk"
        dummy_apk.write_bytes(b"sample apk binary")
        out_json = self.temp_path / "out_version.json"

        argv = [
            "--apk",
            str(dummy_apk),
            "--slug",
            "sample",
            "--title",
            "Sample App",
            "--app-id",
            "com.selfso.sample",
            "--version-code",
            "10",
            "--version-name",
            "1.0.0",
            "--output",
            str(out_json),
        ]
        code = main(argv)
        self.assertEqual(code, 0)
        self.assertTrue(out_json.is_file())

        with open(out_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["slug"], "sample")
        self.assertEqual(data["applicationId"], "com.selfso.sample")
        self.assertEqual(data["versionCode"], 10)


if __name__ == "__main__":
    unittest.main()
