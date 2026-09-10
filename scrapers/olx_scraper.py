from scrapers.base import fetch_page, parse_structured

def parse_ad(item,city,purpose):
    if not (item.get('listId') and item.get('price') is not None):
        return None
    props = {p.get('name'):p.get('value') for p in item.get('properties',[]) if isinstance(p,dict)}
    loc = item.get('locationDetails') or {}
    geo = item.get('location') or {}
    if not isinstance(geo,dict):
        geo = {}
    return {'fonte':'OLX','id_externo':str(item['listId']),'cidade':city,
            'titulo':item.get('subject') or item.get('title') or 'Imóvel',
            'url':item.get('url'),'preco':item['price'],'bairro':loc.get('neighbourhood',''),
            'area_m2':props.get('size'),'quartos':props.get('rooms'),'vagas':props.get('garage_spaces'),
            'latitude':geo.get('latitude'),'longitude':geo.get('longitude'),
            'geo_precisao':'portal_aproximada','tipo':'outro','finalidade':purpose}

def parse(html,city,purpose='venda'):
    return parse_structured(html,'OLX',city,purpose,parse_ad)

def collect(url,city,purpose='venda'):
    return parse(fetch_page(url,['olx.com.br']),city,purpose)
