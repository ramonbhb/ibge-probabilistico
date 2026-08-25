"""Fonética alternativa (Luis) — para comparar com features.br_phonetic_basic_token.

Arquivo original veio com encoding quebrado; Ç→S e Ñ→NH reconstituídos a partir
dos comentários ("cedilha e ñ antes de remover acentos").
"""

from __future__ import annotations

import re
import unicodedata


def limpar(texto) -> str:
    if not isinstance(texto, str):
        return ""

    texto = texto.upper()

    conectivos = {"E", "DE", "DO", "DA", "DOS", "DAS"}

    # Remove pontuação (mantém letras, dígitos e espaço)
    texto = re.sub(r"[^\w\s]", "", texto)

    palavras = texto.split()
    palavras_filtradas = [p for p in palavras if p not in conectivos]
    return " ".join(palavras_filtradas)


def fonetica(nome) -> str:
    nome = limpar(nome)

    # Cedilha e ñ antes de remover acentos (já em maiúsculo)
    nome = nome.replace("Ç", "S")
    nome = nome.replace("Ñ", "NH")

    nome = (
        unicodedata.normalize("NFKD", nome)
        .encode("ASCII", "ignore")
        .decode("utf-8")
    )

    nome = re.sub(r"[-_]", " ", nome)
    nome = re.sub(r"[^A-Z\s]", "", nome)

    resultado: list[str] = []
    for p in nome.split():
        p = re.sub(r"Y", "I", p)
        p = re.sub(r"SCH", "X", p)
        p = re.sub(r"SH", "X", p)
        p = re.sub(r"CH", "X", p)
        p = re.sub(r"PH", "F", p)
        p = re.sub(r"TH", "T", p)
        p = re.sub(r"RH", "R", p)
        p = re.sub(r"WI", "UI", p)
        p = re.sub(r"W", "V", p)
        p = re.sub(r"CK", "K", p)
        p = re.sub(r"QU", "K", p)

        # Nasalização: M + consoante → N + consoante
        p = re.sub(r"M([BCDFGHJKLMNPQRSTVWXZ])", r"N\1", p)

        p = re.sub(r"^H", "", p)
        p = re.sub(r"C([EI])", r"S\1", p)
        p = re.sub(r"C", "K", p)
        p = re.sub(r"G([EI])", r"J\1", p)
        p = re.sub(r"([AEIOU])S([AEIOU])", r"\1Z\2", p)
        p = re.sub(r"SS", "S", p)
        p = re.sub(r"Z$", "S", p)

        # I epentético
        p = re.sub(r"^S([BCDFGHJKLMNPQRSTVWXZ])", r"IS\1", p)
        p = re.sub(r"([BDPTKVGF])([BDPTKVGMNC])", r"\1I\2", p)
        p = re.sub(r"([BCDFGJKPTVXZ])$", r"\1I", p)

        # Finais
        p = re.sub(r"O$", "U", p)
        p = re.sub(r"E$", "I", p)
        p = re.sub(r"L$", "U", p)
        p = re.sub(r"M$", "N", p)

        p = re.sub(r"(.)\1+", r"\1", p)
        if p:
            resultado.append(p)

    return " ".join(resultado)
