"""Adaptadores conservadores: bloqueios e contratos desconhecidos são erros visíveis."""
import json
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from connectors.http import fetch, ExternalUnavailable
from normalizer import FIELDS
from config import USER_AGENT

class ScraperUnavailable(RuntimeError):
    pass

def remover_campos_proibidos(record):
    return {k:v for k,v in record.items() if k in FIELDS}

def validate_portal_url(url,allowed_hosts):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Use uma URL HTTPS pública do portal selecionado.')
    host = (parsed.hostname or '').lower()
    if not any(host == d or host.endswith('.'+d) for d in allowed_hosts):
        raise ValueError('O domínio não corresponde ao portal selecionado.')
    return parsed

def fetch_page(url,allowed_hosts):
    parsed = validate_portal_url(url,allowed_hosts)
    # Fail closed if robots cannot be checked; never circumvent captcha or login.
    try:
        robot_text = fetch(f'https://{parsed.netloc}/robots.txt',as_json=False,ttl=86400)
        robots = RobotFileParser()
        robots.parse(robot_text.splitlines())
        if not robots.can_fetch(USER_AGENT,url):
            raise ScraperUnavailable('Coleta não permitida pelo robots.txt para esta URL.')
        from connectors.http import _reserve
        delay = robots.crawl_delay(USER_AGENT) or robots.crawl_delay('*') or 3
        if delay > 3:
            _reserve(parsed.netloc,interval=delay)
        html = fetch(url,as_json=False,cache=False)
        if any(text in html.lower() for text in ('cf-chl-', 'g-recaptcha', 'access denied')):
            raise ScraperUnavailable('Portal bloqueou a coleta. Use exportação autorizada CSV/JSON.')
        return html
    except ExternalUnavailable as exc:
        raise ScraperUnavailable(str(exc)) from exc

def json_scripts(html):
    soup = BeautifulSoup(html,'html.parser')
    for tag in soup.find_all('script'):
        if tag.get('type') in ('application/json','application/ld+json') or tag.get('id') == '__NEXT_DATA__':
            try:
                yield json.loads(tag.string or tag.get_text())
            except (ValueError,TypeError):
                continue

def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value,list):
        for child in value:
            yield from walk(child)

def ld_record(item,source,city,purpose):
    offer = item.get('offers') or {}
    if isinstance(offer,list):
        offer = offer[0] if offer else {}
    if not isinstance(offer,dict) or offer.get('price') is None:
        return None
    property_item = item.get('itemOffered') or item
    if offer.get('businessFunction') and not str(offer['businessFunction']).endswith('/Sell' if purpose=='venda' else '/LeaseOut'):
        return None
    address = property_item.get('address') or {}
    if isinstance(address,dict) and address.get('addressLocality') and city.casefold() not in str(address['addressLocality']).casefold():
        return None
    geo = property_item.get('geo') or {}
    floor = property_item.get('floorSize') or {}
    url = item.get('url') or offer.get('url')
    if url and url.startswith('www.'):
        url = 'https://' + url
    identifier = item.get('sku') or item.get('productID') or (urlsplit(url).path.rstrip('/').split('/')[-1] if url else None) or item.get('@id')
    if not identifier:
        return None
    if len(str(identifier))>160:
        import hashlib
        identifier=hashlib.sha256(str(identifier).encode()).hexdigest()
    return {'fonte':source,'id_externo':str(identifier),'cidade':city,
            'bairro':'','titulo':item.get('name','Imóvel'),'url':url,'preco':offer['price'],
            'area_m2':floor.get('value') if isinstance(floor,dict) else None,
            'quartos':property_item.get('numberOfBedrooms'), 'finalidade':purpose,
            'latitude':geo.get('latitude') if isinstance(geo,dict) else None,
            'longitude':geo.get('longitude') if isinstance(geo,dict) else None,
            'geo_precisao':'portal_aproximada','tipo':'apartamento' if property_item.get('@type')=='Apartment' else 'outro'}

def parse_structured(html,source,city,purpose,custom):
    rows = {}
    for payload in json_scripts(html):
        for item in walk(payload):
            record = custom(item,city,purpose) or ld_record(item,source,city,purpose)
            if record:
                rows[str(record['id_externo'])] = remover_campos_proibidos(record)
    if not rows:
        raise ScraperUnavailable('Nenhum anúncio reconhecido no HTML. O contrato do portal precisa de validação; importe CSV/JSON autorizado.')
    return list(rows.values())
