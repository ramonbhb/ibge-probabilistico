"""Nome fonético vem do join; o 00 só parte primeiro/último."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import materialize_censo_registros  # noqa: E402
from features import full_name_phon_basic  # noqa: E402


def test_split_usa_phon_do_join_sem_recalcular() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE censo_staging (
            person_id_censo VARCHAR,
            id_domicilio VARCHAR,
            nome_completo_raw VARCHAR,
            nome_mae_inferido VARCHAR,
            data_nascimento VARCHAR,
            sexo_raw VARCHAR,
            idade INTEGER,
            cep VARCHAR,
            uf VARCHAR,
            cod_municipio VARCHAR,
            nome_completo_phon VARCHAR
        )
        """
    )
    con.execute(
        """
        INSERT INTO censo_staging VALUES
        ('1', 'd1', 'Christian da Silva', 'Maria', '1990-01-02',
         '1', 32, '65000000', '21', '2111300', 'CHRISTIAN SILVA'),
        ('2', 'd2', 'Edgard Costa', 'Ana', '1985-05-05',
         '1', 37, '65000000', '21', '2111300', 'EDIGAR COSTA')
        """
    )
    materialize_censo_registros(con)
    rows = {
        r[0]: r[1:]
        for r in con.execute(
            """
            SELECT person_id_censo, nome_completo, nome_completo_phon,
                   primeiro_nome_phon, ultimo_nome_phon
            FROM censo_registros
            """
        ).fetchall()
    }
    assert rows["1"][0] == "CHRISTIAN SILVA"
    assert rows["1"][1] == "CHRISTIAN SILVA"
    assert rows["1"][2] == "CHRISTIAN"
    assert rows["1"][3] == "SILVA"
    assert rows["1"][1] != full_name_phon_basic("CHRISTIAN SILVA")
    assert rows["2"][1] == "EDIGAR COSTA"
    assert rows["2"][2] == "EDIGAR"
    assert rows["2"][3] == "COSTA"
    con.close()


def test_sem_phon_no_staging_falha() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE censo_staging (
            person_id_censo VARCHAR,
            id_domicilio VARCHAR,
            nome_completo_raw VARCHAR,
            nome_mae_inferido VARCHAR,
            data_nascimento VARCHAR,
            sexo_raw VARCHAR,
            idade INTEGER,
            cep VARCHAR,
            uf VARCHAR,
            cod_municipio VARCHAR
        )
        """
    )
    con.execute(
        "INSERT INTO censo_staging VALUES "
        "('1', 'd1', 'Ana', NULL, '1990-01-01', '2', 32, '', '21', '2111300')"
    )
    with pytest.raises(RuntimeError, match="nome_completo_phon"):
        materialize_censo_registros(con)
    con.close()
