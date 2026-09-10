"""Transporte observável: rate limit, robots, timeout e redirects restritos à fonte."""
from dataclasses import dataclass
from urllib.parse import urljoin,urlsplit
from urllib.robotparser import RobotFileParser
import requests
from config import USER_AGENT
from connectors.http import _reserve
from scrapers.base import validate_portal_url

class CollectionFailure(RuntimeError):
    def __init__(self,kind,message,status=None):
        super().__init__(message);self.kind=kind;self.status=status

@dataclass
class Page:
    url: str
    text: str
    status: int

class PublicClient:
    def __init__(self,domains,*,timeout=(6,15),user_agent=USER_AGENT):
        self.domains=domains;self.timeout=timeout;self.user_agent=user_agent
        self.robots={};self.requests_count=0
    def _request(self,url,interval=3):
        for _ in range(6):
            validate_portal_url(url,self.domains)
            _reserve(urlsplit(url).netloc,interval=max(3,interval))
            self.requests_count+=1
            try:
                response=requests.get(url,headers={'User-Agent':self.user_agent},timeout=self.timeout,allow_redirects=False)
            except requests.Timeout as exc:
                raise CollectionFailure('network_error','Timeout; não comprova bloqueio do site.') from exc
            except requests.RequestException as exc:
                raise CollectionFailure('network_error',f'Falha de conexão: {type(exc).__name__}.') from exc
            if response.status_code in (301,302,303,307,308):
                target=urljoin(url,response.headers.get('Location',''))
                if target==url:raise CollectionFailure('http_error','Redirecionamento sem destino válido.',response.status_code)
                try:validate_portal_url(target,self.domains)
                except ValueError as exc:raise CollectionFailure('redirect_blocked','Redirecionamento para domínio fora da fonte.') from exc
                # Revalidate robots for the redirect destination before following HTML redirects.
                if interval >= 0 and not urlsplit(target).path.endswith('/robots.txt'):
                    policy=self._policy(target)
                    if not policy.can_fetch(self.user_agent,target):
                        raise CollectionFailure('robots_disallowed','robots.txt não permite o destino do redirecionamento.')
                url=target;continue
            if response.status_code in (401,403,429):
                raise CollectionFailure('http_blocked',f'HTTP {response.status_code}; fonte não coletada.',response.status_code)
            if len(response.content)>15_000_000:
                raise CollectionFailure('response_too_large','Resposta excedeu o limite de 15 MB.')
            return Page(url,response.text,response.status_code)
        raise CollectionFailure('http_error','Limite de redirecionamentos excedido.')
    def _policy(self,url):
        origin=f'{urlsplit(url).scheme}://{urlsplit(url).netloc}'
        if origin not in self.robots:
            page=self._request(origin+'/robots.txt',interval=-1)
            policy=RobotFileParser()
            if page.status in (404,410):
                # Verified absence of robots, not a timeout or access denial.
                policy.parse(['User-agent: *','Disallow:'])
            elif page.status==200:
                if '<html' in page.text[:500].lower():
                    raise CollectionFailure('robots_unavailable','robots.txt retornou HTML, não uma política verificável.')
                policy.parse(page.text.splitlines())
            else:raise CollectionFailure('robots_unavailable',f'Não foi possível verificar robots.txt: HTTP {page.status}.',page.status)
            self.robots[origin]=policy
        return self.robots[origin]
    def get(self,url):
        validate_portal_url(url,self.domains)
        policy=self._policy(url)
        if not policy.can_fetch(self.user_agent,url):
            raise CollectionFailure('robots_disallowed','Coleta não permitida pelo robots.txt para esta URL.')
        delay=policy.crawl_delay(self.user_agent) or policy.crawl_delay('*') or 3
        page=self._request(url,delay)
        if page.status!=200:
            raise CollectionFailure('http_error',f'HTTP {page.status}.',page.status)
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(page.text,'html.parser')
        heading=' '.join(x.get_text(' ',strip=True) for x in soup.select('title,h1')).lower()
        if 'cf-chl-' in page.text or any(x in heading for x in ['access denied','just a moment','captcha','verifique que você é humano']):
            raise CollectionFailure('challenge','Desafio de acesso detectado; execução interrompida.')
        return page
