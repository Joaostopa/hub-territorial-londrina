"""Malha oficial fornecida pelo operador em GeoJSON EPSG:4326; sem bairros sintéticos."""
import json
from normalizer import clean_text
import pandas as pd
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union
from shapely import make_valid
from config import DATA_DIR
from geoutils import local_projection, circle_geometry

GEO_DIR = DATA_DIR/'bairros'
GEO_DIR.mkdir(exist_ok=True)

def validate_geojson(payload):
    if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'),list):
        raise ValueError('Envie uma FeatureCollection GeoJSON.')
    if not payload['features'] or len(payload['features']) > 20000:
        raise ValueError('A malha deve conter entre 1 e 20.000 feições.')
    features, seen = [], set()
    for feature in payload['features']:
        props = feature.get('properties') or {}
        code = str(props.get('CD_BAIRRO') or props.get('codigo') or '')
        name = str(props.get('NM_BAIRRO') or props.get('nome') or '')
        if not code or not name or code in seen:
            raise ValueError('Cada bairro precisa de codigo/CD_BAIRRO único e nome/NM_BAIRRO.')
        geom = make_valid(shape(feature['geometry']))
        if geom.geom_type not in ('Polygon','MultiPolygon') or geom.is_empty:
            raise ValueError('A malha deve conter apenas polígonos válidos.')
        left,bottom,right,top = geom.bounds
        if left < -180 or right > 180 or bottom < -90 or top > 90:
            raise ValueError('Converta a malha para EPSG:4326 (longitude/latitude).')
        seen.add(code)
        features.append({'type':'Feature','properties':{'codigo':code,'nome':clean_text(name,160)},'geometry':mapping(geom)})
    return {'type':'FeatureCollection','features':features}

def save_mesh(code,payload,source):
    if not source.strip():
        raise ValueError('Informe a origem e o ano da malha.')
    valid = validate_geojson(payload)
    valid['metadata'] = {'fonte':source.strip()}
    (GEO_DIR/f'{code}.geojson').write_text(json.dumps(valid,ensure_ascii=False),encoding='utf-8')

def intersect_neighborhoods(code,lat,lon,radius):
    path = GEO_DIR/f'{code}.geojson'
    cols = ['codigo','bairro','fracao_area','area_intersecao_km2']
    if not path.exists():
        return pd.DataFrame(columns=cols),None,'Malha de bairros não cadastrada para este município.'
    payload = json.loads(path.read_text(encoding='utf-8'))
    forward,_ = local_projection(lat,lon)
    circle_wgs = circle_geometry(lat,lon,radius)
    circle = transform(forward,circle_wgs)
    rows, features, pieces = [],[],[]
    for feature in payload['features']:
        geom = shape(feature['geometry'])
        if not geom.intersects(circle_wgs):
            continue
        projected = transform(forward,geom)
        intersection = projected.intersection(circle)
        if intersection.area <= 1e-4 or projected.area <= 0:
            continue
        pieces.append(intersection)
        props = feature['properties']
        rows.append({'codigo':str(props['codigo']),'bairro':props['nome'],
                     'fracao_area':min(1,intersection.area/projected.area),
                     'area_intersecao_km2':intersection.area/1e6})
        features.append(feature)
    frame = pd.DataFrame(rows,columns=cols)
    union_area = unary_union(pieces).area if pieces else 0
    frame.attrs['cobertura_circulo'] = union_area/circle.area
    frame.attrs['sobreposicao'] = sum(p.area for p in pieces) - union_area > max(1,circle.area*.001)
    return frame,{'type':'FeatureCollection','features':features},payload.get('metadata',{}).get('fonte','Origem não informada')
