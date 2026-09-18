"""Lookup ESPECIE ⋈ LOGR lê parquet, não CSV."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import materialize_censo_logr_lookup  # noqa: E402


def test_logr_lookup_le_parquet(tmp_path: Path) -> None:
    con = duckdb.connect()
    especie = tmp_path / "especie.parquet"
    logr = tmp_path / "logr.parquet"
    con.execute(
        f"""
        COPY (
            SELECT
                '211130005000001' AS cod_setor,
                '1' AS num_quadra,
                '2' AS num_face,
                '123' AS cod_seglogr
        ) TO '{especie}' (FORMAT PARQUET)
        """
    )
    con.execute(
        f"""
        COPY (
            SELECT
                '211130005000001' AS COD_SETOR,
                '123' AS COD_SEGLOGR,
                '21' AS COD_UF,
                '2111300' AS COD_MUNICIPIO,
                '65000000' AS CEP_SEGLOGR,
                'RUA' AS NOM_TIPO_SEGLOGR,
                '' AS NOM_TITULO_SEGLOGR,
                'GRANDE' AS NOM_SEGLOGR
        ) TO '{logr}' (FORMAT PARQUET)
        """
    )
    materialize_censo_logr_lookup(
        con,
        especie_path=especie,
        logr_path=logr,
        filtro_uf=None,
        filtro_municipio=None,
    )
    row = con.execute(
        """
        SELECT cod_setor_norm, num_quadra, num_face, cep, tipo_logradouro, logradouro
        FROM censo_logr_lookup
        """
    ).fetchone()
    con.close()
    assert row == (
        "211130005000001",
        "001",
        "002",
        "65000000",
        "RUA",
        "GRANDE",
    )
