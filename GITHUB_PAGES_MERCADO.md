# Painel de mercado no GitHub Pages

A interface publicada em `docs/` oferece o mesmo layout em Londrina e Curitiba. Curitiba mantém os 414 anúncios de venda publicados e inclui o anúncio de aluguel da mesma exportação original (13/09/2026). Nenhum anúncio foi consultado novamente nesta atualização.

## Dados publicados

Cada página lê `imoveis.json`, `ibge.json`, `pois.json`, `bairros.geojson` e `historico.json` de sua própria pasta. Não substitua os dados de Londrina pelos de Curitiba. A interface reutilizada fica em `docs/curitiba/`.

A malha territorial traz população e domicílios dos bairros do Censo 2022. Círculos usam fração de área; cobertura incompleta suprime o total. Crescimento demográfico fica indisponível sem outro período comparável.

## Histórico

`historico.json` contém `{ "version": 1, "batches": [] }`. Cada lote tem `source`, `purpose` (venda/aluguel), `coverage` (identificador fixo da busca), `observed_at` ou `observed` (ISO 8601), `complete` (booleano), `note` e `records` (anúncios normalizados). A cidade é a da página. Use os mesmos IDs, fonte e escopo em observações sucessivas.

Somente uma coleta completa pode produzir uma estimativa por ausência. Falhas, truncamento e rejeições impedem esse uso. Resultado vazio exige `empty_confirmed: true`. Reaparecimentos revertem a estimativa. Estimativas são por anúncio, salvo identificação explícita por empreendimento, torre e unidade.

Importações na interface permanecem apenas na sessão. O botão **Baixar histórico da sessão** permite guardar os dados e carregá-los novamente. Para compartilhar, publique o arquivo na pasta da cidade. Não coloque tokens ou dados pessoais no repositório público. GitHub Pages não executa o coletor Python nem guarda segredos de API; a futura integração deve gerar esses arquivos fora do navegador.

## Verificação

Execute `node --test tests/market.test.cjs` na raiz do repositório. O teste valida ausência, reaparecimento, separação de finalidade, preservação da base e inicialização das abas com filtros.
