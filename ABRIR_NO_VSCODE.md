> **Atualização Apify — Londrina (09/09/2026):** integração com o Actor informado, histórico por execução, exportação e agendamento semanal no Windows. Comece por [APIFY_LONDRINA.md](APIFY_LONDRINA.md). Configure seu token localmente; a primeira coleta autenticada ainda precisa ser executada e validada.

# Executar no notebook com Visual Studio Code

Esta é a edição local em Python/Streamlit. Não precisa de hospedagem, conta de nuvem ou chave para IBGE/OSM. Internet é necessária para atualizar fontes e carregar o mapa.

1. Instale Python 3.12, marcando **Add Python to PATH**.
2. Extraia todo o ZIP. Abra a pasta `imoveis-hub` no **Visual Studio Code → Arquivo → Abrir Pasta**.
3. Instale as extensões Python e Python Debugger sugeridas pelo editor.
4. Execute `instalar_windows.bat` uma vez. Ele instala as dependências em `.venv`, inicializa o banco e importa a base real datada de 08/09/2026. Não apaga o banco existente.
5. No VS Code, pressione **Ctrl+Shift+P → Python: Select Interpreter**, escolha `.venv\Scripts\python.exe`.
6. Em **Executar e Depurar**, selecione **Hub Territorial — abrir site** e pressione **F5**.
7. Abra **http://localhost:8501** no navegador. Alternativa: clique duas vezes em `iniciar_windows.bat`.
8. Mantenha o modo demonstração desativado. Para atualizar os anúncios, abra **Fontes e coletas**, marque Human e Santamérica e comece com uma página de cada.

Se o PowerShell impedir a ativação do ambiente, não precisa mudar a política: os comandos abaixo usam diretamente o Python correto.

```powershell
.\.venv\Scripts\python.exe preparar_projeto.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

## O que é real nesta entrega

- 37 anúncios extraídos em 08/09/2026: Human (10), Santamérica (27). Links e datas preservados em `dados_verificados/imoveis_2026-09-08.json`.
- 9 posições utilizáveis fornecidas pela Human, identificadas como aproximadas. Uma posição incompatível com Londrina foi descartada; endereços não são inventados.
- IBGE/Censo 2022: população municipal, rendimento domiciliar mensal per capita médio e mediano e 21 faixas etárias. Fontes: tabelas 4714, 10295 e 9514. As idades foram reconciliadas com a população total de Londrina.
- OSM/Overpass para conveniências e Nominatim para pesquisa de endereços. Cobertura colaborativa e distâncias em linha reta.

Consulta preservada não significa informação atualizada hoje. A data da observação acompanha os anúncios. Em falhas de consulta ao IBGE, a cópia validada de Londrina é identificada como consulta de 08/09/2026. Dados municipais não são indicadores exatos do círculo.

## Limites conhecidos

OLX e ZAP recusaram o acesso com HTTP 403; Imovelweb recusou a página de busca; Mônaco não permitiu este coletor no robots.txt. Não há promessa de coleta total desses portais. O funcionamento de uma fonte pode mudar.

A malha de bairros exige um arquivo oficial compatível; não confundir regiões administrativas com bairros. Demografia exata do círculo, estoque realmente disponível e preço efetivo de venda não estão comprovados nesta base.

O layout local é o Streamlit; a interface web que estava sendo preparada para hospedagem ainda não foi publicada. Não depende dela para executar este projeto.

## Desenvolvimento

- `app.py`: telas e fluxo principal.
- `scrapers/`: adaptadores de cada fonte e transporte com limites.
- `collect_batch.py`: coleta em lote e diagnóstico.
- `connectors/ibge_perfil.py`: população, renda e idade municipais.
- `normalizer.py`: padronização e qualidade das informações.
- `db/`: armazenamento SQLite e consultas.
- `map_ui.py` e `geoutils.py`: mapa, desenho e filtro espacial.
- `pdf_report.py`: relatório.

Antes de atualizar uma instalação antiga, faça backup de `data/`, `.env` e credenciais. Não envie esses arquivos ao compartilhar o código.
