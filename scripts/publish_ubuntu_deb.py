#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import argparse
import datetime
import gzip
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Known Selfso Ubuntu packages registry
KNOWN_UBUNTU_PACKAGES: Dict[str, Dict[str, Any]] = {
    "octi-server": {
        "title": "OCTI Multiplayer & Archive Server",
        "packageName": "octi-server",
        "binaryPath": "/usr/sbin/octi-server",
        "serviceName": "octi-server.service",
        "defaultPort": 6874,
        "stateDir": "/var/lib/octi",
        "configLabel": "OIDC SSO Configuration",
        "configPath": "/etc/octi/oidc.json",
        "envConfigPath": "/etc/default/octi-server",
        "suite": "noble",
        "component": "main",
        "arch": "amd64",
        "minOs": "Ubuntu 24.04 LTS (Noble Numbat) amd64",
        "tagline": "C++17 HTTP/REST multiplayer room manager, 5-provider OIDC SSO verifier, Elo rating engine & SQLite WAL archive daemon for OCTI.",
        "description": "Production Ubuntu 24.04 LTS (noble) systemd daemon packaging of the OCTI multiplayer game server (/usr/sbin/octi-server), featuring 5-provider OIDC authentication, matchmaking, P2P voice relay coordination, and persistent SQLite WAL game archive.",
        "category": "Multiplayer Game Server",
        "projectUrl": "/projects/octi/",
        "defaultDebCandidates": [
            "octi/server/build/octi-server_*_amd64.deb",
        ],
    },
    "abc-80": {
        "title": "ABC-80 Microcomputer Emulator & Web Server",
        "packageName": "abc-80",
        "binaryPath": "/usr/sbin/abc80_server",
        "cliBinaryPath": "/usr/bin/abc80_cli",
        "serviceName": "abc-80.service",
        "defaultPort": 8008,
        "stateDir": "/etc/abc-80",
        "configLabel": "Daemon & Hardware Configuration",
        "configPath": "/etc/abc-80/abc-80.cfg",
        "envConfigPath": "/etc/default/abc-80",
        "suite": "noble",
        "component": "main",
        "arch": "amd64",
        "minOs": "Ubuntu 24.04 LTS (Noble Numbat) amd64",
        "tagline": "Cycle-accurate Z80 microcomputer emulator, CLI, and WebSocket/HTTP interactive front-panel server daemon for the 1980s Taiwanese ABC-80 educational kit.",
        "description": "Production Ubuntu 24.04 LTS (noble) systemd daemon (/usr/sbin/abc80_server) and interactive CLI (/usr/bin/abc80_cli) for the ABC-80 Z80 single-board microcomputer, featuring cycle-accurate Z80/8255 PPI emulation, WebSocket front-panel UI, Kansas City cassette tape library, and QBasic exercise host.",
        "category": "Hardware Emulator & Web Server",
        "projectUrl": "/projects/",
        "defaultDebCandidates": [
            "abc-80/build/abc-80_*_amd64.deb",
        ],
    },
}


