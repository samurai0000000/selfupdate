#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import argparse
import datetime
import html
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional, Union

# Enable importing gen_version_json from current or scripts directory
_SCRIPT_DIR = Path(__file__).parent.resolve()
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from gen_version_json import compute_sha256, find_aapt2, generate_manifest

# Known Selfso Android application registry
KNOWN_APPS: Dict[str, Dict[str, Any]] = {
    "aimon": {
        "title": "AIMon Companion",
        "applicationId": "com.selfso.aimon",
        "apkFilename": "aimon-companion.apk",
        "tagline": "Ed25519-authenticated AI quota monitor, telemetry dashboard & mobile approval relay.",
        "description": "Mobile companion application for the AIMon daemon, providing real-time AI coding assistant quota tracking, usage insights, hardware bridge status, and cryptographic Ed25519 mobile approval workflows.",
        "category": "AI & Infrastructure",
        "projectUrl": "/projects/",
        "defaultApkCandidates": [
            "aimon/third_party/antimatter/android/app/build/outputs/apk/release/app-release.apk",
            "aimon/third_party/antimatter/android/app/build/outputs/apk/debug/app-debug.apk",
            "aimon/web/aimon-companion.apk",
        ],
        "extraCopyTargets": [
            "aimon/web/aimon-companion.apk",
        ],
    },
    "robohero": {
        "title": "RoboHero Controller",
        "applicationId": "com.selfso.robohero",
        "apkFilename": "robohero.apk",
        "tagline": "17-DOF humanoid robot controller, servo telemetry & motion macro console.",
        "description": "Android control console for the 17-servo RoboHero humanoid robotics platform, supporting real-time joint telemetry (S00..S16), calibration poses, and motion sequence execution.",
        "category": "Robotics & Control",
        "projectUrl": "/projects/",
        "defaultApkCandidates": [
            "robohero/app/android/app/build/outputs/apk/release/RoboHero-*.apk",
            "robohero/app/android/app/build/outputs/apk/debug/RoboHero-*.apk",
        ],
        "extraCopyTargets": [],
    },
    "octi": {
        "title": "OCTI Strategy Game",
        "applicationId": "com.selfso.octi",
        "apkFilename": "octi.apk",
        "tagline": "Abstract strategy board game with directional prongs & minimax AI engine.",
        "description": "Android edition of the OCTI abstract strategy board game, featuring interactive pod and prong mechanics, local pass-and-play, and an alpha-beta pruned minimax AI opponent.",
        "category": "Board Game AI",
        "projectUrl": "/projects/octi/",
        "defaultApkCandidates": [
            "octi/android/app/build/outputs/apk/release/app-release.apk",
            "octi/android/app/build/outputs/apk/debug/app-debug.apk",
        ],
        "extraCopyTargets": [],
    },
    "nigosh": {
        "title": "Nigosh Companion",
        "applicationId": "com.selfso.nigosh",
        "apkFilename": "nigosh.apk",
        "tagline": "Mobile controller & telemetry companion for the two-wheeled self-balancing robot.",
        "description": "Android companion application for the Nigosh two-wheeled self-balancing robotics platform, providing wireless control, PID telemetry inspection, and balance diagnostics.",
        "category": "Robotics & Control",
        "projectUrl": "/projects/",
        "defaultApkCandidates": [
            "nigosh/mobile/android/app/build/outputs/apk/release/app-release.apk",
            "nigosh/mobile/android/app/build/outputs/apk/debug/app-debug.apk",
        ],
        "extraCopyTargets": [],
    },
}

ANDROID_API_MAP: Dict[int, str] = {
    21: "Android 5.0 (Lollipop)+",
    22: "Android 5.1 (Lollipop)+",
    23: "Android 6.0 (Marshmallow)+",
    24: "Android 7.0 (Nougat)+",
    25: "Android 7.1 (Nougat)+",
    26: "Android 8.0 (Oreo)+",
    27: "Android 8.1 (Oreo)+",
    28: "Android 9.0 (Pie)+",
    29: "Android 10+",
    30: "Android 11+",
    31: "Android 12+",
    32: "Android 12L+",
    33: "Android 13+",
    34: "Android 14+",
    35: "Android 15+",
}


