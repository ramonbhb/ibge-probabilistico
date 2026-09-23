"""logradouro_norm: nome da rua sem tipo, igual nos dois lados."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features import logradouro_norm_sql  # noqa: E402


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("Rua da Paz", "DA PAZ"),
        ("R DA PAZ", "DA PAZ"),
        ("Av. Central", "CENTRAL"),
        ("AVENIDA CENTRAL", "CENTRAL"),
        ("GRANDE", "GRANDE"),
        ("RIO BRANCO", "RIO BRANCO"),
        ("", None),
        (None, None),
    ],
)
def test_logradouro_norm(valor, esperado) -> None:
    con = duckdb.connect()
    expr = logradouro_norm_sql("v")
    got = con.execute(f"SELECT {expr} FROM (SELECT ? AS v)", [valor]).fetchone()[0]
    con.close()
    assert got == esperado
