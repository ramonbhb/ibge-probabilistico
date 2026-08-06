"""Análise descritiva de registro_unificado (EDA sem Splink)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd

if TYPE_CHECKING:
    import duckdb

ORIGEM_COLORS = {"cpf": "#2563eb", "censo": "#16a34a"}


def _is_filled_sql(col: str) -> str:
    return f"({col} IS NOT NULL AND TRIM(CAST({col} AS VARCHAR)) <> '')"


def table_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return con.execute(f"SELECT * FROM {table} LIMIT 0").df().columns.tolist()


def missingness_table(
    con: duckdb.DuckDBPyConnection,
    table: str = "registro_unificado",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Percentual preenchido por coluna e origem."""
    available = set(table_columns(con, table))
    cols = [c for c in (columns or []) if c in available] if columns else sorted(available)
    if not cols:
        return pd.DataFrame()

    rows = []
    for col in cols:
        rows.append(
            con.execute(f"""
            SELECT
                '{col}' AS coluna,
                origem,
                COUNT(*) AS n,
                SUM(CASE WHEN {_is_filled_sql(col)} THEN 1 ELSE 0 END) AS preenchido
            FROM {table}
            GROUP BY origem
            """).df()
        )
    out = pd.concat(rows, ignore_index=True)
    out["pct_preenchido"] = (out["preenchido"] / out["n"] * 100).round(1)
    out["pct_missing"] = (100 - out["pct_preenchido"]).round(1)
    return out


def top_values(
    con: duckdb.DuckDBPyConnection,
    col: str,
    *,
    table: str = "registro_unificado",
    n: int = 20,
    origem: str | None = None,
    where_extra: str = "",
) -> pd.DataFrame:
    """Top-N valores de uma coluna (opcionalmente filtrado por origem)."""
    origem_clause = f"AND origem = '{origem.replace(chr(39), chr(39)+chr(39))}'" if origem else ""
    extra = f"AND ({where_extra})" if where_extra else ""
    return con.execute(f"""
    SELECT origem, CAST({col} AS VARCHAR) AS valor, COUNT(*) AS n
    FROM {table}
    WHERE {_is_filled_sql(col)} {origem_clause} {extra}
    GROUP BY origem, valor
    ORDER BY n DESC
    LIMIT {n * (2 if origem is None else 1)}
    """).df()


def count_by_origem(con: duckdb.DuckDBPyConnection, table: str = "registro_unificado") -> pd.DataFrame:
    return con.execute(f"""
    SELECT origem, COUNT(*) AS n
    FROM {table}
    GROUP BY origem
    ORDER BY origem
    """).df()


def sexo_distribution(con: duckdb.DuckDBPyConnection, table: str = "registro_unificado") -> pd.DataFrame:
    return con.execute(f"""
    SELECT
        origem,
        CASE
            WHEN NOT ({_is_filled_sql('sexo')}) THEN '(vazio)'
            WHEN UPPER(TRIM(CAST(sexo AS VARCHAR))) IN ('M', 'MASC', 'MASCULINO', '1') THEN 'M'
            WHEN UPPER(TRIM(CAST(sexo AS VARCHAR))) IN ('F', 'FEM', 'FEMININO', '2') THEN 'F'
            ELSE 'outro'
        END AS sexo_cat,
        COUNT(*) AS n
    FROM {table}
    GROUP BY origem, sexo_cat
    ORDER BY origem, sexo_cat
    """).df()


def dob_year_distribution(
    con: duckdb.DuckDBPyConnection,
    table: str = "registro_unificado",
) -> pd.DataFrame:
    return con.execute(f"""
    SELECT
        origem,
        TRY_CAST(substr(CAST(data_nascimento AS VARCHAR), 1, 4) AS INTEGER) AS ano,
        COUNT(*) AS n
    FROM {table}
    WHERE {_is_filled_sql('data_nascimento')}
      AND TRY_CAST(substr(CAST(data_nascimento AS VARCHAR), 1, 4) AS INTEGER) BETWEEN 1900 AND 2025
    GROUP BY origem, ano
    ORDER BY ano
    """).df()


def cep_prefix_top(
    con: duckdb.DuckDBPyConnection,
    *,
    table: str = "registro_unificado",
    top_n: int = 15,
) -> pd.DataFrame:
    return con.execute(f"""
    SELECT origem, substr(lpad(regexp_replace(CAST(cep AS VARCHAR), '[^0-9]', '', 'g'), 8, '0'), 1, 5) AS cep5,
           COUNT(*) AS n
    FROM {table}
    WHERE {_is_filled_sql('cep')}
    GROUP BY origem, cep5
    ORDER BY n DESC
    LIMIT {top_n * 2}
    """).df()


