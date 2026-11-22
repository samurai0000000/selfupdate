#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import argparse
import copy
import datetime
import html
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import urllib.parse

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
        "tagline": "AI quota monitor, telemetry dashboard & mobile agent chat companion.",
        "description": "Mobile companion application for the AIMon daemon, providing real-time AI coding assistant quota tracking, usage insights, hardware bridge status, and remote agent chat.",
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


def parse_portal_context(base_url: str) -> Dict[str, Any]:
    """Derive host, origin, path, and portal-mode flags from base_url."""
    clean_base = (base_url or "https://www.selfso.com/software/android/").strip().rstrip("/")
    parsed = urllib.parse.urlparse(clean_base)
    scheme = parsed.scheme or "https"
    host = parsed.netloc or "www.selfso.com"
    origin = f"{scheme}://{host}"
    path_slash = (parsed.path.rstrip("/") + "/") if parsed.path else "/software/android/"
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


def is_external_catalog_entry(app_manifest: Dict[str, Any], portal_base_url: str) -> bool:
    """Return True if an entry in version.json points to a different host than portal_base_url."""
    portal_host = (urllib.parse.urlparse(portal_base_url or "").netloc or "").lower()
    entry_url = str(
        app_manifest.get("apkUrl")
        or app_manifest.get("packageUrl")
        or app_manifest.get("pageUrl")
        or ""
    )
    entry_host = (urllib.parse.urlparse(entry_url).netloc or "").lower()
    return bool(entry_host and portal_host and entry_host != portal_host)


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
            else (ws / "octi/web/html/software/android")
        )
        if base_url_arg:
            b_url = base_url_arg
        elif web_root_arg and "www/selfso" in Path(web_root_arg).as_posix():
            b_url = "https://www.selfso.com/software/android/"
        else:
            b_url = "https://octi.selfso.com/software/android/"
    else:
        w_root = (
            Path(web_root_arg).resolve()
            if web_root_arg
            else (ws / "www/selfso/html/software/android")
        )
        b_url = base_url_arg or "https://www.selfso.com/software/android/"
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
          <li><a href="/software/android/" class="nav-link active">Android</a></li>
          <li><a href="/software/windows/" class="nav-link">Windows</a></li>
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
            <li><a href="/software/android/">Android Software</a></li>
            <li><a href="/software/windows/">Windows Software</a></li>
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


