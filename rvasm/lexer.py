import re
from typing import Final

from rvasm.model import AsmError, Token, TokenKind

TOKEN_SPEC: Final[list[tuple[str, str]]] = [
    ("COMMENT", r"#.*"),
    ("STRING", r'"(?:[^"\\]|\\.)*"'),
    ("NUM", r"[+-]?(?:0[xX][0-9a-fA-F]+|0[bB][01]+|[0-9]+)"),
    ("IDENT", r"[A-Za-z_.$][A-Za-z0-9_.$]*"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("COMMA", r","),
    ("COLON", r":"),
    ("WS", r"[ \t]+"),
    ("MISMATCH", r"."),
]


TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    "|".join("(?P<%s>%s)" % pair for pair in TOKEN_SPEC)
)

DEC_DIGITS: Final[str] = "0123456789"
HEX_DIGITS: Final[str] = "0123456789abcdefABCDEF"
BIN_DIGITS: Final[str] = "01"


def tokenize(line: str) -> list[Token]:
    tokens: list[Token] = []
    mo: re.Match[str]
    for mo in TOKEN_RE.finditer(line):
        group: str | None = mo.lastgroup
        text: str = mo.group()
        if group == "MISMATCH":
            raise AsmError(
                "cadena sin cerrar" if text == '"' else f"carácter inesperado '{text}'"
            )
        if group is not None and group in TokenKind.__members__:
            tokens.append(Token(TokenKind[group], text))
    return tokens


def digits_in(text: str, allowed: str) -> bool:
    return text != "" and all(c in allowed for c in text)


def is_hex(body: str) -> bool:
    return body[:2] in ("0x", "0X") and digits_in(body[2:], HEX_DIGITS)


def is_bin(body: str) -> bool:
    return body[:2] in ("0b", "0B") and digits_in(body[2:], BIN_DIGITS)


def is_dec(body: str) -> bool:
    return digits_in(body, DEC_DIGITS)


def parse_num(text: str) -> int:
    sign: int = -1 if text[:1] == "-" else 1
    body: str = text[1:] if text[:1] in ("+", "-") else text
    if is_hex(body):
        return sign * int(body[2:], 16)
    if is_bin(body):
        return sign * int(body[2:], 2)
    if is_dec(body):
        return sign * int(body, 10)
    raise AsmError(f"inmediato inválido '{text}'")