def format_min_sdk(min_sdk: Optional[int]) -> str:
    """Format an Android minSdk level into human-readable Android version."""
    if not min_sdk:
        return "Android 7.0+ (API 24)"
    name = ANDROID_API_MAP.get(min_sdk, f"Android API {min_sdk}+")
    return f"{name} (API {min_sdk})"


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


def find_candidate_apk(
    slug: str, workspace_root: Optional[Union[str, Path]] = None
) -> Optional[Path]:
    """Discover the newest compiled APK (by mtime) for a known app within workspace."""
    ws = Path(workspace_root) if workspace_root else (Path.home() / "work")
    meta = KNOWN_APPS.get(slug)
    if not meta:
        return None

    candidates = meta.get("defaultApkCandidates", [])
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
    # Prefer the most recently modified APK (newest build), breaking ties by path name
    found.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return found[0]


def detect_slug_from_cwd(cwd: Optional[Path] = None) -> Optional[str]:
    """Detect the project slug when invoked from inside a project workspace (e.g. ~/work/octi)."""
    cur = (cwd or Path.cwd()).resolve()
    parts = [p.lower() for p in cur.parts]
    for slug in KNOWN_APPS:
        if slug in parts:
            return slug
    return None


def render_portal_html(catalog_data: Dict[str, Any], base_url: str) -> str:
    """Render the master portal index.html with cards for all available apps."""
    apps_dict = catalog_data.get("apps", {})
    sorted_apps = []

    # Sort apps deterministically
    for app_id, app_info in apps_dict.items():
        slug = app_info.get("slug", "")
        sorted_apps.append((slug, app_info))
    sorted_apps.sort(key=lambda item: item[0])

    cards_html = []
    for slug, app in sorted_apps:
        meta = KNOWN_APPS.get(slug, {})
        title = html.escape(app.get("title") or meta.get("title") or slug.capitalize())
        category = html.escape(app.get("category") or meta.get("category") or "Software & Tools")
        tagline = html.escape(app.get("tagline") or meta.get("tagline") or app.get("releaseNotes", ""))
        version_name = html.escape(str(app.get("versionName", "1.0")))
        version_code = int(app.get("versionCode", 1))
        app_id_esc = html.escape(app.get("applicationId", ""))
        min_sdk_str = html.escape(format_min_sdk(app.get("minSdk")))
        size_str = html.escape(format_size_bytes(app.get("sizeBytes", 0)))
        pub_date = html.escape(format_date(app.get("publishedAt", "")))
        sha256 = html.escape(app.get("sha256", ""))
        apk_filename = app.get("apkFilename") or meta.get("apkFilename") or f"{slug}.apk"
        apk_url = html.escape(app.get("apkUrl", f"{slug}/{apk_filename}"))
        page_url = f"{slug}/"

        card = f"""        <!-- App Card: {title} -->
        <div class="card" id="{slug}">
          <span class="card-tag">{category}</span>
          <h2 class="card-title" style="font-size: 1.45rem; margin-top: 0.5rem; margin-bottom: 0.5rem;">{title}</h2>
          <p class="card-desc" style="margin-bottom: 1rem;">{tagline}</p>

          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
            <span class="badge">v{version_name} (Build {version_code})</span>
            <span class="badge">{min_sdk_str}</span>
            <span class="badge">{size_str}</span>
            <span class="badge">{pub_date}</span>
          </div>

          <div style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.75rem;">
            <code>{app_id_esc}</code>
          </div>

          <div style="background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.5rem 0.75rem; font-family: var(--font-mono); font-size: 0.73rem; word-break: break-all; margin-bottom: 1.5rem; color: var(--text-secondary);">
            <span style="color: var(--text-muted); user-select: none;">SHA-256: </span>{sha256}
          </div>

          <div style="display: flex; gap: 0.65rem; flex-wrap: wrap; margin-top: auto;">
            <a href="{apk_url}" class="btn btn-primary" download>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
              </svg>
              Download APK
            </a>
            <a href="{page_url}" class="btn btn-outline">Release Details &rarr;</a>
            <a href="{slug}/version.json" class="btn btn-outline">version.json</a>
          </div>
        </div>"""
        cards_html.append(card)

    cards_joined = "\n\n".join(cards_html) if cards_html else "        <p>No applications published yet.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="SELFSO.COM Android Software Distribution Portal — Independent Android companion applications and algorithmic tools.">
  <title>Android Software & OTA Distribution &bull; SELFSO.COM</title>
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
          <span class="badge" style="margin-bottom: 0.75rem;">OTA Distribution Portal</span>
          <h1 style="font-size: 2.35rem; margin-bottom: 0.75rem;">Selfso Android Applications</h1>
        </div>
        <p style="color: var(--text-secondary); max-width: 720px; font-size: 1.05rem; line-height: 1.6;">
          Independent, open-source Android applications and mobile companion tools engineered for robotics, artificial intelligence, abstract gaming, and systems telemetry. Distributed directly via cryptographic OTA updates.
        </p>

        <!-- Cross-link banner to Windows desktop portal -->
        <div style="margin-top: 1.25rem; display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.85rem; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 0.88rem;">
          <span style="color: var(--accent); font-weight: 600;">Windows Portal:</span>
          <span>Looking for native 64-bit Windows desktop apps?</span>
          <a href="/software/windows/" style="color: var(--accent); text-decoration: underline; margin-left: 0.25rem;">Visit the Windows Software Portal &rarr;</a>
        </div>
      </div>

      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));">
{cards_joined}
      </div>

      <!-- OTA Architecture & Verification Section -->
      <div style="margin-top: 3.5rem; border-top: 1px solid var(--border-subtle); padding-top: 2.5rem;">
        <span class="badge" style="margin-bottom: 0.75rem;">Distribution &amp; Security Architecture</span>
        <h2 style="font-size: 1.75rem; margin-bottom: 0.75rem;">OTA Self-Update Architecture (<code>com.selfso.selfupdate</code>)</h2>
        <p style="color: var(--text-secondary); max-width: 760px; margin-bottom: 1.5rem; line-height: 1.6;">
          All Selfso Android applications embed the first-party <code>com.selfso.selfupdate</code> in-app update engine. On launch or background trigger, applications poll <code>https://www.selfso.com/software/android/version.json</code>, verify cryptographic SHA-256 digests against streaming downloads, and commit in-place package installations via Android&rsquo;s <code>PackageInstaller</code> Session API.
        </p>

        <div class="terminal-box">
          <div class="terminal-header">
            <div class="terminal-dots">
              <span class="terminal-dot dot-red"></span>
              <span class="terminal-dot dot-yellow"></span>
              <span class="terminal-dot dot-green"></span>
            </div>
            <span class="terminal-title">OTA Catalog Verification &bull; curl &amp; sha256sum</span>
          </div>
          <div class="terminal-body">
            <div class="terminal-line">
              <span class="terminal-prompt">$</span>
              <span>curl -s https://www.selfso.com/software/android/version.json</span>
            </div>
            <div style="color: #a1a1aa; margin-bottom: 0.85rem; font-size: 0.8rem;">
              &#123; "schemaVersion": 1, "baseUrl": "https://www.selfso.com/software/android/", "apps": &#123; ... &#125; &#125;
            </div>
            <div class="terminal-line">
              <span class="terminal-prompt">$</span>
              <span>echo "&lt;sha256&gt;  &lt;app&gt;.apk" | sha256sum -c</span>
            </div>
            <div style="color: #34d399; font-size: 0.8rem;">
              &lt;app&gt;.apk: OK (verified authentic)
            </div>
          </div>
        </div>
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


