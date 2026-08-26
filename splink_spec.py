"""Spec compartilhada de blocking e settings Splink (02 treinar / 02b / 03).

Notebooks orquestram o fluxo; esta módulo é a fonte única das regras e do
SettingsCreator — não substitui os notebooks.
"""

from __future__ import annotations

from typing import Any

# Colunas de cada regra OR. Spec vigente = 02_treinar (predição).
# 02: block_on(*cols). 03: blocking_rules_or_sql() no WHERE dos pares distintos.
# Sexo: DOB+UF (parte o bloco sem nome) e último+mês+dia (aperta o bloco largo).
# Não entra nas regras que já têm primeiro+último.
# cpf_norm NÃO entra aqui: só prior/EM no 02. No Censo a coluna vem da coorte;
# incluí-la na predição faria a GT sempre candidata e o 03 circularia.
BLOCKING_RULE_COLUMNS: tuple[tuple[str, ...], ...] = (
    ("nome_completo_phon",),
    ("primeiro_nome_phon", "ultimo_nome_phon", "ano_nascimento"),
    ("primeiro_nome_phon", "ultimo_nome_phon", "mes_nascimento", "dia_nascimento"),
    ("primeiro_nome_phon", "ultimo_nome_phon", "mes_nascimento", "ano_nascimento"),
    ("primeiro_nome_phon", "data_nascimento"),
    ("ultimo_nome_phon", "data_nascimento"),
    ("primeiro_nome_phon", "mes_nascimento", "dia_nascimento"),
    ("primeiro_nome_phon", "mes_nascimento", "ano_nascimento"),
    ("ultimo_nome_phon", "mes_nascimento", "dia_nascimento", "sexo"),
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


def build_blocking_rules() -> list[Any]:
    """Lista de block_on(...) para SettingsCreator / chart de blocking."""
    from splink import block_on

    return [block_on(*cols) for cols in BLOCKING_RULE_COLUMNS]


def data_nascimento_comparison():
    """Um eixo de data: Null → Exact+TF → DL≤1 → mês e dia iguais → ELSE m=1e-6.

    Não usa NullLevel('data_nascimento'): isso abortaria o score quando o ano
    foi anulado e mês/dia restaram. ELSE fixo (~−20 bits) para datas que
    discordam de verdade.
    """
    import splink.comparison_level_library as cll
    import splink.comparison_library as cl

    null_sql = (
        "(data_nascimento_l IS NULL OR data_nascimento_r IS NULL) AND "
        "(mes_nascimento_l IS NULL OR mes_nascimento_r IS NULL OR "
        "dia_nascimento_l IS NULL OR dia_nascimento_r IS NULL)"
    )
    mes_dia_sql = (
        "mes_nascimento_l = mes_nascimento_r AND "
        "dia_nascimento_l = dia_nascimento_r AND "
        "mes_nascimento_l IS NOT NULL AND dia_nascimento_l IS NOT NULL"
    )
    return cl.CustomComparison(
        comparison_levels=[
            cll.CustomLevel(null_sql, label_for_charts="Null data e mes/dia").configure(
                is_null_level=True
            ),
            cll.ExactMatchLevel("data_nascimento", term_frequency_adjustments=True),
            cll.DamerauLevenshteinLevel("data_nascimento", 1),
            cll.CustomLevel(mes_dia_sql, label_for_charts="Mes e dia iguais"),
            cll.ElseLevel().configure(
                m_probability=1e-6,
                fix_m_probability=True,
            ),
        ],
        output_column_name="data_nascimento",
    )


def build_comparisons() -> list[Any]:
    """Comparisons da 1ª passada (sem nome_mae*, sem nome_meio, sem sexo/CEP/CPF)."""
    import splink.comparison_level_library as cll
    import splink.comparison_library as cl

    return [
        cl.NameComparison(
            "nome_completo_phon", jaro_winkler_thresholds=[0.95, 0.92]
        ).configure(term_frequency_adjustments=True),
        cl.NameComparison(
            "primeiro_nome_phon", jaro_winkler_thresholds=[0.95, 0.92]
        ).configure(term_frequency_adjustments=True),
        cl.NameComparison(
            "ultimo_nome_phon", jaro_winkler_thresholds=[0.95, 0.92]
        ).configure(term_frequency_adjustments=True),
        data_nascimento_comparison(),
        cl.CustomComparison(
            comparison_levels=[
                cll.NullLevel("idade"),
                cll.ExactMatchLevel("idade"),
                cll.AbsoluteDifferenceLevel("idade", 1),
                cll.ElseLevel(),
            ],
            output_column_name="idade",
        ),
        cl.ExactMatch("uf").configure(term_frequency_adjustments=True),
    ]


def build_settings(*, blocking_rules: list[Any] | None = None):
    """SettingsCreator link_only Censo × CPF."""
    from splink import SettingsCreator

    return SettingsCreator(
        link_type="link_only",
        unique_id_column_name="unique_id",
        comparisons=build_comparisons(),
        blocking_rules_to_generate_predictions=(
            blocking_rules if blocking_rules is not None else build_blocking_rules()
        ),
        retain_intermediate_calculation_columns=True,
    )


def deterministic_prior_rules() -> list[Any]:
    """Regras do prior (estimate_probability_two_random_records_match)."""
    from splink import block_on

    return [
        block_on("nome_completo_phon", "data_nascimento"),
        block_on("cpf_norm"),
    ]
