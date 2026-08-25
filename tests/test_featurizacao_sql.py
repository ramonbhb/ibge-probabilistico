"""Paridade entre a featurização SQL (DuckDB) e a implementação Python de referência."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features import (  # noqa: E402
    clean_name,
    clean_name_sql,
    full_name_phon_basic,
    name_feature_columns_sql,
    select_list_sql,
    split_name_three_parts,
)

NOMES = [
    "José da Silva",
    "MARIA DAS GRAÇAS",
    "Ana Beatriz Kühn",
    "Wanderley Y. Zacharias",
    "Philippe Schwartz",
    "Guilherme Guimarães",
    "Joaquim Queiroz Quintela",
    "Nascimento Cheira Chácara",
    "Cecília Cícero Célia",
    "Gilberto Gil Gêmeo",
    "Aaaa Bbbb Cccc",
    "Hilda Hoffmann Horta",
    "Assunção Exceção Excelso",
    "Mitzi Katz Fritz",
    "Carvalho",
    "",
    "   ",
    "nan",
    "NULL",
    "None",
    "O'CONNOR-SMITH",
    "Anna Karolyna Wanderlyz",
    "Ximenes Xisto Xuxa",
    "Ludwig van Beethoven",
    "MARIA   DE    FATIMA",
    "Ilha Solteira 2 do Norte",
    "Ç ç Ñ ñ",
    "Æneas Œuvre",
    "Renê\tDescartes\nCartesius",
    "Vitor\x0bHugo\rMenezes\x0cFilho",
    "A",
    "A B",
    "A B C",
    "A B C D",
]

CHAVES = [
    "nome_completo",
    "nome_completo_phon",
    "primeiro_nome",
    "nome_meio",
    "ultimo_nome",
    "primeiro_nome_phon",
    "nome_meio_phon",
    "ultimo_nome_phon",
]


def referencia_python(nome: str) -> dict[str, str | None]:
    limpo = clean_name(nome)
    primeiro, meio, ultimo = split_name_three_parts(limpo) if limpo else ("", "", "")
    completo_phon = full_name_phon_basic(limpo) if limpo else ""
    p_phon, m_phon, u_phon = (
        split_name_three_parts(completo_phon) if completo_phon else ("", "", "")
    )

    def nulo(v: str) -> str | None:
        return v if v else None

    return {
        "nome_completo": limpo,
        "nome_completo_phon": nulo(completo_phon),
        "primeiro_nome": nulo(primeiro),
        "nome_meio": nulo(meio),
        "ultimo_nome": nulo(ultimo),
        "primeiro_nome_phon": nulo(p_phon),
        "nome_meio_phon": nulo(m_phon),
        "ultimo_nome_phon": nulo(u_phon),
    }


@pytest.fixture(scope="module")
def resultado_sql() -> dict[str, dict[str, str | None]]:
    from features import PESSOA_COLUMNS

    con = duckdb.connect()
    con.execute("CREATE TABLE bruto (id INTEGER, nome VARCHAR)")
    con.executemany(
        "INSERT INTO bruto VALUES (?, ?)", list(enumerate(NOMES))
    )
    cols = name_feature_columns_sql("nome_norm", col_map=PESSOA_COLUMNS)
    sql = f"""
    WITH norm AS (
        SELECT id, {clean_name_sql('nome')} AS nome_norm FROM bruto
    )
    SELECT id, {select_list_sql(cols)} FROM norm ORDER BY id
    """
    linhas = con.execute(sql).fetchall()
    nomes_col = [d[0] for d in con.execute(sql).description]
    con.close()
    return {
        NOMES[linha[0]]: dict(zip(nomes_col[1:], linha[1:])) for linha in linhas
    }


@pytest.mark.parametrize("nome", NOMES, ids=lambda n: repr(n))
def test_paridade_sql_python(nome: str, resultado_sql) -> None:
    esperado = referencia_python(nome)
    obtido = resultado_sql[nome]
    for chave in CHAVES:
        assert obtido[chave] == esperado[chave], (
            f"{chave} divergiu em {nome!r}: "
            f"SQL={obtido[chave]!r} Python={esperado[chave]!r}"
        )


@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("Jose DA silva", "JOSE SILVA"),
        ("JOSE SILVA DA COSTA", "JOSE SILVA COSTA"),
        ("MARIA DOS SANTOS", "MARIA SANTOS"),
        ("DEISE SILVA", "DEISE SILVA"),
        ("Desconhecido", None),
        ("Maria Ignorada", "MARIA"),
        ("Mãe", None),
        ("JOSE MARIA HELENA SILVA", "JOSE MARIA HELENA SILVA"),
    ],
)
def test_clean_name_particulas_e_placeholders(nome: str, esperado: str | None) -> None:
    assert clean_name(nome) == esperado


def test_nome_meio_phon_composto() -> None:
    ref = referencia_python("JOSE MARIA HELENA SILVA")
    assert ref["nome_meio"] == "MARIA HELENA"
    assert ref["nome_meio_phon"]
    assert ref["nome_meio_phon"] in (ref["nome_completo_phon"] or "")


def test_divergencia_conhecida_ligaturas() -> None:
    """strip_accents do DuckDB não decompõe ligaduras; o NFKD do Python decompõe."""
    from features import full_name_norm, normalize_text_sql

    literal = "'" + chr(0xFB01) + "LHO'"
    con = duckdb.connect()
    sql_out = con.execute(f"SELECT {normalize_text_sql(literal)}").fetchone()[0]
    con.close()
    assert full_name_norm("\ufb01lho") == "FILHO"
    assert sql_out == "LHO"


def test_nome_mae_renomeia_colunas() -> None:
    from features import NOME_MAE_COLUMNS

    cols = name_feature_columns_sql(
        "nome_mae_norm", col_map=NOME_MAE_COLUMNS
    )
    assert set(cols) == set(NOME_MAE_COLUMNS.values())
    assert cols["nome_mae"] == "nome_mae_norm"
    assert "nome_meio_mae_phon" in cols


def test_nao_gera_colunas_phon_sv() -> None:
    cols = name_feature_columns_sql("nome_norm")
    assert not any("phon_sv" in alias for alias in cols)


@pytest.mark.skipif(
    not os.environ.get("BENCH_SQL"),
    reason="benchmark opcional; rode com BENCH_SQL=1",
)
def test_benchmark_list_reduce() -> None:
    """Custo do dedupe por list_reduce numa amostra de alguns milhões de linhas."""
    from features import normalize_text_sql

    n = int(os.environ.get("BENCH_SQL_N", 5_000_000))
    con = duckdb.connect()
    con.execute(
        f"""
        CREATE TABLE amostra AS
        SELECT list_element(
            ['José da Silva', 'MARIA DAS GRAÇAS', 'Guilherme Guimarães',
             'Philippe Schwartz', 'Assunção Exceção'],
            (i % 5) + 1
        ) AS nome
        FROM range({n}) t(i)
        """
    )
    cols = name_feature_columns_sql("nome_norm")
    sql = f"""
    CREATE TABLE saida AS
    WITH norm AS (SELECT {clean_name_sql('nome')} AS nome_norm FROM amostra)
    SELECT {select_list_sql(cols)} FROM norm
    """
    inicio = time.perf_counter()
    con.execute(sql)
    duracao = time.perf_counter() - inicio
    total = con.execute("SELECT count(*) FROM saida").fetchone()[0]
    con.close()
    assert total == n
    print(f"\n{n:,} linhas em {duracao:.1f}s ({n / duracao / 1e6:.2f}M linhas/s)")
