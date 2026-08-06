"""Regras de limpeza do NB00b: filtro de óbito, data inválida e valores-sentinela."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    ANO_NASCIMENTO_MIN,
    ANO_OBITO_CORTE,
    ANO_REFERENCIA_CENSO,
    SEXO_VALIDOS,
    cep_valido_sql,
    dob_valida_sql,
    limpeza_columns_sql,
    obito_antes_do_censo_sql,
    sexo_valido_sql,
    texto_nao_vazio_sql,
)


@pytest.fixture()
def con():
    conexao = duckdb.connect()
    yield conexao
    conexao.close()


def escalar(con, expr: str, valor, tipo: str = "VARCHAR"):
    return con.execute(
        f"SELECT {expr} FROM (SELECT CAST(? AS {tipo}) AS v) t", [valor]
    ).fetchone()[0]


# --- Óbito -------------------------------------------------------------------


@pytest.mark.parametrize(
    "ano,removido",
    [
        (None, False),          # vivo, ou qualquer linha do Censo
        (0, False),             # sentinela, não é ano de óbito
        (-1, False),
        (1990, True),
        (ANO_OBITO_CORTE - 1, True),
        (ANO_OBITO_CORTE, False),       # o corte em si fica
        (ANO_REFERENCIA_CENSO, False),
        (9999, False),          # absurdo no futuro não é motivo para descartar
    ],
)
def test_filtro_obito(con, ano, removido) -> None:
    assert escalar(con, obito_antes_do_censo_sql("v"), ano, "INTEGER") is removido


def test_filtro_obito_nao_derruba_linha_por_null(con) -> None:
    """NOT (expr) precisa manter a linha quando o ano é NULL, sem propagar NULL."""
    con.execute(
        "CREATE TABLE t AS SELECT * FROM (VALUES (1, NULL), (2, 1990), (3, 2022)) "
        "v(id, ano_obito)"
    )
    ids = con.execute(
        f"SELECT id FROM t WHERE NOT {obito_antes_do_censo_sql()} ORDER BY id"
    ).fetchall()
    assert [i[0] for i in ids] == [1, 3]


# --- Data de nascimento ------------------------------------------------------


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("1990-01-02", "1990-01-02"),
        (f"{ANO_NASCIMENTO_MIN}-01-01", f"{ANO_NASCIMENTO_MIN}-01-01"),
        (f"{ANO_REFERENCIA_CENSO}-12-31", f"{ANO_REFERENCIA_CENSO}-12-31"),
        ("", None),
        ("   ", None),
        (None, None),
        ("1850-05-05", None),                      # antes da faixa
        (f"{ANO_REFERENCIA_CENSO + 1}-01-01", None),  # depois do Censo
        ("2022-02-30", None),                      # dia que não existe
        ("nao-e-data", None),
    ],
)
def test_dob_valida(con, valor, esperado) -> None:
    assert escalar(con, dob_valida_sql("v"), valor) == esperado


# --- CEP ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("30110001", "30110001"),
        ("30110-001", "30110001"),
        ("00000000", None),   # o lpad do cep_norm_sql fabrica isso quando falta CEP
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_cep_valido(con, valor, esperado) -> None:
    assert escalar(con, cep_valido_sql("v"), valor) == esperado


# --- Sexo --------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("M", "M"),
        ("F", "F"),
        ("m", "M"),
        (" f ", "F"),
        ("O", None),    # outro
        ("I", None),    # ignorado
        ("N", None),    # não informado
        ("9", None),
        ("0", None),
        ("", None),
        (None, None),
    ],
)
def test_sexo_valido(con, valor, esperado) -> None:
    assert escalar(con, sexo_valido_sql("v"), valor) == esperado


def test_sexo_residual_nao_fabrica_concordancia(con) -> None:
    """Dois 'outro' não são a mesma pessoa; ExactMatch os trataria como acordo."""
    con.execute(
        "CREATE TABLE t AS SELECT * FROM (VALUES (1, 'O'), (2, 'O'), (3, 'M'), (4, 'M')) "
        "v(id, sexo)"
    )
    pares = lambda expr: con.execute(  # noqa: E731
        f"SELECT COUNT(*) FROM (SELECT id, {expr} AS s FROM t) l "
        f"JOIN (SELECT id, {expr} AS s FROM t) r ON l.s = r.s AND l.id < r.id"
    ).fetchone()[0]
    assert pares("sexo") == 2, "antes: o par de 'O' também concorda"
    assert pares(sexo_valido_sql("sexo")) == 1, "depois: só o par de 'M'"


def test_sexo_lista_vem_da_config() -> None:
    assert SEXO_VALIDOS == ("M", "F")
    for valor in SEXO_VALIDOS:
        assert f"'{valor}'" in sexo_valido_sql()


def test_texto_vazio_vira_null(con) -> None:
    assert escalar(con, texto_nao_vazio_sql("v"), "") is None
    assert escalar(con, texto_nao_vazio_sql("v"), "  ") is None
    assert escalar(con, texto_nao_vazio_sql("v"), "SILVA") == "SILVA"


def test_null_nao_casa_com_null(con) -> None:
    """A razão de tudo isso: '' = '' fabrica par candidato, NULL = NULL não."""
    assert con.execute("SELECT '' = ''").fetchone()[0] is True
    assert con.execute("SELECT NULL = NULL").fetchone()[0] is None


# --- Montagem das colunas ----------------------------------------------------


def tipos_registro() -> dict[str, str]:
    return {
        "unique_id": "VARCHAR",
        "origem": "VARCHAR",
        "cpf_norm": "VARCHAR",
        "nome_completo": "VARCHAR",
        "primeiro_nome": "VARCHAR",
        "ultimo_nome": "VARCHAR",
        "data_nascimento": "VARCHAR",
        "sexo": "VARCHAR",
        "idade": "INTEGER",
        "cep": "VARCHAR",
        "ano_obito": "INTEGER",
        "person_id_censo": "VARCHAR",
    }


def test_colunas_estruturais_e_numericas_intactas() -> None:
    cols = limpeza_columns_sql(tipos_registro())
    for nome in ("unique_id", "origem", "cpf_norm", "person_id_censo", "ano_obito"):
        assert cols[nome] == nome, f"{nome} não deveria ser transformada"
    assert set(cols) == set(tipos_registro()), "nenhuma coluna pode sumir"


def test_nomes_entram_na_limpeza() -> None:
    """primeiro_nome e ultimo_nome estão na blocking rule principal do NB02."""
    cols = limpeza_columns_sql(tipos_registro())
    for nome in ("nome_completo", "primeiro_nome", "ultimo_nome"):
        assert cols[nome] != nome
        assert "NULLIF" in cols[nome]


def test_sexo_usa_a_regra_de_categoria() -> None:
    cols = limpeza_columns_sql(tipos_registro())
    assert cols["sexo"] == sexo_valido_sql("sexo")


def test_idade_do_cpf_acompanha_a_data(con) -> None:
    cols = limpeza_columns_sql(tipos_registro())
    con.execute(
        """CREATE TABLE t AS SELECT * FROM (VALUES
        ('cpf',   '1850-01-01', 172),
        ('cpf',   '1990-01-02',  32),
        ('censo', '',            40)
    ) v(origem, data_nascimento, idade)"""
    )
    linhas = con.execute(
        f"SELECT origem, {cols['idade']} AS idade FROM t"
    ).fetchall()
    assert linhas == [("cpf", None), ("cpf", 32), ("censo", 40)], (
        "idade do CPF deriva da data e cai junto; a do Censo vem de PECP0003"
    )
