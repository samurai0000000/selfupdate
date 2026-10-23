#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# Ensure selfupdate root directory is in sys.path
_TESTS_DIR = Path(__file__).resolve().parent
_REPO_DIR = _TESTS_DIR.parent
if str(_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_DIR))

from scripts.publish_ubuntu_deb import (
    KNOWN_UBUNTU_PACKAGES,
    detect_slug_from_cwd,
    ensure_gpg_key,
    find_candidate_deb,
    inspect_deb_package,
    main,
    publish_ubuntu_package,
    rebuild_apt_metadata,
)


def create_synthetic_deb(
    output_path: Path,
    package: str = "octi-server",
    version: str = "2.0.5",
    arch: str = "amd64",
    depends: str = "libc6 (>= 2.38), libgcc-s1 (>= 3.0), libsqlite3-0 (>= 3.5.9), libssl3t64 (>= 3.0.0), libstdc++6 (>= 13.1), adduser",
    description: str = "OCTI Multiplayer, SSO & Game Archive Server\n Authoritative server daemon.",
) -> Path:
    """Create a minimal synthetic .deb archive via dpkg-deb for hermetic testing."""
    output_path = output_path.resolve()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / f"{package}_{version}_{arch}"
        deb_dir = root / "DEBIAN"
        deb_dir.mkdir(parents=True, exist_ok=True)

        control_text = (
            f"Package: {package}\n"
            f"Version: {version}\n"
            f"Section: games\n"
            f"Priority: optional\n"
            f"Architecture: {arch}\n"
            f"Depends: {depends}\n"
            f"Maintainer: Charles Chiou <samurai@selfso.com>\n"
            f"Homepage: https://www.selfso.com/projects/octi/\n"
            f"Description: {description}\n"
        )
        (deb_dir / "control").write_text(control_text, encoding="utf-8")

        bin_dir = root / "usr" / "sbin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        dummy_bin = bin_dir / package
        dummy_bin.write_bytes(b"#!/bin/sh\necho 'octi_server version 2.0.5'\n")
        dummy_bin.chmod(0o755)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["dpkg-deb", "--root-owner-group", "--build", str(root), str(output_path)],
            check=True,
            capture_output=True,
        )

    return output_path


