"""materialize_gt_no_subset: 1:1 vs prata descartada."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    materialize_gt_no_subset,
    materialize_ouro_1a1,
    stamp_censo_cpf_from_ouro,
)


def test_prata_n_para_1_e_descartada(tmp_path: Path) -> None:
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
    assert counts["n_prata_descartada"] == 2
    assert counts["n_gt_no_subset"] == 1


def test_stamp_censo_so_ouro_1a1(tmp_path: Path) -> None:
    con = duckdb.connect()
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
    con.execute(
        """
        CREATE TABLE registro AS SELECT * FROM (VALUES
            ('censo_A', 'censo', 'A', CAST(NULL AS VARCHAR)),
            ('censo_B', 'censo', 'B', CAST(NULL AS VARCHAR)),
            ('censo_C', 'censo', 'C', CAST(NULL AS VARCHAR)),
            ('cpf_x', 'cpf', CAST(NULL AS VARCHAR), '00000000009')
        ) v(unique_id, origem, person_id_censo, cpf_norm)
        """
    )
    ouro = materialize_ouro_1a1(con, cohort_parquet=path)
    n = stamp_censo_cpf_from_ouro(con, table="registro")
    rows = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT unique_id, cpf_norm FROM registro ORDER BY unique_id"
        ).fetchall()
    }
    con.close()
    assert ouro["n_pares_1a1_nacional"] == 1
    assert n == 1
    assert rows["censo_A"] == "00000000001"
    assert rows["censo_B"] is None
    assert rows["censo_C"] is None
    assert rows["cpf_x"] == "00000000009"
