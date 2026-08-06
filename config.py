"""Configuração do pipeline probabilístico Censo × CPF (bronze → Splink)."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from features import normalize_date_sql


def normalize_uf_filtro(filtro: str | int | float | None) -> str | None:
    """Normaliza FILTRO_UF para string SQL (aceita int/float do notebook)."""
    if filtro is None:
        return None
    if isinstance(filtro, bool):
        return None
    if isinstance(filtro, int):
        return f"{filtro:02d}"
    if isinstance(filtro, float) and filtro.is_integer():
        return f"{int(filtro):02d}"
    s = str(filtro).strip()
    return s or None


# =============================================================================
# AJUSTE AQUI — caminhos, filtro UF e mapeamento de colunas bronze
# =============================================================================
#
# Variáveis de ambiente: OUTPUT_DIR, CPF_ARQUIVO, CENSO_PESSOAS_ARQUIVO,
# CENSO_CEP_ARQUIVO, COHORT_DEDUP_ARQUIVO, FILTRO_UF

PROB_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(
    os.environ.get("OUTPUT_DIR", Path.home() / "data/probabilistico_output")
).expanduser()

CENSO_DIR = Path(
    os.environ.get("CENSO_DIR", Path.home() / "singed/bases/bronze/censo")
).expanduser()

CENSO_RAW_DIR = Path(
    os.environ.get("CENSO_RAW_DIR", Path.home() / "singed/bases/raw/censo")
).expanduser()

CENSO_CEP_ARQUIVO = Path(
    os.environ.get(
        "CENSO_CEP_ARQUIVO",
        CENSO_RAW_DIR / "data_cep_uniq.csv",
    )
).expanduser()

CENSO_PESSOAS_ARQUIVO = Path(
    os.environ.get(
        "CENSO_PESSOAS_ARQUIVO",
        CENSO_DIR / "censo_pessoas_2022_20260505.parquet",
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

# None = nacional. Prioridade: env FILTRO_UF > valor abaixo.
FILTRO_UF: str | int | None = None  # ex.: 42 (SC)
_env_uf = os.environ.get("FILTRO_UF", "").strip()
if _env_uf:
    FILTRO_UF = _env_uf
FILTRO_UF = normalize_uf_filtro(FILTRO_UF)

DUCKDB_ARQUIVO = OUTPUT_DIR / "probabilistico.duckdb"

REGISTRO_UNIFICADO = OUTPUT_DIR / "registro_unificado.parquet"
GROUND_TRUTH_CLUSTERS = OUTPUT_DIR / "ground_truth_clusters.parquet"
SPLINK_SETTINGS_DRAFT = OUTPUT_DIR / "splink_settings_draft.json"

CPF_NORM_SQL = "lpad(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 11, '0')"

# Colunas bronze conhecidas (defaults do projeto)
CPF_COL_CPF = "COD_CPF"
CPF_COL_NOME = "NOM_PESSOA"
CPF_COL_DATA_NASC = "DAT_NASCIMENTO"
CPF_COL_NOME_MAE = "NOM_MAE"
CPF_COL_SEXO = "COD_SEXO"
CPF_COL_UF = "COD_UFMUN"
CPF_COL_CEP = "COD_CEP"

CENSO_COL_ID_MORADOR = "ID_MORADOR"
CENSO_COL_ID_DOMICILIO = "ID_DOMICILIO"
CENSO_COL_PRIMEIRO_NOME = "PECP0029"
CENSO_COL_SOBRENOME = "PECP0357"
CENSO_COL_DOB_ANO = "PECP0008"
CENSO_COL_DOB_MES = "PECP0036"
CENSO_COL_DOB_DIA = "PECP0006"
CENSO_COL_SEXO = "PECP0002"
CENSO_COL_RELACAO = "PECP0004"
CENSO_COL_UF = "B0001"
# Chaves de join pessoas ↔ data_cep_uniq.csv
CENSO_COL_SETOR = "B0000"
CENSO_COL_QUADRA = "NUM_QUADRA"
CENSO_COL_FACE = "NUM_FACE"

# Colunas em data_cep_uniq.csv
CEP_COL_UF = "COD_UF"
CEP_COL_MUNICIPIO = "COD_MUNICIPIO"
CEP_COL_DISTRITO = "COD_DISTRITO"
CEP_COL_SUBDISTRITO = "COD_SUBDISTRITO"
CEP_COL_SETOR = "COD_SETOR"
CEP_COL_QUADRA = "NUM_QUADRA"
CEP_COL_FACE = "NUM_FACE"
CEP_COL_CEP = "CEP"
CEP_COL_LOG = "NO_LOG"

USE_PHONETIC_STRIP_VOWELS = os.environ.get(
    "USE_PHONETIC_STRIP_VOWELS", "false"
).lower() in ("1", "true", "yes")

DUCKDB_THREADS = int(os.environ.get("DUCKDB_THREADS", "20"))
DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "300GB")


def cpf_norm_sql(col: str) -> str:
    return CPF_NORM_SQL.format(col=col)


def setor_norm_sql(col: str) -> str:
    """Normaliza código de setor censitário (15 díg.) para join."""
    return (
        f"lpad(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 15, '0')"
    )


def cpf_uf_sql(col: str) -> str:
    """UF (2 dígitos IBGE) a partir de COD_UFMUN ou similar."""
    digits = f"lpad(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 7, '0')"
    return f"substr({digits}, 1, 2)"


def censo_uf_sql(alias: str = "p") -> str:
    """UF (2 díg.) a partir do setor censitário B0000."""
    return f"substr({setor_norm_sql(f'{alias}.{CENSO_COL_SETOR}')}, 1, 2)"


def cpf_uf_expr(alias: str = "c") -> str:
    return cpf_uf_sql(f'{alias}."{CPF_COL_UF}"')


def censo_uf_expr(alias: str = "p") -> str:
    return censo_uf_sql(alias)


def censo_cep_join_on(p_alias: str = "p", cep_alias: str = "k") -> str:
    """Condição ON para join censo_pessoas ↔ lookup de CEP."""
    return f"""{setor_norm_sql(f'{p_alias}.{CENSO_COL_SETOR}')} = {cep_alias}.cod_setor_norm
        AND CAST({p_alias}.{CENSO_COL_QUADRA} AS VARCHAR) = {cep_alias}.num_quadra
        AND CAST({p_alias}.{CENSO_COL_FACE} AS VARCHAR) = {cep_alias}.num_face"""


def materialize_censo_cep_lookup(
    con: duckdb.DuckDBPyConnection,
    *,
    source_path: Path | None = None,
    target_table: str = "censo_cep_lookup",
    filtro_uf: str | int | float | None = FILTRO_UF,
) -> None:
    """Materializa lookup de CEP a partir de data_cep_uniq.csv (opcionalmente filtrado por UF)."""
    path = (source_path or CENSO_CEP_ARQUIVO).expanduser()
    uf_clause = "TRUE"
    uf = normalize_uf_filtro(filtro_uf)
    if uf:
        safe = uf.replace("'", "''")
        uf_col = f'c."{CEP_COL_UF}"'
        uf_clause = (
            f"lpad(regexp_replace(CAST({uf_col} AS VARCHAR), '[^0-9]', '', 'g'), 2, '0') = '{safe}'"
        )

    con.execute(f"""
    CREATE OR REPLACE TABLE {target_table} AS
    SELECT
        {setor_norm_sql(f'c."{CEP_COL_SETOR}"')} AS cod_setor_norm,
        CAST(c."{CEP_COL_QUADRA}" AS VARCHAR) AS num_quadra,
        CAST(c."{CEP_COL_FACE}" AS VARCHAR) AS num_face,
        {cep_norm_sql(f'MIN(c."{CEP_COL_CEP}")')} AS cep
    FROM read_csv('{path}', header=true, auto_detect=true) c
    WHERE {uf_clause}
    GROUP BY 1, 2, 3
    """)


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


def uf_filter_clause(
    uf_expr: str,
    filtro: str | int | float | None = FILTRO_UF,
) -> str:
    uf = normalize_uf_filtro(filtro)
    if not uf:
        return "TRUE"
    safe = uf.replace("'", "''")
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


SPLINK_INPUT_VIEW = "splink_input"


def materialize_splink_input(con: duckdb.DuckDBPyConnection) -> None:
    """View Splink: registro_unificado + coluna cluster (labels GT)."""
    con.execute(f"""
    CREATE OR REPLACE VIEW {SPLINK_INPUT_VIEW} AS
    SELECT r.*, g.cluster
    FROM registro_unificado r
    LEFT JOIN ground_truth_clusters g ON r.unique_id = g.unique_id
    """)


def get_splink_db_api(con: duckdb.DuckDBPyConnection):
    """DuckDBAPI Splink reutilizando conexão configurada (threads, memory_limit)."""
    from splink import DuckDBAPI

    return DuckDBAPI(connection=con)


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
    print("CENSO_CEP_ARQUIVO:", CENSO_CEP_ARQUIVO)
    print("COHORT_DEDUP_ARQUIVO:", COHORT_DEDUP_ARQUIVO)
    print("FILTRO_UF:", FILTRO_UF)
    print("USE_PHONETIC_STRIP_VOWELS:", USE_PHONETIC_STRIP_VOWELS)
    print("DUCKDB_ARQUIVO:", DUCKDB_ARQUIVO)
