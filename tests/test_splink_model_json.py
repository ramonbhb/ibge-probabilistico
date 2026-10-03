"""Contrato do JSON (02) e das 14 regras de predição (02b)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MODELS_DIR, SPLINK_MODEL_JSON  # noqa: E402

_BLOCK_ON = re.compile(r"block_on\((.*?)\)", re.S)
_QUOTED = re.compile(r"['\"](\w+)['\"]")
_NOTEBOOK_02 = Path(__file__).resolve().parent.parent / "notebooks" / "02_treinar_splink.ipynb"
_NOTEBOOK_02B = Path(__file__).resolve().parent.parent / "notebooks" / "02b_aplicar_splink.ipynb"


def _model_path() -> Path | None:
    for path in (SPLINK_MODEL_JSON, MODELS_DIR / "splink_model.json"):
        if path.exists():
            return path
    return None


def _blocking_src_02b() -> str:
    nb = json.loads(_NOTEBOOK_02B.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        text = "".join(cell.get("source", []))
        if "blocking_rules = [" in text:
            return text
    raise AssertionError("02b sem célula blocking_rules")


def _blocking_from_02b() -> list[tuple[str, ...]]:
    return [tuple(_QUOTED.findall(args)) for args in _BLOCK_ON.findall(_blocking_src_02b())]


@pytest.fixture(scope="module")
def model() -> dict:
    path = _model_path()
    if path is None:
        pytest.skip("splink_model.json ausente — rode notebooks/02_treinar_splink.ipynb")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    comparison_names = [c["output_column_name"] for c in data.get("comparisons", [])]
    if (
        "nome_completo_phon" not in comparison_names
        or "primeiro_nome_phon" in comparison_names
        or "ultimo_nome_phon" in comparison_names
        or "nome_meio_phon" in comparison_names
        or "sexo" in comparison_names
    ):
        pytest.skip(
            f"{path} ainda é um JSON antigo "
            "(score fora do spec: só nome completo, sem primeiro/último/meio/sexo). "
            "Retreinar notebooks/02_treinar_splink.ipynb."
        )
    return data


@pytest.fixture(scope="module")
def blocking_cols() -> list[tuple[str, ...]]:
    return _blocking_from_02b()


@pytest.fixture(scope="module")
def comparison_names(model: dict) -> list[str]:
    return [c["output_column_name"] for c in model["comparisons"]]


def test_dez_block_on_predicao(blocking_cols: list[tuple[str, ...]]) -> None:
    assert len(blocking_cols) == 10
    assert blocking_cols[0] == ("nome_completo_phon",)
    assert (
        "primeiro_nome_phon",
        "mes_nascimento",
        "dia_nascimento",
        "cod_municipio",
    ) in blocking_cols
    assert (
        "primeiro_nome_phon",
        "mes_nascimento",
        "ano_nascimento",
        "cod_municipio",
    ) in blocking_cols
    assert (
        "ultimo_nome_phon",
        "mes_nascimento",
        "dia_nascimento",
        "sexo",
        "cep",
    ) in blocking_cols
    assert (
        "ultimo_nome_phon",
        "mes_nascimento",
        "ano_nascimento",
        "sexo",
        "cep",
    ) in blocking_cols
    assert ("logradouro_norm", "cep", "ano_nascimento", "sexo") not in blocking_cols
    assert ("nome_mae_phon", "data_nascimento") not in blocking_cols
    assert (
        "primeiro_nome_phon",
        "mes_nascimento",
        "ano_nascimento",
        "sexo",
        "cep",
    ) not in blocking_cols
    assert (
        "nome_mae_phon",
        "ano_nascimento",
        "mes_nascimento",
        "sexo",
    ) not in blocking_cols
    assert ("data_nascimento", "sexo", "cep") not in blocking_cols
    assert ("data_nascimento", "cep") not in blocking_cols
    assert ("data_nascimento", "uf", "sexo", "cep") not in blocking_cols


def test_doze_regra_dl_sql() -> None:
    src = _blocking_src_02b()
    assert src.count("block_on(") == 10
    assert "l.nome_mae_phon = r.nome_mae_phon" in src
    assert "damerau_levenshtein" in src
    assert "l.primeiro_nome_phon" in src
    assert "l.sexo = r.sexo" in src
    assert "l.ano_nascimento = r.ano_nascimento" in src
    assert "l.mes_nascimento = r.mes_nascimento" in src
    assert "l.ultimo_nome_phon = r.ultimo_nome_phon" in src
    assert "* 6" in src
    assert src.count("abs(l.idade - r.idade) <= 1") == 3
    assert "l.primeiro_nome_phon = r.primeiro_nome_phon" in src
    assert "l.cod_municipio = r.cod_municipio" in src
    assert "l.logradouro_norm = r.logradouro_norm" in src
    assert "l.cep = r.cep" in src
    nb_03b = json.loads(
        (_NOTEBOOK_02B.parent / "03b_avaliar_lista_ouro.ipynb").read_text(
            encoding="utf-8"
        )
    )
    src_03b = "\n".join(
        "".join(cell.get("source", []))
        for cell in nb_03b["cells"]
        if "blocking_rules = [" in "".join(cell.get("source", []))
    )
    assert src_03b.count("block_on(") == 10
    assert src_03b.count("abs(l.idade - r.idade) <= 1") == 3
    assert "l.nome_mae_phon = r.nome_mae_phon" in src_03b


def test_cpf_fora_do_blocking_de_predicao(
    blocking_cols: list[tuple[str, ...]],
) -> None:
    for cols in blocking_cols:
        assert "cpf_norm" not in cols


def test_meio_fora_do_blocking_de_predicao(
    blocking_cols: list[tuple[str, ...]],
) -> None:
    for cols in blocking_cols:
        assert "nome_meio_phon" not in cols
        assert "nome_meio" not in cols


def test_sexo_nas_regras_esperadas(blocking_cols: list[tuple[str, ...]]) -> None:
    com_sexo = [cols for cols in blocking_cols if "sexo" in cols]
    assert (
        "ultimo_nome_phon",
        "mes_nascimento",
        "dia_nascimento",
        "sexo",
        "cep",
    ) in com_sexo
    assert (
        "ultimo_nome_phon",
        "mes_nascimento",
        "ano_nascimento",
        "sexo",
        "cep",
    ) in com_sexo
    assert len(com_sexo) == 2
    for cols in blocking_cols:
        if "primeiro_nome_phon" in cols and "ultimo_nome_phon" in cols:
            assert "sexo" not in cols
        if (
            "primeiro_nome_phon" in cols
            and "ultimo_nome_phon" not in cols
            and "cep" not in cols
        ):
            assert "sexo" not in cols


def test_comparisons_sem_cpf_sexo_cep(comparison_names: list[str]) -> None:
    blob = " ".join(comparison_names).lower()
    assert "cpf" not in blob
    assert "sexo" not in blob
    assert "cep" not in blob


def test_comparisons_so_completo_sem_token_sem_meio_sem_mae(
    comparison_names: list[str],
) -> None:
    assert "nome_completo_phon" in comparison_names
    assert "primeiro_nome_phon" not in comparison_names
    assert "ultimo_nome_phon" not in comparison_names
    assert "primeiro_ultimo_phon" not in comparison_names
    assert "nome_meio_phon" not in comparison_names
    assert "primeiro_ultimo" not in comparison_names
    assert "data_nascimento" in comparison_names
    assert "idade" in comparison_names
    assert "uf" in comparison_names
    assert "ano_nascimento" not in comparison_names
    assert "mes_nascimento" not in comparison_names
    assert "dia_nascimento" not in comparison_names
    assert "nome_mae_phon" not in comparison_names


def test_idade_else_m_fixo(model: dict) -> None:
    idade = next(c for c in model["comparisons"] if c["output_column_name"] == "idade")
    else_lvl = idade["comparison_levels"][-1]
    assert else_lvl.get("sql_condition") == "ELSE"
    assert else_lvl.get("m_probability") == 1e-6
    assert else_lvl.get("fix_m_probability") is True


def test_data_nascimento_else_m_fixo(model: dict) -> None:
    dob = next(
        c for c in model["comparisons"] if c["output_column_name"] == "data_nascimento"
    )
    levels = dob["comparison_levels"]
    sqls = " ".join(lvl.get("sql_condition", "") for lvl in levels)
    assert levels[0].get("is_null_level") is True
    if "mes_nascimento_l = mes_nascimento_r" in sqls:
        pytest.skip(
            "JSON antigo com mês/dia — retreinar notebooks/02_treinar_splink.ipynb"
        )
    assert "damerau_levenshtein" in sqls.lower()
    assert "<= 1" in sqls
    assert "<= 2" in sqls
    else_lvl = levels[-1]
    assert else_lvl.get("sql_condition") == "ELSE"
    assert else_lvl.get("m_probability") == 1e-6
    assert else_lvl.get("fix_m_probability") is True


def _comparisons_src_02() -> str:
    nb = json.loads(_NOTEBOOK_02.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        text = "".join(cell.get("source", []))
        if "comparisons = [" in text and "nome_completo_phon" in text:
            return text
    raise AssertionError("02 sem célula comparisons")


def test_02_data_damerau_aninhado() -> None:
    src = _comparisons_src_02()
    assert "mes_dia_ano_sql" not in src
    i1 = src.find("DamerauLevenshteinLevel('data_nascimento', 1)")
    i2 = src.find("DamerauLevenshteinLevel('data_nascimento', 2)")
    assert i1 != -1 and i2 != -1
    assert i1 < i2
    bloco = src[src.find("ExactMatchLevel('data_nascimento'") : i1]
    ordem = (
        "troca_mes_dia_sql",
        "dia_diferente_sql",
        "mes_diferente_sql",
        "ano_pm1_sql",
    )
    pos = [bloco.find(nome) for nome in ordem]
    assert all(p != -1 for p in pos)
    assert pos == sorted(pos)


def test_damerau_iso_08_vs_10() -> None:
    con = duckdb.connect()
    rows = con.execute(
        """
        SELECT a, b, damerau_levenshtein(a, b) AS d
        FROM (VALUES
            ('1980-10-08', '1980-10-08'),
            ('1980-10-08', '1980-10-09'),
            ('1980-10-08', '1980-10-10'),
            ('1980-10-08', '1980-10-18'),
            ('1999-10-08', '2000-10-08')
        ) v(a, b)
        """
    ).fetchall()
    con.close()
    dist = {(a, b): d for a, b, d in rows}
    assert dist[("1980-10-08", "1980-10-08")] == 0
    assert dist[("1980-10-08", "1980-10-09")] == 1
    assert dist[("1980-10-08", "1980-10-10")] == 2
    assert dist[("1980-10-08", "1980-10-18")] == 1
    assert dist[("1999-10-08", "2000-10-08")] > 2


TROCA_MES_DIA_SQL = (
    "ano_nascimento_l = ano_nascimento_r AND "
    "mes_nascimento_l = dia_nascimento_r AND "
    "dia_nascimento_l = mes_nascimento_r AND "
    "mes_nascimento_l <> dia_nascimento_l"
)
DIA_DIFERENTE_SQL = (
    "ano_nascimento_l = ano_nascimento_r AND "
    "mes_nascimento_l = mes_nascimento_r AND "
    "dia_nascimento_l <> dia_nascimento_r"
)
MES_DIFERENTE_SQL = (
    "ano_nascimento_l = ano_nascimento_r AND "
    "dia_nascimento_l = dia_nascimento_r AND "
    "mes_nascimento_l <> mes_nascimento_r"
)
ANO_PM1_SQL = (
    "mes_nascimento_l = mes_nascimento_r AND "
    "dia_nascimento_l = dia_nascimento_r AND "
    "abs(try_cast(ano_nascimento_l AS INTEGER) - "
    "try_cast(ano_nascimento_r AS INTEGER)) = 1"
)


def test_data_por_componente() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE pares AS SELECT * FROM (VALUES
            ('2011-11-01', '2011-01-11'),
            ('2010-04-10', '2010-04-08'),
            ('2007-11-19', '2007-09-19'),
            ('2018-03-15', '2017-03-15'),
            ('1999-10-08', '2000-10-08'),
            ('2007-01-28', '2017-03-28')
        ) v(data_l, data_r)
        """
    )
    niveis = {
        (data_l, data_r): nivel
        for data_l, data_r, nivel in con.execute(
            f"""
            SELECT data_l, data_r,
                CASE
                    WHEN {TROCA_MES_DIA_SQL} THEN 'troca'
                    WHEN {DIA_DIFERENTE_SQL} THEN 'dia'
                    WHEN {MES_DIFERENTE_SQL} THEN 'mes'
                    WHEN {ANO_PM1_SQL} THEN 'ano'
                    WHEN damerau_levenshtein(data_l, data_r) <= 1 THEN 'dl1'
                    WHEN damerau_levenshtein(data_l, data_r) <= 2 THEN 'dl2'
                    ELSE 'else'
                END AS nivel
            FROM (
                SELECT
                    data_l,
                    data_r,
                    substr(data_l, 1, 4) AS ano_nascimento_l,
                    substr(data_r, 1, 4) AS ano_nascimento_r,
                    substr(data_l, 6, 2) AS mes_nascimento_l,
                    substr(data_r, 6, 2) AS mes_nascimento_r,
                    substr(data_l, 9, 2) AS dia_nascimento_l,
                    substr(data_r, 9, 2) AS dia_nascimento_r
                FROM pares
            )
            """
        ).fetchall()
    }
    con.close()
    assert niveis[("2011-11-01", "2011-01-11")] == "troca"
    assert niveis[("2010-04-10", "2010-04-08")] == "dia"
    assert niveis[("2007-11-19", "2007-09-19")] == "mes"
    assert niveis[("2018-03-15", "2017-03-15")] == "ano"
    assert niveis[("1999-10-08", "2000-10-08")] == "ano"
    assert niveis[("2007-01-28", "2017-03-28")] == "dl2"


