import re
import unittest

from rvasm.lexer import tokenize
from rvasm.model import AsmError, Operand, Statement
from rvasm.parser import parse


class ParseStatementTest(unittest.TestCase):
    def test_statements(self) -> None:
        # Arrange
        cases: list[tuple[int, str, Statement]] = [
            (8, "loop: beqz a1, end", Statement(8, ("loop",), "beqz", (Operand("reg", 11), Operand("sym", "end")))),
            (1, "a: b: nop", Statement(1, ("a", "b"), "nop", ())),
            (1, "solo:", Statement(1, ("solo",), None, ())),
            (1, "", Statement(1, (), None, ())),
            (1, "LW A0, 8(sp)", Statement(1, (), "lw", (Operand("sym", "A0"), Operand("mem", 8, 2)))),
            (1, "lw a0, (sp)", Statement(1, (), "lw", (Operand("reg", 10), Operand("mem", 0, 2)))),
            (1, "lw a0, 0 ( sp )", Statement(1, (), "lw", (Operand("reg", 10), Operand("mem", 0, 2)))),
            (1, "lw a0, -4(s0)", Statement(1, (), "lw", (Operand("reg", 10), Operand("mem", -4, 8)))),
            (
                1,
                ".WORD 1, 0x10, -1",
                Statement(1, (), ".word", (Operand("num", 1), Operand("num", 16), Operand("num", -1))),
            ),
            (1, "j 8", Statement(1, (), "j", (Operand("num", 8),))),
        ]
        case: tuple[int, str, Statement]
        for case in cases:
            with self.subTest(line=case[1]):
                # Act
                statement: Statement = parse(case[0], tokenize(case[1]))

                # Assert
                self.assertEqual(statement, case[2])

    def test_strings(self) -> None:
        # Arrange
        cases: list[tuple[str, tuple[Operand, ...]]] = [
            ('.string "hi"', (Operand("str", b"hi"),)),
            ('.string "a", "b"', (Operand("str", b"a"), Operand("str", b"b"))),
            ('.string "a#b"  # c', (Operand("str", b"a#b"),)),
            ('.string "a, b"', (Operand("str", b"a, b"),)),
            (r'.string "a\tb\n\"q\"\\ AA"', (Operand("str", b'a\tb\n"q"\\ AA'),)),
            ('.string "ñ"', (Operand("str", b"\xc3\xb1"),)),
            (r'.string "\r"', (Operand("str", b"\r"),)),
        ]
        case: tuple[str, tuple[Operand, ...]]
        for case in cases:
            with self.subTest(line=case[0]):
                # Act
                args: tuple[Operand, ...] = parse(1, tokenize(case[0])).args

                # Assert
                self.assertEqual(args, case[1])

    def test_syntax_errors(self) -> None:
        # Arrange
        cases: list[tuple[str, str]] = [
            ("lw a0, 0(foo)", "registro inexistente 'foo'"),
            ("lw a0, 0(a1", "línea mal formada cerca de '('"),
            ("addi a0 a0 1", "línea mal formada cerca de 'a0'"),
            ("addi a0,,1", "línea mal formada cerca de ','"),
            ("addi a0, a0, 1,", "línea mal formada cerca de ','"),
            ("addi ,a0", "línea mal formada cerca de ','"),
            (r'.string "a\qb"', r"secuencia de escape desconocida '\q'"),
            (r'.string "\x41"', r"secuencia de escape desconocida '\x'"),
            (r'.string "\8"', r"secuencia de escape desconocida '\8'"),
            (r'.string "\0"', r"secuencia de escape desconocida '\0'"),
        ]
        case: tuple[str, str]
        for case in cases:
            with self.subTest(line=case[0]):
                # Act
                # Assert
                with self.assertRaisesRegex(AsmError, f"^{re.escape(case[1])}$"):
                    parse(1, tokenize(case[0]))
