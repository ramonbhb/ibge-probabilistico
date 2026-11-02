# Treino Splink — comparações, versões e por que cada uma

Há duas especificações de comparação e quatro treinos. O que muda entre eles é o que entra no score e em qual base o *m* e o *u* são estimados. A especificação que ficou para reportar na UF 21 é a do notebook `02c`.

## As quatro versões

| Notebook | JSON | Base | Comparisons no score |
|---|---|---|---|
| `02_treinar_splink` | `splink_model.json` | `censo_limpo` × `cpf_limpo` (UF 21, cerca de 6,59 milhões × 8,45 milhões), fonética deste projeto | nome, data, UF |
| `02c_treinar_splink_mae_endereco` | `splink_model_mae_endereco.json` | a mesma base do 02 | nome, data, mãe, endereço |
| `02e_treinar_splink_csv_luis` | `splink_model_mae_endereco_luis.json` | CSVs do notebook 07, bases V3 do Luis, já sem a lista ouro de avaliação | iguais ao 02c |
| `spark/03_treinar_luis_nacional` | o mesmo nome do 02e | os mesmos CSVs, em escala nacional, no Spark | iguais ao 02c, SQL reescrito para Spark |

Os quatro são `link_only` (só Censo × CPF). O treino usa o conjunto inteiro. As 14 regras de `predict` ficam no notebook de aplicação e não entram no EM.

O `02` e o `02c` são modelos paralelos na mesma base. O `02e` e o Spark não redesenham a comparação: congelam a especificação do `02c` e trocam a população (e, no Spark, o motor).

## Como o treino está organizado

A sequência é a mesma nos quatro.

1. **Prior.** Regras determinísticas `cpf_norm` ou `nome_completo_phon` + `data_nascimento`, com `recall = 0,7`. São outra lista, distinta das 14 regras de predição. O 0,7 diz que essas duas regras pegam cerca de 70% dos matches verdadeiros, então o λ não é só a contagem desses pares sobre todos os pares possíveis.

2. **u.** Amostra aleatória de até 500 milhões de pares. Fica fixo depois (`fix_u_probabilities = True`). O EM só move o *m*.

3. **m pelo rótulo `cpf_norm`.** Mesmo CPF é match. `NULL` não casa com `NULL`, então Censo sem carimbo da coorte não fabrica par. Esse passo vê sobretudo os níveis exatos: na ouro o nome e a data costumam bater por inteiro. Os níveis fuzzy (prefixo, DL, JW) em geral não aparecem aqui e ficam para o EM. O CPF não entra no score nem no blocking de predição. Se entrasse, a ouro seria sempre candidata e a avaliação no `03b` / `03c` circularia.

4. **EM**, até 10 milhões de pares por sessão. Cada sessão bloqueia numa chave que deixa de fora a comparison que se quer estimar. O Splink não estima *m* de uma coluna que está na chave.

   - **Nome:** bloqueio em `data_nascimento` + `sexo`. A data sai da sessão. Entre gente com a mesma data e o mesmo sexo, o que separa match de não-match é o nome, inclusive os níveis fuzzy que o rótulo de CPF não viu.
   - **Data:** bloqueio em `primeiro_nome_phon` + `ultimo_nome_phon`. Primeiro e último não desligam `nome_completo_phon` (é outra coluna). Por isso a chave leva a tautologia `nome_completo_phon IS NULL OR IS NOT NULL`, sempre verdadeira. O Splink trata o nome completo como parte do bloqueio e tira essa comparison da sessão. Sem isso, o *m* do nome da sessão anterior seria reescrito num bloco em que os nomes já estão muito correlacionados.
   - **Diagnóstico:** o mesmo bloqueio da data mais `sexo`. O settings é copiado antes e restaurado depois. Esse *m* não vai para o JSON. Serve para ver o quanto o *m* da data muda quando o bloco também exige sexo.
   - **Só a partir do `02c`:** mãe em `nome_completo_phon` + `data_nascimento`; endereço em `primeiro` + `último` + `data_nascimento`. A mãe e o endereço ficam fora da chave, então são eles que o EM estima.

