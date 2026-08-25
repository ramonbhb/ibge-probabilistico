"""Blocking rules compartilhadas entre 02 e 03."""

from __future__ import annotations

import sys
from pathlib import Path

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


def test_cpf_fora_do_blocking_de_predicao() -> None:
    for cols in BLOCKING_RULE_COLUMNS:
        assert "cpf_norm" not in cols
    assert "cpf_norm" not in blocking_rules_or_sql("ca", "pb")


def test_sexo_so_na_regra_sem_nome() -> None:
    com_sexo = [cols for cols in BLOCKING_RULE_COLUMNS if "sexo" in cols]
    assert com_sexo == [("data_nascimento", "uf", "sexo")]


def test_sql_or_tem_todas_as_regras() -> None:
    sql = blocking_rules_or_sql("ca", "pb")
    assert sql.count(" OR ") == 11
    assert "ca.nome_completo_phon = pb.nome_completo_phon" in sql
    assert "ca.ultimo_nome_phon = pb.ultimo_nome_phon" in sql
    assert "ca.mes_nascimento = pb.mes_nascimento" in sql
    assert "ca.cep = pb.cep" in sql
    assert "ca.uf = pb.uf" in sql


def test_regra_unica_sem_parenteses_extras() -> None:
    assert (
        blocking_rule_sql(("nome_completo_phon",), "l", "r")
        == "l.nome_completo_phon = r.nome_completo_phon"
    )
    assert blocking_rule_sql(
        ("primeiro_nome_phon", "sexo"), "l", "r"
    ) == "(l.primeiro_nome_phon = r.primeiro_nome_phon AND l.sexo = r.sexo)"
