# Validação na lista de ouro

Pacote de métricas do [`notebooks/03b_avaliar_lista_ouro.ipynb`](notebooks/03b_avaliar_lista_ouro.ipynb). O [`03_avaliar.ipynb`](notebooks/03_avaliar.ipynb) não avalia ouro nem `cohort_dedup`.

Pergunta operacional: **dado que o pipeline associou um CPF, qual a chance de não ser o da lista?** No campo não há rótulo; a ouro 1:1 substitui isso.

## Recorte

- Esquerda: Censos da [`LISTA_OURO_ARQUIVO`](config.py) que existem em `censo_limpo` (`censo_ouro`).
- Direita: `cpf_limpo` do estado, **sem** tirar os CPFs da ouro (`cpf_limpo_aplicacao` não serve).
- Verdade: pares 1:1 da lista (`ID_MORADOR` ↔ `cpf_cpf`). Quem não está nos dois limpos é cobertura, não erro do modelo.
- Sistema: JSON do 02, 11 regras do 02b, `predict(p ≥ 0,5)`, atribuição do 04 (`T`, veto de mãe, teto `MAX_CENSOS_POR_CPF`).

Isso avalia o **pipeline**, não o EM isolado.

## Notação

No conjunto G (ouro 1:1 com os dois ids nas bases):

- `Y(c)` = CPF ouro
- `M(c)` = CPF de `melhor_por_censo` (`p ≥ T`, veto ok); indefinido se não há
- `A(c)` = CPF de `associacoes_unicas`; indefinido se não há

Quando `A` existe, `A = M`. A associação é a escolha **condicionada** a o CPF ter no máximo 3 Censos em `melhor_por_censo`.

Cada Censo de G cai em **um** corte:

| Corte | O que aconteceu |
|-------|-----------------|
| `associou_cpf_ouro` | Saiu em `associacoes_unicas` com o CPF da verdade. Acerto. |
| `associou_cpf_errado` | Saiu na associação com **outro** CPF. FP da associação. Também é FN (não associou o certo). |
| `melhor_par_mas_cpf_repartilhado` | Tinha `M`, mas o CPF ficou com 4+ Censos. |
| `teve_par_abaixo_de_T` | Entrou no predict (`p ≥ 0,5`) e não passou no corte / veto. |
| `nenhum_par` | Nenhuma linha no predict. |

## Métricas obrigatórias

1. **Recall de associação** = `P(A = Y)` = `n_associou_cpf_ouro / n_ouro`
2. **FN** = `1 − recall` = não associou o CPF ouro. Os quatro cortes restantes **somam** o FN; não o definem.
3. **Precisão da associação** = `P(A = Y | A definido)` = `n_associou_cpf_ouro / (n_associou_cpf_ouro + n_associou_cpf_errado)`
4. **FP da associação** = `1 − precisão` = `P(A ≠ Y | A definido)` — “associei e errei?”
5. **FP da escolha** = `P(M ≠ Y | M definido)` — o mesmo erro **antes** do teto de 3. Sempre `n_M_errado ≥ n_associou_cpf_errado`. Se FP da escolha for bem maior que FP da associação, o teto está retirando grupos ruins (e também pode retirar acerto compartilhado).
6. **Recall do par ouro no predict** = `P((c, Y) está no parquet com p ≥ 0,5)` — blocking + score, sem atribuição.
7. **Decomposição do FN** (partição): `associou_cpf_errado`, `melhor_par_mas_cpf_repartilhado`, `teve_par_abaixo_de_T`, `nenhum_par`.
8. **O mesmo pacote nos quadrantes** nome fonético igual/diferente × DOB igual/diferente (nulo não conta como igual).

F1 é opcional para slide. O par precisão + recall já é o padrão de validação de linkage 1:1.

## Gráficos Splink (`clerical_match_score`)

Diagnóstico de **ranking pairwise**, depois do pacote acima. Não substituem os 8 números.

Tabela `labels_clericais`: par ouro = 1; outro CPF do mesmo Censo em `splink_predictions` = 0. Sem negativo a ROC/precisão do Splink degeneram. O Splink re-pontua só esses pares (`accuracy_analysis_from_labels_table`, `prediction_errors_from_labels_table` no corte `T`).

Precisão/ROC/F1 daí comparam rótulo clerical × `match_probability` do par. Não são `P(A = Y | A definido)`. FP/FN do `prediction_errors` também são do par, não da associação 1:1.

## O que não é métrica de vínculo associado

- Acurácia com verdadeiro negativo (o TN é o estado inteiro).
- ROC/precisão Splink nos pares rotulados (mede ranking, não o CPF associado). Os gráficos do 03b são esse diagnóstico.
- `n_associou_cpf_errado / n_ouro` como “taxa de FP” (mistura quem nem associou; isso já é FN).
- Média de `p` do Splink (`p` não é P(match) neste notebook).
- Contar todo par `p ≥ T` que não é ouro: o Splink gera vários candidatos; a atribuição escolhe um.

## Limites

As taxas valem na população da ouro, não no Censo médio, salvo os quadrantes mostrarem o contrário. Lista “certa” costuma ser mais fácil que o morador médio (FP/FN otimistas); lista de casos duros vira o contrário.

A esquerda só tem Censo ouro: o teto de 3 vê menos competição que o 04 na aplicação. O CPF que cada Censo ouro *escolhe* (`M`) está bem simulado; quantos *sobrevivem* em `A` fica um pouco mais folgado.

O 00/02 ainda carimbam `cpf_norm` da `cohort_dedup` para prior/EM. O 03b **não** usa a coorte como rótulo. Se a ouro cruzar gente que o EM já viu, o modelo pode estar otimista — isso é treino, não a conta do 03b.

Erro da lista 1:1 (gêmeo, CPF repetido, rótulo ruim) vira FP/FN fictício. Com lista grande o erro de amostragem é irrelevante; viés da ouro e erro de rótulo dominam.
