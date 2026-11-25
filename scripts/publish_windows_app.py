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
from typing import Any, Dict, List, Optional, Tuple, Union
import urllib.parse

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
        "packageFilename": "robohero_teleop-setup.exe",
        "executableName": "robohero_teleop.exe",
        "installType": "installer",
        "installerArgs": "/S",
        "arch": "x86_64",
        "minOs": "Windows 10 (64-bit)+",
        "tagline": "Real-time AI pose-tracking teleoperation & 3D URDF visualization studio for RoboHero.",
        "description": "64-bit Windows Qt6, OpenCV, and ONNX Runtime DirectML desktop studio for real-time human pose estimation, kinematic retargeting, and 17-DOF humanoid robot teleoperation.",
        "category": "Robotics & Control",
        "projectUrl": "/projects/",
        "defaultPackageCandidates": [
            "robohero/app/teleop/build/windows/robohero_teleop-setup-*.exe",
            "robohero/app/teleop/build/windows-msvc/Release/robohero_teleop.exe",
            "robohero/app/teleop/build/windows/robohero_teleop.exe",
        ],
    },
    "robohero-motion": {
        "title": "RoboHero Motion Studio",
        "applicationId": "com.selfso.robohero.motion",
        "packageFilename": "robohero_motion-setup.exe",
        "executableName": "robohero_motion.exe",
        "installType": "installer",
        "installerArgs": "/S",
        "arch": "x86_64",
        "minOs": "Windows 10 (64-bit)+",
        "tagline": "Keyframe motion timeline editor, parametric gait generator & 3D URDF previewer.",
        "description": "64-bit Windows Qt6 and OpenGL desktop keyframe animation editor and parametric gait synthesizer for the 17-servo RoboHero humanoid robot.",
        "category": "Robotics & Control",
        "projectUrl": "/projects/",
        "defaultPackageCandidates": [
            "robohero/app/motion/build/windows/robohero_motion-setup-*.exe",
            "robohero/app/motion/build/windows-msvc/Release/robohero_motion.exe",
            "robohero/app/motion/build/windows/robohero_motion.exe",
        ],
    },
    "vidaicut": {
        "title": "VidAICut Studio",
        "applicationId": "com.selfso.vidaicut",
        "packageFilename": "vidaicut-setup.exe",
        "executableName": "vidaicut.exe",
        "installType": "installer",
        "installerArgs": "/S",
        "arch": "x86_64",
        "minOs": "Windows 10 (64-bit)+",
        "tagline": "AI-assisted video editing suite for automated scene segmentation, speed-ramping, pause excision & subtitle/marker generation.",
        "description": "64-bit Windows Qt6 and FFmpeg desktop video editing studio powered by Google Gemini 3.8 Flash for automated scene classification, speed-ramping, idle pause removal, DaVinci Resolve marker export, and SubRip subtitle generation.",
        "category": "AI Video Production",
        "projectUrl": "/projects/",
        "defaultPackageCandidates": [
            "vidaicut/build/windows/vidaicut-setup-*.exe",
            "vidaicut/build/windows/vidaicut.exe",
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
    elif "vidaicut" in cwd_str:
        return "vidaicut"

    for slug in KNOWN_WINDOWS_APPS.keys():
        if slug in cwd.parts:
            return slug

    return None


def parse_portal_context(base_url: str) -> Dict[str, Any]:
    """Derive host, origin, path, and portal-mode flags from base_url."""
    clean_base = (base_url or "https://www.selfso.com/software/windows/").strip().rstrip("/")
    parsed = urllib.parse.urlparse(clean_base)
    scheme = parsed.scheme or "https"
    host = parsed.netloc or "www.selfso.com"
    origin = f"{scheme}://{host}"
    path_slash = (parsed.path.rstrip("/") + "/") if parsed.path else "/software/windows/"
    is_selfso_portal = host.lower() in ("www.selfso.com", "selfso.com")
    arena_host = "octi.selfso.com" if is_selfso_portal else host
    arena_origin = f"https://{arena_host}" if is_selfso_portal else origin
    return {
        "clean_base": clean_base,
        "base_url_slash": f"{clean_base}/",
        "scheme": scheme,
        "site_host": host,
        "site_origin": origin,
        "host_path": f"{host}{path_slash}",
        "is_selfso_portal": is_selfso_portal,
        "arena_host": arena_host,
        "arena_origin": arena_origin,
    }


def resolve_cli_target_defaults(
    slug: Optional[str],
    web_root_arg: Optional[str],
    base_url_arg: Optional[str],
    workspace_root: Union[str, Path],
) -> Tuple[Path, str]:
    """Resolve CLI default web_root and base_url (--slug octi defaults to octi standalone portal)."""
    ws = Path(workspace_root).resolve()
    if slug == "octi":
        w_root = (
            Path(web_root_arg).resolve()
            if web_root_arg
            else (ws / "octi/web/html/software/windows")
        )
        if base_url_arg:
            b_url = base_url_arg
        elif web_root_arg and "www/selfso" in Path(web_root_arg).as_posix():
            b_url = "https://www.selfso.com/software/windows/"
        else:
            b_url = "https://octi.selfso.com/software/windows/"
    else:
        w_root = (
            Path(web_root_arg).resolve()
            if web_root_arg
            else (ws / "www/selfso/html/software/windows")
        )
        b_url = base_url_arg or "https://www.selfso.com/software/windows/"
    return w_root, b_url


def _render_site_chrome(ctx: Dict[str, Any], page_title: str, meta_description: str) -> Tuple[str, str]:
    """Render matching header/head and footer/script HTML for Selfso vs standalone OCTI/custom portals."""
    desc_esc = html.escape(meta_description)
    if ctx["is_selfso_portal"]:
        head_and_header = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{desc_esc}">
  <title>{page_title} &bull; SELFSO.COM</title>
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
  </header>"""
        footer_and_script = """  <footer class="site-footer">
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
    (function() {
      var btn = document.getElementById('mobileNavBtn');
      var menu = document.getElementById('navMenu');
      if (btn && menu) {
        btn.addEventListener('click', function() {
          menu.classList.toggle('open');
        });
      }
    })();
  </script>
</body>
</html>
"""
        return head_and_header, footer_and_script

    host_esc = html.escape(ctx["site_host"])
    head_and_header = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{desc_esc}">
  <title>{page_title} &bull; {host_esc}</title>
  <link rel="stylesheet" href="/css/main.css">
</head>
<body>
  <header class="site-header">
    <div class="nav-container">
      <a href="/" class="brand">
        <span class="brand-badge">OCTI</span>
        <div class="brand-text">
          <span class="brand-name" data-dynamic-host>{host_esc}</span>
          <span class="brand-tagline">Online Arena &bull; Clients &bull; Archive</span>
        </div>
      </a>

      <button class="mobile-toggle" id="mobileNavBtn" aria-label="Toggle Navigation">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <nav>
        <ul class="nav-menu" id="navMenu">
          <li><a href="/" class="nav-link">Arena</a></li>
          <li><a href="/#play" class="nav-link">Browser Play</a></li>
          <li><a href="/archives/" class="nav-link">Archives</a></li>
          <li><a href="/robots/" class="nav-link">Bots</a></li>
          <li><a href="/journal/" class="nav-link">Journal</a></li>
          <li><a href="/software/android/" class="nav-link">Android</a></li>
          <li><a href="/software/windows/" class="nav-link active">Windows</a></li>
        </ul>
      </nav>
    </div>
  </header>"""
    footer_and_script = f"""  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <span class="brand-badge">OCTI</span>
          <p>Online multiplayer OCTI arena, game archive, and native client distribution.</p>
        </div>
        <div class="footer-col">
          <h5>Arena &amp; Downloads</h5>
          <ul class="footer-links">
            <li><a href="/">OCTI Online Arena</a></li>
            <li><a href="/software/windows/">Windows Software</a></li>
            <li><a href="/software/android/">Android Software</a></li>
            <li><a href="/archives/">Game Archives</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h5>Resources</h5>
          <ul class="footer-links">
            <li><a href="/robots/">Bring Your &rsquo;Bot!</a></li>
            <li><a href="/journal/">The OCTI Journal</a></li>
            <li><a href="/privacy/">Privacy Policy</a></li>
            <li><a href="/data-deletion/">Data Deletion</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; 2001&ndash;2026 Charles Chiou &bull; <span data-dynamic-host>{host_esc}</span></span>
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
      if (window.location && window.location.host) {{
        var els = document.querySelectorAll('[data-dynamic-host]');
        for (var i = 0; i < els.length; i++) {{
          els[i].textContent = window.location.host;
        }}
      }}
    }})();
  </script>
</body>
</html>
"""
    return head_and_header, footer_and_script


def render_app_card(
    app_manifest: Dict[str, Any], app_meta: Dict[str, Any], base_url: str
) -> str:
    """Render a single application card for the master portal grid."""
    raw_slug = app_manifest.get("slug", "")
    slug = html.escape(raw_slug)
    title = html.escape(app_manifest.get("title") or app_meta.get("title") or raw_slug.capitalize())
    category = html.escape(app_manifest.get("category") or app_meta.get("category") or "Windows Desktop")
    tagline = html.escape(app_manifest.get("tagline") or app_meta.get("tagline") or app_manifest.get("releaseNotes", ""))
    version_name = html.escape(str(app_manifest.get("versionName", "1.0.0")))
    version_code = int(app_manifest.get("versionCode", 1))
    app_id = html.escape(app_manifest.get("applicationId", ""))
    executable_name = html.escape(app_manifest.get("executableName", f"{raw_slug}.exe"))
    arch = html.escape(app_manifest.get("arch", "x86_64"))
    min_os = html.escape(app_manifest.get("minOs", "Windows 10 (64-bit)+"))
    size_str = html.escape(format_size_bytes(app_manifest.get("sizeBytes", 0)))
    pub_date = html.escape(format_date(app_manifest.get("publishedAt", "")))
    sha256 = html.escape(app_manifest.get("sha256", ""))
    pkg_url = html.escape(app_manifest.get("packageUrl", ""))
    install_type = app_manifest.get("installType", "installer")
    install_badge = "Setup Installer" if install_type == "installer" else "Standalone Binary"
    download_btn_text = "Download Installer" if install_type == "installer" else "Download Binary"

    details_href = f"{slug}/"
    manifest_href = f"{slug}/version.json"

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
            <a href="{details_href}" class="btn btn-outline">Release Details &amp; Install Guide &rarr;</a>
            <a href="#windows-install-guide" class="btn btn-outline">Step-by-Step Setup</a>
            <a href="{manifest_href}" class="btn btn-outline">version.json</a>
          </div>
        </div>"""


def render_windows_install_guide_html(
    pkg_filename: str = "octi-setup.exe",
    app_title: str = "OCTI Desktop Player",
    executable_name: str = "octi.exe",
    app_id: str = "com.selfso.octi",
    sha256_hint: str = "206987c831e12a685c225913c82e5d0b8796feb6e61b744fce97b91100e04041",
    base_url: str = "https://www.selfso.com/software/windows/",
) -> str:
    """Render the comprehensive Windows 11/10 visual installation, permissions, and Google SSO onboarding guide."""
    ctx = parse_portal_context(base_url)
    site_host_esc = html.escape(ctx["site_host"])
    base_url_slash_esc = html.escape(ctx["base_url_slash"])
    arena_host_esc = html.escape(ctx["arena_host"])
    arena_origin_esc = html.escape(ctx["arena_origin"])
    sha_short = (sha256_hint[:16] + "...") if len(sha256_hint) > 16 else (sha256_hint or "<sha256>")
    return f"""
      <!-- Comprehensive Windows 11 / 10 Installation & Google Onboarding Guide -->
      <section id="windows-install-guide" style="margin-top: 3rem; border-top: 1px solid var(--border-subtle); padding-top: 2.75rem;">
        <style>
          .guide-alert-box {{
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-left: 5px solid #d97706;
            border-radius: var(--radius-md);
            padding: 1.5rem 1.75rem;
            margin-bottom: 2rem;
            box-shadow: var(--shadow-card);
          }}
          .guide-nav-pills {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 2.25rem;
            padding: 0.85rem 1rem;
            background: #ffffff;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-card);
          }}
          .guide-nav-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            font-family: var(--font-mono);
            font-size: 0.78rem;
            font-weight: 600;
            color: var(--text-primary);
            background: #f4f4f5;
            border: 1px solid var(--border-subtle);
            padding: 0.4rem 0.8rem;
            border-radius: var(--radius-sm);
            text-decoration: none !important;
          }}
          .guide-nav-pill:hover {{
            background: #18181b;
            color: #ffffff;
            border-color: #18181b;
          }}
          .guide-step-card {{
            background: #ffffff;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 2rem;
            margin-bottom: 2.25rem;
            box-shadow: var(--shadow-card);
          }}
          .guide-step-header {{
            display: flex;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 1.25rem;
          }}
          .guide-step-num {{
            flex-shrink: 0;
            width: 38px;
            height: 38px;
            border-radius: 50%;
            background: #18181b;
            color: #ffffff;
            font-family: var(--font-mono);
            font-weight: 700;
            font-size: 0.95rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 6px rgba(0,0,0,0.15);
          }}
          .guide-callout-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background: #dc2626;
            color: #ffffff;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            font-weight: 700;
            margin-right: 0.35rem;
            vertical-align: middle;
          }}
          .guide-screenshot-frame {{
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            overflow: hidden;
            margin-top: 1.25rem;
            box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08);
          }}
          .guide-screenshot-bar {{
            background: #0f172a;
            color: #e2e8f0;
            padding: 0.55rem 1rem;
            font-family: var(--font-mono);
            font-size: 0.76rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
          }}
          .guide-checklist {{
            list-style: none;
            padding: 0;
            margin: 0 0 1.25rem 0;
          }}
          .guide-checklist li {{
            position: relative;
            padding: 0.6rem 0.85rem;
            margin-bottom: 0.55rem;
            background: #fafafa;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            color: var(--text-secondary);
            font-size: 0.95rem;
            line-height: 1.6;
          }}
          .guide-checklist li strong {{
            color: var(--text-primary);
          }}
        </style>

        <span class="badge badge-vermilion" style="margin-bottom: 0.75rem;">Step-by-Step Visual Installation &amp; Onboarding Guide</span>
        <h2 style="font-size: 2rem; margin-bottom: 0.75rem;">How to Install on Windows 11 / 10 &amp; Onboard with Google</h2>
        <p style="color: var(--text-secondary); max-width: 820px; font-size: 1.05rem; line-height: 1.7; margin-bottom: 1.5rem;">
          Because desktop applications on this portal are distributed directly from <code>{site_host_esc}</code> as independent first-party builds rather than through the commercial Microsoft Store, <strong>Microsoft Windows 11</strong> and your web browser will show unrecognized-app security prompts on first install. Follow this visual guide to understand why these warnings appear, safely complete installation, configure Windows permissions, and sign in with your <strong>Google Account</strong>.
        </p>

        <!-- Why Windows 11 Warns You (The Facts) -->
        <div class="guide-alert-box" id="win-why-warnings">
          <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.65rem;">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#b45309" stroke-width="2.2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
            <h3 style="font-size: 1.2rem; color: #92400e; margin: 0;">Why Does Windows 11 Flag <code>{pkg_filename}</code> as an &ldquo;Unrecognized App&rdquo;?</h3>
          </div>
          <p style="color: #78350f; font-size: 0.96rem; line-height: 1.65; margin-bottom: 0.85rem;">
            <strong>1. Direct Independent Distribution (No Commercial EV Certificate):</strong> Microsoft Windows 11 <strong>Defender SmartScreen</strong> requires software publishers either to distribute through the Microsoft Store or to purchase expensive commercial Extended Validation (EV) Authenticode hardware tokens from third-party Certificate Authorities and accumulate tens of thousands of telemetry downloads before suppressing warnings. Because independent, ad-free engineering and strategy software is published here directly without commercial middlemen, Windows labels the installer as <code>Publisher: Unknown publisher</code>.
          </p>
          <p style="color: #78350f; font-size: 0.96rem; line-height: 1.65; margin-bottom: 0;">
            <strong>2. Cryptographic Integrity Without Third-Party Lock-In:</strong> Instead of commercial store gatekeeping, every installer is served over TLS from <code>{site_host_esc}</code> with a published <strong>RFC 6234 SHA-256 checksum</strong> (<code>{sha_short}</code>) in <code>version.json</code>. Once installed, the built-in C++17 <code>selfupdate</code> engine verifies future updates cryptographically in memory before applying them.
          </p>
        </div>

        <!-- Quick Jump Navigation -->
        <div class="guide-nav-pills" aria-label="Installation Guide Steps">
          <a href="#win-step-1" class="guide-nav-pill"><span>1</span> Browser Download Keep</a>
          <a href="#win-step-2" class="guide-nav-pill"><span>2</span> Windows 11 SmartScreen</a>
          <a href="#win-step-3" class="guide-nav-pill"><span>3</span> App Settings &amp; Setup Wizard</a>
          <a href="#win-step-4" class="guide-nav-pill"><span>4</span> Firewall &amp; Mic Permissions</a>
          <a href="#win-step-5" class="guide-nav-pill"><span>5</span> Google Account Onboarding</a>
        </div>

        <!-- STEP 1: Browser Download Prompt -->
        <div class="guide-step-card" id="win-step-1">
          <div class="guide-step-header">
            <span class="guide-step-num">1</span>
            <div>
              <span class="badge" style="margin-bottom: 0.35rem;">Microsoft Edge &bull; Google Chrome &bull; Brave</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 1: Download <code>{pkg_filename}</code> &amp; Confirm Browser Keep Prompt</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                When downloading an independent <code>.exe</code> setup installer, Microsoft Edge or Google Chrome may pause the file in the Downloads bar with <em>&ldquo;{pkg_filename} isn&rsquo;t commonly downloaded.&rdquo;</em>
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Open Browser Downloads (<code>Ctrl + J</code>):</strong> In the top-right Downloads popup of Microsoft Edge or Chrome, hover over <code>{pkg_filename}</code> and click the three-dot <strong><code>&bull;&bull;&bull;</code> (More actions)</strong> icon, then click <strong>Keep</strong>.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Expand &ldquo;Show more&rdquo;:</strong> A secondary prompt appears titled <em>&ldquo;Make sure you trust {pkg_filename} before you open it.&rdquo;</em> Click <strong>Show more &#8964;</strong> to reveal the confirmation action.</li>
            <li><span class="guide-callout-badge">3</span> <strong>Click &ldquo;Keep anyway&rdquo; &amp; Open File:</strong> Click <strong>Keep anyway</strong>, then click <strong>Open file</strong> (or double-click <code>{pkg_filename}</code> in your <code>Downloads</code> folder).</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 1 &bull; Browser Download Verification (Microsoft Edge / Chrome on Windows 11)</span>
              <span>File: {pkg_filename}</span>
            </div>
            <svg viewBox="0 0 920 340" width="100%" style="display: block; background: #0f172a; font-family: 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Screenshot of Microsoft Edge Download Keep and Keep Anyway prompts">
              <!-- Left Panel: Downloads Flyout -->
              <rect x="20" y="20" width="420" height="300" rx="10" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
              <text x="40" y="52" fill="#f8fafc" font-size="15" font-weight="700">Downloads</text>
              <text x="360" y="52" fill="#60a5fa" font-size="12">See more</text>
              <line x1="20" y1="66" x2="440" y2="66" stroke="#334155" stroke-width="1"/>

              <!-- Download Item Card -->
              <rect x="34" y="82" width="392" height="108" rx="8" fill="#0f172a" stroke="#f59e0b" stroke-width="1.5"/>
              <polygon points="56,105 68,126 44,126" fill="#f59e0b"/>
              <text x="54" y="124" fill="#0f172a" font-size="11" font-weight="800">!</text>
              <text x="80" y="108" fill="#f8fafc" font-size="13" font-weight="600">{pkg_filename} isn&apos;t commonly</text>
              <text x="80" y="126" fill="#f8fafc" font-size="13" font-weight="600">downloaded. Make sure you trust it.</text>
              <text x="80" y="148" fill="#94a3b8" font-size="11">{base_url_slash_esc}...</text>

              <!-- 3-dot button highlighted -->
              <rect x="372" y="92" width="40" height="28" rx="6" fill="#334155" stroke="#ef4444" stroke-width="2.5"/>
              <text x="381" y="110" fill="#ffffff" font-size="15" font-weight="700">&bull;&bull;&bull;</text>
              <circle cx="364" cy="90" r="12" fill="#dc2626"/>
              <text x="360" y="95" fill="#ffffff" font-size="12" font-weight="700">1</text>

              <!-- Context Menu Dropdown -->
              <rect x="250" y="128" width="166" height="114" rx="7" fill="#1e293b" stroke="#64748b" stroke-width="1.5"/>
              <rect x="256" y="136" width="154" height="32" rx="5" fill="#ef4444" fill-opacity="0.22" stroke="#ef4444" stroke-width="2"/>
              <text x="274" y="157" fill="#ffffff" font-size="13" font-weight="700">&#10003;  Keep</text>
              <text x="274" y="188" fill="#cbd5e1" font-size="12">Delete</text>
              <text x="274" y="216" fill="#cbd5e1" font-size="12">Report as safe</text>

              <!-- Arrow between panels -->
              <path d="M 448 170 L 472 170" stroke="#60a5fa" stroke-width="3" stroke-linecap="round"/>
              <polygon points="470,164 480,170 470,176" fill="#60a5fa"/>

              <!-- Right Panel: Make sure you trust dialog -->
              <rect x="484" y="20" width="416" height="300" rx="10" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
              <circle cx="518" cy="56" r="14" fill="#f59e0b" fill-opacity="0.2" stroke="#f59e0b" stroke-width="2"/>
              <text x="514" y="61" fill="#fbbf24" font-size="15" font-weight="800">!</text>
              <text x="542" y="54" fill="#f8fafc" font-size="14" font-weight="700">Make sure you trust {pkg_filename}</text>
              <text x="542" y="73" fill="#f8fafc" font-size="14" font-weight="700">before you open it</text>
              <text x="504" y="104" fill="#cbd5e1" font-size="12">Microsoft Defender SmartScreen couldn&apos;t verify if this file is</text>
              <text x="504" y="122" fill="#cbd5e1" font-size="12">safe because it isn&apos;t commonly downloaded.</text>
              <text x="504" y="146" fill="#94a3b8" font-size="11.5">Name: {pkg_filename}  &bull;  Publisher: Unknown</text>

              <!-- Show more link highlighted -->
              <rect x="500" y="162" width="118" height="28" rx="5" fill="#dc2626" fill-opacity="0.18" stroke="#ef4444" stroke-width="2"/>
              <text x="512" y="181" fill="#93c5fd" font-size="12.5" font-weight="700">Show more &#8964;</text>
              <circle cx="628" cy="176" r="12" fill="#dc2626"/>
              <text x="624" y="181" fill="#ffffff" font-size="12" font-weight="700">2</text>

              <!-- Expanded Keep anyway link highlighted -->
              <rect x="500" y="202" width="142" height="32" rx="6" fill="#16a34a" fill-opacity="0.22" stroke="#22c55e" stroke-width="2.5"/>
              <text x="514" y="223" fill="#86efac" font-size="13" font-weight="700">Keep anyway</text>
              <circle cx="654" cy="218" r="12" fill="#dc2626"/>
              <text x="650" y="223" fill="#ffffff" font-size="12" font-weight="700">3</text>

              <!-- Bottom buttons -->
              <rect x="654" y="262" width="110" height="36" rx="6" fill="#2563eb"/>
              <text x="688" y="285" fill="#ffffff" font-size="13" font-weight="600">Delete</text>
              <rect x="774" y="262" width="106" height="36" rx="6" fill="#334155"/>
              <text x="807" y="285" fill="#e2e8f0" font-size="13">Cancel</text>
            </svg>
          </div>
        </div>

        <!-- STEP 2: Windows 11 Defender SmartScreen -->
        <div class="guide-step-card" id="win-step-2">
          <div class="guide-step-header">
            <span class="guide-step-num">2</span>
            <div>
              <span class="badge badge-vermilion" style="margin-bottom: 0.35rem;">Most Common Roadblock on Windows 11</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 2: Bypass Windows 11 SmartScreen (&ldquo;Windows protected your PC&rdquo;)</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                When you launch <code>{pkg_filename}</code>, Windows 11 displays a blue dialog titled <strong>&ldquo;Windows protected your PC&rdquo;</strong>. By default, Windows hides the <em>Run anyway</em> button until you click <strong>More info</strong>.
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Click &ldquo;More info&rdquo; (Do NOT click Don&rsquo;t run):</strong> In the blue <em>Windows protected your PC</em> window, click the underlined <strong>More info</strong> link directly beneath the warning paragraph.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Verify App Name &amp; Click &ldquo;Run anyway&rdquo;:</strong> The dialog expands to show <code>App: {pkg_filename}</code> and <code>Publisher: Unknown publisher</code>, and reveals a second button at the bottom. Click <strong>Run anyway</strong> to start the setup wizard.</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 2 &bull; Windows 11 Defender SmartScreen Modal (&ldquo;More info&rdquo; &rarr; &ldquo;Run anyway&rdquo;)</span>
              <span>Windows 11 Security</span>
            </div>
            <svg viewBox="0 0 920 360" width="100%" style="display: block; background: #0f172a; font-family: 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Before and after screenshot of Windows protected your PC SmartScreen dialog showing More info and Run anyway">
              <!-- State A: Initial SmartScreen Prompt -->
              <rect x="20" y="22" width="420" height="316" rx="8" fill="#004578" stroke="#38bdf8" stroke-width="1.5"/>
              <rect x="20" y="22" width="420" height="32" rx="8" fill="#003359"/>
              <text x="36" y="43" fill="#bae6fd" font-size="11.5" font-weight="600">STATE A &bull; Initial Windows 11 Prompt (Run Button Hidden)</text>

              <text x="44" y="86" fill="#ffffff" font-size="22" font-weight="300">Windows protected your PC</text>
              <text x="44" y="118" fill="#e0f2fe" font-size="12.5">Microsoft Defender SmartScreen prevented an unrecognized</text>
              <text x="44" y="136" fill="#e0f2fe" font-size="12.5">app from starting. Running this app might put your PC</text>
              <text x="44" y="154" fill="#e0f2fe" font-size="12.5">at risk.</text>

              <!-- Highlighted More info link -->
              <rect x="40" y="170" width="90" height="28" rx="5" fill="#dc2626" fill-opacity="0.35" stroke="#fca5a5" stroke-width="2.5"/>
              <text x="48" y="189" fill="#ffffff" font-size="13" font-weight="700" text-decoration="underline">More info</text>
              <circle cx="144" cy="184" r="13" fill="#dc2626"/>
              <text x="140" y="189" fill="#ffffff" font-size="12.5" font-weight="700">1</text>
              <text x="164" y="189" fill="#fde047" font-size="12" font-weight="700">&larr; Click &ldquo;More info&rdquo; first!</text>

              <!-- Don't run button -->
              <rect x="304" y="280" width="114" height="36" rx="4" fill="#005a9e" stroke="#7dd3fc" stroke-width="1.5"/>
              <text x="332" y="303" fill="#ffffff" font-size="13" font-weight="600">Don&apos;t run</text>

              <!-- Arrow between states -->
              <path d="M 448 180 L 472 180" stroke="#fde047" stroke-width="3" stroke-linecap="round"/>
              <polygon points="470,174 480,180 470,186" fill="#fde047"/>

              <!-- State B: Expanded SmartScreen Prompt -->
              <rect x="480" y="22" width="420" height="316" rx="8" fill="#004578" stroke="#38bdf8" stroke-width="1.5"/>
              <rect x="480" y="22" width="420" height="32" rx="8" fill="#003359"/>
              <text x="496" y="43" fill="#86efac" font-size="11.5" font-weight="600">STATE B &bull; After Clicking &ldquo;More info&rdquo; (Run Anyway Revealed)</text>

              <text x="504" y="86" fill="#ffffff" font-size="22" font-weight="300">Windows protected your PC</text>
              <text x="504" y="116" fill="#e0f2fe" font-size="12">Microsoft Defender SmartScreen prevented an unrecognized</text>
              <text x="504" y="134" fill="#e0f2fe" font-size="12">app from starting. Running this app might put your PC at risk.</text>

              <rect x="504" y="152" width="372" height="58" rx="6" fill="#003359"/>
              <text x="518" y="174" fill="#f8fafc" font-size="12.5" font-weight="600">App:  <tspan font-family="monospace" fill="#93c5fd">{pkg_filename}</tspan></text>
              <text x="518" y="196" fill="#f8fafc" font-size="12.5" font-weight="600">Publisher:  <tspan fill="#cbd5e1">Unknown publisher</tspan></text>

              <!-- Run anyway button highlighted -->
              <rect x="634" y="276" width="124" height="42" rx="5" fill="#16a34a" stroke="#fde047" stroke-width="3"/>
              <text x="655" y="302" fill="#ffffff" font-size="13.5" font-weight="700">Run anyway</text>
              <circle cx="622" cy="274" r="13" fill="#dc2626"/>
              <text x="618" y="279" fill="#ffffff" font-size="12.5" font-weight="700">2</text>
              <text x="504" y="302" fill="#fde047" font-size="12" font-weight="700">Click &ldquo;Run anyway&rdquo; &rarr;</text>

              <!-- Don't run button -->
              <rect x="768" y="279" width="110" height="36" rx="4" fill="#003359" stroke="#64748b" stroke-width="1"/>
              <text x="795" y="302" fill="#cbd5e1" font-size="13">Don&apos;t run</text>
            </svg>
          </div>
        </div>

        <!-- STEP 3: Windows 11 App Settings, SmartScreen Policy & Setup Wizard -->
        <div class="guide-step-card" id="win-step-3">
          <div class="guide-step-header">
            <span class="guide-step-num">3</span>
            <div>
              <span class="badge" style="margin-bottom: 0.35rem;">Windows 11 Settings &bull; UAC &bull; NSIS Installer</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 3: Adjust Windows 11 App Settings (If Blocked) &amp; Complete Setup Wizard</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                If your Windows 11 PC is restricted to <em>&ldquo;The Microsoft Store only&rdquo;</em> or hides the <em>More info</em> link, adjust your Windows 11 App Settings as shown below, then complete the Setup Wizard.
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Allow Apps from Anywhere in Windows Settings:</strong> Press <code>Win + I</code> to open <strong>Settings &rarr; Apps &rarr; Advanced app settings</strong>. Next to <strong>Choose where to get apps</strong>, change the dropdown from <em>The Microsoft Store only</em> to <strong>Anywhere</strong>.</li>
            <li><span class="guide-callout-badge">2</span> <strong>If SmartScreen Still Blocks Execution:</strong> Open the Start Menu, type <strong>Windows Security</strong>, go to <strong>App &amp; browser control &rarr; Reputation-based protection settings</strong>, and ensure <em>Check apps and files</em> is not locked to Block mode.</li>
            <li><span class="guide-callout-badge">3</span> <strong>Accept UAC &amp; Finish Setup Wizard:</strong> When Windows User Account Control (UAC) asks <em>&ldquo;Do you want to allow this app from an unknown publisher to make changes to your device?&rdquo;</em>, click <strong>Yes</strong>, then click <strong>Install &rarr; Finish</strong> in the setup wizard.</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 3 &bull; Windows 11 Settings &rarr; Apps &rarr; Advanced App Settings &amp; Setup Wizard</span>
              <span>Settings (Win + I)</span>
            </div>
            <svg viewBox="0 0 920 330" width="100%" style="display: block; background: #0f172a; font-family: 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Screenshot of Windows 11 Settings Advanced app settings Choose where to get apps set to Anywhere and Setup Wizard">
              <!-- Left Panel: Windows 11 Settings -->
              <rect x="20" y="20" width="465" height="290" rx="10" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
              <text x="40" y="48" fill="#94a3b8" font-size="12">Settings  &rsaquo;  Apps  &rsaquo;  <tspan fill="#f8fafc" font-weight="700">Advanced app settings</tspan></text>
              <line x1="20" y1="62" x2="485" y2="62" stroke="#334155" stroke-width="1"/>

              <!-- Choose where to get apps row -->
              <rect x="34" y="78" width="436" height="92" rx="8" fill="#0f172a" stroke="#ef4444" stroke-width="2"/>
              <text x="50" y="106" fill="#f8fafc" font-size="13.5" font-weight="700">Choose where to get apps</text>
              <text x="50" y="126" fill="#94a3b8" font-size="11.5">Installing apps only from the Microsoft Store helps protect</text>
              <text x="50" y="142" fill="#94a3b8" font-size="11.5">your device, or allow apps from anywhere on the web.</text>

              <!-- Dropdown set to Anywhere -->
              <rect x="328" y="96" width="128" height="36" rx="6" fill="#16a34a" fill-opacity="0.25" stroke="#22c55e" stroke-width="2.5"/>
              <text x="344" y="119" fill="#86efac" font-size="13" font-weight="700">Anywhere   &#8964;</text>
              <circle cx="322" cy="94" r="12" fill="#dc2626"/>
              <text x="318" y="99" fill="#ffffff" font-size="12" font-weight="700">1</text>

              <!-- Windows Security Reputation-based protection row -->
              <rect x="34" y="184" width="436" height="108" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1"/>
              <text x="50" y="210" fill="#f8fafc" font-size="13" font-weight="700">Windows Security &rsaquo; App &amp; browser control</text>
              <text x="50" y="232" fill="#cbd5e1" font-size="11.5">Reputation-based protection &rarr; Check apps and files:</text>
              <text x="50" y="254" fill="#93c5fd" font-size="11.5" font-weight="600">Set to &ldquo;Warn&rdquo; (default) so &ldquo;Run anyway&rdquo; is available</text>
              <circle cx="446" cy="206" r="12" fill="#dc2626"/>
              <text x="442" y="211" fill="#ffffff" font-size="12" font-weight="700">2</text>

              <!-- Right Panel: Setup Wizard & UAC -->
              <rect x="505" y="20" width="395" height="290" rx="10" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
              <rect x="505" y="20" width="395" height="34" rx="10" fill="#0f172a"/>
              <text x="524" y="42" fill="#f8fafc" font-size="12.5" font-weight="700">{app_title} Setup Wizard</text>

              <text x="528" y="82" fill="#f8fafc" font-size="15" font-weight="700">Completing {app_title} Setup</text>
              <text x="528" y="106" fill="#cbd5e1" font-size="12">Installed to: C:\\Program Files\\Selfso\\{executable_name}</text>
              <text x="528" y="128" fill="#86efac" font-size="12" font-weight="600">&#10003; Desktop &amp; Start Menu Shortcuts Created</text>
              <text x="528" y="150" fill="#86efac" font-size="12" font-weight="600">&#10003; C++17 Self-Update Engine Registered</text>

              <!-- Run checkbox -->
              <rect x="528" y="176" width="18" height="18" rx="4" fill="#2563eb"/>
              <text x="532" y="190" fill="#ffffff" font-size="13" font-weight="700">&#10003;</text>
              <text x="556" y="190" fill="#f8fafc" font-size="13" font-weight="600">Launch {app_title} now</text>

              <!-- Finish button highlighted -->
              <rect x="752" y="252" width="124" height="38" rx="6" fill="#2563eb" stroke="#fde047" stroke-width="2.5"/>
              <text x="794" y="276" fill="#ffffff" font-size="13.5" font-weight="700">Finish</text>
              <circle cx="742" cy="252" r="12" fill="#dc2626"/>
              <text x="738" y="257" fill="#ffffff" font-size="12" font-weight="700">3</text>
            </svg>
          </div>
        </div>

        <!-- STEP 4: Windows Defender Firewall & Microphone Permissions -->
        <div class="guide-step-card" id="win-step-4">
          <div class="guide-step-header">
            <span class="guide-step-num">4</span>
            <div>
              <span class="badge" style="margin-bottom: 0.35rem;">Network &amp; Voice Chat Permissions</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 4: Grant Windows Firewall &amp; Microphone Permissions</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                When launching <code>{executable_name}</code> for online multiplayer, P2P voice chat, or local hardware bridge telemetry, Windows will ask for network and microphone permissions.
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Check Private &amp; Public Networks in Windows Firewall:</strong> When the <em>Windows Defender Firewall has blocked some features of this app</em> alert appears, check both <strong>Private networks</strong> and <strong>Public networks</strong>.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Click &ldquo;Allow access&rdquo;:</strong> Click <strong>Allow access</strong> at the bottom right of the Firewall prompt so online lobby connections and P2P voice streams are not dropped.</li>
            <li><span class="guide-callout-badge">3</span> <strong>Enable Desktop Microphone Access (For Voice Chat):</strong> Open <strong>Windows Settings (<code>Win + I</code>) &rarr; Privacy &amp; security &rarr; Microphone</strong> and ensure both <strong>Microphone access</strong> and <strong>Let desktop apps access your microphone</strong> are toggled <strong>On</strong>.</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 4 &bull; Windows Defender Firewall Alert &amp; Settings &rarr; Privacy &amp; Security &rarr; Microphone</span>
              <span>Executable: {executable_name}</span>
            </div>
            <svg viewBox="0 0 920 320" width="100%" style="display: block; background: #0f172a; font-family: 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Screenshot of Windows Defender Firewall Allow access dialog and Windows 11 Microphone privacy settings">
              <!-- Left Panel: Windows Defender Firewall -->
              <rect x="20" y="20" width="445" height="280" rx="10" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
              <rect x="20" y="20" width="445" height="34" rx="10" fill="#0f172a"/>
              <text x="38" y="42" fill="#f8fafc" font-size="12.5" font-weight="700">Windows Security Alert &bull; Windows Defender Firewall</text>

              <text x="38" y="76" fill="#93c5fd" font-size="13.5" font-weight="700">Windows Defender Firewall has blocked some features</text>
              <text x="38" y="98" fill="#cbd5e1" font-size="12">Name: <tspan fill="#f8fafc" font-weight="600">{app_title} ({executable_name})</tspan></text>
              <text x="38" y="118" fill="#cbd5e1" font-size="12">Publisher: <tspan fill="#94a3b8">Unknown</tspan></text>

              <!-- Network checkboxes highlighted -->
              <rect x="34" y="132" width="415" height="86" rx="7" fill="#0f172a" stroke="#ef4444" stroke-width="2"/>
              <rect x="48" y="146" width="18" height="18" rx="4" fill="#2563eb"/>
              <text x="52" y="160" fill="#ffffff" font-size="13" font-weight="700">&#10003;</text>
              <text x="74" y="160" fill="#f8fafc" font-size="12.5" font-weight="600">Private networks, such as my home or work network</text>

              <rect x="48" y="182" width="18" height="18" rx="4" fill="#2563eb"/>
              <text x="52" y="196" fill="#ffffff" font-size="13" font-weight="700">&#10003;</text>
              <text x="74" y="196" fill="#f8fafc" font-size="12.5" font-weight="600">Public networks, such as those in airports and coffee shops</text>
              <circle cx="436" cy="144" r="12" fill="#dc2626"/>
              <text x="432" y="149" fill="#ffffff" font-size="12" font-weight="700">1</text>

              <!-- Allow access button highlighted -->
              <rect x="218" y="242" width="130" height="38" rx="6" fill="#16a34a" stroke="#fde047" stroke-width="2.5"/>
              <text x="242" y="266" fill="#ffffff" font-size="13" font-weight="700">Allow access</text>
              <circle cx="206" cy="242" r="12" fill="#dc2626"/>
              <text x="202" y="247" fill="#ffffff" font-size="12" font-weight="700">2</text>

              <rect x="358" y="242" width="90" height="38" rx="6" fill="#334155"/>
              <text x="382" y="266" fill="#cbd5e1" font-size="13">Cancel</text>

              <!-- Right Panel: Microphone Settings -->
              <rect x="485" y="20" width="415" height="280" rx="10" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
              <text x="505" y="48" fill="#94a3b8" font-size="12">Settings  &rsaquo;  Privacy &amp; security  &rsaquo;  <tspan fill="#f8fafc" font-weight="700">Microphone</tspan></text>
              <line x1="485" y1="62" x2="900" y2="62" stroke="#334155" stroke-width="1"/>

              <!-- Toggle 1 -->
              <rect x="502" y="80" width="380" height="64" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1"/>
              <text x="518" y="108" fill="#f8fafc" font-size="13" font-weight="600">Microphone access</text>
              <text x="518" y="126" fill="#94a3b8" font-size="11">Let apps use your microphone</text>
              <rect x="814" y="98" width="48" height="24" rx="12" fill="#2563eb"/>
              <circle cx="850" cy="110" r="9" fill="#ffffff"/>
              <text x="784" y="115" fill="#93c5fd" font-size="12" font-weight="700">On</text>

              <!-- Toggle 2 highlighted -->
              <rect x="502" y="160" width="380" height="92" rx="8" fill="#0f172a" stroke="#22c55e" stroke-width="2"/>
              <text x="518" y="188" fill="#f8fafc" font-size="13" font-weight="700">Let desktop apps access your microphone</text>
              <text x="518" y="210" fill="#86efac" font-size="11.5" font-weight="600">&#10003; {executable_name} (Currently allowed for P2P Voice Chat)</text>
              <rect x="814" y="178" width="48" height="24" rx="12" fill="#16a34a"/>
              <circle cx="850" cy="190" r="9" fill="#ffffff"/>
              <text x="784" y="195" fill="#86efac" font-size="12" font-weight="700">On</text>
              <circle cx="872" cy="166" r="12" fill="#dc2626"/>
              <text x="868" y="171" fill="#ffffff" font-size="12" font-weight="700">3</text>
            </svg>
          </div>
        </div>

        <!-- STEP 5: Onboarding with Google Account (SSO) -->
        <div class="guide-step-card" id="win-step-5">
          <div class="guide-step-header">
            <span class="guide-step-num">5</span>
            <div>
              <span class="badge badge-indigo" style="margin-bottom: 0.35rem;">Google OAuth 2.0 SSO &bull; Cross-Device Profile &amp; Elo Sync</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 5: Sign In &amp; Onboard with Your Google Account</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                Sign in with your Google Account to play rated online matches, join live voice/chat tables, and synchronize your player handle, avatar, Elo ratings, and game archives across Windows Desktop, Android, and Web (<code>{arena_origin_esc}</code>).
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Open &ldquo;Sign In to OCTI&rdquo; &amp; Click &ldquo;Continue with Google&rdquo;:</strong> In the top toolbar or Online Lobby of the desktop app, click <strong>Sign In</strong> (or <strong>Account</strong>). In the dialog that opens, click <strong>Continue with Google</strong>.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Select Your Google Account in the Browser:</strong> The desktop app starts a secure localhost loopback listener (<code>http://127.0.0.1:&lt;port&gt;/auth/callback</code>) and opens Google&rsquo;s official sign-in page (<code>accounts.google.com</code>) in your default web browser. Click your Google account to authorize.</li>
            <li><span class="guide-callout-badge">3</span> <strong>Choose Your Player Name (First-Time Onboarding):</strong> Your browser automatically hands the verified OIDC token back to the desktop app. On your first sign-in, the dialog transitions to <strong>&ldquo;Welcome to OCTI! Choose Your Player Name&rdquo;</strong>. Type your desired player handle (<code>3&ndash;24</code> characters, e.g., <code>GrandmasterA</code>).</li>
            <li><span class="guide-callout-badge">4</span> <strong>Click &ldquo;Continue&rdquo; to Complete Onboarding:</strong> Click <strong>Continue</strong>. Your Google avatar, player handle, and <code>1500</code> starting Elo ratings (<code>2P &bull; 4P &bull; OFK</code>) are immediately active!</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 5 &bull; Google Account SSO Sign-In &amp; First-Time Player Name Onboarding</span>
              <span>OAuth 2.0 Loopback Handoff &rarr; {arena_host_esc}</span>
            </div>
            <svg viewBox="0 0 920 350" width="100%" style="display: block; background: #0f172a; font-family: 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Three-step screenshot of OCTI Desktop Sign In with Google dialog, Google OAuth account chooser, and Welcome to OCTI Choose Your Player Name onboarding">
              <!-- Panel 1: Sign In to OCTI Dialog -->
              <rect x="16" y="20" width="284" height="310" rx="10" fill="#1c1917" stroke="#b45309" stroke-width="1.5"/>
              <rect x="16" y="20" width="284" height="32" rx="10" fill="#292524"/>
              <text x="32" y="41" fill="#fbbf24" font-size="12" font-weight="700">1. Desktop Dialog &bull; Sign In to OCTI</text>

              <text x="32" y="76" fill="#fef3c7" font-size="16" font-weight="700">Sign In to OCTI</text>
              <text x="32" y="98" fill="#d6d3d1" font-size="11">Sign in with your Google account to play</text>
              <text x="32" y="114" fill="#d6d3d1" font-size="11">online, chat, and track your rating.</text>

              <rect x="28" y="132" width="260" height="92" rx="8" fill="#292524" stroke="#44403c" stroke-width="1"/>
              <text x="40" y="152" fill="#a8a29e" font-size="11" font-weight="600">Choose Sign-In Method</text>

              <!-- Continue with Google button highlighted -->
              <rect x="40" y="164" width="236" height="44" rx="6" fill="#d97706" stroke="#fde047" stroke-width="2.5"/>
              <circle cx="64" cy="186" r="11" fill="#ffffff"/>
              <text x="59" y="191" fill="#2563eb" font-size="13" font-weight="800">G</text>
              <text x="86" y="191" fill="#1c1917" font-size="13.5" font-weight="800">Continue with Google</text>
              <circle cx="272" cy="164" r="12" fill="#dc2626"/>
              <text x="268" y="169" fill="#ffffff" font-size="12" font-weight="700">1</text>

              <text x="32" y="252" fill="#93c5fd" font-size="11">Completing sign-in with Google in</text>
              <text x="32" y="268" fill="#93c5fd" font-size="11">your browser... (127.0.0.1 loopback)</text>

              <!-- Panel 2: Browser Google Account Picker -->
              <rect x="318" y="20" width="284" height="310" rx="10" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5"/>
              <rect x="318" y="20" width="284" height="32" rx="10" fill="#f1f5f9"/>
              <text x="334" y="41" fill="#334155" font-size="11.5" font-weight="700">2. Browser &bull; accounts.google.com</text>

              <text x="340" y="78" fill="#202124" font-size="16" font-weight="700">Choose an account</text>
              <text x="340" y="98" fill="#5f6368" font-size="12">to continue to <tspan fill="#1a73e8" font-weight="700">{arena_host_esc}</tspan></text>

              <!-- Selected Google account card -->
              <rect x="332" y="118" width="256" height="64" rx="8" fill="#eff6ff" stroke="#2563eb" stroke-width="2.5"/>
              <circle cx="360" cy="150" r="18" fill="#2563eb"/>
              <text x="354" y="156" fill="#ffffff" font-size="15" font-weight="700">A</text>
              <text x="388" y="145" fill="#1e293b" font-size="13" font-weight="700">Alex Player</text>
              <text x="388" y="164" fill="#64748b" font-size="11.5">alex.player@gmail.com</text>
              <circle cx="582" cy="122" r="12" fill="#dc2626"/>
              <text x="578" y="127" fill="#ffffff" font-size="12" font-weight="700">2</text>

              <!-- Loopback confirmation banner -->
              <rect x="332" y="204" width="256" height="84" rx="8" fill="#f0fdf4" stroke="#86efac" stroke-width="1.5"/>
              <text x="346" y="228" fill="#166534" font-size="12" font-weight="700">&#10003; Google OAuth Verified</text>
              <text x="346" y="248" fill="#15803d" font-size="11">Redirecting token automatically to</text>
              <text x="346" y="264" fill="#15803d" font-size="11" font-family="monospace">http://127.0.0.1/auth/callback</text>

              <!-- Panel 3: Welcome to OCTI Onboarding & Profile -->
              <rect x="620" y="20" width="284" height="310" rx="10" fill="#1c1917" stroke="#b45309" stroke-width="1.5"/>
              <rect x="620" y="20" width="284" height="32" rx="10" fill="#292524"/>
              <text x="636" y="41" fill="#86efac" font-size="12" font-weight="700">3. Choose Handle &amp; Synced Profile</text>

              <text x="636" y="74" fill="#fef3c7" font-size="14.5" font-weight="700">Welcome to OCTI!</text>
              <text x="636" y="92" fill="#d6d3d1" font-size="11.5">Choose Your Player Name:</text>

              <!-- Handle input box -->
              <rect x="636" y="104" width="252" height="38" rx="6" fill="#0c0a09" stroke="#f59e0b" stroke-width="2"/>
              <text x="648" y="128" fill="#fef3c7" font-size="13" font-family="monospace" font-weight="600">GrandmasterA</text>
              <circle cx="884" cy="104" r="12" fill="#dc2626"/>
              <text x="880" y="109" fill="#ffffff" font-size="12" font-weight="700">3</text>

              <!-- Continue button -->
              <rect x="636" y="152" width="252" height="38" rx="6" fill="#16a34a" stroke="#fde047" stroke-width="2"/>
              <text x="730" y="176" fill="#ffffff" font-size="13.5" font-weight="700">Continue</text>
              <circle cx="884" cy="152" r="12" fill="#dc2626"/>
              <text x="880" y="157" fill="#ffffff" font-size="12" font-weight="700">4</text>

              <!-- Connected Profile Summary -->
              <rect x="636" y="206" width="252" height="106" rx="8" fill="#292524" stroke="#44403c" stroke-width="1"/>
              <text x="648" y="228" fill="#86efac" font-size="11.5" font-weight="700">&#10003; Google &bull; Connected (SSO)</text>
              <text x="648" y="248" fill="#fef3c7" font-size="12" font-weight="600">Player: GrandmasterA</text>
              <text x="648" y="268" fill="#fbbf24" font-size="11" font-family="monospace">Rating &mdash; 2P: 1500 &bull; 4P: 1500</text>
              <text x="648" y="286" fill="#a8a29e" font-size="10.5">Synced across Windows, Android &amp; Web</text>
            </svg>
          </div>
        </div>
      </section>
"""


def render_portal_html(catalog: Dict[str, Any], base_url: str) -> str:
    """Render the master portal index.html for all Windows desktop applications."""
    ctx = parse_portal_context(base_url)
    base_url_slash_esc = html.escape(ctx["base_url_slash"])
    cards_list = []
    apps = catalog.get("apps", {})

    # Display in preferred order
    preferred_order = ["octi", "aimon", "robohero-teleop", "robohero-motion", "vidaicut"]
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
    portal_install_guide_html = render_windows_install_guide_html(base_url=base_url)

    if ctx["is_selfso_portal"]:
        meta_desc = "SELFSO.COM Windows Desktop Software Distribution Portal — Independent 64-bit Windows Qt6 desktop applications and local hardware bridges with zero-dependency C++17 self-update."
        portal_heading = "Selfso Windows Desktop Applications"
        back_href = "/projects/"
        back_label = "&larr; Back to Projects"
    else:
        meta_desc = f"{ctx['site_host']} Windows Desktop Software Distribution Portal — Native 64-bit Windows Qt6 installers with zero-dependency C++17 self-update."
        portal_heading = "OCTI Windows Desktop Portal"
        back_href = "/"
        back_label = "&larr; Back to OCTI Arena"

    head_and_header, footer_and_script = _render_site_chrome(
        ctx, "Windows Software &amp; Self-Update Distribution", meta_desc
    )

    return f"""{head_and_header}

  <main class="site-wrapper">
    <div class="container" style="padding-top: 3.5rem; padding-bottom: 4rem;">
      <div style="margin-bottom: 2.5rem;">
        <a href="{back_href}" style="color: var(--text-muted); font-size: 0.9rem; text-decoration: none;">{back_label}</a>
        <div style="margin-top: 0.75rem;">
          <span class="badge" style="margin-bottom: 0.75rem;">Native Windows Desktop Portal</span>
          <h1 style="font-size: 2.35rem; margin-bottom: 0.75rem;">{portal_heading}</h1>
        </div>
        <p style="color: var(--text-secondary); max-width: 760px; font-size: 1.05rem; line-height: 1.6;">
          Independent, native 64-bit Windows Qt6 desktop applications, robotics control studios, and local EDA/CAD hardware automation bridges. Distributed directly with zero-dependency C++17 cryptographic self-update support.
        </p>

        <!-- Cross-link banner to Android portal & Install Guide -->
        <div style="margin-top: 1.25rem; display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem;">
          <div style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.85rem; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 0.88rem;">
            <span style="color: var(--accent); font-weight: 600;">Android Portal:</span>
            <span>Looking for Android mobile companion tools?</span>
            <a href="/software/android/" style="color: var(--accent); text-decoration: underline; margin-left: 0.25rem;">Visit the Android OTA Portal &rarr;</a>
          </div>
          <a href="#windows-install-guide" class="btn btn-outline" style="padding: 0.48rem 0.95rem; font-size: 0.86rem; border-color: #d97706; color: #b45309; background: #fffbeb;">
            &#9888; Windows 11 SmartScreen &amp; Google Sign-In Guide &darr;
          </a>
        </div>
      </div>

      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));">
{cards_joined}
      </div>

