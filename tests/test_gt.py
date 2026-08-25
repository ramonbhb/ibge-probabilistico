"""GT 1:1 da coorte e carimbo CPF no Censo."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    materialize_cohort_cpf_por_censo,
    materialize_gt_1a1,
    materialize_gt_no_subset,
    stamp_censo_cpf_from_cohort,
)


def test_nao_1a1_e_descartado_do_gt(tmp_path: Path) -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE splink_input AS SELECT * FROM (VALUES
            ('censo_A', 'censo'),
            ('censo_B', 'censo'),
            ('cpf_1', 'cpf'),
            ('cpf_2', 'cpf'),
            ('cpf_3', 'cpf')
        ) v(unique_id, origem)
        """
    )
    path = tmp_path / "cohort.parquet"
    con.execute(f"""
    COPY (
        SELECT * FROM (VALUES
            ('A', '1'),
            ('B', '2'),
            ('B', '3')
        ) v(PERSON_ID_CENSO, CPF_NORM)
    ) TO '{path}' (FORMAT PARQUET)
    """)
    counts = materialize_gt_no_subset(
        con, cohort_parquet=path, splink_view="splink_input"
    )
    con.close()
    assert counts["n_pares_coorte_nacional"] == 3
    assert counts["n_pares_1a1_nacional"] == 1
    assert counts["n_nao_1a1_descartada"] == 2
    assert counts["n_gt_no_subset"] == 1


def test_stamp_censo_coorte_com_min(tmp_path: Path) -> None:
    con = duckdb.connect()
    path = tmp_path / "cohort.parquet"
    con.execute(f"""
    COPY (
        SELECT * FROM (VALUES
            ('A', '1'),
            ('B', '3'),
            ('B', '2')
        ) v(PERSON_ID_CENSO, CPF_NORM)
    ) TO '{path}' (FORMAT PARQUET)
    """)
    con.execute(
        """
        CREATE TABLE censo AS SELECT * FROM (VALUES
            ('censo_A', 'A', CAST(NULL AS VARCHAR)),
            ('censo_B', 'B', CAST(NULL AS VARCHAR)),
            ('censo_C', 'C', CAST(NULL AS VARCHAR))
        ) v(unique_id, person_id_censo, cpf_norm)
        """
    )
    stats = materialize_cohort_cpf_por_censo(con, cohort_parquet=path)
    n = stamp_censo_cpf_from_cohort(con, table="censo")
    rows = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT unique_id, cpf_norm FROM censo ORDER BY unique_id"
        ).fetchall()
    }
    con.close()
    assert stats["n_censo_com_cpf_coorte"] == 2
    assert stats["n_censo_cpf_ambiguo"] == 1
    assert n == 2
    assert rows["censo_A"] == "00000000001"
    assert rows["censo_B"] == "00000000002"  # MIN(2, 3)
    assert rows["censo_C"] is None


def test_gt_1a1_nao_filtra_por_rotulo(tmp_path: Path) -> None:
    """Toda cohort_dedup é confiável; só a cardinalidade 1:1 importa."""
    con = duckdb.connect()
    path = tmp_path / "cohort.parquet"
    con.execute(f"""
    COPY (
        SELECT * FROM (VALUES
            ('A', '1'),
            ('C', '9')
        ) v(PERSON_ID_CENSO, CPF_NORM)
    ) TO '{path}' (FORMAT PARQUET)
    """)
    counts = materialize_gt_1a1(con, cohort_parquet=path)
    con.close()
    assert counts["n_pares_1a1_nacional"] == 2
    assert counts["n_nao_1a1_descartada"] == 0