def format_size_bytes(size_bytes: int) -> str:
    """Format byte size into human-readable KB or MB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def format_date(iso_str: str) -> str:
    """Extract YYYY-MM-DD from an ISO-8601 string."""
    if not iso_str:
        return ""
    return iso_str.split("T")[0]


def ensure_gpg_key(gnupg_home: Path) -> str:
    """Ensure dedicated GPG signing key exists in gnupg_home (mode 0700).

    Generates a passwordless Ed25519 signing key if none exists.
    Returns the 40-hex-character fingerprint of the primary secret key.
    """
    gnupg_home = gnupg_home.resolve()
    gnupg_home.mkdir(parents=True, exist_ok=True)
    gnupg_home.chmod(0o700)

    # Inspect existing secret keys
    res = subprocess.run(
        [
            "gpg",
            "--homedir",
            str(gnupg_home),
            "--batch",
            "--with-colons",
            "--list-secret-keys",
        ],
        capture_output=True,
        text=True,
    )

    fingerprint: Optional[str] = None
    if res.returncode == 0 and res.stdout.strip():
        for line in res.stdout.splitlines():
            parts = line.split(":")
            if parts[0] == "fpr" and len(parts) > 9 and len(parts[9].strip()) == 40:
                fingerprint = parts[9].strip()
                break

    if not fingerprint:
        batch_spec = (
            "Key-Type: eddsa\n"
            "Key-Curve: ed25519\n"
            "Key-Usage: sign\n"
            "Name-Real: Selfso Archive Automatic Signing Key\n"
            "Name-Email: samurai@selfso.com\n"
            "Expire-Date: 0\n"
            "%no-protection\n"
            "%commit\n"
        )
        gen_res = subprocess.run(
            [
                "gpg",
                "--homedir",
                str(gnupg_home),
                "--batch",
                "--generate-key",
            ],
            input=batch_spec,
            text=True,
            capture_output=True,
        )
        if gen_res.returncode != 0:
            raise RuntimeError(
                f"Failed to generate GPG signing key: {gen_res.stderr.strip()}"
            )

        res2 = subprocess.run(
            [
                "gpg",
                "--homedir",
                str(gnupg_home),
                "--batch",
                "--with-colons",
                "--list-secret-keys",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in res2.stdout.splitlines():
            parts = line.split(":")
            if parts[0] == "fpr" and len(parts) > 9 and len(parts[9].strip()) == 40:
                fingerprint = parts[9].strip()
                break

    if not fingerprint:
        raise RuntimeError(f"Unable to determine GPG signing key fingerprint in {gnupg_home}")

    return fingerprint


def inspect_deb_package(deb_path: Path) -> Dict[str, Any]:
    """Inspect Debian .deb package and extract control stanza, hashes, and size."""
    deb_path = deb_path.resolve()
    if not deb_path.is_file():
        raise FileNotFoundError(f"Debian package not found: {deb_path}")

    res = subprocess.run(
        ["dpkg-deb", "-f", str(deb_path)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"dpkg-deb -f failed for {deb_path}: {res.stderr.strip()}"
        )

    raw_control = res.stdout.strip()
    fields: Dict[str, str] = {}
    current_key: Optional[str] = None
    for line in raw_control.splitlines():
        if line.startswith(" ") or line.startswith("\t"):
            if current_key:
                fields[current_key] = fields[current_key] + "\n" + line
        elif ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            current_key = key
            fields[key] = val

    deb_bytes = deb_path.read_bytes()
    size = len(deb_bytes)
    md5_hash = hashlib.md5(deb_bytes).hexdigest()
    sha1_hash = hashlib.sha1(deb_bytes).hexdigest()
    sha256_hash = hashlib.sha256(deb_bytes).hexdigest()

    installed_size_raw = fields.get("Installed-Size", "0")
    try:
        installed_size = int(installed_size_raw)
    except ValueError:
        installed_size = 0

    return {
        "raw_control": raw_control,
        "package": fields.get("Package", ""),
        "version": fields.get("Version", ""),
        "architecture": fields.get("Architecture", "amd64"),
        "depends": fields.get("Depends", ""),
        "installed_size": installed_size,
        "maintainer": fields.get("Maintainer", ""),
        "section": fields.get("Section", ""),
        "priority": fields.get("Priority", ""),
        "homepage": fields.get("Homepage", ""),
        "description": fields.get("Description", ""),
        "size": size,
        "md5": md5_hash,
        "sha1": sha1_hash,
        "sha256": sha256_hash,
        "path": deb_path,
    }


def find_candidate_deb(
    slug: str, workspace_root: Optional[Union[str, Path]] = None
) -> Optional[Path]:
    """Discover the newest compiled .deb package (by mtime) for a known package within workspace."""
    ws = Path(workspace_root) if workspace_root else (Path(__file__).resolve().parents[2])
    meta = KNOWN_UBUNTU_PACKAGES.get(slug)
    if not meta:
        return None

    candidates = meta.get("defaultDebCandidates", [])
    found: List[Path] = []
    for cand in candidates:
        if "*" in cand:
            for m in ws.glob(cand):
                if m.is_file():
                    found.append(m)
        else:
            p = ws / cand
            if p.is_file():
                found.append(p)

    if not found:
        return None

    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0]


def detect_slug_from_cwd(
    workspace_root: Optional[Union[str, Path]] = None,
    cwd: Optional[Union[str, Path]] = None,
) -> Optional[str]:
    """Detect package slug from current working directory."""
    cwd_path = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    cwd_str = str(cwd_path)
    if "octi" in cwd_str:
        return "octi-server"
    if "abc-80" in cwd_str:
        return "abc-80"
    for slug in KNOWN_UBUNTU_PACKAGES.keys():
        if slug in cwd_path.parts:
            return slug
    return None


def rebuild_apt_metadata(
    web_root: Path,
    gnupg_home: Path,
    base_apt_url: str = "https://ppa.selfso.com/ubuntu",
    suite: str = "noble",
    component: str = "main",
    arch: str = "amd64",
) -> Dict[str, Any]:
    """Scan web_root/pool, rebuild Packages, Packages.gz, Release, InRelease, Release.gpg, and keyrings."""
    web_root = web_root.resolve()
    gnupg_home = gnupg_home.resolve()

    dists_suite = web_root / "dists" / suite
    binary_dir = dists_suite / component / f"binary-{arch}"
    binary_dir.mkdir(parents=True, exist_ok=True)

    # Discover all .deb packages in pool
    pool_dir = web_root / "pool"
    deb_files: List[Path] = []
    if pool_dir.is_dir():
        deb_files = sorted(pool_dir.glob("**/*.deb"))

    stanzas: List[str] = []
    for deb_file in deb_files:
        info = inspect_deb_package(deb_file)
        rel_filename = deb_file.relative_to(web_root).as_posix()
        clean_raw = info["raw_control"].rstrip()
        stanza = (
            f"{clean_raw}\n"
            f"Filename: {rel_filename}\n"
            f"Size: {info['size']}\n"
            f"MD5sum: {info['md5']}\n"
            f"SHA1: {info['sha1']}\n"
            f"SHA256: {info['sha256']}"
        )
        stanzas.append(stanza)

    packages_content = ("\n\n".join(stanzas) + "\n\n") if stanzas else "\n"
    packages_path = binary_dir / "Packages"
    packages_gz_path = binary_dir / "Packages.gz"

    packages_bytes = packages_content.encode("utf-8")
    packages_path.write_bytes(packages_bytes)

    with open(packages_gz_path, "wb") as f_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=f_out, mtime=0) as gz:
            gz.write(packages_bytes)

    # Relative symlink dists/stable -> noble
    stable_symlink = web_root / "dists" / "stable"
    if stable_symlink.is_symlink() or stable_symlink.exists():
        stable_symlink.unlink()
    stable_symlink.symlink_to(suite)

    # Compute checksums for Release
    pkg_b = packages_path.read_bytes()
    pkg_gz_b = packages_gz_path.read_bytes()

    p_size = len(pkg_b)
    p_md5 = hashlib.md5(pkg_b).hexdigest()
    p_sha1 = hashlib.sha1(pkg_b).hexdigest()
    p_sha256 = hashlib.sha256(pkg_b).hexdigest()

    gz_size = len(pkg_gz_b)
    gz_md5 = hashlib.md5(pkg_gz_b).hexdigest()
    gz_sha1 = hashlib.sha1(pkg_gz_b).hexdigest()
    gz_sha256 = hashlib.sha256(pkg_gz_b).hexdigest()

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S UTC")
    rel_p = f"{component}/binary-{arch}/Packages"
    rel_gz = f"{component}/binary-{arch}/Packages.gz"

    release_content = (
        "Origin: selfso.com\n"
        "Label: Selfso Ubuntu Repository\n"
        f"Suite: {suite}\n"
        f"Codename: {suite}\n"
        "Version: 24.04\n"
        f"Date: {date_str}\n"
        f"Architectures: {arch}\n"
        f"Components: {component}\n"
        "Description: Selfso Official Ubuntu 24.04 LTS (Noble) APT Package Repository\n"
        "MD5Sum:\n"
        f" {p_md5} {p_size} {rel_p}\n"
        f" {gz_md5} {gz_size} {rel_gz}\n"
        "SHA1:\n"
        f" {p_sha1} {p_size} {rel_p}\n"
        f" {gz_sha1} {gz_size} {rel_gz}\n"
        "SHA256:\n"
        f" {p_sha256} {p_size} {rel_p}\n"
        f" {gz_sha256} {gz_size} {rel_gz}\n"
    )
    release_path = dists_suite / "Release"
    release_path.write_text(release_content, encoding="utf-8")

    # Cryptographically sign InRelease and Release.gpg
    inrelease_path = dists_suite / "InRelease"
    release_gpg_path = dists_suite / "Release.gpg"

    subprocess.run(
        [
            "gpg",
            "--homedir",
            str(gnupg_home),
            "--batch",
            "--yes",
            "--digest-algo",
            "SHA256",
            "--clearsign",
            "-o",
            str(inrelease_path),
            str(release_path),
        ],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [
            "gpg",
            "--homedir",
            str(gnupg_home),
            "--batch",
            "--yes",
            "--digest-algo",
            "SHA256",
            "--armor",
            "--detach-sign",
            "-o",
            str(release_gpg_path),
            str(release_path),
        ],
        check=True,
        capture_output=True,
    )

    # Export public keyrings
    keyring_gpg = web_root / "selfso-archive-keyring.gpg"
    keyring_asc = web_root / "selfso-archive-keyring.asc"

    subprocess.run(
        [
            "gpg",
            "--homedir",
            str(gnupg_home),
            "--batch",
            "--yes",
            "--export",
            "-o",
            str(keyring_gpg),
        ],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [
            "gpg",
            "--homedir",
            str(gnupg_home),
            "--batch",
            "--yes",
            "--armor",
            "--export",
            "-o",
            str(keyring_asc),
        ],
        check=True,
        capture_output=True,
    )

    # Write selfso.list
    selfso_list = web_root / "selfso.list"
    selfso_list_content = (
        f"deb [arch=amd64 signed-by=/etc/apt/keyrings/selfso-archive-keyring.gpg] "
        f"{base_apt_url} {suite} {component}\n"
    )
    selfso_list.write_text(selfso_list_content, encoding="utf-8")

    return {
        "suite": suite,
        "component": component,
        "arch": arch,
        "packagesCount": len(stanzas),
        "packagesPath": packages_path,
        "packagesGzPath": packages_gz_path,
        "releasePath": release_path,
        "inreleasePath": inrelease_path,
        "releaseGpgPath": release_gpg_path,
        "keyringGpgPath": keyring_gpg,
        "keyringAscPath": keyring_asc,
        "selfsoListPath": selfso_list,
    }


def render_portal_html(catalog: Dict[str, Any], base_apt_url: str) -> str:
    """Render master index.html for Ubuntu APT repository."""
    cards_list: List[str] = []
    fingerprint = catalog.get("gpgFingerprint", "")
    suite = catalog.get("suite", "noble")
    component = catalog.get("components", ["main"])[0]

    for pkg_name, pkg in sorted(catalog.get("packages", {}).items()):
        slug = html.escape(pkg.get("slug", pkg_name))
        title = html.escape(pkg.get("title", pkg_name))
        tagline = html.escape(pkg.get("tagline", ""))
        version = html.escape(str(pkg.get("version", "1.0.0")))
        arch = html.escape(pkg.get("architecture", "amd64"))
        min_os = html.escape(pkg.get("minOs", "Ubuntu 24.04 LTS (noble)"))
        size_str = html.escape(format_size_bytes(pkg.get("sizeBytes", 0)))
        pub_date = html.escape(format_date(pkg.get("publishedAt", "")))
        sha256 = html.escape(pkg.get("sha256", ""))
        category = html.escape(pkg.get("category", "Ubuntu Package"))
        binary_path = html.escape(pkg.get("binaryPath", ""))
        service_name = html.escape(pkg.get("serviceName", ""))
        default_port = pkg.get("defaultPort")
        port_badge = f" &bull; Port <code>{default_port}</code>" if default_port else ""
        pool_deb = pkg.get("poolDebPath", "")
        deb_download_url = f"{base_apt_url}/{pool_deb}" if pool_deb else f"{slug}/{slug}_{arch}.deb"

        card_html = f"""        <!-- Package Card: {title} -->
        <div class="card" id="{slug}">
          <span class="card-tag">{category}</span>
          <h2 class="card-title" style="font-size: 1.45rem; margin-top: 0.5rem; margin-bottom: 0.5rem;">{title}</h2>
          <p class="card-desc" style="margin-bottom: 1rem;">{tagline}</p>

          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
            <span class="badge">v{version}</span>
            <span class="badge">{min_os}</span>
            <span class="badge">{arch}</span>
            <span class="badge">systemd daemon</span>
            <span class="badge">{size_str}</span>
            <span class="badge">{pub_date}</span>
          </div>

          <div style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">
            <code>{binary_path}</code> &bull; <code>{service_name}</code>{port_badge}
          </div>

          <div style="background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.5rem 0.75rem; font-family: var(--font-mono); font-size: 0.73rem; word-break: break-all; margin-bottom: 1.5rem; color: var(--text-secondary);">
            <span style="color: var(--text-muted); user-select: none;">SHA-256: </span>{sha256}
          </div>

          <div style="display: flex; gap: 0.65rem; flex-wrap: wrap; margin-top: auto;">
            <a href="{deb_download_url}" class="btn btn-primary" download>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
              </svg>
              Download .deb
            </a>
            <a href="{slug}/" class="btn btn-outline">Package Details &rarr;</a>
            <a href="{slug}/version.json" class="btn btn-outline">version.json</a>
          </div>
        </div>"""
        cards_list.append(card_html)

    cards_rendered = "\n\n".join(cards_list) if cards_list else "<p>No packages currently staged in repository.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="SELFSO.COM Ubuntu Linux &amp; APT Package Repository — Signed APT distribution (ppa.selfso.com) providing production Ubuntu 24.04 LTS (noble) systemd daemons and packages.">
  <title>Ubuntu Linux &amp; APT Package Repository &bull; SELFSO.COM</title>
  <link rel="stylesheet" href="/css/main.css">
</head>
<body>
  <header class="site-header">
    <div class="nav-container">
      <a href="/" class="brand">
        <span class="brand-badge">SELFSO</span>
        <div class="brand-text">
          <span class="brand-name">SELFSO.COM</span>
          <span class="brand-tagline">Systems &bull; Code &bull; Philosophy</span>
        </div>
      </a>

      <button class="mobile-toggle" id="mobileNavBtn" aria-label="Toggle Navigation">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <nav>
        <ul class="nav-menu" id="navMenu">
          <li><a href="/" class="nav-link">Home</a></li>
          <li><a href="/news.html" class="nav-link">News</a></li>
          <li><a href="/projects/" class="nav-link active">Projects</a></li>
          <li><a href="/info.html" class="nav-link">Info</a></li>
          <li><a href="/links.html" class="nav-link">Links</a></li>
          <li><a href="/contact.html" class="nav-link">Contact</a></li>
        </ul>
      </nav>
    </div>
  </header>

  <main class="site-wrapper">
    <div class="container" style="padding-top: 3.5rem; padding-bottom: 4rem;">
      <div style="margin-bottom: 2.5rem;">
        <a href="/projects/" style="color: var(--text-muted); font-size: 0.9rem; text-decoration: none;">&larr; Back to Projects</a>
        <div style="margin-top: 0.75rem;">
          <span class="badge" style="margin-bottom: 0.75rem;">Ubuntu APT Repository</span>
          <h1 style="font-size: 2.35rem; margin-bottom: 0.75rem;">Selfso Ubuntu Linux &amp; APT Package Repository</h1>
        </div>
        <p style="color: var(--text-secondary); max-width: 780px; font-size: 1.05rem; line-height: 1.6;">
          Official signed APT repository (<code>ppa.selfso.com</code>) providing production Ubuntu 24.04 LTS (noble) systemd daemons and Debian packages for Selfso server infrastructure and algorithmic platforms.
        </p>

        <!-- Cross-link badges to sibling software portals -->
        <div style="margin-top: 1.25rem; display: flex; gap: 0.75rem; flex-wrap: wrap;">
          <div style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.85rem; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 0.88rem;">
            <span style="color: var(--accent-indigo); font-weight: 600;">Android Portal:</span>
            <span>Mobile companion apps &amp; OTA updates</span>
            <a href="/software/android/" style="color: var(--accent-indigo); text-decoration: underline; margin-left: 0.25rem;">Visit Android OTA Portal &rarr;</a>
          </div>
          <div style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.85rem; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 0.88rem;">
            <span style="color: var(--accent-indigo); font-weight: 600;">Windows Portal:</span>
            <span>Native Qt6 desktop applications &amp; self-update</span>
            <a href="/software/windows/" style="color: var(--accent-indigo); text-decoration: underline; margin-left: 0.25rem;">Visit Windows Portal &rarr;</a>
          </div>
        </div>
      </div>

      <!-- APT Setup Instructions Card -->
      <div class="card" style="margin-bottom: 2.5rem; border-color: var(--border-indigo);">
        <span class="card-tag">APT Configuration &bull; Ubuntu 24.04 LTS (noble)</span>
        <h2 class="card-title" style="font-size: 1.45rem; margin-top: 0.5rem; margin-bottom: 1rem;">Repository Quick Setup</h2>
        <p class="card-desc" style="margin-bottom: 1.25rem;">
          Configure your Ubuntu 24.04 LTS machine to trust and install packages directly from <code>ppa.selfso.com</code>:
        </p>

        <pre style="background: var(--bg-code); color: #f4f4f5; padding: 1.25rem; border-radius: var(--radius-md); font-family: var(--font-mono); font-size: 0.85rem; line-height: 1.6; margin-bottom: 1.5rem; overflow-x: auto; white-space: pre;"><span style="color: #a1a1aa;"># 1. Install Selfso GPG Archive Signing Key</span>
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://ppa.selfso.com/ubuntu/selfso-archive-keyring.gpg | sudo tee /etc/apt/keyrings/selfso-archive-keyring.gpg > /dev/null

<span style="color: #a1a1aa;"># 2. Add repository source list</span>
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/selfso-archive-keyring.gpg] https://ppa.selfso.com/ubuntu noble main" | sudo tee /etc/apt/sources.list.d/selfso.list

<span style="color: #a1a1aa;"># 3. Update and install Selfso Ubuntu packages (octi-server, abc-80)</span>
sudo apt-get update
sudo apt-get install -y octi-server abc-80

<span style="color: #a1a1aa;"># 4. Verify systemd daemon status</span>
systemctl status octi-server.service abc-80.service
/usr/sbin/octi-server --version
/usr/sbin/abc80_server --version</pre>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1.25rem; font-size: 0.88rem;">
          <div>
            <div style="color: var(--text-muted); font-size: 0.78rem;">Suite &amp; Codename</div>
            <div style="font-weight: 600;"><code>{suite}</code> (symlinked <code>stable</code>)</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.78rem;">Component &amp; Arch</div>
            <div style="font-weight: 600;"><code>{component}</code> &bull; <code>amd64</code></div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.78rem;">Base APT URL</div>
            <div style="font-weight: 600;"><code>{base_apt_url}</code></div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.78rem;">Keyring Downloads</div>
            <div>
              <a href="selfso-archive-keyring.gpg" style="font-size: 0.82rem;">keyring.gpg</a> &bull;
              <a href="selfso-archive-keyring.asc" style="font-size: 0.82rem;">keyring.asc</a> &bull;
              <a href="selfso.list" style="font-size: 0.82rem;">selfso.list</a>
            </div>
          </div>
        </div>

        <div style="background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.5rem 0.75rem; font-family: var(--font-mono); font-size: 0.75rem; word-break: break-all; color: var(--text-secondary);">
          <span style="color: var(--text-muted); user-select: none;">GPG Key Fingerprint: </span>{fingerprint}
        </div>
      </div>

      <!-- Packages Grid -->
      <div style="margin-bottom: 1.5rem;">
        <h2 style="font-size: 1.65rem; margin-bottom: 0.35rem;">Available Packages</h2>
        <p style="color: var(--text-muted); font-size: 0.95rem; margin-bottom: 0;">
          Precompiled, cryptographically verified Debian packages and systemd daemon units.
        </p>
      </div>

      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));">
{cards_rendered}
      </div>
    </div>
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <span class="brand-badge">SELFSO</span>
          <p>Private computing infrastructure and creative portal. Operating continuously since 2001.</p>
        </div>
        <div class="footer-col">
          <h5>Navigation</h5>
          <ul class="footer-links">
            <li><a href="/">Home</a></li>
            <li><a href="/news.html">News &amp; Timeline</a></li>
            <li><a href="/projects/">Projects</a></li>
            <li><a href="/software/android/">Android Software</a></li>
            <li><a href="/software/windows/">Windows Software</a></li>
            <li><a href="/software/ubuntu/">Ubuntu APT Repo</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h5>Information</h5>
          <ul class="footer-links">
            <li><a href="/info.html">About &amp; Philosophy</a></li>
            <li><a href="/links.html">Resources</a></li>
            <li><a href="/poweredby.html">Powered By</a></li>
            <li><a href="/contact.html">Contact</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; 2001&ndash;2026 SELFSO.COM. All Rights Reserved.</span>
        <span>Built with Pure Static HTML</span>
      </div>
    </div>
  </footer>

  <script>
    (function() {{
      var btn = document.getElementById('mobileNavBtn');
      var menu = document.getElementById('navMenu');
      if (btn && menu) {{
        btn.addEventListener('click', function() {{
          menu.classList.toggle('open');
        }});
      }}
    }})();
  </script>
</body>
</html>
"""


