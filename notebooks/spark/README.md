# Splink 5 + Spark

Fluxo oficial nesta branch (`spark-splink5`): **treino e apply no Spark**.
Os notebooks `02c`–`02g` com DuckDB ficam de lado.

## Ordem

### Pipeline UF21 (mãe + endereço)

1. Copiar para `/data/spark/shared/datasets/`:
   - `censo_limpo_uf21.parquet`, `cpf_limpo_uf21.parquet` (treino)
   - `censo_limpo_aplicacao.parquet`, `cpf_limpo_aplicacao.parquet` (apply)
2. [`01_treinar_mae_endereco_uf21.ipynb`](01_treinar_mae_endereco_uf21.ipynb)
   → grava `splink_model_mae_endereco.json`
3. [`02_aplicar_mae_endereco_uf21.ipynb`](02_aplicar_mae_endereco_uf21.ipynb)
   → grava `splink_predictions_mae_endereco_spark.parquet`

### Pipeline Luis nacional

1. Rodar o notebook 07 (DuckDB) e copiar CSVs para `/data/spark/shared/datasets/`:
   - treino: `censo_aplicacao_splink_cpf.csv`, `cpf_aplicacao_splink_cpf.csv`
   - apply: `censo_aplicacao_splink.csv`, `cpf_aplicacao_splink.csv`
2. [`03_treinar_luis_nacional.ipynb`](03_treinar_luis_nacional.ipynb)
   → grava `splink_model_mae_endereco_luis.json`
3. [`04_aplicar_luis_nacional.ipynb`](04_aplicar_luis_nacional.ipynb)
   → grava `splink_predictions_mae_endereco_luis.parquet`

## Sessão Spark

Config compartilhada em [`spark_cluster.json`](spark_cluster.json).

Nos notebooks, troque só:

```python
CLUSTER = 'small'  # ou 'full'
```

- `small` — 28 cores / 14 executors (teste)
- `full` — 42 cores / 21 executors (job pesado)

JAR Splink via `PYSPARK_SUBMIT_ARGS` (path no JSON). Checkpoint:
`/data/spark/shared/checkpoints`. Ajuste `driver.host` no JSON se
rodar em outra máquina.

**Reinicie o kernel** se a sessão Spark já existia sem o JAR / checkpoint /
perfil novo.

## Requisitos no cluster

- Splink 5 + PySpark
- Comparisons customizadas em SQL **Spark** (`split`/`size`/`jaro_winkler`), não DuckDB

## Linker (Splink 5.0)

```python
db_api = SparkAPI(
    spark_session=spark,
    break_lineage_method='checkpoint',
    repartition_after_blocking=False,
)
censo_in = db_api.register(df_censo, dataset_display_name='censo')
cpf_in = db_api.register(df_cpf, dataset_display_name='cpf')
linker = Linker([censo_in, cpf_in], settings)
```
