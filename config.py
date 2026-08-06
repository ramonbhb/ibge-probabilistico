"""Configuração do pipeline probabilístico Censo × CPF (bronze → Splink)."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

# normalize_date_sql disponível via features (usado nos notebooks)

# =============================================================================
# AJUSTE AQUI — caminhos, filtro UF e mapeamento de colunas bronze
# =============================================================================
#
# Variáveis de ambiente: OUTPUT_DIR, CPF_ARQUIVO, CENSO_PESSOAS_ARQUIVO,
# CENSO_ESPECIE2_ARQUIVO, COHORT_DEDUP_ARQUIVO, FILTRO_UF

PROB_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROB_DIR / "output")).expanduser()

CENSO_DIR = Path(
    os.environ.get("CENSO_DIR", Path.home() / "singed/bases/bronze/censo")
).expanduser()

CENSO_PESSOAS_ARQUIVO = Path(
    os.environ.get(
        "CENSO_PESSOAS_ARQUIVO",
        CENSO_DIR / "censo_pessoas_2022_20260505.parquet",
    )
).expanduser()

CENSO_ESPECIE2_ARQUIVO = Path(
    os.environ.get(
        "CENSO_ESPECIE2_ARQUIVO",
        CENSO_DIR / "censo_especie2_2022_20260505.parquet",
    )
).expanduser()

CPF_ARQUIVO = Path(
    os.environ.get(
        "CPF_ARQUIVO",
        Path.home() / "singed/bases/bronze/cpf/cpf.parquet",
    )
).expanduser()

COHORT_DIR = Path(
    os.environ.get("COHORT_DIR", Path.home() / "capefe/dados/CohortDados")
).expanduser()

COHORT_DEDUP_ARQUIVO = Path(
    os.environ.get("COHORT_DEDUP_ARQUIVO", COHORT_DIR / "cohort_dedup.parquet")
).expanduser()

# None = nacional; ex.: '35' (SP), '33' (RJ)
_env_uf = os.environ.get("FILTRO_UF", "").strip()
FILTRO_UF: str | None = _env_uf or None

DUCKDB_ARQUIVO = OUTPUT_DIR / "probabilistico.duckdb"

REGISTRO_UNIFICADO = OUTPUT_DIR / "registro_unificado.parquet"
GROUND_TRUTH_CLUSTERS = OUTPUT_DIR / "ground_truth_clusters.parquet"
SPLINK_SETTINGS_DRAFT = OUTPUT_DIR / "splink_settings_draft.json"

CPF_NORM_SQL = "lpad(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 11, '0')"

# Colunas bronze conhecidas (defaults do projeto)
CPF_COL_CPF = "COD_CPF"
CPF_COL_NOME = "NOM_PESSOA"
CPF_COL_DATA_NASC = "DAT_NASCIMENTO"

CENSO_COL_ID_MORADOR = "ID_MORADOR"
CENSO_COL_ID_DOMICILIO = "ID_DOMICILIO"
CENSO_COL_PRIMEIRO_NOME = "PECP0029"
CENSO_COL_SOBRENOME = "PECP0357"
CENSO_COL_DOB_ANO = "PECP0008"
CENSO_COL_DOB_MES = "PECP0036"
CENSO_COL_DOB_DIA = "PECP0006"
CENSO_COL_SETOR = "B0000"
CENSO_COL_ENDERECO = "B0006"
CENSO_COL_QUADRA = "NUM_QUADRA"
CENSO_COL_FACE = "NUM_FACE"
CENSO_COL_SEQ_ESPECIE = "COD_SEQ_ESPECIE"

# Placeholders — preencher após DESCRIBE no NB00 (None = coluna ausente / NULL)
CPF_COL_NOME_MAE: str | None = os.environ.get("CPF_COL_NOME_MAE") or None
CPF_COL_SEXO: str | None = os.environ.get("CPF_COL_SEXO") or None
CPF_COL_CEP: str | None = os.environ.get("CPF_COL_CEP") or None
CPF_COL_ESTADO: str | None = os.environ.get("CPF_COL_ESTADO") or None
CPF_COL_UF: str | None = os.environ.get("CPF_COL_UF") or None

CENSO_COL_NOME_MAE: str | None = os.environ.get("CENSO_COL_NOME_MAE") or None
CENSO_COL_SEXO: str | None = os.environ.get("CENSO_COL_SEXO") or None
CENSO_COL_CEP: str | None = os.environ.get("CENSO_COL_CEP") or None
CENSO_COL_ESTADO: str | None = os.environ.get("CENSO_COL_ESTADO") or None

# espécie2 — chaves de join e CEP domiciliar (ajustar após DESCRIBE)
ESPECIE2_COL_SETOR = "COD_SETOR"
ESPECIE2_COL_QUADRA = "NUM_QUADRA"
ESPECIE2_COL_FACE = "NUM_FACE"
ESPECIE2_COL_ENDERECO = "COD_ENDERECO"
ESPECIE2_COL_SEQ = "SEQ_ESPECIE"
ESPECIE2_COL_CEP: str | None = os.environ.get("ESPECIE2_COL_CEP") or None

DUCKDB_THREADS = int(os.environ.get("DUCKDB_THREADS", "8"))
DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "32GB")


def cpf_norm_sql(col: str) -> str:
    return CPF_NORM_SQL.format(col=col)


def censo_uf_sql(col: str = f"p.{CENSO_COL_SETOR}") -> str:
    return f"substr(lpad(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 12, '0'), 1, 2)"


def censo_dob_sql(
    ano: str = f"p.{CENSO_COL_DOB_ANO}",
    mes: str = f"p.{CENSO_COL_DOB_MES}",
    dia: str = f"p.{CENSO_COL_DOB_DIA}",
) -> str:
    return f"""COALESCE(CAST({ano} AS VARCHAR), '') || '-' ||
        LPAD(COALESCE(CAST({mes} AS VARCHAR), ''), 2, '0') || '-' ||
        LPAD(COALESCE(CAST({dia} AS VARCHAR), ''), 2, '0')"""


def sql_optional_col(alias: str, col: str | None, *, cast_varchar: bool = True) -> str:
    if not col:
        return "NULL"
    expr = f'{alias}."{col}"' if "." not in col else col
    return f"CAST({expr} AS VARCHAR)" if cast_varchar else expr


def uf_filter_clause(uf_expr: str, filtro: str | None = FILTRO_UF) -> str:
    if not filtro:
        return "TRUE"
    safe = filtro.replace("'", "''")
    return f"{uf_expr} = '{safe}'"


def cep_norm_sql(col: str) -> str:
    return f"lpad(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 8, '0')"


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_connection(
    threads: int | None = None,
    memory_limit: str | None = None,
) -> duckdb.DuckDBPyConnection:
    ensure_output_dir()
    con = duckdb.connect(str(DUCKDB_ARQUIVO))
    con.execute(f"PRAGMA threads={threads or DUCKDB_THREADS}")
    con.execute(f"PRAGMA memory_limit='{memory_limit or DUCKDB_MEMORY_LIMIT}'")
    con.execute("SET preserve_insertion_order = false")
    temp_dir = os.environ.get("DUCKDB_TEMP_DIR", str(OUTPUT_DIR / "duckdb_temp"))
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{temp_dir}'")
    return con


def benchmark_checkpoint(con: duckdb.DuckDBPyConnection, name: str, sql: str) -> None:
    result = con.execute(sql).fetchone()
    print(f"[checkpoint] {name}: {result[0]}")


def export_parquet(
    con: duckdb.DuckDBPyConnection,
    table: str,
    *,
    out_name: str | None = None,
    path: Path | None = None,
) -> Path:
    ensure_output_dir()
    name = out_name or table
    out = path or OUTPUT_DIR / f"{name}.parquet"
    con.execute(f"COPY {table} TO '{out}' (FORMAT PARQUET)")
    return out


def table_stats(con: duckdb.DuckDBPyConnection, table: str, distinct_cols: list[str] | None = None):
    distinct_cols = distinct_cols or []
    parts = ["COUNT(*) AS n_rows"] + [
        f"COUNT(DISTINCT {col}) AS n_distinct_{col.lower()}" for col in distinct_cols
    ]
    return con.sql(f"SELECT {', '.join(parts)} FROM {table}").df()


def list_tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    return set(con.sql("SHOW TABLES").df()["name"].tolist())


def load_table_from_parquet(
    con: duckdb.DuckDBPyConnection,
    table: str,
    parquet_path: Path,
) -> bool:
    if not parquet_path.exists():
        return False
    con.execute(f"""
    CREATE OR REPLACE TABLE {table} AS
    SELECT * FROM read_parquet('{parquet_path}')
    """)
    return True


def require_tables(
    con: duckdb.DuckDBPyConnection,
    tables: list[str],
    *,
    notebook_origem: str = "00",
    try_parquet: bool | None = None,
    parquet_map: dict[str, Path] | None = None,
) -> None:
    parquet_map = parquet_map or {
        "registro_unificado": REGISTRO_UNIFICADO,
        "ground_truth_clusters": GROUND_TRUTH_CLUSTERS,
    }
    missing: list[str] = []
    for table in tables:
        if table in list_tables(con):
            continue
        if try_parquet is not False and table in parquet_map:
            if load_table_from_parquet(con, table, parquet_map[table]):
                continue
        missing.append(table)

    if missing:
        raise RuntimeError(
            f"Tabelas ausentes no DuckDB: {missing}\n"
            f"Execute o notebook {notebook_origem} por completo antes de continuar.\n"
            f"DuckDB: {DUCKDB_ARQUIVO}"
        )


def require_input(path: Path, *, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} não encontrado: {path}")


def print_paths() -> None:
    print("OUTPUT_DIR:", OUTPUT_DIR)
    print("CPF_ARQUIVO:", CPF_ARQUIVO)
    print("CENSO_PESSOAS_ARQUIVO:", CENSO_PESSOAS_ARQUIVO)
    print("CENSO_ESPECIE2_ARQUIVO:", CENSO_ESPECIE2_ARQUIVO)
    print("COHORT_DEDUP_ARQUIVO:", COHORT_DEDUP_ARQUIVO)
    print("FILTRO_UF:", FILTRO_UF)
    print("DUCKDB_ARQUIVO:", DUCKDB_ARQUIVO)