def render_android_install_guide_html(
    apk_filename: str = "octi.apk",
    app_title: str = "OCTI Strategy Game",
    app_id: str = "com.selfso.octi",
    sha256_hint: str = "088b054e74bac4ca96bcd2417865d9066f85e6456d125b3cd4c9449ff1203c24",
    base_url: str = "https://www.selfso.com/software/android/",
) -> str:
    """Render the comprehensive Android sideloading, Settings permissions, Play Protect, and Google SSO onboarding guide."""
    ctx = parse_portal_context(base_url)
    site_host_esc = html.escape(ctx["site_host"])
    host_path_esc = html.escape(ctx["host_path"])
    base_url_slash_esc = html.escape(ctx["base_url_slash"])
    arena_host_esc = html.escape(ctx["arena_host"])
    arena_origin_esc = html.escape(ctx["arena_origin"])
    sha_short = (sha256_hint[:16] + "...") if len(sha256_hint) > 16 else (sha256_hint or "<sha256>")
    return f"""
      <!-- Comprehensive Android Sideloading, Settings Permissions & Google Onboarding Guide -->
      <section id="android-install-guide" style="margin-top: 3rem; border-top: 1px solid var(--border-subtle); padding-top: 2.75rem;">
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
        <h2 style="font-size: 2rem; margin-bottom: 0.75rem;">How to Install on Android (Direct APK) &amp; Onboard with Google</h2>
        <p style="color: var(--text-secondary); max-width: 820px; font-size: 1.05rem; line-height: 1.7; margin-bottom: 1.5rem;">
          Because first-party Android applications here are distributed directly from <code>{site_host_esc}</code> via our independent Over-The-Air (OTA) portal rather than hosted on the commercial <strong>Google Play Store</strong>, Android requires you to grant <strong>Install unknown apps</strong> permission and confirm <strong>Google Play Protect</strong> on your first install. Follow this step-by-step visual guide with screenshots to install the app and sign in with your <strong>Google Account</strong>.
        </p>

        <!-- Why Android Warns You (The Facts) -->
        <div class="guide-alert-box" id="android-why-warnings">
          <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.65rem;">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#b45309" stroke-width="2.2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
            <h3 style="font-size: 1.2rem; color: #92400e; margin: 0;">Why Does Android Warn You About Installing <code>{apk_filename}</code>?</h3>
          </div>
          <p style="color: #78350f; font-size: 0.96rem; line-height: 1.65; margin-bottom: 0.85rem;">
            <strong>1. Direct Independent OTA Distribution (Not on Google Play Store):</strong> Applications on this portal are distributed directly from <code>{host_path_esc}</code> so releases and updates reach your device immediately without app-store gatekeeping or telemetry trackers. By default, Android blocks web browsers (such as Chrome) from installing <code>.apk</code> packages outside the Play Store until you toggle <strong>Allow from this source</strong> in Android Settings.
          </p>
          <p style="color: #78350f; font-size: 0.96rem; line-height: 1.65; margin-bottom: 0;">
            <strong>2. Cryptographic Signing &amp; One-Time Setup:</strong> Every release APK (<code>{app_id}</code>) is cryptographically signed with the official release key and published alongside its <strong>SHA-256 digest</strong> (<code>{sha_short}</code>) in <code>version.json</code>. Once you complete this initial install, all future updates are verified and installed directly inside the app via <code>com.selfso.selfupdate</code>!
          </p>
        </div>

        <!-- Quick Jump Navigation -->
        <div class="guide-nav-pills" aria-label="Android Installation Guide Steps">
          <a href="#and-step-1" class="guide-nav-pill"><span>1</span> Chrome APK Download</a>
          <a href="#and-step-2" class="guide-nav-pill"><span>2</span> Settings: Install Unknown Apps</a>
          <a href="#and-step-3" class="guide-nav-pill"><span>3</span> Google Play Protect</a>
          <a href="#and-step-4" class="guide-nav-pill"><span>4</span> Samsung Auto Blocker &amp; Permissions</a>
          <a href="#and-step-5" class="guide-nav-pill"><span>5</span> Google Account Onboarding</a>
        </div>

        <!-- STEP 1: Download the APK in Chrome / Browser -->
        <div class="guide-step-card" id="and-step-1">
          <div class="guide-step-header">
            <span class="guide-step-num">1</span>
            <div>
              <span class="badge" style="margin-bottom: 0.35rem;">Chrome for Android &bull; Mobile Browser</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 1: Download <code>{apk_filename}</code> &amp; Tap &ldquo;Open&rdquo;</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                When you tap the <strong>Download APK</strong> button on your phone, Google Chrome displays a standard warning dialog because <code>.apk</code> files are installable application packages.
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Tap &ldquo;Download anyway&rdquo;:</strong> When Chrome shows <em>&ldquo;File might be harmful &mdash; Do you want to download {apk_filename} anyway?&rdquo;</em> at the bottom of your screen, tap <strong>Download anyway</strong>.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Tap &ldquo;Open&rdquo; When Completed:</strong> Once the download finishes, tap <strong>Open</strong> on the Chrome notification bar (or open Chrome&rsquo;s <code>&#8942; &rarr; Downloads</code> menu / your phone&rsquo;s <strong>Files</strong> app and tap <code>{apk_filename}</code>).</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 1 &bull; Android Chrome APK Download Prompt &amp; Open Notification</span>
              <span>Package: {apk_filename}</span>
            </div>
            <svg viewBox="0 0 920 350" width="100%" style="display: block; background: #0f172a; font-family: Roboto, 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Phone screenshots showing Chrome File might be harmful Download anyway prompt and File downloaded Open toast">
              <!-- Phone 1A: File might be harmful -->
              <rect x="65" y="18" width="350" height="314" rx="22" fill="#1e293b" stroke="#475569" stroke-width="2.5"/>
              <rect x="195" y="28" width="90" height="6" rx="3" fill="#475569"/>
              <text x="90" y="54" fill="#94a3b8" font-size="11" font-weight="600">SCREEN 1A &bull; Chrome Download Warning</text>

              <!-- Browser address bar -->
              <rect x="85" y="66" width="310" height="28" rx="14" fill="#0f172a"/>
              <text x="104" y="84" fill="#cbd5e1" font-size="11" font-family="monospace">{base_url_slash_esc}</text>

              <!-- Bottom sheet modal -->
              <rect x="77" y="138" width="326" height="182" rx="16" fill="#0f172a" stroke="#64748b" stroke-width="1.5"/>
              <circle cx="110" cy="172" r="14" fill="#ef4444" fill-opacity="0.2" stroke="#ef4444" stroke-width="2"/>
              <text x="106" y="177" fill="#f87171" font-size="15" font-weight="800">!</text>
              <text x="134" y="170" fill="#f8fafc" font-size="14" font-weight="700">File might be harmful</text>
              <text x="96" y="198" fill="#cbd5e1" font-size="12">Do you want to download <tspan fill="#93c5fd" font-family="monospace" font-weight="600">{apk_filename}</tspan></text>
              <text x="96" y="216" fill="#cbd5e1" font-size="12">anyway?</text>

              <rect x="96" y="262" width="110" height="38" rx="19" fill="#1e293b" stroke="#475569" stroke-width="1"/>
              <text x="130" y="286" fill="#93c5fd" font-size="12.5" font-weight="600">Cancel</text>

              <!-- Download anyway button highlighted -->
              <rect x="218" y="260" width="166" height="42" rx="21" fill="#2563eb" stroke="#fde047" stroke-width="3"/>
              <text x="242" y="286" fill="#ffffff" font-size="13" font-weight="700">Download anyway</text>
              <circle cx="384" cy="258" r="13" fill="#dc2626"/>
              <text x="380" y="263" fill="#ffffff" font-size="12.5" font-weight="700">1</text>

              <!-- Arrow between phones -->
              <path d="M 435 175 L 485 175" stroke="#fde047" stroke-width="3" stroke-linecap="round"/>
              <polygon points="483,169 493,175 483,181" fill="#fde047"/>

              <!-- Phone 1B: Download complete -> Open -->
              <rect x="505" y="18" width="350" height="314" rx="22" fill="#1e293b" stroke="#475569" stroke-width="2.5"/>
              <rect x="635" y="28" width="90" height="6" rx="3" fill="#475569"/>
              <text x="530" y="54" fill="#86efac" font-size="11" font-weight="600">SCREEN 1B &bull; Tap &ldquo;Open&rdquo; After Download</text>

              <!-- Top toast notification -->
              <rect x="522" y="74" width="316" height="72" rx="14" fill="#0f172a" stroke="#22c55e" stroke-width="2"/>
              <circle cx="550" cy="110" r="14" fill="#16a34a" fill-opacity="0.25"/>
              <text x="544" y="115" fill="#4ade80" font-size="15" font-weight="800">&#10003;</text>
              <text x="574" y="104" fill="#f8fafc" font-size="13" font-weight="700">File downloaded</text>
              <text x="574" y="124" fill="#94a3b8" font-size="11.5" font-family="monospace">{apk_filename}</text>

              <!-- Open button highlighted -->
              <rect x="752" y="90" width="72" height="38" rx="19" fill="#16a34a" stroke="#fde047" stroke-width="2.5"/>
              <text x="771" y="114" fill="#ffffff" font-size="13" font-weight="700">Open</text>
              <circle cx="826" cy="88" r="13" fill="#dc2626"/>
              <text x="822" y="93" fill="#ffffff" font-size="12.5" font-weight="700">2</text>

              <!-- Alternative Files/Downloads tip box -->
              <rect x="525" y="176" width="310" height="128" rx="12" fill="#0f172a" stroke="#334155" stroke-width="1"/>
              <text x="542" y="202" fill="#f8fafc" font-size="12.5" font-weight="700">Missed the &ldquo;Open&rdquo; popup?</text>
              <text x="542" y="226" fill="#cbd5e1" font-size="11.5">1. Tap the <tspan fill="#fde047" font-weight="700">&#8942;</tspan> menu at top-right of Chrome</text>
              <text x="542" y="248" fill="#cbd5e1" font-size="11.5">2. Tap <tspan fill="#93c5fd" font-weight="700">Downloads</tspan> (or open the <tspan fill="#93c5fd" font-weight="700">Files</tspan> app)</text>
              <text x="542" y="270" fill="#cbd5e1" font-size="11.5">3. Tap <tspan fill="#86efac" font-family="monospace" font-weight="700">{apk_filename}</tspan> to launch installer</text>
            </svg>
          </div>
        </div>

        <!-- STEP 2: Enable "Install Unknown Apps" in Android Settings -->
        <div class="guide-step-card" id="and-step-2">
          <div class="guide-step-header">
            <span class="guide-step-num">2</span>
            <div>
              <span class="badge badge-vermilion" style="margin-bottom: 0.35rem;">Required First-Time Android Permission</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 2: Enable &ldquo;Install Unknown Apps&rdquo; in Android Settings</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                When you open <code>{apk_filename}</code> for the first time, Android stops to ask permission for your browser (or Files app) to install apps outside the Google Play Store.
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Tap &ldquo;Settings&rdquo; in the Security Prompt:</strong> When Android displays <em>&ldquo;For your security, your phone currently isn&rsquo;t allowed to install unknown apps from this source&rdquo;</em>, tap <strong>Settings</strong>.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Toggle &ldquo;Allow from this source&rdquo; ON:</strong> In the <strong>Install unknown apps</strong> screen (also reachable via <em>Settings &rarr; Apps &rarr; Special app access &rarr; Install unknown apps &rarr; Chrome</em>), tap the switch next to <strong>Allow from this source</strong> so it turns <strong>ON</strong>.</li>
            <li><span class="guide-callout-badge">3</span> <strong>Tap Back (<code>&larr;</code>) &amp; Tap &ldquo;Install&rdquo;:</strong> Press the Android Back button once to return to the installer dialog and tap <strong>Install</strong>.</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 2 &bull; Android Settings &rarr; Install Unknown Apps &rarr; Allow From This Source</span>
              <span>Android 10 / 11 / 12 / 13 / 14 / 15</span>
            </div>
            <svg viewBox="0 0 920 360" width="100%" style="display: block; background: #0f172a; font-family: Roboto, 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Three Android phone screens showing Settings prompt, Allow from this source toggle in Install unknown apps, and Do you want to install this app Install button">
              <!-- Phone 2A: Prompt -> Tap Settings -->
              <rect x="18" y="20" width="276" height="320" rx="20" fill="#1e293b" stroke="#475569" stroke-width="2"/>
              <text x="36" y="48" fill="#94a3b8" font-size="11" font-weight="700">2A &bull; Unknown Apps Prompt</text>

              <rect x="32" y="88" width="248" height="190" rx="14" fill="#0f172a" stroke="#64748b" stroke-width="1.5"/>
              <text x="48" y="116" fill="#f8fafc" font-size="13.5" font-weight="700">Chrome</text>
              <text x="48" y="140" fill="#cbd5e1" font-size="11.5">For your security, your phone</text>
              <text x="48" y="158" fill="#cbd5e1" font-size="11.5">currently isn&apos;t allowed to install</text>
              <text x="48" y="176" fill="#cbd5e1" font-size="11.5">unknown apps from this source.</text>
              <text x="48" y="194" fill="#cbd5e1" font-size="11.5">You can change this in Settings.</text>

              <text x="122" y="250" fill="#94a3b8" font-size="12.5" font-weight="600">Cancel</text>
              <!-- Settings button highlighted -->
              <rect x="182" y="228" width="84" height="34" rx="17" fill="#2563eb" stroke="#fde047" stroke-width="2.5"/>
              <text x="199" y="250" fill="#ffffff" font-size="12.5" font-weight="700">Settings</text>
              <circle cx="266" cy="226" r="12" fill="#dc2626"/>
              <text x="262" y="231" fill="#ffffff" font-size="12" font-weight="700">1</text>

              <!-- Phone 2B: Settings -> Allow from this source -->
              <rect x="322" y="20" width="276" height="320" rx="20" fill="#1e293b" stroke="#475569" stroke-width="2"/>
              <text x="340" y="48" fill="#fde047" font-size="11" font-weight="700">2B &bull; Toggle Permission ON</text>

              <!-- Back arrow & header -->
              <rect x="336" y="62" width="248" height="36" rx="8" fill="#0f172a"/>
              <text x="350" y="85" fill="#93c5fd" font-size="15" font-weight="800">&larr;</text>
              <text x="376" y="85" fill="#f8fafc" font-size="13" font-weight="700">Install unknown apps</text>

              <!-- App icon & name -->
              <circle cx="460" cy="128" r="20" fill="#2563eb"/>
              <text x="453" y="134" fill="#ffffff" font-size="15" font-weight="700">C</text>
              <text x="434" y="164" fill="#f8fafc" font-size="13" font-weight="700">Chrome</text>

              <!-- Allow from this source toggle card -->
              <rect x="336" y="182" width="248" height="58" rx="10" fill="#0f172a" stroke="#22c55e" stroke-width="2.5"/>
              <text x="350" y="216" fill="#f8fafc" font-size="12.5" font-weight="700">Allow from this source</text>
              <rect x="520" y="199" width="48" height="24" rx="12" fill="#16a34a"/>
              <circle cx="556" cy="211" r="9" fill="#ffffff"/>
              <circle cx="574" cy="184" r="12" fill="#dc2626"/>
              <text x="570" y="189" fill="#ffffff" font-size="12" font-weight="700">2</text>

              <text x="344" y="268" fill="#94a3b8" font-size="11">After toggling ON, tap Back (&larr;)</text>
              <text x="344" y="286" fill="#94a3b8" font-size="11">to return to the installer dialog.</text>

              <!-- Phone 2C: Do you want to install this app? -> Install -->
              <rect x="626" y="20" width="276" height="320" rx="20" fill="#1e293b" stroke="#475569" stroke-width="2"/>
              <text x="644" y="48" fill="#86efac" font-size="11" font-weight="700">2C &bull; Tap &ldquo;Install&rdquo;</text>

              <rect x="640" y="88" width="248" height="190" rx="14" fill="#0f172a" stroke="#64748b" stroke-width="1.5"/>
              <text x="658" y="118" fill="#f8fafc" font-size="14" font-weight="700">{app_title}</text>
              <text x="658" y="144" fill="#cbd5e1" font-size="12">Do you want to install this</text>
              <text x="658" y="162" fill="#cbd5e1" font-size="12">application?</text>
              <text x="658" y="190" fill="#94a3b8" font-size="11" font-family="monospace">{app_id}</text>

              <text x="730" y="250" fill="#94a3b8" font-size="12.5" font-weight="600">Cancel</text>
              <rect x="792" y="228" width="82" height="34" rx="17" fill="#16a34a" stroke="#fde047" stroke-width="2.5"/>
              <text x="813" y="250" fill="#ffffff" font-size="12.5" font-weight="700">Install</text>
              <circle cx="876" cy="226" r="12" fill="#dc2626"/>
              <text x="872" y="231" fill="#ffffff" font-size="12" font-weight="700">3</text>
            </svg>
          </div>
        </div>

        <!-- STEP 3: Pass Google Play Protect ("More details" -> "Install anyway") -->
        <div class="guide-step-card" id="and-step-3">
          <div class="guide-step-header">
            <span class="guide-step-num">3</span>
            <div>
              <span class="badge badge-vermilion" style="margin-bottom: 0.35rem;">Most Important Step &bull; Google Play Protect</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 3: Pass Google Play Protect (&ldquo;More details&rdquo; &rarr; &ldquo;Install anyway&rdquo;)</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                During installation, <strong>Google Play Protect</strong> may display an <em>&ldquo;Unrecognized app&rdquo;</em> or <em>&ldquo;Blocked by Play Protect&rdquo;</em> dialog because the app is distributed directly from <code>{site_host_esc}</code> rather than the Play Store. <strong>Do NOT tap &ldquo;Don&rsquo;t install&rdquo; or &ldquo;OK&rdquo;</strong> &mdash; follow the two taps below:
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Tap &ldquo;More details &#8964;&rdquo;:</strong> Directly beneath the Play Protect warning paragraph, tap the <strong>More details &#8964;</strong> link to expand the hidden options.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Tap &ldquo;Install anyway&rdquo;:</strong> At the bottom of the expanded text, tap the underlined <strong>Install anyway</strong> link (if Play Protect asks to scan the app first, you may tap <em>Scan app</em> or <em>Install without scanning</em>).</li>
            <li><span class="guide-callout-badge">3</span> <strong>Tap &ldquo;Open&rdquo;:</strong> Once Android confirms <em>&ldquo;App installed&rdquo;</em>, tap <strong>Open</strong> to launch {app_title}!</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 3 &bull; Google Play Protect Modal (&ldquo;More details&rdquo; &rarr; &ldquo;Install anyway&rdquo;)</span>
              <span>Google Play Protect</span>
            </div>
            <svg viewBox="0 0 920 360" width="100%" style="display: block; background: #0f172a; font-family: Roboto, 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Before and after phone screenshots of Google Play Protect showing More details and Install anyway">
              <!-- Phone 3A: Initial Play Protect Dialog -->
              <rect x="65" y="18" width="350" height="324" rx="22" fill="#1e293b" stroke="#475569" stroke-width="2.5"/>
              <text x="90" y="48" fill="#fde047" font-size="11" font-weight="700">STATE A &bull; Initial Play Protect Prompt</text>

              <rect x="85" y="62" width="310" height="260" rx="16" fill="#0f172a" stroke="#f59e0b" stroke-width="1.5"/>
              <text x="108" y="92" fill="#fbbf24" font-size="12" font-weight="700">&#9888; Google Play Protect</text>
              <text x="108" y="118" fill="#f8fafc" font-size="14.5" font-weight="700">Play Protect doesn&apos;t recognize</text>
              <text x="108" y="138" fill="#f8fafc" font-size="14.5" font-weight="700">this app&apos;s developer</text>
              <text x="108" y="164" fill="#cbd5e1" font-size="11.5">Apps from unknown developers can sometimes</text>
              <text x="108" y="182" fill="#cbd5e1" font-size="11.5">be unsafe. Only install if you trust the source.</text>

              <!-- More details highlighted -->
              <rect x="104" y="198" width="126" height="32" rx="6" fill="#dc2626" fill-opacity="0.28" stroke="#fca5a5" stroke-width="2.5"/>
              <text x="114" y="219" fill="#93c5fd" font-size="12.5" font-weight="700">More details &#8964;</text>
              <circle cx="242" cy="214" r="13" fill="#dc2626"/>
              <text x="238" y="219" fill="#ffffff" font-size="12.5" font-weight="700">1</text>
              <text x="262" y="219" fill="#fde047" font-size="11.5" font-weight="700">&larr; Tap here!</text>

              <!-- Prominent Don't install button (do not tap) -->
              <rect x="108" y="264" width="264" height="38" rx="19" fill="#334155"/>
              <text x="182" y="288" fill="#cbd5e1" font-size="12.5">Don&apos;t install (Skip)</text>

              <!-- Arrow -->
              <path d="M 435 180 L 485 180" stroke="#fde047" stroke-width="3" stroke-linecap="round"/>
              <polygon points="483,174 493,180 483,186" fill="#fde047"/>

              <!-- Phone 3B: Expanded Play Protect Dialog -> Install anyway -->
              <rect x="505" y="18" width="350" height="324" rx="22" fill="#1e293b" stroke="#475569" stroke-width="2.5"/>
              <text x="530" y="48" fill="#86efac" font-size="11" font-weight="700">STATE B &bull; Tap &ldquo;Install anyway&rdquo;</text>

              <rect x="525" y="62" width="310" height="260" rx="16" fill="#0f172a" stroke="#22c55e" stroke-width="1.5"/>
              <text x="548" y="90" fill="#fbbf24" font-size="12" font-weight="700">&#9888; Google Play Protect (Expanded)</text>
              <text x="548" y="114" fill="#cbd5e1" font-size="11.5">Play Protect hasn&apos;t seen this app before</text>
              <text x="548" y="132" fill="#cbd5e1" font-size="11.5">because it was downloaded directly from</text>
              <text x="548" y="150" fill="#93c5fd" font-size="11.5" font-family="monospace">{site_host_esc}</text>

              <!-- Install anyway highlighted -->
              <rect x="544" y="170" width="154" height="38" rx="8" fill="#16a34a" fill-opacity="0.28" stroke="#22c55e" stroke-width="2.5"/>
              <text x="560" y="194" fill="#86efac" font-size="13.5" font-weight="700" text-decoration="underline">Install anyway</text>
              <circle cx="712" cy="189" r="13" fill="#dc2626"/>
              <text x="708" y="194" fill="#ffffff" font-size="12.5" font-weight="700">2</text>

              <!-- Installed -> Open banner -->
              <rect x="544" y="232" width="272" height="68" rx="10" fill="#1e293b" stroke="#475569" stroke-width="1"/>
              <text x="560" y="258" fill="#86efac" font-size="12.5" font-weight="700">&#10003; App installed</text>
              <text x="560" y="278" fill="#cbd5e1" font-size="11">{app_title}</text>
              <rect x="726" y="246" width="76" height="36" rx="18" fill="#2563eb" stroke="#fde047" stroke-width="2"/>
              <text x="747" y="269" fill="#ffffff" font-size="12.5" font-weight="700">Open</text>
              <circle cx="804" cy="244" r="12" fill="#dc2626"/>
              <text x="800" y="249" fill="#ffffff" font-size="12" font-weight="700">3</text>
            </svg>
          </div>
        </div>

        <!-- STEP 4: Samsung One UI Auto Blocker, Android 14+ Restricted Settings & App Permissions -->
        <div class="guide-step-card" id="and-step-4">
          <div class="guide-step-header">
            <span class="guide-step-num">4</span>
            <div>
              <span class="badge" style="margin-bottom: 0.35rem;">Samsung Galaxy One UI 6+ &bull; Android 14/15 Permissions</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 4: Samsung &ldquo;Auto Blocker&rdquo; Settings &amp; Microphone Permissions</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                Using a newer Samsung Galaxy phone or joining a live P2P voice chat table? Check these two Android Settings screens:
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Samsung Galaxy Users (One UI 6.0 / 6.1+ &ldquo;Auto Blocker&rdquo;):</strong> Newer Samsung phones turn on <em>Auto Blocker</em> by default, which blocks all non-Play-Store APKs with <em>&ldquo;Blocked by Auto Blocker&rdquo;</em>. Open <strong>Settings &rarr; Security and privacy &rarr; Auto Blocker</strong> and toggle <strong>Auto Blocker OFF</strong> while installing.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Android 13 / 14 / 15 &ldquo;Restricted Settings&rdquo; Unlock:</strong> If a special permission is grayed out with <em>&ldquo;Restricted setting&rdquo;</em>, open <strong>Settings &rarr; Apps &rarr; {app_title}</strong>, tap the top-right <strong><code>&#8942;</code> (3-dot menu)</strong>, and tap <strong>Allow restricted settings</strong>.</li>
            <li><span class="guide-callout-badge">3</span> <strong>Microphone Permission for Live P2P Voice Chat:</strong> When you unmute or join a voice-enabled match, Android asks <em>&ldquo;Allow {app_title} to record audio?&rdquo;</em> &mdash; tap <strong>While using the app</strong> (or enable it anytime in <em>Settings &rarr; Apps &rarr; {app_title} &rarr; Permissions &rarr; Microphone</em>).</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 4 &bull; Samsung Auto Blocker Setting &amp; Android Microphone Runtime Permission</span>
              <span>Settings &rarr; Security &amp; Privacy / Permissions</span>
            </div>
            <svg viewBox="0 0 920 330" width="100%" style="display: block; background: #0f172a; font-family: Roboto, 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Phone screenshots showing Samsung Settings Security and privacy Auto Blocker toggle Off and Android Microphone permission While using the app">
              <!-- Phone 4A: Samsung Auto Blocker & Restricted Settings -->
              <rect x="65" y="18" width="350" height="294" rx="22" fill="#1e293b" stroke="#475569" stroke-width="2.5"/>
              <text x="90" y="46" fill="#93c5fd" font-size="11" font-weight="700">4A &bull; Samsung Settings &rsaquo; Auto Blocker</text>

              <rect x="85" y="60" width="310" height="106" rx="12" fill="#0f172a" stroke="#ef4444" stroke-width="2"/>
              <text x="102" y="86" fill="#f8fafc" font-size="13" font-weight="700">Security and privacy &rsaquo; Auto Blocker</text>
              <text x="102" y="108" fill="#cbd5e1" font-size="11">Toggle OFF temporarily to allow installing</text>
              <text x="102" y="124" fill="#cbd5e1" font-size="11">direct APK packages outside Play Store.</text>
              <rect x="102" y="134" width="140" height="24" rx="12" fill="#334155"/>
              <text x="116" y="150" fill="#fde047" font-size="11.5" font-weight="700">Off (Allowed)</text>
              <circle cx="380" cy="64" r="12" fill="#dc2626"/>
              <text x="376" y="69" fill="#ffffff" font-size="12" font-weight="700">1</text>

              <!-- Android 14 Restricted Settings -->
              <rect x="85" y="180" width="310" height="112" rx="12" fill="#0f172a" stroke="#475569" stroke-width="1"/>
              <text x="102" y="206" fill="#f8fafc" font-size="12.5" font-weight="700">Settings &rsaquo; Apps &rsaquo; App info (Top-Right &#8942;)</text>
              <text x="102" y="228" fill="#cbd5e1" font-size="11">On Android 14/15, tap <tspan fill="#fde047" font-weight="700">&#8942;</tspan> at top-right of App Info</text>
              <rect x="102" y="242" width="210" height="34" rx="8" fill="#1e293b" stroke="#60a5fa" stroke-width="1.5"/>
              <text x="116" y="264" fill="#93c5fd" font-size="12" font-weight="700">&#10003; Allow restricted settings</text>
              <circle cx="380" cy="184" r="12" fill="#dc2626"/>
              <text x="376" y="189" fill="#ffffff" font-size="12" font-weight="700">2</text>

              <!-- Phone 4B: Microphone Runtime Permission -->
              <rect x="505" y="18" width="350" height="294" rx="22" fill="#1e293b" stroke="#475569" stroke-width="2.5"/>
              <text x="530" y="46" fill="#86efac" font-size="11" font-weight="700">4B &bull; Microphone Permission (Voice Chat)</text>

              <rect x="530" y="68" width="300" height="224" rx="16" fill="#0f172a" stroke="#64748b" stroke-width="1.5"/>
              <circle cx="680" cy="100" r="16" fill="#2563eb" fill-opacity="0.25"/>
              <text x="673" y="106" fill="#60a5fa" font-size="16" font-weight="700">&#127908;</text>
              <text x="562" y="134" fill="#f8fafc" font-size="13" font-weight="700">Allow {app_title}</text>
              <text x="615" y="152" fill="#f8fafc" font-size="13" font-weight="700">to record audio?</text>

              <!-- While using the app highlighted -->
              <rect x="550" y="170" width="260" height="38" rx="19" fill="#16a34a" stroke="#fde047" stroke-width="2.5"/>
              <text x="612" y="194" fill="#ffffff" font-size="12.5" font-weight="700">While using the app</text>
              <circle cx="814" cy="170" r="12" fill="#dc2626"/>
              <text x="810" y="175" fill="#ffffff" font-size="12" font-weight="700">3</text>

              <rect x="550" y="216" width="260" height="32" rx="16" fill="#1e293b"/>
              <text x="634" y="237" fill="#cbd5e1" font-size="12">Only this time</text>
              <text x="646" y="274" fill="#94a3b8" font-size="12">Don&apos;t allow</text>
            </svg>
          </div>
        </div>

        <!-- STEP 5: Onboarding with Google Account on Android (SSO) -->
        <div class="guide-step-card" id="and-step-5">
          <div class="guide-step-header">
            <span class="guide-step-num">5</span>
            <div>
              <span class="badge badge-indigo" style="margin-bottom: 0.35rem;">Google OAuth 2.0 SSO &bull; Instant Deep-Link Return</span>
              <h3 style="font-size: 1.4rem; margin-bottom: 0.25rem;">Step 5: Sign In &amp; Onboard with Your Google Account</h3>
              <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.96rem;">
                Sign in with your Google Account inside the Android app to play rated online matches, join live voice/text chat rooms, and synchronize your Elo ratings and game archives across Android, Windows Desktop, and Web (<code>{arena_origin_esc}</code>).
              </p>
            </div>
          </div>

          <ul class="guide-checklist">
            <li><span class="guide-callout-badge">1</span> <strong>Tap &ldquo;Sign In&rdquo; &rarr; &ldquo;Continue with Google&rdquo;:</strong> Launch the app and tap <strong>Sign In</strong> (or the <strong>Account</strong> button in the top bar / Online Lobby). In the <strong>&ldquo;Sign In to OCTI&rdquo;</strong> dialog, tap the gold/brass <strong>Continue with Google</strong> button.</li>
            <li><span class="guide-callout-badge">2</span> <strong>Tap Your Google Account:</strong> The app opens Google&rsquo;s official sign-in screen (<code>accounts.google.com</code>) in a secure Custom Tab / browser. Tap your Google account to continue.</li>
            <li><span class="guide-callout-badge">3</span> <strong>Automatic Deep-Link Return &amp; Enter Player Name:</strong> Android automatically returns to the app via <code>octi://auth/callback</code>. On your first sign-in, the <strong>&ldquo;Welcome to OCTI!&rdquo;</strong> onboarding dialog prompts <em>&ldquo;Choose the player name others will see:&rdquo;</em> &mdash; enter your desired <strong>Player Name</strong> (<code>3&ndash;24</code> characters).</li>
            <li><span class="guide-callout-badge">4</span> <strong>Tap &ldquo;Continue&rdquo; &amp; Play Online:</strong> Tap <strong>Continue</strong>. Your Google avatar, player name, and Elo ratings (<code>Rating &mdash; 2P: 1500 &bull; 4P: 1500 &bull; OFK: 1500</code>) are now active across all your devices!</li>
          </ul>

          <div class="guide-screenshot-frame">
            <div class="guide-screenshot-bar">
              <span>SCREENSHOT 5 &bull; Android In-App Google Sign-In, Deep-Link Return &amp; Player Name Onboarding</span>
              <span>octi://auth/callback &bull; Google SSO</span>
            </div>
            <svg viewBox="0 0 920 360" width="100%" style="display: block; background: #0f172a; font-family: Roboto, 'Segoe UI', Inter, sans-serif;" role="img" aria-label="Three Android phone screens showing Sign In to OCTI Continue with Google button, Google account selector, and Welcome to OCTI Player Name onboarding">
              <!-- Phone 5A: Sign In to OCTI Dialog -->
              <rect x="18" y="20" width="276" height="320" rx="20" fill="#1c1917" stroke="#b45309" stroke-width="2"/>
              <text x="36" y="48" fill="#fbbf24" font-size="11" font-weight="700">5A &bull; Tap &ldquo;Continue with Google&rdquo;</text>

              <rect x="32" y="68" width="248" height="248" rx="14" fill="#292524" stroke="#78350f" stroke-width="1.5"/>
              <text x="48" y="98" fill="#f59e0b" font-size="16" font-weight="700">Sign In to OCTI</text>
              <text x="48" y="122" fill="#d6d3d1" font-size="11.5">Sign in to play online, chat with</text>
              <text x="48" y="140" fill="#d6d3d1" font-size="11.5">players, and track your rating.</text>

              <!-- Brass Continue with Google button -->
              <rect x="46" y="164" width="220" height="46" rx="23" fill="#d97706" stroke="#fde047" stroke-width="3"/>
              <circle cx="72" cy="187" r="11" fill="#ffffff"/>
              <text x="67" y="192" fill="#2563eb" font-size="13" font-weight="800">G</text>
              <text x="92" y="192" fill="#1c1917" font-size="13" font-weight="800">Continue with Google</text>
              <circle cx="264" cy="162" r="12" fill="#dc2626"/>
              <text x="260" y="167" fill="#ffffff" font-size="12" font-weight="700">1</text>

              <rect x="192" y="266" width="72" height="32" rx="16" fill="#1c1917" stroke="#57534e" stroke-width="1"/>
              <text x="212" y="287" fill="#d6d3d1" font-size="12">Close</text>

              <!-- Phone 5B: Google Account Chooser -->
              <rect x="322" y="20" width="276" height="320" rx="20" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
              <text x="340" y="48" fill="#1e293b" font-size="11" font-weight="700">5B &bull; Select Google Account</text>

              <text x="344" y="80" fill="#202124" font-size="15.5" font-weight="700">Choose an account</text>
              <text x="344" y="100" fill="#5f6368" font-size="11.5">to continue to <tspan fill="#1a73e8" font-weight="700">{arena_host_esc}</tspan></text>

              <!-- Account row highlighted -->
              <rect x="338" y="118" width="244" height="64" rx="10" fill="#eff6ff" stroke="#2563eb" stroke-width="2.5"/>
              <circle cx="366" cy="150" r="18" fill="#2563eb"/>
              <text x="360" y="156" fill="#ffffff" font-size="15" font-weight="700">A</text>
              <text x="394" y="145" fill="#1e293b" font-size="13" font-weight="700">Alex Player</text>
              <text x="394" y="164" fill="#64748b" font-size="11.5">alex.player@gmail.com</text>
              <circle cx="578" cy="120" r="12" fill="#dc2626"/>
              <text x="574" y="125" fill="#ffffff" font-size="12" font-weight="700">2</text>

              <rect x="338" y="204" width="244" height="92" rx="10" fill="#f0fdf4" stroke="#86efac" stroke-width="1.5"/>
              <text x="352" y="228" fill="#166534" font-size="12" font-weight="700">&#10003; Instant Deep-Link Return</text>
              <text x="352" y="248" fill="#15803d" font-size="11">Redirects automatically back into</text>
              <text x="352" y="266" fill="#15803d" font-size="11" font-family="monospace">octi://auth/callback</text>

              <!-- Phone 5C: Welcome to OCTI Onboarding -->
              <rect x="626" y="20" width="276" height="320" rx="20" fill="#1c1917" stroke="#b45309" stroke-width="2"/>
              <text x="644" y="48" fill="#86efac" font-size="11" font-weight="700">5C &bull; Choose Player Name &amp; Play</text>

              <rect x="640" y="64" width="248" height="256" rx="14" fill="#292524" stroke="#78350f" stroke-width="1.5"/>
              <text x="656" y="90" fill="#f59e0b" font-size="15" font-weight="700">Welcome to OCTI!</text>
              <text x="656" y="110" fill="#d6d3d1" font-size="11">Choose the player name others will see:</text>

              <!-- OutlinedTextField Player Name -->
              <rect x="654" y="122" width="220" height="42" rx="6" fill="#1c1917" stroke="#f59e0b" stroke-width="2"/>
              <text x="664" y="136" fill="#fbbf24" font-size="9.5">Player Name</text>
              <text x="664" y="154" fill="#fef3c7" font-size="13" font-family="monospace" font-weight="700">GrandmasterA</text>
              <circle cx="872" cy="122" r="12" fill="#dc2626"/>
              <text x="868" y="127" fill="#ffffff" font-size="12" font-weight="700">3</text>

              <!-- Continue button -->
              <rect x="768" y="176" width="106" height="36" rx="18" fill="#d97706" stroke="#fde047" stroke-width="2.5"/>
              <text x="792" y="199" fill="#1c1917" font-size="12.5" font-weight="800">Continue</text>
              <circle cx="874" cy="176" r="12" fill="#dc2626"/>
              <text x="870" y="181" fill="#ffffff" font-size="12" font-weight="700">4</text>

              <!-- Connected Profile Summary -->
              <rect x="654" y="224" width="220" height="82" rx="8" fill="#1c1917" stroke="#44403c" stroke-width="1"/>
              <text x="666" y="244" fill="#86efac" font-size="11" font-weight="700">&#10003; Google &bull; Connected</text>
              <text x="666" y="264" fill="#fbbf24" font-size="10.5" font-family="monospace">Rating &mdash; 2P: 1500 &bull; 4P: 1500</text>
              <text x="666" y="282" fill="#a8a29e" font-size="10">OTA Self-Update Active (selfupdate)</text>
            </svg>
          </div>
        </div>
      </section>
"""


