> **Atualização Apify — Londrina (09/09/2026):** integração com o Actor informado, histórico por execução, exportação e agendamento semanal no Windows. Comece por [APIFY_LONDRINA.md](APIFY_LONDRINA.md). Configure seu token localmente; a primeira coleta autenticada ainda precisa ser executada e validada.

> **Atualização de 09/09/2026:** para a edição local com dados reais, siga `ABRIR_NO_VSCODE.md`. O texto abaixo registra a entrega anterior, quando a coleta ainda não havia sido validada. Em 08/09 foram extraídos 37 anúncios de Human/Santamérica.

# Coleta multifuente — piloto Londrina

1. Extraia o ZIP em uma pasta. Para atualizar uma instalação existente, faça backup do banco e copie o código, preservando `data/`, `.env` e credenciais.
2. Execute `instalar_windows.bat`.
3. Execute `coletar_londrina.bat`. Ele tenta as oito fontes cadastradas com até três páginas por fonte e grava `diagnostico_coleta.json`. Não feche o terminal durante a execução.
4. Execute `iniciar_windows.bat`. Desative **Modo demonstração** e abra **Fontes e coletas** para ver os resultados. Também é possível executar as fontes individualmente nessa tela.
5. Em **Dados e coleta**, confira os anúncios recebidos. Só registros com latitude e longitude participam da busca por raio. Endereço ou bairro não são coordenadas exatas.

O piloto busca apartamentos à venda em Londrina. O cadastro Yticon é separado dos anúncios e não recebe preços inventados. A escolha de outra cidade na lateral não altera esse piloto.

## O que está pronto

- Registro de OLX, ZAP, VivaReal, Imovelweb, Santamérica, Human, Mônaco e Yticon.
- Leitura de dados estruturados públicos e extração conservadora de cartões das imobiliárias.
- Paginação por links de próxima página presentes no HTML; limite total inclui páginas de detalhes.
- Verificação de robots.txt, intervalo mínimo de três segundos, redirects restritos à fonte e interrupção em bloqueios.
- Persistência incremental: uma falha posterior preserva os registros já gravados.
- Histórico de execuções, limites atingidos, rejeições e falhas por fonte.
- Banco inicializado antes da consulta; não é necessário criar `imoveis` manualmente.

## Limite da validação desta entrega

Em 07/09/2026, páginas de imobiliárias puderam ser consultadas pela pesquisa web, mas as tentativas diretas por Python terminaram em `ReadTimeout`, inclusive no IBGE. O arquivo `validacao/acesso_direto_2026-09-07.json` registra essas tentativas. VivaReal não foi incluído nessa sondagem direta.

**Nenhuma coleta automática real foi concluída neste ambiente.** Os testes são de código com respostas controladas; não certificam os contratos atuais dos portais. URLs, seletores e estruturas poderão precisar de ajuste após o diagnóstico local. Não há anúncios inventados no banco real e a demonstração continua separada.

`parse_unrecognized` significa que o adaptador não reconheceu dados; não significa mercado sem anúncios. `network_error` significa falha de conexão; não prova bloqueio pelo portal. `partial` exige leitura de `detail`. Mesmo `success` não certifica cobertura completa: confira `truncated`.

A deduplicação é por fonte e identificador; um imóvel anunciado em duas fontes ainda pode aparecer duas vezes. Não se infere venda/retirada pelo desaparecimento de uma página. Dados municipais do IBGE não são indicadores exatos de um círculo. Não há promessa de coleta de todos os portais ou de APIs privadas.

## Terminal

```bat
venv\Scripts\python.exe collect_batch.py --sources santamerica human monaco --max-pages 3
venv\Scripts\python.exe collect_batch.py --sources olx zap vivareal imovelweb --max-pages 3
venv\Scripts\python.exe collect_batch.py --sources yticon --max-pages 5
```

Máximo permitido por execução: 20 páginas e 1.000 registros por fonte. O código de saída 2 indica alguma fonte sem sucesso completo. Consulte o JSON gerado antes de agendar novas execuções. A execução é sequencial; não foi criado agendamento automático.
