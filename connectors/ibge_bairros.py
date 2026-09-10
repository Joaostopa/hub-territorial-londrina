"""Indicadores da malha cadastrada. Estimativas por área exigem cobertura completa."""
import pandas as pd
import numpy as np
from config import DATA_DIR

IND_DIR = DATA_DIR/'indicadores'
IND_DIR.mkdir(exist_ok=True)
NUMERIC = ['populacao','renda_media','populacao_anterior','pop_0_14','pop_15_64','pop_65_mais']

def save_indicators(code,df):
    required = {'codigo','ano','fonte','populacao'}
    if not required.issubset(df.columns):
        raise ValueError('Colunas obrigatórias: codigo, ano, fonte, populacao.')
    df = df.copy()
    df['codigo'] = df.codigo.astype(str).str.strip()
    if df.codigo.duplicated().any() or (df.codigo=='').any():
        raise ValueError('codigo precisa ser único e preenchido.')
    if df.fonte.isna().any() or df.fonte.astype(str).str.strip().eq('').any():
        raise ValueError('Informe a fonte de cada indicador.')
    for col in NUMERIC+['ano','ano_anterior']:
        if col not in df:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col],errors='raise')
        if (df[col].dropna() < 0).any() or np.isinf(df[col].dropna()).any():
            raise ValueError(f'{col} deve ser não negativo e finito.')
    if df.ano.isna().any() or ((df.ano % 1)!=0).any():
        raise ValueError('Informe o ano inteiro dos indicadores.')
    mask = df.ano_anterior.notna()
    if (df.loc[mask,'ano_anterior'] >= df.loc[mask,'ano']).any():
        raise ValueError('ano_anterior deve ser menor que ano.')
    ages = df[['pop_0_14','pop_15_64','pop_65_mais']]
    full = ages.notna().all(axis=1) & df.populacao.notna()
    if ((ages.sum(axis=1)-df.populacao).abs()[full] > 1).any():
        raise ValueError('A soma das faixas etárias deve corresponder à população.')
    df[['codigo','ano','fonte','ano_anterior']+NUMERIC].to_csv(IND_DIR/f'{code}.csv',index=False)

def area_demographics(code,neighborhoods,overlap=False):
    result = {'status':'indisponivel','populacao_estimada':None,'renda_media':None,
              'crescimento_pct':None,'faixas':{},'ano':None,'ano_anterior':None,
              'fontes':[], 'mensagem':'Indicadores por bairro não cadastrados.'}
    path = IND_DIR/f'{code}.csv'
    if neighborhoods.empty or not path.exists():
        return result,pd.DataFrame()
    data = pd.read_csv(path,dtype={'codigo':str})
    merged = neighborhoods.merge(data,on='codigo',how='left',validate='one_to_one')
    result['fontes'] = merged.fonte.dropna().unique().tolist()
    overlap = overlap or neighborhoods.attrs.get('sobreposicao',False)
    complete_mesh = neighborhoods.attrs.get('cobertura_circulo',0) >= .995
    if merged.populacao.isna().any() or merged.ano.nunique() != 1 or overlap or not complete_mesh:
        result['mensagem'] = 'Malha ou indicadores sem cobertura completa do círculo, anos diferentes ou polígonos sobrepostos: não foi calculado um total.'
        return result,merged
    weights = merged.populacao * merged.fracao_area
    total = float(weights.sum())
    result.update(status='estimativa',populacao_estimada=total,ano=int(merged.ano.iloc[0]),
                  mensagem='Estimativa por fração de área, assumindo distribuição uniforme dentro de cada bairro; não é contagem censitária do círculo.')
    if total > 0 and merged.renda_media.notna().all():
        result['renda_media'] = float((merged.renda_media*weights).sum()/total)
    if merged.populacao_anterior.notna().all() and merged.ano_anterior.notna().all() and merged.ano_anterior.nunique()==1:
        previous = (merged.populacao_anterior*merged.fracao_area).sum()
        if previous > 0:
            result['crescimento_pct'] = float((total/previous-1)*100)
            result['ano_anterior'] = int(merged.ano_anterior.iloc[0])
    for col,label in [('pop_0_14','0 a 14 anos'),('pop_15_64','15 a 64 anos'),('pop_65_mais','65 anos ou mais')]:
        if merged[col].notna().all():
            result['faixas'][label] = float((merged[col]*merged.fracao_area).sum())
    return result,merged