def render_package_html(pkg: Dict[str, Any], base_apt_url: str) -> str:
    """Render package-specific release details page (<web_root>/<slug>/index.html)."""
    slug = html.escape(pkg.get("slug", ""))
    title = html.escape(pkg.get("title", slug))
    version = html.escape(str(pkg.get("version", "1.0.0")))
    arch = html.escape(pkg.get("architecture", "amd64"))
    min_os = html.escape(pkg.get("minOs", "Ubuntu 24.04 LTS (noble)"))
    tagline = html.escape(pkg.get("tagline", ""))
    description = html.escape(pkg.get("description", ""))
    category = html.escape(pkg.get("category", "Ubuntu Package"))
    binary_path = html.escape(pkg.get("binaryPath", ""))
    service_name = html.escape(pkg.get("serviceName", ""))
    default_port = pkg.get("defaultPort", 6874)
    size_str = html.escape(format_size_bytes(pkg.get("sizeBytes", 0)))
    pub_date = html.escape(format_date(pkg.get("publishedAt", "")))
    maintainer = html.escape(pkg.get("maintainer", "Charles Chiou <samurai@selfso.com>"))
    depends = html.escape(pkg.get("depends", ""))
    sha256 = html.escape(pkg.get("sha256", ""))
    sha1 = html.escape(pkg.get("sha1", ""))
    md5 = html.escape(pkg.get("md5", ""))
    fingerprint = html.escape(pkg.get("gpgFingerprint", ""))
    state_dir = html.escape(pkg.get("stateDir", "/var/lib/octi"))
    config_label = html.escape(pkg.get("configLabel", "OIDC SSO Configuration"))
    config_path = html.escape(pkg.get("configPath", "/etc/octi/oidc.json"))
    env_config_path = html.escape(pkg.get("envConfigPath", "/etc/default/octi-server"))
    deb_filename = f"{slug}_{arch}.deb"
    pool_deb = pkg.get("poolDebPath", "")
    deb_download_url = f"{base_apt_url}/{pool_deb}" if pool_deb else deb_filename

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{tagline}">
  <title>{title} &bull; Ubuntu Package &bull; SELFSO.COM</title>
  <link rel="stylesheet" href="/css/main.css">
