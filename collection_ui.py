"""UI sem rede na abertura; execução somente mediante botão do administrador."""
import pandas as pd
import streamlit as st
from sqlalchemy import select
from db.models import CollectionRun, CollectedProject
from scrapers.sources import SOURCES
from collect_batch import collect_source


def render(engine, *, demo, is_admin, refresh):
    st.title('Fontes e coletas')
    st.write('Piloto: apartamentos à venda em Londrina. Cada execução tem cobertura limitada às páginas visitadas.')
    st.info('Base inicial real de 08/09/2026: 10 anúncios da Human e 27 da Santamérica, com 9 posições utilizáveis. São observações datadas, não garantia de disponibilidade atual. OLX/ZAP/Imovelweb retornaram HTTP 403 na validação; Mônaco não permitiu este coletor em robots.txt.')
    st.dataframe(pd.DataFrame([{'Fonte':s.name,'Conteúdo':s.kind,'Página inicial':s.start_url} for s in SOURCES.values()]),hide_index=True,use_container_width=True)
    if demo:
        st.info('Desative o modo demonstração para coletar e gravar dados reais.')
    elif is_admin:
        selected=st.multiselect('Fontes desta execução',list(SOURCES),default=['santamerica','human'],format_func=lambda k:SOURCES[k].name)
        pages=st.number_input('Máximo de páginas por fonte',min_value=1,max_value=20,value=3)
        st.caption('Intervalo mínimo de 3 segundos por domínio. Sem contornar bloqueios. Anúncios sem coordenadas ficam na base, mas não entram na busca por raio.')
        if st.button('Executar coleta em Londrina',disabled=not selected):
            results=[]
            for key in selected:
                with st.spinner(f'Consultando {SOURCES[key].name}…'):
                    results.append(collect_source(engine,key,max_pages=pages))
            refresh()
            st.dataframe(pd.DataFrame(results),hide_index=True)
            st.download_button('Baixar diagnóstico JSON',pd.DataFrame(results).to_json(orient='records',force_ascii=False,indent=2),'diagnostico_coleta.json','application/json')
    else: st.info('Somente administradores podem executar a coleta.')
    if not demo and is_admin and st.button('Carregar base real verificada de 08/09/2026'):
        import json
        from pathlib import Path
        from db.repository import import_records
        rows=json.loads((Path(__file__).resolve().parent/'dados_verificados/imoveis_2026-09-08.json').read_text(encoding='utf-8'))
        status=import_records(engine,rows);refresh();st.write(status)
    if not demo and is_admin:
        from apify_ui import render as render_apify
        render_apify(engine, refresh)
    st.subheader('Últimas execuções')
    with engine.connect() as conn:
        runs=pd.read_sql(select(CollectionRun).order_by(CollectionRun.id.desc()).limit(50),conn)
        projects=pd.read_sql(select(CollectedProject).order_by(CollectedProject.observado_em.desc()).limit(100),conn)
    st.dataframe(runs,hide_index=True,use_container_width=True)
    st.caption('success: registros reconhecidos; partial: houve rejeição ou falha após gravações; network_error: conexão falhou; parse_unrecognized: formato não reconhecido. Confira também truncated e detail.')
    st.subheader('Empreendimentos coletados')
    st.write('Cadastro separado dos anúncios: sem inventar preço ou localização exata.')
    st.dataframe(projects,hide_index=True,use_container_width=True)
