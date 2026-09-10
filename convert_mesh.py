"""Converte shapefile oficial para GeoJSON EPSG:4326. Requer requirements-geo.txt."""
import argparse,json
from pathlib import Path
from connectors.ibge_malha import validate_geojson

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',help='Arquivo .shp com .dbf/.shx/.prj na mesma pasta')
    parser.add_argument('destination',help='GeoJSON novo a criar')
    parser.add_argument('--code-column',default='CD_BAIRRO')
    parser.add_argument('--name-column',default='NM_BAIRRO')
    args=parser.parse_args()
    destination=Path(args.destination)
    if destination.exists():parser.error('O destino já existe; escolha outro nome.')
    try:import geopandas as gpd
    except ImportError:parser.error('Instale: python -m pip install -r requirements-geo.txt')
    frame=gpd.read_file(args.source)
    if frame.crs is None:parser.error('CRS ausente. Obtenha o arquivo .prj; não presumimos a projeção.')
    frame=frame[[args.code_column,args.name_column,'geometry']].rename(columns={args.code_column:'codigo',args.name_column:'nome'})
    frame['codigo']=frame.codigo.astype(str)
    payload=validate_geojson(json.loads(frame.to_crs(4326).to_json()))
    destination.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    print(f'Malha convertida: {destination}')
if __name__=='__main__':main()