{portal_install_guide_html}

      <!-- Self-Update Architecture & Verification Section -->
      <div style="margin-top: 3.5rem; border-top: 1px solid var(--border-subtle); padding-top: 2.5rem;">
        <span class="badge" style="margin-bottom: 0.75rem;">Distribution &amp; Security Architecture</span>
        <h2 style="font-size: 1.75rem; margin-bottom: 0.75rem;">Zero-Dependency C++17 Self-Update Architecture (<code>namespace selfupdate</code>)</h2>
        <p style="color: var(--text-secondary); max-width: 760px; margin-bottom: 1.5rem; line-height: 1.6;">
          Windows applications on this portal embed the reusable, zero-dependency C++17 <code>selfupdate</code> engine. On launch or manual user trigger, applications poll <code>{base_url_slash_esc}version.json</code>, verify cryptographic RFC 6234 SHA-256 digests against streaming downloads, and execute either detached setup installers with PID-wait trampoline handoff or atomic <code>.old</code> in-place binary replacements with automatic rollback.
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
              <span>curl -s {base_url_slash_esc}version.json</span>
            </div>
            <div style="color: #a1a1aa; margin-bottom: 0.85rem; font-size: 0.8rem;">
              &#123; "schemaVersion": 1, "baseUrl": "{base_url_slash_esc}", "apps": &#123; ... &#125; &#125;
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

