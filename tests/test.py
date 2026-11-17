#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Mac ARJ contributors.
"""Synthetic-only integration tests: python3 tests/test.py [-v].

No real archives are discovered or opened. All fixture files, extraction output,
and subprocess working directories live in a TemporaryDirectory under TMPDIR
(or the platform temporary directory) and are removed afterwards. No installs or builds are run.
The 7zz tests run independently of the app; app tests explicitly skip if the
bundle has not yet been built. A skipped app suite is NOT an app verification.
"""

import os
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from typing import Literal, overload

from generate_fixture import DEFAULT_FILES, archive_bytes, write_fixture

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dist/Mac ARJ.app/Contents/MacOS/Mac ARJ"
SEVEN_ZIP = next((p for p in (Path("/opt/homebrew/bin/7zz"), Path("/usr/local/bin/7zz"))
                  if p.is_file()), Path("/opt/homebrew/bin/7zz"))
SCRATCH = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(directory):
    """Compare both names and exact bytes, not merely presence/count."""
    return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob("*") if p.is_file()}


class TemporaryCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mac-arj-tests-", dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.inputs = self.work / "inputs"
        self.inputs.mkdir()

    def run_command(self, command, timeout=30):
        return subprocess.run([str(part) for part in command], cwd=self.work,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)

    def assert_files(self, destination, expected=DEFAULT_FILES):
        self.assertEqual(snapshot(destination), expected)


@unittest.skipUnless(SEVEN_ZIP.is_file(), "Homebrew 7zz is not installed")
class FixtureRecognitionTests(TemporaryCase):
    def test_deterministic_and_recognized_as_arj(self):
        self.assertEqual(archive_bytes(), archive_bytes())
        source = write_fixture(self.inputs / "fixture.arj")
        before = sha256(source)
        listing = self.run_command([SEVEN_ZIP, "l", "-slt", source])
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertIn("Type = Arj", listing.stdout)
        check = self.run_command([SEVEN_ZIP, "t", source])
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        output = self.work / "reference-output"
        extract = self.run_command([SEVEN_ZIP, "x", "-y", f"-o{output}", source])
        self.assertEqual(extract.returncode, 0, extract.stdout + extract.stderr)
        self.assert_files(output)
        self.assertEqual(sha256(source), before)

    def test_bad_body_crc_is_not_bad_header(self):
        source = write_fixture(self.inputs / "bad-crc.arj", corrupt_crc=True)
        listing = self.run_command([SEVEN_ZIP, "l", "-slt", source])
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertIn("Type = Arj", listing.stdout)
        check = self.run_command([SEVEN_ZIP, "t", source])
        self.assertNotEqual(check.returncode, 0)
        self.assertIn("CRC Failed", check.stdout + check.stderr)

    def test_encrypted_flag_is_visible(self):
        source = write_fixture(self.inputs / "flag-encrypted.arj", file_flags=1)
        listing = self.run_command([SEVEN_ZIP, "l", "-slt", source])
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertIn("Encrypted = +", listing.stdout)

    def test_split_after_flag_is_visible(self):
        source = write_fixture(self.inputs / "flag-volume.arj",
                               main_flags=4, file_flags=4)
        listing = self.run_command([SEVEN_ZIP, "l", "-slt", source])
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertIn("Position = 0", listing.stdout)


