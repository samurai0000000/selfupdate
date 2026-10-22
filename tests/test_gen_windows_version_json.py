#!/usr/bin/env python3
# Copyright (C) 2026, Charles Chiou

import os
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.gen_windows_version_json import (
    compute_sha256,
    compute_version_code,
    detect_install_type,
    generate_manifest,
    main,
    normalize_version_name,
    parse_pe_metadata,
)


def create_synthetic_pe(
    rcdata_strings=None,
    version_strings=None,
    file_version=(1, 2, 3, 0),
    product_version=(1, 2, 3, 0),
    machine=0x8664,  # x86_64
) -> bytes:
    """Build a synthetic PE binary with both RT_RCDATA and RT_VERSION resources."""
    def pad(b: bytes, align: int = 4) -> bytes:
        rem = len(b) % align
        return b + (b"\0" * (align - rem)) if rem != 0 else b

    if rcdata_strings is None:
        rcdata_strings = ["Qt6Core.dll", "FileVersion", "6.8.3.0", "ProductName", "Qt6"]

    if version_strings is None:
        version_strings = [
            ("ProductName", "aimon"),
            ("ProductVersion", "1.2.3.0"),
            ("FileVersion", "1.2.3.0"),
            ("CompanyName", "Charles Chiou"),
        ]

    # 1. RT_RCDATA payload (contains embedded fake strings that must NOT be matched)
    rcdata_bytes = ("\0".join(rcdata_strings) + "\0").encode("utf-16le")
    rcdata_payload = pad(rcdata_bytes, 4)

    # 2. RT_VERSION payload (VS_VERSIONINFO structure)
    fv_ms = (file_version[0] << 16) | file_version[1]
    fv_ls = (file_version[2] << 16) | file_version[3]
    pv_ms = (product_version[0] << 16) | product_version[1]
    pv_ls = (product_version[2] << 16) | product_version[3]

    fixed_file_info = struct.pack(
        "<IIIIIIIIIIIII",
        0xFEEF04BD,  # dwSignature
        0x00010000,  # dwStrucVersion
        fv_ms,
        fv_ls,
        pv_ms,
        pv_ls,
        0x0000003F,  # dwFileFlagsMask
        0,           # dwFileFlags
        0x00040004,  # dwFileOS (VOS_NT_WINDOWS32)
        0x00000001,  # dwFileType (VFT_APP)
        0,           # dwFileSubtype
        0,           # dwFileDateMS
        0,           # dwFileDateLS
    )

    str_entries = b""
    for k, v in version_strings:
        k_b = (k + "\0").encode("utf-16le")
        v_b = (v + "\0").encode("utf-16le")
        w_val_len = len(v) + 1
        entry_hdr = struct.pack("<HHH", 0, w_val_len, 1)
        raw_entry = entry_hdr + k_b
        raw_entry = pad(raw_entry, 4) + v_b
        w_len = len(raw_entry)
        raw_entry = struct.pack("<H", w_len) + raw_entry[2:]
        str_entries += pad(raw_entry, 4)

    # StringTable header ("040904B0\0")
    st_key = "040904B0\0".encode("utf-16le")
    st_raw = struct.pack("<HHH", 0, 0, 1) + st_key
    st_raw = pad(st_raw, 4) + str_entries
    st_len = len(st_raw)
    st_raw = struct.pack("<H", st_len) + st_raw[2:]

    # StringFileInfo header ("StringFileInfo\0")
    sfi_key = "StringFileInfo\0".encode("utf-16le")
    sfi_raw = struct.pack("<HHH", 0, 0, 1) + sfi_key
    sfi_raw = pad(sfi_raw, 4) + st_raw
    sfi_len = len(sfi_raw)
    sfi_raw = struct.pack("<H", sfi_len) + sfi_raw[2:]

    # VS_VERSIONINFO root header ("VS_VERSION_INFO\0")
    vinfo_key = "VS_VERSION_INFO\0".encode("utf-16le")
    vinfo_raw = struct.pack("<HHH", 0, len(fixed_file_info), 0) + vinfo_key
    vinfo_raw = pad(vinfo_raw, 4) + fixed_file_info
    vinfo_raw = pad(vinfo_raw, 4) + sfi_raw
    vinfo_len = len(vinfo_raw)
    version_payload = struct.pack("<H", vinfo_len) + vinfo_raw[2:]
    version_payload = pad(version_payload, 4)

    # Assemble .rsrc directory table
    rsrc_sec_va = 0x2000
    rsrc_raw_ptr = 0x400

    root_dir = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 2)
    entry_rcdata = struct.pack("<II", 10, 0x80000000 | 0x20)
    entry_version = struct.pack("<II", 16, 0x80000000 | 0x60)

    rcdata_dir_l2 = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", 1, 0x80000000 | 0x38)
    rcdata_dir_l3 = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", 1033, 0x50)

    ver_dir_l2 = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", 1, 0x80000000 | 0x78)
    ver_dir_l3 = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", 1033, 0x90)

    rcdata_payload_rva = rsrc_sec_va + 0xA0
    ver_payload_rva = rcdata_payload_rva + len(rcdata_payload)

    rcdata_data_entry = struct.pack("<IIII", rcdata_payload_rva, len(rcdata_payload), 0, 0)
    ver_data_entry = struct.pack("<IIII", ver_payload_rva, len(version_payload), 0, 0)

    rsrc_data = (
        root_dir + entry_rcdata + entry_version +
        rcdata_dir_l2 +
        rcdata_dir_l3 +
        rcdata_data_entry +
        ver_dir_l2 +
        ver_dir_l3 +
        ver_data_entry +
        rcdata_payload +
        version_payload
    )

    # DOS Header
    dos_hdr = bytearray(0x80)
    dos_hdr[0:2] = b"MZ"
    struct.pack_into("<I", dos_hdr, 0x3C, 0x80)

    # PE Signature + COFF Header
    pe_sig = b"PE\0\0"
    is_64 = (machine == 0x8664 or machine == 0xAA64)
    opt_size = 240 if is_64 else 224
    coff_hdr = struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, opt_size, 0x0022)

    # Optional Header
    opt_hdr = bytearray(opt_size)
    magic = 0x20B if is_64 else 0x10B
    struct.pack_into("<H", opt_hdr, 0, magic)
    struct.pack_into("<I", opt_hdr, 16, 0x1000)
    rva_sizes_offset = 108 if is_64 else 92
    struct.pack_into("<I", opt_hdr, rva_sizes_offset, 16)
    rsrc_dir_offset = 128 if is_64 else 112
    struct.pack_into("<II", opt_hdr, rsrc_dir_offset, rsrc_sec_va, len(rsrc_data))

    # Section Header (.rsrc)
    sec_hdr = struct.pack(
        "<8sIIIIIIHHI",
        b".rsrc\0\0\0",
        len(rsrc_data),
        rsrc_sec_va,
        len(rsrc_data),
        rsrc_raw_ptr,
        0, 0, 0, 0,
        0x40000040,
    )

    headers = dos_hdr + pe_sig + coff_hdr + opt_hdr + sec_hdr
    pe_bytes = bytes(headers)
    if len(pe_bytes) < rsrc_raw_ptr:
        pe_bytes += b"\0" * (rsrc_raw_ptr - len(pe_bytes))
    pe_bytes += rsrc_data

    return pe_bytes