</head>
<body>
  <header class="site-header">
    <div class="nav-container">
      <a href="/" class="brand">
        <span class="brand-badge">SELFSO</span>
        <div class="brand-text">
          <span class="brand-name">SELFSO.COM</span>
          <span class="brand-tagline">Systems &bull; Code &bull; Philosophy</span>
        </div>
      </a>

      <button class="mobile-toggle" id="mobileNavBtn" aria-label="Toggle Navigation">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <nav>
        <ul class="nav-menu" id="navMenu">
          <li><a href="/" class="nav-link">Home</a></li>
          <li><a href="/news.html" class="nav-link">News</a></li>
          <li><a href="/projects/" class="nav-link active">Projects</a></li>
          <li><a href="/info.html" class="nav-link">Info</a></li>
          <li><a href="/links.html" class="nav-link">Links</a></li>
          <li><a href="/contact.html" class="nav-link">Contact</a></li>
        </ul>
      </nav>
    </div>
  </header>

  <main class="site-wrapper">
    <div class="container" style="padding-top: 3.5rem; padding-bottom: 4rem;">
      <div style="margin-bottom: 2rem;">
        <div style="margin-bottom: 0.75rem;">
          <a href="../" class="btn btn-outline" style="padding: 0.25rem 0.65rem; font-size: 0.8rem;">&larr; All Ubuntu Packages</a>
        </div>
        <span class="badge" style="margin-bottom: 0.75rem;">{category}</span>
        <h1 style="font-size: 2.35rem; margin-bottom: 0.75rem;">{title}</h1>
        <p style="color: var(--text-secondary); max-width: 760px; font-size: 1.05rem; line-height: 1.6;">
          {description}
        </p>
      </div>

      <div class="card" style="margin-bottom: 2.5rem;">
        <h3 style="font-size: 1.25rem; margin-bottom: 1.25rem;">Package Specifications &bull; v{version}</h3>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.25rem; margin-bottom: 1.5rem;">
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Package Name</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.88rem;">{pkg.get('packageName', slug)}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Version</div>
            <div style="font-weight: 600;">v{version}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Architecture</div>
            <div style="font-weight: 600;">{arch}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Target OS</div>
            <div style="font-weight: 600;">{min_os}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Binary Location</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.85rem;">{binary_path}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Systemd Service</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.85rem;">{service_name}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Default HTTP Port</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.88rem;">{default_port}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Package Size</div>
            <div style="font-weight: 600;">{size_str}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Published Date</div>
            <div style="font-weight: 600;">{pub_date}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Maintainer</div>
            <div style="font-weight: 600; font-size: 0.85rem;">{maintainer}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">State &amp; Asset Directory</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.85rem;">{state_dir}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">{config_label}</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.85rem;">{config_path}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Environment Overrides</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.85rem;">{env_config_path}</div>
          </div>
        </div>

        <div style="margin-bottom: 1.25rem;">
          <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Runtime Dependencies</div>
          <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-secondary); background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.5rem 0.75rem;">
            {depends}
          </div>
        </div>

        <div style="margin-bottom: 1.5rem;">
          <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Cryptographic Checksums</div>
          <div style="background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.75rem; font-family: var(--font-mono); font-size: 0.75rem; line-height: 1.6; color: var(--text-secondary);">
            <div><span style="color: var(--text-muted); user-select: none;">SHA-256: </span>{sha256}</div>
            <div><span style="color: var(--text-muted); user-select: none;">SHA-1:   </span>{sha1}</div>
            <div><span style="color: var(--text-muted); user-select: none;">MD5:     </span>{md5}</div>
          </div>
        </div>

        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
          <a href="{deb_download_url}" class="btn btn-primary" download>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
            Download {deb_filename}
          </a>
          <a href="version.json" class="btn btn-outline">version.json</a>
          <a href="../" class="btn btn-outline">&larr; Back to APT Portal</a>
        </div>
      </div>

      <!-- APT Setup Instructions Box -->
      <div class="card" style="border-color: var(--border-indigo);">
        <span class="card-tag">Terminal Quick Start</span>
        <h3 style="font-size: 1.25rem; margin-top: 0.5rem; margin-bottom: 0.75rem;">Install via APT Package Manager</h3>
        <p class="card-desc" style="margin-bottom: 1rem;">
          Execute in your Ubuntu 24.04 terminal to configure the archive key and install <code>{pkg.get('packageName', slug)}</code>:
        </p>
        <pre style="background: var(--bg-code); color: #f4f4f5; padding: 1.25rem; border-radius: var(--radius-md); font-family: var(--font-mono); font-size: 0.85rem; line-height: 1.6; overflow-x: auto; white-space: pre;"><span style="color: #a1a1aa;"># 1. Install Selfso GPG archive keyring</span>
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://ppa.selfso.com/ubuntu/selfso-archive-keyring.gpg | sudo tee /etc/apt/keyrings/selfso-archive-keyring.gpg > /dev/null