{footer_and_script}"""


def render_app_html(
    app_manifest: Dict[str, Any], app_meta: Dict[str, Any], base_url: str
) -> str:
    """Render a dedicated detail page index.html for a single Windows application."""
    ctx = parse_portal_context(base_url)
    clean_base_esc = html.escape(ctx["clean_base"])
    slug = html.escape(app_manifest.get("slug", ""))
    title = html.escape(app_manifest.get("title") or app_meta.get("title") or slug.capitalize())
    category = html.escape(app_manifest.get("category") or app_meta.get("category") or "Windows Desktop")
    raw_tagline = app_manifest.get("tagline") or app_meta.get("tagline") or app_manifest.get("releaseNotes", "")
    tagline = html.escape(raw_tagline)
    description = html.escape(app_manifest.get("description") or app_meta.get("description") or raw_tagline)
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
    if not ctx["is_selfso_portal"] and project_url == "/projects/octi/":
        project_url = "/"

    project_btn_html = ""
    if project_url:
        btn_label = "OCTI Online Arena" if (not ctx["is_selfso_portal"] and project_url == "/") else "Project Documentation"
        project_btn_html = f'<a href="{html.escape(project_url)}" class="btn btn-outline">{btn_label}</a>'

    head_and_header, footer_and_script = _render_site_chrome(
        ctx, f"{title} &bull; Windows Distribution", raw_tagline
    )

    return f"""{head_and_header}

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
          <a href="#windows-install-guide" class="btn btn-outline" style="border-color: #d97706; color: #b45309; background: #fffbeb;">
            &#9888; Windows 11 Install &amp; Google Sign-In Guide &darr;
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

