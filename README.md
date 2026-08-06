# Linkage probabilístico — Censo × CPF

Pipeline interativo (notebooks + DuckDB) para empilhar **bases bronze** CPF e Censo, rodar **Splink dedupe_only** cross-source e avaliar contra **ground truth** da coorte (`cohort_dedup`).

Treino e validação são separados: o modelo é treinado sem ver a coorte (NB02) e só depois avaliado contra ela (NB03).

## Pré-requisitos

1. Parquets bronze + `cohort_dedup.parquet` ([`cohort/`](../cohort/))
2. `pip install -e .` em `probabilistico/`

## Configuração

### Parâmetros de análise — só em [`config.py`](config.py)

Recorte geográfico e fonética mudam a cada rodada e ficam versionados, no bloco `PARÂMETROS DE ANÁLISE` no topo do arquivo:

```python
FILTRO_UF: str | int | None = None            # ex.: 42 (SC); None = nacional
FILTRO_MUNICIPIO: str | int | None = 2111300  # IBGE 7 díg.; None = sem filtro
USE_PHONETIC_STRIP_VOWELS = False             # True = colunas *_phon_sv (remove vogais)
ANO_OBITO_CORTE = 2021                        # óbito antes disso sai da base (NB00b)
ANO_NASCIMENTO_MIN = 1900                     # ano fora de [MIN, 2022] anula a data
SEXO_VALIDOS = ("M", "F")                     # fora daqui o sexo vira NULL
```

Não existem `export FILTRO_UF` / `export FILTRO_MUNICIPIO`: filtro é parâmetro de análise, não configuração de ambiente.

Para sobrescrever o filtro só na sessão atual de um notebook, use `config.set_filtros()` — nunca reatribua `FILTRO_UF` / `FILTRO_MUNICIPIO`:

```python
import config
config.set_filtros(municipio=2111300)   # None desliga o filtro
print(config.FILTRO_UF, config.FILTRO_MUNICIPIO)
```

`from config import FILTRO_UF` copia o valor no momento do import; reatribuir essa cópia deixa o notebook exibindo o filtro novo enquanto as funções de filtro continuam usando o antigo.

### Caminhos e recursos — variam por máquina

Têm default em `config.py` e aceitam variável de ambiente:

```bash
export OUTPUT_DIR=~/data/probabilistico_output
export DUCKDB_THREADS=20           # Splink/DuckDB
export DUCKDB_MEMORY_LIMIT=300GB   # Splink/DuckDB
```

Também aceitam override por ambiente: `CENSO_DIR`, `CENSO_RAW_DIR`, `CENSO_CEP_ARQUIVO` (default `~/singed/bases/raw/censo/data_cep_uniq.csv`), `CENSO_PESSOAS_ARQUIVO`, `CPF_ARQUIVO`, `COHORT_DIR`, `COHORT_DEDUP_ARQUIVO`, `DUCKDB_TEMP_DIR`.

## Notebooks

| Notebook | Função |
|----------|--------|
| [`00_preparar_bases.ipynb`](notebooks/00_preparar_bases.ipynb) | Bronze → filtro UF/município → inferência mãe → CEP → stack |
| [`00b_limpar_dados.ipynb`](notebooks/00b_limpar_dados.ipynb) | Remove óbito anterior ao Censo, anula data inválida e valores-sentinela |
| [`01_analise_descritiva.ipynb`](notebooks/01_analise_descritiva.ipynb) | EDA visual: missing, top nomes, sexo, DOB, idade, CEP, UF, município |
| [`02_deduplicar_splink.ipynb`](notebooks/02_deduplicar_splink.ipynb) | Profile + blocking pré-treino + treino + predict/clustering (sem coorte) |
| [`03_validar_coorte.ipynb`](notebooks/03_validar_coorte.ipynb) | Labels da coorte (positivos + negativos difíceis) → precision/recall |

**Pipeline:** `00` → `00b_limpar_dados` → `01_analise_descritiva` → `02_deduplicar_splink` → `03_validar_coorte`.

Do NB00b em diante tudo consome `registro_limpo`, não `registro_unificado`. O `materialize_splink_input` resolve isso sozinho e avisa alto se cair na tabela suja.

O NB03 depende dos artefatos do NB02 (`splink_model.json`, `splink_clusters.parquet`) e recarrega o modelo do JSON, sem reestimar nada.

