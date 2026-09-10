"""Censo 2022: indicadores municipais, sem atribuição automática ao círculo."""
import json,math
from pathlib import Path
from connectors.http import fetch,ExternalUnavailable
from connectors.ibge_censo import municipal_population

AGE_IDS='93070,93084,93085,93086,93087,93088,93089,93090,93091,93092,93093,93094,93095,93096,93097,93098,49108,49109,60040,60041,6653'
SNAPSHOT=Path(__file__).resolve().parents[1]/'dados_verificados/ibge_londrina_2022.json'

def municipal_profile(code):
    result=municipal_population(code)
    result.update(renda_media=None,renda_mediana=None,faixas_municipais=[],fontes_perfil=[],avisos=[])
    fallback=json.loads(SNAPSHOT.read_text(encoding='utf-8')) if str(code)=='4113700' else None
    if result['populacao'] is None and fallback:
        result.update(populacao=fallback['population'],status='snapshot',mensagem='Consulta validada em 08/09/2026; atualização online indisponível. Dado municipal, não do círculo.')
    income_url='https://servicodados.ibge.gov.br/api/v3/agregados/10295/periodos/2022/variaveis/13431|13534'
    try:
        rows=fetch(income_url,params={'localidades':f'N6[{code}]','classificacao':'2[6794]|86[95251]|58[95253]'},ttl=30*86400)
        values={r['id']:float(r['resultados'][0]['series'][0]['serie']['2022']) for r in rows}
        if set(values)!={'13431','13534'} or not all(math.isfinite(v) and v>=0 for v in values.values()):raise ValueError('Renda inválida')
        result.update(renda_media=values['13431'],renda_mediana=values['13534'])
    except (ExternalUnavailable,ValueError,KeyError,IndexError,TypeError):
        if fallback:
            result.update(renda_media=fallback['incomeMean'],renda_mediana=fallback['incomeMedian'])
            result['avisos'].append('Renda: consulta preservada de 08/09/2026; atualização indisponível.')
        else:result['avisos'].append('Renda municipal indisponível.')
    result['fontes_perfil'].append('https://sidra.ibge.gov.br/tabela/10295')
    age_url='https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/2022/variaveis/93'
    try:
        rows=fetch(age_url,params={'localidades':f'N6[{code}]','classificacao':f'2[6794]|287[{AGE_IDS}]|286[113635]'},ttl=30*86400)
        groups=[]
        for row in rows[0]['resultados']:
            category=next(c for c in row['classificacoes'] if str(c['id'])=='287')
            groups.append({'faixa':next(iter(category['categoria'].values())),'pessoas':int(row['series'][0]['serie']['2022'])})
        if len(groups)!=21 or any(g['pessoas']<0 for g in groups) or sum(g['pessoas'] for g in groups)!=result['populacao']:raise ValueError('Idades não reconciliadas')
        result['faixas_municipais']=groups
    except (ExternalUnavailable,ValueError,KeyError,IndexError,TypeError,StopIteration):
        if fallback:
            result['faixas_municipais']=[{'faixa':r['name'],'pessoas':r['count']} for r in fallback['ages']]
            result['avisos'].append('Idades: consulta preservada de 08/09/2026; atualização indisponível.')
        else:result['avisos'].append('Faixas etárias indisponíveis ou não reconciliadas.')
    result['fontes_perfil'].append('https://sidra.ibge.gov.br/tabela/9514')
    return result
