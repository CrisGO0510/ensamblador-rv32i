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
TOKEN_RE: Final[re.Pattern[str]] = re.compile("|".join("(?P<%s>%s)" % pair for pair in TOKEN_SPEC))
KINDS: Final[dict[str, TokenKind]] = {
    "STRING": "STRING",
    "NUM": "NUM",
    "IDENT": "IDENT",
    "LPAREN": "LPAREN",
    "RPAREN": "RPAREN",
    "COMMA": "COMMA",
    "COLON": "COLON",
}
NUM_RE: Final[re.Pattern[str]] = re.compile(r"([+-]?)(0[xX][0-9a-fA-F]+|0[bB][01]+|[0-9]+)", re.ASCII)


def tokenize(line: str) -> list[Token]:
    tokens: list[Token] = []
    mo: re.Match[str]
    for mo in TOKEN_RE.finditer(line):
        group: str | None = mo.lastgroup
        text: str = mo.group()
        if group == "MISMATCH":
            raise AsmError("cadena sin cerrar" if text == '"' else f"carácter inesperado '{text}'")
        if group in KINDS:
            tokens.append(Token(KINDS[group], text, mo.start()))
    return tokens


def parse_num(text: str) -> int:
    mo: re.Match[str] | None = NUM_RE.fullmatch(text)
    if mo is None:
        raise AsmError(f"inmediato inválido '{text}'")
    sign: int = -1 if mo.group(1) == "-" else 1
    body: str = mo.group(2)
    if body[1:2] in ("x", "X"):
        return sign * int(body[2:], 16)
    if body[1:2] in ("b", "B"):
        return sign * int(body[2:], 2)
    if len(body) > 1 and body[0] == "0":
        raise AsmError(f"inmediato inválido '{text}'")
    return sign * int(body, 10)