def render_app_html(
    app_manifest: Dict[str, Any], app_meta: Dict[str, Any], base_url: str
) -> str:
    """Render a dedicated detail page index.html for a single application."""
    slug = html.escape(app_manifest.get("slug", ""))
    title = html.escape(app_manifest.get("title") or app_meta.get("title") or slug.capitalize())
    category = html.escape(app_manifest.get("category") or app_meta.get("category") or "Software & Tools")
    tagline = html.escape(app_manifest.get("tagline") or app_meta.get("tagline") or app_manifest.get("releaseNotes", ""))
    description = html.escape(app_manifest.get("description") or app_meta.get("description") or tagline)
    version_name = html.escape(str(app_manifest.get("versionName", "1.0")))
    version_code = int(app_manifest.get("versionCode", 1))
    app_id = html.escape(app_manifest.get("applicationId", ""))
    min_sdk_str = html.escape(format_min_sdk(app_manifest.get("minSdk")))
    size_str = html.escape(format_size_bytes(app_manifest.get("sizeBytes", 0)))
    pub_date = html.escape(format_date(app_manifest.get("publishedAt", "")))
    sha256 = html.escape(app_manifest.get("sha256", ""))
    release_notes = html.escape(app_manifest.get("releaseNotes", ""))
    apk_filename = html.escape(app_manifest.get("apkFilename") or app_meta.get("apkFilename") or f"{slug}.apk")
    project_url = app_manifest.get("projectUrl") or app_meta.get("projectUrl")

    project_btn_html = ""
    if project_url:
        project_btn_html = f'<a href="{html.escape(project_url)}" class="btn btn-outline">Project Documentation</a>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{tagline}">
  <title>{title} &bull; Android Distribution &bull; SELFSO.COM</title>
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
      <a href="../" style="display: inline-flex; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem; color: var(--text-secondary); text-decoration: none; font-size: 0.9rem; font-weight: 500;">
        &larr; Back to Android Software Portal
      </a>

      <div style="margin-bottom: 2rem;">
        <span class="badge" style="margin-bottom: 0.75rem;">{category}</span>
        <h1 style="font-size: 2.35rem; margin-bottom: 0.5rem;">{title}</h1>
        <p style="color: var(--text-secondary); max-width: 720px; font-size: 1.1rem; line-height: 1.6;">
          {tagline}
        </p>
      </div>

      <div style="display: flex; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 1.75rem;">
        <span class="badge">v{version_name} (Build {version_code})</span>
        <span class="badge">{min_sdk_str}</span>
        <span class="badge">{size_str}</span>
        <span class="badge">Published {pub_date}</span>
      </div>

      <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 2.5rem;">
        <a href="{apk_filename}" class="btn btn-primary" download>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
          </svg>
          Download APK ({size_str})
        </a>
        <a href="version.json" class="btn btn-outline">View version.json</a>
        {project_btn_html}
      </div>

      <div class="card" style="margin-bottom: 2rem;">
        <h3 style="font-size: 1.25rem; margin-bottom: 0.75rem;">Application Overview</h3>
        <p style="color: var(--text-secondary); line-height: 1.6; margin-bottom: 1.25rem;">
          {description}
        </p>

        <h4 style="font-size: 1rem; margin-bottom: 0.5rem;">Release Notes</h4>
        <p style="color: var(--text-secondary); line-height: 1.6; margin-bottom: 1rem;">
          {release_notes}
        </p>

        <h4 style="font-size: 1rem; margin-bottom: 0.5rem;">Package Metadata</h4>
        <div style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-secondary);">
          <div><strong>Application ID:</strong> <code>{app_id}</code></div>
          <div><strong>Minimum Android Version:</strong> {min_sdk_str}</div>
          <div><strong>File Size:</strong> {size_str} ({app_manifest.get('sizeBytes', 0)} bytes)</div>
        </div>
      </div>

      <!-- Verification Terminal Box -->
      <div class="terminal-box">
        <div class="terminal-header">
          <div class="terminal-dots">
            <span class="terminal-dot dot-red"></span>
            <span class="terminal-dot dot-yellow"></span>
            <span class="terminal-dot dot-green"></span>
          </div>
          <span class="terminal-title">Cryptographic Verification &bull; {apk_filename}</span>
        </div>
        <div class="terminal-body">
          <div class="terminal-line">
            <span class="terminal-prompt">$</span>
            <span>echo "{sha256}  {apk_filename}" | sha256sum -c</span>
          </div>
          <div style="color: #34d399; margin-bottom: 0.75rem; font-size: 0.8rem;">
            {apk_filename}: OK
          </div>
          <div class="terminal-line">
            <span class="terminal-prompt">$</span>
            <span>curl -s https://www.selfso.com/software/android/{slug}/version.json</span>
          </div>
        </div>
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