**REBUILD:** no NB00, `REBUILD=False` reutiliza `probabilistico.duckdb` sem refazer. **`REFILTER_GEO=True`** refaz só filtro UF/município.

**Blocking Splink:** regras definidas inline no NB02 (colunas completas, sem `substr`). Profile, gráfico cumulativo e maiores blocos são executados **antes** do treino.

Referências: [`notebooks/_exemplo/`](notebooks/_exemplo/) (Splink + inferência mãe didática).

## Variáveis unificadas

- Nome: completo, primeiro/meio/último
- **`nome_mae`:** CPF direto (`NOM_MAE`); Censo **inferido** por domicílio ([`inferir_pais.py`](inferir_pais.py)). Sofre o mesmo split da pessoa: `primeiro_nome_mae`, `nome_meio_mae`, `ultimo_nome_mae`, com as fonéticas correspondentes. Vazio vira `NULL` (`NULLIF`), para o Splink não casar `'' = ''`
- **CEP Censo:** join `data_cep_uniq.csv` por `B0000` + quadra/face ([`materialize_censo_cep_lookup`](config.py))
- Sexo, DOB, **idade** (anos na referência do Censo 2022), CEP, **UF**, **`cod_municipio`** (IBGE 7 díg.)
- **`ano_obito`:** só CPF, `NULL` no Censo. Não entra em comparação — existe para o filtro do NB00b e para auditoria
- **`idade`:** anos completos na referência do Censo ([`idade_censo_sql`](config.py), [`idade_cpf_sql`](config.py)). Ver abaixo
- Fonética **básica** sempre: `*_phon` (substituições PT-BR)
- Fonética **agressiva** opcional: `*_phon_sv` (`USE_PHONETIC_STRIP_VOWELS=True`)

### Idade

No Censo as duas colunas **dividem a população**, não uma cobre a outra: `PECP0003` (3 díg.) é preenchida só para quem tem **1 ano ou mais**, `PECP0030` (2 díg.) só para **menores de 1 ano**. Quem tem meses preenchidos tem 0 ano completo — não se divide por 12. No CPF a idade é derivada de `data_nascimento`, então tudo que impede a data de parsear zera a idade junto.

Se a idade vier muito nula, a célula **3b do NB00** aponta a causa: tipos das colunas, contagem de nulos de cada lado e os valores crus mais frequentes. Dois casos conhecidos que zeram a idade do CPF inteiro:

- `DAT_NASCIMENTO` como **inteiro de 8 dígitos** (`19900102`) ou string compacta. O `normalize_date_sql` do `ibge_common` só reconhece data com separador. Por isso existe [`normalize_date_compacta_sql`](features.py), extensão local que aceita `YYYYMMDD` sem tocar na função compartilhada. É estritamente aditiva: só age onde a original falhava, exige 8 dígitos e valida via `strptime`, então `99999999` e `19900230` seguem rejeitados. O diagnóstico mostra `recuperado_compacto`, que é quanto esse formato estava custando.
- Data fora de `[ANO_NASCIMENTO_MIN, ANO_REFERENCIA_CENSO]`, que o NB00b anula junto com a idade.

### Featurização de nomes: SQL, não Python

Normalização, split e fonética são expressões SQL do DuckDB geradas por [`features.py`](features.py) (`normalize_text_sql`, `name_feature_columns_sql`, `select_list_sql`). O NB00 monta `*_registros` direto do staging, sem tabela intermediária: pessoa e mãe saem do mesmo passe, apenas com aliases diferentes (`PESSOA_COLUMNS`, `NOME_MAE_COLUMNS`).

A versão anterior trazia a tabela inteira para a memória via `fetch_arrow_table()` antes de distribuir em `ProcessPoolExecutor`. Em SQL o processamento é vetorizado e em streaming, sem teto de RAM.

Duas traduções não são literais, porque o RE2 do DuckDB não tem lookahead nem backreference no padrão:

- `C(?=[EI])` vira `regexp_replace(x, 'C([EI])', 'S\1', 'g')` — o `\1` vale na substituição;
- o dedupe de caracteres repetidos vira `list_reduce` sobre a lista de caracteres.

