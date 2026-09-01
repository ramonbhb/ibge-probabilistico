"""Filtro geográfico: escalar ou lista de UF / município."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from config import (  # noqa: E402
    geo_filter_clause,
    municipio_filter_clause,
    normalize_municipio_lista,
    normalize_uf_lista,
    uf_filter_clause,
)


def test_normalize_uf_escalar() -> None:
    assert normalize_uf_lista(21) == ("21",)
    assert normalize_uf_lista("42") == ("42",)
    assert normalize_uf_lista(None) is None
    assert normalize_uf_lista([]) is None


def test_normalize_uf_lista() -> None:
    assert normalize_uf_lista([21, 22]) == ("21", "22")
    assert normalize_uf_lista([21, 21, 22]) == ("21", "22")
    assert normalize_uf_lista((21,)) == ("21",)


def test_normalize_municipio_lista() -> None:
    assert normalize_municipio_lista(2111300) == ("2111300",)
    assert normalize_municipio_lista([2111300, 2105302]) == ("2111300", "2105302")
    assert normalize_municipio_lista(None) is None


def test_uf_clause_eq_e_in() -> None:
    assert uf_filter_clause("uf", 21) == "uf = '21'"
    assert uf_filter_clause("uf", [21, 22]) == "uf IN ('21', '22')"
    assert uf_filter_clause("uf", None) == "TRUE"


def test_municipio_clause_eq_e_in() -> None:
    assert municipio_filter_clause("mun", 2111300) == "mun = '2111300'"
    assert municipio_filter_clause("mun", [2111300, 2105302]) == (
        "mun IN ('2111300', '2105302')"
    )
    assert municipio_filter_clause("mun", None) == "TRUE"


def test_geo_and_quando_os_dois() -> None:
    clause = geo_filter_clause(
        "uf", "mun", filtro_uf=[21, 22], filtro_municipio=2111300
    )
    assert "uf IN ('21', '22')" in clause
    assert "mun = '2111300'" in clause
    assert " AND " in clause


def test_set_filtros_lista() -> None:
    old_uf, old_mun = config.FILTRO_UF, config.FILTRO_MUNICIPIO
    try:
        uf, mun = config.set_filtros(uf=[21, 22], municipio=None)
        assert uf == ("21", "22")
        assert mun is None
        assert config.FILTRO_UF == ("21", "22")
        assert uf_filter_clause("x") == "x IN ('21', '22')"
        assert municipio_filter_clause("y") == "TRUE"

        config.set_filtros(uf=None, municipio=[2111300, 2105302])
        assert config.FILTRO_MUNICIPIO == ("2111300", "2105302")
        assert municipio_filter_clause("y") == "y IN ('2111300', '2105302')"
    finally:
        config.set_filtros(uf=old_uf, municipio=old_mun)