class TestGenWindowsVersionJson(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_synthetic_pe_with_rcdata_and_rt_version(self):
        """
        Critical Test: Verify that embedded RCDATA (type 10) containing fake Qt6 strings
        is completely ignored, and RT_VERSION (type 16) is extracted authentically.
        """
        pe_bytes = create_synthetic_pe(
            rcdata_strings=["Qt6Core.dll", "FileVersion", "6.8.3.0", "ProductName", "Qt6"],
            version_strings=[
                ("ProductName", "aimon"),
                ("ProductVersion", "1.2.3.0"),
                ("FileVersion", "1.2.3.0"),
                ("CompanyName", "Charles Chiou"),
                ("OriginalFilename", "aimon.exe"),
            ],
            file_version=(1, 2, 3, 0),
            product_version=(1, 2, 3, 0),
            machine=0x8664,
        )

        test_exe = self.tmp_path / "aimon-setup-1.2.3.exe"
        with open(test_exe, "wb") as f:
            f.write(pe_bytes)

        meta = parse_pe_metadata(test_exe)
        self.assertEqual(meta.get("arch"), "x86_64")
        self.assertEqual(meta.get("fixed_product_version"), (1, 2, 3, 0))
        self.assertEqual(meta.get("fixed_file_version"), (1, 2, 3, 0))

        strings = meta.get("strings", {})
        # Must match authentic RT_VERSION strings
        self.assertEqual(strings.get("ProductName"), "aimon")
        self.assertEqual(strings.get("ProductVersion"), "1.2.3.0")
        self.assertEqual(strings.get("FileVersion"), "1.2.3.0")
        self.assertEqual(strings.get("CompanyName"), "Charles Chiou")
        self.assertEqual(strings.get("OriginalFilename"), "aimon.exe")

        # Must NEVER match RT_RCDATA strings
        self.assertNotIn("Qt6", strings.values())
        self.assertNotIn("6.8.3.0", strings.values())

        # Test manifest generation on synthetic PE
        manifest = generate_manifest(test_exe)
        self.assertEqual(manifest["slug"], "aimon")
        self.assertEqual(manifest["title"], "aimon")
        self.assertEqual(manifest["applicationId"], "com.selfso.aimon")
        self.assertEqual(manifest["versionName"], "1.2.3")
        self.assertEqual(manifest["versionCode"], 10203)
        self.assertEqual(manifest["installType"], "installer")
        self.assertEqual(manifest["installerArgs"], "/S")
        self.assertEqual(manifest["executableName"], "aimon.exe")
        self.assertEqual(manifest["arch"], "x86_64")
        self.assertEqual(manifest["sizeBytes"], len(pe_bytes))
        self.assertEqual(manifest["sha256"], compute_sha256(test_exe))

    def test_cli_parameter_invocation(self):
        pe_bytes = create_synthetic_pe(
            rcdata_strings=[],
            version_strings=[
                ("ProductName", "OCTI Desktop Player"),
                ("ProductVersion", "2.0.3"),
                ("FileVersion", "2.0.3"),
                ("CompanyName", "Charles Chiou"),
                ("OriginalFilename", "octi.exe"),
            ],
            file_version=(2, 0, 3, 0),
            product_version=(2, 0, 3, 0),
            machine=0x8664,
        )
        pkg_arg = self.tmp_path / "octi-setup-2.0.3.exe"
        out_arg = self.tmp_path / "out-version.json"
        pkg_arg.write_bytes(pe_bytes)

        rc = main([
            "--package", str(pkg_arg),
            "--slug", "octi",
            "--output", str(out_arg),
        ])
        self.assertEqual(rc, 0)
        import json
        manifest = json.loads(out_arg.read_text(encoding="utf-8"))
        self.assertEqual(manifest["slug"], "octi")
        self.assertEqual(manifest["title"], "OCTI Desktop Player")
        self.assertEqual(manifest["versionName"], "2.0.3")
        self.assertEqual(manifest["versionCode"], 20003)
        self.assertEqual(manifest["installType"], "installer")

    def test_normalize_version_name(self):
        self.assertEqual(normalize_version_name("1.2.3.0"), "1.2.3")
        self.assertEqual(normalize_version_name("2.0.3"), "2.0.3")
        self.assertEqual(normalize_version_name("v3.1.4"), "3.1.4")
        self.assertEqual(normalize_version_name("V1.0.5"), "1.0.5")
        self.assertEqual(normalize_version_name(None, None, "octi-setup-2.0.3.exe"), "2.0.3")
        self.assertEqual(normalize_version_name(None, None, "aimon-setup-1.2.3.exe"), "1.2.3")
        self.assertEqual(normalize_version_name(None, None, "app.exe"), "1.0.0")

    def test_compute_version_code(self):
        self.assertEqual(compute_version_code("1.2.3"), 10203)
        self.assertEqual(compute_version_code("2.0.3"), 20003)
        self.assertEqual(compute_version_code("1.10.2"), 11002)
        self.assertEqual(compute_version_code("0.5.1"), 501)
        self.assertEqual(compute_version_code("1.0.0", explicit_code=99999), 99999)

    def test_detect_install_type(self):
        self.assertEqual(detect_install_type("octi-setup.exe"), "installer")
        self.assertEqual(detect_install_type("aimon-install-1.0.exe"), "installer")
        self.assertEqual(detect_install_type("robohero_teleop.exe"), "binary")
        self.assertEqual(detect_install_type("app.exe", explicit_type="installer"), "installer")
        self.assertEqual(detect_install_type("setup.exe", explicit_type="binary"), "binary")

    def test_non_pe_and_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            generate_manifest(self.tmp_path / "nonexistent.exe")

        text_file = self.tmp_path / "test.txt"
        text_file.write_text("Hello, this is not a PE file.")
        self.assertEqual(parse_pe_metadata(text_file), {})
        manifest = generate_manifest(text_file, slug="my-app", version_name="1.5.0")
        self.assertEqual(manifest["slug"], "my-app")
        self.assertEqual(manifest["versionName"], "1.5.0")
        self.assertEqual(manifest["versionCode"], 10500)


if __name__ == "__main__":
    unittest.main()