Sexo entra no bloqueio do EM e nas regras de predição. Não é comparison: com duas categorias, acordo é frequente demais para valer peso próprio.

## Especificação do 02: o que entra no score e por quê

Três comparisons. Mãe, CEP, sexo e CPF ficam de fora do score. Primeiro, meio, último e `primeiro_ultimo` ficam nas tabelas e na blocagem.

### Nome — só `nome_completo_phon`

Primeiro e último no score fariam `SILVA` exato mais um primeiro parecido somarem ponto com o miolo diferente (`HELENA FERREIRA SILVA` / `HELLENA LIMA SILVA`). Esse par cai no ELSE do completo. A frequência do exato é a do próprio nome completo: nome comum desce um pouco, nome raro sobe, e o nível só dispara quando o completo é igual.

A cascata é a primeira condição que casa:

| Nível | O que pega |
|---|---|
| Nulo | um dos lados sem nome |
| Exato + frequência do termo | nome fonético idêntico |
| Prefixo, mínimo de 2 tokens, comprimentos diferentes | sobrenome a menos no fim (`MARIA JOAQUINA SANTOS PEREIRA` / `MARIA JOAQUINA SANTOS`) |
| Damerau-Levenshtein ≤ 1 na string | um caractere ou uma transposição no completo |
| Um token com DL ≤ 2, último igual, pelo menos 3 tokens | `ALICE` / `ALICIA`, `CLEONITO` / `CLEONILDO` |
| Até dois tokens, cada um com DL ≤ 2 | `WEVERDOR MORAIS SILVA` / `WEVERTON MORAES SILVA`, `SOUSA` / `SOUZA` |
| Um token a mais, nome curto com pelo menos 3 tokens | token no meio (`NEUZIN PAULINO GUAJAJARA` / `NEUZIN PAULINO PINTO GUAJAJARA`) |
| Mesmos tokens, ordem diferente, pelo menos 3 | `ELAINE FERREIRA COSTA MATOS` / `ELAINE COSTA FERREIRA MATOS` |
| Último igual e Jaro-Winkler ≥ 0,95, depois ≥ 0,92 | resto parecido, com sobrenome coincidindo |
| ELSE | o resto, inclusive `RODRIGUES` vs `PEREIRA` mesmo com JW alto na string |

O JW do completo só roda se o último token coincidir. Sem isso, sobrenomes diferentes e frequentes ganhariam peso. `HELENA FERREIRA SILVA` / `HELLENA LIMA SILVA` não entra no nível de dois tokens: o miolo passa de 2 caracteres.

### Data — uma comparison só, com a idade no fim

Não usamos o `DateOfBirthComparison` do Splink: ele mede distância em dias e meses e não separa os erros de digitação que importam aqui. A cascata:

- nulo só quando faltam data, idade e mês/dia;
- data ISO exata, com frequência do termo;
- mês e dia trocados, ano igual (`2011-11-01` / `2011-01-11`);
- mesmo ano e mês, dia diferente (`10` / `08`);
- mesmo ano e dia, mês diferente (`11` / `09`);
- mesmo mês e dia, ano ± 1 (`2018` / `2017`, `1999` / `2000`);
- Damerau ≤ 1 e ≤ 2 na string ISO, para o que sobrou perto como texto (transposição `01` ↔ `10`, dia `08` vs `10` quando não caiu num nível semântico);
- as duas datas presentes e nenhuma das regras acima (`2007-01-28` / `2017-03-28` cai aqui, não em ano ± 1);
- idade exata, depois idade ± 1;
- ELSE.

A idade só é alcançada quando a data não existe nos dois lados. Com as duas datas preenchidas, o par para num nível de data e a idade não soma. No Censo, se a data validada existe, a idade é anulada no notebook `00b` pelo mesmo motivo.

### UF — match exato com frequência do termo

No recorte de uma UF só isso quase não discrimina: os dois lados são 21, o nível "UF diferente" não aparece no treino e o *m* desse nível fica sem estimativa. É o motivo de a especificação seguinte tirar a UF.

