"""Melhor nota por Censo; única = CPF com um só Censo no topo."""

from __future__ import annotations

import duckdb


def _melhor_e_unicas(con: duckdb.DuckDBPyConnection, threshold: float = 0.95) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TABLE melhor_por_censo AS
        SELECT unique_id_censo, unique_id_cpf, match_probability
        FROM splink_predictions
        WHERE match_probability >= {threshold}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY unique_id_censo
            ORDER BY match_probability DESC, unique_id_cpf
        ) = 1
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE associacoes_unicas AS
        SELECT m.*
        FROM melhor_por_censo m
        JOIN (
            SELECT unique_id_cpf
            FROM melhor_por_censo
            GROUP BY 1
            HAVING COUNT(*) = 1
        ) c ON c.unique_id_cpf = m.unique_id_cpf
        """
    )


def _rows(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, str]:
    return {
        r[0]: r[1]
        for r in con.execute(
            f"SELECT unique_id_censo, unique_id_cpf FROM {table}"
        ).fetchall()
    }


def test_melhor_nota_cpf_compartilhado_nao_e_unica() -> None:
    """C1-X 0,99, C2-X 0,98, C2-Y 0,97 → C2 fica com X; X tem 2 Censos; única vazia."""
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_X', 0.98),
            ('censo_B', 'cpf_Y', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_unicas(con)
    melhor = _rows(con, "melhor_por_censo")
    unicas = _rows(con, "associacoes_unicas")
    n_x = con.execute(
        "SELECT n_censo FROM ("
        "  SELECT unique_id_cpf, COUNT(*) AS n_censo FROM melhor_por_censo GROUP BY 1"
        ") WHERE unique_id_cpf = 'cpf_X'"
    ).fetchone()[0]
    con.close()
    assert melhor == {"censo_A": "cpf_X", "censo_B": "cpf_X"}
    assert unicas == {}
    assert n_x == 2


def test_dois_pares_distintos_sao_unicas() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_Y', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_unicas(con)
    unicas = _rows(con, "associacoes_unicas")
    con.close()
    assert unicas == {"censo_A": "cpf_X", "censo_B": "cpf_Y"}


def test_empate_desempata_por_unique_id_cpf() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_A', 'cpf_W', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_unicas(con)
    melhor = _rows(con, "melhor_por_censo")
    unicas = _rows(con, "associacoes_unicas")
    con.close()
    assert melhor == {"censo_A": "cpf_W"}
    assert unicas == {"censo_A": "cpf_W"}
