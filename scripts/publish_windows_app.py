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

# Enable importing gen_windows_version_json from current or scripts directory
_SCRIPT_DIR = Path(__file__).parent.resolve()
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from gen_windows_version_json import (
    compute_sha256,
    generate_manifest,
    parse_pe_metadata,
)

# Known Selfso Windows application registry
KNOWN_WINDOWS_APPS: Dict[str, Dict[str, Any]] = {
    "octi": {
        "title": "OCTI Desktop Player",
        "applicationId": "com.selfso.octi",
        "packageFilename": "octi-setup.exe",
        "executableName": "octi.exe",
        "installType": "installer",
        "installerArgs": "/S",
        "arch": "x86_64",
        "minOs": "Windows 10 (64-bit)+",
        "tagline": "64-bit Windows Qt6 desktop client, minimax AI opponent & P2P voice lobby for OCTI.",
        "description": "Native 64-bit Windows Qt6 desktop application for the OCTI abstract strategy board game, featuring interactive board geometry, local alpha-beta minimax AI, online multiplayer lobby, and low-latency P2P voice chat.",
        "category": "Board Game AI",
        "projectUrl": "/projects/octi/",
        "defaultPackageCandidates": [
            "octi/desktop/build/windows/octi-setup-*.exe",
            "octi/desktop/build/windows/octi.exe",
        ],
    },
    "aimon": {
        "title": "AIMon System Tray & EDA Bridge",
        "applicationId": "com.selfso.aimon",
        "packageFilename": "aimon-setup.exe",
        "executableName": "aimon.exe",
        "installType": "installer",
        "installerArgs": "--silent",
        "arch": "x86_64",
        "minOs": "Windows 10 (64-bit)+",
        "tagline": "Windows Qt6 System Tray quota monitor & local RPC bridge for EasyEDA Pro, KiCad & FreeCAD.",
        "description": "Windows System Tray companion and local EDA/CAD hardware automation bridge for AIMon, monitoring real-time AI coding assistant quotas and connecting EasyEDA Pro, KiCad, and FreeCAD to the central AIMon MCP gateway.",
        "category": "AI & EDA Automation",
        "projectUrl": "/projects/",
        "defaultPackageCandidates": [
            "aimon/build/windows/aimon-setup-*.exe",
            "aimon/build/windows/app/aimon.exe",
        ],
    },
    "robohero-teleop": {
        "title": "RoboHero Teleop Studio",
        "applicationId": "com.selfso.robohero.teleop",
        "packageFilename": "robohero_teleop.exe",
        "executableName": "robohero_teleop.exe",
        "installType": "binary",
        "installerArgs": "",
        "arch": "x86_64",
        "minOs": "Windows 10 (64-bit)+",
        "tagline": "Real-time AI pose-tracking teleoperation & 3D URDF visualization studio for RoboHero.",
        "description": "64-bit Windows Qt6, OpenCV, and ONNX Runtime DirectML desktop studio for real-time human pose estimation, kinematic retargeting, and 17-DOF humanoid robot teleoperation.",
        "category": "Robotics & Control",
        "projectUrl": "/projects/",
        "defaultPackageCandidates": [
            "robohero/app/teleop/build/windows-msvc/Release/robohero_teleop.exe",
            "robohero/app/teleop/build/windows/robohero_teleop.exe",
        ],
    },
    "robohero-motion": {
        "title": "RoboHero Motion Studio",
        "applicationId": "com.selfso.robohero.motion",
        "packageFilename": "robohero_motion.exe",
        "executableName": "robohero_motion.exe",
        "installType": "binary",
        "installerArgs": "",
        "arch": "x86_64",
        "minOs": "Windows 10 (64-bit)+",
        "tagline": "Keyframe motion timeline editor, parametric gait generator & 3D URDF previewer.",
        "description": "64-bit Windows Qt6 and OpenGL desktop keyframe animation editor and parametric gait synthesizer for the 17-servo RoboHero humanoid robot.",
        "category": "Robotics & Control",
        "projectUrl": "/projects/",
        "defaultPackageCandidates": [
            "robohero/app/motion/build/windows-msvc/Release/robohero_motion.exe",
            "robohero/app/motion/build/windows/robohero_motion.exe",
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


def find_candidate_package(
    slug: str, workspace_root: Optional[Union[str, Path]] = None
) -> Optional[Path]:
    """Discover the newest compiled package (by mtime) for a known app within workspace."""
    ws = Path(workspace_root) if workspace_root else (Path.home() / "work")
    meta = KNOWN_WINDOWS_APPS.get(slug)
    if not meta:
        return None

    candidates = meta.get("defaultPackageCandidates", [])
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


def detect_slug_from_cwd(workspace_root: Optional[Union[str, Path]] = None) -> Optional[str]:
    """Detect application slug from the current working directory."""
    cwd = Path.cwd().resolve()
    cwd_str = str(cwd)

    if "robohero/app/teleop" in cwd_str:
        return "robohero-teleop"
    elif "robohero/app/motion" in cwd_str:
        return "robohero-motion"
    elif "octi" in cwd_str:
        return "octi"
    elif "aimon" in cwd_str:
        return "aimon"

    for slug in KNOWN_WINDOWS_APPS.keys():
        if slug in cwd.parts:
            return slug

    return None


def render_app_card(
    app_manifest: Dict[str, Any], app_meta: Dict[str, Any], base_url: str
) -> str:
    """Render a single application card for the master portal grid."""
    slug = html.escape(app_manifest.get("slug", ""))
    title = html.escape(app_manifest.get("title") or app_meta.get("title") or slug.capitalize())
    category = html.escape(app_manifest.get("category") or app_meta.get("category") or "Windows Desktop")
    tagline = html.escape(app_manifest.get("tagline") or app_meta.get("tagline") or app_manifest.get("releaseNotes", ""))
    version_name = html.escape(str(app_manifest.get("versionName", "1.0.0")))
    version_code = int(app_manifest.get("versionCode", 1))
    app_id = html.escape(app_manifest.get("applicationId", ""))
    executable_name = html.escape(app_manifest.get("executableName", f"{slug}.exe"))
    arch = html.escape(app_manifest.get("arch", "x86_64"))
    min_os = html.escape(app_manifest.get("minOs", "Windows 10 (64-bit)+"))
    size_str = html.escape(format_size_bytes(app_manifest.get("sizeBytes", 0)))
    pub_date = html.escape(format_date(app_manifest.get("publishedAt", "")))
    sha256 = html.escape(app_manifest.get("sha256", ""))
    pkg_url = html.escape(app_manifest.get("packageUrl", ""))
    install_type = app_manifest.get("installType", "installer")
    install_badge = "Setup Installer" if install_type == "installer" else "Standalone Binary"
    download_btn_text = "Download Installer" if install_type == "installer" else "Download Binary"

    return f"""        <!-- App Card: {title} -->
        <div class="card" id="{slug}">
          <span class="card-tag">{category}</span>
          <h2 class="card-title" style="font-size: 1.45rem; margin-top: 0.5rem; margin-bottom: 0.5rem;">{title}</h2>
          <p class="card-desc" style="margin-bottom: 1rem;">{tagline}</p>

          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
            <span class="badge">v{version_name} (Build {version_code})</span>
            <span class="badge">{min_os}</span>
            <span class="badge">{arch}</span>
            <span class="badge">{install_badge}</span>
            <span class="badge">{size_str}</span>
            <span class="badge">{pub_date}</span>
          </div>

          <div style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">
            <code>{app_id}</code> &bull; <code>{executable_name}</code>
          </div>

          <div style="background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.5rem 0.75rem; font-family: var(--font-mono); font-size: 0.73rem; word-break: break-all; margin-bottom: 1.5rem; color: var(--text-secondary);">
            <span style="color: var(--text-muted); user-select: none;">SHA-256: </span>{sha256}
          </div>

          <div style="display: flex; gap: 0.65rem; flex-wrap: wrap; margin-top: auto;">
            <a href="{pkg_url}" class="btn btn-primary" download>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
              </svg>
              {download_btn_text}
            </a>
            <a href="{slug}/" class="btn btn-outline">Release Details &rarr;</a>
            <a href="{slug}/version.json" class="btn btn-outline">version.json</a>
          </div>
        </div>"""


def render_portal_html(catalog: Dict[str, Any], base_url: str) -> str:
    """Render the master portal index.html for all Windows desktop applications."""
    cards_list = []
    apps = catalog.get("apps", {})

    # Display in preferred order
    preferred_order = ["octi", "aimon", "robohero-teleop", "robohero-motion"]
    seen = set()

    for slug in preferred_order:
        app_entry = None
        for key, candidate in apps.items():
            if (isinstance(candidate, dict) and candidate.get("slug") == slug) or key == slug:
                app_entry = candidate
                break
        if app_entry:
            meta = KNOWN_WINDOWS_APPS.get(slug, {})
            cards_list.append(render_app_card(app_entry, meta, base_url))
            seen.add(app_entry.get("slug", slug))

    for key, candidate in apps.items():
        if isinstance(candidate, dict):
            s = candidate.get("slug", key)
            if s not in seen:
                meta = KNOWN_WINDOWS_APPS.get(s, {})
                cards_list.append(render_app_card(candidate, meta, base_url))
                seen.add(s)

    cards_joined = "\n\n".join(cards_list)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="SELFSO.COM Windows Desktop Software Distribution Portal — Independent 64-bit Windows Qt6 desktop applications and local hardware bridges with zero-dependency C++17 self-update.">
  <title>Windows Software &amp; Self-Update Distribution &bull; SELFSO.COM</title>
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
          <span class="badge" style="margin-bottom: 0.75rem;">Native Windows Desktop Portal</span>
          <h1 style="font-size: 2.35rem; margin-bottom: 0.75rem;">Selfso Windows Desktop Applications</h1>
        </div>
        <p style="color: var(--text-secondary); max-width: 760px; font-size: 1.05rem; line-height: 1.6;">
          Independent, native 64-bit Windows Qt6 desktop applications, robotics control studios, and local EDA/CAD hardware automation bridges. Distributed directly with zero-dependency C++17 cryptographic self-update support.
        </p>

        <!-- Cross-link banner to Android portal -->
        <div style="margin-top: 1.25rem; display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.85rem; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 0.88rem;">
          <span style="color: var(--accent); font-weight: 600;">Android Portal:</span>
          <span>Looking for Android mobile companion tools?</span>
          <a href="/software/android/" style="color: var(--accent); text-decoration: underline; margin-left: 0.25rem;">Visit the Android OTA Portal &rarr;</a>
        </div>
      </div>

      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));">
{cards_joined}
      </div>

      <!-- Self-Update Architecture & Verification Section -->
      <div style="margin-top: 3.5rem; border-top: 1px solid var(--border-subtle); padding-top: 2.5rem;">
        <span class="badge" style="margin-bottom: 0.75rem;">Distribution &amp; Security Architecture</span>
        <h2 style="font-size: 1.75rem; margin-bottom: 0.75rem;">Zero-Dependency C++17 Self-Update Architecture (<code>namespace selfupdate</code>)</h2>
        <p style="color: var(--text-secondary); max-width: 760px; margin-bottom: 1.5rem; line-height: 1.6;">
          All Selfso Windows applications embed the reusable, zero-dependency C++17 <code>selfupdate</code> engine. On launch or manual user trigger, applications poll <code>https://www.selfso.com/software/windows/version.json</code>, verify cryptographic RFC 6234 SHA-256 digests against streaming downloads, and execute either detached setup installers with PID-wait trampoline handoff or atomic <code>.old</code> in-place binary replacements with automatic rollback.
        </p>

        <div class="terminal-box">
          <div class="terminal-header">
            <div class="terminal-dots">
              <span class="terminal-dot dot-red"></span>
              <span class="terminal-dot dot-yellow"></span>
              <span class="terminal-dot dot-green"></span>
            </div>
            <span class="terminal-title">Windows Catalog Verification &bull; curl &amp; sha256sum</span>
          </div>
          <div class="terminal-body">
            <div class="terminal-line">
              <span class="terminal-prompt">$</span>
              <span>curl -s https://www.selfso.com/software/windows/version.json</span>
            </div>
            <div style="color: #a1a1aa; margin-bottom: 0.85rem; font-size: 0.8rem;">
              &#123; "schemaVersion": 1, "baseUrl": "https://www.selfso.com/software/windows/", "apps": &#123; ... &#125; &#125;
            </div>
            <div class="terminal-line">
              <span class="terminal-prompt">$</span>
              <span>echo "&lt;sha256&gt;  &lt;app&gt;-setup.exe" | sha256sum -c</span>
            </div>
            <div style="color: #34d399; font-size: 0.8rem;">
              &lt;app&gt;-setup.exe: OK (verified authentic)
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
    """Render a dedicated detail page index.html for a single Windows application."""
    slug = html.escape(app_manifest.get("slug", ""))
    title = html.escape(app_manifest.get("title") or app_meta.get("title") or slug.capitalize())
    category = html.escape(app_manifest.get("category") or app_meta.get("category") or "Windows Desktop")
    tagline = html.escape(app_manifest.get("tagline") or app_meta.get("tagline") or app_manifest.get("releaseNotes", ""))
    description = html.escape(app_manifest.get("description") or app_meta.get("description") or tagline)
    version_name = html.escape(str(app_manifest.get("versionName", "1.0.0")))
    version_code = int(app_manifest.get("versionCode", 1))
    app_id = html.escape(app_manifest.get("applicationId", ""))
    executable_name = html.escape(app_manifest.get("executableName", f"{slug}.exe"))
    arch = html.escape(app_manifest.get("arch", "x86_64"))
    min_os = html.escape(app_manifest.get("minOs", "Windows 10 (64-bit)+"))
    size_str = html.escape(format_size_bytes(app_manifest.get("sizeBytes", 0)))
    pub_date = html.escape(format_date(app_manifest.get("publishedAt", "")))
    sha256 = html.escape(app_manifest.get("sha256", ""))
    release_notes = html.escape(app_manifest.get("releaseNotes", ""))
    pkg_filename = html.escape(app_manifest.get("packageFilename") or app_meta.get("packageFilename") or f"{slug}.exe")
    install_type = app_manifest.get("installType", "installer")
    install_badge = "Setup Installer" if install_type == "installer" else "Standalone Binary"
    installer_args = html.escape(app_manifest.get("installerArgs", ""))
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
  <title>{title} &bull; Windows Distribution &bull; SELFSO.COM</title>
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
          <a href="../" class="btn btn-outline" style="padding: 0.25rem 0.65rem; font-size: 0.8rem;">&larr; All Windows Applications</a>
        </div>
        <span class="badge" style="margin-bottom: 0.75rem;">{category}</span>
        <h1 style="font-size: 2.35rem; margin-bottom: 0.75rem;">{title}</h1>
        <p style="color: var(--text-secondary); max-width: 720px; font-size: 1.05rem; line-height: 1.6;">
          {description}
        </p>
      </div>

      <div class="card" style="margin-bottom: 2.5rem;">
        <h3 style="font-size: 1.25rem; margin-bottom: 1.25rem;">Release Specifications &bull; v{version_name}</h3>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.25rem; margin-bottom: 1.5rem;">
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Version</div>
            <div style="font-weight: 600;">v{version_name} <span style="font-weight: normal; color: var(--text-muted); font-size: 0.85rem;">(Build {version_code})</span></div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Architecture</div>
            <div style="font-weight: 600;">{arch}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Minimum OS</div>
            <div style="font-weight: 600;">{min_os}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Install Mode</div>
            <div style="font-weight: 600;">{install_badge}</div>
          </div>
          <div>
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Executable</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.88rem;">{executable_name}</div>
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
            <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">Application ID</div>
            <div style="font-weight: 600; font-family: var(--font-mono); font-size: 0.85rem;">{app_id}</div>
          </div>
        </div>

        <div style="margin-bottom: 1.5rem;">
          <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 0.25rem;">SHA-256 Checksum</div>
          <div style="background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.5rem 0.75rem; font-family: var(--font-mono); font-size: 0.75rem; word-break: break-all; color: var(--text-secondary);">
            {sha256}
          </div>
        </div>

        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
          <a href="{pkg_filename}" class="btn btn-primary" download>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align: middle;">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
            Download {pkg_filename}
          </a>
          {project_btn_html}
          <a href="version.json" class="btn btn-outline">version.json</a>
        </div>
      </div>

      <!-- Release Notes -->
      <div style="margin-bottom: 2.5rem;">
        <h3 style="font-size: 1.25rem; margin-bottom: 0.75rem;">Release Notes</h3>
        <p style="color: var(--text-secondary); line-height: 1.6;">
          {release_notes}
        </p>
      </div>

      <!-- Integrity Verification -->
      <div class="terminal-box">
        <div class="terminal-header">
          <div class="terminal-dots">
            <span class="terminal-dot dot-red"></span>
            <span class="terminal-dot dot-yellow"></span>
            <span class="terminal-dot dot-green"></span>
          </div>
          <span class="terminal-title">Cryptographic SHA-256 Verification</span>
        </div>
        <div class="terminal-body">
          <div class="terminal-line">
            <span class="terminal-prompt">$</span>
            <span>echo "{sha256}  {pkg_filename}" | sha256sum -c</span>
          </div>
          <div style="color: #34d399; font-size: 0.8rem;">
            {pkg_filename}: OK
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
    package_path: Union[str, Path],
    web_root: Union[str, Path],
    workspace_root: Optional[Union[str, Path]] = None,
    base_url: str = "https://www.selfso.com/software/windows/",
    release_notes: Optional[str] = None,
    published_at: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Publish a single Windows package into the static web portal hierarchy."""
    src_pkg = Path(package_path).resolve()
    if not src_pkg.is_file():
        raise FileNotFoundError(f"Source package file not found: {package_path}")

    w_root = Path(web_root).resolve()
    app_meta = KNOWN_WINDOWS_APPS.get(slug, {})

    target_filename = app_meta.get("packageFilename", f"{slug}.exe")
    app_dir = w_root / slug
    staged_pkg = app_dir / target_filename

    # Clean base url
    clean_base = base_url.rstrip("/")

    # Compute release notes
    notes = release_notes or app_meta.get("tagline") or f"{app_meta.get('title', slug)} release."

    # If dry_run, generate manifest directly from source
    eval_pkg = src_pkg if dry_run else staged_pkg

    if not dry_run:
        app_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_pkg, staged_pkg)

    # Generate single-app manifest
    manifest = generate_manifest(
        package_path=eval_pkg,
        slug=slug,
        title=app_meta.get("title"),
        application_id=app_meta.get("applicationId"),
        install_type=app_meta.get("installType"),
        installer_args=app_meta.get("installerArgs"),
        executable_name=app_meta.get("executableName"),
        arch=app_meta.get("arch"),
        min_os=app_meta.get("minOs"),
        package_url=f"{clean_base}/{slug}/{target_filename}",
        page_url=f"{clean_base}/{slug}/",
        release_notes=notes,
        published_at=published_at,
        base_url=base_url,
    )

    if app_meta.get("category"):
        manifest["category"] = app_meta["category"]
    if app_meta.get("tagline"):
        manifest["tagline"] = app_meta["tagline"]
    if app_meta.get("description"):
        manifest["description"] = app_meta["description"]
    if app_meta.get("projectUrl"):
        manifest["projectUrl"] = app_meta["projectUrl"]
    manifest["packageFilename"] = target_filename

    if dry_run:
        return manifest

    # Write per-app version.json
    per_app_json_path = app_dir / "version.json"
    with open(per_app_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Update master multi-app catalog version.json non-destructively
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

    # Non-destructive update: find existing key for slug or applicationId
    target_key = manifest["applicationId"]
    existing_key_to_replace = None
    for k, v in catalog.get("apps", {}).items():
        if isinstance(v, dict):
            if v.get("slug") == slug or v.get("applicationId") == target_key or k == slug:
                existing_key_to_replace = k
                break

    if existing_key_to_replace and existing_key_to_replace != target_key:
        del catalog["apps"][existing_key_to_replace]

    catalog["apps"][target_key] = manifest

    with open(master_json_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Render per-app index.html
    app_html = render_app_html(manifest, app_meta, base_url)
    with open(app_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(app_html)

    # Render master portal index.html
    portal_html = render_portal_html(catalog, base_url)
    with open(w_root / "index.html", "w", encoding="utf-8") as f:
        f.write(portal_html)

    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for publish_windows_app.py."""
    parser = argparse.ArgumentParser(
        description="Publish compiled Windows applications to the static distribution portal."
    )
    parser.add_argument(
        "--package",
        "--exe",
        dest="package_path",
        help="Explicit path to compiled .exe or .zip package (auto-discovered if omitted).",
    )
    parser.add_argument(
        "--slug",
        choices=list(KNOWN_WINDOWS_APPS.keys()),
        help="Application slug identifier (auto-detected from current working directory if omitted).",
    )
    parser.add_argument(
        "--publish-all",
        action="store_true",
        help="Batch-publish all known Windows applications with existing built binaries.",
    )
    parser.add_argument(
        "--web-root",
        default=str(Path.home() / "work" / "www" / "selfso" / "html" / "software" / "windows"),
        help="Root path of the static web portal hierarchy.",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(Path.home() / "work"),
        help="Workspace root path containing personal project repositories.",
    )
    parser.add_argument(
        "--base-url",
        default="https://www.selfso.com/software/windows/",
        help="Base public URL for static package distribution.",
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

    if args.publish_all:
        published_count = 0
        skipped_count = 0
        print(f"Batch publishing all known Windows applications to: {web_root}")
        for slug in KNOWN_WINDOWS_APPS.keys():
            cand = find_candidate_package(slug, ws_root)
            if not cand:
                print(f"  [-] {slug:18s}: No candidate package found under workspace; skipping.")
                skipped_count += 1
                continue

            print(f"  [+] Publishing {slug:16s} from: {cand}")
            try:
                manifest = publish_app(
                    slug=slug,
                    package_path=cand,
                    web_root=web_root,
                    workspace_root=ws_root,
                    base_url=args.base_url,
                    release_notes=args.release_notes,
                    published_at=args.published_at,
                    dry_run=args.dry_run,
                )
                print(
                    f"      => v{manifest['versionName']} (code={manifest['versionCode']}), "
                    f"type={manifest['installType']}, {format_size_bytes(manifest['sizeBytes'])}, "
                    f"sha256={manifest['sha256'][:16]}..."
                )
                published_count += 1
            except Exception as e:
                sys.stderr.write(f"      [!] Error publishing {slug}: {e}\n")

        print(f"\nBatch publish complete: {published_count} published, {skipped_count} skipped.")
        return 0

    # Single-app publishing mode
    slug = args.slug
    if not slug:
        slug = detect_slug_from_cwd(ws_root)
        if slug:
            print(f"Auto-detected application slug from working directory: {slug}")
        else:
            parser.error(
                "Application slug could not be auto-detected from current directory. "
                "Specify --slug or use --publish-all."
            )

    package_path = args.package_path
    if not package_path:
        cand = find_candidate_package(slug, ws_root)
        if not cand:
            parser.error(
                f"No candidate package found for '{slug}' under workspace {ws_root}. "
                "Specify --package path explicitly."
            )
        package_path = cand
        print(f"Discovered candidate package: {package_path}")

    try:
        manifest = publish_app(
            slug=slug,
            package_path=package_path,
            web_root=web_root,
            workspace_root=ws_root,
            base_url=args.base_url,
            release_notes=args.release_notes,
            published_at=args.published_at,
            dry_run=args.dry_run,
        )
    except Exception as e:
        sys.stderr.write(f"Error publishing application '{slug}': {e}\n")
        return 1

    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        print(f"Successfully published '{slug}' v{manifest['versionName']} (Build {manifest['versionCode']})")
        print(f"  Package: {web_root / slug / manifest['packageFilename']}")
        print(f"  Catalog: {web_root / 'version.json'}")
        print(f"  Portal:  {web_root / 'index.html'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
