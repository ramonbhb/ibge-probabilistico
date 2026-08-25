"""Spec compartilhada de blocking Splink (02 treinar e 03 avaliar)."""

from __future__ import annotations

# Colunas de cada regra OR. Spec vigente = 02_treinar (predição).
# 02: block_on(*cols). 03: blocking_rules_or_sql() no WHERE dos pares distintos.
# Sexo só na regra sem nome DOB+UF (parte o bloco largo). Não entra nas regras com nome.
# cpf_norm NÃO entra aqui: só prior/EM no 02. No Censo a coluna só existe na ouro 1:1;
# incluí-la na predição faria a ouro sempre candidata e o 03 circularia.
BLOCKING_RULE_COLUMNS: tuple[tuple[str, ...], ...] = (
    ("nome_completo_phon",),
    ("primeiro_nome_phon", "ultimo_nome_phon", "ano_nascimento"),
    ("primeiro_nome_phon", "ultimo_nome_phon", "mes_nascimento", "dia_nascimento"),
    ("primeiro_nome_phon", "ultimo_nome_phon", "mes_nascimento", "ano_nascimento"),
    ("primeiro_nome_phon", "data_nascimento"),
    ("ultimo_nome_phon", "data_nascimento"),
    ("primeiro_nome_phon", "mes_nascimento", "dia_nascimento"),
    ("primeiro_nome_phon", "mes_nascimento", "ano_nascimento"),
    ("ultimo_nome_phon", "mes_nascimento", "dia_nascimento"),
    ("ultimo_nome_phon", "mes_nascimento", "ano_nascimento"),
    ("data_nascimento", "cep"),
    ("data_nascimento", "uf", "sexo"),
)


def blocking_rule_sql(
    columns: tuple[str, ...],
    left_alias: str,
    right_alias: str,
) -> str:
    parts = [f"{left_alias}.{col} = {right_alias}.{col}" for col in columns]
    if len(parts) == 1:
        return parts[0]
    return "(" + " AND ".join(parts) + ")"


def blocking_rules_or_sql(left_alias: str = "l", right_alias: str = "r") -> str:
    """Disjunção das regras, para WHERE de labels / cobertura de blocking."""
    return " OR ".join(
        blocking_rule_sql(cols, left_alias, right_alias)
        for cols in BLOCKING_RULE_COLUMNS
    )