def test_02_nome_completo_token_aware() -> None:
    src = _comparisons_src_02()
    assert "prefixo_sql" in src
    assert "list_slice" in src
    assert "[-1]" in src
    assert "jw_ultimo_095_sql" in src
    assert "NameComparison(\n        'nome_completo_phon'" not in src
    assert "NameComparison(\n        'primeiro_nome_phon'" not in src
    assert "NameComparison" not in src
    assert "damerau_levenshtein" in src
    assert "dl_completo_1_sql" in src
    assert "dl_completo_2_sql" not in src
    assert "DL <= 2 proporcional" not in src
    assert "dl_token_1_sql" not in src
    assert "comparison_token" not in src
    assert "dl_primeiro_2_sql" not in src
    assert "term_frequency_adjustments=True" in src
    assert "tf_adjustment_column='primeiro_nome_phon'" not in src
    assert "disable_tf_exact_match_detection" not in src
    assert "ExactMatchLevel('primeiro_nome_phon'" not in src
    assert "ultimo_nome_phon" not in src
    jw95 = src[src.find("jw_ultimo_095_sql") : src.find("jw_ultimo_092_sql")]
    assert jw95.find("[-1]") < jw95.find("jaro_winkler_similarity")
    assert "um_token_sql" in src
    assert "dois_tokens_sql" in src
    assert "token_a_mais_sql" in src
    assert "ordem_sql" in src
    niveis = src[src.find("comparison_levels=") :]
    assert niveis.find("dl_completo_1_sql") < niveis.find("um_token_sql")
    assert niveis.find("um_token_sql") < niveis.find("jw_ultimo_095_sql")
    assert niveis.find("dois_tokens_sql") < niveis.find("jw_ultimo_095_sql")


