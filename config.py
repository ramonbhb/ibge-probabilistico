"""Configuração do pipeline probabilístico Censo × CPF (bronze → Splink)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

from features import normalize_date_sql

# Distingue "argumento não informado" de "None = sem filtro", já que None é
# um valor válido para FILTRO_UF/FILTRO_MUNICIPIO.
_UNSET: Any = object()


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


def normalize_municipio_filtro(filtro: str | int | float | None) -> str | None:
    """Normaliza FILTRO_MUNICIPIO para código IBGE 7 dígitos."""
    if filtro is None:
        return None
    if isinstance(filtro, bool):
        return None
    digits = "".join(ch for ch in str(filtro).strip() if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(7)[-7:]


# =============================================================================
# PARÂMETROS DE ANÁLISE — ajuste aqui a cada rodada
# =============================================================================

# Recorte geográfico. None = sem filtro (base nacional).
FILTRO_UF: str | int | None = None            # ex.: 42 (SC)
FILTRO_MUNICIPIO: str | int | None = 2111300  # ex.: 4205407 (Florianópolis)

FILTRO_UF = normalize_uf_filtro(FILTRO_UF)
FILTRO_MUNICIPIO = normalize_municipio_filtro(FILTRO_MUNICIPIO)

# True = gera também as colunas *_phon_sv (fonética agressiva, remove vogais).
USE_PHONETIC_STRIP_VOWELS = False

# --- Limpeza (NB00b) ---------------------------------------------------------

# Remove do CPF quem morreu antes do Censo. Conservador de propósito: a data de
# referência do Censo 2022 é 31/07/2022, então mortes em 2021 também não seriam
# enumeradas, mas manter 2021 evita descartar registro por erro de digitação no
# ano. Quem tem ano de óbito nulo (vivo) e o Censo inteiro nunca são afetados.
ANO_OBITO_CORTE = 2021

# Faixa aceita para o ano de nascimento; fora dela a data vira NULL.
ANO_NASCIMENTO_MIN = 1900

# Categorias de sexo que discriminam. O normalize_sexo_sql devolve a inicial do
# que não for M/F ('O' de outro, 'I' de ignorado, '9' de não informado), e para
# o ExactMatch dois resíduos iguais seriam concordância. Só entram os que
# separam a população; o resto vira NULL. Confira a distribuição no NB00b antes
# de mexer: se a base tiver uma terceira categoria de verdade e com volume,
# anulá-la joga sinal fora.
SEXO_VALIDOS = ("M", "F")


def set_filtros(
    *,
    uf: str | int | float | None = _UNSET,
    municipio: str | int | float | None = _UNSET,
) -> tuple[str | None, str | None]:
    """Sobrescreve os filtros geográficos para a sessão atual.

    Use isto no notebook em vez de reatribuir FILTRO_UF/FILTRO_MUNICIPIO:
    `from config import FILTRO_UF` cria uma cópia do nome, e reatribuí-la não
    altera o estado lido pelas funções de filtro.
    """
    global FILTRO_UF, FILTRO_MUNICIPIO
    if uf is not _UNSET:
        FILTRO_UF = normalize_uf_filtro(uf)
    if municipio is not _UNSET:
        FILTRO_MUNICIPIO = normalize_municipio_filtro(municipio)
    return FILTRO_UF, FILTRO_MUNICIPIO


# =============================================================================
# CAMINHOS E RECURSOS — variam por máquina, aceitam variável de ambiente
# =============================================================================
#
# OUTPUT_DIR, CENSO_DIR, CENSO_RAW_DIR, CENSO_CEP_ARQUIVO,
# CENSO_PESSOAS_ARQUIVO, CPF_ARQUIVO, COHORT_DIR, COHORT_DEDUP_ARQUIVO,
# DUCKDB_TEMP_DIR, DUCKDB_THREADS, DUCKDB_MEMORY_LIMIT

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

DUCKDB_ARQUIVO = OUTPUT_DIR / "probabilistico.duckdb"

REGISTRO_UNIFICADO = OUTPUT_DIR / "registro_unificado.parquet"
REGISTRO_LIMPO = OUTPUT_DIR / "registro_limpo.parquet"

# Artefatos do treino (NB02), consumidos pela validação (NB03)
SPLINK_MODEL_JSON = OUTPUT_DIR / "splink_model.json"
SPLINK_PREDICTIONS = OUTPUT_DIR / "splink_predictions.parquet"
SPLINK_CLUSTERS = OUTPUT_DIR / "splink_clusters.parquet"
METRICAS_COHORT = OUTPUT_DIR / "metricas_cohort.csv"

CPF_NORM_SQL = "lpad(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 11, '0')"

# Colunas bronze conhecidas (defaults do projeto)
CPF_COL_CPF = "COD_CPF"
CPF_COL_NOME = "NOM_PESSOA"
CPF_COL_DATA_NASC = "DAT_NASCIMENTO"
CPF_COL_NOME_MAE = "NOM_MAE"
CPF_COL_SEXO = "COD_SEXO"
CPF_COL_UF = "COD_UFMUN"
CPF_COL_CEP = "COD_CEP"
# Opcional no bronze: o NB00 detecta a presença e cai para NULL se não existir.
CPF_COL_ANO_OBITO = "ANO_OBITO"

CENSO_COL_ID_MORADOR = "ID_MORADOR"
CENSO_COL_ID_DOMICILIO = "ID_DOMICILIO"
CENSO_COL_PRIMEIRO_NOME = "PECP0029"
CENSO_COL_SOBRENOME = "PECP0357"
CENSO_COL_DOB_ANO = "PECP0008"
CENSO_COL_DOB_MES = "PECP0036"
CENSO_COL_DOB_DIA = "PECP0006"
CENSO_COL_SEXO = "PECP0002"
CENSO_COL_RELACAO = "PECP0004"
# Mutuamente exclusivas, não valor e fallback: PECP0003 (3 díg.) só é preenchida
# para quem tem 1 ano ou mais, PECP0030 (2 díg.) só para menores de 1 ano.
CENSO_COL_IDADE_ANOS = "PECP0401"
CENSO_COL_IDADE_MESES = "PECP0030"
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

DUCKDB_THREADS = int(os.environ.get("DUCKDB_THREADS", "20"))
DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "300GB")

ANO_REFERENCIA_CENSO = 2022
IDADE_MAX = 120
# PECP0030 cobre só o primeiro ano de vida.
CENSO_IDADE_MESES_MAX = 11


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


def cpf_municipio_sql(col: str) -> str:
    """Código IBGE município (7 díg.) a partir de COD_UFMUN."""
    return f"lpad(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 7, '0')"


def censo_municipio_sql(alias: str = "p") -> str:
    """Código IBGE município (7 díg.) a partir do setor censitário B0000."""
    return f"substr({setor_norm_sql(f'{alias}.{CENSO_COL_SETOR}')}, 1, 7)"


def cpf_municipio_expr(alias: str = "c") -> str:
    return cpf_municipio_sql(f'{alias}."{CPF_COL_UF}"')


def censo_municipio_expr(alias: str = "p") -> str:
    return censo_municipio_sql(alias)


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
    filtro_uf: str | int | float | None = _UNSET,
    filtro_municipio: str | int | float | None = _UNSET,
) -> None:
    """Materializa lookup de CEP a partir de data_cep_uniq.csv (filtro UF e/ou município)."""
    path = (source_path or CENSO_CEP_ARQUIVO).expanduser()
    clauses: list[str] = []
    uf = normalize_uf_filtro(FILTRO_UF if filtro_uf is _UNSET else filtro_uf)
    if uf:
        safe = uf.replace("'", "''")
        uf_col = f'c."{CEP_COL_UF}"'
        clauses.append(
            f"lpad(regexp_replace(CAST({uf_col} AS VARCHAR), '[^0-9]', '', 'g'), 2, '0') = '{safe}'"
        )
    mun = normalize_municipio_filtro(
        FILTRO_MUNICIPIO if filtro_municipio is _UNSET else filtro_municipio
    )
    if mun:
        safe_mun = mun.replace("'", "''")
        mun_col = f'c."{CEP_COL_MUNICIPIO}"'
        clauses.append(
            f"lpad(regexp_replace(CAST({mun_col} AS VARCHAR), '[^0-9]', '', 'g'), 7, '0') = '{safe_mun}'"
        )
    where_clause = " AND ".join(clauses) if clauses else "TRUE"

    con.execute(f"""
    CREATE OR REPLACE TABLE {target_table} AS
    SELECT
        {setor_norm_sql(f'c."{CEP_COL_SETOR}"')} AS cod_setor_norm,
        CAST(c."{CEP_COL_QUADRA}" AS VARCHAR) AS num_quadra,
        CAST(c."{CEP_COL_FACE}" AS VARCHAR) AS num_face,
        {cep_norm_sql(f'MIN(c."{CEP_COL_CEP}")')} AS cep
    FROM read_csv('{path}', header=true, auto_detect=true) c
    WHERE {where_clause}
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


