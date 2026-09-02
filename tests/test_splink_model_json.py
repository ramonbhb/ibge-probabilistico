"""Contrato do JSON (02) e das 12 regras de predição (02b)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MODELS_DIR, SPLINK_MODEL_JSON  # noqa: E402

_BLOCK_ON = re.compile(r"block_on\((.*?)\)", re.S)
_QUOTED = re.compile(r"['\"](\w+)['\"]")
_NOTEBOOK_02B = Path(__file__).resolve().parent.parent / "notebooks" / "02b_aplicar_splink.ipynb"


def _model_path() -> Path | None:
    for path in (SPLINK_MODEL_JSON, MODELS_DIR / "splink_model.json"):
        if path.exists():
            return path
    return None


def _blocking_from_02b() -> list[tuple[str, ...]]:
    nb = json.loads(_NOTEBOOK_02B.read_text(encoding="utf-8"))
    src = None
    for cell in nb["cells"]:
        text = "".join(cell.get("source", []))
        if "blocking_rules = [" in text:
            src = text
            break
    if src is None:
        raise AssertionError("02b sem célula blocking_rules")
    return [tuple(_QUOTED.findall(args)) for args in _BLOCK_ON.findall(src)]


@pytest.fixture(scope="module")
def model() -> dict:
    path = _model_path()
    if path is None:
        pytest.skip("splink_model.json ausente — rode notebooks/02_treinar_splink.ipynb")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    comparison_names = [c["output_column_name"] for c in data.get("comparisons", [])]
    if (
        "primeiro_nome_phon" not in comparison_names
        or "ultimo_nome_phon" not in comparison_names
        or "nome_meio_phon" in comparison_names
        or "sexo" in comparison_names
    ):
        pytest.skip(
            f"{path} ainda é um JSON antigo "
            "(score fora do spec: completo + primeiro + último, sem meio/sexo). "
            "Retreinar notebooks/02_treinar_splink.ipynb."
        )
    return data


@pytest.fixture(scope="module")
def blocking_cols() -> list[tuple[str, ...]]:
    return _blocking_from_02b()


@pytest.fixture(scope="module")
def comparison_names(model: dict) -> list[str]:
    return [c["output_column_name"] for c in model["comparisons"]]


def test_doze_regras_predicao(blocking_cols: list[tuple[str, ...]]) -> None:
    assert len(blocking_cols) == 12
    assert blocking_cols[0] == ("nome_completo_phon",)
    assert ("data_nascimento", "cep") in blocking_cols
    assert ("data_nascimento", "uf", "sexo", "cep") in blocking_cols
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
        "cep",
    ) in blocking_cols


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
    assert ("data_nascimento", "uf", "sexo", "cep") in com_sexo
    assert (
        "ultimo_nome_phon",
        "mes_nascimento",
        "dia_nascimento",
        "sexo",
        "cep",
    ) in com_sexo
    assert len(com_sexo) == 2
    for cols in blocking_cols:
        if "primeiro_nome_phon" in cols and "ultimo_nome_phon" in cols:
            assert "sexo" not in cols


def test_comparisons_sem_cpf_sexo_cep(comparison_names: list[str]) -> None:
    blob = " ".join(comparison_names).lower()
    assert "cpf" not in blob
    assert "sexo" not in blob
    assert "cep" not in blob


def test_comparisons_completo_primeiro_ultimo_sem_composto_sem_meio_sem_mae(
    comparison_names: list[str],
) -> None:
    assert "nome_completo_phon" in comparison_names
    assert "primeiro_nome_phon" in comparison_names
    assert "ultimo_nome_phon" in comparison_names
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
    labels = [lvl.get("label_for_charts", "") for lvl in levels]
    sqls = " ".join(lvl.get("sql_condition", "") for lvl in levels)
    assert levels[0].get("is_null_level") is True
    assert any("mes" in lab.lower() and "dia" in lab.lower() for lab in labels)
    assert "mes_nascimento_l = mes_nascimento_r" in sqls
    assert "dia_nascimento_l = dia_nascimento_r" in sqls
    else_lvl = levels[-1]
    assert else_lvl.get("sql_condition") == "ELSE"
    assert else_lvl.get("m_probability") == 1e-6
    assert else_lvl.get("fix_m_probability") is True
