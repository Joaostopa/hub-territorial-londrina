"""Importação por whitelist: nunca persiste telefone, e-mail ou nome de anunciante."""
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
import pandas as pd

FIELDS = {'fonte','id_externo','data_coleta','titulo','url','cidade','bairro','finalidade',
          'tipo','preco','area_m2','quartos','vagas','latitude','longitude','geo_precisao'}
REQUIRED = {'fonte','id_externo','cidade','preco','finalidade'}

def number(value, *, br_thousands=False):
    if value is None or str(value).strip().lower() in ('', 'none', 'nan', 'null'):
        return None
    if isinstance(value, (int, float)):
        n = float(value)
    else:
        raw = re.sub(r'[^\d,.+\-]', '', str(value))
        if ',' in raw:
            raw = raw.replace('.', '').replace(',', '.')
        elif br_thousands and re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+',raw):
            raw = raw.replace('.', '')
        n = float(raw)
    if not math.isfinite(n):
        raise ValueError('Valor numérico não finito.')
    return n

def clean_text(value, limit):
    value = re.sub(r'<[^>]+>', '', str(value or ''))
    value = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[removido]', value)
    value = re.sub(r'(?:\+?55[\s-]*)?\(?\d{2}\)?[\s-]*\d{4,5}[\s-]*\d{4}\b', '[removido]', value)
    return value.strip()[:limit]

def clean_url(value):
    if not value:
        return None
    parts = urlsplit(str(value))
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))

def normalize_record(raw, *, demo=False):
    data = {k: v for k, v in raw.items() if k in FIELDS and not (isinstance(v, float) and math.isnan(v))}
    missing = [k for k in REQUIRED if data.get(k) is None or str(data[k]).strip() == '']
    if missing:
        raise ValueError('Campos obrigatórios ausentes: ' + ', '.join(missing))
    out = {k: clean_text(data.get(k), size) for k, size in
           [('fonte',80),('id_externo',160),('cidade',100),('bairro',160),('titulo',300)]}
    # Stable IDs are not contact fields: never redact a numeric listing ID as a phone.
    identifier = re.sub(r'<[^>]+>', '', str(data['id_externo'])).strip()
    if not identifier or len(identifier) > 160:
        raise ValueError('id_externo deve ter entre 1 e 160 caracteres.')
    out['id_externo'] = identifier
    from config import CITIES
    import unicodedata
    def city_key(value):
        return ''.join(c for c in unicodedata.normalize('NFD',value.casefold()) if unicodedata.category(c) != 'Mn')
    city_lookup = {city_key(c):c for c in CITIES}
    if city_key(out['cidade']) not in city_lookup:
        raise ValueError('Cidade fora do piloto: use um dos seis municípios disponíveis no aplicativo.')
    out['cidade'] = city_lookup[city_key(out['cidade'])]
    out['titulo'] = out['titulo'] or 'Imóvel'
    out['finalidade'] = str(data['finalidade']).strip().lower()
    if out['finalidade'] not in ('venda','aluguel'):
        raise ValueError('finalidade deve ser venda ou aluguel.')
    out['tipo'] = clean_text(data.get('tipo') or 'outro',60).lower()
    out['preco'] = number(data['preco'], br_thousands=True)
    out['area_m2'] = number(data.get('area_m2'), br_thousands=True)
    if out['preco'] is None or out['preco'] <= 0:
        raise ValueError('preco deve ser positivo.')
    if out['area_m2'] is not None and out['area_m2'] <= 0:
        raise ValueError('area_m2 deve ser positiva ou vazia.')
    out['preco_m2'] = out['preco']/out['area_m2'] if out['area_m2'] else None
    if out['preco_m2'] is not None and not math.isfinite(out['preco_m2']):
        raise ValueError('Preço/m² fora dos limites numéricos.')
    for key in ('quartos','vagas'):
        val = number(data.get(key))
        if val is not None and (val < 0 or val != int(val)):
            raise ValueError(f'{key} deve ser inteiro não negativo.')
        out[key] = int(val) if val is not None else None
    out['latitude'], out['longitude'] = number(data.get('latitude')), number(data.get('longitude'))
    lat, lon = out['latitude'], out['longitude']
    if (lat is None) != (lon is None):
        raise ValueError('Informe latitude e longitude juntas.')
    if lat is not None and (not -90 <= lat <= 90 or not -180 <= lon <= 180):
        raise ValueError('Coordenadas inválidas.')
    out['geo_precisao'] = clean_text(data.get('geo_precisao') or ('informada' if lat is not None else 'nao_informada'),30)
    if lat is not None:
        from geoutils import haversine
        center=CITIES[out['cidade']]
        if haversine(lat,lon,center['lat'],center['lon'])>100:
            out['latitude']=out['longitude']=None
            out['geo_precisao']='fora_cidade_revisar'
    out['url'] = clean_url(data.get('url'))
    if data.get('data_coleta'):
        timestamp = pd.to_datetime(data['data_coleta'], utc=True, errors='raise')
        if pd.isna(timestamp):
            raise ValueError('data_coleta inválida.')
        out['data_coleta'] = timestamp.to_pydatetime().replace(tzinfo=None)
    else:
        out['data_coleta'] = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    out['is_demo'] = demo
    return out