class TestPublishUbuntuDeb(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.web_root = self.tmp_path / "web"
        self.gnupg_home = self.tmp_path / "gnupg"
        self.ws_root = self.tmp_path / "work"

        self.web_root.mkdir(parents=True, exist_ok=True)
        self.gnupg_home.mkdir(parents=True, exist_ok=True)
        self.gnupg_home.chmod(0o700)
        self.ws_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_ensure_gpg_key_and_idempotence(self):
        """Verify ensure_gpg_key generates an Ed25519 signing key and returns its 40-hex fingerprint."""
        fpr1 = ensure_gpg_key(self.gnupg_home)
        self.assertIsInstance(fpr1, str)
        self.assertEqual(len(fpr1), 40)

        # Mode check on gnupg directory
        mode = self.gnupg_home.stat().st_mode & 0o777
        self.assertEqual(mode, 0o700)

        # Idempotence: calling again with same gnupg_home returns identical fingerprint
        fpr2 = ensure_gpg_key(self.gnupg_home)
        self.assertEqual(fpr1, fpr2)

    def test_inspect_deb_package(self):
        """Verify inspect_deb_package extracts stanzas, hashes, and sizes accurately."""
        deb_path = self.tmp_path / "octi-server_2.0.5_amd64.deb"
        create_synthetic_deb(deb_path, package="octi-server", version="2.0.5", arch="amd64")

        info = inspect_deb_package(deb_path)
        self.assertEqual(info["package"], "octi-server")
        self.assertEqual(info["version"], "2.0.5")
        self.assertEqual(info["architecture"], "amd64")
        self.assertIn("libssl3t64", info["depends"])
        self.assertEqual(info["maintainer"], "Charles Chiou <samurai@selfso.com>")
        self.assertEqual(info["size"], deb_path.stat().st_size)

        expected_sha256 = hashlib.sha256(deb_path.read_bytes()).hexdigest()
        self.assertEqual(info["sha256"], expected_sha256)
        expected_md5 = hashlib.md5(deb_path.read_bytes()).hexdigest()
        self.assertEqual(info["md5"], expected_md5)
        expected_sha1 = hashlib.sha1(deb_path.read_bytes()).hexdigest()
        self.assertEqual(info["sha1"], expected_sha1)

    def test_publish_ubuntu_package_full_workflow(self):
        """Verify full publish_ubuntu_package workflow: staging, APT metadata, GPG signing & gpgv verification."""
        deb_path = self.tmp_path / "octi-server_2.0.5_amd64.deb"
        create_synthetic_deb(deb_path, package="octi-server", version="2.0.5", arch="amd64")

        manifest = publish_ubuntu_package(
            slug="octi-server",
            deb_path=deb_path,
            web_root=self.web_root,
            gnupg_home=self.gnupg_home,
            workspace_root=self.ws_root,
            base_apt_url="https://ppa.selfso.com/ubuntu",
            release_notes="OCTI server 2.0.5 noble test release.",
        )

        self.assertEqual(manifest["slug"], "octi-server")
        self.assertEqual(manifest["version"], "2.0.5")
        self.assertEqual(manifest["architecture"], "amd64")
        self.assertEqual(manifest["suite"], "noble")

        # 1. Staged pool package
        pool_deb = self.web_root / "pool" / "main" / "o" / "octi-server" / "octi-server_2.0.5_amd64.deb"
        self.assertTrue(pool_deb.is_file())
        self.assertEqual(pool_deb.stat().st_size, deb_path.stat().st_size)

        # 2. Direct download copy
        direct_deb = self.web_root / "octi-server" / "octi-server_amd64.deb"
        self.assertTrue(direct_deb.is_file())
        self.assertEqual(direct_deb.stat().st_size, deb_path.stat().st_size)

        # 3. Packages and Packages.gz
        binary_dir = self.web_root / "dists" / "noble" / "main" / "binary-amd64"
        packages_path = binary_dir / "Packages"
        packages_gz_path = binary_dir / "Packages.gz"
        self.assertTrue(packages_path.is_file())
        self.assertTrue(packages_gz_path.is_file())

        pkg_text = packages_path.read_text(encoding="utf-8")
        self.assertIn("Package: octi-server", pkg_text)
        self.assertIn("Version: 2.0.5", pkg_text)
        self.assertIn("Filename: pool/main/o/octi-server/octi-server_2.0.5_amd64.deb", pkg_text)
        self.assertIn(f"SHA256: {manifest['sha256']}", pkg_text)

        # 4. dists/stable relative symlink
        stable_symlink = self.web_root / "dists" / "stable"
        self.assertTrue(stable_symlink.is_symlink())
        self.assertEqual(os.readlink(str(stable_symlink)), "noble")

        # 5. Release file and digest verification
        release_path = self.web_root / "dists" / "noble" / "Release"
        self.assertTrue(release_path.is_file())
        release_text = release_path.read_text(encoding="utf-8")
        self.assertIn("Origin: selfso.com", release_text)
        self.assertIn("Suite: noble", release_text)
        self.assertIn("Architectures: amd64", release_text)
        self.assertIn("Components: main", release_text)

        pkg_sha256 = hashlib.sha256(packages_path.read_bytes()).hexdigest()
        pkg_gz_sha256 = hashlib.sha256(packages_gz_path.read_bytes()).hexdigest()
        self.assertIn(f"{pkg_sha256} {packages_path.stat().st_size} main/binary-amd64/Packages", release_text)
        self.assertIn(f"{pkg_gz_sha256} {packages_gz_path.stat().st_size} main/binary-amd64/Packages.gz", release_text)

        # 6. GPG Signatures and Keyring verification via gpgv
        keyring_gpg = self.web_root / "selfso-archive-keyring.gpg"
        keyring_asc = self.web_root / "selfso-archive-keyring.asc"
        self.assertTrue(keyring_gpg.is_file())
        self.assertTrue(keyring_asc.is_file())

        inrelease_path = self.web_root / "dists" / "noble" / "InRelease"
        release_gpg_path = self.web_root / "dists" / "noble" / "Release.gpg"
        self.assertTrue(inrelease_path.is_file())
        self.assertTrue(release_gpg_path.is_file())

        res_inrelease = subprocess.run(
            ["gpgv", "--keyring", str(keyring_gpg), str(inrelease_path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_inrelease.returncode, 0, f"gpgv InRelease failed: {res_inrelease.stderr}")

        res_detach = subprocess.run(
            ["gpgv", "--keyring", str(keyring_gpg), str(release_gpg_path), str(release_path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_detach.returncode, 0, f"gpgv Release.gpg failed: {res_detach.stderr}")

        # 7. selfso.list
        selfso_list = self.web_root / "selfso.list"
        self.assertTrue(selfso_list.is_file())
        list_text = selfso_list.read_text(encoding="utf-8")
        self.assertEqual(
            list_text.strip(),
            "deb [arch=amd64 signed-by=/etc/apt/keyrings/selfso-archive-keyring.gpg] https://ppa.selfso.com/ubuntu noble main",
        )

        # 8. version.json catalog and per-package metadata
        cat_json_path = self.web_root / "version.json"
        self.assertTrue(cat_json_path.is_file())
        with open(cat_json_path, "r", encoding="utf-8") as f:
            cat_data = json.load(f)
        self.assertEqual(cat_data["schemaVersion"], 1)
        self.assertEqual(cat_data["suite"], "noble")
        self.assertIn("octi-server", cat_data["packages"])
        self.assertEqual(cat_data["packages"]["octi-server"]["version"], "2.0.5")
        self.assertEqual(cat_data["packages"]["octi-server"]["sha256"], manifest["sha256"])

        pkg_json_path = self.web_root / "octi-server" / "version.json"
        self.assertTrue(pkg_json_path.is_file())
        with open(pkg_json_path, "r", encoding="utf-8") as f:
            pkg_data = json.load(f)
        self.assertEqual(pkg_data["version"], "2.0.5")
        self.assertEqual(pkg_data["binaryPath"], "/usr/sbin/octi-server")
        self.assertEqual(pkg_data["serviceName"], "octi-server.service")
        self.assertEqual(pkg_data["defaultPort"], 6874)

        # 9. HTML portal rendering
        portal_html = self.web_root / "index.html"
        self.assertTrue(portal_html.is_file())
        p_html_text = portal_html.read_text(encoding="utf-8")
        self.assertIn("OCTI Multiplayer &amp; Archive Server", p_html_text)
        self.assertIn("/usr/sbin/octi-server", p_html_text)
        self.assertIn("apt-get install -y octi-server", p_html_text)
        self.assertIn(manifest["sha256"], p_html_text)

        pkg_html = self.web_root / "octi-server" / "index.html"
        self.assertTrue(pkg_html.is_file())
        k_html_text = pkg_html.read_text(encoding="utf-8")
        self.assertIn("OCTI Multiplayer &amp; Archive Server", k_html_text)
        self.assertIn("/var/lib/octi", k_html_text)
        self.assertIn("/etc/octi/oidc.json", k_html_text)
        self.assertIn("/etc/default/octi-server", k_html_text)

    def test_find_candidate_deb(self):
        """Verify candidate discovery selects the newest candidate by modification time."""
        c1 = self.ws_root / "octi/server/build/octi-server_2.0.4_amd64.deb"
        c2 = self.ws_root / "octi/server/build/octi-server_2.0.5_amd64.deb"
        create_synthetic_deb(c1, version="2.0.4")
        create_synthetic_deb(c2, version="2.0.5")

        os.utime(str(c1), (1000.0, 1000.0))
        os.utime(str(c2), (2000.0, 2000.0))

        cand = find_candidate_deb("octi-server", workspace_root=self.ws_root)
        self.assertIsNotNone(cand)
        self.assertEqual(cand.name, "octi-server_2.0.5_amd64.deb")

    def test_detect_slug_from_cwd(self):
        """Verify detect_slug_from_cwd detects octi-server slug from octi path."""
        slug = detect_slug_from_cwd()
        # When run inside an octi workspace directory, detect_slug_from_cwd detects octi-server
        if "octi" in str(Path.cwd()):
            self.assertEqual(slug, "octi-server")

    def test_dry_run_mode(self):
        """Verify dry-run mode computes manifest without writing files to web_root."""
        deb_path = self.tmp_path / "octi-server_2.0.5_amd64.deb"
        create_synthetic_deb(deb_path)

        manifest = publish_ubuntu_package(
            slug="octi-server",
            deb_path=deb_path,
            web_root=self.web_root,
            gnupg_home=self.gnupg_home,
            dry_run=True,
        )
        self.assertTrue(manifest.get("dryRun"))
        self.assertEqual(manifest["version"], "2.0.5")
        self.assertFalse((self.web_root / "dists").exists())
        self.assertFalse((self.web_root / "pool").exists())

    def test_cli_invocation(self):
        """Verify CLI main entry point accepts arguments and runs cleanly."""
        deb_path = self.tmp_path / "octi-server_2.0.5_amd64.deb"
        create_synthetic_deb(deb_path)

        ret = main(
            [
                "--slug",
                "octi-server",
                "--deb",
                str(deb_path),
                "--web-root",
                str(self.web_root),
                "--gnupg-home",
                str(self.gnupg_home),
                "--base-apt-url",
                "https://ppa.selfso.com/ubuntu",
            ]
        )
        self.assertEqual(ret, 0)
        self.assertTrue((self.web_root / "version.json").is_file())
        self.assertTrue((self.web_root / "dists" / "noble" / "InRelease").is_file())

    def test_unknown_slug_raises(self):
        """Verify unknown package slug raises ValueError."""
        deb_path = self.tmp_path / "test.deb"
        create_synthetic_deb(deb_path)
        with self.assertRaises(ValueError):
            publish_ubuntu_package(
                slug="nonexistent-package",
                deb_path=deb_path,
                web_root=self.web_root,
                gnupg_home=self.gnupg_home,
            )


if __name__ == "__main__":
    unittest.main()
