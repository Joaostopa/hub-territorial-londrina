"""Timeouts, cache em disco e intervalo mínimo por domínio, inclusive entre processos."""
import hashlib
import json
import sqlite3
import time
from urllib.parse import urlsplit
import requests
from config import DATA_DIR, USER_AGENT

class ExternalUnavailable(RuntimeError):
    pass

def _reserve(host, interval=3):
    # Reserve slots under a DB lock; sleep happens after releasing the lock.
    with sqlite3.connect(DATA_DIR/'http_cache.sqlite', timeout=30) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS rate (host TEXT PRIMARY KEY, next_at REAL)')
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT next_at FROM rate WHERE host=?',(host,)).fetchone()
        now = time.time()
        start = max(now, row[0] if row else now)
        conn.execute('INSERT OR REPLACE INTO rate VALUES (?,?)',(host,start+interval))
    time.sleep(max(0,start-time.time()))

def fetch(url, *, params=None, data=None, ttl=86400, as_json=True, cache=True):
    key = hashlib.sha256(json.dumps([url,params,data],sort_keys=True).encode()).hexdigest()
    cache_dir = DATA_DIR/'cache'
    cache_dir.mkdir(exist_ok=True)
    path = cache_dir/f'{key}.json'
    if cache and path.exists():
        try:
            cached = json.loads(path.read_text(encoding='utf-8'))
            if time.time()-cached['time'] < ttl:
                return cached['value']
        except (ValueError, OSError, KeyError):
            pass
    _reserve(urlsplit(url).netloc)
    try:
        response = requests.request('POST' if data else 'GET',url,params=params,data=data,
                                    headers={'User-Agent':USER_AGENT},timeout=(8,25))
        response.raise_for_status()
        if len(response.content) > 15_000_000:
            raise ExternalUnavailable('Resposta externa excedeu 15 MB.')
        result = response.json() if as_json else response.text
        if not cache:
            return result
        # Unique temporary path prevents concurrent writers clobbering one another.
        import tempfile, os
        fd, temporary = tempfile.mkstemp(dir=cache_dir, suffix='.tmp')
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump({'time':time.time(),'value':result},f,ensure_ascii=False)
        os.replace(temporary,path)
        return result
    except (requests.RequestException, ValueError) as exc:
        raise ExternalUnavailable(f'Fonte indisponível ({urlsplit(url).netloc}): {type(exc).__name__}.') from exc
