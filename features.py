"""Normalização e featurização para linkage probabilístico (split primeiro/meio/último)."""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

try:
    import polars as pl
except ImportError:  # pragma: no cover
    pl = None  # type: ignore[assignment,misc]

# Shim ibge_common quando ibge-listas está no path
_IBGE_LISTAS = Path(__file__).resolve().parent.parent / "ibge-listas"
if _IBGE_LISTAS.is_dir() and str(_IBGE_LISTAS) not in sys.path:
    sys.path.insert(0, str(_IBGE_LISTAS))

try:
    from ibge_common.features.ouro_cpf import (  # noqa: F401
        normalize_date,
        normalize_date_sql,
        normalize_text,
        tokenize_name,
    )
except ImportError:
    def strip_accents(text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in text if not unicodedata.combining(ch))

    def normalize_text(text) -> str:
        if text is None:
            return ""
        text = str(text).upper().strip()
        if text in {"", "NAN", "NONE", "NULL"}:
            return ""
        text = strip_accents(text)
        text = re.sub(r"[^A-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def normalize_date(x) -> str:
        if x is None:
            return ""
        s = str(x).strip()
        if s in {"", "NAN", "NONE", "NULL"}:
            return ""
        try:
            if hasattr(x, "strftime"):
                return x.strftime("%Y-%m-%d")
            parts = re.split(r"[-/]", s)
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    yyyy, mm, dd = parts
                else:
                    dd, mm, yyyy = parts
                return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
        except Exception:
            pass
        return ""

    def normalize_date_sql(col: str) -> str:
        s = f"trim(CAST({col} AS VARCHAR))"
        s_dash = f"replace({s}, '/', '-')"
        return f"""
        CASE
            WHEN {col} IS NULL THEN ''
            WHEN {s} IN ('', 'NAN', 'NONE', 'NULL') THEN ''
            WHEN length({s_dash}) = 10 AND substr({s_dash}, 5, 1) = '-'
                THEN {s_dash}
            WHEN length({s_dash}) = 10 AND substr({s_dash}, 3, 1) = '-'
                THEN coalesce(strftime(try_strptime({s_dash}, '%d-%m-%Y'), '%Y-%m-%d'), '')
            ELSE coalesce(
                strftime(try_cast({col} AS DATE), '%Y-%m-%d'),
                strftime(try_strptime({s_dash}, '%Y-%m-%d'), '%Y-%m-%d'),
                strftime(try_strptime({s_dash}, '%d-%m-%Y'), '%Y-%m-%d'),
                ''
            )
        END
        """.strip()

    def tokenize_name(name) -> list[str]:
        name = normalize_text(name)
        return [tok for tok in name.split() if tok] if name else []


_PHONETIC_REPLACEMENTS = [
    ("PH", "F"), ("Y", "I"), ("W", "V"), ("CK", "K"), ("SCH", "X"),
    ("SH", "X"), ("CH", "X"), ("LH", "L"), ("NH", "N"), ("GUI", "GI"),
    ("GUE", "GE"), ("QUI", "KI"), ("QUE", "KE"), ("SS", "S"),
    ("XC", "S"), ("XS", "S"), ("TS", "S"), ("TZ", "S"), ("Z", "S"), ("H", ""),
]


def _dedupe_consecutive(token: str) -> str:
    return re.sub(r"(.)\1+", r"\1", token)


def br_phonetic_basic_token(token: str) -> str:
    """Substituições fonéticas PT-BR; sem remoção de vogais."""
    token = normalize_text(token)
    if not token:
        return ""
    for a, b in _PHONETIC_REPLACEMENTS:
        token = token.replace(a, b)
    token = re.sub(r"C(?=[EI])", "S", token)
    token = re.sub(r"G(?=[EI])", "J", token)
    token = token.replace("Q", "K").replace("C", "K")
    return _dedupe_consecutive(token)


def br_phonetic_token(token: str, *, strip_vowels: bool = False) -> str:
    """Fonética básica; strip_vowels=True aplica remoção agressiva de vogais."""
    token = br_phonetic_basic_token(token)
    if strip_vowels and len(token) > 1:
        token = token[0] + re.sub(r"[AEIOU]", "", token[1:])
        token = _dedupe_consecutive(token)
    return token


def full_name_norm(name) -> str:
    return " ".join(tokenize_name(name))


def full_name_phon_basic(name) -> str:
    vals = [br_phonetic_basic_token(t) for t in tokenize_name(name)]
    return " ".join(v for v in vals if v)


def full_name_phon_sv(name) -> str:
    vals = [br_phonetic_token(t, strip_vowels=True) for t in tokenize_name(name)]
    return " ".join(v for v in vals if v)


def split_name_three_parts(name) -> tuple[str, str, str]:
    toks = tokenize_name(name)
    if not toks:
        return "", "", ""
    if len(toks) == 1:
        return toks[0], "", ""
    return toks[0], " ".join(toks[1:-1]), toks[-1]


def _token_phon_basic(token: str) -> str:
    return br_phonetic_basic_token(token) if token else ""


def _token_phon_sv(token: str) -> str:
    return br_phonetic_token(token, strip_vowels=True) if token else ""


def normalize_sexo(sexo) -> str:
    s = normalize_text(sexo)
    if s in {"M", "MASC", "MASCULINO", "1"}:
        return "M"
    if s in {"F", "FEM", "FEMININO", "2"}:
        return "F"
    return s[:1] if s else ""


def normalize_cep(cep) -> str:
    if cep is None:
        return ""
    digits = re.sub(r"\D", "", str(cep))
    if len(digits) < 5:
        return ""
    return digits.zfill(8)[:8]


def _featurize_three_part_list(names: list, *, strip_vowels: bool = False) -> dict[str, list]:
    primeiro, meio, ultimo = zip(*(split_name_three_parts(n) for n in names)) if names else ([], [], [])
    out: dict[str, list] = {
        "nome_completo_norm": [full_name_norm(n) for n in names],
        "nome_completo_phon": [full_name_phon_basic(n) for n in names],
        "primeiro_nome": list(primeiro),
        "nome_meio": list(meio),
        "ultimo_nome": list(ultimo),
        "primeiro_nome_phon": [_token_phon_basic(t) for t in primeiro],
        "ultimo_nome_phon": [_token_phon_basic(t) for t in ultimo],
    }
    if strip_vowels:
        out["nome_completo_phon_sv"] = [full_name_phon_sv(n) for n in names]
        out["primeiro_nome_phon_sv"] = [_token_phon_sv(t) for t in primeiro]
        out["ultimo_nome_phon_sv"] = [_token_phon_sv(t) for t in ultimo]
    return out


def _featurize_chunk(args: tuple[list, bool]) -> dict[str, list]:
    names, strip_vowels = args
    return _featurize_three_part_list(names, strip_vowels=strip_vowels)


def featurize_three_part_names_batch(
    con: duckdb.DuckDBPyConnection,
    *,
    source_table: str,
    target_table: str,
    name_col: str,
    where_sql: str = "",
    chunk_size: int = 500_000,
    n_workers: int | None = None,
    strip_vowels: bool | None = None,
) -> None:
    """Adiciona colunas de nome (primeiro/meio/último + fonética básica)."""
    if strip_vowels is None:
        from config import USE_PHONETIC_STRIP_VOWELS
        strip_vowels = USE_PHONETIC_STRIP_VOWELS

    where_clause = f" WHERE {where_sql}" if where_sql else ""
    arrow = con.execute(f"SELECT * FROM {source_table}{where_clause}").fetch_arrow_table()
    if n_workers is None:
        n_workers = min(os.cpu_count() or 4, 8)

    if pl is not None:
        frame = pl.from_arrow(arrow)
        names = frame[name_col].to_list()
        n = len(names)
        if n_workers <= 1 or n <= chunk_size:
            feat = _featurize_three_part_list(names, strip_vowels=strip_vowels)
        else:
            chunks = [names[i : i + chunk_size] for i in range(0, n, chunk_size)]
            merged: dict[str, list] = {}
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                for part in pool.map(
                    _featurize_chunk,
                    [(c, strip_vowels) for c in chunks],
                    chunksize=1,
                ):
                    for col, vals in part.items():
                        merged.setdefault(col, []).extend(vals)
            feat = merged
        for col, vals in feat.items():
            frame = frame.with_columns(pl.Series(col, vals))
        con.register("_feat_three", frame.to_arrow())
    else:
        import pandas as pd

        frame = arrow.to_pandas()
        names = frame[name_col].tolist()
        feat = _featurize_three_part_list(names, strip_vowels=strip_vowels)
        for col, vals in feat.items():
            frame[col] = vals
        con.register("_feat_three", frame)

    con.execute(f"CREATE OR REPLACE TABLE {target_table} AS SELECT * FROM _feat_three")
    con.unregister("_feat_three")
