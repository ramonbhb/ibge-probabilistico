"""Idade: Censo via PECP0401 (0–140); CPF derivada da data de nascimento."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    ANO_REFERENCIA_CENSO,
    CENSO_COL_IDADE_CALC,
    CENSO_IDADE_MAX,
    DATA_REFERENCIA_IDADE,
    idade_censo_sql,
    idade_cpf_sql,
    idade_int_sql,
)
from features import normalize_date_compacta_sql, normalize_date_sql  # noqa: E402


@pytest.fixture()
def con():
    conexao = duckdb.connect()
    yield conexao
    conexao.close()


def idade_censo(con, valor, tipo: str = "VARCHAR"):
    con.execute(
        f'CREATE OR REPLACE TABLE p AS SELECT CAST(? AS {tipo}) AS "{CENSO_COL_IDADE_CALC}"',
        [valor],
    )
    return con.execute(f"SELECT {idade_censo_sql('p')} FROM p p").fetchone()[0]


# --- Censo (PECP0401) --------------------------------------------------------


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("35", 35),
        ("0", 0),
        (str(CENSO_IDADE_MAX), CENSO_IDADE_MAX),
        (None, None),
        ("", None),
        (str(CENSO_IDADE_MAX + 1), None),
        ("-1", None),
        ("999", None),
    ],
)
def test_idade_censo_pecp0401(con, valor, esperado) -> None:
    assert idade_censo(con, valor) == esperado


@pytest.mark.parametrize("tipo", ["VARCHAR", "INTEGER", "DOUBLE", "DECIMAL"])
def test_idade_censo_tolera_o_tipo_da_coluna(con, tipo) -> None:
    if tipo == "DECIMAL":
        con.execute(
            f'CREATE OR REPLACE TABLE p AS SELECT CAST(35 AS DECIMAL(11,0)) AS "{CENSO_COL_IDADE_CALC}"'
        )
        assert con.execute(f"SELECT {idade_censo_sql('p')} FROM p p").fetchone()[0] == 35
    else:
        valor = "35" if tipo == "VARCHAR" else 35
        assert idade_censo(con, valor, tipo) == 35


@pytest.mark.parametrize(
    "valor,esperado",
    [("35", 35), ("035", 35), (" 35 ", 35), ("35.0", 35), ("", None), ("NA", None)],
)
def test_cast_tolerante(con, valor, esperado) -> None:
    assert con.execute(
        f"SELECT {idade_int_sql('v')} FROM (SELECT CAST(? AS VARCHAR) AS v) t", [valor]
    ).fetchone()[0] == esperado


# --- CPF ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "data,esperado",
    [
        # DATA_REFERENCIA_IDADE = 2022-08-01 → anos completos
        ("1990-01-02", 32),   # aniversário antes da ref
        ("1990-09-01", 31),   # aniversário depois da ref
        ("2022-06-01", 0),
        ("2022-08-01", 0),
        ("", None),
        (None, None),
        ("1850-01-01", None),
        ("2030-01-01", None),
    ],
)
def test_idade_cpf(con, data, esperado) -> None:
    assert DATA_REFERENCIA_IDADE == "2022-08-01"
    dob = normalize_date_sql("v")
    assert con.execute(
        f"SELECT {idade_cpf_sql(dob)} FROM (SELECT CAST(? AS VARCHAR) AS v) t", [data]
    ).fetchone()[0] == esperado


@pytest.mark.parametrize(
    "bruto,esperado",
    [
        ("1990-01-02", "1990-01-02"),
        ("02/01/1990", "1990-01-02"),
        ("19900102", "1990-01-02"),
        ("", ""),
        ("99999999", ""),
    ],
)
def test_formatos_de_data_aceitos(con, bruto, esperado) -> None:
    saida = con.execute(
        f"SELECT {normalize_date_compacta_sql('v')} "
        "FROM (SELECT CAST(? AS VARCHAR) AS v) t",
        [bruto],
    ).fetchone()[0]
    assert saida == esperado, f"{bruto!r} → {saida!r}"
