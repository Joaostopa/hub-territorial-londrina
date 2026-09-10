"""Coleta de uma página ou importação de um arquivo; executável por cron/agendador."""
import argparse,json
from pathlib import Path
from config import CITIES
from db.models import make_engine,init_db
from db.repository import import_records
from io_utils import read_table

def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--file',help='CSV/XLSX/JSON normalizado')
    source.add_argument('--url',help='Página de resultados pública')
    p.add_argument('--portal',choices=['OLX','ImovelWeb'])
    p.add_argument('--city',choices=list(CITIES),default='Londrina')
    p.add_argument('--purpose',choices=['venda','aluguel'],default='venda')
    args=p.parse_args()
    if args.file:
        path=Path(args.file);records=read_table(path.name,path.read_bytes()).to_dict('records')
    else:
        if not args.portal:p.error('--portal obrigatório quando usar --url')
        from scrapers.olx_scraper import collect as olx
        from scrapers.imovelweb_scraper import collect as iw
        records=(olx if args.portal=='OLX' else iw)(args.url,args.city,args.purpose)
    result=import_records(init_db(make_engine()),records)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['rejeitados'] else 0
if __name__=='__main__':
    raise SystemExit(main())