{render_windows_install_guide_html(pkg_filename=pkg_filename, app_title=title, executable_name=executable_name, app_id=app_id, sha256_hint=sha256, base_url=base_url)}

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
          <div style="color: #34d399; margin-bottom: 0.75rem; font-size: 0.8rem;">
            {pkg_filename}: OK
          </div>
          <div class="terminal-line">
            <span class="terminal-prompt">$</span>
            <span>curl -s {clean_base_esc}/{slug}/version.json</span>
          </div>
        </div>
      </div>
    </div>
  </main>

{footer_and_script}"""


def publish_app(
    slug: str,
    package_path: Union[str, Path],
    web_root: Union[str, Path],
    workspace_root: Optional[Union[str, Path]] = None,
    base_url: str = "https://www.selfso.com/software/windows/",
    release_notes: Optional[str] = None,
    published_at: Optional[str] = None,
    force_public: bool = False,
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

    # Generate single-app manifest for the newly provided package first
    new_manifest = generate_manifest(
        package_path=src_pkg,
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
        new_manifest["category"] = app_meta["category"]
    if app_meta.get("tagline"):
        new_manifest["tagline"] = app_meta["tagline"]
    if app_meta.get("description"):
        new_manifest["description"] = app_meta["description"]
    if app_meta.get("projectUrl"):
        new_manifest["projectUrl"] = app_meta["projectUrl"]
    new_manifest["packageFilename"] = target_filename

    # Check if per-app version.json and staged_pkg already exist on disk
    per_app_json_path = app_dir / "version.json"
    existing_app_manifest = None
    if per_app_json_path.is_file():
        try:
            with open(per_app_json_path, "r", encoding="utf-8") as f:
                existing_app_manifest = json.load(f)
        except Exception:
            existing_app_manifest = None

    is_same_version = (
        (not force_public)
        and existing_app_manifest is not None
        and staged_pkg.is_file()
        and int(existing_app_manifest.get("versionCode", -1)) == int(new_manifest.get("versionCode", -2))
        and str(existing_app_manifest.get("versionName", "")) == str(new_manifest.get("versionName", ""))
    )

    # Compute latest_filename
    if target_filename.lower().endswith(".exe"):
        latest_filename = target_filename[:-4] + "-latest.exe"
    elif target_filename.lower().endswith(".zip"):
        latest_filename = target_filename[:-4] + "-latest.zip"
    else:
        stem = Path(target_filename).stem
        suffix = Path(target_filename).suffix
        latest_filename = f"{stem}-latest{suffix}"

    latest_pkg = app_dir / latest_filename
    if not dry_run:
        app_dir.mkdir(parents=True, exist_ok=True)
        if src_pkg.resolve() != latest_pkg.resolve():
            shutil.copy2(src_pkg, latest_pkg)

    sha8 = new_manifest["sha256"][:8]
    latest_entry: Dict[str, Any] = {
        "packageFilename": latest_filename,
        "packageUrl": f"{clean_base}/{slug}/{latest_filename}?sha={sha8}",
        "sha256": new_manifest["sha256"],
        "sizeBytes": new_manifest["sizeBytes"],
        "publishedAt": new_manifest["publishedAt"],
    }
    if release_notes:
        latest_entry["releaseNotes"] = release_notes

    if is_same_version:
        # Keep public binary untouched. Retain all top-level public fields from existing_app_manifest
        manifest = dict(existing_app_manifest)
        manifest["latest"] = latest_entry
    else:
        if not dry_run:
            if src_pkg.resolve() != staged_pkg.resolve():
                shutil.copy2(src_pkg, staged_pkg)
        manifest = new_manifest
        manifest["latest"] = latest_entry

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


def publish_all(
    web_root: Union[str, Path],
    workspace_root: Optional[Union[str, Path]] = None,
    base_url: str = "https://www.selfso.com/software/windows/",
    release_notes: Optional[str] = None,
    published_at: Optional[str] = None,
    force_public: bool = False,
    dry_run: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Batch-publish all known Windows applications with existing built binaries, skipping apps hosted on standalone portals (e.g. octi on octi.selfso.com)."""
    ws_root = Path(workspace_root).resolve() if workspace_root else (Path.home() / "work")
    w_root = Path(web_root).resolve()
    ctx = parse_portal_context(base_url)
    published: Dict[str, Dict[str, Any]] = {}

    for slug, meta in KNOWN_WINDOWS_APPS.items():
        if slug == "octi" and ctx["is_selfso_portal"]:
            print(f"  [-] {slug:18s}: Hosted standalone on octi.selfso.com; skipping www portal.")
            continue
        cand = find_candidate_package(slug, ws_root)
        if not cand:
            print(f"  [-] {slug:18s}: No candidate package found under workspace; skipping.")
            continue
        print(f"  [+] Publishing {slug:16s} from: {cand}")
        manifest = publish_app(
            slug=slug,
            package_path=cand,
            web_root=w_root,
            workspace_root=ws_root,
            base_url=base_url,
            release_notes=release_notes,
            published_at=published_at,
            force_public=force_public,
            dry_run=dry_run,
        )
        published[slug] = manifest

    return published


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
        default=None,
        help="Root path of the static web portal hierarchy (defaults to octi/web/html/software/windows for --slug octi, else www/selfso/html/software/windows).",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(Path.home() / "work"),
        help="Workspace root path containing personal project repositories.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base public URL for static package distribution (defaults to https://octi.selfso.com/software/windows/ for --slug octi, else https://www.selfso.com/software/windows/).",
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
        "--force-public",
        action="store_true",
        help="Force overwriting the public release binary even if the version is unchanged.",
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
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Re-render portal and per-app HTML pages from existing version.json manifests without modifying binaries.",
    )
    return parser


