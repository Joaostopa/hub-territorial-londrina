# Importar vendas do novo coletor

O site público já recebeu a base validada enviada em 13/09/2026. Não foi iniciada nova coleta paga.

## Resultado desta importação

- Arquivo original: 415 registros, 415 IDs, 14 páginas.
- Aceitos: 414 apartamentos à venda em Curitiba.
- Excluído: 1 anúncio de aluguel, conforme o escopo atual.
- Bacacheri informado: 376; outros bairros: 38.
- 414 posições numéricas utilizáveis no recorte municipal. Destas, 37 são centros geométricos, apresentados como rua aproximada e desabilitados no mapa por padrão.
- Coordenadas declaradas pelo portal não foram verificadas presencialmente.
- Datas published_at/created_at/updated_at não são datas da coleta. Referência desta base: exportação fornecida 2026-09-13 21:23:06.702 UTC, identificada pelo nome do arquivo. O horário real de coleta não consta nos registros.
- Não são 414 imóveis físicos únicos confirmados nem a totalidade da oferta do Bacacheri.
- Para empreendimento com variantes, preço mínimo rotulado “A partir de”; área útil permanece ausente quando não há vínculo inequívoco entre preço e área da mesma tipologia.
- Contatos, dados do anunciante e mídia com URLs incompletas não foram publicados.

## No seu computador: sem baixar o projeto inteiro

1. Baixe `importar_vivareal_vendas.py` deste repositório e coloque na pasta que já contém `curitiba_pipeline.py`.
2. Coloque nessa pasta o JSON exportado da Apify.
3. No terminal do VS Code, execute:

```powershell
python importar_vivareal_vendas.py "dataset_vivareal-scraper_2026-09-13_21-23-06-702.json"
.\iniciar_curitiba.bat
```

O importador não precisa de token e não cobra. Faz backup antes de acrescentar observações ao banco local. O mesmo arquivo não é importado duas vezes. A referência de arquivos futuros é o momento da importação, claramente identificado; não usa publicação como coleta.

Para atualizar também a interface local sem baixar tudo, substitua `docs/curitiba/app.js` e `docs/curitiba/index.html` pelas versões deste repositório. Os campos novos indicam referência temporal, preço mínimo por empreendimento e precisão de coordenadas. O menu de finalidade fica apenas em venda; o histórico anterior no banco não é apagado.

O upload JSON da página também reconhece o novo coletor, mas é temporário no navegador. Para histórico permanente use o script Python.

O script `coletar_curitiba.bat` ainda chama o Actor anterior que parou na primeira página. Não use esse script para ampliar a base. Esta entrega adapta a importação do novo coletor, não substitui a rotina de coleta paga.

## Verificação

Validação executada sobre o arquivo real: contagens, cidade, finalidade, tipos, 415 IDs, 14 páginas, exclusão do aluguel, repetição idempotente, supressão de contatos, áreas não pareadas e filtro web de 376 registros do Bacacheri. A existência física, disponibilidade atual e exatidão geográfica de cada imóvel não foram reconfirmadas individualmente.
