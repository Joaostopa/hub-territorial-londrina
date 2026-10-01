# Coleta e classificação de Curitiba

O site continua no GitHub Pages. `docs/curitiba/empreendimentos.json` é o endpoint
JSON público de leitura do catálogo, usado pela tela. Não é uma API oficial das
construtoras nem um serviço que executa scraping a cada consulta. Atualizações
dependem da execução dos scripts e publicação dos JSONs no repositório.

## Construtoras

Instale `python -m pip install -r scripts/requirements-market.txt`.
Execute `python scripts/collect_builders.py`. São lidos os catálogos públicos de
Plaenge, Vectra e A.Yoshii com cidade explícita Curitiba. Falhas preservam dados
anteriores e aparecem em `sources`. A coleta não cobre necessariamente páginas
adicionais, imóveis retirados ou todo o portfólio histórico. O primeiro catálogo
A.Yoshii foi conferido no site oficial e importado de forma assistida, pois a
requisição HTTP do coletor recebeu 403. Não se contorna esse bloqueio.

## Imovelweb pela Apify

Integração preparada com `anyxsolutions/imovelweb-scraper`, entrada e saída
documentadas em https://apify.com/anyxsolutions/imovelweb-scraper.
Ainda não validada com execução paga: em 30/09 a conta atingiu US$ 10/US$ 10 e
a plataforma desabilitou novos Actors. Não foi ativada assinatura ou recarga.

Configure `APIFY_TOKEN` no ambiente de execução privado. Nunca coloque token nos
arquivos de `docs`, JavaScript, query strings ou commits. Exemplo de execução
após liberar saldo, com teto explícito escolhido pelo operador:

```sh
python scripts/apify_imovelweb.py --collect --purpose venda --limit 200 --max-total-charge-usd 2
```

O valor do exemplo não é previsão de custo. A busca retorna cartões; uma segunda
execução obtém detalhes, descontando o custo da primeira do teto autorizado.
Se o custo não vier na resposta, a segunda execução não começa. Reexecute com
`--purpose aluguel` e orçamento próprio para aluguel. Os resultados são parciais,
com finalidade e fonte separadas; ausências não geram vendas estimadas.

É possível importar exportação de detalhes sem iniciar execução paga:

```sh
python scripts/apify_imovelweb.py --input detalhes.json --purpose venda --run-id ID_DA_EXECUCAO --observed-at 2026-09-30T19:00:00Z
```

Não se aceita cidade inferida apenas pela URL de busca: cada detalhe precisa
informar Curitiba/PR, preço positivo em BRL e URL do Imovelweb. Anúncios entre
portais podem representar o mesmo imóvel: não são contabilizados como unidades
exclusivas. Campos desconhecidos permanecem vazios.

## Classificação Python

```sh
python scripts/classify_properties.py --raw exportacao-vivareal.json --run-id ID_DA_EXECUCAO
```

Prioridade: campo estruturado do portal; depois evidência explícita do título ou
descrição. Detecta na planta, em construção e pronto, recusa negações, previsões,
menções a prédios vizinhos e textos conflitantes. Data de entrega prevista não
prova conclusão. "Lançamento" é fase comercial e não determina estágio físico.
Cada resultado guarda origem, evidência e tipo de confiança. Não é inspeção da obra.

Construtora vem de campo explícito, expressão textual identificável ou associação
única do nome ao catálogo oficial. Anunciante não é construtora por suposição.
Alto padrão é um indício declarado na fonte, não certificação por preço.
O JSON público não contém contatos, credenciais ou descrições integrais.

Verificação: `python -m unittest discover -s tests -p 'test_*.py'` e
`node --test tests/market.test.cjs`.