def render_portal_html(catalog_data: Dict[str, Any], base_url: str) -> str:
    """Render the master portal index.html with cards for all available apps."""
    ctx = parse_portal_context(base_url)
    base_url_slash_esc = html.escape(ctx["base_url_slash"])
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
        is_ext = is_external_catalog_entry(app, base_url)
        if is_ext:
            raw_page_url = str(app.get("pageUrl") or f"{slug}/")
            page_url = html.escape(raw_page_url)
            manifest_btn_url = html.escape(raw_page_url.rstrip("/") + "/version.json")
            ext_host = html.escape(
                urllib.parse.urlparse(str(app.get("apkUrl") or raw_page_url)).netloc
            )
            ext_badge_html = f'\n            <span class="badge">Hosted on {ext_host}</span>'
        else:
            page_url = f"{html.escape(slug)}/"
            manifest_btn_url = f"{html.escape(slug)}/version.json"
            ext_badge_html = ""

        card = f"""        <!-- App Card: {title} -->
        <div class="card" id="{html.escape(slug)}">
          <span class="card-tag">{category}</span>
          <h2 class="card-title" style="font-size: 1.45rem; margin-top: 0.5rem; margin-bottom: 0.5rem;">{title}</h2>
          <p class="card-desc" style="margin-bottom: 1rem;">{tagline}</p>

          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
            <span class="badge">v{version_name} (Build {version_code})</span>
            <span class="badge">{min_sdk_str}</span>
            <span class="badge">{size_str}</span>
            <span class="badge">{pub_date}</span>{ext_badge_html}
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
            <a href="{page_url}" class="btn btn-outline">Release Details &amp; Install Guide &rarr;</a>
            <a href="#android-install-guide" class="btn btn-outline">Step-by-Step Setup</a>
            <a href="{manifest_btn_url}" class="btn btn-outline">version.json</a>
          </div>
        </div>"""
        cards_html.append(card)

    cards_joined = "\n\n".join(cards_html) if cards_html else "        <p>No applications published yet.</p>"
    portal_install_guide_html = render_android_install_guide_html(base_url=base_url)

    if ctx["is_selfso_portal"]:
        meta_desc = "SELFSO.COM Android Software Distribution Portal — Independent Android companion applications and algorithmic tools."
        portal_heading = "Selfso Android Applications"
        back_href = "/projects/"
        back_label = "&larr; Back to Projects"
    else:
        meta_desc = f"{ctx['site_host']} Android Software Distribution Portal — Direct APK downloads and cryptographic OTA self-update."
        portal_heading = "OCTI Android Software Portal"
        back_href = "/"
        back_label = "&larr; Back to OCTI Arena"

    head_and_header, footer_and_script = _render_site_chrome(
        ctx, "Android Software &amp; OTA Distribution", meta_desc
    )

    return f"""{head_and_header}

  <main class="site-wrapper">
    <div class="container" style="padding-top: 3.5rem; padding-bottom: 4rem;">
      <div style="margin-bottom: 2.5rem;">
        <a href="{back_href}" style="color: var(--text-muted); font-size: 0.9rem; text-decoration: none;">{back_label}</a>
        <div style="margin-top: 0.75rem;">
          <span class="badge" style="margin-bottom: 0.75rem;">OTA Distribution Portal</span>
          <h1 style="font-size: 2.35rem; margin-bottom: 0.75rem;">{portal_heading}</h1>
        </div>
        <p style="color: var(--text-secondary); max-width: 720px; font-size: 1.05rem; line-height: 1.6;">
          Independent, open-source Android applications and mobile companion tools engineered for robotics, artificial intelligence, abstract gaming, and systems telemetry. Distributed directly via cryptographic OTA updates.
        </p>

        <!-- Cross-link banner to Windows desktop portal & Install Guide -->
        <div style="margin-top: 1.25rem; display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem;">
          <div style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.85rem; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 0.88rem;">
            <span style="color: var(--accent); font-weight: 600;">Windows Portal:</span>
            <span>Looking for native 64-bit Windows desktop apps?</span>
            <a href="/software/windows/" style="color: var(--accent); text-decoration: underline; margin-left: 0.25rem;">Visit the Windows Software Portal &rarr;</a>
          </div>
          <a href="#android-install-guide" class="btn btn-outline" style="padding: 0.48rem 0.95rem; font-size: 0.86rem; border-color: #d97706; color: #b45309; background: #fffbeb;">
            &#9888; Android Unknown Apps, Play Protect &amp; Google Sign-In Guide &darr;
          </a>
        </div>
      </div>

      <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));">
{cards_joined}
      </div>

{portal_install_guide_html}

      <!-- OTA Architecture & Verification Section -->
      <div style="margin-top: 3.5rem; border-top: 1px solid var(--border-subtle); padding-top: 2.5rem;">
        <span class="badge" style="margin-bottom: 0.75rem;">Distribution &amp; Security Architecture</span>
        <h2 style="font-size: 1.75rem; margin-bottom: 0.75rem;">OTA Self-Update Architecture (<code>com.selfso.selfupdate</code>)</h2>
        <p style="color: var(--text-secondary); max-width: 760px; margin-bottom: 1.5rem; line-height: 1.6;">
          Applications on this portal embed the first-party <code>com.selfso.selfupdate</code> in-app update engine. On launch or background trigger, applications poll <code>{base_url_slash_esc}version.json</code>, verify cryptographic SHA-256 digests against streaming downloads, and commit in-place package installations via Android&rsquo;s <code>PackageInstaller</code> Session API.
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
              <span>curl -s {base_url_slash_esc}version.json</span>
            </div>
            <div style="color: #a1a1aa; margin-bottom: 0.85rem; font-size: 0.8rem;">
              &#123; "schemaVersion": 1, "baseUrl": "{base_url_slash_esc}", "apps": &#123; ... &#125; &#125;
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

{footer_and_script}"""


