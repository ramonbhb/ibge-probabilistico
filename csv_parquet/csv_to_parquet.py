#!/usr/bin/env python3
"""CSV → Parquet genérico (DuckDB). Linha ruim: anula o campo, não descarta a linha."""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent / "ingestion" / "datasets.yaml"
CHUNK = 8 << 20
NUL_STRIP_SUFFIX = ".nulstrip.csv"


@dataclass
class ConvertStats:
    name: str
    n_rows: int
    n_nul_bytes: int
    n_fields_nulled: int
    n_rows_repaired: int
    n_rows_dropped: int
    elapsed_s: float


class UnrepairableRowsError(RuntimeError):
    pass


def ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _is_dirty(val: str, leftover_quote: str | None) -> bool:
    if any(ord(c) < 32 and c not in "\t" for c in val):
        return True
    return bool(leftover_quote and leftover_quote in val)


def _strip_outer(val: str, quote: str) -> str:
    if quote and len(val) >= 2 and val[0] == quote and val[-1] == quote:
        return val[1:-1]
    return val


def parse_row(
    line: str,
    *,
    delim: str,
    quote: str,
    n_cols: int | None,
    escape: str | None = None,
) -> tuple[list[str | None] | None, int]:
    """Campos da linha, ou None se n não fecha. n_nulled = campos viraram NULL."""
    line = line.rstrip("\r\n")
    if quote == "":
        return _parse_split(line, delim=delim, n_cols=n_cols)
    return _parse_rfc(
        line, delim=delim, quote=quote, n_cols=n_cols, escape=escape
    )


def _parse_split(
    line: str, *, delim: str, n_cols: int | None
) -> tuple[list[str | None] | None, int]:
    parts = line.split(delim)
    fields: list[str | None] = []
    n_nulled = 0
    for part in parts:
        val = _strip_outer(part, '"')
        if _is_dirty(val, leftover_quote='"'):
            fields.append(None)
            n_nulled += 1
        else:
            fields.append(val)
    if n_cols is None:
        return fields, n_nulled
    if len(fields) < n_cols:
        fields.extend([None] * (n_cols - len(fields)))
        return fields, n_nulled
    extra = fields[n_cols:]
    if extra and not all(x is None or str(x).strip() == "" for x in extra):
        return None, 0
    return fields[:n_cols], n_nulled


