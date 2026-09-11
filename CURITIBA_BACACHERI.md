# Piloto Curitiba / Bacacheri

## O que foi entregue e o que falta

Código de coleta, importação, histórico, geocodificação opcional, dados públicos e apresentação em `docs/curitiba/`. População do IBGE 2022 consultada na API oficial: 1.773.718 habitantes em Curitiba. Esse total NÃO é a população do Bacacheri.

Meta solicitada: **3.000 anúncios**, interpretando “3000 mil” como três mil, não três milhões. Nenhuma quantidade é garantida. Não há nova base Apify de Curitiba embutida: ela depende de execução com token válido ou JSON real fornecido pelo usuário. A tela mostra zero até receber registros reais.

Não foram reutilizados anúncios de Londrina como se fossem de Curitiba. A base anterior e sua página permanecem disponíveis no endereço raiz.

## Usar no Windows / VS Code

1. Atualize o projeto pelo GitHub (se foi clonado, `git pull --ff-only`; se usa ZIP, baixe a nova versão para outra pasta e copie apenas o `.env` e a pasta `data` do projeto anterior, mantendo seu backup).
2. Na pasta que contém `curitiba_pipeline.py`, crie/atualize o `.env` local com `APIFY_TOKEN=SEU_TOKEN_NOVO`. Os tokens anteriormente enviados no chat devem ser revogados. Não envie nem publique o `.env`.
3. Execute `./coletar_curitiba.bat` no PowerShell. São dois pedidos separados: apartamento, Curitiba/PR, venda e aluguel mensal, até 1.500 resultados por pedido, portais BOTH.
4. Aguarde a conclusão em Runs no Console Apify e execute `./sincronizar_curitiba.bat`. Pode repetir a sincronização sem duplicar observações já importadas. Execuções ainda em andamento ficam pendentes. Resultados de execução finalizada com falha/timeout são importados como parciais, com status impresso.
5. Execute `./iniciar_curitiba.bat`: abre http://127.0.0.1:8503/curitiba/. Se o navegador abrir antes do servidor, recarregue a página. Deixe o terminal aberto.
6. A apresentação abre filtrada em Bacacheri. Troque para “Toda Curitiba” para ver o conjunto municipal. O filtro de bairro usa campo informado, não a posição dentro de polígono oficial.

O pipeline novo usa apenas a biblioteca padrão do Python 3.11 ou superior. Não precisa instalar novas dependências. O aplicativo Streamlit anterior continua com seus requisitos próprios.

## Custos e cobertura

- O Actor documenta filtro municipal, não filtro por bairro ou fase da obra. A cobertura no Bacacheri depende do que vier nas páginas coletadas em Curitiba.
- A tarifa consultada em 11/09/2026 é US$0,002 por resultado e US$0,10 por início. Três mil resultados em duas execuções sugerem cerca de US$6,20, mas a cobrança real pode variar e duplicatas reduzem a contagem útil.
- Cada POST inclui `maxTotalChargeUsd=4` e `restartOnError=false`. Reservas são feitas ANTES da chamada, com transação SQLite; timeout não autoriza nova chamada automática.
- O saldo preventivo usa a tabela `intel_budget` do mesmo banco SQLite usado pelo painel anterior, com teto acumulado US$10. Se você já reservou US$8 no painel de Londrina, não há reserva suficiente para dois novos pedidos. Não apague o banco para contornar o limite.
- Não há reset semanal nem aumento automático de orçamento. Esta proteção não limita execuções iniciadas em outros aplicativos ou diretamente na Apify.
- Uma finalidade com job existente é retomada; `collect` não cria novas rodadas semanais. Novas rodadas exigem revisão de orçamento. O piloto não promete atualização contínua sem saldo/autorização.
- Deduplicação por ID compartilhado do Grupo ZAP + finalidade, mantendo histórico por portal. Não é deduplicação física universal de imóveis.

Fonte do Actor: https://apify.com/jungle_synthesizer/brazil-vivareal-zap-imoveis-scraper

## Geocodificar endereços ausentes

Opcionalmente, configure `GEOAPIFY_API_KEY` no `.env`, obtida em https://myprojects.geoapify.com/ . Confira a franquia, limite e cobrança do seu plano ANTES de usar. Nenhuma chave é colocada na página pública.

