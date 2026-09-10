from connectors.http import fetch, ExternalUnavailable

def municipal_population(code):
    """SIDRA 4714, variável 93, Censo 2022; contexto municipal, nunca do círculo."""
    url = 'https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022/variaveis/93'
    try:
        payload = fetch(url,params={'localidades':f'N6[{code}]'},ttl=30*86400)
        raw = payload[0]['resultados'][0]['series'][0]['serie']['2022']
        population = int(raw)
        if population <= 0:
            raise ValueError('População inválida')
        return {'status':'ok','populacao':population,'ano':2022,'escopo':'município',
                'fonte':url,'mensagem':'População do município inteiro; não corresponde à área desenhada.'}
    except (ExternalUnavailable,KeyError,IndexError,ValueError,TypeError) as exc:
        return {'status':'indisponivel','populacao':None,'ano':2022,'escopo':'município',
                'fonte':url,'mensagem':'Não foi possível consultar o Censo 2022. Tente novamente mais tarde.'}
