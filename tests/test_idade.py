"""Idade: PECP0003 e PECP0030 dividem a população, não uma cobre a outra."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    ANO_REFERENCIA_CENSO,
    CENSO_COL_IDADE_ANOS,
    CENSO_COL_IDADE_MESES,
    IDADE_MAX,
    idade_censo_sql,
    idade_cpf_sql,
    idade_int_sql,
)
from features import normalize_date_sql  # noqa: E402


@pytest.fixture()
def con():
    conexao = duckdb.connect()
    yield conexao
    conexao.close()


def idade_censo(con, anos, meses, tipo: str = "VARCHAR"):
    con.execute(
        f'CREATE OR REPLACE TABLE p AS SELECT CAST(? AS {tipo}) AS "'
        f'{CENSO_COL_IDADE_ANOS}", CAST(? AS {tipo}) AS "{CENSO_COL_IDADE_MESES}"',
        [anos, meses],
    )
    return con.execute(f"SELECT {idade_censo_sql('p')} FROM p p").fetchone()[0]


# --- Censo -------------------------------------------------------------------


@pytest.mark.parametrize(
    "anos,meses,esperado",
    [
        # PECP0003 preenchida: 1 ano ou mais
        ("35", None, 35),
        ("1", None, 1),
        (str(IDADE_MAX), None, IDADE_MAX),
        # PECP0030 preenchida: menos de 1 ano, logo 0 ano completo
        (None, "0", 0),
        (None, "5", 0),
        (None, "11", 0),
        # Nenhuma das duas
        (None, None, None),
        ("", "", None),
        # Fora de faixa
        (str(IDADE_MAX + 1), None, None),
        ("-1", None, None),
        (None, "12", None),   # 12 meses seria 1 ano, deveria estar em PECP0003
        (None, "999", None),
    ],
)
def test_idade_censo(con, anos, meses, esperado) -> None:
    assert idade_censo(con, anos, meses) == esperado


def test_meses_nao_sao_divididos_por_doze(con) -> None:
    """PECP0030 cobre só o primeiro ano: 11 meses é 0 ano, não 0.9."""
    assert idade_censo(con, None, "11") == 0


def test_anos_zero_aceito_por_seguranca(con) -> None:
    """Fora do documentado, mas se aparecer significa menos de 1 ano."""
    assert idade_censo(con, "0", None) == 0


def test_anos_tem_precedencia_sobre_meses(con) -> None:
    """Se as duas vierem preenchidas, a de anos manda."""
    assert idade_censo(con, "40", "7") == 40


@pytest.mark.parametrize("tipo", ["VARCHAR", "INTEGER", "DOUBLE"])
def test_idade_censo_tolera_o_tipo_da_coluna(con, tipo) -> None:
    valor = "35" if tipo == "VARCHAR" else 35
    assert idade_censo(con, valor, None, tipo) == 35


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
        ("1990-01-02", ANO_REFERENCIA_CENSO - 1990),
        ("2022-06-01", 0),
        ("", None),
        (None, None),
        ("1850-01-01", None),
        ("2030-01-01", None),
    ],
)
def test_idade_cpf(con, data, esperado) -> None:
    dob = normalize_date_sql("v")
    assert con.execute(
        f"SELECT {idade_cpf_sql(dob)} FROM (SELECT CAST(? AS VARCHAR) AS v) t", [data]
    ).fetchone()[0] == esperado


@pytest.mark.parametrize(
    "bruto,parseou",
    [
        ("1990-01-02", True),
        ("02/01/1990", True),
        ("02-01-1990", True),
        ("19900102", False),   # formato compacto não é tratado hoje
        ("01/1990", False),
    ],
)
def test_formatos_de_data_aceitos(con, bruto, parseou) -> None:
    """Se DAT_NASCIMENTO vier num formato fora desta lista, a idade do CPF zera."""
    saida = con.execute(
        f"SELECT {normalize_date_sql('v')} FROM (SELECT CAST(? AS VARCHAR) AS v) t",
        [bruto],
    ).fetchone()[0]
    assert (saida != "") is parseou, f"{bruto!r} → {saida!r}"
