"""Hub de Inteligência Territorial - execute com: python -m streamlit run app.py"""
from pathlib import Path
import hashlib
import json
import logging
import math
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
from config import CITIES, DATA_DIR, DATABASE_URL, DEMO_DATABASE_URL, AUTH_REQUIRED, ALLOWED_EMAILS, ADMIN_EMAILS
from db.models import make_engine, init_db, SchemaMismatch
from db.repository import (latest, filter_listings, import_records, favorites, save_favorite,
                           delete_favorite, competitors, save_competitor, delete_competitor,
                           record_report, report_history)
from geoutils import within_radius, extract_circle, area_signature
from analytics import metrics, monthly_history, opportunity_scores
from connectors.ibge_perfil import municipal_profile
from connectors.ibge_malha import intersect_neighborhoods, save_mesh
from connectors.ibge_bairros import area_demographics, save_indicators
from connectors.pois_overpass import nearby_pois, COLUMNS as POI_COLUMNS
from connectors.geocoding import search_address
from connectors.http import ExternalUnavailable
from io_utils import csv_bytes, excel_bytes, read_table
from pdf_report import build_pdf, fmt
from map_ui import build_map
from alerts import enable_alert, disable_alert, check_alerts, events_for

st.set_page_config(page_title='Hub Territorial | Inteligência Imobiliária',page_icon='◎',layout='wide')
st.markdown('''<style>
.stApp {background:#f4f7fa;}
[data-testid="stSidebar"] {background:#fff;border-right:1px solid #dce5eb;}
h1,h2,h3 {color:#123f50;letter-spacing:-.025em;}
[data-testid="stMetric"] {background:#fff;border:1px solid #dce5eb;border-radius:10px;padding:16px;}
[data-testid="stMetricValue"] {color:#123f50;}
.block-container {padding-top:2rem;max-width:1640px;}
</style>''',unsafe_allow_html=True)
logging.basicConfig(level=logging.INFO)
logger=logging.getLogger('hub')


def identity():
    if not AUTH_REQUIRED:
        return 'local',True
    if not st.user.is_logged_in:
        st.title('Hub Territorial')
        st.write('Entre com sua conta autorizada.')
        if st.button('Entrar',type='primary'):
            try: st.login()
            except Exception:
                st.error('Configure o provedor OIDC em .streamlit/secrets.toml. Consulte o README.')
        st.stop()
    email=str(st.user.get('email','')).lower()
    if not ALLOWED_EMAILS or email not in ALLOWED_EMAILS:
        st.error('Esta conta não está na lista de usuários autorizados.')
        if st.button('Sair'):st.logout()
        st.stop()
    subject=str(st.user.get('sub',''))
    issuer=str(st.user.get('iss',''))
    if not subject:
        st.error('O provedor não retornou um identificador de usuário (sub).');st.stop()
    return hashlib.sha256(f'{issuer}|{subject}'.encode()).hexdigest(),email in ADMIN_EMAILS

owner,is_admin=identity()

@st.cache_resource
def database(demo):
    engine=init_db(make_engine(DEMO_DATABASE_URL if demo else None))
    if demo:
        from demo import seed_demo
        seed_demo(engine)
    return engine

@st.cache_data(ttl=300)
def load_listings(demo,city,revision):
    return latest(database(demo),city)

@st.cache_data(ttl=3600)
def load_pois(area):
    return nearby_pois(*area)

@st.cache_data(ttl=86400)
def load_population(code):
    return municipal_profile(code)


def reset_map():
    st.session_state['map_epoch']=st.session_state.get('map_epoch',0)+1
    st.session_state.pop('pdf_ready',None)


def refresh_data():
    st.session_state['revision']=st.session_state.get('revision',0)+1
    reset_map()


def load_area_later(item):
    st.session_state['pending_area']=item
    st.session_state['navigation']='Explorar mapa'

pending=st.session_state.pop('pending_area',None)
if pending:
    st.session_state['city']=pending['cidade']
    st.session_state['area']=(pending['latitude'],pending['longitude'],pending['raio_km'])
    st.session_state['map_center']=st.session_state['area'][:2]
    for key,value in json.loads(pending['filtros_json']).items():
        st.session_state['f_'+key]=value
    reset_map()

