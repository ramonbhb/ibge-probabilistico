"""Lookup espécie ⋈ endereço ⋈ face ⋈ LOGR; rua vem da face."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    CENSO_COL_ENDERECO,
    CENSO_COL_FACE,
    CENSO_COL_QUADRA,
    CENSO_COL_SEQ_ESPECIE,
    CENSO_COL_SETOR,
    censo_cep_join_on,
    materialize_censo_logr_lookup,
)


def test_logr_lookup_usa_seglogr_da_face(tmp_path: Path) -> None:
    con = duckdb.connect()
    especie = tmp_path / "especie.parquet"
    endereco = tmp_path / "endereco.parquet"
    face = tmp_path / "face.parquet"
    logr = tmp_path / "logr.parquet"
    setor = "211130005000001"

    # especie.cod_seglogr aponta para a outra rua de propósito.
    con.execute(
        f"""
        COPY (
            SELECT * FROM (
                SELECT
                    '{setor}' AS cod_setor, '1' AS num_quadra, '2' AS num_face,
                    '10' AS cod_endereco, '1' AS seq_especie,
                    '222' AS cod_seglogr
                UNION ALL
                SELECT
                    '{setor}', '1', '3', '20', '1', '111'
            )
        ) TO '{especie}' (FORMAT PARQUET)
        """
    )
    con.execute(
        f"""
        COPY (
            SELECT * FROM (
                SELECT
                    '{setor}' AS cod_setor, '1' AS num_quadra, '2' AS num_face,
                    '10' AS cod_endereco
                UNION ALL
                SELECT '{setor}', '1', '3', '20'
            )
        ) TO '{endereco}' (FORMAT PARQUET)
        """
    )
    con.execute(
        f"""
        COPY (
            SELECT * FROM (
                SELECT
                    '{setor}' AS cod_setor, '1' AS num_quadra, '2' AS num_face,
                    '111' AS cod_seglogr
                UNION ALL
                SELECT '{setor}', '1', '3', '222'
            )
        ) TO '{face}' (FORMAT PARQUET)
        """
    )
    con.execute(
        f"""
        COPY (
            SELECT * FROM (
                SELECT
                    '{setor}' AS COD_SETOR, '111' AS COD_SEGLOGR,
                    '21' AS COD_UF, '2111300' AS COD_MUNICIPIO,
                    '65000000' AS CEP_SEGLOGR, 'RUA' AS NOM_TIPO_SEGLOGR,
                    '' AS NOM_TITULO_SEGLOGR, 'GRANDE' AS NOM_SEGLOGR
                UNION ALL
                SELECT
                    '{setor}', '222', '21', '2111300',
                    '65000001', 'AVENIDA', '', 'CENTRAL'
            )
        ) TO '{logr}' (FORMAT PARQUET)
        """
    )
    materialize_censo_logr_lookup(
        con,
        especie_path=especie,
        endereco_path=endereco,
        face_path=face,
        logr_path=logr,
        filtro_uf=None,
        filtro_municipio=None,
    )
    n = con.execute("SELECT COUNT(*) FROM censo_logr_lookup").fetchone()[0]
    assert n == 2

    con.execute(
        f"""
        CREATE TABLE p AS
        SELECT
            '{setor}' AS {CENSO_COL_SETOR},
            '1' AS {CENSO_COL_QUADRA},
            '2' AS {CENSO_COL_FACE},
            '10' AS {CENSO_COL_ENDERECO},
            '1' AS {CENSO_COL_SEQ_ESPECIE}
        """
    )
    join_on = censo_cep_join_on("p", "k")
    row = con.execute(
        f"""
        SELECT k.cep, k.tipo_logradouro, k.logradouro
        FROM p
        LEFT JOIN censo_logr_lookup k ON {join_on}
        """
    ).fetchone()
    con.close()
    assert row == ("65000000", "RUA", "GRANDE")
