# Roadmap do Wallet

Documento vivo para continuar o trabalho em qualquer sessão, com qualquer pessoa ou IA.
**Ao retomar:** leia este arquivo e o `CLAUDE.md`, rode `git status` e continue pelo primeiro item `[ ]` de "Agora".
**Ao terminar um item:** marque `[x]` e registre decisões relevantes.

## Objetivo

Carteira pessoal de investimentos em dark mode: importar a posição da B3, entender a distribuição por classe, categoria e subcategoria, e abrir rapidamente a análise de cada ativo no Investidor10.

## Decisões já tomadas

- Os dados antigos do banco de desenvolvimento não precisam ser preservados como referência (decisão do dono do projeto em 02/11/2026). Mesmo assim, **não apague nada sem pedir**.
- O app é somente dark mode; não há tema claro.
- O relatório da B3 é uma foto da posição: a importação reconcilia a foto com as boletas e cria só a diferença.
- A tabela `Asset` é global: categorias editadas valem para todos os usuários.

## Feito na grande atualização (02/11/2026)

- [x] Backend: `position` e `orders` retornam objetos nomeados em vez de arrays posicionais
- [x] Backend: campos para as visões (emissor, corretoras, vencimento, indexador, rendimento)
- [x] Backend: edição de categoria e subcategoria de um ativo
- [x] Backend: comando para zerar a carteira de um usuário
- [x] Backend: corrigir `GET /api/order/<id>` (lê boleta de outro usuário e não serializa)
- [x] Frontend: tema escuro, layout e componentes base; trocar `alert()` por avisos
- [x] Frontend: gráfico de pizza com navegação (classe → categoria → subcategoria → ativo)
- [x] Frontend: links para o Investidor10
- [x] Frontend: refazer dashboard, boletas, ativos, detalhe do ativo, login e perfil
- [x] Verificar no navegador, em ambiente isolado, com capturas de tela

## Feito depois (02/11/2026)

- [x] Botão de ocultar valores (`lib/privacy.tsx`); novos valores da carteira devem usar `useFormat`
- [x] Tooltip da pizza acima do valor central
- [x] Emissores: recuperados das descrições (migração `0010`), e a importação completa os que faltam
- [x] Tela de emissores com uso do limite do FGC (`/issuers`)
- [x] Filtro por classe na tabela de posições
- [x] Metas de alocação por classe e por categoria dentro da classe (`/targets`), com quanto falta em reais e resumo no dashboard
- [x] Cotações automáticas pelo COTAHIST da B3, com histórico diário por usuário e botão de atualizar (`wallet/market_update.py`)
- [x] Categorias automáticas para ativos que não têm (`app/categories.py`)
- [x] Importação do extrato de movimentação da B3, sem duplicar linhas entre arquivos (`wallet/movements.py`)
- [x] Preço médio real, lucro realizado e histórico completo a partir do extrato
- [x] Página de proventos: dividendos, rendimentos, JCP e juros por mês e por ativo (`/income`)
- [x] Testes de navegador no repositório, em ambiente isolado (`e2e/run.sh`)
- [x] Rendimento diário estimado da renda fixa pela taxa implícita de cada título (`wallet/fixed_income.py`)
- [x] Calendário de vencimentos e caixa, com simulação de reinvestimento pelas metas (`/maturities`)
- [x] Rentabilidade ponderada pelo tempo contra CDI e Ibovespa (`wallet/performance.py`, `/performance`)
- [x] Gráfico de proventos agrupado por mês ou ano
- [x] Calculadora de aporte (`lib/contribution.ts`): divide o valor entre os grupos abaixo da meta, sem sugerir vendas

## Próximos passos

Sem ordem obrigatória.

- [ ] **Agrupar emissores por conglomerado:** bancos do mesmo grupo dividem o limite do FGC, e a tela mostra cada emissor separado
- [ ] Teto global do FGC (R$ 1 milhão por CPF a cada 4 anos) como indicador na tela de emissores
- [ ] Calculadora de aporte por ativo: sugerir tickers e quantidades, considerando preço e lote
- [ ] Categoria de ETF sem depender da importação: nenhuma fonte externa testada traz esse dado
- [ ] **Vencimento de títulos antigos:** o extrato não informa vencimento, então títulos encerrados sem baixa saem do histórico na última atividade conhecida, e o patrimônio antigo fica subestimado
- [ ] Desdobramento depois da última importação: sem o extrato atualizado, a posição fica distorcida até importar de novo
- [ ] Recalcular o histórico ao editar boletas manuais com data passada (importações já recalculam)
- [ ] **Imposto de Renda:** vendas por mês, isenção de ações, FIIs à parte, prejuízo a compensar e resumo anual
- [ ] IPCA como terceira referência de rentabilidade (série 433 do Banco Central)
- [ ] Metas por subcategoria (hoje são dois níveis: classe e categoria)
- [ ] Indexador CDI e tipos CRI, CRA e debênture na importação

