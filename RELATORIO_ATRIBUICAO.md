# Atribuição depois do pareamento

Trecho para o relatório. Implementação: [`notebooks/04_atribuir.ipynb`](notebooks/04_atribuir.ipynb). Números: UF 21.

O pareamento (Splink) só devolve candidatos com uma nota de 0 a 1. Essa nota usa nome completo fonético, data de nascimento (idade como fallback) e UF. **O nome da mãe não entra na nota**; entra só na atribuição. A atribuição percorre os pares de cima para baixo e decide quem fica com CPF.

Uma pessoa do Censo recebe no máximo um CPF. Um CPF recebe no máximo três pessoas do Censo. A ficha aceita guarda o degrau da nota e o motivo (`score` ou o nome da prova).

## Resultado (UF 21)

| Série | Pessoas | % do Censo limpo |
|---|---:|---:|
| Lista ouro (determinístico) | 510.774 | 7,8% |
| Pareamento (escada) | 4.092.388 | 62,1% |
| Sem CPF | 1.986.642 | 30,1% |

No recorte de aplicação (já sem a lista ouro): **67,3%** atribuídos (4.092.388 de 6.079.030).

---

## Sequência das regras

As regras abaixo são a ordem lógica completa. Se um par falha em qualquer passo e não cai numa exceção explícita, ele não é atribuído naquele momento.

### 1. Piso de nota

Só entram pares com nota **≥ 0,05**. Abaixo disso o pareamento não alimenta a escada.

### 2. Fila de elegíveis (portas)

Há três portas. O par precisa passar por **uma** delas.

**Porta A — faixa [0,95 ; 0,99).**  
Entra direto. Não se exige primeiro nome parecido nem acordo de mãe. (Nessa faixa a atribuição ainda vai pedir prova extra no passo 4.)

**Porta B — demais notas (≥ 0,05, fora de A).**  
Exige as duas coisas:

1. **Primeiro nome** dos dois lados preenchido e com Levenshtein ≤ 1  
   **ou** a prova `data_uma_palavra` (definida no passo 4), com primeiro nome da pessoa fora do top 10 do Censo.
2. **Mãe:**
   - nota ≥ 0,99 → não se exige mãe (a nota basta na atribuição);
   - **ou** um dos lados sem mãe;
   - **ou** a mãe **passa** (passo 3);
   - **ou** nome completo e data de nascimento **iguais** nos dois lados (exceção dura).

**Porta C** não existe: quem não está em A nem B fica de fora da fila.

### 3. Quando a mãe “passa”

Usado quando os dois lados têm `nome_mae_phon`. A mãe passa se **qualquer** linha abaixo for verdadeira (avaliar de cima para baixo; a primeira que couber basta):

| # | Condição | Nota mínima |
|---|---|---|
| M1 | Nomes da mãe **iguais** | qualquer (≥ 0,05) |
| M2 | **Prefixo** igual com ≥ 2 palavras (o começo do nome mais longo coincide com o mais curto) | qualquer |
| M3 | Jaro-Winkler ≥ 0,75 | **≥ 0,50** |
| M4 | Mãe **contida** no outro nome, sem ser prefixo, com ≥ 2 palavras em comum | **≥ 0,50** |
| M5 | Uma palavra só da mãe contida no outro nome | **≥ 0,90** |
| M6 | Uma das datas **nula**, e (Jaro-Winkler ≥ 0,75 **ou** contida ≥ 2) | **≥ 0,35** |
| M7 | Data nula **ou** datas diferentes com \|ano_censo − ano_cpf\| ≤ 10, **e** ainda: (Jaro-Winkler ≥ 0,75 **e** primeiro nome da mãe fora do top 10 do Censo) **ou** contida com ≥ **3** palavras (nesse caso o top 10 não bloqueia) | **> 0,05 e < 0,50** |

Definições usadas em M4–M7:

- **Contida:** os nomes têm comprimentos diferentes; todas as palavras do mais curto aparecem no mais longo; e isso **não** é só o prefixo (M2).
- **Top 10 da mãe:** os 10 `primeiro_nome_mae_phon` mais frequentes no Censo de aplicação (na UF 21: MARIA, ANA, FRANCISCA, ANTONIA, RAIMUNDA, ADRIANA, ELIANE, SANDRA, MARCIA, PATRICIA).
- A diferença de ano em M7 usa as **datas** (não a coluna `idade`, que no Censo fica vazia quando a data existe).