def uf_distribution(con: duckdb.DuckDBPyConnection, table: str = "registro_unificado") -> pd.DataFrame:
    return con.execute(f"""
    SELECT origem, CAST(uf AS VARCHAR) AS uf, COUNT(*) AS n
    FROM {table}
    WHERE {_is_filled_sql('uf')}
    GROUP BY origem, uf
    ORDER BY n DESC
    """).df()


def nome_meio_rate(con: duckdb.DuckDBPyConnection, table: str = "registro_unificado") -> pd.DataFrame:
    return con.execute(f"""
    SELECT
        origem,
        COUNT(*) AS n,
        SUM(CASE WHEN {_is_filled_sql('nome_meio')} THEN 1 ELSE 0 END) AS com_meio,
        ROUND(100.0 * SUM(CASE WHEN {_is_filled_sql('nome_meio')} THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_meio
    FROM {table}
    GROUP BY origem
    """).df()


def plot_origem_counts(df: pd.DataFrame, *, title: str = "Registros por origem") -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [ORIGEM_COLORS.get(o, "#64748b") for o in df["origem"]]
    ax.bar(df["origem"], df["n"], color=colors)
    ax.set_title(title)
    ax.set_ylabel("Quantidade")
    for i, v in enumerate(df["n"]):
        ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.show()


def plot_missingness_bars(df: pd.DataFrame, *, title: str = "Preenchimento por coluna (%)") -> None:
    if df.empty:
        return
    pivot = df.pivot(index="coluna", columns="origem", values="pct_preenchido").fillna(0)
    fig, ax = plt.subplots(figsize=(10, max(4, len(pivot) * 0.35)))
    pivot.plot(kind="barh", ax=ax, color=[ORIGEM_COLORS.get(c, "#64748b") for c in pivot.columns])
    ax.set_xlabel("% preenchido")
    ax.set_title(title)
    ax.legend(title="Origem")
    ax.set_xlim(0, 100)
    plt.tight_layout()
    plt.show()


def plot_top_bars(
    df: pd.DataFrame,
    *,
    title: str,
    value_col: str = "valor",
    split_by_origem: bool = True,
) -> None:
    if df.empty:
        return
    origens = df["origem"].unique() if split_by_origem else [None]
    ncols = len(origens) if split_by_origem else 1
    fig, axes = plt.subplots(1, ncols, figsize=(7 * ncols, 6), squeeze=False)
    for idx, orig in enumerate(origens if split_by_origem else [None]):
        ax = axes[0, idx]
        sub = df[df["origem"] == orig].head(20) if orig else df.head(20)
        sub = sub.sort_values("n")
        color = ORIGEM_COLORS.get(orig, "#64748b") if orig else "#64748b"
        ax.barh(sub[value_col], sub["n"], color=color)
        ax.set_title(f"{title}" + (f" — {orig}" if orig else ""))
        ax.set_xlabel("Quantidade")
    plt.tight_layout()
    plt.show()


def plot_sexo_distribution(df: pd.DataFrame) -> None:
    if df.empty:
        return
    pivot = df.pivot(index="sexo_cat", columns="origem", values="n").fillna(0)
    fig, ax = plt.subplots(figsize=(7, 4))
    pivot.plot(kind="bar", ax=ax, color=[ORIGEM_COLORS.get(c, "#64748b") for c in pivot.columns])
    ax.set_title("Distribuição de sexo")
    ax.set_ylabel("Quantidade")
    ax.set_xlabel("Sexo")
    ax.legend(title="Origem")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.show()


def plot_dob_year_hist(df: pd.DataFrame) -> None:
    if df.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    for orig in df["origem"].unique():
        sub = df[df["origem"] == orig]
        ax.hist(
            sub["ano"],
            bins=30,
            alpha=0.55,
            label=orig,
            weights=sub["n"],
            color=ORIGEM_COLORS.get(orig, "#64748b"),
        )
    ax.set_title("Distribuição do ano de nascimento")
    ax.set_xlabel("Ano")
    ax.set_ylabel("Quantidade")
    ax.legend(title="Origem")
    plt.tight_layout()
    plt.show()


def plot_cep_prefix(df: pd.DataFrame, *, title: str = "Top prefixos CEP (5 dígitos)") -> None:
    plot_top_bars(df, title=title, value_col="cep5")


def plot_uf_distribution(df: pd.DataFrame) -> None:
    if df.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    for orig in df["origem"].unique():
        sub = df[df["origem"] == orig].sort_values("n", ascending=False).head(10)
        ax.bar(
            [f"{orig}:{u}" for u in sub["uf"]],
            sub["n"],
            color=ORIGEM_COLORS.get(orig, "#64748b"),
            alpha=0.85,
            label=orig,
        )
    ax.set_title("UF — top 10 por origem")
    ax.set_ylabel("Quantidade")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.show()
