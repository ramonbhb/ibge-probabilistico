"""Greedy 1:1 em materialize_atribuicao (não 'melhor por Censo e drop de CPF')."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    materialize_atribuicao,
    materialize_cluster_composicao,
)


def _base(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE splink_input AS SELECT * FROM (VALUES
            ('censo_A', 'censo'),
            ('censo_B', 'censo'),
            ('censo_C', 'censo'),
            ('censo_D', 'censo'),
            ('censo_E', 'censo'),
            ('cpf_X', 'cpf'),
            ('cpf_Y', 'cpf'),
            ('cpf_Z', 'cpf'),
            ('cpf_W', 'cpf')
        ) v(unique_id, origem)
        """
    )


def test_greedy_fica_com_segundo_melhor_cpf() -> None:
    """C1-X 0,99, C2-X 0,98, C2-Y 0,97 → C2 fica com Y, não fica sem par."""
    con = duckdb.connect()
    _base(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_X', 0.98),
            ('censo_B', 'cpf_Y', 0.97)
        ) v(unique_id_l, unique_id_r, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE splink_clusters AS SELECT * FROM (VALUES
            ('censo_A', 1),
            ('censo_B', 1),
            ('cpf_X', 1),
            ('cpf_Y', 1)
        ) v(unique_id, cluster_id)
        """
    )
    # 2×2 seria `outros` na classificação real; força tipo permitido para
    # isolar o greedy (melhor-por-Censo + drop deixaria B sem par).
    con.execute(
        """
        CREATE TABLE cluster_composicao AS SELECT * FROM (VALUES
            (1, 4, 2, 2, '1_cpf_n_censo')
        ) v(cluster_id, n, n_censo, n_cpf, tipo)
        """
    )
    stats = materialize_atribuicao(con, threshold=0.95)
    rows = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT unique_id_censo, unique_id_cpf FROM atribuicao_censo_cpf"
        ).fetchall()
    }
    con.close()
    assert stats["n_candidatos"] == 3
    assert stats["n_atribuidos"] == 2
    assert rows == {"censo_A": "cpf_X", "censo_B": "cpf_Y"}


def test_outros_nao_entra() -> None:
    con = duckdb.connect()
    _base(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_C', 'cpf_Z', 0.99),
            ('censo_D', 'cpf_W', 0.99)
        ) v(unique_id_l, unique_id_r, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE splink_clusters AS SELECT * FROM (VALUES
            ('censo_C', 9),
            ('censo_D', 9),
            ('cpf_Z', 9),
            ('cpf_W', 9)
        ) v(unique_id, cluster_id)
        """
    )
    materialize_cluster_composicao(con)
    tipo = con.execute(
        "SELECT tipo FROM cluster_composicao WHERE cluster_id = 9"
    ).fetchone()[0]
    assert tipo == "outros"
    stats = materialize_atribuicao(con, threshold=0.95)
    n = con.execute("SELECT COUNT(*) FROM atribuicao_censo_cpf").fetchone()[0]
    con.close()
    assert stats["n_candidatos"] == 0
    assert n == 0


def test_1_cpf_n_censo_fica_o_melhor_censo() -> None:
    con = duckdb.connect()
    _base(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_D', 'cpf_W', 0.99),
            ('censo_E', 'cpf_W', 0.96)
        ) v(unique_id_l, unique_id_r, match_probability)
        """
    )
    con.execute(
        """
        CREATE TABLE splink_clusters AS SELECT * FROM (VALUES
            ('censo_D', 2),
            ('censo_E', 2),
            ('cpf_W', 2)
        ) v(unique_id, cluster_id)
        """
    )
    materialize_cluster_composicao(con)
    tipo = con.execute(
        "SELECT tipo FROM cluster_composicao WHERE cluster_id = 2"
    ).fetchone()[0]
    assert tipo == "1_cpf_n_censo"
    materialize_atribuicao(con, threshold=0.95)
    rows = con.execute(
        "SELECT unique_id_censo, unique_id_cpf FROM atribuicao_censo_cpf"
    ).fetchall()
    con.close()
    assert rows == [("censo_D", "cpf_W")]
