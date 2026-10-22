#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
from typing import Any, Dict, List, Optional, Tuple, Union


def compute_sha256(file_path: Union[str, Path]) -> str:
    """Compute streaming SHA-256 lowercase 64-character hex digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def parse_string_file_info(ver_bytes: bytes) -> Dict[str, str]:
    """Parse StringFileInfo key-value pairs from PE RT_VERSION resource payload."""
    strings: Dict[str, str] = {}
    if not ver_bytes:
        return strings

    target_keys = [
        "ProductName",
        "ProductVersion",
        "FileVersion",
        "CompanyName",
        "FileDescription",
        "OriginalFilename",
        "InternalName",
        "LegalCopyright",
    ]

    for key in target_keys:
        # Search for null-terminated UTF-16LE key
        k_bytes = (key + "\0").encode("utf-16le")
        k_pos = ver_bytes.find(k_bytes)
        if k_pos != -1 and k_pos >= 6:
            entry_start = k_pos - 6
            try:
                w_len, w_val_len, w_type = struct.unpack_from("<HHH", ver_bytes, entry_start)
                val_start = k_pos + len(k_bytes)
                # Align to 4-byte boundary relative to entry_start
                if (val_start - entry_start) % 4 != 0:
                    val_start += 2
                if val_start < len(ver_bytes) and w_val_len > 0:
                    val_bytes = ver_bytes[val_start : val_start + w_val_len * 2]
                    val_str = val_bytes.decode("utf-16le", errors="replace").rstrip("\0")
                    strings[key] = val_str
            except struct.error:
                continue

    return strings


def parse_pe_metadata(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Parse PE header and traverse the .rsrc 3-level resource directory down to
    RT_VERSION (type ID 16) to extract machine architecture, VS_FIXEDFILEINFO,
    and StringFileInfo keys.

    Crucially, this isolates RT_VERSION from other resource sections such as
    RT_RCDATA (type ID 10) which may embed ZIP payloads (e.g. Qt6Core.dll).
    """
    path = Path(file_path)
    if not path.is_file():
        return {}

    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return {}

    if len(data) < 64 or data[:2] != b"MZ":
        return {}

    try:
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if e_lfanew + 24 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
            return {}

        machine, num_sections, _, _, _, opt_hdr_size, _ = struct.unpack_from(
            "<HHIIIHH", data, e_lfanew + 4
        )

        arch = "unknown"
        if machine == 0x8664:
            arch = "x86_64"
        elif machine == 0x014C:
            arch = "x86"
        elif machine == 0xAA64:
            arch = "arm64"

        opt_offset = e_lfanew + 24
        if opt_offset + opt_hdr_size > len(data):
            return {"arch": arch}

        magic = struct.unpack_from("<H", data, opt_offset)[0]
        is_pe32_plus = (magic == 0x20B)

        # Resource Data Directory entry is index 2
        rsrc_dir_offset = opt_offset + (128 if is_pe32_plus else 112)
        rsrc_rva, rsrc_size = struct.unpack_from("<II", data, rsrc_dir_offset)
        if rsrc_rva == 0 or rsrc_size == 0:
            return {"arch": arch}

        # Parse section headers to map RVAs to file offsets
        sec_offset = opt_offset + opt_hdr_size
        sections: List[Tuple[int, int, int, int]] = []  # (vsize, va, raw_size, raw_ptr)
        for i in range(num_sections):
            sec_hdr = sec_offset + i * 40
            if sec_hdr + 40 > len(data):
                break
            vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", data, sec_hdr + 8)
            sections.append((vsize, va, raw_size, raw_ptr))

        def rva_to_offset(rva: int) -> Optional[int]:
            for vsize, va, raw_size, raw_ptr in sections:
                if va <= rva < va + max(vsize, raw_size):
                    return raw_ptr + (rva - va)
            return None

        rsrc_raw_offset = rva_to_offset(rsrc_rva)
        if rsrc_raw_offset is None or rsrc_raw_offset >= len(data):
            return {"arch": arch}

        def parse_dir_entries(dir_offset: int) -> List[Tuple[int, int]]:
            if dir_offset + 16 > len(data):
                return []
            num_named, num_id = struct.unpack_from("<HH", data, dir_offset + 12)
            total = num_named + num_id
            entries: List[Tuple[int, int]] = []
            entry_offset = dir_offset + 16
            for idx in range(total):
                if entry_offset + (idx + 1) * 8 > len(data):
                    break
                eid, off = struct.unpack_from("<II", data, entry_offset + idx * 8)
                entries.append((eid, off))
            return entries

        # Level 1: Find Resource Type 16 (RT_VERSION)
        version_bytes: Optional[bytes] = None
        for type_id, off1 in parse_dir_entries(rsrc_raw_offset):
            if type_id == 16:  # RT_VERSION
                real_off1 = off1 & 0x7FFFFFFF
                # Level 2: Name / Resource ID (e.g. 1)
                for name_id, off2 in parse_dir_entries(rsrc_raw_offset + real_off1):
                    real_off2 = off2 & 0x7FFFFFFF
                    # Level 3: Language ID (e.g. 1033)
                    for lang_id, off3 in parse_dir_entries(rsrc_raw_offset + real_off2):
                        real_off3 = off3 & 0x7FFFFFFF
                        # Leaf: IMAGE_RESOURCE_DATA_ENTRY (16 bytes)
                        if rsrc_raw_offset + real_off3 + 16 <= len(data):
                            data_rva, data_size = struct.unpack_from(
                                "<II", data, rsrc_raw_offset + real_off3
                            )[:2]
                            file_off = rva_to_offset(data_rva)
                            if (
                                file_off is not None
                                and file_off + data_size <= len(data)
                            ):
                                version_bytes = data[file_off : file_off + data_size]
                                break
                    if version_bytes:
                        break
            if version_bytes:
                break

        res: Dict[str, Any] = {"arch": arch}
        if not version_bytes:
            return res

        # Parse VS_FIXEDFILEINFO (signature 0xFEEF04BD)
        ff_idx = version_bytes.find(b"\xbd\x04\xef\xfe")
        if ff_idx != -1 and ff_idx + 52 <= len(version_bytes):
            _, _, fv_ms, fv_ls, pv_ms, pv_ls = struct.unpack_from(
                "<IIIIII", version_bytes, ff_idx
            )
            res["fixed_file_version"] = (
                fv_ms >> 16,
                fv_ms & 0xFFFF,
                fv_ls >> 16,
                fv_ls & 0xFFFF,
            )
            res["fixed_product_version"] = (
                pv_ms >> 16,
                pv_ms & 0xFFFF,
                pv_ls >> 16,
                pv_ls & 0xFFFF,
            )

        # Parse StringFileInfo
        res["strings"] = parse_string_file_info(version_bytes)
        return res

    except Exception:
        return {}