```powershell
python curitiba_pipeline.py geocode --limit 100
```

O serviço recebe somente endereço, número, CEP, bairro, cidade e país; nenhum contato do anunciante. Usa cache e processa sequencialmente. Máximo preventivo de 1.000 consultas acumuladas por banco; 100 por comando por padrão. Esse limite de chamadas não é teto financeiro da conta Geoapify.

- Resultado de endereço/número: confere cidade, rua e número; continua marcado como aproximado.
- Resultado de rua/CEP: confere correspondência e exibe precisão reduzida; só aparece no mapa/raio se ativar “Incluir rua/CEP”. Não se trata da localização exata do imóvel.
- Resultado apenas de bairro/cidade: rejeitado. Não posiciona imóveis no centro do bairro.
- Resultados ambíguos ou sem endereço suficiente continuam sem coordenadas, disponíveis na lista.
- Não foi usado Nominatim público para geocodificação massiva.

Documentação: https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/

## Fases dos apartamentos

“Na planta”, “em construção” e “pronto” só são classificados quando há expressão explícita e não ambígua no texto. A tabela mostra trecho e origem. Sem evidência, fica “Não informado”. O campo DEVELOPMENT não comprova obra em andamento nem USED comprova entrega. Datas estimadas de entrega não são tratadas como entrega concluída.

## Histórico, importação e recuperação

Banco SQLite absoluto: `data/imoveis.db` por padrão. Respeita `DATA_DIR` e URL SQLite de `DATABASE_URL`; não suporta PostgreSQL neste pipeline específico. Tabelas novas `ctb_*` convivem com as tabelas de Londrina.

Observações são acrescentadas, nunca sobrescritas. Reimportação idempotente e preço anterior preservado. São armazenados campos imobiliários selecionados, não contatos nem o JSON bruto completo do portal. A exportação da apresentação contém apenas a observação mais recente por ID/finalidade.

```powershell
python curitiba_pipeline.py import "C:\caminho\dataset-apify.json"
python curitiba_pipeline.py status
python curitiba_pipeline.py export
```

Backups consistentes antes de coleta/importação/sincronização em `data/backups/`. Importação JSON requer arquivo compatível com o Actor selecionado, até 20 mil registros ou 50 MB. Outros Actors exigem adaptadores próprios.

Se um POST foi enviado mas sua resposta se perdeu, o job fica START_UNCERTAIN. Confira no Console e vincule o run real:

```powershell
python curitiba_pipeline.py attach ID_DO_JOB RUN_ID
python curitiba_pipeline.py sync
```

O run é validado quanto a Actor, município, tipo e finalidade antes de aceitar.

## IBGE, mapa e publicação

`python curitiba_pipeline.py public` busca população municipal IBGE e conveniências OSM em até 3 km do centro de visualização do Bacacheri. Em falha preserva snapshot anterior, com data explícita. Ausência de POI não prova inexistência de serviços. Não há malha oficial de bairro ou indicadores demográficos por raio embutidos.

A página local e GitHub Pages leem JSON, sem token. O upload JSON na página é temporário no navegador; para histórico permanente use o comando `import`. Após importar ou geocodificar no Python, os JSON são exportados em `docs/curitiba/`.

Para atualizar o site GitHub Pages, envie apenas os JSON normalizados de `docs/curitiba/` ao repositório. Não envie `.env`, banco ou backups. Hospedagem não sincroniza automaticamente com o notebook.

Endereço esperado após Pages ativado: https://joaostopa.github.io/hub-territorial-londrina/curitiba/

## Anúncios sem posição individual: grupo do bairro

A página oferece um marcador agregado de referência visual no Bacacheri. Reúne anúncios com bairro Bacacheri informado que não têm posição habilitada. Quando o bairro está vazio, uma menção literal a Bacacheri no título/descrição pode aparecer como pista separada, marcada para conferência; não é prova de endereço. A opção de incluir menções pode ser desligada.

O marcador não altera coordenadas individuais nem entra no cálculo do raio. Ao clicar em “Ver anúncios do bairro”, o círculo é limpo e a lista abre filtrada por bairro/menção. A opção é exclusiva do Bacacheri neste piloto. Não há custo de geocodificação para esse agrupamento. A leitura da descrição ocorre em novas importações/coletas; dados antigos sem descrição não são enriquecidos retroativamente.
