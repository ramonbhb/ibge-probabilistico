"""Inferência de nome da mãe no Censo a partir de relação familiar por domicílio."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from config import (
    CENSO_COL_ID_DOMICILIO,
    CENSO_COL_ID_MORADOR,
    CENSO_COL_PRIMEIRO_NOME,
    CENSO_COL_RELACAO,
    CENSO_COL_SEXO,
    CENSO_COL_SOBRENOME,
)
from features import normalize_text

if TYPE_CHECKING:
    import duckdb

RESPONSAVEL = "01"
CONJUGE = {"02", "03"}
FILHO_AMBOS = "04"
FILHO_RESP = "05"
ENTEADO = "06"
OUTROS_PAIS = "08"
SOGROS = "09"

SEXO_MASC = "1"
SEXO_FEM = "2"


def primeiro_nome_por_sexo(pessoas: list[dict[str, Any]], sexo_alvo: str) -> str | None:
    for p in pessoas:
        if str(p.get("sexo", "")).strip() == str(sexo_alvo):
            return p.get("nome_completo")
    return None


def inferir_pais_familia(membros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responsavel = [m for m in membros if m["relacao"] == RESPONSAVEL]
    conjuges = [m for m in membros if m["relacao"] in CONJUGE]
    sogros = [m for m in membros if m["relacao"] == SOGROS]
    outros_pais = [m for m in membros if m["relacao"] == OUTROS_PAIS]

    nome_mae_casa = primeiro_nome_por_sexo(responsavel + conjuges + outros_pais, SEXO_FEM)
    nome_pai_casa = primeiro_nome_por_sexo(responsavel + conjuges + outros_pais, SEXO_MASC)

    sogros_por_conjuge: dict[str, dict[str, str | None]] = {}
    if conjuges:
        id_conjuge = conjuges[0]["ID_MORADOR"]
        for s in sogros:
            bucket = sogros_por_conjuge.setdefault(id_conjuge, {})
            if s["sexo"] == SEXO_FEM:
                bucket["nome_mae"] = s["nome_completo"]
            elif s["sexo"] == SEXO_MASC:
                bucket["nome_pai"] = s["nome_completo"]

    saida: list[dict[str, Any]] = []
    for m in membros:
        rel = m["relacao"]
        pid = m["ID_MORADOR"]
        nome_mae: str | None = None
        nome_pai: str | None = None

        if rel == FILHO_AMBOS:
            nome_mae, nome_pai = nome_mae_casa, nome_pai_casa
        elif rel == FILHO_RESP:
            nome_mae = primeiro_nome_por_sexo(responsavel, SEXO_FEM)
            nome_pai = primeiro_nome_por_sexo(responsavel, SEXO_MASC)
        elif rel == ENTEADO:
            nome_mae = primeiro_nome_por_sexo(conjuges, SEXO_FEM)
            nome_pai = primeiro_nome_por_sexo(conjuges, SEXO_MASC)
        elif rel in CONJUGE:
            info = sogros_por_conjuge.get(pid, {})
            nome_mae = info.get("nome_mae")
            nome_pai = info.get("nome_pai")

        saida.append({
            "ID_DOMICILIO": m["ID_DOMICILIO"],
            "ID_MORADOR": pid,
            "nome_mae": normalize_text(nome_mae) if nome_mae else "",
        })

    return saida


def inferir_nome_mae_duckdb(
    con: duckdb.DuckDBPyConnection,
    *,
    source_table: str = "censo_pessoas_filtrado",
    target_table: str = "censo_pais_inferidos",
) -> None:
    """Materializa nome_mae inferido por morador.

    **Importante:** `source_table` deve ser a tabela já filtrada por UF
    (ex.: `censo_pessoas_filtrado`), nunca o bronze nacional inteiro.
    """
    q = f"""
    SELECT
        CAST({CENSO_COL_ID_DOMICILIO} AS VARCHAR) AS ID_DOMICILIO,
        CAST({CENSO_COL_ID_MORADOR} AS VARCHAR) AS ID_MORADOR,
        TRIM(COALESCE(CAST({CENSO_COL_PRIMEIRO_NOME} AS VARCHAR), '') || ' ' ||
             COALESCE(CAST({CENSO_COL_SOBRENOME} AS VARCHAR), '')) AS nome_completo,
        LPAD(TRIM(CAST({CENSO_COL_RELACAO} AS VARCHAR)), 2, '0') AS relacao,
        TRIM(CAST({CENSO_COL_SEXO} AS VARCHAR)) AS sexo
    FROM {source_table}
    ORDER BY 1, 2
    """
    cur = con.execute(q)

    out_rows: list[dict[str, Any]] = []
    current_fam: str | None = None
    membros: list[dict[str, Any]] = []

    def flush(membros_local: list[dict[str, Any]]) -> None:
        if membros_local:
            out_rows.extend(inferir_pais_familia(membros_local))

    while True:
        rows = cur.fetchmany(100_000)
        if not rows:
            break
        for id_dom, id_mor, nome, rel, sexo in rows:
            fam = str(id_dom)
            if current_fam is None:
                current_fam = fam
            if fam != current_fam:
                flush(membros)
                membros = []
                current_fam = fam
            membros.append({
                "ID_DOMICILIO": fam,
                "ID_MORADOR": str(id_mor),
                "nome_completo": str(nome).strip(),
                "relacao": str(rel).strip().zfill(2),
                "sexo": str(sexo).strip(),
            })

    flush(membros)

    con.register("_pais_inferidos_df", __import__("pandas").DataFrame(out_rows))
    con.execute(f"""
    CREATE OR REPLACE TABLE {target_table} AS
    SELECT
        CAST(ID_MORADOR AS VARCHAR) AS person_id_censo,
        CAST(ID_DOMICILIO AS VARCHAR) AS id_domicilio,
        NULLIF(TRIM(CAST(nome_mae AS VARCHAR)), '') AS nome_mae
    FROM _pais_inferidos_df
    """)
    con.unregister("_pais_inferidos_df")
