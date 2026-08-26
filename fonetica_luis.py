"""Fonética alternativa (Luis) — experimental, para comparar com features.py.

Diferencial vs produção: regras “faladas” (S entre vogais → Z, finais O→U/E→I/L→U/M→N,
nasal M+cons→N, epêntese ^S+cons). Dígrafo/limpeza alinhados à produção.
"""

from __future__ import annotations

import re
import unicodedata

from features import TERMOS_RUIDO_NOME

_CONECTIVOS = set(TERMOS_RUIDO_NOME)

_RE_NAO_LETRA = re.compile(r"[^A-Z\s]")
_RE_ESPACOS = re.compile(r"\s+")
_RE_M_CONS = re.compile(r"M([BCDFGHJKLMNPQRSTVWXZ])")
_RE_C_SOFT = re.compile(r"C([EI])")
_RE_G_SOFT = re.compile(r"G([EI])")
_RE_S_VOGAL = re.compile(r"([AEIOU])S([AEIOU])")
_RE_Z_FIM = re.compile(r"Z$")
_RE_S_INICIO = re.compile(r"^S([BCDFGHJKLMNPQRSTVWXZ])")
_RE_FINAL_O = re.compile(r"O$")
_RE_FINAL_E = re.compile(r"E$")
_RE_FINAL_L = re.compile(r"L$")
_RE_FINAL_M = re.compile(r"M$")
_RE_DEDUPE = re.compile(r"(.)\1+")


def limpar(texto) -> str:
    """Upper, Ç/Ñ, ASCII, só letras, remove partículas/placeholders."""
    if not isinstance(texto, str):
        return ""

    texto = texto.upper()
    texto = texto.replace("Ç", "S").replace("Ñ", "NH")
    texto = (
        unicodedata.normalize("NFKD", texto)
        .encode("ASCII", "ignore")
        .decode("utf-8")
    )
    texto = _RE_NAO_LETRA.sub(" ", texto)
    texto = _RE_ESPACOS.sub(" ", texto).strip()
    if not texto:
        return ""

    palavras = [p for p in texto.split() if p not in _CONECTIVOS]
    return " ".join(palavras)


def _fonetica_token(p: str) -> str:
    p = p.replace("Y", "I")
    for a, b in (
        ("SCH", "X"),
        ("SH", "X"),
        ("CH", "X"),
        ("PH", "F"),
        ("TH", "T"),
        ("RH", "R"),
        ("WI", "UI"),
        ("W", "V"),
        ("CK", "K"),
        ("QUE", "KE"),
        ("QUI", "KI"),
        ("QU", "K"),
        ("GUI", "GI"),
        ("GUE", "GE"),
        ("NH", "N"),
        ("LH", "L"),
    ):
        p = p.replace(a, b)

    p = _RE_M_CONS.sub(r"N\1", p)

    if p.startswith("H"):
        p = p[1:]
    p = _RE_C_SOFT.sub(r"S\1", p)
    p = p.replace("C", "K")
    p = _RE_G_SOFT.sub(r"J\1", p)
    p = _RE_S_VOGAL.sub(r"\1Z\2", p)
    p = p.replace("SS", "S")
    p = _RE_Z_FIM.sub("S", p)

    # Dedupe antes da epêntese — evita FILIPIPI a partir de PHILIPPE.
    p = _RE_DEDUPE.sub(r"\1", p)

    # Epêntese só no S inicial + consoante (sem regra de cluster no meio).
    p = _RE_S_INICIO.sub(r"IS\1", p)

    p = _RE_FINAL_O.sub("U", p)
    p = _RE_FINAL_E.sub("I", p)
    p = _RE_FINAL_L.sub("U", p)
    p = _RE_FINAL_M.sub("N", p)

    p = _RE_DEDUPE.sub(r"\1", p)
    return p


def fonetica(nome) -> str:
    nome = limpar(nome)
    if not nome:
        return ""
    resultado = []
    for p in nome.split():
        out = _fonetica_token(p)
        if out:
            resultado.append(out)
    return " ".join(resultado)
