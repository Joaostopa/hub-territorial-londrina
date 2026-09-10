from html import escape
import folium
from folium.plugins import Draw, MarkerCluster, Fullscreen
from branca.element import MacroElement, Template
from pdf_report import fmt

class SingleCircle(MacroElement):
    """Um círculo editável; propaga edição como evento completo para streamlit-folium."""
    _template=Template('''{% macro script(this, kwargs) %}
      var hubMap = {{this._parent.get_name()}};
      var hubGroup = {{this.group.get_name()}};
      hubGroup.eachLayer(function(layer) {
        layer.feature = {type: 'Feature', properties: {radius: layer.getRadius()}};
      });
      hubMap.on('draw:created', function(e) {
        if (e.layerType !== 'circle') return;
        hubGroup.clearLayers();
        e.layer.feature = {type:'Feature', properties:{radius:e.layer.getRadius()}};
        hubGroup.addLayer(e.layer);
      });
      hubMap.on('draw:edited', function(e) {
        e.layers.eachLayer(function(layer) {
          if (typeof layer.getRadius === 'function') {
            layer.feature = {type:'Feature', properties:{radius:layer.getRadius()}};
            hubMap.fire('draw:created', {layer:layer, layerType:'circle'});
          }
        });
      });
    {% endmacro %}''')
    def __init__(self,group):
        super().__init__();self._name='SingleCircle';self.group=group

def build_map(center,area,df,pois,competition,neighborhood_geo=None):
    m=folium.Map(location=center,zoom_start=13,tiles='OpenStreetMap',control_scale=True,prefer_canvas=True)
    editable=folium.FeatureGroup(name='Área de análise',overlay=True,control=False).add_to(m)
    if area:
        folium.Circle(location=area[:2],radius=area[2]*1000,color='#137C9B',weight=2,
                      fill=True,fill_opacity=.07).add_to(editable)
    Draw(feature_group=editable,export=False,show_geometry_on_click=False,
         draw_options={'circle':{'shapeOptions':{'color':'#137C9B'}},'polygon':False,
                       'polyline':False,'rectangle':False,'marker':False,'circlemarker':False},
         edit_options={'edit':True,'remove':True}).add_to(m)
    SingleCircle(editable).add_to(m)
    if neighborhood_geo and neighborhood_geo.get('features'):
        folium.GeoJson(neighborhood_geo,name='Bairros',
                       style_function=lambda _: {'fillOpacity':.025,'weight':1,'color':'#8C6B40'},
                       tooltip=folium.GeoJsonTooltip(fields=['nome'],aliases=['Bairro'])).add_to(m)
    listings=folium.FeatureGroup(name=f'Anúncios ({len(df)})').add_to(m)
    target=MarkerCluster().add_to(listings) if len(df)>500 else listings
    for row in df.itertuples():
        popup=f'<b>{escape(row.titulo)}</b><br>R$ {fmt(row.preco,2)}<br>{escape(row.bairro or "Bairro não informado")}<br>{escape(row.fonte)}'
        if row.url and str(row.url).startswith(('https://','http://')):
            popup+=f'<br><a href="{escape(row.url,quote=True)}" target="_blank" rel="noopener noreferrer">Abrir anúncio</a>'
        folium.CircleMarker([row.latitude,row.longitude],radius=5,color='#137C9B',weight=1,
                            fill=True,fill_opacity=.8,popup=folium.Popup(popup,max_width=280)).add_to(target)
    nearby=folium.FeatureGroup(name=f'Conveniências ({len(pois)})',show=False).add_to(m)
    for row in pois.itertuples():
        folium.CircleMarker([row.latitude,row.longitude],radius=4,color='#45876F',fill=True,
                            tooltip=escape(f'{row.categoria}: {row.nome}')).add_to(nearby)
    rivals=folium.FeatureGroup(name=f'Concorrência ({len(competition)})').add_to(m)
    for row in competition.itertuples():
        folium.Marker([row.latitude,row.longitude],tooltip=escape(row.nome),
                      popup=folium.Popup(escape(f'{row.incorporadora} | {row.status}'),max_width=220),
                      icon=folium.Icon(color='orange',icon='building',prefix='fa')).add_to(rivals)
    folium.LayerControl(collapsed=True).add_to(m)
    Fullscreen().add_to(m)
    return m
