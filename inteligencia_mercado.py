"""Complemento de apresentação. Coloque ao lado de app.py. Não contém anúncios fictícios."""
from pathlib import Path
import json
import re
import unicodedata
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from sqlalchemy import select, text as sqltext
from db.models import make_engine, init_db, Imovel, ApifyRun
from db.repository import latest, import_records
from connectors.apify import ApifyError, Client, ACTOR
from apify_service import start, sync


class BudgetClient(Client):
    """Reserva conservadora: até duas execuções de US$ 4 neste complemento."""
    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def start(self, inputs):
        with self.engine.begin() as conn:
            conn.execute(sqltext('CREATE TABLE IF NOT EXISTS intel_budget (id INTEGER PRIMARY KEY, reservado INTEGER NOT NULL)'))
            conn.execute(sqltext('INSERT INTO intel_budget(id,reservado) VALUES (1,0) ON CONFLICT(id) DO NOTHING'))
            reserved=conn.execute(sqltext('UPDATE intel_budget SET reservado=reservado+4 WHERE id=1 AND reservado+4<=10 RETURNING reservado')).scalar()
            if reserved is None:
                raise ApifyError('Limite preventivo desta apresentação atingido. Consulte as execuções já iniciadas; não inicie novamente.')
        return self.request('POST', f'/acts/{ACTOR}/runs', json=inputs,
            params={'timeout':3600,'maxTotalChargeUsd':4,'restartOnError':'false'})['data']


def key(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value or '').casefold()) if unicodedata.category(c) != 'Mn').strip()


def prepare(df):
    df = df.copy()
    if df.empty:
        return df
    df['bairro_exibicao'] = df.bairro.fillna('').str.strip().replace('', 'Não informado')
    df['bairro_comparacao'] = df.bairro_exibicao.map(key)
    df['preco_m2'] = df.preco.div(df.area_m2.where(df.area_m2 > 0))
    df['tem_coordenadas'] = df.latitude.notna() & df.longitude.notna()
    df['idade_coleta_dias'] = (pd.Timestamp.now(tz='UTC').tz_localize(None)-pd.to_datetime(df.data_coleta)).dt.total_seconds().div(86400).clip(lower=0)
    return df


def summarize(df, minimum=5):
    if df.empty:
        return pd.DataFrame()
    result = df.groupby('bairro_comparacao').agg(
        bairro=('bairro_exibicao','first'), anuncios=('id','count'),
        com_area=('preco_m2','count'), preco_mediano=('preco','median'),
        mediana_m2=('preco_m2','median'), p25_m2=('preco_m2',lambda x:x.quantile(.25)),
        p75_m2=('preco_m2',lambda x:x.quantile(.75)), area_mediana=('area_m2','median'),
        com_coordenadas=('tem_coordenadas','sum')).reset_index(drop=True)
    result['amostra_suficiente'] = result.com_area >= minimum
    return result.sort_values('anuncios',ascending=False)


def money(value):
    if pd.isna(value): return '—'
    return ('R$ '+f'{value:,.0f}').replace(',','X').replace('.',',').replace('X','.')