def render_app_html(
    app_manifest: Dict[str, Any], app_meta: Dict[str, Any], base_url: str
) -> str:
    """Render a dedicated detail page index.html for a single application."""
    ctx = parse_portal_context(base_url)
    clean_base_esc = html.escape(ctx["clean_base"])
    slug = html.escape(app_manifest.get("slug", ""))
    title = html.escape(app_manifest.get("title") or app_meta.get("title") or slug.capitalize())
    category = html.escape(app_manifest.get("category") or app_meta.get("category") or "Software & Tools")
    raw_tagline = app_manifest.get("tagline") or app_meta.get("tagline") or app_manifest.get("releaseNotes", "")
    tagline = html.escape(raw_tagline)
    description = html.escape(app_manifest.get("description") or app_meta.get("description") or raw_tagline)
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
    if not ctx["is_selfso_portal"] and project_url == "/projects/octi/":
        project_url = "/"

    project_btn_html = ""
    if project_url:
        btn_label = "OCTI Online Arena" if (not ctx["is_selfso_portal"] and project_url == "/") else "Project Documentation"
        project_btn_html = f'<a href="{html.escape(project_url)}" class="btn btn-outline">{btn_label}</a>'

    head_and_header, footer_and_script = _render_site_chrome(
        ctx, f"{title} &bull; Android Distribution", raw_tagline
    )

    return f"""{head_and_header}

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
        <a href="#android-install-guide" class="btn btn-outline" style="border-color: #d97706; color: #b45309; background: #fffbeb;">
          &#9888; Android Unknown Apps, Play Protect &amp; Google Sign-In Guide &darr;
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

{render_android_install_guide_html(apk_filename=apk_filename, app_title=title, app_id=app_id, sha256_hint=sha256, base_url=base_url)}

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
            <span>curl -s {clean_base_esc}/{slug}/version.json</span>
          </div>
        </div>
      </div>
    </div>
  </main>

{footer_and_script}"""


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
    force_public: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Publish a single Android APK into the static web portal hierarchy."""
    src_apk = Path(apk_path).resolve()
    if not src_apk.is_file():
        raise FileNotFoundError(f"Source APK file not found: {apk_path}")

    w_root = Path(web_root).resolve()
    app_meta = KNOWN_APPS.get(slug, {})

    target_filename = app_meta.get("apkFilename", f"{slug}.apk")
    app_dir = w_root / slug
    staged_apk = app_dir / target_filename

    # Clean base url
    clean_base = base_url.rstrip("/")

    # Compute release notes
    notes = release_notes or app_meta.get("tagline") or f"{app_meta.get('title', slug)} release."

    # Discover metadata from source APK location if present
    meta_path = None
    if (src_apk.parent / "output-metadata.json").is_file():
        meta_path = src_apk.parent / "output-metadata.json"

    # Generate single-app manifest for the newly provided APK first
    new_manifest = generate_manifest(
        apk_path=src_apk,
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
        new_manifest["category"] = app_meta["category"]
    if app_meta.get("tagline"):
        new_manifest["tagline"] = app_meta["tagline"]
    if app_meta.get("description"):
        new_manifest["description"] = app_meta["description"]
    if app_meta.get("projectUrl"):
        new_manifest["projectUrl"] = app_meta["projectUrl"]
    new_manifest["apkFilename"] = target_filename
    if "packageUrl" not in new_manifest:
        new_manifest["packageUrl"] = new_manifest.get("apkUrl", "")

    # Check if per-app version.json and staged_apk already exist on disk
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
        and staged_apk.is_file()
        and int(existing_app_manifest.get("versionCode", -1)) == int(new_manifest.get("versionCode", -2))
        and str(existing_app_manifest.get("versionName", "")) == str(new_manifest.get("versionName", ""))
    )

    # Compute latest_filename
    if target_filename.lower().endswith(".apk"):
        latest_filename = target_filename[:-4] + "-latest.apk"
    else:
        stem = Path(target_filename).stem
        suffix = Path(target_filename).suffix
        latest_filename = f"{stem}-latest{suffix}"

    latest_apk = app_dir / latest_filename
    if not dry_run:
        app_dir.mkdir(parents=True, exist_ok=True)
        if src_apk.resolve() != latest_apk.resolve():
            shutil.copy2(src_apk, latest_apk)

    sha8 = new_manifest["sha256"][:8]
    latest_entry: Dict[str, Any] = {
        "apkFilename": latest_filename,
        "apkUrl": f"{clean_base}/{slug}/{latest_filename}?sha={sha8}",
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
            if src_apk.resolve() != staged_apk.resolve():
                shutil.copy2(src_apk, staged_apk)
        manifest = new_manifest
        manifest["latest"] = latest_entry

    if dry_run:
        return manifest

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


def bridge_external_catalog_entry(
    manifest: Dict[str, Any],
    www_software_dir: Union[str, Path],
    www_base_url: str = "https://www.selfso.com/software/android/",
) -> Path:
    """Mirror an externally hosted app manifest into www's master version.json & index.html without copying binaries."""
    target_dir = Path(www_software_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    master_json_path = target_dir / "version.json"
    clean_www_base = www_base_url if www_base_url.endswith("/") else f"{www_base_url}/"
    catalog: Dict[str, Any] = {
        "schemaVersion": 1,
        "baseUrl": clean_www_base,
        "updatedAt": manifest.get("publishedAt", ""),
        "apps": {},
    }
    if master_json_path.is_file():
        try:
            with open(master_json_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                catalog["schemaVersion"] = existing.get("schemaVersion", 1)
                catalog["baseUrl"] = existing.get("baseUrl") or clean_www_base
                if isinstance(existing.get("apps"), dict):
                    catalog["apps"] = existing["apps"]
        except Exception:
            pass

    app_id = manifest["applicationId"]
    catalog["updatedAt"] = manifest.get("publishedAt", catalog.get("updatedAt", ""))
    catalog["apps"][app_id] = copy.deepcopy(manifest)

    with open(master_json_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    portal_html = render_portal_html(catalog, catalog["baseUrl"])
    with open(target_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(portal_html)

    return master_json_path


def _catalog_has_external_entry(web_root: Path, slug: str, app_id: str, base_url: str) -> bool:
    master_json_path = web_root / "version.json"
    if not master_json_path.is_file():
        return False
    try:
        with open(master_json_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        for k, entry in (catalog.get("apps") or {}).items():
            if isinstance(entry, dict) and (
                entry.get("slug") == slug or entry.get("applicationId") == app_id or k == slug
            ):
                if is_external_catalog_entry(entry, base_url):
                    return True
    except Exception:
        pass
    return False


def publish_all(
    web_root: Union[str, Path],
    workspace_root: Optional[Union[str, Path]] = None,
    base_url: str = "https://www.selfso.com/software/android/",
    release_notes: Optional[str] = None,
    no_extra_copy: bool = False,
    keep_debug_suffix: bool = False,
    aapt2_bin: Optional[str] = None,
    published_at: Optional[str] = None,
    force_public: bool = False,
    dry_run: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Discover and publish all available built APKs from KNOWN_APPS."""
    ws = Path(workspace_root) if workspace_root else (Path.home() / "work")
    w_root = Path(web_root).resolve()
    ctx = parse_portal_context(base_url)
    published: Dict[str, Dict[str, Any]] = {}

    for slug, meta in KNOWN_APPS.items():
        app_id = meta.get("applicationId", "")
        if _catalog_has_external_entry(w_root, slug, app_id, base_url) or (
            slug == "octi" and ctx["is_selfso_portal"]
        ):
            print(f"Skipping {slug}: hosted externally (preserving catalog bridge).")
            continue
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
                force_public=force_public,
                dry_run=dry_run,
            )
            published[slug] = manifest
        else:
            print(f"Skipping {slug}: no compiled APK candidate found.")

    return published


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
        if is_external_catalog_entry(app_manifest, base_url):
            continue
        slug = app_manifest.get("slug") or key
        app_dir = web_root / slug
        per_app_json = app_dir / "version.json"
        if per_app_json.is_file():
            with open(per_app_json, "r", encoding="utf-8") as f:
                app_manifest = json.load(f)
        app_meta = KNOWN_APPS.get(slug, {})
        app_dir.mkdir(parents=True, exist_ok=True)
        app_html = render_app_html(app_manifest, app_meta, base_url)
        with open(app_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(app_html)
        rendered_apps += 1

    portal_html = render_portal_html(catalog, base_url)
    with open(web_root / "index.html", "w", encoding="utf-8") as f:
        f.write(portal_html)
    print(f"Re-rendered Android portal index.html and {rendered_apps} per-app HTML page(s) in {web_root}")
    return 0


def main(argv: Optional[list] = None) -> int:
    default_ws_root = Path.home() / "work"

    parser = argparse.ArgumentParser(
        description="Publish Android APKs to static web distribution portal."
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
        default=None,
        help="Target web root directory for software/android (defaults to octi/web/html/software/android for --slug octi, else www/selfso/html/software/android)",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(default_ws_root),
        help="Root directory of personal workspace",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base distribution URL (defaults to https://octi.selfso.com/software/android/ for --slug octi, else https://www.selfso.com/software/android/)",
    )
    parser.add_argument(
        "--bridge-www-catalog",
        default=None,
        help="Optional www software/android directory whose version.json & index.html should mirror this external app entry without copying binaries",
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
    parser.add_argument(
        "--force-public",
        action="store_true",
        help="Force overwriting the public release binary even if the version is unchanged.",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Re-render portal and per-app HTML pages from existing version.json manifests without modifying APKs.",
    )

    args = parser.parse_args(argv)

    if args.render_only:
        w_root, b_url = resolve_cli_target_defaults(
            args.slug, args.web_root, args.base_url, args.workspace_root
        )
        return re_render_existing_portal(w_root, b_url)

    if args.publish_all:
        w_root, b_url = resolve_cli_target_defaults(
            None, args.web_root, args.base_url, args.workspace_root
        )
        published = publish_all(
            web_root=w_root,
            workspace_root=args.workspace_root,
            base_url=b_url,
            release_notes=args.release_notes,
            no_extra_copy=args.no_extra_copy,
            keep_debug_suffix=args.keep_debug_suffix,
            aapt2_bin=args.aapt2,
            published_at=args.published_at,
            force_public=args.force_public,
        )
        print(f"Successfully published {len(published)} application(s).")
        return 0

    slug = args.slug or detect_slug_from_cwd()
    if not slug:
        sys.stderr.write("Error: Either --slug (or running inside a project dir) or --publish-all is required.\n")
        return 1

    w_root, b_url = resolve_cli_target_defaults(
        slug, args.web_root, args.base_url, args.workspace_root
    )

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
            web_root=w_root,
            workspace_root=args.workspace_root,
            base_url=b_url,
            release_notes=args.release_notes,
            no_extra_copy=args.no_extra_copy,
            keep_debug_suffix=args.keep_debug_suffix,
            aapt2_bin=args.aapt2,
            published_at=args.published_at,
            force_public=args.force_public,
        )
        if args.bridge_www_catalog:
            bridge_external_catalog_entry(manifest, args.bridge_www_catalog)
        print(
            f"Successfully published {manifest['slug']} v{manifest['versionName']} (Build {manifest['versionCode']})."
        )
        return 0
    except Exception as e:
        sys.stderr.write(f"Publication failed: {e}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