Se os dois têm mãe e nenhuma linha M1–M7 vale, e não há a exceção nome+data iguais da porta B, a ficha **não entra** na fila (salvo a porta A).

### 4. Prova extra (corroborador)

Para toda nota **&lt; 0,99**, a atribuição exige uma prova além da nota. Vale a **primeira** que fechar, nesta ordem:

| Código | Prova |
|---|---|
| `mae` | Mãe passa (passo 3). |
| `logradouro` | Rua normalizada e município iguais. |
| `data_prefixo` | Data igual e prefixo do nome completo (≥ 2 palavras). |
| `data_primeiro` | Data igual, último nome igual, primeiro nome longo (≥ 6 letras) e parecido (Damerau-Levenshtein pequeno em relação ao tamanho). |
| `data_uma_palavra` | Data igual ou “próxima” (um caractere de diferença na data, ou mesmo dia/mês com ano ± 1); no máximo uma palavra do nome diferente (espaço colado conta); primeiro nome da pessoa **fora** do top 10; em nome de três palavras, só o do meio trocado não vale. |
| `nome_cep` | Nome completo igual, CEP igual, primeiro nome fora do top 10. |
| `tokens_cep` | ≥ 80% das palavras do nome em comum, CEP igual, primeiro nome fora do top 10. |

Sem nenhuma dessas provas, o par pode até estar na fila, mas **não sobe na escada** abaixo de 0,99 (`sem_corroborador`).

### 5. Escada por fatia de nota

Os elegíveis com prova (ou nota ≥ 0,99) são vistos do maior para o menor, em fatias de 0,025.

Em **todo** degrau:

- a pessoa do Censo ainda não tem CPF;
- o CPF ainda não tem 3 pessoas;
- se aceitar o grupo daquele degrau faria o CPF passar de 3, o grupo inteiro daquele degrau fica de fora.

**5.1 Nota ≥ 0,99 (`score`).**  
A nota basta. Sem prova extra. Sem trava de candidato único. Se a mesma pessoa tiver vários CPF nessa faixa, fica o de maior nota; empate desempata por CEP igual e mãe “combinando” no sentido largo (igual / prefixo / Jaro-Winkler ≥ 0,75).

**5.2 De 0,975 até 0,80.**  
Exige prova (passo 4). Sem trava de candidato único. Mesma pessoa → maior nota; CPF → até 3.

**5.3 De 0,775 até 0,05.**  
Exige prova (passo 4) **e** trava de candidato único **dentro da fatia**: a pessoa só pode ter um CPF candidato naquela fatia e esse CPF só pode ter uma pessoa. Se houver dois, nenhum entra — **salvo** se `libera_11` estiver ligado:

| Libera a trava 1:1 quando | Nota |
|---|---|
| Jaro-Winkler da mãe **> 0,90** | ≥ 0,50 |
| Mãe contida (≥ 2) **e** datas iguais | ≥ 0,50 |
| Ramo M6 (data nula) | ≥ 0,35 |
| Ramo M7 (baixa nota) | > 0,05 e < 0,50 |

### 6. O que fica registrado

| Campo | Conteúdo |
|---|---|
| `degrau` | Piso da fatia em que a ficha foi aceita |
| `regra` | `score` (só no ≥ 0,99) ou o código da prova (`mae`, `logradouro`, …) |

---

## O que a escada não pega no limite de cima

O grosso sem CPF **não** está na nota alta: cerca de **1,64 milhão** (83% dos sem CPF) tem melhor par abaixo de 0,25 ou nem vira candidato no blocking. Isso é recall do pareamento.

Com melhor par **≥ 0,75** e ainda sem CPF (~204 mil), a decomposição é:

| Motivo | N | Leitura |
|---|---:|---|
| Sem corroborador | ~174 mil | Nota boa (nome/data do modelo), porta ok, mas **nenhuma prova do passo 4** — em geral mãe vazia ou que não fecha M1–M7, sem rua/CEP útil. |
| Veto de mãe ou primeiro nome | ~27 mil | Primeiro nome longe, ou mães que não passam no passo 3. |
| Outro na escada | ~3 mil | Quase sempre trava 1:1 sem `libera_11`. |

Esse é o **teto da atribuição**: o modelo já apostou em nome e data; a escada pede um segundo sinal e ele não aparece. Afrouxar a prova ou a trava 1:1 nessa faixa sobe cobertura e muda o tipo de erro (homônimo sem âncora). Por isso a regra para aqui e deixa o resto para lista ouro, revisão ou um modelo que use a mãe na nota.
