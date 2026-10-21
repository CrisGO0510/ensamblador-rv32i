import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Final

from rvasm.cli import AsmResult, assemble_lines, pack_words

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
ASSEMBLER: Final[str] = str(ROOT / "assembler.py")

SUMA: Final[str] = """# Suma 10 + 9 + ... + 1 en a1
        .text
main:   li   a0, 10        # contador
        li   a1, 0         # acumulador
loop:   beqz a0, end
        add  a1, a1, a0
        addi a0, a0, -1
        j    loop
end:    j    end
"""

SUMA_WORDS: Final[list[str]] = ["00a00513", "00000593", "00050863", "00a585b3", "fff50513", "ff5ff06f", "0000006f"]

DRAWING: Final[str] = """.data
n:   .word 5
msg: .string "hi"
.text
main: la   a0, msg
      lw   a1, n
      li   a2, 0x12345FFF
loop: beqz a1, end
      j    loop
end:  j    end
"""

ERRORES: Final[str] = """addi x1, x2, x3
addi x1, x2, 4096
addi x1, x2, 0x7FF
slli x1, x2, 32
beq  x1, x2, nowhere
"""

ONLY_DATA: Final[str] = ".data\n.word 1\n"

DIAGNOSTIC_RE: Final[re.Pattern[str]] = re.compile(r"^errores\.asm:(\d+): error: ")