def _parse_rfc(
    line: str,
    *,
    delim: str,
    quote: str,
    n_cols: int | None,
    escape: str | None,
) -> tuple[list[str | None] | None, int]:
    i = 0
    n = len(line)
    fields: list[str | None] = []
    n_nulled = 0
    want = n_cols if n_cols is not None else 10**9

    def resync_after_break() -> None:
        nonlocal i, n_nulled
        fields.append(None)
        n_nulled += 1
        while i < n and line[i] != delim:
            i += 1
        if i < n and line[i] == delim:
            i += 1

    while len(fields) < want:
        if i >= n:
            if n_cols is not None:
                fields.extend([None] * (n_cols - len(fields)))
            break
        if line[i] == quote:
            i += 1
            buf: list[str] = []
            broken = False
            while True:
                if i >= n:
                    broken = True
                    break
                ch = line[i]
                if (
                    escape
                    and escape != quote
                    and ch == escape
                    and i + 1 < n
                ):
                    buf.append(line[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    if i + 1 < n and line[i + 1] == quote:
                        buf.append(quote)
                        i += 2
                        continue
                    i += 1
                    if i < n and line[i] != delim:
                        broken = True
                    elif i < n and line[i] == delim:
                        i += 1
                    break
                buf.append(ch)
                i += 1
            if broken:
                resync_after_break()
                continue
            val = "".join(buf)
            if _is_dirty(val, leftover_quote=None):
                fields.append(None)
                n_nulled += 1
            else:
                fields.append(val)
            continue
        start = i
        while i < n and line[i] != delim:
            i += 1
        val = line[start:i]
        if i < n and line[i] == delim:
            i += 1
        if _is_dirty(val, leftover_quote=None):
            fields.append(None)
            n_nulled += 1
        else:
            fields.append(val)

    if n_cols is not None and i < n:
        leftover = line[i:].strip()
        if leftover:
            return None, 0
    return fields, n_nulled


def repair_csv_line(
    csv_line: str,
    *,
    delim: str,
    quote: str,
    n_cols: int,
    escape: str | None,
) -> tuple[list[list[str | None]], list[str], int]:
    """Quebra csv_line em linhas físicas (DuckDB às vezes engole a seguinte)."""
    repaired: list[list[str | None]] = []
    dropped: list[str] = []
    n_nulled = 0
    for phys in csv_line.splitlines():
        if phys.strip() == "":
            continue
        row, nulled = parse_row(
            phys, delim=delim, quote=quote, n_cols=n_cols, escape=escape
        )
        if row is None:
            dropped.append(phys)
        else:
            repaired.append(row)
            n_nulled += nulled
    return repaired, dropped, n_nulled


def strip_nul(src: Path, dest: Path) -> int:
    n = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as inf, dest.open("wb") as out:
        while True:
            chunk = inf.read(CHUNK)
            if not chunk:
                break
            c = chunk.count(b"\0")
            if c:
                n += c
                chunk = chunk.replace(b"\0", b"")
            out.write(chunk)
    return n


def read_header_names(
    path: Path,
    *,
    delim: str,
    quote: str,
    encoding: str,
    header: bool,
) -> list[str]:
    with path.open("rb") as f:
        buf = b""
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                buf = buf.split(b"\n", 1)[0]
                break
    buf = buf.replace(b"\0", b"").removeprefix(b"\xef\xbb\xbf").rstrip(b"\r")
    first = buf.decode(encoding, errors="replace")
    if quote == "":
        parts = [_strip_outer(p, '"') for p in first.split(delim)]
    else:
        row, _ = parse_row(
            first, delim=delim, quote=quote, n_cols=None, escape=None
        )
        parts = ["" if x is None else x for x in (row or first.split(delim))]
    if not header:
        n = max(len(parts), 1)
        return [f"column{i}" for i in range(n)]
    names: list[str] = []
    seen: dict[str, int] = {}
    for i, raw in enumerate(parts):
        name = (raw or "").strip() or f"column{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        names.append(name)
    return names


def _columns_sql(names: list[str]) -> str:
    inner = ", ".join(f"{sql_str(n)}: 'VARCHAR'" for n in names)
    return "{" + inner + "}"


def _read_csv_sql(
    path: Path,
    opts: dict,
    names: list[str],
    *,
    ignore_errors: bool = False,
) -> str:
    delim = opts["delim"]
    quote = opts["quote"]
    encoding = opts["encoding"]
    header = opts["header"]
    escape = opts.get("escape")
    parts = [
        f"'{sql_path(path)}'",
        f"delim={sql_str(delim)}",
        f"quote={sql_str(quote)}",
        f"header={'true' if header else 'false'}",
        f"encoding={sql_str(encoding)}",
        f"columns={_columns_sql(names)}",
        "auto_detect=false",
        "all_varchar=true",
        "parallel=true",
        "max_line_size=20000000",
    ]
    if quote and escape:
        parts.append(f"escape={sql_str(escape)}")
    if ignore_errors:
        parts.extend(
            [
                "ignore_errors=true",
                "store_rejects=true",
                "rejects_table='rejects'",
            ]
        )
    return "read_csv(" + ", ".join(parts) + ")"


def _clean_select_sql(names: list[str], *, strip_outer_quotes: bool) -> str:
    if not strip_outer_quotes:
        return ", ".join(ident(n) for n in names)
    q = sql_str('"')
    exprs = []
    for n in names:
        col = ident(n)
        trimmed = f"trim(both {q} from CAST({col} AS VARCHAR))"
        exprs.append(
            f"""CASE
                WHEN {col} IS NULL THEN NULL
                WHEN {col} LIKE '%' || chr(0) || '%' THEN NULL
                WHEN regexp_matches(CAST({col} AS VARCHAR), '[\x01-\x08\x0B\x0C\x0E-\x1F]') THEN NULL
                WHEN instr({trimmed}, '"') > 0 THEN NULL
                ELSE {trimmed}
            END AS {col}"""
        )
    return ", ".join(exprs)


def _dirty_count_sql(names: list[str]) -> str:
    q = sql_str('"')
    parts = []
    for n in names:
        col = ident(n)
        trimmed = f"trim(both {q} from CAST({col} AS VARCHAR))"
        parts.append(
            f"""(CASE
                WHEN {col} IS NULL THEN 0
                WHEN {col} LIKE '%' || chr(0) || '%' THEN 1
                WHEN regexp_matches(CAST({col} AS VARCHAR), '[\x01-\x08\x0B\x0C\x0E-\x1F]') THEN 1
                WHEN instr({trimmed}, '"') > 0 THEN 1
                ELSE 0
            END)"""
        )
    return " + ".join(parts) if parts else "0"


def _is_csv_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        s in msg
        for s in (
            "csv",
            "unterminated",
            "invalid input",
            "sniffing",
            "quote",
            "null byte",
            "\x00",
        )
    )


def _normalize_opts(read_options: dict | None) -> dict:
    opts = dict(read_options or {})
    delim = opts.get("delim", ",")
    quote = opts.get("quote", '"')
    if quote is None:
        quote = ""
    escape = opts.get("escape")
    header = opts.get("header", True)
    if isinstance(header, str):
        header = header.strip().lower() in {"1", "true", "yes"}
    strip = opts.get("strip_outer_quotes")
    if strip is None:
        strip = quote == ""
    on_unrepairable = opts.get("on_unrepairable", "keep_going")
    return {
        "delim": delim,
        "quote": quote,
        "encoding": opts.get("encoding", "latin-1"),
        "header": bool(header),
        "escape": escape,
        "strip_outer_quotes": bool(strip),
        "on_unrepairable": on_unrepairable,
    }


def _copy_parquet(con: duckdb.DuckDBPyConnection, select_sql: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({select_sql}) TO '{sql_path(dest)}' "
        f"(FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def _parquet_count(con: duckdb.DuckDBPyConnection, dest: Path) -> int:
    return con.execute(
        f"SELECT count(*) FROM read_parquet('{sql_path(dest)}')"
    ).fetchone()[0]


def _try_strict(
    con: duckdb.DuckDBPyConnection,
    source: Path,
    dest: Path,
    opts: dict,
    names: list[str],
) -> tuple[int, int]:
    rel = _read_csv_sql(source, opts, names, ignore_errors=False)
    select = _clean_select_sql(names, strip_outer_quotes=opts["strip_outer_quotes"])
    if opts["strip_outer_quotes"]:
        n_nulled = con.execute(
            f"SELECT COALESCE(SUM({_dirty_count_sql(names)}), 0) FROM {rel}"
        ).fetchone()[0]
    else:
        n_nulled = 0
    _copy_parquet(con, f"SELECT {select} FROM {rel}", dest)
    return _parquet_count(con, dest), int(n_nulled)


def _copy_with_repair(
    con: duckdb.DuckDBPyConnection,
    source: Path,
    dest: Path,
    opts: dict,
    names: list[str],
) -> tuple[int, int, int]:
    rel = _read_csv_sql(source, opts, names, ignore_errors=True)
    select = _clean_select_sql(names, strip_outer_quotes=opts["strip_outer_quotes"])
    con.execute("DROP TABLE IF EXISTS rejects")
    con.execute("DROP TABLE IF EXISTS reject_scans")
    con.execute(f"CREATE OR REPLACE TEMP TABLE _good AS SELECT {select} FROM {rel}")

    reject_rows = con.execute(
        "SELECT line, csv_line FROM rejects"
    ).fetchall()
    seen: set[int] = set()
    repaired: list[list[str | None]] = []
    dropped_lines: list[str] = []
    n_nulled = 0
    n_repaired_lines = 0
    for line_no, csv_line in reject_rows:
        if line_no in seen or csv_line is None:
            continue
        seen.add(line_no)
        rows, dropped, nulled = repair_csv_line(
            csv_line,
            delim=opts["delim"],
            quote=opts["quote"],
            n_cols=len(names),
            escape=opts["escape"],
        )
        if rows:
            n_repaired_lines += 1
            repaired.extend(rows)
            n_nulled += nulled
        dropped_lines.extend(dropped)

    if repaired:
        ddl = ", ".join(f"{ident(n)} VARCHAR" for n in names)
        con.execute(f"CREATE OR REPLACE TEMP TABLE _repaired ({ddl})")
        placeholders = ", ".join(["?"] * len(names))
        con.executemany(
            f"INSERT INTO _repaired VALUES ({placeholders})", repaired
        )
        union = (
            "SELECT * FROM _good UNION ALL BY NAME SELECT * FROM _repaired"
        )
    else:
        union = "SELECT * FROM _good"

    _copy_parquet(con, union, dest)
    for phys in dropped_lines:
        print(f"      [DROP] {phys[:200]}")
    return int(n_nulled), n_repaired_lines, len(dropped_lines)


def convert_file(
    input_path: Path,
    output_path: Path,
    read_options: dict | None = None,
    *,
    name: str = "",
) -> ConvertStats:
    t0 = time.perf_counter()
    opts = _normalize_opts(read_options)
    input_path = Path(input_path).expanduser()
    output_path = Path(output_path).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    tmp: Path | None = None
    n_nul_bytes = 0
    source = input_path
    con = duckdb.connect()
    threads = os.environ.get("DUCKDB_THREADS")
    if threads:
        con.execute(f"SET threads TO {int(threads)}")
    try:
        names = read_header_names(
            input_path,
            delim=opts["delim"],
            quote=opts["quote"],
            encoding=opts["encoding"],
            header=opts["header"],
        )
        n_fields_nulled = 0
        n_rows_repaired = 0
        n_rows_dropped = 0
        parsed = False
        try:
            n_rows, n_fields_nulled = _try_strict(
                con, source, output_path, opts, names
            )
            parsed = True
        except Exception as exc:
            if not _is_csv_error(exc):
                raise
        if not parsed:
            tmp = output_path.parent / (output_path.name + NUL_STRIP_SUFFIX)
            n_nul_bytes = strip_nul(input_path, tmp)
            source = tmp
            names = read_header_names(
                source,
                delim=opts["delim"],
                quote=opts["quote"],
                encoding=opts["encoding"],
                header=opts["header"],
            )
            if n_nul_bytes:
                try:
                    n_rows, n_fields_nulled = _try_strict(
                        con, source, output_path, opts, names
                    )
                    parsed = True
                except Exception as exc2:
                    if not _is_csv_error(exc2):
                        raise
        if not parsed:
            n_fields_nulled, n_rows_repaired, n_rows_dropped = (
                _copy_with_repair(con, source, output_path, opts, names)
            )
            n_rows = _parquet_count(con, output_path)
    finally:
        con.close()
        if tmp is not None and tmp.exists():
            tmp.unlink()

    if n_rows_dropped and opts["on_unrepairable"] == "fail":
        raise UnrepairableRowsError(
            f"{name or input_path.name}: {n_rows_dropped} linha(s) sem n campos"
        )
    return ConvertStats(
        name=name or input_path.name,
        n_rows=n_rows,
        n_nul_bytes=n_nul_bytes,
        n_fields_nulled=n_fields_nulled,
        n_rows_repaired=n_rows_repaired,
        n_rows_dropped=n_rows_dropped,
        elapsed_s=time.perf_counter() - t0,
    )


def convert_dataset(dataset: dict) -> ConvertStats:
    return convert_file(
        Path(dataset["input_path"]),
        Path(dataset["output_path"]),
        dataset.get("read_options"),
        name=dataset.get("name", ""),
    )


def load_datasets_config(config_path: str | Path) -> list[dict]:
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["datasets"]


def _print_stats(stats: ConvertStats) -> None:
    print(f"--- {stats.name}")
    print(f"      parquet: {stats.n_rows:,} linhas")
    print(f"      NUL removidos: {stats.n_nul_bytes:,}")
    print(f"      campos anulados: {stats.n_fields_nulled:,}")
    print(f"      linhas reparadas: {stats.n_rows_repaired:,}")
    print(f"      linhas dropadas: {stats.n_rows_dropped:,}")
    print(f"      {stats.elapsed_s:.1f}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSV → Parquet (DuckDB)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--only", help="Só este dataset (campo name)")
    args = parser.parse_args(argv)
    config_path = args.config.expanduser()
    if not config_path.exists():
        print(f"Configuração não encontrada: {config_path}")
        return 1
    datasets = load_datasets_config(config_path)
    if args.only:
        datasets = [d for d in datasets if d.get("name") == args.only]
        if not datasets:
            print(f"Nenhum dataset name={args.only!r} em {config_path}")
            return 1
    exit_code = 0
    for dataset in datasets:
        name = dataset.get("name", "")
        try:
            stats = convert_dataset(dataset)
        except FileNotFoundError as exc:
            print(f"[ERRO] {name}: arquivo não encontrado: {exc}")
            exit_code = 1
            continue
        except UnrepairableRowsError as exc:
            print(f"[FALHA] {exc}")
            exit_code = 1
            continue
        _print_stats(stats)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