def run():
    st.set_page_config(page_title='Hub Territorial | Inteligência de mercado',page_icon='📍',layout='wide')
    st.markdown('''<style>
    .stApp{background:#f5f8fb;color:#16334b} h1,h2,h3{color:#12344f}
    [data-testid="stMetric"]{background:white;padding:18px;border-radius:14px;border:1px solid #dce7ee}
    [data-testid="stSidebar"]{background:#edf4f7}
    .stButton>button[kind="primary"]{background:#087d80;border-color:#087d80;color:white}
    @media print {[data-testid="stSidebar"],header,.stButton{display:none!important}}
    </style>''',unsafe_allow_html=True)
    st.title('Hub Territorial')
    st.caption('Londrina · Inteligência de mercado · Preços anunciados, fontes e datas verificáveis')
    engine=init_db(make_engine())
    df=prepare(latest(engine,'Londrina'))
    if not df.empty:
        df=df[~df.is_demo].copy()
    with st.sidebar:
        st.subheader('Recorte de mercado')
        purpose=st.selectbox('Finalidade',['venda','aluguel'])
        types=sorted(df.tipo.dropna().unique()) if not df.empty else []
        selected_types=st.multiselect('Tipos',types,default=['apartamento'] if 'apartamento' in types else [])
        sources=st.multiselect('Fontes',sorted(df.fonte.unique()) if not df.empty else [])
        region=st.radio('Região',['Londrina inteira','Gleba Palhano (bairro informado)','Selecionar bairros'])
        chosen=st.multiselect('Bairros',sorted(df.bairro_exibicao.unique()) if not df.empty else [],disabled=region!='Selecionar bairros')
        days=st.number_input('Idade máxima da coleta (dias) · 0 = todas',0,3650,90)
        minimum=st.number_input('Mínimo com área para comparar bairros',3,100,5)
        if st.button('Recarregar banco'): st.rerun()
        st.caption('O recorte por bairro é textual, não um limite territorial oficial. Não presume imóveis únicos entre fontes.')
    selected=df.copy()
    if not selected.empty:
        selected=selected[selected.finalidade==purpose]
        if selected_types: selected=selected[selected.tipo.isin(selected_types)]
        if sources: selected=selected[selected.fonte.isin(sources)]
        if days: selected=selected[selected.idade_coleta_dias<=days]
        if region.startswith('Gleba'): selected=selected[selected.bairro_comparacao.str.contains('gleba palhano',regex=False)]
        if region=='Selecionar bairros': selected=selected[selected.bairro_exibicao.isin(chosen)]
    tabs=st.tabs(['Visão de mercado','Anúncios e comparação','Mapa e entorno','IBGE e território','Coletar e importar'])
    with tabs[0]:
        if selected.empty:
            st.info('Nenhum anúncio real no recorte. Ajuste os filtros ou importe uma execução em Coletar e importar.')
        else:
            c=st.columns(4)
            c[0].metric('Anúncios no recorte',len(selected))
            c[1].metric('Preço anunciado mediano',money(selected.preco.median()))
            c[2].metric('Mediana por m²',money(selected.preco_m2.median()))
            c[3].metric('Cobertura de localização',f'{selected.tem_coordenadas.mean():.0%}')
            st.caption(f'{selected.preco_m2.notna().sum()} anúncios com área para preço/m² · {selected.bairro_comparacao.nunique()} bairros informados ou não informados · {selected.fonte.nunique()} fontes. Coletas: {selected.data_coleta.min():%d/%m/%Y} a {selected.data_coleta.max():%d/%m/%Y}.')
            st.info('Anúncios sem coordenadas participam de todas as análises desta tela. Somente o mapa depende da localização. Contagens são de anúncios por fonte; não representam o estoque total de imóveis da cidade.')
            summary=summarize(selected,minimum)
            left,right=st.columns(2)
            with left:
                st.subheader('Oferta anunciada por bairro')
                st.bar_chart(summary.head(15).set_index('bairro').anuncios,color='#087d80')
            with right:
                st.subheader('Mediana de preço/m² por bairro')
                eligible=summary[summary.amostra_suficiente & (summary.bairro!='Não informado')].sort_values('mediana_m2').head(15)
                if eligible.empty: st.info('Amostra insuficiente para comparação por bairro.')
                else: st.bar_chart(eligible.set_index('bairro').mediana_m2,color='#163e60')
            if len(selected.tipo.unique())>1: st.warning('Há tipos de imóvel diferentes neste recorte. Selecione um tipo para tornar a comparação de preço/m² mais consistente.')
            left,right=st.columns(2)
            with left:
                st.subheader('Distribuição por preço')
                edges=[0,200000,350000,500000,750000,1000000,1500000,3000000,float('inf')] if purpose=='venda' else [0,1000,2000,3000,5000,8000,15000,float('inf')]
                labels=[money(a)+' a '+money(b) if b!=float('inf') else 'Acima de '+money(a) for a,b in zip(edges,edges[1:])]
                bands=pd.cut(selected.preco,edges,labels=labels,include_lowest=True)
                st.bar_chart(bands.value_counts(sort=False),color='#087d80')
            with right:
                st.subheader('Distribuição por metragem')
                bands=pd.cut(selected.area_m2,[0,50,80,120,180,250,float('inf')],labels=['Até 50','50–80','80–120','120–180','180–250','Acima de 250'],include_lowest=True)
                st.bar_chart(bands.value_counts(sort=False),color='#163e60')
                st.caption(f'{selected.area_m2.isna().sum()} anúncios sem área não entram neste gráfico. Área em m²; a definição da área pode variar entre fontes.')
            st.subheader('Quadro de comparação')
            st.dataframe(summary,hide_index=True,use_container_width=True)
            eligible=summary[summary.amostra_suficiente & (summary.bairro!='Não informado')]
            if not eligible.empty:
                top=summary.iloc[0]
                st.write(f'O maior volume observado está em **{top.bairro}**, com **{top.anuncios} anúncios** ({top.anuncios/len(selected):.1%} do recorte).')
                lo=eligible.loc[eligible.mediana_m2.idxmin()];hi=eligible.loc[eligible.mediana_m2.idxmax()]
                st.write(f'Entre bairros com pelo menos {minimum} anúncios com área, a mediana anunciada varia de **{money(lo.mediana_m2)}/m² em {lo.bairro}** a **{money(hi.mediana_m2)}/m² em {hi.bairro}**.')
            st.caption('Diferenças de padrão, idade, área privativa/total e composição da amostra influenciam as comparações. Preço menor não comprova oportunidade ou retorno financeiro.')
            st.subheader('Qualidade e procedência')
            st.dataframe(selected.groupby('fonte').agg(anuncios=('id','count'),com_area=('area_m2','count'),com_coordenadas=('tem_coordenadas','sum'),ultima_coleta=('data_coleta','max')),use_container_width=True)
    with tabs[1]:
        if not selected.empty:
            text=st.text_input('Buscar no título, bairro ou identificador')
            rows=selected.copy()
            if text:
                mask=rows[['titulo','bairro_exibicao','id_externo']].fillna('').astype(str).agg(' '.join,axis=1).map(key).str.contains(key(text),regex=False)
                rows=rows[mask]
            cols=['fonte','titulo','bairro_exibicao','tipo','preco','area_m2','preco_m2','quartos','vagas','data_coleta','geo_precisao','url']
            st.dataframe(rows[cols],hide_index=True,use_container_width=True,column_config={'url':st.column_config.LinkColumn('Abrir anúncio')})
            st.caption('Fonte e link acompanham cada registro. Esta lista inclui anúncios sem localização e não muda ao desenhar o círculo.')
            st.download_button('Exportar recorte CSV',rows[cols].to_csv(index=False,sep=';').encode('utf-8-sig'),'mercado_londrina.csv','text/csv')
            with st.expander('Observações históricas reais'):
                with engine.connect() as conn: hist=pd.read_sql(select(Imovel).where(Imovel.cidade=='Londrina',Imovel.is_demo==False),conn,parse_dates=['data_coleta'])
                ids=set(zip(selected.fonte,selected.id_externo))
                hist=hist[[tuple(x) in ids for x in zip(hist.fonte,hist.id_externo)]]
                st.write(f'{len(hist)} observações para os anúncios do recorte atual. Não há reconstrução de preços anteriores às coletas.')
                st.dataframe(hist[cols[:-1]] if all(c in hist for c in cols[:-1]) else hist,hide_index=True,use_container_width=True)
    with tabs[2]:
        import folium
        from folium.plugins import Draw,MarkerCluster
        from streamlit_folium import st_folium
        from geoutils import within_radius,extract_circle
        from connectors.pois_overpass import nearby_pois,COLUMNS
        area=st.session_state.get('intel_area',(-23.326,-51.189,2.5))
        categories=st.multiselect('O que mostrar no mapa?',['Imóveis','Restaurante','Escola','Mercado','Farmácia','Academia','Hospital'],default=['Imóveis','Restaurante','Escola'])
        st.caption('Arraste um círculo para mudar o recorte do mapa. A análise de mercado continua seguindo os filtros da barra lateral.')
        if st.button('Consultar conveniências reais deste círculo'):
            with st.spinner('Consultando OpenStreetMap…'):
                result,note=nearby_pois(*area)
                st.session_state['intel_pois']=(area,result,note)
        saved=st.session_state.get('intel_pois')
        pois=saved[1] if saved and saved[0]==area else pd.DataFrame(columns=COLUMNS)
        if saved and saved[0]==area:st.caption(saved[2])
        m=folium.Map(location=area[:2],zoom_start=13,tiles='OpenStreetMap')
        folium.Circle(area[:2],radius=area[2]*1000,color='#087d80',fill=True,fill_opacity=.08).add_to(m)
        Draw(export=False,draw_options={'circle':True,'rectangle':False,'polyline':False,'polygon':False,'marker':False,'circlemarker':False},edit_options={'edit':False,'remove':False}).add_to(m)
        geo=selected[selected.tem_coordenadas].copy() if not selected.empty else selected
        inside=within_radius(geo,*area) if not geo.empty else geo
        from html import escape
        cluster=MarkerCluster().add_to(m)
        if 'Imóveis' in categories:
            for r in inside.itertuples():
                popup=f'{escape(r.titulo)}<br>{money(r.preco)}<br>{escape(r.geo_precisao)}'
                if r.url and str(r.url).startswith(('https://','http://')):popup+=f'<br><a href="{escape(r.url,quote=True)}" target="_blank" rel="noopener">Anúncio original</a>'
                folium.Marker([r.latitude,r.longitude],popup=folium.Popup(popup,max_width=260)).add_to(cluster)
        for r in pois[pois.categoria.isin(categories)].itertuples():
            folium.CircleMarker([r.latitude,r.longitude],radius=6,color='#b5771a',fill=True,tooltip=escape(r.categoria+': '+r.nome)).add_to(m)
        event=st_folium(m,height=530,use_container_width=True,key='intel_map',returned_objects=['last_active_drawing','last_circle_radius'])
        try:new=extract_circle(event)
        except (ValueError,TypeError):new=None
        if new and any(abs(a-b)>0.00001 for a,b in zip(new,area)):
            st.session_state['intel_area']=new;st.rerun()
        st.write(f'{len(inside)} anúncios localizados no círculo · {len(selected)-len(geo)} sem coordenadas no recorte de mercado.')
        st.caption('Posições fornecidas por portais podem ser aproximadas. Não atribuímos o centro do bairro a um imóvel sem endereço confirmado. OpenStreetMap © contribuidores; conveniências dependem da cobertura colaborativa.')
    with tabs[3]:
        snapshot=Path(__file__).parent/'dados_verificados/ibge_londrina_2022.json'
        if snapshot.exists():
            ibge=json.loads(snapshot.read_text(encoding='utf-8'))
            st.subheader('Londrina — referência municipal do Censo 2022')
            c=st.columns(3);c[0].metric('População',f"{ibge['population']:,}".replace(',','.'));c[1].metric('Renda média per capita mensal',money(ibge['incomeMean']));c[2].metric('Renda mediana per capita mensal',money(ibge['incomeMedian']))
            st.warning('Indicadores do município inteiro, em valores de 2022. Não representam a renda ou população da Gleba Palhano nem do círculo selecionado.')
            st.bar_chart(pd.DataFrame(ibge['ages']).set_index('name')['count'],color='#087d80')
            st.markdown(f"[População — IBGE]({ibge['source']}) · [Rendimento — IBGE]({ibge['incomeSource']}) · [Faixa etária — IBGE](https://sidra.ibge.gov.br/tabela/9514)")
        else:st.info('Snapshot oficial não encontrado no projeto; nenhum indicador foi inventado.')
        st.write('Renda por bairro, velocidade de vendas, estoque vendido, vacância e valorização exigem bases próprias ou séries temporais. Não são calculados a partir de uma única coleta de anúncios.')
    with tabs[4]:
        from config import AUTH_REQUIRED
        if AUTH_REQUIRED:
            st.info('Para coletar em ambiente com autenticação, use o aplicativo principal, que valida o perfil administrador. Este complemento é para apresentação local.')
            return
        st.subheader('Ampliar a base real — VivaReal + ZAP')
        st.write('Londrina/PR · todas as tipologias. Teto de US$ 4 por execução e reserva preventiva de até US$ 8 em duas execuções neste complemento. Não cobre gastos feitos no Console, aplicativo principal ou agendamentos. A reserva fica mantida mesmo se a conexão cair.')
        limit=st.number_input('Máximo de anúncios por execução',1,1500,1500)
        business=st.selectbox('Finalidade da coleta',['SALE','RENTAL'])
        if st.button('Iniciar coleta paga',type='primary'):
            try:
                st.session_state['intel_run']=start(engine,business,limit,client=BudgetClient(engine))
                st.success('Execução iniciada. Consulte o mesmo ID abaixo; não clique novamente em iniciar.')
            except ApifyError as exc:st.error(str(exc))
        run_id=st.text_input('ID da execução Apify',key='intel_run')
        if st.button('Consultar e importar sem iniciar nova coleta',disabled=not run_id):
            try: st.write(sync(engine,run_id.strip()));st.info('Após importar, clique Recarregar banco na barra lateral.')
            except ApifyError as exc:st.error(str(exc))
        with engine.connect() as conn:runs=pd.read_sql(select(ApifyRun).order_by(ApifyRun.started_at.desc()).limit(50),conn)
        st.dataframe(runs,hide_index=True,use_container_width=True)
        st.subheader('Importar JSON normalizado de outra fonte')
        st.caption('Formato do projeto: fonte, id_externo, cidade, finalidade, preco, data_coleta; área e coordenadas opcionais. JSON bruto de outro Actor precisa de adaptador próprio.')
        upload=st.file_uploader('Arquivo de anúncios reais',type=['json'])
        if upload and st.button('Importar arquivo'):
            try:
                rows=json.loads(upload.getvalue())
                if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Use uma lista de até 10.000 registros.')
                if any(not r.get('data_coleta') or key(r.get('cidade'))!='londrina' for r in rows):raise ValueError('Todos os registros precisam de data_coleta e cidade Londrina.')
                st.write(import_records(engine,rows));st.info('Clique Recarregar banco.')
            except (ValueError,TypeError,AttributeError) as exc:st.error(str(exc))
        st.caption('A importação não verifica sozinha a autenticidade do arquivo: confira os links originais. Nenhuma coleta Apify foi executada pelo autor deste complemento na sua conta.')

if __name__=='__main__': run()
