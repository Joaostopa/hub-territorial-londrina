from pathlib import Path
from unittest.mock import patch
import streamlit as st
from streamlit.testing.v1 import AppTest

APP=Path(__file__).resolve().parents[1]/'app.py'

def test_initial_empty_and_navigation():
    with patch('streamlit_folium.st_folium',return_value={'last_active_drawing':None,'all_drawings':None}):
        app=AppTest.from_file(str(APP),default_timeout=30).run()
        assert not app.exception
        assert any('Explore' in t.value for t in app.title)
        for page in ['Fontes e coletas','Dados e coleta','Áreas e alertas','Concorrência','Relatórios','Comparar áreas']:
            app.radio(key='navigation').set_value(page).run()
            assert not app.exception, [e.message for e in app.exception]

def test_draw_persists_filters_and_deletion():
    feature={'type':'Feature','geometry':{'type':'Point','coordinates':[-51.1696,-23.3045]},'properties':{'radius':2000}}
    event={'last_active_drawing':feature,'last_circle_radius':2,'all_drawings':[feature]}
    with patch('streamlit_folium.st_folium',return_value={'last_active_drawing':None,'all_drawings':None}):
        app=AppTest.from_file(str(APP),default_timeout=30).run()
        app.toggle(key='demo').set_value(True).run()
        assert not app.exception
    with patch('streamlit_folium.st_folium',return_value=event):
        app.run()
        assert not app.exception,[e.message for e in app.exception]
        assert app.session_state['area']==(-23.3045,-51.1696,2)
        app.selectbox(key='f_finalidade').set_value('aluguel').run()
        assert not app.exception,[e.message for e in app.exception]
        assert app.session_state['area']==(-23.3045,-51.1696,2)
    with patch('streamlit_folium.st_folium',return_value={'last_active_drawing':None,'all_drawings':[]}):
        app.run()
        assert not app.exception
        assert app.session_state['area'] is None
