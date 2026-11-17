#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Mac ARJ contributors.
"""Generate tiny, deterministic, stored-method ARJ fixtures using only stdlib.

Provenance: these bytes are generated from scratch, not copied from a user's
archive or a downloaded fixture. Header layout was cross-checked against
7-Zip's public CPP/7zip/Archive/ArjHandler.cpp (ip7z/7zip). The fixed header is
30 bytes, version 3/minimum extractor 1, DOS host, method 0, and binary files.
Every basic header and file body has an independently computed CRC32; extended
headers are absent and the archive ends in 60 EA 00 00. Timestamps are fixed.

Flag fixtures are deliberately synthetic unsupported-input probes: setting the
garbled or split-after bit does NOT implement encryption or a real volume set.
No external tools, network access, or third-party Python packages generate data.
"""

import argparse
from pathlib import Path
import struct
import zlib

SIGNATURE = b"\x60\xea"
FIRST_HEADER_SIZE = 30
DOS_TIME = 0x58210000  # 2024-01-01 00:00:00, independent of local time zone.
DEFAULT_FILES = {
    "hello.txt": b"Hello from the deterministic Mac ARJ fixture!\n",
    "nested/with spaces.txt": b"A nested file with spaces.\n",
    "bytes.bin": bytes(range(256)),
    "empty.txt": b"",
}


def _block(header):
    return (SIGNATURE + struct.pack("<H", len(header)) + header
            + struct.pack("<I", zlib.crc32(header) & 0xFFFFFFFF) + b"\0\0")


def archive_bytes(files=None, *, file_flags=0, main_flags=0, corrupt_crc=False):
    """Return an ARJ byte string; mapping insertion order determines file order.

    Names are ASCII on purpose: ARJ has no universal UTF-8 filename convention.
    Korean names are tested on the outer archive's filesystem name instead.
    Unsafe member names are accepted here exclusively to make rejection tests.
    corrupt_crc changes the first member's advertised data CRC but recomputes
    its header CRC, isolating a real body-CRC failure from header corruption.
    """
    if files is None:
        files = DEFAULT_FILES
    main = struct.pack("<8B4I3H", FIRST_HEADER_SIZE, 3, 1, 0, main_flags,
                       0, 2, 0, DOS_TIME, DOS_TIME, 0, 0, 0, 0, 0)
    result = bytearray(_block(main + b"fixture.arj\0\0"))
    for index, (name, data) in enumerate(files.items()):
        encoded = name.encode("ascii")
        if b"\0" in encoded:
            raise ValueError("ARJ member names cannot contain NUL")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        if corrupt_crc and index == 0:
            crc ^= 1
        header = struct.pack("<8B4I3H", FIRST_HEADER_SIZE, 3, 1, 0,
                             file_flags, 0, 0, 0, DOS_TIME, len(data),
                             len(data), crc, 0, 0x20, 0)
        result.extend(_block(header + encoded + b"\0\0"))
        result.extend(data)
    result.extend(SIGNATURE + b"\0\0")
    return bytes(result)


def write_fixture(path, files=None, **kwargs):
    """Write only the explicitly supplied output file and return its Path."""
    path = Path(path)
    path.write_bytes(archive_bytes(files, **kwargs))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new .arj file to generate")
    parser.add_argument("--corrupt-crc", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite an existing file")
    write_fixture(args.output, corrupt_crc=args.corrupt_crc)
    print(args.output)


if __name__ == "__main__":
    main()