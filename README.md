# Analisador de Testes A/B de Cashback — Méliuz

Solução reutilizável que recebe os dados de um teste A/B de cashback e devolve,
num único comando, uma **análise completa**, um **relatório apresentável para o
gestor** e o **registro do teste numa planilha de acompanhamento**.

> Pergunta central que a solução responde: *"Dado este teste A/B, qual variante
> de cashback devemos escalar para 100% do tráfego?"*

## O problema

O time de Growth do Méliuz roda dezenas de testes A/B de cashback por mês. Hoje,
analisar cada teste leva de 2 a 4 horas e depende de quem está olhando — o que
gera inconsistência e gargalo. Esta solução automatiza a análise: qualquer
pessoa do time roda o mesmo comando para qualquer teste novo e recebe uma
decisão acionável, consistente e reproduzível.

## A decisão: qual métrica vence

A variante vencedora é escolhida pelo **lucro líquido = comissão − cashback** —
a receita que o Méliuz recebe do parceiro menos o custo do incentivo devolvido
ao usuário. É o que de fato importa ao decidir qual nível de cashback escalar.

A diferença entre a melhor variante e a segunda colocada é submetida a um
**teste t pareado por data** (com Wilcoxon como reforço não-paramétrico),
aproveitando que as variantes rodam em paralelo nos mesmos dias. A solução
classifica a confiança em **Alta**, **Moderada** ou **Inconclusivo** — e, quando
inconclusivo, recomenda estender o teste em vez de escalar.

## Arquitetura

A solução separa duas camadas, o que garante reúso e consistência:

- **Núcleo determinístico (Python):** toda a matemática — parsing, limpeza,
  métricas, estatística e regra de decisão — vive em código fixo e testável.
  Nenhum modelo de IA faz conta com dado financeiro, então o mesmo dataset
  sempre produz o mesmo resultado.
- **Camada de linguagem natural (`CLAUDE.md` + CLI):** permite acionar tudo por
  uma ferramenta de IA (Claude Code, Cursor, etc.) ou por um comando único. A IA
  orquestra e narra; o núcleo decide.

O mesmo código processa os 3 datasets (e qualquer outro no mesmo formato) sem
alteração — basta apontar o arquivo. O número de variantes (2, 3 ou mais) é
detectado automaticamente.

## Estrutura do repositório

```
meliuz-ab-analyzer/
├── analise.py            # CLI: ponto de entrada que orquestra todo o fluxo
├── CLAUDE.md             # instruções para acionar a solução por linguagem natural
├── requirements.txt      # dependências
├── pytest.ini            # configuração dos testes
├── src/
│   ├── ingestao.py       # leitura + limpeza robusta dos dados
│   ├── analise_engine.py # métricas, estatística e decisão
│   ├── validacao.py      # checagens de validade do teste (SRM, amostra, outliers)
│   ├── recomendacao.py   # sugestão do próximo teste (elasticidade do cashback)
│   ├── relatorio.py      # geração do relatório HTML do gestor
│   └── tracker.py        # registro no CSV e no Google Sheets
├── tests/                # suíte de testes automatizados (pytest)
├── data/                 # os datasets dos testes
├── relatorios/           # relatórios HTML gerados
└── tracker.csv           # planilha de acompanhamento (todos os testes)
```

## Como rodar

### Pré-requisitos

Python 3.10+ e Git.

### Instalação

```bash
# crie e ative um ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1

# instale as dependências
pip install -r requirements.txt
```

### Uso

Um comando faz o fluxo completo (análise + relatório + registro no CSV):

```bash
python analise.py data/dataset_01_parceiroA.csv
```

Troque o arquivo para analisar qualquer outro teste — o mesmo comando vale para
Parceiros A, B, C ou novos datasets:

```bash
python analise.py data/dataset_02_parceiroB.csv
python analise.py data/dataset_03_parceiroC.csv
```

Cada execução gera um relatório em `relatorios/` e registra (ou atualiza) a
linha do teste em `tracker.csv`.

### Testes

