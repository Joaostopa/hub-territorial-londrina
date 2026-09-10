import json
import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from db.models import ApifyRun
from apify_service import start, sync, history
from connectors.apify import ApifyError

def render(engine, refresh):
    st.subheader('Apify — Londrina/PR')
    st.write('VivaReal + ZAP. Todas as tipologias; venda e aluguel mensal em execuções separadas.')
    st.caption('Integração preparada pelo contrato documentado do Actor. A primeira coleta autenticada ainda precisa ser validada. Coordenadas são aproximadas; contagens representam anúncios, não imóveis únicos entre portais.')
    business=st.selectbox('Finalidade no Apify',['SALE','RENTAL'],format_func=lambda x:'Venda' if x=='SALE' else 'Aluguel mensal')
    limit=st.number_input('Limite de anúncios desta coleta',1,10000,100,step=1)
    st.caption('O limite restringe a cobertura; não significa todos os anúncios de Londrina. Consulte o preço vigente no Apify antes de iniciar.')
    if st.button('Iniciar coleta no Apify (consome saldo)'):
        try:
            run_id=start(engine,business,limit)
            st.session_state['apify_run_id']=run_id
            st.success('Coleta iniciada. Use o botão abaixo para consultar e importar quando terminar.')
        except (ApifyError,SQLAlchemyError) as exc:
            st.error(str(exc) if isinstance(exc,ApifyError) else 'Não foi possível registrar a execução. Confira Runs no Apify antes de iniciar novamente.')
    run_id=st.text_input('ID da execução Apify',key='apify_run_id')
    if st.button('Consultar execução e importar resultado',disabled=not run_id):
        try:
            result=sync(engine,run_id.strip());refresh();st.write(result)
        except (ApifyError,ValueError,SQLAlchemyError) as exc:
            st.error(str(exc) if isinstance(exc,ApifyError) else 'Importação cancelada por validação ou conflito no banco; tente consultar a mesma execução novamente.')
    with engine.connect() as conn:
        runs=pd.read_sql(select(ApifyRun).order_by(ApifyRun.started_at.desc()).limit(100),conn)
    st.dataframe(runs,hide_index=True,use_container_width=True)
    with st.expander('Histórico completo do Apify e exportação'):
        records=history(engine)
        if records.empty:
            st.info('Nenhuma observação Apify importada ainda.')
        else:
            payload=pd.DataFrame([dict(json.loads(r.payload_json),run_id=r.run_id) for r in records.itertuples()])
            st.write(f'{len(payload)} observações preservadas, incluindo preços que se repetem entre coletas.')
            st.dataframe(payload,hide_index=True,use_container_width=True)
            st.download_button('Baixar histórico JSON',payload.to_json(orient='records',force_ascii=False,indent=2),'historico_apify_londrina.json','application/json')
            choices=sorted(payload.id_externo.unique())
            chosen=st.selectbox('Histórico de preço do anúncio',choices)
            chart=payload[payload.id_externo==chosen].copy()
            chart['data_coleta']=pd.to_datetime(chart.data_coleta,utc=True)
            st.line_chart(chart,x='data_coleta',y='preco',color='fonte')
    st.caption('Agendamento e backup: siga APIFY_LONDRINA.md. Anúncios ausentes não são marcados como vendidos. O histórico começa na primeira coleta importada.')