def re_render_existing_portal(web_root: Path, base_url: str) -> int:
    """Re-render master portal index.html and all local per-app index.html files from existing version.json manifests."""
    master_json_path = web_root / "version.json"
    if not master_json_path.is_file():
        sys.stderr.write(f"Error: Master catalog not found at {master_json_path}\n")
        return 1
    with open(master_json_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    rendered_apps = 0
    for key, app_manifest in catalog.get("apps", {}).items():
        if not isinstance(app_manifest, dict):
            continue
        slug = app_manifest.get("slug") or key
        app_dir = web_root / slug
        per_app_json = app_dir / "version.json"
        if per_app_json.is_file():
            with open(per_app_json, "r", encoding="utf-8") as f:
                app_manifest = json.load(f)
        app_meta = KNOWN_WINDOWS_APPS.get(slug, {})
        app_dir.mkdir(parents=True, exist_ok=True)
        app_html = render_app_html(app_manifest, app_meta, base_url)
        with open(app_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(app_html)
        rendered_apps += 1

    portal_html = render_portal_html(catalog, base_url)
    with open(web_root / "index.html", "w", encoding="utf-8") as f:
        f.write(portal_html)
    print(f"Re-rendered Windows portal index.html and {rendered_apps} per-app HTML page(s) in {web_root}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    ws_root = Path(args.workspace_root).resolve()

    if args.render_only:
        web_root, base_url = resolve_cli_target_defaults(
            args.slug, args.web_root, args.base_url, ws_root
        )
        return re_render_existing_portal(web_root, base_url)

    if args.publish_all:
        web_root, base_url = resolve_cli_target_defaults(
            None, args.web_root, args.base_url, ws_root
        )
        print(f"Batch publishing all known Windows applications to: {web_root}")
        published = publish_all(
            web_root=web_root,
            workspace_root=ws_root,
            base_url=base_url,
            release_notes=args.release_notes,
            published_at=args.published_at,
            force_public=args.force_public,
            dry_run=args.dry_run,
        )
        print(
            f"\nBatch publish complete: {len(published)} published, "
            f"{len(KNOWN_WINDOWS_APPS) - len(published)} skipped."
        )
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

    web_root, base_url = resolve_cli_target_defaults(
        slug, args.web_root, args.base_url, ws_root
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
            base_url=base_url,
            release_notes=args.release_notes,
            published_at=args.published_at,
            force_public=args.force_public,
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
