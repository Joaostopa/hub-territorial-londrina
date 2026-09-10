"""Estatísticas de anúncios observados; não representam todo o mercado."""
from datetime import datetime, timezone
import math
import pandas as pd
from sqlalchemy import select
from db.models import Imovel
from db.repository import filter_listings
from geoutils import within_radius

def metrics(df, radius):
    prices = pd.to_numeric(df.get('preco_m2',pd.Series(dtype=float)), errors='coerce').dropna()
    prices = prices[prices > 0]
    return {'anuncios': len(df), 'com_preco_m2': len(prices),
            'mediana_m2': float(prices.median()) if len(prices) else None,
            'media_m2': float(prices.mean()) if len(prices) else None,
            'q1_m2': float(prices.quantile(.25)) if len(prices) else None,
            'q3_m2': float(prices.quantile(.75)) if len(prices) else None,
            'densidade': len(df)/(math.pi*radius**2)}

def monthly_history(engine, city, filters, area=None):
    with engine.connect() as conn:
        df = pd.read_sql(select(Imovel).where(Imovel.cidade == city),conn,parse_dates=['data_coleta'])
    if df.empty:
        return pd.DataFrame(columns=['mes','bairro','mediana_m2','anuncios'])
    df['mes'] = df.data_coleta.dt.to_period('M').astype(str)
    # One observation per source/listing/month. No carry-forward of stale ads.
    df = df.sort_values(['data_coleta','id']).drop_duplicates(['fonte','id_externo','mes'], keep='last')
    df = filter_listings(df, {**filters, 'max_age_days': 0})
    if area:
        df = within_radius(df,*area)
    df = df.dropna(subset=['preco_m2'])
    df['bairro'] = df.bairro.fillna('').replace('', 'Não informado')
    return (df.groupby(['mes','bairro']).agg(mediana_m2=('preco_m2','median'),
              anuncios=('id','count')).reset_index())

def opportunity_scores(rows):
    """Heurística relativa entre áreas comparáveis, nunca previsão de retorno."""
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result['score'] = float('nan')
    required = ['mediana_m2','crescimento_pct','renda_media','densidade']
    eligible = result[(result['anuncios'] >= 5) & (result['com_preco_m2'] >= 5)].dropna(subset=required)
    if len(eligible) < 3:
        return result
    total = pd.Series(0.0,index=eligible.index)
    for col, weight, lower_is_better in [('mediana_m2',.4,True),('crescimento_pct',.25,False),
                                        ('renda_media',.2,False),('densidade',.15,True)]:
        v = eligible[col]
        normalized = (v-v.min())/(v.max()-v.min()) if v.max() != v.min() else pd.Series(.5,index=v.index)
        total += weight*((1-normalized) if lower_is_better else normalized)
    result.loc[eligible.index,'score'] = (total*100).round(1)
    return result
