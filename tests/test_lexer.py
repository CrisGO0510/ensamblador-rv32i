import unittest

from rvasm.lexer import parse_num, tokenize
from rvasm.model import AsmError, Token


class TokenizeTest(unittest.TestCase):
    def test_token_kinds_and_texts(self) -> None:
        # Arrange
        cases: list[tuple[str, list[str], list[str]]] = [
            (
                "loop: beqz a1, end  # salto",
                ["IDENT", "COLON", "IDENT", "IDENT", "COMMA", "IDENT"],
                ["loop", ":", "beqz", "a1", ",", "end"],
            ),
            (
                "lw a0, 8(sp)",
                ["IDENT", "IDENT", "COMMA", "NUM", "LPAREN", "IDENT", "RPAREN"],
                ["lw", "a0", ",", "8", "(", "sp", ")"],
            ),
            ('.string "a#b"  # c', ["IDENT", "STRING"], [".string", '"a#b"']),
        ]
        case: tuple[str, list[str], list[str]]
        for case in cases:
            with self.subTest(line=case[0]):
                # Act
                tokens: list[Token] = tokenize(case[0])

                # Assert
                self.assertEqual([t.kind for t in tokens], case[1])
                self.assertEqual([t.text for t in tokens], case[2])

    def test_blank_and_comment_lines_are_empty(self) -> None:
        # Arrange
        lines: list[str] = ["", "\t # x", "   # solo comentario"]
        line: str
        for line in lines:
            with self.subTest(line=line):
                # Act
                tokens: list[Token] = tokenize(line)

                # Assert
                self.assertEqual(tokens, [])

    def test_lexical_errors(self) -> None:
        # Arrange
        cases: list[tuple[str, str]] = [
            ("addi a0, a0, @", "carácter inesperado '@'"),
            ('.string "abc', "cadena sin cerrar"),
        ]
        case: tuple[str, str]
        for case in cases:
            with self.subTest(line=case[0]):
                # Act
                # Assert
                with self.assertRaisesRegex(AsmError, f"^{case[1]}$"):
                    tokenize(case[0])


class ParseNumTest(unittest.TestCase):
    def test_valid_numbers(self) -> None:
        # Arrange
        cases: list[tuple[str, int]] = [
            ("42", 42), ("-12", -12), ("+5", 5), ("0xFF", 255), ("0XfF", 255),
            ("-0x10", -16), ("0b1010", 10), ("0B101", 5), ("0", 0), ("-0", 0),
            ("00", 0), ("010", 10), ("08", 8), ("-08", -8),
        ]
        case: tuple[str, int]
        for case in cases:
            with self.subTest(text=case[0]):
                # Act
                value: int = parse_num(case[0])

                # Assert
                self.assertEqual(value, case[1])

    def test_invalid_numbers(self) -> None:
        # Arrange
        texts: list[str] = ["1_000", "0x", "1.5", "٣", " 5", "0x_1"]
        text: str
        for text in texts:
            with self.subTest(text=text):
                # Act
                # Assert
                with self.assertRaisesRegex(AsmError, "inmediato inválido"):
                    parse_num(text)

    def test_invalid_message_quotes_the_text(self) -> None:
        # Arrange
        text: str = "1.5"

        # Act
        # Assert
        with self.assertRaisesRegex(AsmError, "^inmediato inválido '1\\.5'$"):
            parse_num(text)
