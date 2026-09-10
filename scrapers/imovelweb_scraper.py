from scrapers.base import fetch_page, parse_structured

def parse_ad(item,city,purpose):
    if not item.get('postingId') or not item.get('priceOperationTypes'):
        return None
    price_types = item['priceOperationTypes']
    prices = price_types[0].get('prices',[]) if isinstance(price_types,list) else []
    if not prices:
        return None
    location = item.get('postingLocation') or {}
    geo = location.get('postingGeolocation') or {}
    coords = geo.get('geolocation') or geo
    features = item.get('mainFeatures') or {}
    def feature(key):
        raw = features.get(key,{})
        return raw.get('value') if isinstance(raw,dict) else raw
    url = item.get('url','')
    if url.startswith('/'):
        url = 'https://www.imovelweb.com.br'+url
    return {'fonte':'ImovelWeb','id_externo':str(item['postingId']),'cidade':city,
            'titulo':item.get('title','Imóvel'),'url':url,'preco':prices[0].get('amount'),
            'bairro':(location.get('location') or {}).get('name',''),
            'area_m2':feature('CFT100'),'quartos':feature('CFT2'),'vagas':feature('CFT7'),
            'latitude':coords.get('latitude'),'longitude':coords.get('longitude'),
            'geo_precisao':'portal_aproximada','tipo':'outro','finalidade':purpose}

def parse(html,city,purpose='venda'):
    return parse_structured(html,'ImovelWeb',city,purpose,parse_ad)

def collect(url,city,purpose='venda'):
    return parse(fetch_page(url,['imovelweb.com.br']),city,purpose)
