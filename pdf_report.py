"""PDF paginado com todos os anúncios filtrados e proveniência dos dados."""
from io import BytesIO
from datetime import datetime, timezone
from html import escape
import math
from pathlib import Path
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                               PageBreak, Flowable, KeepTogether)
from analytics import metrics
from geoutils import local_projection

FONT_DIR=Path(reportlab.__file__).resolve().parent/'fonts'
pdfmetrics.registerFont(TTFont('HubSans',str(FONT_DIR/'Vera.ttf')))
pdfmetrics.registerFont(TTFont('HubSans-Bold',str(FONT_DIR/'VeraBd.ttf')))

NAVY=colors.HexColor('#123F50')
BLUE=colors.HexColor('#137C9B')
PALE=colors.HexColor('#ECF4F7')
GRAY=colors.HexColor('#526571')

def fmt(value,decimals=0):
    if value is None or pd.isna(value):
        return 'Não disponível'
    return f'{float(value):,.{decimals}f}'.replace(',','X').replace('.',',').replace('X','.')

class AreaPlot(Flowable):
    """Planta de localização métrica, sem ruas ou imagens de terceiros."""
    def __init__(self,area,df,neighborhood_geo=None):
        super().__init__()
        self.width,self.height=483,242
        self.area,self.df,self.geo=area,df,neighborhood_geo
    def draw(self):
        c=self.canv
        lat,lon,radius=self.area
        project,_=local_projection(lat,lon)
        scale=92/(radius*1000)
        cx,cy=241,126
        c.setFillColor(PALE);c.roundRect(0,0,self.width,self.height,8,fill=1,stroke=0)
        c.setStrokeColor(colors.HexColor('#C8DCE3'));c.setLineWidth(.5)
        for x in range(20,483,30): c.line(x,28,x,222)
        for y in range(36,223,30): c.line(20,y,463,y)
        if self.geo:
            from shapely.geometry import shape
            for feature in self.geo.get('features',[]):
                geom=shape(feature['geometry'])
                parts=[geom] if geom.geom_type=='Polygon' else list(geom.geoms)
                for part in parts:
                    # Clip boundaries to circle to keep the plot self-contained.
                    from geoutils import circle_geometry
                    clipped=part.intersection(circle_geometry(*self.area))
                    polygons=[clipped] if clipped.geom_type=='Polygon' else list(getattr(clipped,'geoms',[]))
                    for poly in polygons:
                        if poly.geom_type!='Polygon': continue
                        path=c.beginPath()
                        for i,(x,y) in enumerate(poly.exterior.coords):
                            x,y=project(x,y)
                            (path.moveTo if i==0 else path.lineTo)(cx+x*scale,cy+y*scale)
                        c.setStrokeColor(colors.HexColor('#98B5BF'));c.drawPath(path)
        c.setStrokeColor(BLUE);c.setLineWidth(1.3);c.circle(cx,cy,92,stroke=1,fill=0)
        c.setFillColor(BLUE)
        for row in self.df.itertuples():
            x,y=project(row.longitude,row.latitude)
            c.circle(cx+x*scale,cy+y*scale,2,stroke=0,fill=1)
        c.setStrokeColor(NAVY);c.line(cx-5,cy,cx+5,cy);c.line(cx,cy-5,cx,cy+5)
        c.setFont('HubSans-Bold',9);c.setFillColor(NAVY);c.drawString(444,211,'N')
        c.line(447,187,447,206);c.line(443,200,447,206);c.line(451,200,447,206)
        c.setFont('HubSans',8)
        c.drawString(15,12,f'Raio: {fmt(radius,2)} km | Azul: anúncios | Cruz: centro | Projeção local métrica')