def publish_app(
    slug: str,
    apk_path: Union[str, Path],
    web_root: Union[str, Path],
    workspace_root: Optional[Union[str, Path]] = None,
    base_url: str = "https://www.selfso.com/software/android/",
    release_notes: Optional[str] = None,
    no_extra_copy: bool = False,
    keep_debug_suffix: bool = False,
    aapt2_bin: Optional[str] = None,
    published_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish a single Android APK into the static web portal hierarchy."""
    src_apk = Path(apk_path).resolve()
    if not src_apk.is_file():
        raise FileNotFoundError(f"Source APK file not found: {apk_path}")

    w_root = Path(web_root).resolve()
    app_meta = KNOWN_APPS.get(slug, {})

    target_filename = app_meta.get("apkFilename", f"{slug}.apk")
    app_dir = w_root / slug
    app_dir.mkdir(parents=True, exist_ok=True)
    staged_apk = app_dir / target_filename

    # Copy APK to target staging location
    shutil.copy2(src_apk, staged_apk)

    # Clean base url
    clean_base = base_url.rstrip("/")

    # Compute release notes
    notes = release_notes or app_meta.get("tagline") or f"{app_meta.get('title', slug)} release."

    # Discover metadata from source APK location if present
    meta_path = None
    if (src_apk.parent / "output-metadata.json").is_file():
        meta_path = src_apk.parent / "output-metadata.json"

    # Generate single-app manifest
    manifest = generate_manifest(
        apk_path=staged_apk,
        slug=slug,
        title=app_meta.get("title"),
        application_id=app_meta.get("applicationId"),
        apk_url=f"{clean_base}/{slug}/{target_filename}",
        page_url=f"{clean_base}/{slug}/",
        release_notes=notes,
        published_at=published_at,
        base_url=base_url,
        keep_debug_suffix=keep_debug_suffix,
        metadata_path=meta_path,
        aapt2_bin=aapt2_bin,
    )
    if app_meta.get("category"):
        manifest["category"] = app_meta["category"]
    if app_meta.get("tagline"):
        manifest["tagline"] = app_meta["tagline"]
    if app_meta.get("description"):
        manifest["description"] = app_meta["description"]
    if app_meta.get("projectUrl"):
        manifest["projectUrl"] = app_meta["projectUrl"]
    manifest["apkFilename"] = target_filename

    # Write per-app version.json
    per_app_json_path = app_dir / "version.json"
    with open(per_app_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Update master multi-app catalog version.json
    master_json_path = w_root / "version.json"
    catalog: Dict[str, Any] = {
        "schemaVersion": 1,
        "baseUrl": base_url if base_url.endswith("/") else f"{base_url}/",
        "updatedAt": manifest["publishedAt"],
        "apps": {},
    }

    if master_json_path.is_file():
        try:
            with open(master_json_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, dict):
                    if "schemaVersion" in existing:
                        catalog["schemaVersion"] = existing["schemaVersion"]
                    if "apps" in existing and isinstance(existing["apps"], dict):
                        catalog["apps"] = existing["apps"]
        except Exception:
            pass

    catalog["baseUrl"] = base_url if base_url.endswith("/") else f"{base_url}/"
    catalog["updatedAt"] = manifest["publishedAt"]
    catalog["apps"][manifest["applicationId"]] = manifest

    with open(master_json_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Handle extra copy targets if configured
    if not no_extra_copy and workspace_root:
        ws_root = Path(workspace_root).resolve()
        for extra in app_meta.get("extraCopyTargets", []):
            dest = ws_root / extra
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_apk, dest)

    # Render per-app index.html
    app_html = render_app_html(manifest, app_meta, base_url)
    with open(app_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(app_html)

    # Render master portal index.html
    portal_html = render_portal_html(catalog, base_url)
    with open(w_root / "index.html", "w", encoding="utf-8") as f:
        f.write(portal_html)

    return manifest


def publish_all(
    web_root: Union[str, Path],
    workspace_root: Optional[Union[str, Path]] = None,
    base_url: str = "https://www.selfso.com/software/android/",
    release_notes: Optional[str] = None,
    no_extra_copy: bool = False,
    keep_debug_suffix: bool = False,
    aapt2_bin: Optional[str] = None,
    published_at: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Discover and publish all available built APKs from KNOWN_APPS."""
    ws = Path(workspace_root) if workspace_root else (Path.home() / "work")
    published: Dict[str, Dict[str, Any]] = {}

    for slug in KNOWN_APPS:
        cand = find_candidate_apk(slug, ws)
        if cand:
            print(f"Publishing {slug} from {cand}...")
            manifest = publish_app(
                slug=slug,
                apk_path=cand,
                web_root=web_root,
                workspace_root=ws,
                base_url=base_url,
                release_notes=release_notes,
                no_extra_copy=no_extra_copy,
                keep_debug_suffix=keep_debug_suffix,
                aapt2_bin=aapt2_bin,
                published_at=published_at,
            )
            published[slug] = manifest
        else:
            print(f"Skipping {slug}: no compiled APK candidate found.")

    return published


def main(argv: Optional[list] = None) -> int:
    default_web_root = Path.home() / "work/www/selfso/html/software/android"
    default_ws_root = Path.home() / "work"

    parser = argparse.ArgumentParser(
        description="Publish Android APKs to Selfso static web portal."
    )
    parser.add_argument("--slug", help="Application slug to publish (e.g. octi, aimon)")
    parser.add_argument("--apk", help="Path to APK binary to publish")
    parser.add_argument(
        "--publish-all",
        action="store_true",
        help="Discover and publish all known APK binaries in workspace",
    )
    parser.add_argument(
        "--web-root",
        default=str(default_web_root),
        help="Target web root directory for software/android",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(default_ws_root),
        help="Root directory of personal workspace",
    )
    parser.add_argument(
        "--base-url",
        default="https://www.selfso.com/software/android/",
        help="Base distribution URL",
    )
    parser.add_argument("--release-notes", help="Release notes text")
    parser.add_argument(
        "--no-extra-copy",
        action="store_true",
        help="Skip copying to extraCopyTargets",
    )
    parser.add_argument(
        "--keep-debug-suffix",
        action="store_true",
        help="Do not strip .debug suffix from applicationId",
    )
    parser.add_argument("--aapt2", help="Path to aapt2 binary")
    parser.add_argument("--published-at", help="Publication timestamp in ISO-8601 UTC format")

    args = parser.parse_args(argv)

    if args.publish_all:
        published = publish_all(
            web_root=args.web_root,
            workspace_root=args.workspace_root,
            base_url=args.base_url,
            release_notes=args.release_notes,
            no_extra_copy=args.no_extra_copy,
            keep_debug_suffix=args.keep_debug_suffix,
            aapt2_bin=args.aapt2,
            published_at=args.published_at,
        )
        print(f"Successfully published {len(published)} application(s).")
        return 0

    slug = args.slug or detect_slug_from_cwd()
    if not slug:
        sys.stderr.write("Error: Either --slug (or running inside a project dir) or --publish-all is required.\n")
        return 1

    apk_path = args.apk
    if not apk_path:
        cand = find_candidate_apk(slug, args.workspace_root)
        if cand:
            apk_path = str(cand)
        else:
            sys.stderr.write(
                f"Error: No APK provided via --apk and no candidate discovered for {slug}.\n"
            )
            return 1

    try:
        manifest = publish_app(
            slug=slug,
            apk_path=apk_path,
            web_root=args.web_root,
            workspace_root=args.workspace_root,
            base_url=args.base_url,
            release_notes=args.release_notes,
            no_extra_copy=args.no_extra_copy,
            keep_debug_suffix=args.keep_debug_suffix,
            aapt2_bin=args.aapt2,
            published_at=args.published_at,
        )
        print(
            f"Successfully published {manifest['slug']} v{manifest['versionName']} (Build {manifest['versionCode']})."
        )
        return 0
    except Exception as e:
        sys.stderr.write(f"Publication failed: {e}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