## Dívida técnica conhecida

- [ ] `populate_asset` usa endpoints da B3 que respondem 405 em parte das etapas; revisar ou remover
- [ ] `consolidate` ainda recalcula a renda variável do zero, por caminho diferente de `wallet/consolidation.py`
- [ ] Segurança: `SECRET_KEY` no código, `DEBUG=True`, `CORS_ALLOW_ALL_ORIGINS` e views com `@csrf_exempt`
- [ ] Autenticação: o cookie `currentUser` não é `HttpOnly` nem validado pelo middleware do frontend
- [ ] Dependências `latest` em `frontend/package.json`; fixar versões
- [ ] Edição de categoria em `Asset` é global e qualquer usuário autenticado pode alterar; decidir se vira dado por usuário
- [ ] Dois pacotes de gráfico (Chart.js e Highcharts); avaliar manter só um
- [ ] `frontend/Dockerfile`: a etapa final roda `npm install --production` e remove `tailwindcss` e `typescript`; `next build` falha nessa imagem. Testar se um `docker-compose up --build` com volume novo ainda sobe em modo dev
- [ ] Não testados no navegador: sessão expirada (401), filtro por corretora com mais de uma corretora e clique no nível "Ativo" da pizza
- [ ] Remover `backend/dev.py` e `backend/wallet/dev.py`
- [ ] `AssetClassificationTests` está em `wallet/tests.py`, mas testa o app `app`; mover ao criar os testes de `app`
- [ ] Testes para `user`; a lógica do frontend só é coberta pelos testes de navegador
- [ ] `template1` do Postgres com divergência de collation impede `manage.py test` no banco de desenvolvimento

## Como começar do zero

Os dados antigos continuam no banco. Para descartar a carteira antiga de um usuário e importar de novo:

```bash
docker exec backend python manage.py reset_portfolio --username SEU_USUARIO         # só mostra o que seria apagado
docker exec backend python manage.py reset_portfolio --username SEU_USUARIO --yes   # apaga boletas e histórico desse usuário
```

## Cotações e histórico

O serviço `market-updater` do `docker-compose` roda `market_scheduler`, que atualiza a cada 3 horas. O botão "Atualizar cotações" do dashboard faz o mesmo na hora. Para preencher preços antigos, use um ano inteiro de cada vez:

```bash
docker exec backend python manage.py update_market_data --year 2024 2025
```

## Fluxo de importação recomendado

1. Importe o relatório de posição e o extrato de movimentação, em qualquer ordem. Sem o relatório, títulos de renda fixa não aparecem.
2. Depois, envie extratos menores quando quiser, inclusive com períodos repetidos: as linhas já importadas são ignoradas.
3. Envie um relatório de posição novo de tempos em tempos, para corrigir saldos e atualizar o valor da renda fixa.

## Como verificar

- **Testes do backend:** rodar contra um Postgres descartável, nunca o banco de desenvolvimento:
  ```bash
  docker run -d --rm --name wallet_test_pg --network wallet_default -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test -e POSTGRES_DB=test postgres:16
  docker exec -e HOST=wallet_test_pg -e PORT=5432 -e USER_POSTGRES=test -e PASSWORD=test -e DB_NAME=test backend python manage.py test wallet --noinput
  docker rm -f wallet_test_pg
  ```
  O shell é zsh: escreva as flags `-e` literalmente, sem guardá-las em variável.
- **Frontend:** `docker exec frontend npx tsc --noEmit` e `docker exec frontend npm run lint`.
- **Navegador:** `e2e/run.sh`, em ambiente isolado e com dados fictícios. Toda tela nova precisa de teste aqui.
- **Mudou `tailwind.config.ts`?** Reinicie o contêiner (`docker restart frontend`), senão as cores novas não são geradas.
- **Visual:** abra o app e olhe. Testes automáticos não pegaram botões invisíveis nem gráficos em branco; as capturas de tela pegaram.
- **`docker-compose`:** nesta máquina precisa de `DOCKER_API_VERSION=1.44`.

## Estado do trabalho

Tudo o que está marcado como feito neste arquivo já está em `main`. Os ajustes locais de `docker-compose.yml` (portas e versão do Postgres) ficam fora dos commits de propósito: o arquivo deve continuar aparecendo como modificado. Commits não levam linha de coautoria.
