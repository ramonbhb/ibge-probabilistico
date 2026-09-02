"""Normalização e featurização para linkage probabilístico (split primeiro/meio/último)."""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

# Shim ibge_common quando ibge-listas está no path
_IBGE_LISTAS = Path(__file__).resolve().parent.parent / "ibge-listas"
if _IBGE_LISTAS.is_dir() and str(_IBGE_LISTAS) not in sys.path:
    sys.path.insert(0, str(_IBGE_LISTAS))

try:
    from ibge_common.features.ouro_cpf import (  # noqa: F401
        normalize_date,
        normalize_date_sql,
        normalize_text,
        tokenize_name,
    )
except ImportError:
    def strip_accents(text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in text if not unicodedata.combining(ch))

    def normalize_text(text) -> str:
        if text is None:
            return ""
        text = str(text).upper().strip()
        if text in {"", "NAN", "NONE", "NULL"}:
            return ""
        # Ç/Ñ antes do ASCII — senão viram C/N e perdem o valor fonético.
        text = text.replace("Ç", "S").replace("Ñ", "NH")
        text = strip_accents(text)
        text = re.sub(r"[^A-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def normalize_date(x) -> str:
        if x is None:
            return ""
        s = str(x).strip()
        if s in {"", "NAN", "NONE", "NULL"}:
            return ""
        try:
            if hasattr(x, "strftime"):
                return x.strftime("%Y-%m-%d")
            parts = re.split(r"[-/]", s)
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    yyyy, mm, dd = parts
                else:
                    dd, mm, yyyy = parts
                return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
        except Exception:
            pass
        return ""

    def normalize_date_sql(col: str) -> str:
        s = f"trim(CAST({col} AS VARCHAR))"
        s_dash = f"replace({s}, '/', '-')"
        return f"""
        CASE
            WHEN {col} IS NULL THEN ''
            WHEN {s} IN ('', 'NAN', 'NONE', 'NULL') THEN ''
            WHEN length({s_dash}) = 10 AND substr({s_dash}, 5, 1) = '-'
                THEN {s_dash}
            WHEN length({s_dash}) = 10 AND substr({s_dash}, 3, 1) = '-'
                THEN coalesce(strftime(try_strptime({s_dash}, '%d-%m-%Y'), '%Y-%m-%d'), '')
            ELSE coalesce(
                strftime(try_cast({col} AS DATE), '%Y-%m-%d'),
                strftime(try_strptime({s_dash}, '%Y-%m-%d'), '%Y-%m-%d'),
                strftime(try_strptime({s_dash}, '%d-%m-%Y'), '%Y-%m-%d'),
                ''
            )
        END
        """.strip()

    def tokenize_name(name) -> list[str]:
        name = normalize_text(name)
        return [tok for tok in name.split() if tok] if name else []


# Partículas e placeholders removidos por replace com espaço: " DA " → " ".
# Só tokens isolados (com espaço antes e depois); DEISE e DELMA não são afetados.
PARTICULAS_NOME: tuple[str, ...] = (
    "DA", "DE", "DI", "DO", "DU", "DAS", "DOS", "DES", "DEL", "E", "Y",
)
PLACEHOLDERS_NOME: tuple[str, ...] = (
    "DESCONHECIDO", "DESCONHECIDA", "IGNORADO", "IGNORADA", "MAE",
)
TERMOS_RUIDO_NOME: tuple[str, ...] = PARTICULAS_NOME + PLACEHOLDERS_NOME


def _pt_pre_ascii(text: str) -> str:
    """Ç→S e Ñ→NH antes do strip de acentos (senão viram C/N)."""
    if not text:
        return ""
    return (
        str(text)
        .replace("Ç", "S")
        .replace("ç", "S")
        .replace("Ñ", "NH")
        .replace("ñ", "NH")
    )


def _strip_noise_terms(text: str) -> str:
    """Remove partículas e placeholders por replace com espaço ao redor."""
    if not text:
        return ""
    padded = f" {text} "
    for termo in TERMOS_RUIDO_NOME:
        padded = padded.replace(f" {termo} ", " ")
    return re.sub(r"\s+", " ", padded).strip()


def clean_name(text) -> str | None:
    """Normaliza e remove partículas/placeholders; vazio vira None."""
    # Pré-processa mesmo quando normalize_text vem do ibge_common.
    norm = normalize_text(_pt_pre_ascii(text) if text is not None else text)
    if not norm:
        return None
    limpo = _strip_noise_terms(norm)
    return limpo if limpo else None


# Ordem: dígrafos longos antes de H solto; GUI/GUE e QUI/QUE antes do soft G/C.
_PHONETIC_REPLACEMENTS = [
    ("PH", "F"), ("Y", "I"), ("W", "V"), ("CK", "K"), ("SCH", "X"),
    ("SH", "X"), ("CH", "X"), ("TH", "T"), ("RH", "R"),
    ("LH", "L"), ("NH", "N"), ("GUI", "GI"),
    ("GUE", "GE"), ("QUI", "KI"), ("QUE", "KE"), ("SS", "S"),
    ("XC", "S"), ("XS", "S"), ("TS", "S"), ("TZ", "S"), ("Z", "S"), ("H", ""),
]


def _dedupe_consecutive(token: str) -> str:
    return re.sub(r"(.)\1+", r"\1", token)


def br_phonetic_basic_token(token: str) -> str:
    """Substituições fonéticas PT-BR (ortográficas; sem epêntese/finais falados)."""
    token = normalize_text(_pt_pre_ascii(token) if token is not None else token)
    if not token:
        return ""
    for a, b in _PHONETIC_REPLACEMENTS:
        token = token.replace(a, b)
    token = re.sub(r"C(?=[EI])", "S", token)
    token = re.sub(r"G(?=[EI])", "J", token)
    token = token.replace("Q", "K").replace("C", "K")
    return _dedupe_consecutive(token)


def full_name_norm(name) -> str:
    return " ".join(tokenize_name(name))


def full_name_phon_basic(name) -> str:
    vals = [br_phonetic_basic_token(t) for t in tokenize_name(name)]
    return " ".join(v for v in vals if v)


def split_name_three_parts(name) -> tuple[str, str, str]:
    """Split em primeiro / meio / último sobre nome já limpo."""
    limpo = clean_name(name) if name is not None else None
    toks = limpo.split() if limpo else []
    if not toks:
        return "", "", ""
    if len(toks) == 1:
        return toks[0], "", ""
    return toks[0], " ".join(toks[1:-1]), toks[-1]


def linkage_name_norm(name) -> str | None:
    """Nome normalizado para linkage (com limpeza de partículas)."""
    return clean_name(name)


def normalize_date_compacta_sql(col: str) -> str:
    """normalize_date_sql mais o formato compacto YYYYMMDD.

    Extensão local, para não mexer no ibge_common que os outros pipelines usam.
    O `normalize_date_sql` só reconhece data com separador, então uma coluna
    inteira de 8 dígitos (19900102) — encoding comum em extrato de base
    administrativa — devolve '' e leva a idade junto.

    Estritamente aditivo: só age onde a expressão original já falhava, exige 8
    dígitos e valida via strptime, então 99999999 e 19900230 seguem rejeitados.
    """
    base = normalize_date_sql(col)
    digitos = f"regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g')"
    compacta = (
        f"CASE WHEN length({digitos}) = 8 THEN "
        f"coalesce(strftime(try_strptime({digitos}, '%Y%m%d'), '%Y-%m-%d'), '') "
        f"ELSE '' END"
    )
    return f"coalesce(NULLIF({base}, ''), {compacta})"


def normalize_sexo(sexo) -> str:
    s = normalize_text(sexo)
    if s in {"M", "MASC", "MASCULINO", "1"}:
        return "M"
    if s in {"F", "FEM", "FEMININO", "2"}:
        return "F"
    return s[:1] if s else ""


def normalize_sexo_sql(col: str) -> str:
    """Sexo normalizado (M/F) em SQL — equivalente a normalize_sexo()."""
    trimmed = f"upper(trim(CAST({col} AS VARCHAR)))"
    empty = (
        f"trim(CAST({col} AS VARCHAR)) IN ('', 'NAN', 'NONE', 'NULL')"
    )
    return f"""CASE
        WHEN {col} IS NULL OR {empty} THEN ''
        WHEN {trimmed} IN ('M', 'MASC', 'MASCULINO', '1') THEN 'M'
        WHEN {trimmed} IN ('F', 'FEM', 'FEMININO', '2') THEN 'F'
        ELSE substr({trimmed}, 1, 1)
    END"""


def normalize_cep(cep) -> str:
    if cep is None:
        return ""
    digits = re.sub(r"\D", "", str(cep))
    if len(digits) < 5:
        return ""
    return digits.zfill(8)[:8]


# =============================================================================
# Featurização em SQL — espelha as funções Python acima
# =============================================================================
#
# O RE2 do DuckDB não tem lookahead nem backreference no padrão, então dois
# trechos precisam de tradução indireta:
#   - C(?=[EI]) vira 'C([EI])' -> 'S\1' (o \1 vale na substituição, não no padrão)
#   - _dedupe_consecutive vira list_reduce sobre a lista de caracteres


def normalize_text_sql(col: str) -> str:
    """normalize_text() em SQL: maiúsculas, sem acento, só A-Z0-9 e espaço simples."""
    texto = f"trim(upper(CAST({col} AS VARCHAR)))"
    # Ç/Ñ antes de strip_accents (senão Ç→C e Ñ→N).
    texto_pt = f"replace(replace({texto}, 'Ç', 'S'), 'Ñ', 'NH')"
    limpo = (
        f"regexp_replace(regexp_replace(strip_accents({texto_pt}), "
        f"'[^A-Z0-9\\s]', ' ', 'g'), '\\s+', ' ', 'g')"
    )
    return (
        f"CASE WHEN {col} IS NULL OR {texto} IN ('', 'NAN', 'NONE', 'NULL') "
        f"THEN '' ELSE trim({limpo}) END"
    )


def strip_noise_sql(expr: str) -> str:
    """Remove partículas e placeholders por replace `" TERMO "` → `" "`."""
    out = f"' ' || {expr} || ' '"
    for termo in TERMOS_RUIDO_NOME:
        out = f"replace({out}, ' {termo} ', ' ')"
    return f"trim(regexp_replace({out}, '\\s+', ' ', 'g'))"


def clean_name_sql(col: str) -> str:
    """normalize_text_sql + strip_noise_sql; string vazia vira NULL."""
    norm = normalize_text_sql(col)
    return f"NULLIF({strip_noise_sql(norm)}, '')"


def _nullif_empty_sql(expr: str) -> str:
    return f"NULLIF({expr}, '')"


def dedupe_consecutive_sql(expr: str) -> str:
    """_dedupe_consecutive() em SQL, via redução da lista de caracteres.

    O chr(1) inicial resolve dois problemas de uma vez: garante lista não vazia
    (list_reduce exige ao menos um elemento no DuckDB 1.0) e faz a expressão
    aparecer uma única vez, evitando explosão do texto SQL ao aninhar.
    """
    caracteres = f"regexp_extract_all(chr(1) || ({expr}), '.')"
    reduce_ = (
        f"list_reduce({caracteres}, "
        f"(acc, c) -> CASE WHEN ends_with(acc, c) THEN acc ELSE acc || c END)"
    )
    return f"substr({reduce_}, 2)"


def _phonetic_map_sql(expr: str) -> str:
    """Substituições de br_phonetic_basic_token(), sem o dedupe final."""
    out = expr
    for a, b in _PHONETIC_REPLACEMENTS:
        out = f"replace({out}, '{a}', '{b}')"
    out = f"regexp_replace({out}, 'C([EI])', 'S\\1', 'g')"
    out = f"regexp_replace({out}, 'G([EI])', 'J\\1', 'g')"
    return f"replace(replace({out}, 'Q', 'K'), 'C', 'K')"


def phonetic_token_sql(expr: str) -> str:
    """br_phonetic_basic_token() em SQL, para um token já normalizado."""
    return dedupe_consecutive_sql(_phonetic_map_sql(expr))


def phonetic_name_sql(norm_col: str) -> str:
    """full_name_phon_basic() em SQL: fonética por token, descartando os vazios."""
    token_expr = phonetic_token_sql("_tok")
    tokens = f"list_transform(string_split({norm_col}, ' '), _tok -> {token_expr})"
    return f"array_to_string(list_filter({tokens}, _v -> _v <> ''), ' ')"


def _split_parts_sql(norm_col: str) -> dict[str, str]:
    """split_name_three_parts() em SQL, sobre texto já normalizado."""
    toks = f"string_split({norm_col}, ' ')"
    n = f"len({toks})"
    return {
        "primeiro_nome": f"CASE WHEN {norm_col} = '' THEN '' ELSE {toks}[1] END",
        "nome_meio": (
            f"CASE WHEN {n} <= 2 THEN '' "
            f"ELSE array_to_string(list_slice({toks}, 2, {n} - 1), ' ') END"
        ),
        "ultimo_nome": (
            f"CASE WHEN {norm_col} = '' OR {n} <= 1 THEN '' ELSE {toks}[{n}] END"
        ),
    }


# Mapas de alias para name_feature_columns_sql: as chaves canônicas viram as
# colunas da pessoa ou as do nome da mãe, a partir das mesmas expressões.
PESSOA_COLUMNS = {
    "nome_completo_norm": "nome_completo",
    "nome_completo_phon": "nome_completo_phon",
    "primeiro_nome": "primeiro_nome",
    "nome_meio": "nome_meio",
    "ultimo_nome": "ultimo_nome",
    "primeiro_ultimo": "primeiro_ultimo",
    "primeiro_nome_phon": "primeiro_nome_phon",
    "nome_meio_phon": "nome_meio_phon",
    "ultimo_nome_phon": "ultimo_nome_phon",
    "primeiro_ultimo_phon": "primeiro_ultimo_phon",
}

NOME_MAE_COLUMNS = {
    "nome_completo_norm": "nome_mae",
    "nome_completo_phon": "nome_mae_phon",
    "primeiro_nome": "primeiro_nome_mae",
    "nome_meio": "nome_meio_mae",
    "ultimo_nome": "ultimo_nome_mae",
    "primeiro_nome_phon": "primeiro_nome_mae_phon",
    "nome_meio_phon": "nome_meio_mae_phon",
    "ultimo_nome_phon": "ultimo_nome_mae_phon",
}


def name_feature_columns_sql(
    norm_col: str,
    *,
    col_map: dict[str, str] | None = None,
) -> dict[str, str]:
    """Colunas de nome (split + fonética) a partir de coluna já limpa.

    Espera `clean_name_sql` aplicado antes (partículas removidas, vazio = NULL).
    Fonética é calculada uma vez no nome completo e repartida por split.
    """
    safe = f"coalesce({norm_col}, '')"
    partes = _split_parts_sql(safe)
    completo_phon = phonetic_name_sql(safe)
    partes_phon = _split_parts_sql(completo_phon)

    cols = {
        "nome_completo_norm": norm_col,
        "nome_completo_phon": _nullif_empty_sql(completo_phon),
        "primeiro_nome": _nullif_empty_sql(partes["primeiro_nome"]),
        "nome_meio": _nullif_empty_sql(partes["nome_meio"]),
        "ultimo_nome": _nullif_empty_sql(partes["ultimo_nome"]),
        "primeiro_ultimo": _nullif_empty_sql(
            "TRIM(CONCAT_WS(' ', "
            f"NULLIF({partes['primeiro_nome']}, ''), "
            f"NULLIF({partes['ultimo_nome']}, '')))"
        ),
        "primeiro_nome_phon": _nullif_empty_sql(partes_phon["primeiro_nome"]),
        "nome_meio_phon": _nullif_empty_sql(partes_phon["nome_meio"]),
        "ultimo_nome_phon": _nullif_empty_sql(partes_phon["ultimo_nome"]),
        "primeiro_ultimo_phon": _nullif_empty_sql(
            "TRIM(CONCAT_WS(' ', "
            f"NULLIF({partes_phon['primeiro_nome']}, ''), "
            f"NULLIF({partes_phon['ultimo_nome']}, '')))"
        ),
    }
    if col_map:
        cols = {col_map[k]: v for k, v in cols.items() if k in col_map}
    return cols


def select_list_sql(cols: dict[str, str]) -> str:
    """Transforma o dicionário de colunas num trecho de SELECT."""
    return ",\n        ".join(f"{expr} AS {alias}" for alias, expr in cols.items())