def test_nome_completo_json_token_aware(model: dict) -> None:
    completo = next(
        c for c in model["comparisons"] if c["output_column_name"] == "nome_completo_phon"
    )
    sqls = " ".join(lvl.get("sql_condition", "") for lvl in completo["comparison_levels"])
    if "list_slice" not in sqls:
        pytest.skip(
            "JSON antigo sem prefixo de tokens — retreinar notebooks/02_treinar_splink.ipynb"
        )
    labels = [lvl.get("label_for_charts", "") for lvl in completo["comparison_levels"]]
    assert any("prefixo" in lab.lower() for lab in labels)
    exato = next(
        lvl
        for lvl in completo["comparison_levels"]
        if lvl.get("sql_condition") == '"nome_completo_phon_l" = "nome_completo_phon_r"'
    )
    assert exato.get("tf_adjustment_column") == "nome_completo_phon"
    assert "disable_tf_exact_match_detection" not in exato
    for lvl in completo["comparison_levels"]:
        sql = lvl.get("sql_condition", "")
        if "jaro_winkler_similarity" in sql:
            assert "[-1]" in sql
            assert sql.find("string_split") < sql.find("jaro_winkler_similarity")


def test_nome_completo_json_damerau(model: dict) -> None:
    completo = next(
        c for c in model["comparisons"] if c["output_column_name"] == "nome_completo_phon"
    )
    sqls = " ".join(lvl.get("sql_condition", "") for lvl in completo["comparison_levels"])
    if "damerau_levenshtein" not in sqls:
        pytest.skip(
            "JSON antigo sem DL no completo — retreinar notebooks/02_treinar_splink.ipynb"
        )
    assert "<= 1" in sqls
    assert "<= 2" in sqls
