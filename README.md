# Linkage probabilístico — Censo × CPF

Pipeline interativo (notebooks + DuckDB) para empilhar **bases bronze** CPF e Censo, rodar **Splink dedupe_only** cross-source e avaliar contra **ground truth** da coorte (`cohort_dedup`).

## Pré-requisitos

1. Parquets bronze:
   - `~/singed/bases/bronze/cpf/cpf.parquet`
   - `~/singed/bases/bronze/censo/censo_pessoas_*.parquet`
   - `~/singed/bases/bronze/censo/censo_especie2_*.parquet`
2. Coorte atualizada: `~/capefe/dados/CohortDados/cohort_dedup.parquet` ([`cohort/`](../cohort/))

## Instalação

```bash
cd probabilistico
pip install -e .
# opcional: reutilizar normalização do monorepo
pip install -e ../ibge-listas
```

## Configuração

Edite [`config.py`](config.py) ou exporte variáveis:

```bash
export FILTRO_UF=35                    # SP — None = nacional
export CPF_ARQUIVO=~/singed/bases/bronze/cpf/cpf.parquet
export COHORT_DEDUP_ARQUIVO=~/capefe/dados/CohortDados/cohort_dedup.parquet
# placeholders (preencher após DESCRIBE no NB00):
export CPF_COL_NOME_MAE=NOM_MAE
export CENSO_COL_NOME_MAE=PECP0123
export ESPECIE2_COL_CEP=NUM_CEP
```

## Notebooks

Execute com cwd = `probabilistico/`.

| Notebook | Função |
|----------|--------|
| [`notebooks/00_preparar_bases.ipynb`](notebooks/00_preparar_bases.ipynb) | Bronze → DuckDB → `registro_unificado` + `ground_truth_clusters` |
| [`notebooks/01_explorar_variaveis.ipynb`](notebooks/01_explorar_variaveis.ipynb) | Profile, blocking analysis, draft Splink settings |
| [`notebooks/02_deduplicar_splink.ipynb`](notebooks/02_deduplicar_splink.ipynb) | Treino Splink, dedupe, métricas vs coorte |

Referência Splink: [`notebooks/_exemplo/deduplicate_50k_synthetic.ipynb`](notebooks/_exemplo/deduplicate_50k_synthetic.ipynb).

## Saídas

| Arquivo | Descrição |
|---------|-----------|
| `output/probabilistico.duckdb` | DuckDB persistente |
| `output/registro_unificado.parquet` | Stack Censo + CPF (schema Splink) |
| `output/ground_truth_clusters.parquet` | Labels `cluster` da coorte |
| `output/splink_settings_draft.json` | Settings candidatos (NB01) |
| `output/splink_predictions.parquet` | Pares preditos (NB02) |

## Variáveis unificadas

Nome completo, primeiro/meio/último, nome da mãe, sexo, data de nascimento, CEP, estado, UF, `cpf_norm` (balizador — opcional no match).

## Ground truth

Somente [`cohort_dedup.parquet`](../cohort/README.md) — ouro + prata, todas as fontes. **Não** usa listas ouro como entrada de dados.
