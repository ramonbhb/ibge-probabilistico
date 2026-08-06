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
        br_phonetic_token,
        featurize_names_batch,
        full_name_norm,
        full_name_phon,
        normalize_date,
        normalize_date_sql,
        normalize_text,
        tokenize_name,
    )
except ImportError:
    # Fallback mínimo (sem dependência de ibge-listas instalado)
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

    def br_phonetic_token(token: str) -> str:
        token = normalize_text(token)
        if not token:
            return ""
        if len(token) > 1:
            token = token[0] + re.sub(r"[AEIOU]", "", token[1:])
        return token

    def full_name_norm(name) -> str:
        return " ".join(tokenize_name(name))

    def full_name_phon(name) -> str:
        return " ".join(br_phonetic_token(t) for t in tokenize_name(name) if br_phonetic_token(t))

    def featurize_names_batch(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Instale ibge-listas ou polars para featurize_names_batch")


def split_name_three_parts(name) -> tuple[str, str, str]:
    """Divide nome em primeiro, meio e último token (após normalização)."""
    toks = tokenize_name(name)
    if not toks:
        return "", "", ""
    if len(toks) == 1:
        return toks[0], "", ""
    return toks[0], " ".join(toks[1:-1]), toks[-1]


def middle_name_norm(name) -> str:
    return split_name_three_parts(name)[1]


def last_name_norm(name) -> str:
    return split_name_three_parts(name)[2]


def first_name_phon(name) -> str:
    toks = tokenize_name(name)
    return br_phonetic_token(toks[0]) if toks else ""


def last_name_phon(name) -> str:
    return br_phonetic_token(split_name_three_parts(name)[2])


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


def _featurize_three_part_list(names: list) -> dict[str, list]:
    primeiro, meio, ultimo = zip(*(split_name_three_parts(n) for n in names)) if names else ([], [], [])
    return {
        "nome_completo_norm": [full_name_norm(n) for n in names],
        "nome_completo_phon": [full_name_phon(n) for n in names],
        "primeiro_nome": list(primeiro),
        "nome_meio": list(meio),
        "ultimo_nome": list(ultimo),
        "primeiro_nome_phon": [first_name_phon(n) for n in names],
        "ultimo_nome_phon": [last_name_phon(n) for n in names],
    }


def _featurize_chunk(args: tuple[list,]) -> dict[str, list]:
    (names,) = args
    return _featurize_three_part_list(names)


def featurize_three_part_names_batch(
    con: duckdb.DuckDBPyConnection,
    *,
    source_table: str,
    target_table: str,
    name_col: str,
    where_sql: str = "",
    chunk_size: int = 500_000,
    n_workers: int | None = None,
) -> None:
    """Adiciona colunas de nome (primeiro/meio/último) a uma tabela staging."""
    where_clause = f" WHERE {where_sql}" if where_sql else ""
    arrow = con.execute(f"SELECT * FROM {source_table}{where_clause}").fetch_arrow_table()
    if n_workers is None:
        n_workers = min(os.cpu_count() or 4, 8)

    if pl is not None:
        frame = pl.from_arrow(arrow)
        names = frame[name_col].to_list()
        n = len(names)
        if n_workers <= 1 or n <= chunk_size:
            feat = _featurize_three_part_list(names)
        else:
            chunks = [names[i : i + chunk_size] for i in range(0, n, chunk_size)]
            merged: dict[str, list] = {}
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                for part in pool.map(_featurize_chunk, [(c,) for c in chunks], chunksize=1):
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
        feat = _featurize_three_part_list(names)
        for col, vals in feat.items():
            frame[col] = vals
        con.register("_feat_three", frame)

    con.execute(f"CREATE OR REPLACE TABLE {target_table} AS SELECT * FROM _feat_three")
    con.unregister("_feat_three")
