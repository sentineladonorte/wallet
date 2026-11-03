# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Plano e pendências:** veja `docs/ROADMAP.md` antes de começar e atualize-o ao terminar.

## Visão geral

Carteira de investimentos para ativos brasileiros (ações, FIIs e renda fixa): backend Django + frontend Next.js, atrás de um Nginx com HTTPS, orquestrados por Docker Compose.

## Comandos

### Ambiente

```bash
# Certificado autoassinado, necessário uma vez (certs/ fica fora do git)
mkdir -p certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout certs/localhost.key -out certs/localhost.crt -subj "/CN=localhost"

docker-compose up --build     # aplicação em https://localhost (nesta máquina: DOCKER_API_VERSION=1.44 docker-compose ...)
```

Arquivos não versionados que precisam existir:

- `backend/.env`, lido por `python-decouple`: `ENGINE`, `DB_NAME`, `USER_POSTGRES`, `PASSWORD`, `HOST`, `PORT` (e `ALPHAVANTAGE_KEY` para o comando `alphavantage`).
- `frontend/.env.development`: `NEXT_PUBLIC_BACKEND_URL=https://localhost/api`.

As variáveis `POSTGRES_*` do serviço `postgres` estão vazias no `docker-compose.yml` e são herdadas do ambiente em que o Compose roda.

Use o app sempre por `https://localhost`, não por `:3000`: o cookie `currentUser` é `Secure`, e o login depende dele.

### Backend (dentro de `backend/`, ou com `docker-compose exec backend ...`)

```bash
python manage.py migrate
python manage.py makemigrations
python manage.py test                          # todos os testes
python manage.py test wallet                   # um app
python manage.py test wallet.tests.MinhaClasse.test_metodo   # um único teste
flake8                                         # na raiz do repo; .flake8 define max-line-length = 120
```

`wallet` e `app` têm testes, sem acesso à rede; os de `user` ainda são stub. O `flake8` não está em `requirements.txt`. A imagem Docker usa Python 3.9.

### Frontend (dentro de `frontend/`)

```bash
npm run dev
npm run build
npm run lint
```

Não há framework de testes configurado no frontend.

### Testes de navegador

```bash
e2e/run.sh                     # todos
e2e/run.sh -k proventos        # argumentos vão para o pytest
```

Rodam em Docker, num ambiente próprio (`e2e/docker-compose.yml`): banco em memória, rede isolada, sem portas no host, sem acesso à B3 nem ao Investidor10. As planilhas são geradas por `e2e/tests/reports.py` com dados fictícios; nunca use relatórios reais nos testes. Capturas das falhas ficam em `e2e/artifacts/`. Toda tela nova precisa de teste aqui, e todo teste falha se houver erro no console.

### Comandos de dados (`manage.py`)

| Comando | Função |
| --- | --- |
| `populate_asset` | Cadastra `Asset` a partir das APIs públicas da B3 |
| `update_market_data [--year AAAA ...]` | Baixa cotações da B3, preenche categorias e gera o histórico |
| `market_scheduler` | Repete a atualização em intervalos; é o comando do serviço `market-updater` |
| `alphavantage TICKER...` | Importa cotações pela Alpha Vantage |
| `consolidate [--tickers ...]` | Recalcula do zero o histórico de renda variável de todos os usuários |
| `consolidate_fixed_income [--tickers ...]` | Recalcula o histórico de renda fixa |
| `daily_consolidation` | Gera o histórico das datas novas de todos os usuários |
| `reset_portfolio --username X [--yes]` | Apaga boletas e histórico do usuário; sem `--yes`, só mostra o que seria apagado |
| `backup` / `restore ARQUIVO` | `pg_dump`/`pg_restore` em `backend/backups/` |

## Arquitetura

### Roteamento

O Nginx envia `/api` ao Django (`backend:8000`) e o restante ao Next.js (`frontend:3000`). Todas as rotas estão em `backend/config/urls.py`, sem `urls.py` por app.

### Apps Django

- `app`: dados de mercado, globais e sem vínculo com usuário (`Asset`, `AssetPrice`).
- `wallet`: dados por usuário (`Order`, `AssetConsolidatedValue`) e os cálculos de posição.
- `user`: apenas views de autenticação sobre o `User` padrão do Django, sem models próprios.

Não há FK entre `wallet` e `app`: a ligação é por string, com `Order.name` igual a `Asset.ticker`/`AssetPrice.ticker`.

### Fluxo de dados

1. A importação grava `AssetPrice`, e o usuário registra `Order`s pela API.
2. Os comandos de consolidação geram uma linha diária por ativo em `AssetConsolidatedValue` (único por `user, name, date`).
3. `position_history` lê apenas essa tabela. **Nada é consolidado ao criar ou editar uma ordem**, então os gráficos históricos só mudam depois de rodar os comandos.