[`tests/test_featurizacao_sql.py`](tests/test_featurizacao_sql.py) compara SQL e Python coluna a coluna em nomes difíceis. Há **uma divergência conhecida e aceita**: `strip_accents` do DuckDB não decompõe ligaduras tipográficas (`ﬁ`), enquanto o NFKD do Python decompõe. Rode o benchmark com `BENCH_SQL=1 pytest tests/test_featurizacao_sql.py -s`.

## Limpeza (NB00b)

Duas classes de problema, um passe só sobre `registro_unificado`.

**Linha que não pode casar.** Quem morreu antes do Censo 2022 não foi enumerado, então nenhum par Censo × CPF com esse registro é verdadeiro. O corte é `ANO_OBITO_CORTE` sobre `ano_obito`, que vem de `CPF_COL_ANO_OBITO` no bronze. O NB00 falha se a coluna não estiver no bronze, em vez de preencher `NULL` e desligar o filtro em silêncio. Ano nulo (vivo, e todo o Censo), zero e valores absurdos no futuro ficam — o corte só tem limite inferior, para nunca descartar por ruído de digitação.

**Valor-sentinela que o SQL lê como igualdade.** É o problema mais caro dos dois. `l.cep = r.cep` trata `'' = ''` e `'00000000' = '00000000'` como acordo real, então ausência vira par candidato; nas `deterministic_rules` do NB02 vira até match determinístico, contaminando a estimativa do prior. As três colunas afetadas nascem assim: `normalize_date_sql` devolve `''` quando a data não parseia, `cep_norm_sql` faz `lpad(..., 8, '0')` e transforma CEP ausente do CPF em `'00000000'` (o Censo usa `''` para o mesmo caso), e nome que não normaliza vira `''` — inclusive `primeiro_nome` e `ultimo_nome`, que estão na blocking rule principal. Todos viram `NULL`, que não casa com `NULL`.

Data de nascimento inválida é a que não é data real (`2022-02-30` passa pelo `normalize_date_sql` quando já vem em ISO) ou tem ano fora de `[ANO_NASCIMENTO_MIN, ANO_REFERENCIA_CENSO]`. Quando a data do CPF cai, a `idade` cai junto, porque é derivada dela; a do Censo vem de `PECP0003` e não é tocada.

**Categoria residual de sexo.** O `normalize_sexo_sql` mapeia M/F e devolve a inicial de qualquer outra coisa: `'O'` de outro, `'I'` de ignorado, `'9'` de não informado. Para o `ExactMatch('sexo')` do NB02 dois resíduos iguais seriam concordância, e "ambos com sexo desconhecido" não é evidência de serem a mesma pessoa. Só `SEXO_VALIDOS` sobrevive. O NB00b imprime a distribuição completa com uma coluna `mantido` antes de aplicar a regra: se a base tiver uma terceira categoria real e com volume, anulá-la joga sinal fora e vale rever a constante.

O notebook separa **reencodado** (`''` que já era ausência e só mudou de grafia) de **descartado** (valor que existia e foi julgado inválido). O segundo número é o que merece revisão. Há também uma checagem de impacto na coorte: se o filtro de óbito remove ground truth, alguma das duas fontes está errada.

Regras em [`config.py`](config.py) (`obito_antes_do_censo_sql`, `dob_valida_sql`, `cep_valido_sql`, `limpeza_columns_sql`), cobertas por [`tests/test_limpeza.py`](tests/test_limpeza.py).

## Saídas

`~/data/probabilistico_output/`:

| Arquivo | Origem |
|---------|--------|
| `probabilistico.duckdb`, `registro_unificado.parquet` | NB00 |
| `registro_limpo.parquet` | NB00b |
| `splink_model.json`, `splink_predictions.parquet`, `splink_clusters.parquet`, `dashboards/cluster_studio.html` | NB02 |
| `metricas_cohort.csv` | NB03 |

## Ground truth

Somente `cohort_dedup.parquet` — ouro + prata. Listas ouro **não** entram como dado de entrada.

A coorte é carregada apenas no NB03. Lá ela vira uma *labels table* do Splink com:

- **positivos:** pares Censo ↔ CPF estritamente 1:1 na coorte e presentes no subset filtrado;
- **negativos difíceis:** pares de indivíduos distintos da coorte que passam pelas mesmas blocking rules do modelo.

Sem os negativos explícitos o Splink trata todo par não rotulado como não-match, o que subestima a precision e infla a contagem de falsos positivos.