A solução tem uma suíte de testes automatizados (parser de moeda, limpeza,
métricas, decisão, validade do teste, recomendação e tracker). Para rodar:

```bash
pytest
```

### Exportar em PDF

Para gerar também o relatório em PDF (além do HTML), acrescente `--pdf`:

```bash
python analise.py data/dataset_01_parceiroA.csv --pdf
```

A conversão usa o primeiro backend disponível, em ordem de fidelidade:
Playwright (Chromium), wkhtmltopdf (via `pdfkit`) ou WeasyPrint. O mais simples
é `pip install pdfkit` mais o binário `wkhtmltopdf` (wkhtmltopdf.org; no macOS,
`brew install wkhtmltopdf`). Sem nenhum backend, o HTML continua sendo gerado —
basta abri-lo no navegador e usar Imprimir → Salvar como PDF.

## Google Sheets (opcional — diferencial)

Para registrar os testes direto numa planilha do Google Sheets, acrescente a
credencial e o ID da planilha:

```bash
python analise.py data/dataset_01_parceiroA.csv \
    --credenciais credenciais.json --planilha ID_DA_PLANILHA
```

Configuração da credencial (uma vez):

1. No **Google Cloud Console**, crie um projeto e ative as APIs **Google Sheets**
   e **Google Drive**.
2. Crie uma **conta de serviço** e gere uma chave **JSON**; salve como
   `credenciais.json` na raiz do projeto (o `.gitignore` já impede de versioná-la).
3. Crie a planilha no Google Sheets e copie o **ID** da URL (o trecho entre
   `/d/` e `/edit`).
4. Compartilhe a planilha com o e-mail `client_email` da conta de serviço, como
   **Editor**.
5. Para o link público de leitura, defina o compartilhamento como
   *"Qualquer pessoa com o link → Leitor"*.

## Saídas

- **Relatório do gestor** (`relatorios/*.html`): arquivo HTML autocontido com a
  decisão em destaque, o impacto anualizado projetado, a tabela de métricas por
  variante, três gráficos (lucro líquido, volume e evolução temporal), as
  checagens de validade do teste, a base estatística com intervalo de confiança
  e a sugestão do próximo teste. Abre em qualquer navegador e pode ser exportado
  como PDF.
- **Planilha de acompanhamento** (`tracker.csv` e/ou Google Sheets): uma linha
  por teste, com nome, descrição, período, variantes, métrica de decisão,
  resultado, decisão, confiança e data da análise.

## Resultados dos testes analisados

| Parceiro | Período | Decisão | Confiança | Observação |
|---|---|---|---|---|
| A | jan–abr/2011 | Escalar Grupo 1 (cashback 4,2%) | Alta | Vence em lucro, mas o Grupo 3 gera mais volume — trade-off sinalizado |
| B | mai–jun/2011 | Escalar Grupo 1 (cashback 4%) | Alta | Domina todas as métricas; caso mais limpo |
| C | jul–ago/2011 | Escalar Grupo 1 (cashback 5%) | Alta | Grupo 2 (cashback 7%) fica em ponto de equilíbrio (lucro zero) |

**Leitura de negócio:** nos três testes, o menor nível de cashback gerou o maior
lucro líquido, com alta confiança estatística. Aumentar o cashback não trouxe
volume suficiente para compensar a margem cedida ao usuário.

## Planilha de acompanhamento (online)

🔗 **Link (leitura pública):** https://docs.google.com/spreadsheets/d/1xP9FXQZhDMMyS85lnqtbKOKIDGyI5ptHPEHw0OQq3ok/edit?usp=sharing

## Notas técnicas

- **Robustez a dados ruins:** a ingestão converte valores em R$ no formato
  brasileiro (`R$ 10.273`) e descarta linhas com datas inválidas, valores
  negativos, campos vazios ou duplicatas, reportando o que foi removido.
- **Reprodutibilidade:** o núcleo é determinístico — mesma entrada, mesma saída.
- **Stack:** pandas, scipy, matplotlib, Jinja2, gspread, google-auth.