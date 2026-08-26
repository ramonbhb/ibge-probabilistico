"""Blocking rules e comparisons compartilhadas entre 02 e 03."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from splink_spec import (  # noqa: E402
    BLOCKING_RULE_COLUMNS,
    blocking_rule_sql,
    blocking_rules_or_sql,
)


def test_doze_regras() -> None:
    assert len(BLOCKING_RULE_COLUMNS) == 12
    assert BLOCKING_RULE_COLUMNS[0] == ("nome_completo_phon",)
    assert ("data_nascimento", "cep") in BLOCKING_RULE_COLUMNS
    assert ("data_nascimento", "uf", "sexo") in BLOCKING_RULE_COLUMNS
    assert (
        "ultimo_nome_phon",
        "mes_nascimento",
        "dia_nascimento",
        "sexo",
    ) in BLOCKING_RULE_COLUMNS


def test_cpf_fora_do_blocking_de_predicao() -> None:
    for cols in BLOCKING_RULE_COLUMNS:
        assert "cpf_norm" not in cols
    assert "cpf_norm" not in blocking_rules_or_sql("ca", "pb")


def test_sexo_nas_regras_esperadas() -> None:
    com_sexo = [cols for cols in BLOCKING_RULE_COLUMNS if "sexo" in cols]
    assert ("data_nascimento", "uf", "sexo") in com_sexo
    assert (
        "ultimo_nome_phon",
        "mes_nascimento",
        "dia_nascimento",
        "sexo",
    ) in com_sexo
    assert len(com_sexo) == 2
    for cols in BLOCKING_RULE_COLUMNS:
        if "primeiro_nome_phon" in cols and "ultimo_nome_phon" in cols:
            assert "sexo" not in cols


def test_sql_or_tem_todas_as_regras() -> None:
    sql = blocking_rules_or_sql("ca", "pb")
    assert sql.count(" OR ") == 11
    assert "ca.nome_completo_phon = pb.nome_completo_phon" in sql
    assert "ca.ultimo_nome_phon = pb.ultimo_nome_phon" in sql
    assert "ca.mes_nascimento = pb.mes_nascimento" in sql
    assert "ca.cep = pb.cep" in sql
    assert "ca.uf = pb.uf" in sql
    assert "ca.sexo = pb.sexo" in sql


def test_regra_unica_sem_parenteses_extras() -> None:
    assert (
        blocking_rule_sql(("nome_completo_phon",), "l", "r")
        == "l.nome_completo_phon = r.nome_completo_phon"
    )
    assert blocking_rule_sql(
        ("primeiro_nome_phon", "sexo"), "l", "r"
    ) == "(l.primeiro_nome_phon = r.primeiro_nome_phon AND l.sexo = r.sexo)"


def test_build_blocking_rules_len() -> None:
    try:
        from splink_spec import build_blocking_rules
    except ImportError:
        pytest.skip("splink não instalado")
    try:
        rules = build_blocking_rules()
    except ImportError:
        pytest.skip("splink não instalado")
    assert len(rules) == len(BLOCKING_RULE_COLUMNS)


def test_build_comparisons_sem_cpf_sexo_cep() -> None:
    try:
        from splink_spec import build_comparisons
    except ImportError:
        pytest.skip("splink não instalado")
    try:
        comps = build_comparisons()
    except ImportError:
        pytest.skip("splink não instalado")
    blob = " ".join(str(c) for c in comps).lower()
    assert "cpf" not in blob
    assert "sexo" not in blob
    assert "cep" not in blob


def test_comparisons_sem_meio_nem_partes_de_data() -> None:
    try:
        from splink.internals.dialects import DuckDBDialect

        from splink_spec import build_comparisons, data_nascimento_comparison
    except ImportError:
        pytest.skip("splink não instalado")
    try:
        comps = build_comparisons()
        dob = data_nascimento_comparison()
        dialect = DuckDBDialect()
    except ImportError:
        pytest.skip("splink não instalado")

    names = [c.create_output_column_name() for c in comps]
    assert "nome_meio_phon" not in names
    assert "ano_nascimento" not in names
    assert "mes_nascimento" not in names
    assert "dia_nascimento" not in names
    assert "nome_completo_phon" in names
    assert "primeiro_nome_phon" in names
    assert "ultimo_nome_phon" in names
    assert "data_nascimento" in names

    levels = dob.create_comparison_levels()
    sqls = " ".join(lvl.create_sql(dialect) for lvl in levels)
    labels = [lvl.create_label_for_charts() for lvl in levels]
    assert "damerau" in sqls.lower() or "levenshtein" in sqls.lower()
    assert "ELSE" in sqls
    assert any("mes" in lab.lower() and "dia" in lab.lower() for lab in labels)
    else_lvl = levels[-1]
    assert else_lvl.m_probability == 1e-6
    assert else_lvl.fix_m_probability is True
    assert levels[0].is_null_level is True
    assert "mes_nascimento_l = mes_nascimento_r" in sqls
    assert "dia_nascimento_l = dia_nascimento_r" in sqls
