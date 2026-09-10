"""Regenera o PDF de exemplo usando exclusivamente demo.db e anúncios fictícios."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from config import DEMO_DATABASE_URL
from db.models import make_engine,init_db
from demo import seed_demo
from db.repository import latest,filter_listings,competitors
from geoutils import within_radius
from analytics import monthly_history
from pdf_report import build_pdf

def main():
    engine=init_db(make_engine(DEMO_DATABASE_URL));seed_demo(engine)
    area=(-23.3045,-51.1696,3.3)
    filters={'finalidade':'venda','max_age_days':90}
    df=within_radius(filter_listings(latest(engine,'Londrina'),filters),*area)
    pdf=build_pdf('Londrina',area,df,filters,pd.DataFrame(),
                 {'mensagem':'Indicadores de bairros não cadastrados neste exemplo. Nenhuma população foi estimada.','fontes':[]},
                 {'populacao':None,'ano':2022,'fonte':'IBGE - consulta desativada neste exemplo'},
                 pd.DataFrame(),'Consulta desativada no modo demonstração.',monthly_history(engine,'Londrina',filters,area),
                 competitors(engine,'Londrina'),demo=True,mesh_source='Não cadastrada neste exemplo')
    path=Path(__file__).parent/'relatorio_demonstracao.pdf';path.write_bytes(pdf)
    print(f'{path.name}: {len(df)} anúncios fictícios, {len(pdf)} bytes.')
if __name__=='__main__':main()