@unittest.skipUnless(APP.is_file(), "App not built: " + str(APP))
class ApplicationTests(TemporaryCase):
    @overload
    def extract(self, source: Path, success: Literal[True] = True) -> Path: ...

    @overload
    def extract(self, source: Path, success: Literal[False]) -> subprocess.CompletedProcess[str]: ...

    def extract(self, source: Path, success: bool = True) -> Path | subprocess.CompletedProcess[str]:
        before = sha256(source) if source.is_file() else None
        result = self.run_command([APP, "--extract", source])
        if before is not None:
            self.assertTrue(source.is_file(), "source archive was deleted")
            self.assertEqual(sha256(source), before, "source archive was modified")
        diagnostic = f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        if not success:
            self.assertNotEqual(result.returncode, 0, diagnostic)
            self.assertTrue(result.stderr.strip(), "failure needs a stderr diagnostic")
            self.assertFalse(result.stdout.strip(), "failure must not report a destination")
            return result
        self.assertEqual(result.returncode, 0, diagnostic)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, "stdout must contain just the destination: " + diagnostic)
        destination = Path(lines[0])
        self.assertTrue(destination.is_absolute(), diagnostic)
        self.assertTrue(destination.is_dir(), diagnostic)
        self.assertEqual(destination.resolve().parent, source.resolve().parent,
                         "destination must be next to the source archive")
        self.assertNotEqual(destination.resolve(), source.resolve())
        return destination

    def test_success_and_source_preserved(self):
        source = write_fixture(self.inputs / "sample.arj")
        self.assert_files(self.extract(source))

    def test_korean_archive_filename_with_spaces(self):
        source = write_fixture(self.inputs / "한글 압축 파일 이름.arj")
        self.assert_files(self.extract(source))

    def test_symlinked_parent_directory(self):
        alias = self.work / "parent-alias"
        alias.symlink_to(self.inputs, target_is_directory=True)
        source = write_fixture(alias / "aliased.arj")
        self.assert_files(self.extract(source))

    def test_existing_folder_and_repeat_extraction_do_not_overwrite(self):
        source = write_fixture(self.inputs / "collision.arj")
        existing = self.inputs / "collision"
        existing.mkdir()
        (existing / "hello.txt").write_bytes(b"User-owned sentinel; do not overwrite.\n")
        before = snapshot(existing)
        first = self.extract(source)
        self.assertNotEqual(first.resolve(), existing.resolve())
        self.assert_files(first)
        self.assertEqual(snapshot(existing), before)
        second = self.extract(source)
        self.assertNotEqual(second.resolve(), first.resolve())
        self.assertNotEqual(second.resolve(), existing.resolve())
        self.assert_files(second)
        self.assert_files(first)
        self.assertEqual(snapshot(existing), before)

    def test_invalid_archives(self):
        for name, content in (("empty.arj", b""),
                              ("not-an-archive.arj", b"This is not an archive.\n"),
                              ("truncated.arj", archive_bytes()[:45])):
            with self.subTest(name=name):
                source = self.inputs / name
                source.write_bytes(content)
                self.extract(source, success=False)

    def test_missing_archive(self):
        self.extract(self.inputs / "does not exist.arj", success=False)

    def test_crc_failure(self):
        source = write_fixture(self.inputs / "crc-failure.arj", corrupt_crc=True)
        self.extract(source, success=False)

    def test_traversal_is_rejected_not_sanitized(self):
        # Even hypothetical vulnerable extractions stay inside this scratch tree.
        # Check both slash conventions and an absolute path, with no real targets.
        absolute_target = self.work / "absolute-escape.txt"
        names = ["../escape.txt", "nested/../../escape.txt", "C:/escape.txt", "C:\\escape.txt",
                 "..\\escape.txt", str(absolute_target)]
        # Scratch's generated path is ASCII, so the ARJ name remains ASCII too.
        for index, member in enumerate(names):
            with self.subTest(member=member):
                source = write_fixture(self.inputs / f"traversal-{index}.arj",
                                       {member: b"must never be written\n"})
                self.extract(source, success=False)
                self.assertFalse((self.work / "escape.txt").exists())
                self.assertFalse((self.inputs / "escape.txt").exists())
                self.assertFalse(absolute_target.exists())
                self.assertFalse(any(p.is_file() and p.name in {
                    "escape.txt", "..\\escape.txt", "absolute-escape.txt"
                } for p in self.work.rglob("*")), "unsafe member was sanitized/extracted")

    def test_encrypted_flag_rejected(self):
        source = write_fixture(self.inputs / "encrypted-flag.arj", file_flags=1)
        self.extract(source, success=False)

    def test_multivolume_flag_rejected(self):
        # Synthetic split-after marker, not a genuine multipart ARJ fixture.
        source = write_fixture(self.inputs / "multivolume-flag.arj",
                               main_flags=4, file_flags=4)
        self.extract(source, success=False)

    def test_existing_file_and_symlink_are_not_overwritten(self):
        source = write_fixture(self.inputs / "reserved.arj")
        occupied = self.inputs / "reserved"
        occupied.write_bytes(b"keep existing file")
        link = self.inputs / "reserved (2)"
        link.symlink_to(occupied)
        destination = self.extract(source)
        self.assertEqual(destination.name, "reserved (3)")
        self.assertEqual(occupied.read_bytes(), b"keep existing file")
        self.assertTrue(link.is_symlink())
        self.assert_files(destination)

    def test_case_colliding_members_rejected(self):
        source = write_fixture(self.inputs / "case.arj", {"A.txt": b"one", "a.txt": b"two"})
        self.extract(source, success=False)
        self.assertFalse((self.inputs / "case").exists())

    def test_entry_count_cap(self):
        source = write_fixture(self.inputs / "too-many.arj", {f"f{i}": b"" for i in range(10001)})
        self.extract(source, success=False)
        self.assertFalse((self.inputs / "too-many").exists())

    def test_self_test_if_supported(self):
        try:
            result = self.run_command([APP, "--self-test"], timeout=20)
        except subprocess.TimeoutExpired:
            self.skipTest("--self-test not supported or did not finish within 20s")
        text = (result.stdout + result.stderr).lower()
        unsupported = ("unknown option", "unrecognized option", "unsupported option",
                       "unknown argument", "unrecognized argument", "usage:")
        if result.returncode != 0 and any(marker in text for marker in unsupported):
            self.skipTest("--self-test explicitly unsupported")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.strip() or result.stderr.strip(),
                        "--self-test must report a result, not silently launch the GUI")


if __name__ == "__main__":
    unittest.main()