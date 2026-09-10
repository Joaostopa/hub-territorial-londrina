"""Migração não destrutiva: lê SQLite antigo em modo somente leitura e cria outro."""
import argparse
from pathlib import Path
import sqlite3
from urllib.parse import quote
import pandas as pd
from sqlalchemy import URL
from db.models import make_engine,init_db
from db.repository import import_records


def migrate(source,destination,default_city=None,default_purpose='venda'):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file():raise ValueError('O banco de origem não existe.')
    if source==destination or destination.exists():raise ValueError('O destino precisa ser um arquivo novo, diferente da origem.')
    with sqlite3.connect('file:'+quote(source.as_posix(),safe='/:')+'?mode=ro',uri=True) as conn:
        found=conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='imoveis'").fetchone()
        if not found:raise ValueError('A origem não contém a tabela imoveis.')
        frame=pd.read_sql_query('SELECT * FROM imoveis',conn)
    if 'cidade' not in frame and default_city:frame['cidade']=default_city
    if 'finalidade' not in frame:frame['finalidade']=default_purpose
    destination.parent.mkdir(parents=True,exist_ok=True)
    engine=init_db(make_engine(URL.create('sqlite',database=str(destination))))
    result=import_records(engine,frame.to_dict('records'))
    engine.dispose()
    if result['erros']:
        pd.DataFrame(result['erros']).to_csv(destination.with_suffix('.erros.csv'),index=False)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--destination',required=True)
    p.add_argument('--default-city');p.add_argument('--default-purpose',choices=['venda','aluguel'],default='venda')
    a=p.parse_args()
    try:print(migrate(a.source,a.destination,a.default_city,a.default_purpose))
    except ValueError as exc:p.error(str(exc))