def idade_int_sql(col: str) -> str:
    """Inteiro tolerante a texto com espaço, zero à esquerda ou casa decimal."""
    return (
        f"TRY_CAST(TRY_CAST(NULLIF(TRIM(CAST({col} AS VARCHAR)), '') AS DOUBLE) "
        f"AS INTEGER)"
    )


def idade_censo_sql(alias: str = "p") -> str:
    """Idade em anos completos no Censo.

    As duas colunas se dividem a população em vez de uma cobrir a outra:
    PECP0003 vale para 1 ano ou mais, PECP0030 para menores de 1 ano. Quem tem
    meses preenchidos tem 0 ano completo — não é preciso dividir por 12.

    O terceiro ramo é defensivo: PECP0003 = 0 está fora do documentado, mas se
    aparecer significa a mesma coisa que o ramo dos meses e não custa aceitar.
    """
    anos = idade_int_sql(f'{alias}."{CENSO_COL_IDADE_ANOS}"')
    meses = idade_int_sql(f'{alias}."{CENSO_COL_IDADE_MESES}"')
    return f"""CASE
        WHEN {anos} BETWEEN 1 AND {IDADE_MAX} THEN {anos}
        WHEN {meses} BETWEEN 0 AND {CENSO_IDADE_MESES_MAX} THEN 0
        WHEN {anos} = 0 THEN 0
        ELSE NULL
    END"""


