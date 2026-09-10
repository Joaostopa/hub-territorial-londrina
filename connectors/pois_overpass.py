import pandas as pd
from connectors.http import fetch, ExternalUnavailable
from geoutils import validate_area, within_radius
from normalizer import clean_text

CATEGORIES = {'supermarket':'Mercado','convenience':'Mercado','pharmacy':'Farmácia',
              'fitness_centre':'Academia','restaurant':'Restaurante','school':'Escola','hospital':'Hospital'}
COLUMNS = ['id','nome','categoria','latitude','longitude','distancia_km']

def nearby_pois(lat,lon,radius):
    validate_area(lat,lon,radius)
    if radius > 10:
        return pd.DataFrame(columns=COLUMNS), 'POIs disponíveis para raios de até 10 km; reduza o círculo.'
    around = f'around:{radius*1000:.0f},{lat:.6f},{lon:.6f}'
    query = f'''[out:json][timeout:20];(
        nwr["shop"~"^(supermarket|convenience)$"]({around});
        nwr["amenity"~"^(pharmacy|restaurant|school|hospital)$"]({around});
        nwr["leisure"="fitness_centre"]({around}););out center tags;'''
    try:
        payload = fetch('https://overpass-api.de/api/interpreter',data={'data':query},ttl=86400)
        rows = []
        for item in payload.get('elements',[]):
            center = item.get('center',item)
            if 'lat' not in center or 'lon' not in center:
                continue
            tags = item.get('tags',{})
            key = next((tags.get(k) for k in ['shop','amenity','leisure'] if tags.get(k) in CATEGORIES),None)
            if not key:
                continue
            rows.append({'id':f'{item["type"]}/{item["id"]}', 'nome':clean_text(tags.get('name') or CATEGORIES[key],160),
                         'categoria':CATEGORIES[key],'latitude':center['lat'],'longitude':center['lon']})
        df = pd.DataFrame(rows,columns=COLUMNS[:-1])
        df = within_radius(df,lat,lon,radius)
        return df, 'Fonte: OpenStreetMap / Overpass. Cobertura colaborativa; pode haver ausências e duplicatas.'
    except (ExternalUnavailable,KeyError,ValueError,TypeError):
        return pd.DataFrame(columns=COLUMNS), 'Overpass indisponível. Nenhum POI foi inferido ou inventado.'