with st.sidebar:
    st.markdown('### ◎ Hub Territorial')
    st.caption('Inteligência de mercado imobiliário')
    demo=st.toggle('Modo demonstração',value=False,key='demo')
    mode_city_before=(demo,st.session_state.get('city','Londrina'))
    if st.session_state.get('last_mode') != demo:
        st.session_state['area']=None
        st.session_state.pop('map_center',None)
        for key in list(st.session_state):
            if key.startswith('f_') or key=='online':st.session_state.pop(key,None)
        st.session_state['last_mode']=demo
        reset_map()
    city=st.selectbox('Município',list(CITIES),key='city')
    if st.session_state.get('last_city') != city:
        if not pending:
            st.session_state['area']=None
            st.session_state.pop('map_center',None)
        st.session_state.pop('address_results',None)
        st.session_state['last_city']=city
        reset_map()
    navigation=st.radio('Navegação',['Explorar mapa','Comparar áreas','Áreas e alertas','Dados e coleta','Fontes e coletas','Concorrência','Relatórios'],key='navigation')
    st.divider()
    st.markdown('**Filtros dos anúncios**')
    purpose=st.selectbox('Finalidade',['venda','aluguel'],key='f_finalidade')
    try:
        engine=database(demo)
        all_city=load_listings(demo,city,st.session_state.get('revision',0))
    except SchemaMismatch as exc:
        st.error(str(exc));st.stop()
    except Exception:
        logger.exception('Falha ao inicializar banco')
        st.error('Não foi possível abrir o banco. Confira DATABASE_URL, permissões de escrita e o terminal.');st.stop()
    available_types=sorted(all_city.tipo.dropna().unique().tolist())
    available_sources=sorted(all_city.fonte.dropna().unique().tolist())
    for key,options in [('f_tipos',available_types),('f_fontes',available_sources)]:
        if key in st.session_state:
            st.session_state[key]=[x for x in st.session_state[key] if x in options]
    types=st.multiselect('Tipo de imóvel',available_types,key='f_tipos',placeholder='Todos')
    sources=st.multiselect('Fonte',available_sources,key='f_fontes',placeholder='Todas')
    min_price=st.number_input('Preço mínimo (R$)',min_value=0.0,step=50000.0,key='f_preco_min')
    max_price=st.number_input('Preço máximo (R$) · 0 = sem limite',min_value=0.0,step=50000.0,key='f_preco_max')
    min_area=st.number_input('Área mínima (m²)',min_value=0.0,step=10.0,key='f_area_min')
    rooms=st.number_input('Quartos mínimos',min_value=0,max_value=30,step=1,key='f_quartos_min')
    age=st.number_input('Coleta nos últimos dias · 0 = todo histórico',min_value=0,max_value=3650,value=90,key='f_max_age_days')
    online=st.toggle('Consultar IBGE e POIs online',value=not demo,key='online')
    if st.button('Atualizar dados',use_container_width=True):
        refresh_data();st.rerun()
    st.caption('Anúncios coletados; cobertura do mercado não é exaustiva.')
    if AUTH_REQUIRED:
        if st.button('Sair da conta'):st.logout()
    else:
        st.caption('Sessão local. Para uso em equipe, configure login no README.')

filters={'finalidade':purpose,'tipos':types,'fontes':sources,'preco_min':min_price,'preco_max':max_price,
         'area_min':min_area,'quartos_min':rooms,'max_age_days':age}
if max_price and max_price<min_price:
    st.error('O preço máximo deve ser maior ou igual ao mínimo.');st.stop()
base=filter_listings(all_city,filters)
city_meta=CITIES[city]
favs=favorites(engine,owner)
area=st.session_state.get('area')
if demo:
    st.warning('DEMONSTRAÇÃO — anúncios, bairros dos anúncios e preços são fictícios. Banco separado dos dados reais.')


def get_area_context(selected_city,selected_area,fetch_external=True):
    code=CITIES[selected_city]['code']
    if demo:
        neighborhoods=pd.DataFrame(columns=['codigo','bairro','fracao_area','area_intersecao_km2'])
        geo=None;mesh_note='Malha real não usada no modo demonstração.'
    else:
        neighborhoods,geo,mesh_note=intersect_neighborhoods(code,*selected_area)
    demographics,details=area_demographics(code,neighborhoods)
    if fetch_external and online:
        population=load_population(code)
        pois,poi_note=load_pois(tuple(selected_area))
    else:
        population={'populacao':None,'ano':2022,'fonte':'https://servicodados.ibge.gov.br/api/docs/agregados',
                    'mensagem':'Consulta online desativada.','status':'nao_consultado'}
        pois=pd.DataFrame(columns=POI_COLUMNS);poi_note='Consulta de POIs desativada.'
    rivals=within_radius(competitors(engine,selected_city),*selected_area)
    return neighborhoods,geo,mesh_note,demographics,details,population,pois,poi_note,rivals