### Renda fixa é um caso à parte

- Ordens `RF` não têm linha em `Asset` nem em `AssetPrice`; o valor é projetado a partir de `interest_rate` por `consolidate_fixed_income`.
- Em `position`, o preço de `RF` vem de `AssetConsolidatedValue`; o dos demais tipos vem de `AssetPrice`. Sem essas linhas, o ativo aparece sem preço e fica fora dos totais.
- Ao criar uma ordem `RF`, a API grava `name` como `"<nome> <vencimento>"`. O frontend envia esse nome codificado na URL.

### Movimentação da B3: boletas derivadas

O extrato de movimentação (`wallet/movements.py`) e o relatório de posição entram pelo mesmo modal e pelas mesmas rotas; o tipo é detectado pela aba do arquivo. Linhas ficam em `Movement`, e cada relatório vira uma foto em `PositionSnapshot`.

- **Boletas com `source` `movement` são derivadas:** `rebuild_orders` as recria do zero a cada importação, a partir de `Movement` e da foto mais recente, e a API recusa editá-las. Boletas `manual` nunca são tocadas, exceto se o usuário escolher na prévia.
- **Duplicação:** `Movement.fingerprint` usa data, tipo, ativo, corretora, quantidade, preço e valor, sem o nome do produto, que muda com o tempo, e `occurrence` numera operações idênticas legítimas. Dentro de um arquivo, a mesma linha com textos de produto diferentes é duplicata da própria B3 e conta uma vez.
- **Semântica validada contra a posição real:** `Atualização` igual ao saldo não faz nada e, diferente, soma; `Grupamento` informa o saldo final; `Resgate` a crédito é dinheiro de ativo extinto, não venda; saída com valor zero não é prejuízo. Altere essas regras comparando de novo com um relatório de posição.
- **`Order.kind`** define o efeito em `RunningPosition`: `event` e `transfer` mudam só a quantidade; `trade` entra no custo e no lucro realizado; `reconcile` e `succession` mexem no custo sem gerar lucro.
- **A foto de posição manda na quantidade:** o que o extrato não explica é acertado na data dela. Faltando quantidade, entra custo estimado; sobrando em ativo fora da posição, ele é encerrado na última atividade conhecida.
- `rebuild_history` refaz todo o histórico em segundo plano depois de importar, com fila por usuário. Antes da foto, a renda fixa é uma estimativa: cresce a taxa constante do custo até o valor oficial.

### Importação da posição da B3

`wallet/b3_import.py` lê o .xlsx exportado pela B3 e é exposto em `POST /api/orders/import/preview` e `/confirm`, ambos pelo mesmo `build_plan`.

- O arquivo é uma **foto da posição**, sem data nem preço de compra. A importação reconcilia a foto com as boletas por `(user, name, broker)` e cria apenas a diferença de quantidade, então reenviar o mesmo arquivo não cria boletas.
- Custos e datas são estimados e marcados em `Order.cost_estimated`, que é zerado quando `price` ou `date` são editados.
- Boletas importadas de renda fixa não têm `interest_rate`. `consolidate_fixed_income` as ignora, e o valor delas vem do `AssetConsolidatedValue` gravado na importação.
- Posição ausente do arquivo nunca é zerada automaticamente; o usuário escolhe na prévia.
- Um ativo com boletas existentes mantém a classe delas, mesmo que o arquivo classifique diferente.
- A importação grava também em `Asset` e `AssetPrice`, que são **globais** e afetam todos os usuários.
- Sem movimentações, o relatório cria boletas `position` com custo estimado; com elas, só guarda a foto e recalcula.

### Frontend

- Só dark mode. As cores ficam em `tailwind.config.ts` (`canvas`, `surface`, `raised`, `line`, `ink`, `soft`, `muted`, `accent`, `gain`, `loss`, `warn`); use esses nomes, não hex nem cores padrão do Tailwind. Alterar o arquivo exige reiniciar o contêiner `frontend`.
- `components/ui` tem os blocos de interface, e `useToast` substitui `alert()`. `lib/useApi.ts` faz as buscas, com estados de carregamento e erro.
- Os tipos da API estão em `src/types.ts`; `position` e `orders` retornam objetos nomeados.
- A distribuição é calculada no cliente em `lib/allocation.ts`, a partir da lista de posições: cada clique numa fatia vira um filtro, e a hierarquia é classe → categoria → subcategoria → ativo. A tabela e os indicadores do dashboard usam a mesma seleção.
- As cores das classes são fixas em `lib/assets.ts`. A paleta foi validada para o fundo escuro, e a ordem dela importa; não reordene nem gere cores novas: acima de 7 grupos, o restante vira "Outros".
- `investidor10Url` em `lib/assets.ts` monta os links por classe. Renda fixa não tem página por título no Investidor10.
- Valores da carteira são formatados com `useFormat` de `lib/privacy.tsx`, que respeita o botão de ocultar. Use `lib/format` direto só para o que não revela quanto o usuário tem. O percentual de uso do limite do FGC revela, porque o limite é público.
- Highcharts só roda no navegador; importe `charts/stock` com `next/dynamic` e `ssr: false`.

