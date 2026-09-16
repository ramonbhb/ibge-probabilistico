"""3 tokens + epêntese D: paridade SQL/Python, sem CSV de variantes."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features import full_name_phon_basic, phonetic_name_sql  # noqa: E402

PARES = [
    ("EDGARD", "EDGAR"),
    ("DAVID", "DAVI"),
    ("ISTER", "ESTER"),
    ("EDVALDO", "EDIVALDO"),
    ("ADMAR", "ADIMAR"),
    ("EDGAR", "EDIGAR"),
]


def fonetica_sql(nome: str, con: duckdb.DuckDBPyConnection) -> str:
    return con.execute(
        f"SELECT {phonetic_name_sql('nome')} FROM (SELECT ? AS nome)",
        [nome],
    ).fetchone()[0]


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


@pytest.mark.parametrize("a,b", PARES, ids=[f"{a}={b}" for a, b in PARES])
def test_pares_colapsam(a: str, b: str, con) -> None:
    assert full_name_phon_basic(a) == full_name_phon_basic(b)
    assert fonetica_sql(a, con) == fonetica_sql(b, con)
    assert fonetica_sql(a, con) == full_name_phon_basic(a)


def test_edgar_edgard_viram_edigar(con) -> None:
    assert full_name_phon_basic("EDGAR") == "EDIGAR"
    assert fonetica_sql("EDGARD", con) == "EDIGAR"


def test_adriana_e_pedro_sem_epentese(con) -> None:
    assert full_name_phon_basic("ADRIANA") == "ADRIANA"
    assert full_name_phon_basic("PEDRO") == "PEDRO"
    assert fonetica_sql("ADRIANA", con) == "ADRIANA"
    assert fonetica_sql("PEDRO", con) == "PEDRO"


def test_csv_variantes_nao_colapsa() -> None:
    assert full_name_phon_basic("KEMILI") != full_name_phon_basic("KEMELI")
    assert full_name_phon_basic("ISTER") == full_name_phon_basic("ESTER")