def show_metrics(frame,selected_area):
    summary=metrics(frame,selected_area[2])
    cols=st.columns(4)
    cols[0].metric('Anúncios na área',fmt(summary['anuncios']))
    cols[1].metric('Mediana · R$/m²',fmt(summary['mediana_m2'],2))
    cols[2].metric('Raio selecionado',fmt(selected_area[2],2)+' km')
    cols[3].metric('Área de análise',fmt(math.pi*selected_area[2]**2,2)+' km²')
    return summary

if navigation=='Explorar mapa':
    st.title('Explore o território')
    st.write(f'**{city} · {city_meta["state"]}** — use o círculo no mapa, clique e arraste para definir a área.')
    with st.expander('Localizar endereço ou abrir área salva'):
        with st.form('address_form'):
            query=st.text_input('Endereço, bairro ou ponto de referência',placeholder=f'Ex.: Avenida Higienópolis, {city}')
            submitted=st.form_submit_button('Localizar no mapa')
        if submitted:
            try:
                st.session_state['address_results']=search_address(query+', '+city)
            except (ExternalUnavailable,ValueError):
                st.warning('Não foi possível localizar. Navegue pelo mapa ou tente um endereço mais específico.')
        options=st.session_state.get('address_results',[])
        if options:
            chosen=st.selectbox('Resultados',range(len(options)),format_func=lambda i:options[i]['label'])
            if st.button('Centralizar neste local'):
                st.session_state['map_center']=(options[chosen]['lat'],options[chosen]['lon'])
                st.session_state['area']=None;reset_map();st.rerun()
        here=[r for r in favs if r['cidade']==city]
        if here:
            favorite=st.selectbox('Área salva',here,format_func=lambda r:r['nome'])
            st.button('Abrir área salva',on_click=load_area_later,args=(favorite,))
    selection=within_radius(base,*area) if area else base.iloc[0:0].copy()
    neighborhoods=pd.DataFrame();geo=None;mesh_note=''
    demographics={};details=pd.DataFrame();population={};pois=pd.DataFrame(columns=POI_COLUMNS)
    poi_note='';rivals=competitors(engine,city).iloc[0:0]
    if area:
        with st.spinner('Analisando a área selecionada…'):
            neighborhoods,geo,mesh_note,demographics,details,population,pois,poi_note,rivals=get_area_context(city,area)
        show_metrics(selection,area)
        action_col,info_col=st.columns([1,3])
        generate_pdf=action_col.button('Gerar PDF desta área',type='primary',use_container_width=True)
        info_col.caption(f'Centro: {area[0]:.6f}, {area[1]:.6f} · {len(selection.preco_m2.dropna())} anúncios com preço/m². '
                         'Use o lápis para editar ou desenhe outro círculo.')
    else:
        generate_pdf=False
        st.info('Desenhe o primeiro círculo para consultar anúncios, bairros e conveniências.')
    center=st.session_state.get('map_center',area[:2] if area else (city_meta['lat'],city_meta['lon']))
    m=build_map(center,area,selection,pois,rivals,geo)
    result=st_folium(m,use_container_width=True,height=540,key=f'map_{demo}_{city}_{st.session_state.get("map_epoch",0)}',
                     returned_objects=['last_active_drawing','last_circle_radius','all_drawings'])
    # None means no drawing event; [] is an explicit empty edit group after deletion.
    if result and result.get('all_drawings')==[] and area:
        st.session_state['area']=None;reset_map();st.rerun()
    try:
        new_area=extract_circle(result)
        if new_area and area_signature(new_area)!=area_signature(area):
            st.session_state['area']=new_area
            st.session_state['map_center']=new_area[:2]
            reset_map();st.rerun()
    except (ValueError,TypeError,OverflowError) as exc:
        st.warning(str(exc))
    if not area:
        if all_city.empty:
            st.write('Seu banco está pronto, mas ainda não há anúncios. Abra **Dados e coleta** para importar uma base ou ative **Modo demonstração**.')
        st.stop()
    if st.button('Limpar área'):
        st.session_state['area']=None;reset_map();st.rerun()
    if selection.empty:
        st.info('Nenhum anúncio geolocalizado atende aos filtros nesta área. Amplie o raio, ajuste os filtros ou importe mais dados.')
    tabs=st.tabs(['Anúncios','Bairros e população','Conveniências','Histórico de preços'])
    with tabs[0]:
        st.caption('Última observação por fonte e identificador. Um imóvel anunciado em dois portais pode aparecer duas vezes. Venda e aluguel não são misturados.')
        columns=['fonte','id_externo','bairro','tipo','preco','area_m2','preco_m2','quartos','distancia_km','data_coleta','geo_precisao','url']
        st.dataframe(selection.reindex(columns=columns),hide_index=True,use_container_width=True,
                     column_config={'url':st.column_config.LinkColumn('Anúncio'),'preco':st.column_config.NumberColumn('Preço (R$)',format='%.2f'),
                                    'preco_m2':st.column_config.NumberColumn('R$/m²',format='%.2f')})
        a,b=st.columns(2)
        a.download_button('Exportar CSV',csv_bytes(selection),'imoveis_area.csv','text/csv',use_container_width=True)
        b.download_button('Exportar Excel',excel_bytes({'Imoveis':selection,'Filtros':pd.DataFrame([filters]),'Area':pd.DataFrame([{'latitude':area[0],'longitude':area[1],'raio_km':area[2],'cidade':city,'demonstracao':demo}])}),
                          'imoveis_area.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
        with st.form('save_area'):
            name=st.text_input('Nome da área',placeholder='Ex.: Terreno Higienópolis · raio de 2 km',max_chars=120)
            save=st.form_submit_button('Salvar área e filtros')
        if save:
            try:
                save_favorite(engine,owner,name,city,area,filters);st.success('Área salva. Abra Áreas e alertas para gerenciá-la.')
            except ValueError as exc:st.warning(str(exc))
    with tabs[1]:
        st.caption('Interseção geométrica com a malha cadastrada; o bairro textual do anúncio não substitui um polígono.')
        if neighborhoods.empty:st.info(mesh_note)
        else:
            display=neighborhoods.copy();display['cobertura_bairro_pct']=display.fracao_area*100
            st.dataframe(display.drop(columns='fracao_area'),hide_index=True,use_container_width=True)
            st.caption('Fonte da malha: '+mesh_note)
        st.write(demographics.get('mensagem',''))
        if demographics.get('populacao_estimada') is not None:
            a,b=st.columns(2)
            a.metric('População estimada na área',fmt(demographics['populacao_estimada']))
            b.metric('Renda média estimada (R$)',fmt(demographics['renda_media'],2))
            st.caption(f'Ano: {demographics["ano"]} · '+ '; '.join(demographics['fontes']))
            if demographics.get('faixas'):
                st.bar_chart(pd.Series(demographics['faixas'],name='Pessoas estimadas'))
        if not details.empty:
            with st.expander('Dados usados na estimativa'):st.dataframe(details,hide_index=True)
        st.markdown('**Contexto municipal — fora do cálculo do raio**')
        st.metric('População municipal · Censo 2022',fmt(population.get('populacao')))
        st.caption(population.get('mensagem',''))
        a,b=st.columns(2)
        a.metric('Renda média mensal per capita · município',fmt(population.get('renda_media'),2))
        b.metric('Renda mediana mensal per capita · município',fmt(population.get('renda_mediana'),2))
        st.caption('Rendimento domiciliar per capita nominal de 2022 (R$), tabela 10295. Não é renda estimada no círculo.')
        if population.get('faixas_municipais'):
            st.dataframe(pd.DataFrame(population['faixas_municipais']),hide_index=True,use_container_width=True)
            st.caption('População por idade do município inteiro — tabela 9514, Censo 2022.')
        for note in population.get('avisos',[]):st.caption(note)
        for source_url in population.get('fontes_perfil',[]):st.markdown(f'[Fonte oficial IBGE]({source_url})')

    with tabs[2]:
        st.caption(poi_note)
        if not pois.empty:
            st.bar_chart(pois.groupby('categoria').size().rename('Locais'))
            st.dataframe(pois[['nome','categoria','distancia_km']],hide_index=True,use_container_width=True)
        st.markdown('**Concorrência cadastrada na área**')
        st.dataframe(rivals,hide_index=True,use_container_width=True)
    history=monthly_history(engine,city,filters,area)
    with tabs[3]:
        st.caption('Um registro por anúncio e mês, agrupado pelo bairro informado no anúncio. Meses sem observações ficam sem valor. A mudança de composição afeta as medianas.')
        if history.empty:st.info('Não há observações com preço/m² válido para montar o histórico.')
        else:
            pivot=history.pivot(index='mes',columns='bairro',values='mediana_m2')
            st.line_chart(pivot)
            st.dataframe(history,hide_index=True,use_container_width=True)
    report_key=hashlib.sha256(json.dumps([demo,city,area,filters,st.session_state.get('revision',0),online],sort_keys=True).encode()).hexdigest()
    if generate_pdf:
        with st.spinner('Gerando relatório completo…'):
            content=build_pdf(city,area,selection,filters,neighborhoods,demographics,population,pois,poi_note,
                              history,rivals,demo=demo,neighborhood_geo=geo,mesh_source=mesh_note)
            st.session_state['pdf_ready']=(report_key,content)
            record_report(engine,owner,city,area,filters,len(selection))
    ready=st.session_state.get('pdf_ready')
    if ready and ready[0]==report_key:
        st.download_button('Baixar PDF desta área',ready[1],f'relatorio_{city.lower().replace(" ","_")}.pdf','application/pdf',type='primary')

elif navigation=='Comparar áreas':
    st.title('Compare áreas de interesse')
    st.write('Selecione duas ou três áreas salvas. Os filtros atuais são aplicados igualmente a todas elas.')
    chosen=st.multiselect('Áreas',favs,format_func=lambda r:f'{r["nome"]} · {r["cidade"]}',max_selections=3)
    if len(chosen)<2:
        st.info('Salve áreas no mapa e escolha pelo menos duas para comparar.');st.stop()
    rows=[];demo_periods=[]
    for item in chosen:
        ar=(item['latitude'],item['longitude'],item['raio_km'])
        df=within_radius(filter_listings(load_listings(demo,item['cidade'],st.session_state.get('revision',0)),filters),*ar)
        n,g,note,d,details,p,pois,pnote,rivals=get_area_context(item['cidade'],ar,fetch_external=False)
        demo_periods.append((d.get('ano'),d.get('ano_anterior')))
        rows.append({'area':item['nome'],'cidade':item['cidade'],**metrics(df,ar[2]),
                     'renda_media':d.get('renda_media'),'crescimento_pct':d.get('crescimento_pct'),
                     'ano':d.get('ano'),'ano_anterior':d.get('ano_anterior')})
    result=opportunity_scores(rows)
    # Growth/renda from different periods are not comparable.
    if len(set(demo_periods))!=1:result['score']=float('nan')
    for column,row in zip(st.columns(len(rows)),rows):
        with column:
            st.subheader(row['area']);st.caption(row['cidade'])
            st.metric('Anúncios',fmt(row['anuncios']))
            st.metric('Mediana · R$/m²',fmt(row['mediana_m2'],2))
            st.metric('Anúncios por km²',fmt(row['densidade'],1))
            st.metric('Renda média estimada (R$)',fmt(row['renda_media'],2))
    st.dataframe(result,hide_index=True,use_container_width=True)
    st.download_button('Exportar comparação',excel_bytes({'Comparacao':result,'Filtros':pd.DataFrame([filters])}),'comparacao.xlsx')
    st.markdown('**Score exploratório — 0 a 100**')
    st.write('40% preço/m² menor + 25% crescimento populacional maior + 20% renda maior + 15% densidade menor de anúncios. '
             'Normalização mínimo/máximo entre as áreas elegíveis; indicador constante recebe 50 pontos. '
             'Exige três áreas com ao menos cinco anúncios cada, dados completos e períodos demográficos iguais.')
    st.caption('O score depende das áreas escolhidas e da cobertura da coleta. Não é avaliação imobiliária nem previsão de retorno. '
               'Estoque observado baixo pode significar coleta incompleta. A regra pressupõe maior renda como público-alvo; não serve a todo produto.')

elif navigation=='Áreas e alertas':
    st.title('Áreas e alertas')
    st.caption('Alertas ficam registrados aqui. Para execução periódica, agende alerts.py conforme o README. A primeira checagem cria a referência.')
    if not favs:st.info('Nenhuma área salva. Desenhe uma área e dê um nome na aba Anúncios.')
    for item in favs:
        with st.expander(f'{item["nome"]} · {item["cidade"]} · {item["raio_km"]:.2f} km'):
            st.write('Filtros salvos:',json.loads(item['filtros_json']))
            st.button('Abrir no mapa',key=f'open_{item["id"]}',on_click=load_area_later,args=(item,))
            threshold=st.number_input('Alertar variação da mediana a partir de (%)',min_value=1.0,max_value=100.0,value=10.0,key=f'limit_{item["id"]}')
            a,b=st.columns(2)
            if a.button('Ativar / atualizar alerta',key=f'activate_{item["id"]}'):
                enable_alert(engine,owner,item['id'],threshold);st.success('Alerta ativo. Use Verificar agora para criar/atualizar a referência.')
            if b.button('Desativar alerta',key=f'disable_{item["id"]}'):
                disable_alert(engine,owner,item['id']);st.success('Alerta desativado.')
            confirm=st.checkbox('Confirmo excluir esta área e seus alertas',key=f'confirm_{item["id"]}')
            if st.button('Excluir área',key=f'del_{item["id"]}',disabled=not confirm):
                delete_favorite(engine,owner,item['id']);st.rerun()
    if st.button('Verificar alertas agora',type='primary'):
        events=check_alerts(engine,owner);st.success(f'Checagem concluída: {len(events)} novo(s) evento(s).')
    st.dataframe(events_for(engine,owner)[['criado_em','mensagem']],hide_index=True,use_container_width=True)
    with st.expander('Receber por e-mail ou WhatsApp'):
        from notifications import save_target,remove_target,targets
        st.caption('Os envios exigem credenciais configuradas no servidor e execução de alerts.py --notify. '
                   'No WhatsApp, use um template aprovado com uma variável no corpo. Não há envio ao salvar.')
        st.dataframe(pd.DataFrame(targets(engine,owner)),hide_index=True)
        with st.form('notification_target'):
            channel=st.selectbox('Canal',['email','whatsapp'])
            destination=st.text_input('Seu e-mail ou telefone com país e DDD')
            opt_in=st.checkbox('Quero receber os alertas neste destino e confirmo que ele me pertence')
            submit=st.form_submit_button('Salvar preferência')
        if submit:
            try:
                if not opt_in:raise ValueError('Confirme que deseja receber os alertas.')
                if AUTH_REQUIRED and channel=='email' and destination.strip().lower()!=str(st.user.get('email','')).lower():
                    raise ValueError('Use o e-mail da conta autenticada.')
                save_target(engine,owner,channel,destination);st.success('Preferência salva. Configure o agendamento para ativar a entrega.')
            except ValueError as exc:st.warning(str(exc))
        remove_channel=st.selectbox('Canal para cancelar',['email','whatsapp'],key='remove_channel')
        if st.button('Cancelar recebimento neste canal'):
            remove_target(engine,owner,remove_channel);st.rerun()


elif navigation=='Fontes e coletas':
    from collection_ui import render
    render(engine,demo=demo,is_admin=is_admin,refresh=refresh_data)

elif navigation=='Dados e coleta':
    st.title('Dados e coleta')
    st.write('Importe anúncios normalizados, cadastre malha/indicadores ou execute uma coleta assistida.')
    geolocated=int(all_city[['latitude','longitude']].notna().all(axis=1).sum())
    a,b,c=st.columns(3)
    a.metric('Anúncios mais recentes',len(all_city));b.metric('Com coordenadas',geolocated);c.metric('Sem coordenadas',len(all_city)-geolocated)
    st.caption('Sem coordenadas, o anúncio é armazenado no histórico, mas não participa de buscas por raio. Não usamos o centro do bairro como localização do imóvel.')
    if not is_admin:st.info('Importação e edição de dados disponíveis apenas para administradores.');st.stop()
    tabs=st.tabs(['Importar anúncios','Malha e indicadores','Coleta assistida','Diagnóstico'])
    with tabs[0]:
        st.write('Campos obrigatórios: fonte, id_externo, cidade, finalidade e preco. Para aparecer no mapa: latitude e longitude.')
        st.caption('Preço/m² é calculado a partir de preco / area_m2. data_coleta aceita ISO 8601; vazia recebe o instante da importação em UTC.')
        sample=Path(__file__).parent/'exemplos'/'modelo_imoveis.csv'
        if sample.exists():st.download_button('Baixar modelo CSV (somente cabeçalho)',sample.read_bytes(),'modelo_imoveis.csv','text/csv')
        upload=st.file_uploader('CSV, XLSX ou JSON normalizado',type=['csv','xlsx','json'],key='listings_upload')
        if upload:
            try:
                frame=read_table(upload.name,upload.getvalue())
                st.dataframe(frame.head(15),hide_index=True)
                st.caption(f'{len(frame)} registros. Colunas pessoais não fazem parte do esquema e não serão persistidas.')
                if st.button('Importar registros',type='primary'):
                    result=import_records(engine,frame.to_dict('records'),demo=demo)
                    refresh_data();st.success(f'{result["inseridos"]} inseridos · {result["duplicados"]} duplicados · {result["rejeitados"]} rejeitados.')
                    if result['erros']:
                        errors=pd.DataFrame(result['erros']);st.dataframe(errors,hide_index=True)
                        st.download_button('Baixar erros de validação',csv_bytes(errors),'erros_importacao.csv')
            except Exception as exc:
                logger.exception('Falha de importação');st.error(f'Arquivo não importado: {exc}')
    with tabs[1]:
        if demo:st.info('Saia do modo demonstração para cadastrar arquivos territoriais reais.')
        else:
            st.write(f'Arquivos vinculados a **{city} · IBGE {city_meta["code"]}**.')
            st.caption('GeoJSON EPSG:4326; propriedades codigo/nome ou CD_BAIRRO/NM_BAIRRO. '
                       'Use uma malha oficial de bairros. Setores censitários e limites municipais não são equivalentes.')
            with st.form('mesh_upload'):
                mesh=st.file_uploader('Malha de bairros GeoJSON',type=['geojson','json'])
                source=st.text_input('Fonte, ano e endereço de origem da malha')
                replace=st.checkbox('Confirmo cadastrar/substituir a malha deste município')
                save=st.form_submit_button('Salvar malha')
            if save:
                try:
                    if not mesh or not replace:raise ValueError('Selecione o arquivo e confirme o cadastro.')
                    if mesh.size>25_000_000:raise ValueError('Limite de 25 MB.')
                    save_mesh(city_meta['code'],json.loads(mesh.getvalue()),source);refresh_data();st.success('Malha cadastrada.')
                except (ValueError,KeyError,TypeError) as exc:st.error(str(exc))
            st.divider()
            template=Path(__file__).parent/'exemplos'/'modelo_indicadores.csv'
            if template.exists():st.download_button('Modelo dos indicadores',template.read_bytes(),'modelo_indicadores.csv')
            st.caption('Indicadores devem usar os mesmos códigos da malha e a mesma definição de renda. '
                       'As faixas etárias são opcionais, mas precisam somar a população quando todas forem informadas.')
            with st.form('indicators_upload'):
                indicator_file=st.file_uploader('Indicadores por bairro',type=['csv','xlsx'])
                replace=st.checkbox('Confirmo cadastrar/substituir os indicadores deste município')
                save=st.form_submit_button('Salvar indicadores')
            if save:
                try:
                    if not indicator_file or not replace:raise ValueError('Selecione o arquivo e confirme o cadastro.')
                    frame=read_table(indicator_file.name,indicator_file.getvalue())
                    save_indicators(city_meta['code'],frame);refresh_data();st.success('Indicadores cadastrados.')
                except (ValueError,KeyError,TypeError) as exc:st.error(str(exc))
    with tabs[2]:
        st.warning('Adaptadores de portal precisam de validação com páginas reais atuais. Não garantem cobertura total. '
                   'Não contornam login, CAPTCHA ou bloqueios; nesses casos, use CSV/JSON autorizado.')
        portal=st.selectbox('Portal',['OLX','ImovelWeb','VivaReal','ZAP'])
        st.caption(f'Cidade atribuída: {city} · Finalidade atribuída: {purpose}. Use uma página/arquivo que corresponda a esses filtros.')
        if portal in ['OLX','ImovelWeb']:
            url=st.text_input('URL HTTPS da página de resultados')
            if st.button('Coletar esta página'):
                try:
                    from scrapers.olx_scraper import collect as olx_collect
                    from scrapers.imovelweb_scraper import collect as iw_collect
                    with st.spinner('Consultando o portal…'):
                        records=(olx_collect if portal=='OLX' else iw_collect)(url,city,purpose)
                        status=import_records(engine,records,demo=demo)
                    refresh_data();st.write(status)
                except Exception as exc:st.error(f'Coleta não concluída: {exc}')
        else:
            st.info('Importe uma resposta JSON obtida de forma autorizada. O endpoint automático não foi fornecido nem validado.')
            payload=st.file_uploader('JSON de anúncios VivaReal/ZAP',type=['json'],key='portal_json')
            if payload and st.button('Importar JSON do portal'):
                try:
                    from scrapers.vivareal_zap_scraper import parse_payload
                    records=parse_payload(json.loads(payload.getvalue()),city,purpose,portal)
                    st.write(import_records(engine,records,demo=demo));refresh_data()
                except Exception as exc:st.error(str(exc))
    with tabs[3]:
        from sqlalchemy import inspect
        st.write('Tipo de banco:',engine.dialect.name)
        if engine.dialect.name=='sqlite':st.code(str(engine.url.database))
        st.write('Tabelas:',inspect(engine).get_table_names())
        st.caption('Banco inicializado automaticamente; nenhuma tabela existente é apagada. '
                   'Banco antigo incompatível deve ser migrado pelo script migrate_legacy.py após backup.')
        if not all_city.empty:
            st.write('Última coleta:',str(all_city.data_coleta.max()))
            st.dataframe(all_city.groupby('fonte').agg(anuncios=('id','count'),ultima_coleta=('data_coleta','max')).reset_index(),hide_index=True)

elif navigation=='Concorrência':
    st.title('Concorrência no território')
    frame=competitors(engine,city)
    st.dataframe(frame,hide_index=True,use_container_width=True)
    if not is_admin:st.info('Cadastro disponível apenas para administradores.');st.stop()
    with st.form('competitor'):
        name=st.text_input('Empreendimento',max_chars=180)
        company=st.text_input('Incorporadora',max_chars=160)
        a,b=st.columns(2)
        lat=a.number_input('Latitude',value=float(area[0] if area else city_meta['lat']),format='%.6f',min_value=-90.0,max_value=90.0)
        lon=b.number_input('Longitude',value=float(area[1] if area else city_meta['lon']),format='%.6f',min_value=-180.0,max_value=180.0)
        status=st.selectbox('Etapa',['Pré-lançamento','Lançamento','Em obras','Entregue'])
        units=st.number_input('Unidades · 0 = não informado',min_value=0,step=1)
        price_m2=st.number_input('Preço/m² (R$) · 0 = não informado',min_value=0.0,step=100.0)
        save=st.form_submit_button('Cadastrar empreendimento')
    if save:
        try:
            save_competitor(engine,{'nome':name,'incorporadora':company,'cidade':city,'latitude':lat,
                             'longitude':lon,'status':status,'unidades':units or None,'preco_m2':price_m2 or None})
            refresh_data();st.rerun()
        except ValueError as exc:st.warning(str(exc))
    if not frame.empty:
        selected=st.selectbox('Registro para excluir',frame.id.tolist(),format_func=lambda i:frame.loc[frame.id==i,'nome'].iloc[0])
        confirm=st.checkbox('Confirmo excluir o empreendimento selecionado')
        if st.button('Excluir empreendimento',disabled=not confirm):
            delete_competitor(engine,selected);refresh_data();st.rerun()

elif navigation=='Relatórios':
    st.title('Histórico de relatórios')
    st.caption('Registro das gerações desta conta. Os PDFs são baixados no momento da geração; não armazenamos seus arquivos no banco.')
    frame=report_history(engine,owner)
    st.dataframe(frame.drop(columns=['owner'],errors='ignore'),hide_index=True,use_container_width=True)
    st.download_button('Exportar histórico CSV',csv_bytes(frame.drop(columns=['owner'],errors='ignore')),'historico_relatorios.csv')
