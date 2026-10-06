"""Spec do modelo v2 (mãe + endereço) e atribuição simples sem escada."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
NB02C = ROOT / "notebooks" / "02c_treinar_splink_mae_endereco.ipynb"
NB04 = ROOT / "notebooks" / "04_atribuir_mae_endereco.ipynb"


def _celula(nb_path: Path, cell_id: str) -> str:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell.get("id") == cell_id:
            return "".join(cell["source"])
    raise AssertionError(cell_id)


def test_02c_comparisons_mae_endereco_sem_uf() -> None:
    src = _celula(NB02C, "0b32ea1f")
    assert "output_column_name='nome_completo_phon'" in src
    assert "output_column_name='data_nascimento'" in src
    assert "output_column_name='nome_mae_phon'" in src
    assert "output_column_name='endereco'" in src
    assert "label_for_charts='Contida'" in src
    assert "Logradouro e CEP exact" in src
    assert "ExactMatch('uf')" not in src
    assert 'ExactMatch("uf")' not in src


def test_02c_em_mae_e_endereco() -> None:
    src = _celula(NB02C, "em-cpf")
    assert "em_mae" in src
    assert "em_endereco" in src
    assert "block_on('nome_completo_phon', 'data_nascimento')" in src


def test_04_simples_sem_escada() -> None:
    nb = json.loads(NB04.read_text(encoding="utf-8"))
    texto = "\n".join("".join(c["source"]) for c in nb["cells"])
    assert "degraus" not in texto
    assert "libera_11" not in texto
    assert "PISO = 0.50" in texto
    assert "nome_mae_phon IS NOT NULL AND pb.nome_mae_phon IS NOT NULL" in texto
    assert "logradouro_norm = pb.logradouro_norm" in texto
    assert "ca.cep = pb.cep" in texto
    assert "HAVING COUNT(*) <= {TETO}" in texto or "HAVING COUNT(*) <= " in texto


def test_atribuicao_simples_teto_e_desempate() -> None:
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE pessoas (
            unique_id VARCHAR,
            origem VARCHAR,
            nome_mae_phon VARCHAR,
            logradouro_norm VARCHAR,
            cep VARCHAR
        )
        """
    )
    con.executemany(
        "INSERT INTO pessoas VALUES (?, ?, ?, ?, ?)",
        [
            ("censo_A", "censo", "MARIA SILVA", "RUA A", "65000000"),
            ("censo_B", "censo", None, "RUA A", "65000000"),
            ("censo_C", "censo", "ANA", None, None),
            ("censo_D", "censo", "ANA", None, None),
            ("censo_E", "censo", "ANA", None, None),
            ("censo_F", "censo", "ANA", None, None),
            ("cpf_X", "cpf", "MARIA SILVA", "RUA A", "65000000"),
            ("cpf_Y", "cpf", None, "RUA B", "65000001"),
            ("cpf_Z", "cpf", None, None, None),
        ],
    )
    con.execute(
        """
        CREATE TABLE splink_predictions (
            unique_id_censo VARCHAR,
            unique_id_cpf VARCHAR,
            match_probability DOUBLE
        )
        """
    )
    # A: empate 0.80 entre X (mãe+logr+cep) e Y → fica X
    # B: só Y
    # C–F: todos no Z com nota alta → 4 censos → grupo Z cai
    con.executemany(
        "INSERT INTO splink_predictions VALUES (?, ?, ?)",
        [
            ("censo_A", "cpf_X", 0.80),
            ("censo_A", "cpf_Y", 0.80),
            ("censo_B", "cpf_Y", 0.70),
            ("censo_C", "cpf_Z", 0.90),
            ("censo_D", "cpf_Z", 0.89),
            ("censo_E", "cpf_Z", 0.88),
            ("censo_F", "cpf_Z", 0.87),
        ],
    )
    ns = {"con": con, "SPLINK_INPUT_VIEW": "pessoas", "PISO": 0.50, "TETO": 3}
    exec(_celula(NB04, "atribuir"), ns)
    lista = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT unique_id_censo, unique_id_cpf FROM atribuicao"
        ).fetchall()
    }
    con.close()
    assert lista["censo_A"] == "cpf_X"
    assert lista["censo_B"] == "cpf_Y"
    assert "censo_C" not in lista
    assert "censo_D" not in lista
    assert "censo_E" not in lista
    assert "censo_F" not in lista
