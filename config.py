"""Configuração do pipeline probabilístico Censo × CPF (bronze → Splink)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Union

import duckdb

from features import normalize_date_sql

# Distingue "argumento não informado" de "None = sem filtro", já que None é
# um valor válido para FILTRO_UF/FILTRO_MUNICIPIO.
_UNSET: Any = object()

FiltroGeo = Union[str, int, float, Sequence[Union[str, int, float]], None]


def normalize_uf_filtro(filtro: str | int | float | None) -> str | None:
    """Normaliza um código de UF para string SQL (aceita int/float do notebook)."""
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
    """Normaliza um município para código IBGE 7 dígitos."""
    if filtro is None:
        return None
    if isinstance(filtro, bool):
        return None
    digits = "".join(ch for ch in str(filtro).strip() if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(7)[-7:]


def _iter_filtro_valores(filtro: FiltroGeo) -> tuple[Any, ...]:
    if filtro is None or isinstance(filtro, bool):
        return ()
    if isinstance(filtro, (str, bytes)) or not isinstance(filtro, Sequence):
        return (filtro,)
    return tuple(filtro)


def normalize_uf_lista(filtro: FiltroGeo) -> tuple[str, ...] | None:
    """None | escalar | sequência → tupla de UFs (2 dígitos), sem duplicata."""
    seen: set[str] = set()
    out: list[str] = []
    for item in _iter_filtro_valores(filtro):
        uf = normalize_uf_filtro(item)
        if uf and uf not in seen:
            seen.add(uf)
            out.append(uf)
    return tuple(out) or None


def normalize_municipio_lista(filtro: FiltroGeo) -> tuple[str, ...] | None:
    """None | escalar | sequência → tupla de municípios IBGE 7 dígitos."""
    seen: set[str] = set()
    out: list[str] = []
    for item in _iter_filtro_valores(filtro):
        mun = normalize_municipio_filtro(item)
        if mun and mun not in seen:
            seen.add(mun)
            out.append(mun)
    return tuple(out) or None


def _sql_eq_or_in(expr: str, valores: tuple[str, ...]) -> str:
    escaped = [v.replace("'", "''") for v in valores]
    if len(escaped) == 1:
        return f"{expr} = '{escaped[0]}'"
    listed = ", ".join(f"'{v}'" for v in escaped)
    return f"{expr} IN ({listed})"


# =============================================================================
# PARÂMETROS DE ANÁLISE — ajuste aqui a cada rodada
# =============================================================================

# Recorte geográfico. None = sem filtro (base nacional).
# Um eixo por vez (UF *ou* município). Cada um aceita escalar ou lista.
# Se os dois estiverem preenchidos, a cláusula é AND (como antes).
# Região Sul: PR 41, SC 42, RS 43. (MA completo seria FILTRO_UF = 21)
FILTRO_UF: FiltroGeo = [41, 42, 43]
FILTRO_MUNICIPIO: FiltroGeo = None

FILTRO_UF = normalize_uf_lista(FILTRO_UF)
FILTRO_MUNICIPIO = normalize_municipio_lista(FILTRO_MUNICIPIO)

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

# Corte operacional: avaliação (03) e export da lista única (04).
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


def recorte_output_slug(
    filtro_uf: FiltroGeo | Any = _UNSET,
    filtro_municipio: FiltroGeo | Any = _UNSET,
) -> str:
    """Slug estável do recorte: uf_41_42_43, mun_2111300, ou nacional.

    UFs e municípios entram ordenados, então [43, 41] e [41, 43] caem no
    mesmo diretório. Sem filtro → `nacional`.
    """
    uf = FILTRO_UF if filtro_uf is _UNSET else normalize_uf_lista(filtro_uf)
    mun = (
        FILTRO_MUNICIPIO
        if filtro_municipio is _UNSET
        else normalize_municipio_lista(filtro_municipio)
    )
    parts: list[str] = []
    if uf:
        parts.append("uf_" + "_".join(sorted(uf)))
    if mun:
        parts.append("mun_" + "_".join(sorted(mun)))
    return "_".join(parts) if parts else "nacional"


def set_filtros(
    *,
    uf: FiltroGeo | Any = _UNSET,
    municipio: FiltroGeo | Any = _UNSET,
) -> tuple[tuple[str, ...] | None, tuple[str, ...] | None]:
    """Sobrescreve os filtros geográficos para a sessão atual.

    Use isto no notebook em vez de reatribuir FILTRO_UF/FILTRO_MUNICIPIO:
    `from config import FILTRO_UF` cria uma cópia do nome, e reatribuí-la não
    altera o estado lido pelas funções de filtro.

    Aceita escalar ou lista: `set_filtros(uf=[21, 22])`.
    Também rebasa `OUTPUT_DIR` (e DuckDB/parquets) para
    `OUTPUT_DIR_BASE / recorte_output_slug()`. `from config import OUTPUT_DIR`
    continua uma cópia — use `config.OUTPUT_DIR` depois desta chamada.
    """
    global FILTRO_UF, FILTRO_MUNICIPIO
    if uf is not _UNSET:
        FILTRO_UF = normalize_uf_lista(uf)
    if municipio is not _UNSET:
        FILTRO_MUNICIPIO = normalize_municipio_lista(municipio)
    refresh_output_paths()
    return FILTRO_UF, FILTRO_MUNICIPIO


# =============================================================================
# CAMINHOS E RECURSOS — variam por máquina, aceitam variável de ambiente
# =============================================================================
#
# OUTPUT_DIR_BASE, OUTPUT_DIR (subdir do recorte), CENSO_DIR, CENSO_RAW_DIR,
# CENSO_PESSOAS_ARQUIVO, CPF_ARQUIVO, COHORT_DIR, COHORT_DEDUP_ARQUIVO,
# LISTA_OURO_ARQUIVO, DUCKDB_TEMP_DIR, DUCKDB_THREADS, DUCKDB_MEMORY_LIMIT

PROB_DIR = Path(__file__).resolve().parent
OUTPUT_DIR_BASE = Path(
    os.environ.get("OUTPUT_DIR", Path.home() / "data/probabilistico_output")
).expanduser()
OUTPUT_DIR: Path
DUCKDB_ARQUIVO: Path
CENSO_REGISTROS: Path
CPF_REGISTROS: Path
CENSO_LIMPO: Path
CPF_LIMPO: Path
CENSO_LIMPO_APLICACAO: Path
CPF_LIMPO_APLICACAO: Path
SPLINK_MODEL_JSON: Path
SPLINK_PREDICTIONS: Path
SPLINK_ATRIBUICAO: Path

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

LISTA_OURO_ARQUIVO = Path(
    os.environ.get(
        "LISTA_OURO_ARQUIVO",
        Path.home()
        / "capefe/scripts_luis/Pareamento/V4 20260827/regra1.parquet",
    )
).expanduser()


def refresh_output_paths() -> Path:
    """OUTPUT_DIR = OUTPUT_DIR_BASE / slug do filtro; rebind de DuckDB e parquets."""
    global OUTPUT_DIR, DUCKDB_ARQUIVO, CENSO_REGISTROS, CPF_REGISTROS
    global CENSO_LIMPO, CPF_LIMPO, CENSO_LIMPO_APLICACAO, CPF_LIMPO_APLICACAO
    global SPLINK_MODEL_JSON, SPLINK_PREDICTIONS
    global SPLINK_ATRIBUICAO
    OUTPUT_DIR = OUTPUT_DIR_BASE / recorte_output_slug()
    DUCKDB_ARQUIVO = OUTPUT_DIR / "probabilistico.duckdb"
    CENSO_REGISTROS = OUTPUT_DIR / "censo_registros.parquet"
    CPF_REGISTROS = OUTPUT_DIR / "cpf_registros.parquet"
    CENSO_LIMPO = OUTPUT_DIR / "censo_limpo.parquet"
    CPF_LIMPO = OUTPUT_DIR / "cpf_limpo.parquet"
    CENSO_LIMPO_APLICACAO = OUTPUT_DIR / "censo_limpo_aplicacao.parquet"
    CPF_LIMPO_APLICACAO = OUTPUT_DIR / "cpf_limpo_aplicacao.parquet"
    SPLINK_MODEL_JSON = OUTPUT_DIR / "splink_model.json"
    SPLINK_PREDICTIONS = OUTPUT_DIR / "splink_predictions.parquet"
    SPLINK_ATRIBUICAO = OUTPUT_DIR / "splink_atribuicao.parquet"
    return OUTPUT_DIR


refresh_output_paths()

# NB00: bases separadas (sem empilhar). NB00b limpa cada uma.
TABELA_CENSO_REGISTROS = "censo_registros"
TABELA_CPF_REGISTROS = "cpf_registros"
TABELA_CENSO_LIMPA = "censo_limpo"
TABELA_CPF_LIMPA = "cpf_limpo"
TABELA_CENSO_LIMPA_APLICACAO = "censo_limpo_aplicacao"
TABELA_CPF_LIMPA_APLICACAO = "cpf_limpo_aplicacao"

# JSON no treino (02); predictions na aplicação (02b); 03 avalia; 04 exporta a lista
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
DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "370GB")

ANO_REFERENCIA_CENSO = 2022
CENSO_IDADE_MAX = 130


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
    filtro_uf: FiltroGeo | Any = _UNSET,
    filtro_municipio: FiltroGeo | Any = _UNSET,
) -> None:
    """Materializa lookup de CEP a partir de data_cep_uniq.csv (filtro UF e/ou município)."""
    path = (source_path or CENSO_CEP_ARQUIVO).expanduser()
    clauses: list[str] = []
    ufs = normalize_uf_lista(FILTRO_UF if filtro_uf is _UNSET else filtro_uf)
    if ufs:
        uf_col = f'c."{CEP_COL_UF}"'
        uf_expr = (
            f"lpad(regexp_replace(CAST({uf_col} AS VARCHAR), '[^0-9]', '', 'g'), 2, '0')"
        )
        clauses.append(_sql_eq_or_in(uf_expr, ufs))
    muns = normalize_municipio_lista(
        FILTRO_MUNICIPIO if filtro_municipio is _UNSET else filtro_municipio
    )
    if muns:
        mun_col = f'c."{CEP_COL_MUNICIPIO}"'
        mun_expr = (
            f"lpad(regexp_replace(CAST({mun_col} AS VARCHAR), '[^0-9]', '', 'g'), 7, '0')"
        )
        clauses.append(_sql_eq_or_in(mun_expr, muns))
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


def _iso_bruta_sql(col: str) -> str:
    return f"NULLIF(TRIM(CAST({col} AS VARCHAR)), '')"


def _parece_iso_sql(s: str) -> str:
    """YYYY-MM-DD na forma (length ≥ 10 e hífens nas posições 5 e 8)."""
    return (
        f"({s} IS NOT NULL AND length({s}) >= 10 AND "
        f"substr({s}, 5, 1) = '-' AND substr({s}, 8, 1) = '-')"
    )


def ano_nascimento_sql(col: str = "data_nascimento") -> str:
    """Ano só da data validada (nulo se a ISO caiu fora da faixa)."""
    d = dob_valida_sql(col)
    return f"CASE WHEN ({d}) IS NULL THEN NULL ELSE substr({d}, 1, 4) END"


def mes_nascimento_sql(col: str = "data_nascimento") -> str:
    """Mês da ISO crua, mesmo com ano fora da faixa."""
    s = _iso_bruta_sql(col)
    mes = f"substr({s}, 6, 2)"
    return f"""CASE
        WHEN NOT {_parece_iso_sql(s)} THEN NULL
        WHEN TRY_CAST({mes} AS INTEGER) BETWEEN 1 AND 12 THEN {mes}
        ELSE NULL
    END"""


def dia_nascimento_sql(col: str = "data_nascimento") -> str:
    """Dia da ISO crua, mesmo com ano fora da faixa."""
    s = _iso_bruta_sql(col)
    dia = f"substr({s}, 9, 2)"
    return f"""CASE
        WHEN NOT {_parece_iso_sql(s)} THEN NULL
        WHEN TRY_CAST({dia} AS INTEGER) BETWEEN 1 AND 31 THEN {dia}
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
    # da DOB já validada. Se a data cai, a idade cai. Censo: PECP0401 só quando
    # a data validada é nula — senão a comparison de idade no Splink é NullLevel
    # (não duplica a DOB).
    if "idade" in out and "data_nascimento" in colunas:
        dob = dob_valida_sql("data_nascimento")
        out["idade"] = (
            f"CASE WHEN origem = 'cpf' THEN {idade_cpf_sql(dob)} "
            f"WHEN ({dob}) IS NOT NULL THEN NULL "
            f"ELSE idade END"
        )
    # Partes da data: mês/dia da ISO crua (ano inválido ainda rende aniversário);
    # ano só da data validada. Blocking e o nível mês+dia do Splink usam isto.
    if "data_nascimento" in colunas:
        out["ano_nascimento"] = ano_nascimento_sql("data_nascimento")
        out["mes_nascimento"] = mes_nascimento_sql("data_nascimento")
        out["dia_nascimento"] = dia_nascimento_sql("data_nascimento")
    return out


