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
FILTRO_MUNICIPIO: str | int | None = 2111300  # IBGE 7 díg.; None = sem filtro

FILTRO_UF = normalize_uf_filtro(FILTRO_UF)
FILTRO_MUNICIPIO = normalize_municipio_filtro(FILTRO_MUNICIPIO)

# --- Limpeza (NB00b) ---------------------------------------------------------

# Remove do CPF quem tem ano_obito <= corte (inclusive). Quem tem ano nulo
# (vivo) e o Censo inteiro nunca são afetados. Anos absurdos no futuro (9999)
# ficam: só o intervalo (0, corte] é motivo de exclusão.
# Para não remover ninguém: ANO_OBITO_CORTE = 0 (exige ano > 0 AND ano <= corte).
# Subir o corte (ex. 2030) remove mais, não desliga o filtro.
ANO_OBITO_CORTE = 0

# Faixa aceita para o ano de nascimento; fora dela a data vira NULL.
ANO_NASCIMENTO_MIN = 1900

# Data de referência para idade do CPF (anos completos).
DATA_REFERENCIA_IDADE = "2022-08-01"

# Categorias de sexo que discriminam. O normalize_sexo_sql devolve a inicial do
# que não for M/F ('O' de outro, 'I' de ignorado, '9' de não informado), e para
# o ExactMatch dois resíduos iguais seriam concordância. Só entram os que
# separam a população; o resto vira NULL. Confira a distribuição no NB00b antes
# de mexer: se a base tiver uma terceira categoria de verdade e com volume,
# anulá-la joga sinal fora.
SEXO_VALIDOS = ("M", "F")

# Corte operacional: clustering (02b), métricas (03) e atribuição (04).
# Override: export THRESHOLD_AVALIACAO=0.98
THRESHOLD_AVALIACAO = float(os.environ.get("THRESHOLD_AVALIACAO", "0.99"))

# Chunks opcionais do predict() Splink (volume grande). None = default da lib.
# Override: export PREDICT_NUM_CHUNKS_LEFT=4 PREDICT_NUM_CHUNKS_RIGHT=4
def _optional_positive_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    return int(raw)


PREDICT_NUM_CHUNKS_LEFT = _optional_positive_int("PREDICT_NUM_CHUNKS_LEFT")
PREDICT_NUM_CHUNKS_RIGHT = _optional_positive_int("PREDICT_NUM_CHUNKS_RIGHT")


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

# NB00: bases separadas (sem empilhar). NB00b limpa cada uma.
CENSO_REGISTROS = OUTPUT_DIR / "censo_registros.parquet"
CPF_REGISTROS = OUTPUT_DIR / "cpf_registros.parquet"
CENSO_LIMPO = OUTPUT_DIR / "censo_limpo.parquet"
CPF_LIMPO = OUTPUT_DIR / "cpf_limpo.parquet"

TABELA_CENSO_REGISTROS = "censo_registros"
TABELA_CPF_REGISTROS = "cpf_registros"
TABELA_CENSO_LIMPA = "censo_limpo"
TABELA_CPF_LIMPA = "cpf_limpo"

# JSON no treino (02); predictions/clusters na aplicação (02b); 03 avalia; 04 atribui
SPLINK_MODEL_JSON = OUTPUT_DIR / "splink_model.json"
SPLINK_PREDICTIONS = OUTPUT_DIR / "splink_predictions.parquet"
SPLINK_CLUSTERS = OUTPUT_DIR / "splink_clusters.parquet"
METRICAS_AVALIACAO = OUTPUT_DIR / "metricas_avaliacao.csv"
METRICAS_SWEEP = OUTPUT_DIR / "metricas_sweep.csv"
METRICAS_ATRIBUICAO = OUTPUT_DIR / "metricas_atribuicao.csv"
SPLINK_ATRIBUICAO = OUTPUT_DIR / "splink_atribuicao.parquet"
MODELS_DIR = PROB_DIR / "models"

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
# Idade no Censo: PECP0401 é a variável auxiliar calculada (0–140 anos, universo).
# PECP0003/PECP0030 são do questionário (amostra) e ficam só para diagnóstico.
CENSO_COL_IDADE_CALC = "PECP0401"
CENSO_COL_IDADE_ANOS_QUEST = "PECP0003"
CENSO_COL_IDADE_MESES = "PECP0030"
# Alias legado usado no diagnóstico do NB00
CENSO_COL_IDADE_ANOS = CENSO_COL_IDADE_CALC
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
CENSO_IDADE_MAX = 140


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
    """Idade em anos no Censo via PECP0401 (variável calculada, 0–140)."""
    idade = idade_int_sql(f'{alias}."{CENSO_COL_IDADE_CALC}"')
    return f"CASE WHEN {idade} BETWEEN 0 AND {CENSO_IDADE_MAX} THEN {idade} ELSE NULL END"


