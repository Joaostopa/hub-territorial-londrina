"""Piloto explícito: venda de apartamentos em Londrina. URLs públicas, sem endpoints privados."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Source:
    key: str
    name: str
    domains: tuple[str,...]
    start_url: str
    detail_pattern: str
    kind: str = 'anuncios'

SOURCES = {
    s.key:s for s in [
        Source('olx','OLX',('olx.com.br',),'https://www.olx.com.br/imoveis/venda/apartamentos/estado-pr/regiao-de-londrina/londrina',r'/imoveis/[^/?]+-\d{8,}(?:$|\?)'),
        Source('zap','ZAP',('zapimoveis.com.br',),'https://www.zapimoveis.com.br/venda/apartamentos/pr+londrina/',r'/imovel/[^?#]+'),
        Source('vivareal','VivaReal',('vivareal.com.br',),'https://www.vivareal.com.br/venda/parana/londrina/apartamento_residencial/',r'/imovel/[^?#]+'),
        Source('imovelweb','ImovelWeb',('imovelweb.com.br',),'https://www.imovelweb.com.br/apartamentos-venda-londrina-pr.html',r'/propriedades/[^?#]+'),
        Source('santamerica','Santamérica',('santamerica.com.br',),'https://www.santamerica.com.br/comprar/Londrina/Apartamento',r'/(?:comprar|alugar|imovel)/[^?#]*\d{4,}(?:/|$|\?)'),
        Source('human','Human Imóveis',('humanimoveis.com',),'https://www.humanimoveis.com/imoveis/a-venda/apartamento/londrina-pr',r'/(?:imovel|imoveis)/(?!a-venda|para-alugar)[^?#]+'),
        Source('monaco','Mônaco',('imobiliariamonaco.com.br',),'https://www.imobiliariamonaco.com.br/imoveis/a-venda/apartamento/londrina',r'/(?:imovel|imoveis)/(?!a-venda|para-alugar)[^?#]+'),
        Source('yticon','Yticon',('yticon.com.br',),'https://www.yticon.com.br/empreendimentos',r'/empreendimentos/londrina/[^/?#]+','empreendimentos'),
    ]
}