def sql_optional_col(alias: str, col: str | None, *, cast_varchar: bool = True) -> str:
    if not col:
        return "NULL"
    expr = f'{alias}."{col}"' if "." not in col else col
    return f"CAST({expr} AS VARCHAR)" if cast_varchar else expr


def uf_filter_clause(
    uf_expr: str,
    filtro: FiltroGeo | Any = _UNSET,
) -> str:
    ufs = normalize_uf_lista(FILTRO_UF if filtro is _UNSET else filtro)
    if not ufs:
        return "TRUE"
    return _sql_eq_or_in(uf_expr, ufs)


def municipio_filter_clause(
    mun_expr: str,
    filtro: FiltroGeo | Any = _UNSET,
) -> str:
    muns = normalize_municipio_lista(
        FILTRO_MUNICIPIO if filtro is _UNSET else filtro
    )
    if not muns:
        return "TRUE"
    return _sql_eq_or_in(mun_expr, muns)


def geo_filter_clause(
    uf_expr: str,
    mun_expr: str,
    *,
    filtro_uf: FiltroGeo | Any = _UNSET,
    filtro_municipio: FiltroGeo | Any = _UNSET,
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
    """View `splink_input` = UNION das duas bases limpas (+ partes DOB se faltarem).

    Prefere `censo_limpo` / `cpf_limpo`. Se faltarem, cai nas tabelas do NB00
    (ainda com sentinelas) e avisa. Tabelas de aplicação (`*_limpo_aplicacao`)
    não disparam o aviso.
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
    if censo == TABELA_CENSO_REGISTROS or cpf == TABELA_CPF_REGISTROS:
        print(
            f"AVISO: usando {censo}/{cpf} em vez de "
            f"{TABELA_CENSO_LIMPA}/{TABELA_CPF_LIMPA} — "
            "sentinelas podem ainda estar no lugar. Rode o NB00b."
        )
    partes = {"ano_nascimento", "mes_nascimento", "dia_nascimento"}
    cols_censo = {r[0] for r in con.execute(f"DESCRIBE {censo}").fetchall()}
    cols_cpf = {r[0] for r in con.execute(f"DESCRIBE {cpf}").fetchall()}
    ja_tem_partes = partes <= cols_censo and partes <= cols_cpf
    if ja_tem_partes:
        select_sql = "SELECT * FROM unioned"
    else:
        select_sql = f"SELECT t.*, {_DOB_PARTS_SQL} FROM unioned t"
    con.execute(f"""
    CREATE OR REPLACE VIEW {SPLINK_INPUT_VIEW} AS
    WITH unioned AS (
        SELECT * FROM {censo}
        UNION ALL
        SELECT * FROM {cpf}
    )
    {select_sql}
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
    pid = "CAST(PERSON_ID_CENSO AS VARCHAR)"
    con.execute(f"""
    CREATE OR REPLACE TABLE {out_table} AS
    SELECT
        {pid} AS person_id_censo,
        MIN({cpf_gt}) AS cpf_norm,
        COUNT(DISTINCT {cpf_gt}) AS n_cpf_distintos
    FROM {cohort_table}
    WHERE PERSON_ID_CENSO IS NOT NULL AND CPF_NORM IS NOT NULL
    GROUP BY {pid}
    """)
    n_dup = con.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT person_id_censo FROM {out_table}
            GROUP BY person_id_censo HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    if n_dup:
        raise RuntimeError(
            f"{out_table} tem {n_dup} person_id_censo duplicados; "
            "o carimbo de cpf_norm exige 1 linha por Censo."
        )
    n_censo = con.execute(f"SELECT COUNT(*) FROM {out_table}").fetchone()[0]
    n_ambig = con.execute(
        f"SELECT COUNT(*) FROM {out_table} WHERE n_cpf_distintos > 1"
    ).fetchone()[0]
    return {
        "n_censo_com_cpf_coorte": int(n_censo),
        "n_censo_cpf_ambiguo": int(n_ambig),
    }


def materialize_censo_registros(
    con: duckdb.DuckDBPyConnection,
    *,
    staging_table: str = "censo_staging",
    cohort_cpf_table: str = "cohort_cpf_por_censo",
    out_table: str = TABELA_CENSO_REGISTROS,
) -> None:
    """Censo staging → registros, com 1 `cpf_norm` por pessoa (MIN se ambíguo).

    Evita subquery escalar: no DuckDB 1.x ela quebra se a coorte devolver
    mais de uma linha, e `person_id_censo` sem prefixo pode não correlacionar.
    """
    from features import (
        NOME_MAE_COLUMNS,
        PESSOA_COLUMNS,
        clean_name_sql,
        name_feature_columns_sql,
        normalize_sexo_sql,
        select_list_sql,
    )

    pessoa = name_feature_columns_sql("nome_completo_norm", col_map=PESSOA_COLUMNS)
    mae = {
        alias: f"NULLIF({expr}, '')"
        for alias, expr in name_feature_columns_sql(
            "nome_mae_norm", col_map=NOME_MAE_COLUMNS
        ).items()
    }
    sexo_n = normalize_sexo_sql("n.sexo_raw")
    con.execute(f"""
    CREATE OR REPLACE TABLE {out_table} AS
    WITH norm AS (
        SELECT *,
            {clean_name_sql("nome_completo_raw")} AS nome_completo_norm,
            {clean_name_sql("nome_mae_inferido")} AS nome_mae_norm
        FROM {staging_table}
        WHERE person_id_censo IS NOT NULL
    )
    SELECT
        'censo_' || n.person_id_censo AS unique_id, 'censo' AS origem,
        o.cpf_norm,
        {select_list_sql(pessoa)},
        n.data_nascimento,
        {select_list_sql(mae)},
        {sexo_n} AS sexo,
        n.idade,
        n.cep, CAST(n.uf AS VARCHAR) AS uf,
        CAST(n.cod_municipio AS VARCHAR) AS cod_municipio,
        CAST(NULL AS INTEGER) AS ano_obito,
        n.person_id_censo, n.id_domicilio
    FROM norm n
    LEFT JOIN (
        SELECT person_id_censo, MIN(cpf_norm) AS cpf_norm
        FROM {cohort_cpf_table}
        GROUP BY person_id_censo
    ) o ON o.person_id_censo = n.person_id_censo
    """)
    benchmark_checkpoint(con, out_table, f"SELECT COUNT(*) FROM {out_table}")


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
    }