def idade_cpf_sql(
    dob_expr: str, data_ref: str = DATA_REFERENCIA_IDADE
) -> str:
    """Idade em anos completos na data de referência (DATA_REFERENCIA_IDADE)."""
    ano_ref = int(str(data_ref)[:4])
    dob_date = f"TRY_CAST({dob_expr} AS DATE)"
    ano_nasc = f"EXTRACT(YEAR FROM {dob_date})"
    return f"""CASE
        WHEN {dob_expr} IS NULL OR TRIM(CAST({dob_expr} AS VARCHAR)) = '' THEN NULL
        WHEN {dob_date} IS NULL THEN NULL
        WHEN {ano_nasc} BETWEEN {ANO_NASCIMENTO_MIN} AND {ano_ref}
        THEN CAST(EXTRACT(YEAR FROM age(DATE '{data_ref}', {dob_date})) AS INTEGER)
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

# Identificam a linha e não entram em comparação nem em blocking; '' nelas não
# fabrica par, então ficam fora do NULLIF em massa.
COLUNAS_ESTRUTURAIS = frozenset(
    {"unique_id", "origem", "cpf_norm", "person_id_censo", "id_domicilio"}
)


def obito_antes_do_censo_sql(
    col: str = "ano_obito", corte: int = ANO_OBITO_CORTE
) -> str:
    """True quando ano_obito está em (0, corte] — remove o registro.

    Ano nulo (vivo, e todo o Censo) e ano zero (sentinela) são False, então a
    linha fica. Anos absurdo no futuro (9999) também ficam.
    """
    ano = f"TRY_CAST({col} AS INTEGER)"
    return f"({ano} IS NOT NULL AND {ano} > 0 AND {ano} <= {corte})"


def sem_nome_sql(nome_col: str = "nome_completo") -> str:
    """True quando o nome é nulo ou em branco (Censo e CPF)."""
    return f"({texto_nao_vazio_sql(nome_col)} IS NULL)"


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

    # Idade do CPF: recalcula anos completos em DATA_REFERENCIA_IDADE a partir
    # da DOB já validada. Se a data cai, a idade cai. Censo mantém PECP0401.
    if "idade" in out and "data_nascimento" in colunas:
        dob = dob_valida_sql("data_nascimento")
        out["idade"] = (
            f"CASE WHEN origem = 'cpf' THEN {idade_cpf_sql(dob)} ELSE idade END"
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

_DOB_PARTS_SQL = """
        CASE
            WHEN t.data_nascimento IS NULL
              OR TRIM(CAST(t.data_nascimento AS VARCHAR)) = '' THEN NULL
            ELSE substr(CAST(t.data_nascimento AS VARCHAR), 1, 4)
        END AS ano_nascimento,
        CASE
            WHEN t.data_nascimento IS NULL
              OR TRIM(CAST(t.data_nascimento AS VARCHAR)) = '' THEN NULL
            ELSE substr(CAST(t.data_nascimento AS VARCHAR), 6, 2)
        END AS mes_nascimento,
        CASE
            WHEN t.data_nascimento IS NULL
              OR TRIM(CAST(t.data_nascimento AS VARCHAR)) = '' THEN NULL
            ELSE substr(CAST(t.data_nascimento AS VARCHAR), 9, 2)
        END AS dia_nascimento