class HistoryPlot(Flowable):
    def __init__(self,history):
        super().__init__();self.width=483;self.height=160;self.history=history
    def draw(self):
        c=self.canv;h=self.history
        series=h.groupby('mes').mediana_m2.median().sort_index()
        if series.empty:return
        lo,hi=float(series.min()),float(series.max())
        span=hi-lo or max(1,hi*.1);lo-=span*.1;hi+=span*.1
        c.setStrokeColor(GRAY);c.line(55,30,470,30);c.line(55,30,55,145)
        pts=[]
        for i,(month,value) in enumerate(series.items()):
            x=65+i*390/max(1,len(series)-1);y=35+(value-lo)/(hi-lo)*100
            pts.append((x,y));c.setFont('HubSans',7);c.drawCentredString(x,16,month)
        c.setStrokeColor(BLUE);c.setLineWidth(2)
        for a,b in zip(pts,pts[1:]):c.line(*a,*b)
        for x,y in pts:c.circle(x,y,2,stroke=1,fill=0)
        c.setFont('HubSans',8);c.setFillColor(GRAY)
        c.drawRightString(48,137,fmt(hi));c.drawRightString(48,32,fmt(lo))

def build_pdf(city,area,df,filters,neighborhoods,demographics,municipal,pois,poi_note,
              history,competition,*,demo=False,neighborhood_geo=None,mesh_source='Não cadastrada'):
    output=BytesIO()
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='HubTitle',fontName='HubSans-Bold',fontSize=26,leading=30,textColor=NAVY,spaceAfter=10))
    styles.add(ParagraphStyle(name='HubH',fontName='HubSans-Bold',fontSize=15,leading=19,textColor=NAVY,spaceBefore=13,spaceAfter=8))
    styles.add(ParagraphStyle(name='HubBody',fontName='HubSans',fontSize=10,leading=14,textColor=GRAY,spaceAfter=7))
    styles.add(ParagraphStyle(name='HubCell',fontName='HubSans',fontSize=8,leading=10,textColor=NAVY,wordWrap=None))
    def p(text,style='HubBody'):return Paragraph(escape(str(text)),styles[style])
    def table(rows,widths=None):
        rendered=[[p('' if v is None or (isinstance(v,float) and math.isnan(v)) else v,'HubCell') for v in row] for row in rows]
        t=Table(rendered,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCEBF0')),
                    ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F8FA')]),
                    ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),
                    ('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),
                    ('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),1,NAVY)]))
        return t
    summary=metrics(df,area[2])
    timestamp=datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
    story=[p('INTELIGÊNCIA TERRITORIAL','HubBody'),p(city,'HubTitle'),
           p('Análise da área selecionada | '+timestamp)]
    if demo:story.append(p('DEMONSTRAÇÃO - anúncios e preços inteiramente fictícios. Não usar para decisão.','HubH'))
    story.append(table([['Anúncios observados','Mediana do preço/m²','Área do círculo'],
                        [fmt(summary['anuncios']), 'R$ '+fmt(summary['mediana_m2'],2),fmt(math.pi*area[2]**2,2)+' km²']],[161,161,161]))
    story.extend([Spacer(1,14),AreaPlot(area,df,neighborhood_geo),Spacer(1,9),
                  p(f'Centro: {area[0]:.6f}, {area[1]:.6f}. Finalidade: {filters.get("finalidade","venda")}. '
                    f'Com preço/m² válido: {summary["com_preco_m2"]} anúncio(s).'),
                  p('Amostra de anúncios coletados, não censo do mercado. Duplicatas entre portais podem existir. '
                    'Coordenadas do portal podem ser aproximadas. Disponibilidade atual não confirmada.'),
                  p('Filtros aplicados: '+str(filters)),PageBreak(),p('Bairros e demografia','HubH')])
    story.append(p('Malha: '+mesh_source))
    if neighborhoods.empty:
        story.append(p('Nenhum bairro identificado na malha cadastrada. A ausência de malha não significa ausência de bairros.'))
    else:
        story.append(table([['Bairro','Bairro coberto pelo círculo','Interseção (km²)']]+[
            [r.bairro,fmt(r.fracao_area*100,1)+'%',fmt(r.area_intersecao_km2,3)] for r in neighborhoods.itertuples()],[223,150,110]))
    story.append(p(demographics.get('mensagem','Indicadores da área não disponíveis.')))
    if demographics.get('populacao_estimada') is not None:
        story.append(table([['Indicador estimado','Valor'],['População',fmt(demographics['populacao_estimada'])],
                           ['Renda média ponderada', 'R$ '+fmt(demographics.get('renda_media'),2)],
                           ['Ano dos indicadores',demographics.get('ano')]], [280,203]))
        if demographics.get('faixas'):
            story.append(table([['Faixa etária','Pessoas estimadas']]+[[k,fmt(v)] for k,v in demographics['faixas'].items()],[280,203]))
    story.extend([p('Contexto municipal','HubH'),p(f'Censo {municipal.get("ano",2022)}: '
                 f'{fmt(municipal.get("populacao"))} habitantes no município inteiro. Não atribuir esse total ao raio.'),
                  p('Conveniências próximas','HubH'),p(poi_note)])
    if not pois.empty:
        counts=pois.groupby('categoria').size()
        story.append(table([['Categoria','Locais mapeados']]+[[k,int(v)] for k,v in counts.items()],[330,153]))
    if not competition.empty:
        story.extend([p('Concorrência cadastrada','HubH'),table([['Empreendimento','Incorporadora','Etapa']]+
                [[r.nome,r.incorporadora,r.status] for r in competition.itertuples()],[190,173,120])])
    if not history.empty:
        story.extend([PageBreak(),p('Histórico de anúncios observados','HubH'),
                      p('Mediana das medianas por bairro em cada mês. Um registro por fonte/anúncio/mês; '
                        'a composição muda ao longo do tempo. Não mede valorização do mesmo imóvel.'),HistoryPlot(history),
                      table([['Mês','Bairro','Mediana (R$/m²)','Anúncios']]+[
                          [r.mes,r.bairro,fmt(r.mediana_m2,2),r.anuncios] for r in history.itertuples()],[65,240,108,70])])
    story.extend([PageBreak(),p('Inventário da área','HubH'),p(f'{len(df)} anúncio(s). Última observação de cada fonte/identificador.')])
    if df.empty:
        story.append(p('Não há anúncios geolocalizados para os filtros selecionados.'))
    else:
        story.append(table([['Fonte / ID','Bairro / tipo','Preço (R$)','Área m²','R$/m²','km','Coleta']]+[
            [f'{r.fonte}\n{r.id_externo}',f'{r.bairro or "Não informado"}\n{r.tipo}',fmt(r.preco,2),
             fmt(r.area_m2,1),fmt(r.preco_m2,2),fmt(getattr(r,'distancia_km',None),2),
             pd.Timestamp(r.data_coleta).strftime('%d/%m/%y')] for r in df.itertuples()],[92,108,80,45,65,35,58]))
    if not pois.empty:
        story.extend([PageBreak(),p('Locais de conveniência','HubH'),table([['Local','Categoria','Distância km']]+
            [[r.nome,r.categoria,fmt(r.distancia_km,2)] for r in pois.itertuples()],[280,120,83])])
    story.extend([Spacer(1,16),p('Fontes e limites','HubH'),p('IBGE: '+str(municipal.get('fonte','Não consultado'))),
                  p('Indicadores locais: '+'; '.join(demographics.get('fontes') or ['Não cadastrados'])),
                  p('POIs: https://www.openstreetmap.org/copyright | https://overpass-api.de/'),
                  p('Renda: média ponderada pela população estimada dos bairros; usar somente indicadores de mesma definição. '
                    'Áreas com dados incompletos não recebem score. Valores anunciados não são preços de transações.')])
    def footer(c,doc):
        c.saveState();c.setStrokeColor(colors.HexColor('#DCE6EA'));c.line(56,42,539,42)
        c.setFont('HubSans',8);c.setFillColor(GRAY)
        c.drawString(56,29,'HUB TERRITORIAL | '+('DEMONSTRAÇÃO' if demo else 'USO INTERNO'))
        c.drawRightString(539,29,f'{doc.page}');c.restoreState()
    doc=SimpleDocTemplate(output,pagesize=A4,rightMargin=56,leftMargin=56,topMargin=42,bottomMargin=58,
                          title=f'Hub Territorial - {city}',author='Hub de Inteligência Territorial')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
