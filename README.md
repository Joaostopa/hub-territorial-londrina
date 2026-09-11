# Hub Territorial · Londrina e Curitiba

Projeto Python de coleta e análise imobiliária e apresentação estática responsiva em `docs/`.

## Novo piloto: Curitiba / Bacacheri

Abra `docs/curitiba/` na apresentação. Instruções completas: [CURITIBA_BACACHERI.md](CURITIBA_BACACHERI.md). Rotina nova: `curitiba_pipeline.py`; atalhos Windows: `coletar_curitiba.bat`, `sincronizar_curitiba.bat`, `iniciar_curitiba.bat`.

IBGE municipal e conveniências obtidos de fontes públicas. A base de anúncios de Curitiba começa vazia e precisa de coleta Apify ou importação real; não há 3.000 anúncios pré-carregados. Meta não é garantia de estoque. Endereços podem ser geocodificados com precisão identificada, usando chave Geoapify local opcional.


## Abrir a apresentação

A publicação ainda precisa ser ativada pelo proprietário em **Settings → Pages → Deploy from a branch → main → /docs → Save**.

Link das configurações: https://github.com/Joaostopa/hub-territorial-londrina/settings/pages

Endereço esperado **somente após publicação bem-sucedida**: https://joaostopa.github.io/hub-territorial-londrina/

GitHub Pages em repositório privado exige plano compatível (por exemplo, GitHub Pro). Em contas pessoais, manter o código privado não torna automaticamente o site Pages privado. Verifique a visibilidade antes de publicar: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages

O código está mantido privado. Nenhuma mudança de visibilidade foi aplicada automaticamente.

## Dados disponíveis

- 37 anúncios reais coletados de Human Imóveis e Santamérica em 08/09/2026; 9 com coordenadas utilizáveis. A disponibilidade não foi reconfirmada.
- 100 locais das categorias exibidas no OpenStreetMap, em recorte de 1,5 km ao redor de -23.3045, -51.1696, em 08/09/2026. Fora desse recorte, cobertura desconhecida.
- População e faixas etárias municipais do Censo IBGE 2022. Não são estimativas para bairros ou círculos.
- Preços anunciados, não transações concluídas. Anúncios não equivalem a imóveis físicos nem empreendimentos únicos.

## Apresentação web

- Mapa com desenho de círculo; localização aproximada conforme os portais.
- Lista e indicadores incluem anúncios sem coordenadas enquanto nenhum raio está selecionado.
- Busca textual por dados disponíveis de título, bairro, endereço e identificador; não geocodifica automaticamente.
- Filtros por tipo, finalidade, fonte, preço e categorias de conveniência.
- Gráficos por bairro e mediana de preço/m² com amostra mínima de 5 anúncios.
- CSV e impressão do relatório / salvar como PDF pelo navegador.
- Importação temporária de JSON do Actor `jungle_synthesizer/brazil-vivareal-zap-imoveis-scraper`. Apenas Londrina/PR, portais VivaReal/ZAP, campos compatíveis, moeda BRL e coleta datada. Não aceita todo formato de Actor.

O JSON importado é processado em memória neste navegador, sem upload ou cobrança; recarregar restaura a base publicada. Para atualizar permanentemente a apresentação, substitua `docs/imoveis.json` por uma exportação normalizada e revisada. Para histórico completo, use o banco do projeto Python; GitHub Pages não executa a coleta ou sincroniza o notebook.

Dependências externas do mapa: Leaflet/Leaflet Draw via unpkg e tiles OpenStreetMap. A rede corporativa precisa permitir esses domínios. Os indicadores e a lista continuam utilizáveis se a biblioteca do mapa falhar.

## Rodar no notebook

Use Python 3.11 ou 3.12. Veja `COMECE_AQUI.md`, `ABRIR_NO_VSCODE.md` e `APIFY_LONDRINA.md`.

No PowerShell dentro da pasta do projeto:

```powershell
.\instalar_windows.bat
.\.venv\Scripts\python.exe -m streamlit run inteligencia_mercado.py --server.address 127.0.0.1 --server.port 8502
```

Configure um token novo em `.env`, apenas no computador. Nunca envie `.env`, tokens, senhas, bancos pessoais ou arquivos brutos com contatos para este repositório ou para o navegador.

A coleta de até 1.500 itens é um limite solicitado, não garantia de quantidade. O painel suplementar tem reserva preventiva de US$4 por tentativa, no máximo duas tentativas antes de bloquear novas; não limita gastos de outros aplicativos, tarefas ou execuções na conta Apify. Tarifas reais devem ser verificadas no Actor antes de executar.

As rotinas de coleta semanal e os snapshots históricos permanecem no Python. Nenhuma coleta paga foi disparada pela publicação deste projeto.