def normalize_version_name(
    raw_version: Optional[str] = None,
    pe_info: Optional[Dict[str, Any]] = None,
    filename: str = "",
) -> str:
    """Normalize version string into standard major.minor.patch format."""
    candidate = raw_version

    if not candidate and pe_info:
        strings = pe_info.get("strings", {})
        candidate = strings.get("ProductVersion") or strings.get("FileVersion")
        if not candidate and "fixed_product_version" in pe_info:
            fpv = pe_info["fixed_product_version"]
            if fpv[3] == 0:
                candidate = f"{fpv[0]}.{fpv[1]}.{fpv[2]}"
            else:
                candidate = f"{fpv[0]}.{fpv[1]}.{fpv[2]}.{fpv[3]}"

    if not candidate and filename:
        m = re.search(r"[-_]([0-9]+(?:\.[0-9]+)+)", filename)
        if m:
            candidate = m.group(1)

    if not candidate:
        return "1.0.0"

    cand = candidate.strip()
    if cand.startswith("v") or cand.startswith("V"):
        cand = cand[1:]

    # If format is major.minor.patch.0, normalize by stripping trailing .0
    m_quad = re.match(r"^([0-9]+\.[0-9]+\.[0-9]+)\.0$", cand)
    if m_quad:
        return m_quad.group(1)

    return cand


def compute_version_code(version_name: str, explicit_code: Optional[int] = None) -> int:
    """Compute integer versionCode (major * 10000 + minor * 100 + patch)."""
    if explicit_code is not None and explicit_code > 0:
        return explicit_code

    clean = version_name.strip()
    if clean.startswith("v") or clean.startswith("V"):
        clean = clean[1:]

    # Remove any prerelease or build suffix
    for sep in ("-", "+"):
        if sep in clean:
            clean = clean.split(sep, 1)[0]

    parts = clean.split(".")
    major = 0
    minor = 0
    patch = 0

    if len(parts) >= 1:
        try:
            major = int(re.sub(r"\D.*", "", parts[0]) or "0")
        except ValueError:
            pass
    if len(parts) >= 2:
        try:
            minor = int(re.sub(r"\D.*", "", parts[1]) or "0")
        except ValueError:
            pass
    if len(parts) >= 3:
        try:
            patch = int(re.sub(r"\D.*", "", parts[2]) or "0")
        except ValueError:
            pass

    code = major * 10000 + minor * 100 + patch
    return max(code, 1)