def idade_cpf_sql(dob_expr: str, ano: int = ANO_REFERENCIA_CENSO) -> str:
    """Idade em anos na referência do Censo (usa só o ano da data de nascimento)."""
    ano_nasc = f"TRY_CAST(substr(CAST({dob_expr} AS VARCHAR), 1, 4) AS INTEGER)"
    return f"""CASE
        WHEN {dob_expr} IS NULL OR TRIM(CAST({dob_expr} AS VARCHAR)) = '' THEN NULL
        WHEN {ano_nasc} BETWEEN {ANO_NASCIMENTO_MIN} AND {ano}
        THEN {ano} - {ano_nasc}
        ELSE NULL
    END"""


# =============================================================================
# Limpeza (NB00b)
# =============================================================================
#
# O alvo é um só: valor-sentinela que o SQL trata como igualdade real. Em
# `l.cep = r.cep` a comparação '' = '' e '00000000' = '00000000' é verdadeira,
# então ausência vira par candidato e, nas deterministic_rules, vira match
# determinístico na estimativa do prior. NULL não casa com NULL, que é o
# comportamento que queremos para dado ausente.

TABELA_LIMPA = "registro_limpo"

# Identificam a linha e não entram em comparação nem em blocking; '' nelas não
# fabrica par, então ficam fora do NULLIF em massa.
COLUNAS_ESTRUTURAIS = frozenset(
    {"unique_id", "origem", "cpf_norm", "person_id_censo", "id_domicilio"}
)


def obito_antes_do_censo_sql(
    col: str = "ano_obito", corte: int = ANO_OBITO_CORTE
) -> str:
    """True só para óbito comprovadamente anterior ao Censo.

    Ano nulo (vivo, e todo o Censo) e ano zero (sentinela) são False, então a
    linha fica. Anos absurdos no futuro (9999) também ficam: o corte é só o
    limite inferior, para nunca descartar por ruído.
    """
    ano = f"TRY_CAST({col} AS INTEGER)"
    return f"({ano} IS NOT NULL AND {ano} > 0 AND {ano} < {corte})"


def dob_valida_sql(
    col: str = "data_nascimento", ano: int = ANO_REFERENCIA_CENSO
) -> str:
    """Data de nascimento utilizável, ou NULL.

    Exige data real (descarta 2022-02-30, que o normalize_date_sql deixa passar
    quando a string já vem em ISO) e ano dentro da mesma faixa que a idade usa.
    """
    s = f"NULLIF(TRIM(CAST({col} AS VARCHAR)), '')"
    return f"""CASE
        WHEN TRY_CAST({s} AS DATE) IS NULL THEN NULL
        WHEN TRY_CAST(substr({s}, 1, 4) AS INTEGER)
             BETWEEN {ANO_NASCIMENTO_MIN} AND {ano} THEN {s}
        ELSE NULL
    END"""


def cep_valido_sql(col: str = "cep") -> str:
    """CEP ausente vira NULL.

    O lpad do cep_norm_sql transforma CEP vazio do CPF em '00000000' e o Censo
    usa ''. São duas grafias de ausência, e '00000000' não é endereço.
    """
    digitos = f"regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g')"
    return f"CASE WHEN {digitos} IN ('', '00000000') THEN NULL ELSE {digitos} END"


def sexo_valido_sql(col: str = "sexo") -> str:
    """Sexo fora de SEXO_VALIDOS vira NULL (outro, ignorado, não informado)."""
    s = f"upper(NULLIF(TRIM(CAST({col} AS VARCHAR)), ''))"
    lista = ", ".join(f"'{v}'" for v in SEXO_VALIDOS)
    return f"CASE WHEN {s} IN ({lista}) THEN {s} ELSE NULL END"