### Metas de alocação

`AllocationTarget` guarda dois níveis: a classe na carteira (`category` vazia) e a categoria dentro da classe, com percentual sobre o total da classe. `PUT /api/targets` substitui um nível inteiro de uma vez e recusa soma acima de 100%; abaixo disso é permitido. A comparação com a posição é feita no cliente, em `lib/targets.ts`. A categoria é comparada pelo texto exato de `Asset.category`, ou do indexador na renda fixa.

A calculadora de aporte (`lib/contribution.ts`) usa as metas salvas, calcula a meta sobre o total depois do aporte e divide o valor na proporção do que falta a cada grupo, primeiro entre classes e depois dentro de cada classe. Ela trabalha em centavos para a soma fechar exatamente no aporte.

### Cotações, categorias e histórico

`wallet/market_update.py` coordena três etapas, chamadas pelo serviço `market-updater`, pelo comando `update_market_data` e por `POST /api/market-data`. Um lock do Postgres impede duas execuções ao mesmo tempo, e cada uma fica registrada em `MarketDataUpdate`.

- `app/market_data.py` baixa o COTAHIST da B3. O arquivo só existe depois do pregão, e o 404 é tratado como feriado ou arquivo ainda não publicado. Os preços não têm ajuste de desdobramento.
- `app/categories.py` só preenche o que está vazio. Reaproveita nomes já usados, porque as metas comparam o texto exato: ação e BDR copiam outro papel da mesma empresa; se não houver, ação usa o setor da B3 e BDR a indústria do Investidor10; FII usa o segmento do Investidor10; ETF não tem fonte externa e vem do "Tipo" do relatório da B3.
- `wallet/consolidation.py` gera `AssetConsolidatedValue` só para datas posteriores à última linha do usuário, limitado a 30 dias, e nunca sobrescreve o valor gravado por uma importação. Renda fixa sem taxa mantém o último valor.

### Renda fixa projetada, vencimentos e rentabilidade

- `wallet/fixed_income.py` calcula a taxa implícita de cada título, do custo até o valor do relatório de posição, e projeta o valor no histórico e no vencimento. Título recente usa a média da carteira, e taxa em boleta manual tem prioridade. O valor só é oficial na data do relatório; a API sinaliza isso em `value_estimated`.
- Título comprado depois do último relatório aparece sem vencimento, porque o extrato não informa essa data.
- `lib/cashflow.ts` monta o calendário de `/maturities` a partir das posições e dos proventos. A simulação reutiliza a calculadora de aporte, retirando os títulos que vencem.
- `wallet/performance.py` calcula o retorno ponderado pelo tempo a partir de `AssetConsolidatedValue` e das boletas. Compras e vendas são fluxos, não ganho; proventos são ganho; eventos e encerramentos deixam o ativo neutro no dia; variação acima de 40% sem operação é tratada como desdobramento na cotação. O CDI vem do Banco Central (`app/indices.py`) e o Ibovespa é medido pelo `BOVA11`.
- O histórico de renda fixa antes de um relatório é estimado, portanto a rentabilidade antiga também é.

### Autenticação

- A autenticação real é a sessão do Django. O `api.ts` usa `withCredentials: true`.
- O cookie `currentUser` só é verificado por `frontend/src/middleware.ts`, para redirecionar a `/auth`; o valor não é validado.
- `api.ts` trata 401 encerrando a sessão e voltando para `/auth`; sem remover o cookie, o middleware devolveria o usuário à página atual.
- As views em `wallet` são funções Django comuns que verificam `request.user.is_authenticated` manualmente; só `user` usa decorators do DRF.

## Armadilhas

- Os relatórios da B3 têm dados reais de conta e posição. `posicao-*.xlsx` e `movimentacao-*.xlsx` estão no `.gitignore`, e os testes geram planilhas sintéticas.
- `backend/dev.py` e `backend/wallet/dev.py` são scripts avulsos de shell que **alteram dados de forma irreversível** (ajuste de desdobramento do BCFF11). Não os execute nem os importe.
- O banco de desenvolvimento não é descartável, e `manage.py test` não funciona nele. Rode os testes como descrito em `docs/ROADMAP.md`.
- `frontend/package.json` usa `latest` em `next`, `react` e outros, então um build novo pode trazer versões maiores.

## Convenções

Commits usam prefixos: `feat`, `fix`, `chore`, `docs`, `style`, `refactor`, `perf`, `test`, `ci`, `build`, `revert`, `wip`. Mensagens ao usuário nas respostas da API são em português.