"""


def materialize_splink_input(
    con: duckdb.DuckDBPyConnection,
    *,
    censo_table: str | None = None,
    cpf_table: str | None = None,
) -> tuple[str, str]:
    """View `splink_input` = UNION das duas bases limpas (+ partes DOB).

    Prefere `censo_limpo` / `cpf_limpo`. Se faltarem, cai nas tabelas do NB00
    (ainda com sentinelas) e avisa.
    """
    tabelas = list_tables(con)
    censo = censo_table or (
        TABELA_CENSO_LIMPA
        if TABELA_CENSO_LIMPA in tabelas
        else TABELA_CENSO_REGISTROS
    )
    cpf = cpf_table or (
        TABELA_CPF_LIMPA if TABELA_CPF_LIMPA in tabelas else TABELA_CPF_REGISTROS
    )
    if censo not in tabelas or cpf not in tabelas:
        raise RuntimeError(
            f"Tabelas ausentes para Splink: censo={censo!r}, cpf={cpf!r}. "
            "Rode o NB00 e o NB00b."
        )
    if censo != TABELA_CENSO_LIMPA or cpf != TABELA_CPF_LIMPA:
        print(
            f"AVISO: usando {censo}/{cpf} em vez de "
            f"{TABELA_CENSO_LIMPA}/{TABELA_CPF_LIMPA} — "
            "sentinelas podem ainda estar no lugar. Rode o NB00b."
        )
    con.execute(f"""
    CREATE OR REPLACE VIEW {SPLINK_INPUT_VIEW} AS
    SELECT t.*, {_DOB_PARTS_SQL}
    FROM (
        SELECT * FROM {censo}
        UNION ALL
        SELECT * FROM {cpf}
    ) t
    """)
    print(f"{SPLINK_INPUT_VIEW} → {censo} ∪ {cpf}")
    return censo, cpf


def _load_cohort_table(
    con: duckdb.DuckDBPyConnection,
    *,
    cohort_parquet: Path | None,
    cohort_table: str,
) -> None:
    if cohort_parquet is not None:
        con.execute(f"""
        CREATE OR REPLACE TABLE {cohort_table} AS
        SELECT * FROM read_parquet('{cohort_parquet}')
        """)


def materialize_cohort_cpf_por_censo(
    con: duckdb.DuckDBPyConnection,
    *,
    cohort_parquet: Path | None = None,
    cohort_table: str = "cohort_dedup_raw",
    out_table: str = "cohort_cpf_por_censo",
) -> dict[str, int]:
    """Um `cpf_norm` por `person_id_censo` a partir da coorte (MIN se ambíguo).

    Carimba o Censo no NB00/00b. Não é blocking de predição. Toda a
    `cohort_dedup` é confiável; ambiguidade N CPFs por Censo não deve ocorrer.
    """
    _load_cohort_table(con, cohort_parquet=cohort_parquet, cohort_table=cohort_table)
    cpf_gt = cpf_norm_sql("CPF_NORM")
    con.execute(f"""
    CREATE OR REPLACE TABLE {out_table} AS
    SELECT
        CAST(PERSON_ID_CENSO AS VARCHAR) AS person_id_censo,
        MIN({cpf_gt}) AS cpf_norm,
        COUNT(DISTINCT {cpf_gt}) AS n_cpf_distintos
    FROM {cohort_table}
    WHERE PERSON_ID_CENSO IS NOT NULL AND CPF_NORM IS NOT NULL
    GROUP BY 1
    """)
    n_censo = con.execute(f"SELECT COUNT(*) FROM {out_table}").fetchone()[0]
    n_ambig = con.execute(
        f"SELECT COUNT(*) FROM {out_table} WHERE n_cpf_distintos > 1"
    ).fetchone()[0]
    return {
        "n_censo_com_cpf_coorte": int(n_censo),
        "n_censo_cpf_ambiguo": int(n_ambig),
    }


def stamp_censo_cpf_from_cohort(
    con: duckdb.DuckDBPyConnection,
    *,
    table: str,
    cohort_cpf_table: str = "cohort_cpf_por_censo",
) -> int:
    """Preenche `cpf_norm` no Censo a partir da coorte. CPF bronze já tem a coluna.

    Aceita tabela só-Censo (sem coluna `origem`) ou empilhada legada.
    `NULL` no Censo fora da coorte — igualdade NULL não fabrica par.
    """
    cols = {
        r[0]
        for r in con.execute(f"DESCRIBE {table}").fetchall()
    }
    origem_clause = "AND t.origem = 'censo'" if "origem" in cols else ""
    con.execute(f"""
    UPDATE {table} AS t
    SET cpf_norm = o.cpf_norm
    FROM {cohort_cpf_table} AS o
    WHERE t.person_id_censo = o.person_id_censo
      {origem_clause}
    """)
    if "origem" in cols:
        n = con.execute(f"""
        SELECT COUNT(*) FROM {table}
        WHERE origem = 'censo' AND cpf_norm IS NOT NULL
        """).fetchone()[0]
    else:
        n = con.execute(f"""
        SELECT COUNT(*) FROM {table}
        WHERE cpf_norm IS NOT NULL
        """).fetchone()[0]
    return int(n)


def materialize_gt_1a1(
    con: duckdb.DuckDBPyConnection,
    *,
    cohort_parquet: Path | None = None,
    cohort_table: str = "cohort_dedup_raw",
    out_table: str = "gt_1a1",
) -> dict[str, int]:
    """Pares 1:1 da `cohort_dedup` (lista toda confiável).

    Critério estrutural: 1 CPF por Censo e 1 Censo por CPF. N:1 / 1:N saem em
    `n_nao_1a1_descartada`. Alimenta `materialize_gt_no_subset`.
    """
    _load_cohort_table(con, cohort_parquet=cohort_parquet, cohort_table=cohort_table)
    cpf_gt = cpf_norm_sql("CPF_NORM")
    candidatos = f"{out_table}_candidatos"
    con.execute(f"""
    CREATE OR REPLACE TABLE {candidatos} AS
    SELECT *,
        COUNT(*) OVER (PARTITION BY person_id_censo) AS n_cpf_por_censo,
        COUNT(*) OVER (PARTITION BY cpf_norm) AS n_censo_por_cpf
    FROM (
        SELECT DISTINCT
            CAST(PERSON_ID_CENSO AS VARCHAR) AS person_id_censo,
            {cpf_gt} AS cpf_norm
        FROM {cohort_table}
        WHERE PERSON_ID_CENSO IS NOT NULL AND CPF_NORM IS NOT NULL
    )
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE {out_table} AS
    SELECT person_id_censo, cpf_norm
    FROM {candidatos}
    WHERE n_cpf_por_censo = 1 AND n_censo_por_cpf = 1
    """)
    n_distintos = con.execute(f"SELECT COUNT(*) FROM {candidatos}").fetchone()[0]
    n_1a1 = con.execute(f"SELECT COUNT(*) FROM {out_table}").fetchone()[0]
    return {
        "n_pares_coorte_nacional": int(n_distintos),
        "n_pares_1a1_nacional": int(n_1a1),
        "n_nao_1a1_descartada": int(n_distintos) - int(n_1a1),
    }


def materialize_gt_no_subset(
    con: duckdb.DuckDBPyConnection,
    *,
    cohort_parquet: Path | None = None,
    splink_view: str = SPLINK_INPUT_VIEW,
    cohort_table: str = "cohort_dedup_raw",
    pairs_table: str = "ground_truth_pairs",
    subset_table: str = "gt_no_subset",
    gt_table: str = "gt_1a1",
) -> dict[str, int]:
    """Pares 1:1 da coorte com os dois lados em `splink_view`.

    Cria `gt_1a1` (nacional), `ground_truth_pairs` e `gt_no_subset` (recorte).
    Toda a `cohort_dedup` é confiável; só N:1 / 1:N saem (`n_nao_1a1_descartada`).
    """
    counts = materialize_gt_1a1(
        con,
        cohort_parquet=cohort_parquet,
        cohort_table=cohort_table,
        out_table=gt_table,
    )
    con.execute(f"""
    CREATE OR REPLACE TABLE {pairs_table} AS
    SELECT
        'censo_' || person_id_censo AS unique_id_censo,
        'cpf_' || cpf_norm AS unique_id_cpf,
        person_id_censo,
        cpf_norm
    FROM {gt_table}
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE {subset_table} AS
    SELECT gt.*
    FROM {pairs_table} gt
    JOIN {splink_view} c ON c.unique_id = gt.unique_id_censo
    JOIN {splink_view} p ON p.unique_id = gt.unique_id_cpf
    """)
    n_subset = con.execute(f"SELECT COUNT(*) FROM {subset_table}").fetchone()[0]
    return {
        **counts,
        "n_gt_no_subset": int(n_subset),
        # alias legado
        "n_prata_descartada": counts["n_nao_1a1_descartada"],
    }


# Aliases legados (carimbo / GT)
def materialize_ouro_1a1(*args, **kwargs):
    """Alias de `materialize_gt_1a1` (nomenclatura antiga)."""
    if "out_table" not in kwargs:
        kwargs["out_table"] = "ouro_1a1"
    counts = materialize_gt_1a1(*args, **kwargs)
    counts["n_prata_descartada"] = counts["n_nao_1a1_descartada"]
    return counts


def stamp_censo_cpf_from_ouro(
    con: duckdb.DuckDBPyConnection,
    *,
    table: str,
    ouro_table: str = "ouro_1a1",
) -> int:
    """Alias de `stamp_censo_cpf_from_cohort` (nomenclatura antiga)."""
    return stamp_censo_cpf_from_cohort(
        con, table=table, cohort_cpf_table=ouro_table
    )


def materialize_cluster_composicao(
    con: duckdb.DuckDBPyConnection,
    *,
    clusters_table: str = "splink_clusters",
    splink_view: str = SPLINK_INPUT_VIEW,
    out_table: str = "cluster_composicao",
) -> None:
    """Tipo de cluster: singleton, 1_para_1, 1_cpf_n_censo, outros."""
    con.execute(f"""
    CREATE OR REPLACE TABLE {out_table} AS
    SELECT
        cluster_id,
        COUNT(*) AS n,
        COUNT(*) FILTER (WHERE s.origem = 'censo') AS n_censo,
        COUNT(*) FILTER (WHERE s.origem = 'cpf') AS n_cpf,
        CASE
            WHEN COUNT(*) = 1 THEN 'singleton'
            WHEN COUNT(*) FILTER (WHERE s.origem = 'censo') = 1
             AND COUNT(*) FILTER (WHERE s.origem = 'cpf') = 1 THEN '1_para_1'
            WHEN COUNT(*) FILTER (WHERE s.origem = 'cpf') = 1
             AND COUNT(*) FILTER (WHERE s.origem = 'censo') >= 2 THEN '1_cpf_n_censo'
            ELSE 'outros'
        END AS tipo
    FROM {clusters_table} sc
    JOIN {splink_view} s ON s.unique_id = sc.unique_id
    GROUP BY cluster_id
    """)


def materialize_atribuicao(
    con: duckdb.DuckDBPyConnection,
    *,
    threshold: float | None = None,
    predictions_table: str = "splink_predictions",
    clusters_table: str = "splink_clusters",
    composicao_table: str = "cluster_composicao",
    out_table: str = "atribuicao_censo_cpf",
) -> dict[str, int | float]:
    """1 CPF por Censo: greedy por score, fora de clusters `outros`.

    Espera `predictions_table` com unique_id_l = Censo, unique_id_r = CPF.
    Censo e CPF do par precisam estar no mesmo cluster. `outros` (N×M) não entra.
    Empate de score: desempata por unique_id_censo. Ordena no pandas — o `.df()`
    do DuckDB não garante a ordem do `ORDER BY`.
    """
    import pandas as pd

    t = THRESHOLD_AVALIACAO if threshold is None else float(threshold)
    candidatos = con.execute(f"""
    SELECT
        p.unique_id_l AS unique_id_censo,
        p.unique_id_r AS unique_id_cpf,
        p.match_probability,
        cl.cluster_id,
        comp.tipo
    FROM {predictions_table} p
    JOIN {clusters_table} cl ON cl.unique_id = p.unique_id_l
    JOIN {clusters_table} cr ON cr.unique_id = p.unique_id_r
    JOIN {composicao_table} comp ON comp.cluster_id = cl.cluster_id
    WHERE p.match_probability >= {t}
      AND cl.cluster_id = cr.cluster_id
      AND comp.tipo <> 'outros'
    """).df()
    if len(candidatos):
        candidatos = candidatos.sort_values(
            ["match_probability", "unique_id_censo"],
            ascending=[False, True],
            kind="mergesort",
        )

    used_censo: set[str] = set()
    used_cpf: set[str] = set()
    kept: list[dict] = []
    for row in candidatos.itertuples(index=False):
        if row.unique_id_censo in used_censo or row.unique_id_cpf in used_cpf:
            continue
        used_censo.add(row.unique_id_censo)
        used_cpf.add(row.unique_id_cpf)
        kept.append(
            {
                "unique_id_censo": row.unique_id_censo,
                "unique_id_cpf": row.unique_id_cpf,
                "match_probability": float(row.match_probability),
                "cluster_id": row.cluster_id,
                "tipo_cluster": row.tipo,
            }
        )
    out = pd.DataFrame(
        kept,
        columns=[
            "unique_id_censo",
            "unique_id_cpf",
            "match_probability",
            "cluster_id",
            "tipo_cluster",
        ],
    )
    con.register("_atribuicao_df", out)
    con.execute(f"CREATE OR REPLACE TABLE {out_table} AS SELECT * FROM _atribuicao_df")
    con.unregister("_atribuicao_df")
    return {
        "n_candidatos": int(len(candidatos)),
        "n_atribuidos": int(len(out)),
        "threshold": t,
    }


def drop_splink_temp_tables(con: duckdb.DuckDBPyConnection) -> int:
    """Remove tabelas/views `__splink__*` residuais do DuckDB persistente.

    Rodadas anteriores (ou restart do kernel) deixam `__splink__df_representatives_*`
    etc. no arquivo. O Splink tenta dropar essas tabelas no clustering/predict, mas
    marca `created_by_splink=False` para o que não criou nesta sessão e levanta
    ValueError. Limpar antes de criar o Linker evita o erro.
    """
    rows = con.execute(
        """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = 'main'
          AND starts_with(table_name, '__splink__')
        """
    ).fetchall()
    for name, table_type in rows:
        kind = "VIEW" if table_type.upper() == "VIEW" else "TABLE"
        con.execute(f'DROP {kind} IF EXISTS "{name}"')
    if rows:
        print(f"Removidas {len(rows)} tabelas/views residuais __splink__*")
    return len(rows)


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
        TABELA_CENSO_REGISTROS: CENSO_REGISTROS,
        TABELA_CPF_REGISTROS: CPF_REGISTROS,
        TABELA_CENSO_LIMPA: CENSO_LIMPO,
        TABELA_CPF_LIMPA: CPF_LIMPO,
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
    print("ANO_OBITO_CORTE:", ANO_OBITO_CORTE)
    print("ANO_NASCIMENTO_MIN:", ANO_NASCIMENTO_MIN)
    print("DATA_REFERENCIA_IDADE:", DATA_REFERENCIA_IDADE)
    print("SEXO_VALIDOS:", SEXO_VALIDOS)
    print("THRESHOLD_AVALIACAO:", THRESHOLD_AVALIACAO)
    print("DUCKDB_ARQUIVO:", DUCKDB_ARQUIVO)
