from connectors.http import fetch, ExternalUnavailable

def search_address(query):
    if len(query.strip()) < 4:
        raise ValueError('Digite um endereço ou local mais específico.')
    payload = fetch('https://nominatim.openstreetmap.org/search',
                    params={'q':query,'format':'jsonv2','countrycodes':'br','limit':5},ttl=7*86400)
    return [{'label':r['display_name'],'lat':float(r['lat']),'lon':float(r['lon'])} for r in payload]