def texto_nao_vazio_sql(col: str) -> str:
    """String vazia vira NULL."""
    return f"NULLIF(TRIM(CAST({col} AS VARCHAR)), '')"


def limpeza_columns_sql(colunas: dict[str, str]) -> dict[str, str]:
    """Expressão de limpeza por coluna, a partir do mapa nome → tipo do DESCRIBE.

    Só colunas VARCHAR recebem o NULLIF em massa; `idade` e `ano_obito` são
    inteiros e passariam a string se caíssem na regra genérica.
    """
    out: dict[str, str] = {}
    for nome, tipo in colunas.items():
        if nome in COLUNAS_ESTRUTURAIS or not tipo.upper().startswith("VARCHAR"):
            out[nome] = nome
        elif nome == "data_nascimento":
            out[nome] = dob_valida_sql(nome)
        elif nome == "cep":
            out[nome] = cep_valido_sql(nome)
        elif nome == "sexo":
            out[nome] = sexo_valido_sql(nome)
        else:
            out[nome] = texto_nao_vazio_sql(nome)

    # A idade do CPF é derivada da data de nascimento: se a data cai, a idade
    # não pode sobreviver. No Censo a idade vem de PECP0003, independente.
    if "idade" in out and "data_nascimento" in colunas:
        out["idade"] = (
            f"CASE WHEN origem = 'cpf' AND {dob_valida_sql()} IS NULL "
            f"THEN NULL ELSE idade END"
        )
    return out


def sql_optional_col(alias: str, col: str | None, *, cast_varchar: bool = True) -> str:
    if not col:
        return "NULL"
    expr = f'{alias}."{col}"' if "." not in col else col
    return f"CAST({expr} AS VARCHAR)" if cast_varchar else expr


def uf_filter_clause(
    uf_expr: str,
    filtro: str | int | float | None = _UNSET,
) -> str:
    uf = normalize_uf_filtro(FILTRO_UF if filtro is _UNSET else filtro)
    if not uf:
        return "TRUE"
    safe = uf.replace("'", "''")
    return f"{uf_expr} = '{safe}'"


def municipio_filter_clause(
    mun_expr: str,
    filtro: str | int | float | None = _UNSET,
) -> str:
    mun = normalize_municipio_filtro(FILTRO_MUNICIPIO if filtro is _UNSET else filtro)
    if not mun:
        return "TRUE"
    safe = mun.replace("'", "''")
    return f"{mun_expr} = '{safe}'"


def geo_filter_clause(
    uf_expr: str,
    mun_expr: str,
    *,
    filtro_uf: str | int | float | None = _UNSET,
    filtro_municipio: str | int | float | None = _UNSET,
) -> str:
    """Combina filtros UF e município (AND). Município IBGE 7 díg. já inclui UF."""
    parts = [
        uf_filter_clause(uf_expr, filtro_uf),
        municipio_filter_clause(mun_expr, filtro_municipio),
    ]
    active = [p for p in parts if p != "TRUE"]
    if not active:
        return "TRUE"
    return " AND ".join(f"({p})" for p in active)


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


def materialize_splink_input(
    con: duckdb.DuckDBPyConnection, *, tabela: str | None = None
) -> str:
    """View de entrada do Splink. Sem labels: a coorte só entra no NB03.

    Prefere a tabela limpa do NB00b. Cair para `registro_unificado` significa
    rodar com '' e '00000000' onde deveria haver NULL, o que infla os blocos,
    então o aviso é ruidoso de propósito.
    """
    if tabela is None:
        tabelas = list_tables(con)
        tabela = TABELA_LIMPA if TABELA_LIMPA in tabelas else "registro_unificado"
        if tabela != TABELA_LIMPA:
            print(
                f"AVISO: {TABELA_LIMPA} não existe — usando registro_unificado, "
                "com os valores-sentinela ainda no lugar. Rode o NB00b."
            )
    con.execute(f"""
    CREATE OR REPLACE VIEW {SPLINK_INPUT_VIEW} AS
    SELECT * FROM {tabela}
    """)
    print(f"{SPLINK_INPUT_VIEW} → {tabela}")
    return tabela


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
        TABELA_LIMPA: REGISTRO_LIMPO,
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
    print("FILTRO_MUNICIPIO:", FILTRO_MUNICIPIO)
    print("USE_PHONETIC_STRIP_VOWELS:", USE_PHONETIC_STRIP_VOWELS)
    print("ANO_OBITO_CORTE:", ANO_OBITO_CORTE)
    print("ANO_NASCIMENTO_MIN:", ANO_NASCIMENTO_MIN)
    print("SEXO_VALIDOS:", SEXO_VALIDOS)
    print("DUCKDB_ARQUIVO:", DUCKDB_ARQUIVO)
