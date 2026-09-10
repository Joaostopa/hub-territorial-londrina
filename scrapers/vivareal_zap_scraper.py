"""Importa uma resposta JSON obtida de forma autorizada; não presume endpoint privado."""
from scrapers.base import walk, ScraperUnavailable

def parse_payload(payload,city,purpose='venda',source='VivaReal'):
    records = {}
    for item in walk(payload):
        if not item.get('id') or not isinstance(item.get('pricingInfos'),list):
            continue
        price = next((p for p in item['pricingInfos'] if p.get('businessType') == ('SALE' if purpose=='venda' else 'RENTAL')),None)
        if not price or not price.get('price'):
            continue
        address = item.get('address') or {}
        point = (address.get('point') or {})
        def first(key):
            v = item.get(key)
            return v[0] if isinstance(v,list) and v else v
        record = {'fonte':source,'id_externo':str(item['id']),'cidade':city,
                  'titulo':item.get('title','Imóvel'),'preco':price['price'],'finalidade':purpose,
                  'bairro':address.get('neighborhood',''),'area_m2':first('usableAreas'),
                  'quartos':first('bedrooms'),'vagas':first('parkingSpaces'),
                  'latitude':point.get('lat'),'longitude':point.get('lon'),
                  'geo_precisao':'portal_aproximada','tipo':'outro'}
        records[record['id_externo']] = record
    if not records:
        raise ScraperUnavailable('JSON não contém anúncios no contrato pricingInfos/address esperado.')
    return list(records.values())
