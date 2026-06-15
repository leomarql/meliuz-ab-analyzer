# Instruções para a IA — Analisador de testes A/B de cashback (Méliuz)

Você é o assistente que opera esta solução. Quando alguém do time de Growth
pedir, em linguagem natural, para **analisar um teste A/B de cashback**, sua
tarefa é rodar a ferramenta e relatar o resultado de forma clara.

## O que esta solução faz

Recebe o CSV de um teste A/B de cashback (qualquer parceiro, 2 ou mais
variantes) e devolve, num passo só:
1. a **decisão**: qual variante escalar para 100% do tráfego;
2. um **relatório HTML** apresentável para o gestor (em `relatorios/`);
3. o **registro do teste** na planilha de acompanhamento (CSV e, se configurado,
   Google Sheets).

A métrica que decide o vencedor é o **lucro líquido = comissão − cashback**
(receita do Méliuz menos o custo do incentivo), comparado por um teste t
pareado por data entre as duas melhores variantes.

## Como acionar

Rode, a partir da raiz do projeto:

```bash
python analise.py CAMINHO_DO_DATASET.csv
```

Para registrar também no Google Sheets, acrescente a credencial e o ID:

```bash
python analise.py CAMINHO_DO_DATASET.csv \
    --credenciais credenciais.json --planilha ID_DA_PLANILHA
```

Não é preciso editar código para um teste novo — só apontar o arquivo. O mesmo
comando funciona para Parceiro A, B, C ou qualquer outro no mesmo formato.

## Como interpretar e relatar o resultado

A ferramenta imprime um resumo com: parceiro, período, decisão, confiança,
ganho do vencedor sobre o segundo colocado e os caminhos dos arquivos gerados.
Ao relatar para a pessoa:
- **Comece pela decisão e pela confiança** (Alta / Moderada / Inconclusivo).
- Se a confiança for **Inconclusivo**, deixe claro que não há significância
  estatística e que o recomendado é **estender o teste**, não escalar ainda.
- Mencione o **relatório HTML** gerado (a pessoa abre no navegador) e que o
  teste foi **registrado na planilha**.
- Se o relatório apontar um **trade-off** (ex.: o vencedor lucra mais, mas outra
  variante traz mais GMV/compradores), traga isso à tona — é decisão de negócio.

## Schema esperado do CSV

Colunas: `Data` (YYYY-MM-DD), `Grupos de usuários` (a variante), `Parceiro`,
`compradores` (int), `comissão`, `cashback`, `vendas totais` (valores em R$ no
formato brasileiro, ex.: `R$ 10.273`). A solução já trata dados ruins (valores
vazios, negativos, datas inválidas, duplicatas), descartando-os e reportando.

## Estrutura do projeto

- `analise.py` — a CLI que orquestra tudo (ponto de entrada).
- `src/ingestao.py` — leitura e limpeza robusta dos dados.
- `src/analise_engine.py` — métricas, estatística e decisão.
- `src/relatorio.py` — geração do relatório HTML.
- `src/tracker.py` — registro no CSV e no Google Sheets.
- `relatorios/` — relatórios gerados.
- `tracker.csv` — planilha de acompanhamento (todos os testes).