def run_cli(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    # cwd en el temporal para que las rutas relativas lleguen tal cual a los diagnósticos
    return subprocess.run([sys.executable, ASSEMBLER, *args], capture_output=True, text=True, cwd=cwd)


class PackWordsTest(unittest.TestCase):
    def test_packs_little_endian_and_pads_with_zeros(self) -> None:
        # Arrange
        cases: list[tuple[bytes, list[str]]] = [
            (bytes(range(0x61, 0x6B)), ["64636261", "68676665", "00006a69"]),
            (bytes([1, 2, 3, 4, 5, 6]), ["04030201", "00000605"]),
            (b"", []),
        ]
        case: tuple[bytes, list[str]]
        for case in cases:
            with self.subTest(data=case[0]):
                # Act
                words: list[str] = pack_words(case[0])

                # Assert
                self.assertEqual(words, case[1])


class AssembleLinesTest(unittest.TestCase):
    def test_suma_matches_reference_words(self) -> None:
        # Arrange
        lines: list[str] = SUMA.splitlines()

        # Act
        result: AsmResult = assemble_lines(lines)

        # Assert
        self.assertEqual(pack_words(result.image.text), SUMA_WORDS)
        self.assertEqual(result.errors, [])

    def test_error_file_reports_lines_1_2_4_5(self) -> None:
        # Arrange
        lines: list[str] = ERRORES.splitlines()
        keywords: list[str] = ["inmediato", "fuera de rango [-2048, 2047]", "fuera de rango [0, 31]", "no definida"]

        # Act
        result: AsmResult = assemble_lines(lines)

        # Assert
        self.assertEqual([d.line for d in result.errors], [1, 2, 4, 5])
        index: int
        for index in range(len(keywords)):
            self.assertIn(keywords[index], result.errors[index].msg)

    def test_errors_sorted_by_line_across_passes(self) -> None:
        # Arrange
        lines: list[str] = ["j nowhere", "mul x0,x0,x0"]

        # Act
        result: AsmResult = assemble_lines(lines)

        # Assert
        self.assertEqual([d.line for d in result.errors], [1, 2])

    def test_crlf_bom_and_missing_final_newline_assemble_the_same(self) -> None:
        # Arrange
        clean: bytes = assemble_lines(SUMA.splitlines()).image.text
        variants: list[bytes] = [
            SUMA.replace("\n", "\r\n").encode("utf-8"),
            ("﻿" + SUMA).encode("utf-8"),
            SUMA.rstrip("\n").encode("utf-8"),
        ]
        raw: bytes
        for raw in variants:
            with self.subTest(raw=raw[:8]):
                # Act
                result: AsmResult = assemble_lines(raw.decode("utf-8-sig").splitlines())

                # Assert
                self.assertEqual(result.image.text, clean)
                self.assertEqual(result.errors, [])

    def test_empty_file_gives_empty_image(self) -> None:
        # Arrange
        lines: list[str] = []

        # Act
        result: AsmResult = assemble_lines(lines)

        # Assert
        self.assertEqual(result.image.text, b"")
        self.assertEqual(result.errors, [])

    def test_only_data_gives_empty_text(self) -> None:
        # Arrange
        lines: list[str] = ONLY_DATA.splitlines()

        # Act
        result: AsmResult = assemble_lines(lines)

        # Assert
        self.assertEqual(result.image.text, b"")
        self.assertEqual(result.image.data, bytes([1, 0, 0, 0]))
        self.assertEqual(result.errors, [])


class MainEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir: Path = Path(self.tmp.name)

    def test_suma_writes_exact_hex_and_no_data_file(self) -> None:
        # Arrange
        (self.dir / "suma.asm").write_text(SUMA, encoding="utf-8")

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["suma.asm", "suma.hex"])

        # Assert
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "")
        self.assertEqual((self.dir / "suma.hex").read_text(encoding="utf-8"), "".join(w + "\n" for w in SUMA_WORDS))
        self.assertEqual(list(self.dir.glob("*.data.hex")), [])

    def test_drawing_writes_data_hex(self) -> None:
        # Arrange
        (self.dir / "dibujo.asm").write_text(DRAWING, encoding="utf-8")

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["dibujo.asm", "dibujo.hex", "dibujo.data.hex"])

        # Assert
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual((self.dir / "dibujo.data.hex").read_text(encoding="utf-8"), "00000005\n00006968\n")

    def test_errors_exit_1_with_diagnostics_and_remove_stale_outputs(self) -> None:
        # Arrange
        (self.dir / "errores.asm").write_text(ERRORES, encoding="utf-8")
        (self.dir / "errores.hex").write_text("basura\n", encoding="utf-8")
        (self.dir / "errores.data.hex").write_text("basura\n", encoding="utf-8")

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(
            self.dir, ["errores.asm", "errores.hex", "errores.data.hex"]
        )

        # Assert
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        stderr_lines: list[str] = proc.stderr.splitlines()
        self.assertEqual(len(stderr_lines), 4, proc.stderr)
        line_numbers: list[str] = []
        line: str
        for line in stderr_lines:
            match: re.Match[str] | None = DIAGNOSTIC_RE.match(line)
            line_numbers.append(match.group(1) if match else line)
        self.assertEqual(line_numbers, ["1", "2", "4", "5"])
        self.assertFalse((self.dir / "errores.hex").exists())
        self.assertFalse((self.dir / "errores.data.hex").exists())

    def test_wrong_argument_count_exits_2_with_usage(self) -> None:
        # Arrange
        cases: list[list[str]] = [[], ["a.asm"], ["a.asm", "a.hex", "a.data.hex", "extra"]]
        args: list[str]
        for args in cases:
            with self.subTest(args=args):
                # Act
                proc: subprocess.CompletedProcess[str] = run_cli(self.dir, args)

                # Assert
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, "")
                self.assertTrue(proc.stderr.startswith("uso: python assembler.py programa.asm programa.hex"))

    def test_missing_input_exits_2(self) -> None:
        # Arrange
        args: list[str] = ["noexiste.asm", "noexiste.hex"]

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, args)

        # Assert
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("no se puede leer 'noexiste.asm'", proc.stderr)
        self.assertFalse((self.dir / "noexiste.hex").exists())

    def test_only_data_exits_0_with_empty_hex(self) -> None:
        # Arrange
        (self.dir / "datos.asm").write_text(ONLY_DATA, encoding="utf-8")

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["datos.asm", "datos.hex"])

        # Assert
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual((self.dir / "datos.hex").read_bytes(), b"")

    def test_non_utf8_input_exits_2_without_traceback(self) -> None:
        # Arrange
        (self.dir / "binario.asm").write_bytes(b"addi x1, x0, 1\n\xff\n")

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["binario.asm", "binario.hex"])

        # Assert
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "assembler.py: error: no se puede leer 'binario.asm': no es UTF-8 válido\n")

    def test_output_equal_to_input_exits_2_and_keeps_input(self) -> None:
        # Arrange
        (self.dir / "same.asm").write_text(ERRORES, encoding="utf-8")

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["same.asm", "same.asm"])

        # Assert
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "assembler.py: error: la salida 'same.asm' es el mismo archivo que la entrada\n")
        self.assertEqual((self.dir / "same.asm").read_text(encoding="utf-8"), ERRORES)

    def test_form_feed_does_not_split_lines(self) -> None:
        # Arrange
        (self.dir / "errores.asm").write_text("nop # a\x0cb\nmul a0, a1, a2\n", encoding="utf-8")

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["errores.asm", "out.hex"])

        # Assert
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "errores.asm:2: error: instrucción inválida 'mul'\n")

    def test_same_file_for_both_outputs_exits_2_and_touches_nothing(self) -> None:
        # Arrange
        (self.dir / "suma.asm").write_text(SUMA, encoding="utf-8")
        (self.dir / "x.hex").write_text("viejo\n", encoding="utf-8")

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["suma.asm", "x.hex", "./x.hex"])

        # Assert
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "assembler.py: error: las salidas 'x.hex' y './x.hex' son el mismo archivo\n")
        self.assertEqual((self.dir / "x.hex").read_text(encoding="utf-8"), "viejo\n")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["suma.asm", "x.hex"])

    def test_failed_removal_of_stale_output_exits_2_after_diagnostics(self) -> None:
        # Arrange
        (self.dir / "errores.asm").write_text(ERRORES, encoding="utf-8")
        (self.dir / "salida.hex").mkdir()

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["errores.asm", "salida.hex"])

        # Assert
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertNotIn("Traceback", proc.stderr)
        stderr_lines: list[str] = proc.stderr.splitlines()
        self.assertEqual(len([l for l in stderr_lines if DIAGNOSTIC_RE.match(l)]), 4, proc.stderr)
        self.assertIn("assembler.py: error: no se puede borrar 'salida.hex': ", proc.stderr)

    def test_failed_data_write_removes_fresh_hex(self) -> None:
        # Arrange
        (self.dir / "dibujo.asm").write_text(DRAWING, encoding="utf-8")
        (self.dir / "dibujo.data.hex").mkdir()

        # Act
        proc: subprocess.CompletedProcess[str] = run_cli(self.dir, ["dibujo.asm", "dibujo.hex", "dibujo.data.hex"])

        # Assert
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("assembler.py: error: no se puede escribir 'dibujo.data.hex': ", proc.stderr)
        self.assertFalse((self.dir / "dibujo.hex").exists())
