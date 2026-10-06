# Relatório — atribuição mãe + endereço (modelo + resgate)

Recorte UF 21. Pipeline: treino/aplicação Splink com mãe e endereço no score
([`02c`](notebooks/02c_treinar_splink_mae_endereco.ipynb) /
[`02d`](notebooks/02d_aplicar_splink_mae_endereco.ipynb)); atribuição com
faixas e regras R1/R2/R3
([`04_atribuir_mae_endereco`](notebooks/04_atribuir_mae_endereco.ipynb));
avaliação ([`05`](notebooks/05_avaliar_mae_endereco.ipynb)) e números finais
([`06`](notebooks/06_numeros_finais.ipynb)).

O relatório da escada antiga (sem mãe no score) fica em
[`RELATORIO_ATRIBUICAO.md`](RELATORIO_ATRIBUICAO.md) — não misturar.

---

## Avaliação — escada modelo + resgate (UF 21)

| Versão | Atribuídos | Cobertura aplicação |
|---|---:|---:|
| Escada antiga | 4.092.388 | 67,3% |
| Piso simples 0,50 | 4.352.929 | 71,6% |
| **Modelo ≥0,90 + R1/R2/R3** | **4.310.736** | **70,9%** |

Ganha **~218k** vs escada antiga; perde **~42k** vs piso 0,50 puro (esperado: cortou `0,50–0,90` sem corroborador).

### De onde veio a atribuição

| Faixa | Regra | n | % dos atribuídos |
|---|---|---:|---:|
| modelo | score | 4.130.020 | 95,8% |
| resgate | R1 | 62.354 | 1,4% |
| resgate | R2 | 20.897 | 0,5% |
| resgate | R3 | 20.040 | 0,5% |
| baixo | R1 | 62.868 | 1,5% |
| baixo | R2 | 8.133 | 0,2% |
| baixo | R3 | 6.424 | 0,1% |

Resgate+baixo = **180.716** (4,2%). Quase tudo é modelo alto.

### Qualidade (atribuídos)

- Data igual 83%; `|Δano|=0` 87%; CEP igual 66%; mãe preenchida 42% / igual 24%
- 1:1 dominante (4,08M CPF com 1 Censo; 110k com 2; 1,9k com 3)

### Quem ficou de fora

| Melhor p | n | % aplicação |
|---|---:|---:|
| ≥ 0,50 | 119.213 | 2,0% |
| 0,25–0,50 | 125.912 | 2,1% |
| 0,05–0,25 | 242.856 | 4,0% |
| sem par | 1.280.313 | 21,1% |

Dos 119k com `p ≥ 0,50` sem CPF, só **382** são teto — o resto **falhou R1/R2/R3**. Isso é o filtro anti-FP funcionando.

### Lista ouro (`censo_limpo`)

ouro 7,8% / pareamento 65,4% / sem CPF 26,8% (`nos_dois=0`).

### Leitura

1. **Perfil bom:** 96% com `p ≥ 0,90`; resgate é fino e majoritariamente R1 (data+nome).
2. **R3 merece olho** na amostra: casos tipo mesmo nome + mãe parecida com data bem diferente (ex. JOÃO PEREIRA 1966×1945) — risco clássico de FP; se incomodar, endurecer R3 ou tirar do `baixo`.
3. **Buraco grande continua sendo blocking** (1,28M sem par), não threshold.
4. Trade-off vs piso 0,50: −0,7 p.p. de cobertura por ~42k a menos, em troca de exigir âncora abaixo de 0,90 — alinhado ao que se queria.

---

## Regras da atribuição (referência)

| Faixa | Decisão |
|---|---|
| `p ≥ 0,90` | aceita pelo modelo (`score`) |
| `0,50 ≤ p < 0,90` | R1 ou R2 ou R3 |
| `0,25 ≤ p < 0,50` | R1 forte ou R2 (sem R3) |
| `p < 0,25` | não resgata |

Teto 3 cumulativo entre faixas. Prioridade no par: R1 > R2 > R3.

- **R1** — data exata + primeiro nome compatível + (nome contido ou cobertura de tokens ≥ 0,75 / 0,80 no baixo)
- **R2** — nome completo igual/contido + data plausível (≠ exata): \|Δdias\|≤1, ou mesmo dia/mês com \|Δano\|∈{1,10}
- **R3** — primeiro compatível + cobertura nominal + mãe presente + JW mãe (≥ 0,75); **apenas** em `0,50–0,90` (removido do baixo `< 0,50`)

Universo de aplicação: **6.079.030** Censos.

---

## Validação na lista de ouro

Notebook dedicado (não o 03b da escada antiga):
[`notebooks/03c_avaliar_lista_ouro_mae_endereco.ipynb`](notebooks/03c_avaliar_lista_ouro_mae_endereco.ipynb).

Usa `SPLINK_MODEL_MAE_ENDERECO`, blocking do 02d, `predict ≥ 0,25` e a
atribuição modelo/resgate/baixo (R3 só no resgate). Grava
`splink_predictions_ouro_mae_endereco.parquet`.

Rodar o 03c e colar aqui o pacote de métricas (recall, precisão, FP da
associação/escolha, decomposição do FN).
