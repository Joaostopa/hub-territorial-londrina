"""Fixture inteiramente sintética, instalada somente em demo.db."""
import random
from datetime import timedelta
from sqlalchemy import select, func
from config import CITIES
from db.models import Imovel, session, utcnow
from db.repository import import_records

def seed_demo(engine):
    with session(engine) as s:
        if s.scalar(select(func.count()).select_from(Imovel)):
            return
    rng = random.Random(2704)
    rows=[]
    now = utcnow().replace(microsecond=0)
    for city,center in CITIES.items():
        for i in range(100):
            lat,lon = center['lat']+rng.uniform(-.035,.035),center['lon']+rng.uniform(-.035,.035)
            area = rng.randint(40,240)
            purpose = 'aluguel' if i%4==0 else 'venda'
            price = area*rng.uniform(25,55) if purpose=='aluguel' else area*rng.uniform(4500,13000)
            for month in range(6):
                rows.append({'fonte':'DEMONSTRAÇÃO','id_externo':f'{center["code"]}-{i}',
                             'data_coleta':(now-timedelta(days=30*month)).isoformat(),
                             'cidade':city,'bairro':f'Setor fictício {i%4+1}',
                             'titulo':f'Imóvel fictício {i+1:03d}','preco':round(price*(1-.012*month),2),
                             'area_m2':area,'quartos':rng.randint(1,4),'vagas':rng.randint(0,3),
                             'latitude':lat,'longitude':lon,'geo_precisao':'sintetica',
                             'tipo':['apartamento','casa','terreno'][i%3],'finalidade':purpose})
    import_records(engine,rows,demo=True)
