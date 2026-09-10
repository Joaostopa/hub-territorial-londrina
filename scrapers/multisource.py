"""Extração conservadora. Fixtures não equivalem à validação de um portal ao vivo."""
import hashlib
import re
from urllib.parse import urljoin, urlsplit, urldefrag
from bs4 import BeautifulSoup
from scrapers.base import json_scripts, walk, ld_record, validate_portal_url, ScraperUnavailable
from scrapers.olx_scraper import parse_ad as olx_ad
from scrapers.imovelweb_scraper import parse_ad as imovelweb_ad
from scrapers.vivareal_zap_scraper import parse_payload


def links(html, url, source):
    soup = BeautifulSoup(html, 'html.parser')
    base_tag=soup.find('base',href=True)
    if base_tag:
        candidate=urljoin(url,base_tag['href'])
        try:
            validate_portal_url(candidate,source.domains)
            url=candidate
        except ValueError: pass
    details, following = [], []
    for a in soup.select('a[href]'):
        target = urldefrag(urljoin(url, a['href']))[0]
        try: validate_portal_url(target, source.domains)
        except ValueError: continue
        if re.search(source.detail_pattern, urlsplit(target).path):
            details.append(target)
        label = a.get_text(' ', strip=True).lower()
        if 'next' in a.get('rel', []) or label in ('próxima', 'próximo', 'próxima página', 'seguinte', 'next'):
            following.append(target)
    return list(dict.fromkeys(details)), list(dict.fromkeys(following))


def parse_listings(html, url, source):
    records = {}
    for payload in json_scripts(html):
        if source.key in ('zap', 'vivareal'):
            try:
                for row in parse_payload(payload, 'Londrina', source=source.name):
                    records[row['id_externo']] = row
            except ScraperUnavailable: pass
        for item in walk(payload):
            row = None
            if source.key == 'olx': row = olx_ad(item, 'Londrina', 'venda')
            elif source.key == 'imovelweb': row = imovelweb_ad(item, 'Londrina', 'venda')
            # Restrict generic schema to identified real-estate items.
            if row is None and item.get('@type') in ('Apartment', 'House', 'Residence', 'SingleFamilyResidence', 'RealEstateListing'):
                row = ld_record(item, source.name, 'Londrina', 'venda')
            if row:
                records[row['id_externo']] = row
    if source.key == 'santamerica':
        soup = BeautifulSoup(html,'html.parser')
        for card in soup.select('.card-imo'):
            text=card.get_text(' ',strip=True)
            code=re.search(r'Cód\.\s*(\d+)',text)
            price=re.search(r'R\$\s*([\d.,]+)\s*V\b',text)
            link=card.find('a',href=re.compile(r'^comprar/Londrina/Apartamento/'))
            if not code or not price or not link or not link['href'].endswith('/'+code[1]):continue
            title=card.find('h2');area=re.search(r'([\d.,]+)\s*m²\s*A\. Útil',text)
            rooms=re.search(r'(\d+)\s*Dorm',text);garage=re.search(r'(\d+)\s*Garage',text)
            records[code[1]]=dict(fonte=source.name,id_externo=code[1],cidade='Londrina',
                titulo=title.get_text(' ',strip=True) if title else 'Apartamento em Londrina',
                url=urljoin('https://www.santamerica.com.br/',link['href']),preco=price[1],
                finalidade='venda',tipo='apartamento',bairro=link['href'].split('/')[-2].replace('-',' '),
                area_m2=area[1] if area else None,quartos=rooms[1] if rooms else None,vagas=garage[1] if garage else None)
        if records:return list(records.values())
    # Card fallback: never borrow prices/areas from neighboring advertisements.
    soup = BeautifulSoup(html, 'html.parser')
    detail_urls, _ = links(html, url, source)
    for target in detail_urls:
        anchor = next((a for a in soup.select('a[href]') if urldefrag(urljoin(url, a['href']))[0] == target), None)
        if anchor is None: continue
        for node in [anchor, *list(anchor.parents)[:5]]:
            card_urls, _ = links(str(node), url, source)
            if set(card_urls) != {target}: break
            text = node.get_text(' ', strip=True)
            if not re.search(r'Londrina', text, re.I): continue
            prices = re.findall(r'R\$\s*([\d.]+(?:,\d{2})?)\s*([VL])?\b', text)
            sale = [p for p, mode in prices if mode == 'V']
            if not sale and len(prices) == 1 and prices[0][1] != 'L': sale = [prices[0][0]]
            if len(set(sale)) != 1: continue
            code = re.search(r'C[óo]d\.?\s*:?\s*(\d+)', text, re.I)
            area = re.search(r'([\d.,]+)\s*m[²2]\s*(?:A\.\s*Útil|privativ|útil)', text, re.I)
            rooms = re.search(r'(\d+)\s*(?:Dorm|quartos)', text, re.I)
            title = node.find(['h2', 'h3'])
            identifier = code[1] if code else hashlib.sha256(target.encode()).hexdigest()
            if any(r.get('url') == target for r in records.values()): break
            records[identifier] = dict(fonte=source.name, id_externo=identifier, cidade='Londrina',
                titulo=title.get_text(' ', strip=True) if title else 'Apartamento em Londrina',
                url=target, preco=sale[0], finalidade='venda', tipo='apartamento',
                area_m2=area[1] if area else None, quartos=rooms[1] if rooms else None)
            break
    return list(records.values())


def parse_project(html, url, source):
    if not re.search(source.detail_pattern, urlsplit(url).path): return None
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.find('h1')
    if not heading: return None
    # Only a project identity; no inferred price, address or map coordinates.
    return dict(fonte=source.name, url=url, nome=heading.get_text(' ', strip=True)[:200], cidade='Londrina')