### Mãe fora do score nesta versão

No recorte do Maranhão o Censo tem mãe em cerca de 34% das linhas, e um match exato dava peso demais para um campo faltante e, no Censo, inferido por domicílio. `nome_mae_phon` fica na 14ª regra de predição (com município, sexo e idade ± 1) e no resgate da atribuição antiga, não na nota.

## Especificação do 02c: o que mudou e por quê

Nome e data são copiados do `02`. Sai a UF. Entram mãe e endereço. O relatório da UF 21 compara as duas: o recall na ouro sobe de 86,5% para 91,7% e o falso positivo da associação cai de 1,11% para 0,63%. Essa é a versão marcada para reportar.

### Mãe — `nome_mae_phon`, mais curta que a comparison da pessoa

A mãe do Censo é inferida no domicílio; a do CPF é `NOM_MAE`. O erro típico é token a mais ou a menos em qualquer posição, não só no fim, e a grafia é mais solta. Por isso não se repetiu a cascata de Damerau-Levenshtein por token:

| Nível | Por quê |
|---|---|
| Nulo | um lado sem mãe |
| Exato + frequência do termo | mesma fonética |
| Contida, mínimo de 2 tokens, comprimentos diferentes | os tokens do nome mais curto são subconjunto do mais longo, em qualquer posição |
| Mesmos tokens, ordem diferente, pelo menos 3 | ordem trocada |
| JW ≥ 0,92, depois ≥ 0,85 | parecido como string; limiar mais frouxo que o do nome da pessoa (0,95 / 0,92) |
| ELSE | o resto |

Aqui o JW não exige último token igual. No nome da pessoa isso evitava dar ponto a sobrenomes diferentes. Na mãe, sobrenome trocado ou faltando é parte do erro que o nível fuzzy deve absorver, com peso menor que o exato.

O EM da mãe bloqueia em nome completo + data, para o nome da mãe variar entre pares que já parecem a mesma pessoa.

### Endereço — uma comparison composta, não três

Logradouro, CEP e município medem o mesmo fato. Comparisons separadas multiplicariam o fator de Bayes. A cascata vai do acordo mais forte ao mais fraco:

- nulo só quando logradouro, CEP e município faltam ao mesmo tempo em pelo menos um lado; se qualquer peça existe, o par é comparável;
- logradouro e CEP exatos;
- logradouro e município exatos (CEP ausente ou diferente, mesma rua na cidade);
- logradouro com JW ≥ 0,90 e CEP exato (erro de grafia na rua, mesmo CEP);
- só CEP exato;
- ELSE.

O EM do endereço bloqueia em primeiro nome + último nome + data, com o endereço fora da chave.

## Por que o 02e e o Spark existem

A especificação não muda. Muda de onde saem o *m* e o *u*.

O `02c` treina na base limpa deste projeto, com a fonética daqui, e o `cpf_norm` do Censo vem do carimbo da coorte. A lista ouro de avaliação ainda está nessa base.

O `02e` treina nos CSVs do notebook `07`: fonética do Luis (`nome_fonetico` vira `nome_completo_phon`, `nome_fonetico_mae` vira `nome_mae_phon`), universo de aplicação, Censo e CPF já sem a lista ouro de avaliação (`regras1a7`). A coluna `cpf` do CSV vira `cpf_norm` e continua só no prior e no *m*. O JSON é outro arquivo, para não sobrescrever o `02c`. A escolha é estimar os parâmetros na mesma featurização e no mesmo universo que vão ser pontuados, com a ouro de avaliação fora do EM.

O notebook `spark/03` repete essa especificação na base nacional. O SQL deixa de ser DuckDB (`string_split`, `list_slice`, `jaro_winkler_similarity`) e passa a ser Spark (`split`, `slice`, `element_at`, `jaro_winkler`). Limiares, ordem dos níveis e sessões de EM são os mesmos. A UF continua de fora: município e CEP já estão no endereço, e a especificação validada na UF 21 foi a que subiu para o nacional.
