"""Distâncias geodésicas e interpretação defensiva do desenho Folium."""
import math
import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Point, mapping
from shapely.ops import transform

EARTH_KM = 6371.0088

def validate_area(lat, lon, radius):
    lat, lon, radius = float(lat), float(lon), float(radius)
    if not all(math.isfinite(v) for v in (lat, lon, radius)):
        raise ValueError('Centro e raio devem ser números finitos.')
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Coordenadas fora dos limites geográficos.')
    if not 0.05 <= radius <= 30:
        raise ValueError('Desenhe um raio entre 50 metros e 30 km.')
    return lat, lon, radius

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

def within_radius(df, lat, lon, radius):
    validate_area(lat, lon, radius)
    result = df.copy()
    result['distancia_km'] = haversine(lat, lon, result['latitude'].astype(float), result['longitude'].astype(float))
    return result[result['distancia_km'] <= radius + 1e-9].sort_values('distancia_km')

def local_projection(lat, lon):
    crs = CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m')
    return (Transformer.from_crs(4326, crs, always_xy=True).transform,
            Transformer.from_crs(crs, 4326, always_xy=True).transform)

def circle_geometry(lat, lon, radius):
    validate_area(lat, lon, radius)
    forward, backward = local_projection(lat, lon)
    circle = transform(forward, Point(lon, lat)).buffer(radius*1000, quad_segs=128)
    return transform(backward, circle)

def area_signature(area):
    return tuple(round(float(x), 6) for x in area) if area else None

def extract_circle(result):
    """Folium versions may return radius in properties (m) or last_circle_radius (km)."""
    if not result:
        return None
    drawing = result.get('last_active_drawing')
    if not drawing:
        return None
    geom = drawing.get('geometry') or {}
    if geom.get('type') != 'Point':
        return None
    coords = geom.get('coordinates') or []
    if len(coords) < 2:
        return None
    radius_m = (drawing.get('properties') or {}).get('radius')
    radius_km = float(radius_m)/1000 if radius_m is not None else result.get('last_circle_radius')
    if radius_km is None:
        return None
    return validate_area(coords[1], coords[0], radius_km)