def drop_splink_temp_tables(con: duckdb.DuckDBPyConnection) -> int:
    """Remove tabelas/views `__splink__*` residuais do DuckDB persistente.

    Rodadas anteriores (ou restart do kernel) deixam `__splink__df_predict_*`
    etc. no arquivo. O Splink tenta dropar essas tabelas no predict, mas
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


def check_registros_vs_filtrado(con: duckdb.DuckDBPyConnection) -> None:
    """O 00b lê censo_registros/cpf_registros, não as tabelas *_filtrado.

    REFILTER_GEO sozinho no NB00 atualiza o filtro e deixa os registros
    no recorte anterior. Falha cedo se o recorte das tabelas finais não
    bate com FILTRO_UF/FILTRO_MUNICIPIO ou com *_filtrado.
    """
    tabelas = list_tables(con)
    problemas: list[str] = []

    if "censo_pessoas_filtrado" in tabelas and TABELA_CENSO_REGISTROS in tabelas:
        n_f = con.execute("SELECT COUNT(*) FROM censo_pessoas_filtrado").fetchone()[0]
        n_r = con.execute(f"SELECT COUNT(*) FROM {TABELA_CENSO_REGISTROS}").fetchone()[0]
        print(f"censo_pessoas_filtrado: {n_f:,} | {TABELA_CENSO_REGISTROS}: {n_r:,}")
        if n_f > 0 and n_r < int(n_f * 0.9):
            problemas.append(
                f"{TABELA_CENSO_REGISTROS} ({n_r:,}) está atrás de "
                f"censo_pessoas_filtrado ({n_f:,})"
            )
    if "cpf_filtrado" in tabelas and TABELA_CPF_REGISTROS in tabelas:
        n_f = con.execute("SELECT COUNT(*) FROM cpf_filtrado").fetchone()[0]
        n_r = con.execute(f"SELECT COUNT(*) FROM {TABELA_CPF_REGISTROS}").fetchone()[0]
        print(f"cpf_filtrado: {n_f:,} | {TABELA_CPF_REGISTROS}: {n_r:,}")

    def _distintos(table: str, col: str) -> set[str]:
        rows = con.execute(
            f"SELECT DISTINCT CAST({col} AS VARCHAR) FROM {table} "
            f"WHERE {col} IS NOT NULL AND CAST({col} AS VARCHAR) <> ''"
        ).fetchall()
        return {str(r[0]) for r in rows}

    if FILTRO_UF and TABELA_CENSO_REGISTROS in tabelas:
        ufs = _distintos(TABELA_CENSO_REGISTROS, "uf")
        esperadas = set(FILTRO_UF)
        extras = sorted(ufs - esperadas)
        faltando = sorted(esperadas - ufs)
        if extras or faltando:
            problemas.append(
                f"UF em {TABELA_CENSO_REGISTROS}: {sorted(ufs)} ≠ FILTRO_UF "
                f"{sorted(esperadas)}"
                + (f" | extras={extras}" if extras else "")
                + (f" | faltando={faltando}" if faltando else "")
            )
    if FILTRO_MUNICIPIO and TABELA_CENSO_REGISTROS in tabelas:
        muns = _distintos(TABELA_CENSO_REGISTROS, "cod_municipio")
        esperadas = set(FILTRO_MUNICIPIO)
        extras = sorted(muns - esperadas)
        faltando = sorted(esperadas - muns)
        if extras or faltando:
            problemas.append(
                f"município em {TABELA_CENSO_REGISTROS}: {sorted(muns)} ≠ "
                f"FILTRO_MUNICIPIO {sorted(esperadas)}"
                + (f" | extras={extras}" if extras else "")
                + (f" | faltando={faltando}" if faltando else "")
            )

    if problemas:
        raise RuntimeError(
            "Recorte de censo_registros/cpf_registros desatualizado em relação "
            "ao filtro atual. No NB00 use REFILTER_GEO=True e rode até o "
            "export (células de mãe/CEP/registros), não só o filtro "
            "geográfico.\n" + "\n".join(problemas)
        )


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
        TABELA_CENSO_LIMPA_APLICACAO: CENSO_LIMPO_APLICACAO,
        TABELA_CPF_LIMPA_APLICACAO: CPF_LIMPO_APLICACAO,
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
    print("OUTPUT_DIR_BASE:", OUTPUT_DIR_BASE)
    print("OUTPUT_DIR:", OUTPUT_DIR)
    print("recorte:", recorte_output_slug())
    print("CPF_ARQUIVO:", CPF_ARQUIVO)
    print("CENSO_PESSOAS_ARQUIVO:", CENSO_PESSOAS_ARQUIVO)
    print("CENSO_CEP_ARQUIVO:", CENSO_CEP_ARQUIVO)
    print("COHORT_DEDUP_ARQUIVO:", COHORT_DEDUP_ARQUIVO)
    print("LISTA_OURO_ARQUIVO:", LISTA_OURO_ARQUIVO)
    print("CENSO_LIMPO:", CENSO_LIMPO)
    print("CPF_LIMPO:", CPF_LIMPO)
    print("CENSO_LIMPO_APLICACAO:", CENSO_LIMPO_APLICACAO)
    print("CPF_LIMPO_APLICACAO:", CPF_LIMPO_APLICACAO)
    print("FILTRO_UF:", FILTRO_UF)
    print("FILTRO_MUNICIPIO:", FILTRO_MUNICIPIO)
    print("ANO_OBITO_CORTE:", ANO_OBITO_CORTE)
    print("ANO_NASCIMENTO_MIN:", ANO_NASCIMENTO_MIN)
    print("DATA_REFERENCIA_IDADE:", DATA_REFERENCIA_IDADE)
    print("SEXO_VALIDOS:", SEXO_VALIDOS)
    print("THRESHOLD_AVALIACAO:", THRESHOLD_AVALIACAO)
    print("DUCKDB_ARQUIVO:", DUCKDB_ARQUIVO)
