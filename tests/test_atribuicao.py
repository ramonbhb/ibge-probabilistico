"""Melhor nota por Censo; lista = CPF com até MAX_CENSOS_POR_CPF Censos no topo."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MAX_CENSOS_POR_CPF


def _criar_pessoas(con: duckdb.DuckDBPyConnection, rows: list[tuple] | None = None) -> None:
    con.execute(
        "CREATE TABLE pessoas (unique_id VARCHAR, cep VARCHAR, nome_mae_phon VARCHAR)"
    )
    if rows:
        con.executemany("INSERT INTO pessoas VALUES (?, ?, ?)", rows)


def _melhor_e_lista(
    con: duckdb.DuckDBPyConnection,
    threshold: float = 0.95,
    max_censos: int = MAX_CENSOS_POR_CPF,
) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TABLE melhor_por_censo AS
        SELECT p.unique_id_censo, p.unique_id_cpf, p.match_probability
        FROM splink_predictions p
        LEFT JOIN pessoas ca ON ca.unique_id = p.unique_id_censo
        LEFT JOIN pessoas pb ON pb.unique_id = p.unique_id_cpf
        WHERE p.match_probability >= {threshold}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY p.unique_id_censo
            ORDER BY
                p.match_probability DESC,
                (
                    CAST(
                        ca.cep IS NOT NULL AND pb.cep IS NOT NULL
                        AND ca.cep = pb.cep AS INTEGER
                    )
                    + CAST(
                        ca.nome_mae_phon IS NOT NULL AND pb.nome_mae_phon IS NOT NULL
                        AND ca.nome_mae_phon = pb.nome_mae_phon AS INTEGER
                    )
                ) DESC,
                p.unique_id_cpf
        ) = 1
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE associacoes_unicas AS
        SELECT m.*
        FROM melhor_por_censo m
        JOIN (
            SELECT unique_id_cpf
            FROM melhor_por_censo
            GROUP BY 1
            HAVING COUNT(*) <= {max_censos}
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


def test_dois_censos_mesmo_cpf_ficam() -> None:
    """C1-X 0,99, C2-X 0,98 → os dois ficam (n_censo = 2 ≤ 3)."""
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_X', 0.98),
            ('censo_B', 'cpf_Y', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert melhor == {"censo_A": "cpf_X", "censo_B": "cpf_X"}
    assert lista == {"censo_A": "cpf_X", "censo_B": "cpf_X"}


def test_tres_censos_mesmo_cpf_ficam() -> None:
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_X', 0.98),
            ('censo_C', 'cpf_X', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert lista == {
        "censo_A": "cpf_X",
        "censo_B": "cpf_X",
        "censo_C": "cpf_X",
    }


def test_quatro_censos_mesmo_cpf_saem_todos() -> None:
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_X', 0.98),
            ('censo_C', 'cpf_X', 0.97),
            ('censo_D', 'cpf_X', 0.96)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert lista == {}


def test_dois_pares_distintos_entram() -> None:
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_B', 'cpf_Y', 0.97)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert lista == {"censo_A": "cpf_X", "censo_B": "cpf_Y"}


def test_empate_p_escolhe_cep_e_mae_phon() -> None:
    con = duckdb.connect()
    _criar_pessoas(
        con,
        [
            ("censo_A", "80000000", "MARIA"),
            ("cpf_X", "00000001", "JOANA"),
            ("cpf_Z", "80000000", "MARIA"),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_A', 'cpf_Z', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    con.close()
    assert melhor == {"censo_A": "cpf_Z"}


def test_empate_p_e_atributos_cai_no_unique_id_cpf() -> None:
    con = duckdb.connect()
    _criar_pessoas(con)
    con.execute(
        """
        CREATE TABLE splink_predictions AS SELECT * FROM (VALUES
            ('censo_A', 'cpf_X', 0.99),
            ('censo_A', 'cpf_W', 0.99)
        ) v(unique_id_censo, unique_id_cpf, match_probability)
        """
    )
    _melhor_e_lista(con)
    melhor = _rows(con, "melhor_por_censo")
    lista = _rows(con, "associacoes_unicas")
    con.close()
    assert melhor == {"censo_A": "cpf_W"}
    assert lista == {"censo_A": "cpf_W"}