def detect_install_type(filename: str, explicit_type: Optional[str] = None) -> str:
    """Detect whether package is an installer or standalone binary."""
    if explicit_type:
        t = explicit_type.strip().lower()
        if "installer" in t:
            return "installer"
        elif "binary" in t:
            return "binary"
        return explicit_type

    fn = filename.lower()
    if "setup" in fn or "install" in fn:
        return "installer"
    return "binary"


def generate_manifest(
    package_path: Union[str, Path],
    slug: Optional[str] = None,
    title: Optional[str] = None,
    application_id: Optional[str] = None,
    version_code: Optional[int] = None,
    version_name: Optional[str] = None,
    install_type: Optional[str] = None,
    installer_args: Optional[str] = None,
    executable_name: Optional[str] = None,
    arch: Optional[str] = None,
    min_os: Optional[str] = None,
    package_url: Optional[str] = None,
    page_url: Optional[str] = None,
    release_notes: Optional[str] = None,
    published_at: Optional[str] = None,
    base_url: str = "https://www.selfso.com/software/windows/",
) -> Dict[str, Any]:
    """Generate a single-application manifest dictionary from a Windows package."""
    pkg = Path(package_path).resolve()
    if not pkg.is_file():
        raise FileNotFoundError(f"Package file not found: {package_path}")

    filename = pkg.name
    pe_info = parse_pe_metadata(pkg)

    # 1. Resolve slug
    inferred_slug = slug
    if not inferred_slug:
        # e.g. octi-setup-2.0.3.exe -> octi, aimon-setup.exe -> aimon
        m = re.match(r"^([a-zA-Z0-9_-]+?)(?:[-_]setup|[-_]install|[-_][0-9]|\.exe|\.zip)", filename, re.IGNORECASE)
        if m:
            inferred_slug = m.group(1).lower().replace("_", "-")
        else:
            inferred_slug = pkg.stem.lower().replace("_", "-")

    # 2. Resolve title
    inferred_title = title
    if not inferred_title and pe_info:
        strings = pe_info.get("strings", {})
        inferred_title = strings.get("ProductName")
    if not inferred_title:
        inferred_title = inferred_slug.replace("-", " ").title()

    # 3. Resolve applicationId
    inferred_app_id = application_id
    if not inferred_app_id:
        normalized_sub = inferred_slug.replace("-", ".")
        inferred_app_id = f"com.selfso.{normalized_sub}"

    # 4. Resolve versionName and versionCode
    norm_version_name = normalize_version_name(version_name, pe_info, filename)
    computed_version_code = compute_version_code(norm_version_name, version_code)

    # 5. Resolve installType and installerArgs
    resolved_install_type = detect_install_type(filename, install_type)
    resolved_installer_args = installer_args
    if resolved_installer_args is None:
        resolved_installer_args = "/S" if resolved_install_type == "installer" else ""

    # 6. Resolve executableName
    resolved_exe_name = executable_name
    if not resolved_exe_name and pe_info:
        strings = pe_info.get("strings", {})
        resolved_exe_name = strings.get("OriginalFilename") or strings.get("InternalName")
        if resolved_exe_name and not resolved_exe_name.lower().endswith(".exe"):
            resolved_exe_name = f"{resolved_exe_name}.exe"
    if not resolved_exe_name:
        resolved_exe_name = f"{inferred_slug.replace('-', '_')}.exe"

    # 7. Resolve architecture and minOs
    resolved_arch = arch
    if not resolved_arch:
        pe_arch = pe_info.get("arch")
        resolved_arch = pe_arch if pe_arch and pe_arch != "unknown" else "x86_64"

    resolved_min_os = min_os if min_os else "Windows 10 (64-bit)+"

    # 8. Clean base URL and resolve packageUrl / pageUrl
    clean_base = base_url.rstrip("/")
    resolved_pkg_url = package_url
    if not resolved_pkg_url:
        resolved_pkg_url = f"{clean_base}/{inferred_slug}/{filename}"

    resolved_page_url = page_url
    if not resolved_page_url:
        resolved_page_url = f"{clean_base}/{inferred_slug}/"

    # 9. Compute cryptographic digest and size
    sha256_digest = compute_sha256(pkg)
    size_bytes = pkg.stat().st_size

    # 10. Publication timestamp
    pub_at = published_at
    if not pub_at:
        pub_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 11. Release notes
    notes = release_notes or f"{inferred_title} release."

    manifest: Dict[str, Any] = {
        "slug": inferred_slug,
        "title": inferred_title,
        "applicationId": inferred_app_id,
        "versionCode": computed_version_code,
        "versionName": norm_version_name,
        "installType": resolved_install_type,
        "installerArgs": resolved_installer_args,
        "executableName": resolved_exe_name,
        "arch": resolved_arch,
        "minOs": resolved_min_os,
        "packageUrl": resolved_pkg_url,
        "pageUrl": resolved_page_url,
        "sha256": sha256_digest,
        "sizeBytes": size_bytes,
        "publishedAt": pub_at,
        "releaseNotes": notes,
    }

    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for gen_windows_version_json.py."""
    parser = argparse.ArgumentParser(
        description="Inspect Windows PE (.exe) or .zip package and generate selfupdate version.json manifest."
    )
    parser.add_argument(
        "package",
        nargs="?",
        help="Path to Windows installer (.exe) or binary file.",
    )
    parser.add_argument(
        "--package",
        dest="package_opt",
        help="Path to Windows installer (.exe) or binary file (alias).",
    )
    parser.add_argument(
        "--exe",
        dest="exe_opt",
        help="Path to Windows executable file (alias).",
    )
    parser.add_argument(
        "--slug",
        help="Application slug identifier (e.g. octi, aimon).",
    )
    parser.add_argument(
        "--title",
        help="Human-readable application title.",
    )
    parser.add_argument(
        "--app-id",
        "--application-id",
        dest="app_id",
        help="Unique application ID (e.g. com.selfso.octi).",
    )
    parser.add_argument(
        "--version-code",
        type=int,
        help="Integer version code (overrides auto-computed versionCode).",
    )
    parser.add_argument(
        "--version-name",
        help="Human-readable version name (overrides PE / filename version).",
    )
    parser.add_argument(
        "--install-type",
        choices=["installer", "binary"],
        help="Installation type: installer or binary.",
    )
    parser.add_argument(
        "--installer-args",
        help="Command-line arguments for installer mode (default '/S' for installer).",
    )
    parser.add_argument(
        "--executable-name",
        help="Post-install executable name (e.g. octi.exe).",
    )
    parser.add_argument(
        "--arch",
        help="Target architecture (default x86_64).",
    )
    parser.add_argument(
        "--min-os",
        help="Minimum required OS (default 'Windows 10 (64-bit)+').",
    )
    parser.add_argument(
        "--package-url",
        help="Download URL for the package.",
    )
    parser.add_argument(
        "--page-url",
        help="Portal release detail page URL.",
    )
    parser.add_argument(
        "--release-notes",
        help="Release notes summary.",
    )
    parser.add_argument(
        "--published-at",
        help="ISO-8601 publication timestamp (default current UTC time).",
    )
    parser.add_argument(
        "--base-url",
        default="https://www.selfso.com/software/windows/",
        help="Base portal URL (default: https://www.selfso.com/software/windows/).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to output JSON file (defaults to stdout).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation spaces (default: 2).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    pkg_path = args.package or args.package_opt or args.exe_opt
    if not pkg_path:
        parser.error("A package file path must be specified via argument, --package, or --exe.")

    try:
        manifest = generate_manifest(
            package_path=pkg_path,
            slug=args.slug,
            title=args.title,
            application_id=args.app_id,
            version_code=args.version_code,
            version_name=args.version_name,
            install_type=args.install_type,
            installer_args=args.installer_args,
            executable_name=args.executable_name,
            arch=args.arch,
            min_os=args.min_os,
            package_url=args.package_url,
            page_url=args.page_url,
            release_notes=args.release_notes,
            published_at=args.published_at,
            base_url=args.base_url,
        )
    except Exception as e:
        sys.stderr.write(f"Error generating Windows version manifest: {e}\n")
        return 1

    json_text = json.dumps(manifest, indent=args.indent, ensure_ascii=False) + "\n"

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_text)
    else:
        sys.stdout.write(json_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
