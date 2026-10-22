#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional, Union


def compute_sha256(file_path: Union[str, Path]) -> str:
    """Compute streaming SHA-256 lowercase 64-character hex digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def parse_aapt2_badging(text: str) -> Dict[str, Any]:
    """Parse output text from `aapt2 dump badging`."""
    result: Dict[str, Any] = {}

    pkg_name = re.search(r"package:\s+name=['\"]([^'\"]+)['\"]", text)
    if pkg_name:
        result["applicationId"] = pkg_name.group(1)

    vc = re.search(r"package:.*?\s+versionCode=['\"]([^'\"]+)['\"]", text)
    if vc:
        try:
            result["versionCode"] = int(vc.group(1))
        except ValueError:
            pass

    vn = re.search(r"package:.*?\s+versionName=['\"]([^'\"]+)['\"]", text)
    if vn:
        result["versionName"] = vn.group(1)

    sdk = re.search(r"sdkVersion:['\"]([^'\"]+)['\"]", text)
    if sdk:
        try:
            result["minSdk"] = int(sdk.group(1))
        except ValueError:
            pass

    target_sdk = re.search(r"targetSdkVersion:['\"]([^'\"]+)['\"]", text)
    if target_sdk:
        try:
            result["targetSdk"] = int(target_sdk.group(1))
        except ValueError:
            pass

    label = re.search(r"^application-label:['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    if label:
        result["title"] = label.group(1)
    else:
        label_any = re.search(r"application-label(?:-[a-zA-Z_-]+)?:['\"]([^'\"]+)['\"]", text)
        if label_any:
            result["title"] = label_any.group(1)

    return result


def parse_output_metadata(metadata_path: Union[str, Path]) -> Dict[str, Any]:
    """Parse Android Gradle Plugin output-metadata.json file."""
    path = Path(metadata_path)
    if not path.is_file():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    result: Dict[str, Any] = {}
    if "applicationId" in data and data["applicationId"]:
        result["applicationId"] = str(data["applicationId"])

    elements = data.get("elements", [])
    if elements and isinstance(elements, list):
        elem = elements[0]
        if isinstance(elem, dict):
            if "versionCode" in elem and elem["versionCode"] is not None:
                try:
                    result["versionCode"] = int(elem["versionCode"])
                except ValueError:
                    pass
            if "versionName" in elem and elem["versionName"] is not None:
                result["versionName"] = str(elem["versionName"])

    if "minSdkVersionForDexing" in data:
        try:
            result["minSdk"] = int(data["minSdkVersionForDexing"])
        except ValueError:
            pass

    return result


def find_aapt2() -> Optional[str]:
    """Auto-discover aapt2 binary in PATH or Android SDK directories."""
    # 1. PATH lookup
    which_aapt2 = shutil.which("aapt2")
    if which_aapt2:
        return which_aapt2

    # 2. Android SDK build-tools lookup
    candidate_roots = []
    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        val = os.environ.get(env_var)
        if val:
            candidate_roots.append(Path(val) / "build-tools")

    candidate_roots.append(Path.home() / "Android/Sdk/build-tools")

    for bt_dir in candidate_roots:
        if bt_dir.exists() and bt_dir.is_dir():
            versions = sorted(bt_dir.glob("*/aapt2"), reverse=True)
            for aapt2_path in versions:
                if aapt2_path.is_file() and os.access(aapt2_path, os.X_OK):
                    return str(aapt2_path)

    return None


def extract_apk_metadata(
    apk_path: Union[str, Path],
    metadata_path: Optional[Union[str, Path]] = None,
    keep_debug_suffix: bool = False,
    aapt2_bin: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract metadata from an APK using aapt2 and/or output-metadata.json."""
    path = Path(apk_path)
    if not path.is_file():
        raise FileNotFoundError(f"APK file not found: {apk_path}")

    result: Dict[str, Any] = {}

    # Discover and read output-metadata.json if available
    meta_file = None
    if metadata_path:
        meta_file = Path(metadata_path)
    else:
        candidate = path.parent / "output-metadata.json"
        if candidate.is_file():
            meta_file = candidate

    if meta_file and meta_file.is_file():
        result.update(parse_output_metadata(meta_file))

    # Run aapt2 dump badging if available
    bin_path = aapt2_bin or find_aapt2()
    if bin_path:
        try:
            proc = subprocess.run(
                [bin_path, "dump", "badging", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                badging = parse_aapt2_badging(proc.stdout)
                for k, v in badging.items():
                    if v is not None:
                        result[k] = v
        except Exception:
            pass

    # Strip .debug suffix from applicationId if requested
    if "applicationId" in result and not keep_debug_suffix:
        app_id = result["applicationId"]
        if app_id.endswith(".debug"):
            result["applicationId"] = app_id[:-6]

    return result


def generate_manifest(
    apk_path: Union[str, Path],
    slug: Optional[str] = None,
    title: Optional[str] = None,
    application_id: Optional[str] = None,
    version_code: Optional[int] = None,
    version_name: Optional[str] = None,
    min_sdk: Optional[int] = None,
    target_sdk: Optional[int] = None,
    apk_url: Optional[str] = None,
    page_url: Optional[str] = None,
    release_notes: Optional[str] = None,
    published_at: Optional[str] = None,
    base_url: str = "https://www.selfso.com/software/android/",
    keep_debug_suffix: bool = False,
    metadata_path: Optional[Union[str, Path]] = None,
    aapt2_bin: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a single-app version.json manifest dictionary for an APK."""
    apk_file = Path(apk_path)
    if not apk_file.is_file():
        raise FileNotFoundError(f"APK file not found: {apk_path}")

    extracted = extract_apk_metadata(
        apk_path=apk_file,
        metadata_path=metadata_path,
        keep_debug_suffix=keep_debug_suffix,
        aapt2_bin=aapt2_bin,
    )

    final_app_id = application_id or extracted.get("applicationId", "")
    final_version_code = version_code if version_code is not None else extracted.get("versionCode", 1)
    final_version_name = version_name or extracted.get("versionName", "1.0")
    final_min_sdk = min_sdk if min_sdk is not None else extracted.get("minSdk", 24)
    final_target_sdk = target_sdk if target_sdk is not None else extracted.get("targetSdk", 35)

    final_slug = slug or extracted.get("slug")
    if not final_slug:
        if final_app_id:
            final_slug = final_app_id.split(".")[-1]
        else:
            final_slug = apk_file.stem.lower()

    final_title = title or extracted.get("title") or final_slug.replace("-", " ").replace("_", " ").title()

    sha256_hash = compute_sha256(apk_file)
    size_bytes = apk_file.stat().st_size

    base_clean = base_url.rstrip("/")
    final_apk_url = apk_url or f"{base_clean}/{final_slug}/{apk_file.name}"
    final_page_url = page_url or f"{base_clean}/{final_slug}/"

    if not published_at:
        published_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    final_release_notes = (
        release_notes
        if release_notes is not None
        else f"{final_title} v{final_version_name} release."
    )

    manifest: Dict[str, Any] = {
        "slug": str(final_slug),
        "title": str(final_title),
        "applicationId": str(final_app_id),
        "versionCode": int(final_version_code),
        "versionName": str(final_version_name),
        "minSdk": int(final_min_sdk),
        "targetSdk": int(final_target_sdk),
        "apkUrl": str(final_apk_url),
        "pageUrl": str(final_page_url),
        "sha256": str(sha256_hash),
        "sizeBytes": int(size_bytes),
        "publishedAt": str(published_at),
        "releaseNotes": str(final_release_notes),
    }

    return manifest


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate single-app version.json manifest from Android APK."
    )
    parser.add_argument("--apk", required=True, help="Path to .apk file")
    parser.add_argument("--slug", help="Application slug identifier (e.g. octi, aimon)")
    parser.add_argument("--title", help="Application display title")
    parser.add_argument("--app-id", help="Override applicationId")
    parser.add_argument("--version-code", type=int, help="Override versionCode")
    parser.add_argument("--version-name", help="Override versionName")
    parser.add_argument("--min-sdk", type=int, help="Override minSdk")
    parser.add_argument("--target-sdk", type=int, help="Override targetSdk")
    parser.add_argument("--apk-url", help="Direct URL to downloadable APK")
    parser.add_argument("--page-url", help="URL to application release/info page")
    parser.add_argument("--release-notes", help="Release notes text or summary")
    parser.add_argument("--published-at", help="Publication timestamp in ISO-8601 UTC format")
    parser.add_argument(
        "--base-url",
        default="https://www.selfso.com/software/android/",
        help="Base distribution URL",
    )
    parser.add_argument("--metadata", help="Path to AGP output-metadata.json")
    parser.add_argument(
        "--keep-debug-suffix",
        action="store_true",
        help="Do not strip .debug suffix from applicationId",
    )
    parser.add_argument("--aapt2", help="Path to aapt2 binary")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--indent", type=int, default=2, help="JSON formatting indentation")

    args = parser.parse_args(argv)

    try:
        manifest = generate_manifest(
            apk_path=args.apk,
            slug=args.slug,
            title=args.title,
            application_id=args.app_id,
            version_code=args.version_code,
            version_name=args.version_name,
            min_sdk=args.min_sdk,
            target_sdk=args.target_sdk,
            apk_url=args.apk_url,
            page_url=args.page_url,
            release_notes=args.release_notes,
            published_at=args.published_at,
            base_url=args.base_url,
            keep_debug_suffix=args.keep_debug_suffix,
            metadata_path=args.metadata,
            aapt2_bin=args.aapt2,
        )
    except FileNotFoundError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1
    except Exception as e:
        sys.stderr.write(f"Unexpected error: {e}\n")
        return 2

    json_str = json.dumps(manifest, indent=args.indent, ensure_ascii=False) + "\n"

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_str)
    else:
        sys.stdout.write(json_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