<span style="color: #a1a1aa;"># 2. Add repository source list for noble main</span>
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/selfso-archive-keyring.gpg] https://ppa.selfso.com/ubuntu noble main" | sudo tee /etc/apt/sources.list.d/selfso.list

<span style="color: #a1a1aa;"># 3. Update index and install daemon</span>
sudo apt-get update
sudo apt-get install -y {pkg.get('packageName', slug)}

<span style="color: #a1a1aa;"># 4. Inspect daemon service status</span>
systemctl status {service_name}
{binary_path} --version</pre>
      </div>
    </div>
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <span class="brand-badge">SELFSO</span>
          <p>Private computing infrastructure and creative portal. Operating continuously since 2001.</p>
        </div>
        <div class="footer-col">
          <h5>Navigation</h5>
          <ul class="footer-links">
            <li><a href="/">Home</a></li>
            <li><a href="/news.html">News &amp; Timeline</a></li>
            <li><a href="/projects/">Projects</a></li>
            <li><a href="/software/android/">Android Software</a></li>
            <li><a href="/software/windows/">Windows Software</a></li>
            <li><a href="/software/ubuntu/">Ubuntu APT Repo</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h5>Information</h5>
          <ul class="footer-links">
            <li><a href="/info.html">About &amp; Philosophy</a></li>
            <li><a href="/links.html">Resources</a></li>
            <li><a href="/poweredby.html">Powered By</a></li>
            <li><a href="/contact.html">Contact</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; 2001&ndash;2026 SELFSO.COM. All Rights Reserved.</span>
        <span>Built with Pure Static HTML</span>
      </div>
    </div>
  </footer>

  <script>
    (function() {{
      var btn = document.getElementById('mobileNavBtn');
      var menu = document.getElementById('navMenu');
      if (btn && menu) {{
        btn.addEventListener('click', function() {{
          menu.classList.toggle('open');
        }});
      }}
    }})();
  </script>
