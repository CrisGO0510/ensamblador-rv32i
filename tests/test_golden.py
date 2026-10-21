import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
ASSEMBLER: Final[str] = str(ROOT / "assembler.py")
OK_DIR: Final[Path] = ROOT / "tests" / "ok"
ERR_DIR: Final[Path] = ROOT / "tests" / "err"
EXPECT_RE: Final[re.Pattern[str]] = re.compile(r"(\d+):(\S.*)")


class GoldenTest(unittest.TestCase):
    def test_ok(self) -> None:
        # Arrange
        sources: list[Path] = sorted(OK_DIR.glob("*.asm"))
        self.assertTrue(sources)
        source: Path
        for source in sources:
            with self.subTest(name=source.stem):
                # Arrange
                expected_text: str = source.with_suffix(".hex").read_text(encoding="utf-8")
                expected_data_path: Path = source.with_suffix(".data.hex")
                expected_data: str = (
                    expected_data_path.read_text(encoding="utf-8") if expected_data_path.exists() else ""
                )
                tmp: str
                with tempfile.TemporaryDirectory() as tmp:
                    out_hex: Path = Path(tmp) / "out.hex"
                    out_data: Path = Path(tmp) / "out.data.hex"

                    # Act
                    proc: subprocess.CompletedProcess[str] = subprocess.run(
                        [sys.executable, ASSEMBLER, str(source), str(out_hex), str(out_data), "--listado"],
                        capture_output=True,
                        text=True,
                    )

                    # Assert
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(out_hex.read_text(encoding="utf-8"), expected_text)
                    self.assertEqual(out_data.read_text(encoding="utf-8"), expected_data)
                    rows: int = len((Path(tmp) / "out.md").read_text(encoding="utf-8").splitlines()) - 2
                    self.assertEqual(rows, len(expected_text.splitlines()))

    def test_err(self) -> None:
        # Arrange
        sources: list[Path] = sorted(ERR_DIR.glob("*.asm"))
        self.assertTrue(sources)
        source: Path
        for source in sources:
            with self.subTest(name=source.stem):
                # Arrange
                expected: dict[int, list[str]] = {}
                entry: str
                for entry in source.with_suffix(".expect").read_text(encoding="utf-8").splitlines():
                    entry_match: re.Match[str] | None = EXPECT_RE.fullmatch(entry)
                    if entry_match is None:
                        self.fail(f"{source.stem}.expect: línea mal escrita {entry!r}, se espera 'N:palabra'")
                    expected.setdefault(int(entry_match.group(1)), []).append(entry_match.group(2))
                diagnostic_re: re.Pattern[str] = re.compile(rf"{re.escape(source.name)}:(\d+): error: (.*)")
                tmp: str
                with tempfile.TemporaryDirectory() as tmp:
                    shutil.copy(source, tmp)

                    # Act
                    proc: subprocess.CompletedProcess[str] = subprocess.run(
                        [sys.executable, ASSEMBLER, source.name, "out.hex", "out.data.hex"],
                        capture_output=True,
                        text=True,
                        cwd=tmp,
                    )

                    # Assert
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), [source.name])
                found: dict[int, list[str]] = {}
                stderr_line: str
                for stderr_line in proc.stderr.splitlines():
                    if not stderr_line:
                        continue
                    match: re.Match[str] | None = diagnostic_re.fullmatch(stderr_line)
                    if match is None:
                        self.fail(f"línea de stderr que no es un diagnóstico: {stderr_line!r}\n{proc.stderr}")
                    found.setdefault(int(match.group(1)), []).append(match.group(2))
                self.assertEqual(sorted(found), sorted(expected), proc.stderr)
                line: int
                for line in expected:
                    self.assertEqual(len(found[line]), len(expected[line]), proc.stderr)
                    keyword: str
                    for keyword in expected[line]:
                        self.assertTrue(any(keyword in m for m in found[line]), f"{line}:{keyword}\n{proc.stderr}")
