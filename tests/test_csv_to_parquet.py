"""CSV → Parquet: linha ok, NUL, campo anulado, drop só se n não fecha."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "csv_parquet"))

from csv_to_parquet import (  # noqa: E402
    UnrepairableRowsError,
    convert_file,
    parse_row,
)


PIPE_OPTS = {
    "delim": "|",
    "quote": "",
    "strip_outer_quotes": True,
    "encoding": "latin-1",
    "header": True,
}

RFC_OPTS = {
    "delim": ",",
    "quote": '"',
    "encoding": "utf-8",
    "header": True,
}


def _parquet_rows(path: Path) -> list[tuple]:
    con = duckdb.connect()
    rows = con.execute(f"SELECT * FROM read_parquet('{path}') ORDER BY 1, 2").fetchall()
    con.close()
    return rows


def test_parse_row_rfc_ok() -> None:
    row, n_nulled = parse_row(
        '"a,b","c",d', delim=",", quote='"', n_cols=3
    )
    assert row == ["a,b", "c", "d"]
    assert n_nulled == 0


def test_parse_row_aspas_tortas_anula_campo() -> None:
    line = (
        '"291930610000003"|"0"|"47"|"12"|"2023-03-??K?$"2023-06-04 15:40:58"|"0"'
    )
    row, n_nulled = parse_row(line, delim="|", quote='"', n_cols=6)
    assert row is not None
    assert row[0] == "291930610000003"
    assert row[1] == "0"
    assert row[2] == "47"
    assert row[3] == "12"
    assert row[4] is None
    assert row[5] == "0"
    assert n_nulled == 1


def test_parse_row_extra_campo_irreparavel() -> None:
    row, _ = parse_row("1,2,3,4", delim=",", quote='"', n_cols=3)
    assert row is None


def test_csv_ok(tmp_path: Path) -> None:
    src = tmp_path / "ok.csv"
    src.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
    dest = tmp_path / "ok.parquet"
    stats = convert_file(src, dest, RFC_OPTS, name="ok")
    assert stats.n_rows == 2
    assert stats.n_rows_dropped == 0
    assert stats.n_rows_repaired == 0
    assert _parquet_rows(dest) == [("1", "2", "3"), ("4", "5", "6")]


def test_nul_e_aspas_pipe_mantem_linha(tmp_path: Path) -> None:
    src = tmp_path / "especie.csv"
    header = b'"cod_setor"|"num_quadra"|"num_face"|"cod_seglogr"|"dt"|"flag"\n'
    good = b'"291930610000003"|"0"|"47"|"12"|"2023-01-01"|"0"\n'
    bad = (
        b'"291930610000003"|"0"|"47"|"12"|"2023-03-'
        + b"\x00?\x00\x00K?$\x00\x00?\x00"
        + b'"2023-06-04 15:40:58.080000000"|"0"\n'
    )
    good2 = b'"291930610000004"|"1"|"2"|"3"|"2023-02-02"|"1"\n'
    src.write_bytes(header + good + bad + good2)
    dest = tmp_path / "especie.parquet"
    stats = convert_file(src, dest, PIPE_OPTS, name="especie")
    assert stats.n_rows == 3
    assert stats.n_rows_dropped == 0
    assert stats.n_fields_nulled >= 1
    rows = _parquet_rows(dest)
    assert len(rows) == 3
    nulos = [r for r in rows if r[4] is None]
    assert len(nulos) == 1
    assert nulos[0][0] == "291930610000003"
    assert nulos[0][3] == "12"
    assert nulos[0][5] == "0"
    assert any(r[4] == "2023-01-01" for r in rows)
    assert any(r[4] == "2023-02-02" for r in rows)


def test_rfc_repara_campo_e_conta_igual(tmp_path: Path) -> None:
    src = tmp_path / "rfc.csv"
    src.write_bytes(
        b"a,b,c\n"
        b'"ok","x","1"\n'
        b'"bad\x00","not closed"x","2"\n'
        b'"ok2","y","3"\n'
    )
    dest = tmp_path / "rfc.parquet"
    stats = convert_file(src, dest, RFC_OPTS, name="rfc")
    assert stats.n_rows == 3
    assert stats.n_rows_dropped == 0
    rows = {r[2]: r for r in _parquet_rows(dest)}
    assert rows["1"] == ("ok", "x", "1")
    assert rows["2"][2] == "2"
    assert rows["2"][0] is None or rows["2"][1] is None
    assert rows["3"] == ("ok2", "y", "3")


def test_drop_so_quando_n_nao_fecha(tmp_path: Path) -> None:
    src = tmp_path / "extra.csv"
    src.write_text("a,b,c\n1,2,3\n9,9,9,9\n4,5,6\n", encoding="utf-8")
    dest = tmp_path / "extra.parquet"
    stats = convert_file(src, dest, RFC_OPTS, name="extra")
    assert stats.n_rows_dropped == 1
    assert stats.n_rows == 2
    assert _parquet_rows(dest) == [("1", "2", "3"), ("4", "5", "6")]


def test_on_unrepairable_fail(tmp_path: Path) -> None:
    src = tmp_path / "extra.csv"
    src.write_text("a,b,c\n1,2,3,4\n", encoding="utf-8")
    dest = tmp_path / "extra.parquet"
    opts = {**RFC_OPTS, "on_unrepairable": "fail"}
    with pytest.raises(UnrepairableRowsError):
        convert_file(src, dest, opts, name="fail")
