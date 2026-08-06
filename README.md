# Linkage probabilístico — Censo × CPF

Pipeline interativo (notebooks + DuckDB) para empilhar **bases bronze** CPF e Censo, rodar **Splink dedupe_only** cross-source e avaliar contra **ground truth** da coorte (`cohort_dedup`).

Treino e validação são separados: o modelo é treinado sem ver a coorte (NB02) e só depois avaliado contra ela (NB03).

## Pré-requisitos

1. Parquets bronze + `cohort_dedup.parquet` ([`cohort/`](../cohort/))
2. `pip install -e .` em `probabilistico/`

## Configuração

Edite [`config.py`](config.py) ou exporte:

```bash
export FILTRO_UF=35
export FILTRO_MUNICIPIO=3550308   # ex.: São Paulo (IBGE 7 díg.); None = sem filtro
export OUTPUT_DIR=~/data/probabilistico_output
export USE_PHONETIC_STRIP_VOWELS=false   # true = colunas *_phon_sv (remove vogais)
export DUCKDB_THREADS=20                  # Splink/DuckDB (default em config.py)
export DUCKDB_MEMORY_LIMIT=300GB          # Splink/DuckDB (default em config.py)
# CENSO_CEP_ARQUIVO default: ~/singed/bases/raw/Censo/data_cep_uniq.csv
```

Para sobrescrever o filtro geográfico dentro de um notebook, use `config.set_filtros()` — nunca reatribua `FILTRO_UF` / `FILTRO_MUNICIPIO`:

```python
import config
config.set_filtros(municipio=2111300)   # None desliga o filtro
print(config.FILTRO_UF, config.FILTRO_MUNICIPIO)
```

`from config import FILTRO_UF` copia o valor no momento do import; reatribuir essa cópia deixa o notebook exibindo o filtro novo enquanto as funções de filtro continuam usando o antigo.

## Notebooks

| Notebook | Função |
|----------|--------|
| [`00_preparar_bases.ipynb`](notebooks/00_preparar_bases.ipynb) | Bronze → filtro UF/município → inferência mãe → CEP → stack |
| [`00_preparar_bases_leve.ipynb`](notebooks/00_preparar_bases_leve.ipynb) | Igual ao NB00, split SQL rápido — ideal para iterar Splink |
| [`01_analise_descritiva.ipynb`](notebooks/01_analise_descritiva.ipynb) | EDA visual: missing, top nomes, sexo, DOB, idade, CEP, UF, município |
| [`02_deduplicar_splink.ipynb`](notebooks/02_deduplicar_splink.ipynb) | Profile + blocking pré-treino + treino + predict/clustering (sem coorte) |
| [`03_validar_coorte.ipynb`](notebooks/03_validar_coorte.ipynb) | Labels da coorte (positivos + negativos difíceis) → precision/recall |

**Pipeline:** `00` → `01_analise_descritiva` → `02_deduplicar_splink` → `03_validar_coorte`.

O NB03 depende dos artefatos do NB02 (`splink_model.json`, `splink_clusters.parquet`) e recarrega o modelo do JSON, sem reestimar nada.

**REBUILD:** no NB00, `REBUILD=False` reutiliza `probabilistico.duckdb` sem refazer. **`REFILTER_GEO=True`** refaz só filtro UF/município.

**Blocking Splink:** regras definidas inline no NB02 (colunas completas, sem `substr`). Profile, gráfico cumulativo e maiores blocos são executados **antes** do treino.

Referências: [`notebooks/_exemplo/`](notebooks/_exemplo/) (Splink + inferência mãe didática).

## Variáveis unificadas

- Nome: completo, primeiro/meio/último
- **`nome_mae`:** CPF direto (`NOM_MAE`); Censo **inferido** por domicílio ([`inferir_pais.py`](inferir_pais.py))
- **CEP Censo:** join `data_cep_uniq.csv` por `B0000` + quadra/face ([`materialize_censo_cep_lookup`](config.py))
- Sexo, DOB, **idade** (anos na referência do Censo 2022), CEP, **UF**, **`cod_municipio`** (IBGE 7 díg.)
- **`idade`:** Censo `PECP0003` (anos), fallback `PECP0030` (meses → `FLOOR/12`); CPF `ANO_REFERENCIA_CENSO - ano(data_nascimento)` ([`idade_censo_sql`](config.py), [`idade_cpf_sql`](config.py))
- Fonética **básica** sempre: `*_phon` (substituições PT-BR)
- Fonética **agressiva** opcional: `*_phon_sv` (`USE_PHONETIC_STRIP_VOWELS=true`)

## Saídas

`~/data/probabilistico_output/`:

| Arquivo | Origem |
|---------|--------|
| `probabilistico.duckdb`, `registro_unificado.parquet` | NB00 |
| `splink_model.json`, `splink_predictions.parquet`, `splink_clusters.parquet`, `dashboards/cluster_studio.html` | NB02 |
| `metricas_cohort.csv` | NB03 |

## Ground truth

Somente `cohort_dedup.parquet` — ouro + prata. Listas ouro **não** entram como dado de entrada.

A coorte é carregada apenas no NB03. Lá ela vira uma *labels table* do Splink com:

- **positivos:** pares Censo ↔ CPF estritamente 1:1 na coorte e presentes no subset filtrado;
- **negativos difíceis:** pares de indivíduos distintos da coorte que passam pelas mesmas blocking rules do modelo.

Sem os negativos explícitos o Splink trata todo par não rotulado como não-match, o que subestima a precision e infla a contagem de falsos positivos.