</body>
</html>
"""


def publish_ubuntu_package(
    slug: str,
    deb_path: Union[str, Path],
    web_root: Union[str, Path],
    gnupg_home: Optional[Union[str, Path]] = None,
    workspace_root: Optional[Union[str, Path]] = None,
    base_apt_url: str = "https://ppa.selfso.com/ubuntu",
    release_notes: Optional[str] = None,
    published_at: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Publish a single Debian package into the Selfso APT repository and update web portal."""
    meta = KNOWN_UBUNTU_PACKAGES.get(slug)
    if not meta:
        raise ValueError(f"Unknown Ubuntu package slug: '{slug}'")

    deb_path = Path(deb_path).resolve()
    if not deb_path.is_file():
        raise FileNotFoundError(f"Source Debian package not found: {deb_path}")

    web_root = Path(web_root).resolve()
    if not gnupg_home:
        gnupg_home = Path(os.environ.get("SELFSO_APT_GNUPG_HOME", str(Path.home() / ".config" / "selfso-apt" / "gnupg")))
    else:
        gnupg_home = Path(gnupg_home).resolve()

    # Inspect package metadata
    deb_info = inspect_deb_package(deb_path)
    pkg_name = deb_info["package"]
    version = deb_info["version"]
    arch = deb_info["architecture"]
    suite = meta.get("suite", "noble")
    component = meta.get("component", "main")

    if dry_run:
        return {
            "dryRun": True,
            "slug": slug,
            "packageName": pkg_name,
            "version": version,
            "architecture": arch,
            "sizeBytes": deb_info["size"],
            "sha256": deb_info["sha256"],
        }

    # Ensure GPG signing key
    fingerprint = ensure_gpg_key(gnupg_home)

    # Prepare pool target
    pool_char = pkg_name[0]
    pool_dir = web_root / "pool" / component / pool_char / pkg_name
    pool_dir.mkdir(parents=True, exist_ok=True)

    dest_deb_name = f"{pkg_name}_{version}_{arch}.deb"
    pool_target = pool_dir / dest_deb_name

    # Remove any older versions in pool directory to maintain a single clean package entry
    for old_deb in pool_dir.glob(f"{pkg_name}_*_{arch}.deb"):
        if old_deb.name != dest_deb_name:
            old_deb.unlink()

    # Stage .deb into pool
    shutil.copy2(deb_path, pool_target)

    # Stage direct download copy into <web_root>/<slug>/<slug>_<arch>.deb
    slug_dir = web_root / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    direct_target = slug_dir / f"{slug}_{arch}.deb"
    shutil.copy2(deb_path, direct_target)

    # Rebuild APT repository metadata (Packages, Packages.gz, Release, InRelease, Release.gpg, keyrings)
    apt_meta = rebuild_apt_metadata(
        web_root=web_root,
        gnupg_home=gnupg_home,
        base_apt_url=base_apt_url,
        suite=suite,
        component=component,
        arch=arch,
    )

    # Manifest dictionary
    rel_pool_path = pool_target.relative_to(web_root).as_posix()
    pub_timestamp = published_at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pkg_manifest: Dict[str, Any] = {
        "slug": slug,
        "packageName": pkg_name,
        "title": meta.get("title", slug),
        "version": version,
        "architecture": arch,
        "suite": suite,
        "component": component,
        "binaryPath": meta.get("binaryPath", f"/usr/sbin/{pkg_name}"),
        "serviceName": meta.get("serviceName", f"{pkg_name}.service"),
        "defaultPort": meta.get("defaultPort", 6874),
        "stateDir": meta.get("stateDir", f"/etc/{pkg_name}"),
        "configLabel": meta.get("configLabel", "Daemon Configuration"),
        "configPath": meta.get("configPath", f"/etc/{pkg_name}/{pkg_name}.cfg"),
        "envConfigPath": meta.get("envConfigPath", f"/etc/default/{pkg_name}"),
        "poolDebPath": rel_pool_path,
        "debUrl": f"{base_apt_url}/{rel_pool_path}",
        "directDownloadUrl": f"{base_apt_url}/{slug}/{slug}_{arch}.deb",
        "pageUrl": f"/software/ubuntu/{slug}/",
        "aptSourceLine": f"deb [arch=amd64 signed-by=/etc/apt/keyrings/selfso-archive-keyring.gpg] {base_apt_url} {suite} {component}",
        "gpgFingerprint": fingerprint,
        "sha256": deb_info["sha256"],
        "sha1": deb_info["sha1"],
        "md5": deb_info["md5"],
        "sizeBytes": deb_info["size"],
        "installedSizeBytes": deb_info["installed_size"] * 1024,
        "publishedAt": pub_timestamp,
        "category": meta.get("category", "Ubuntu Package"),
        "minOs": meta.get("minOs", "Ubuntu 24.04 LTS (noble)"),
        "tagline": meta.get("tagline", deb_info["description"].splitlines()[0] if deb_info["description"] else ""),
        "description": meta.get("description", deb_info["description"]),
        "maintainer": deb_info["maintainer"],
        "depends": deb_info["depends"],
        "projectUrl": meta.get("projectUrl", "/projects/"),
        "releaseNotes": release_notes or f"Release {version} of {pkg_name} for Ubuntu 24.04 LTS.",
    }

    # Update or create catalog (<web_root>/version.json)
    catalog_path = web_root / "version.json"
    catalog: Dict[str, Any] = {
        "schemaVersion": 1,
        "baseUrl": base_apt_url,
        "suite": suite,
        "components": [component],
        "architectures": [arch],
        "updatedAt": pub_timestamp,
        "gpgFingerprint": fingerprint,
        "aptSourceLine": f"deb [arch=amd64 signed-by=/etc/apt/keyrings/selfso-archive-keyring.gpg] {base_apt_url} {suite} {component}",
        "packages": {},
    }
    if catalog_path.is_file():
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing.get("packages"), dict):
                    catalog["packages"].update(existing["packages"])
        except Exception:
            pass

    catalog["packages"][pkg_name] = pkg_manifest

    # Write <web_root>/version.json
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Write <web_root>/<slug>/version.json
    per_pkg_json = slug_dir / "version.json"
    with open(per_pkg_json, "w", encoding="utf-8") as f:
        json.dump(pkg_manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Render HTML portal pages
    portal_html_path = web_root / "index.html"
    portal_html_content = render_portal_html(catalog, base_apt_url)
    portal_html_path.write_text(portal_html_content, encoding="utf-8")

    pkg_html_path = slug_dir / "index.html"
    pkg_html_content = render_package_html(pkg_manifest, base_apt_url)
    pkg_html_path.write_text(pkg_html_content, encoding="utf-8")

    return pkg_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for publish_ubuntu_deb.py."""
    repo_dir = Path(__file__).resolve().parent.parent
    workspace_dir = repo_dir.parent
    default_web_root = workspace_dir / "www" / "selfso" / "html" / "software" / "ubuntu"
    default_gnupg_home = Path(os.environ.get("SELFSO_APT_GNUPG_HOME", str(Path.home() / ".config" / "selfso-apt" / "gnupg")))

    parser = argparse.ArgumentParser(
        description="Publish Ubuntu .deb packages to Selfso APT repository (ppa.selfso.com)."
    )
    parser.add_argument(
        "--slug",
        help="Package slug to publish (e.g. 'octi-server'). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--deb",
        help="Path to source Debian .deb package. Auto-detected from workspace if omitted.",
    )
    parser.add_argument(
        "--publish-all",
        action="store_true",
        help="Discover and publish all known Ubuntu packages in workspace.",
    )
    parser.add_argument(
        "--web-root",
        default=str(default_web_root),
        help=f"Target web root directory (default: {default_web_root})",
    )
    parser.add_argument(
        "--gnupg-home",
        default=str(default_gnupg_home),
        help=f"GPG homedir for archive signing key (default: {default_gnupg_home})",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(workspace_dir),
        help="Workspace root path containing personal project repositories.",
    )
    parser.add_argument(
        "--base-apt-url",
        default="https://ppa.selfso.com/ubuntu",
        help="Base public URL for APT repository distribution.",
    )
    parser.add_argument(
        "--release-notes",
        help="Release notes summary string.",
    )
    parser.add_argument(
        "--published-at",
        help="ISO-8601 publication timestamp.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate publication without modifying files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the generated manifest as JSON to stdout.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    web_root = Path(args.web_root).resolve()
    ws_root = Path(args.workspace_root).resolve()
    gnupg_home = Path(args.gnupg_home).resolve()

    if args.publish_all:
        published_count = 0
        skipped_count = 0
        print(f"Batch publishing all known Ubuntu packages to: {web_root}")
        for slug in KNOWN_UBUNTU_PACKAGES.keys():
            cand = find_candidate_deb(slug, ws_root)
            if not cand:
                print(f"  [-] {slug:18s}: No candidate .deb found under workspace; skipping.")
                skipped_count += 1
                continue

            print(f"  [+] Publishing {slug:16s} from: {cand}")
            try:
                manifest = publish_ubuntu_package(
                    slug=slug,
                    deb_path=cand,
                    web_root=web_root,
                    gnupg_home=gnupg_home,
                    workspace_root=ws_root,
                    base_apt_url=args.base_apt_url,
                    release_notes=args.release_notes,
                    published_at=args.published_at,
                    dry_run=args.dry_run,
                )
                print(
                    f"      => v{manifest['version']} ({manifest['architecture']}), "
                    f"{format_size_bytes(manifest['sizeBytes'])}, "
                    f"sha256={manifest['sha256'][:16]}..."
                )
                published_count += 1
            except Exception as e:
                sys.stderr.write(f"      [!] Error publishing {slug}: {e}\n")

        print(f"\nBatch publish complete: {published_count} published, {skipped_count} skipped.")
        return 0

    # Single-package publishing mode
    slug = args.slug
    if not slug:
        slug = detect_slug_from_cwd(ws_root)
        if slug:
            print(f"Auto-detected package slug from working directory: {slug}")
        else:
            parser.error(
                "Package slug could not be auto-detected from current directory. "
                "Specify --slug or use --publish-all."
            )

    deb_path = args.deb
    if not deb_path:
        cand = find_candidate_deb(slug, ws_root)
        if not cand:
            parser.error(
                f"No candidate .deb found for '{slug}' under workspace {ws_root}. "
                "Specify --deb path explicitly."
            )
        deb_path = cand
        print(f"Discovered candidate .deb package: {deb_path}")

    try:
        manifest = publish_ubuntu_package(
            slug=slug,
            deb_path=deb_path,
            web_root=web_root,
            gnupg_home=gnupg_home,
            workspace_root=ws_root,
            base_apt_url=args.base_apt_url,
            release_notes=args.release_notes,
            published_at=args.published_at,
            dry_run=args.dry_run,
        )
    except Exception as e:
        sys.stderr.write(f"Error publishing Ubuntu package '{slug}': {e}\n")
        return 1

    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        print(f"Successfully published '{slug}' v{manifest['version']} ({manifest['architecture']})")
        print(f"  Package: {web_root / manifest['poolDebPath']}")
        print(f"  Catalog: {web_root / 'version.json'}")
        print(f"  Portal:  {web_root / 'index.html'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
