#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leitor de Live - o SITE feito em PYTHON (arquivo único, só biblioteca padrão).

O site é o mesmo (mesma tela, mesmo visual). O Python faz o trabalho de verdade:
lê o chat do YouTube, limpa o texto (gírias, risadas, emojis), guarda as configurações,
escolhe a voz e busca o áudio do Google / Amazon Polly. O navegador só mostra a tela e toca o som.

Como usar (no PC ou no Termux do celular):
    python leitor_live_site.py
Depois abra no navegador:  http://127.0.0.1:8000
Opções:  --porta 8000   --host 127.0.0.1   (use --host 0.0.0.0 para abrir de outro aparelho da rede)
"""
import argparse, json, os, random, re, shutil, subprocess, threading, time, unicodedata, webbrowser
import urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs

ARQ = Path.home() / '.leitor_live.json'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'}


# ---- pedido HTTP simples (só biblioteca padrão), no formato que o resto do código usa ----
class _Falha(Exception):
    pass


class _Resp:
    def __init__(self, status, corpo):
        self.status_code, self.content = status, corpo
        self.ok = 200 <= status < 300
        self.text = corpo.decode('utf-8', 'replace')

    def json(self):
        return json.loads(self.text)


def _pedir(metodo, url, params=None, headers=None, dados=None, timeout=20):
    if params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    h = dict(headers or {}); corpo = None
    if dados is not None:
        corpo = json.dumps(dados).encode(); h.setdefault('Content-Type', 'application/json')
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=corpo, headers=h, method=metodo), timeout=timeout)
        return _Resp(r.status, r.read())
    except urllib.error.HTTPError as e:
        return _Resp(e.code, e.read())
    except (urllib.error.URLError, OSError) as e:
        raise _Falha(str(e))


class requests:
    RequestException = _Falha

    @staticmethod
    def get(url, params=None, headers=None, timeout=20):
        return _pedir('GET', url, params, headers, None, timeout)

    @staticmethod
    def post(url, headers=None, json=None, timeout=20):
        return _pedir('POST', url, None, headers, json, timeout)


# ---- configurações (ficam em ~/.leitor_live.json) ----
cfgv = {'voz': 0, 'vel': 0, 'vol': 1, 'nome': True, 'bots': True, 'ler': True, 'int': 0, 'pal': 'disse', 'fundo': True}
live_id = ''
chave_yt = ''
try:
    _d = json.loads(ARQ.read_text('utf-8'))
    cfgv.update(_d.get('cfg', {}))
    live_id = _d.get('live', '') or ''
    chave_yt = (_d.get('ytkey', '') or '').strip()
except Exception:
    pass


def salvar():
    try:
        ARQ.write_text(json.dumps({'cfg': cfgv, 'live': live_id, 'ytkey': chave_yt}, ensure_ascii=False), 'utf-8')
    except Exception:
        pass


# ================= CATÁLOGO DE VOZES =================
GV = {
    'pt':       {'lang': 'pt-BR', 'tld': 'com'},
    'pt-lenta': {'lang': 'pt-BR', 'tld': 'com', 'lenta': True},
    'pt-suave': {'lang': 'pt-BR', 'tld': 'com', 'rate': 0.93},
    'pt-grave': {'lang': 'pt-BR', 'tld': 'com', 'rate': 0.82},
    'pt-jovem': {'lang': 'pt-BR', 'tld': 'com', 'rate': 1.14},
    'pt-aguda': {'lang': 'pt-BR', 'tld': 'com', 'rate': 1.3},
    'pt-pt':    {'lang': 'pt-PT', 'tld': 'pt'},
    'en-us':    {'lang': 'en-US', 'tl': 'en', 'tld': 'com'},
    'en-gb':    {'lang': 'en-GB', 'tl': 'en', 'tld': 'co.uk'},
    'en-au':    {'lang': 'en-AU', 'tl': 'en', 'tld': 'com.au'},
    'es-es':    {'lang': 'es-ES', 'tl': 'es', 'tld': 'es'},
    'es-mx':    {'lang': 'es-MX', 'tl': 'es', 'tld': 'com.mx'},
    'fr':       {'lang': 'fr-FR', 'tl': 'fr', 'tld': 'com'},
    'it':       {'lang': 'it-IT', 'tl': 'it', 'tld': 'com'},
    'de':       {'lang': 'de-DE', 'tl': 'de', 'tld': 'com'},
    'ja':       {'lang': 'ja-JP', 'tl': 'ja', 'tld': 'com'},
    'ko':       {'lang': 'ko-KR', 'tl': 'ko', 'tld': 'com'},
    'ru':       {'lang': 'ru-RU', 'tl': 'ru', 'tld': 'com'},
    'zh':       {'lang': 'zh-CN', 'tl': 'zh-CN', 'tld': 'com'},
    'hi':       {'lang': 'hi-IN', 'tl': 'hi', 'tld': 'com'},
    'ar':       {'lang': 'ar-SA', 'tl': 'ar', 'tld': 'com'},
}
ESTILOS = {
    'grave':   {'nome': 'grave',   'desc': 'Tom bem grave e firme (depende de o aparelho aceitar ajuste de tom).', 'pitch': 0.6,  'rate': 0.95, 'tags': ['Grave', 'Adulta']},
    'suave':   {'nome': 'suave',   'desc': 'Tom calmo e ritmo devagar, agradável de ouvir.',                      'pitch': 0.9,  'rate': 0.88, 'tags': ['Suave']},
    'jovem':   {'nome': 'jovem',   'desc': 'Tom mais agudo e animado, soa mais jovem.',                           'pitch': 1.4,  'rate': 1.08, 'tags': ['Jovem']},
    'animada': {'nome': 'animada', 'desc': 'Rápida e cheia de energia.',                                          'pitch': 1.2,  'rate': 1.18, 'tags': ['Jovem']},
    'locutor': {'nome': 'locutor', 'desc': 'Grave e firme, ritmo de locutor de rádio.',                           'pitch': 0.75, 'rate': 1.05, 'tags': ['Grave', 'Adulta']},
}
PRE = {
    'pt': 'Olá! Eu sou esta voz. Posso ler os comentários da sua live.',
    'en': 'Hello! This is my voice. I can read your live chat comments.',
    'es': '¡Hola! Esta es mi voz. Puedo leer los comentarios de tu directo.',
    'fr': 'Bonjour ! Voici ma voix. Je peux lire le chat de votre live.',
    'it': 'Ciao! Questa è la mia voce. Posso leggere i commenti della tua diretta.',
    'de': 'Hallo! Das ist meine Stimme. Ich kann den Chat deiner Live vorlesen.',
    'ja': 'こんにちは！これが私の声です。ライブのコメントを読み上げます。',
    'ko': '안녕하세요! 제 목소리입니다. 라이브 채팅을 읽어 드릴게요.',
    'ru': 'Привет! Это мой голос. Я могу читать комментарии вашего эфира.',
    'zh': '你好！这是我的声音。我可以朗读直播评论。',
    'hi': 'नमस्ते! यह मेरी आवाज़ है। मैं आपकी लाइव चैट पढ़ सकता हूँ।',
    'ar': 'مرحبًا! هذا صوتي. يمكنني قراءة تعليقات البث.',
}


def V(id, nome, desc, lang, tags):
    return {'id': id, 'nome': nome, 'desc': desc, 'lang': lang, 'tags': tags, 'motor': 'net'}


CAT = [
    # --- Português (Brasil) ---
    V('0', 'Google (feminina)', 'Voz feminina clara e neutra. A mais estável para ler comentários.', 'pt-BR', ['Feminina', 'Natural', 'Adulta']),
    V('1', 'Google lenta', 'A mesma voz, bem devagar e pausada.', 'pt-BR', ['Feminina', 'Suave']),
    V('g:pt-suave', 'Google suave', 'Um pouco mais baixa e calma.', 'pt-BR', ['Feminina', 'Suave']),
    V('g:pt-grave', 'Google grave', 'Tom mais grave e firme, soa mais madura.', 'pt-BR', ['Grave', 'Adulta']),
    V('g:pt-jovem', 'Google jovem', 'Tom mais agudo e animado.', 'pt-BR', ['Feminina', 'Jovem']),
    V('g:pt-aguda', 'Google aguda', 'Bem aguda e divertida, estilo personagem.', 'pt-BR', ['Jovem']),
    V('se:Camila', 'Camila', 'Feminina natural e expressiva (voz estilo Amazon Polly).', 'pt-BR', ['Feminina', 'Natural', 'Adulta']),
    V('se:Camila@1.12', 'Camila jovem', 'A Camila com tom mais agudo e leve.', 'pt-BR', ['Feminina', 'Jovem', 'Natural']),
    V('se:Vitoria', 'Vitória', 'Feminina suave e simpática, fala de forma calma.', 'pt-BR', ['Feminina', 'Natural', 'Suave']),
    V('se:Ricardo', 'Ricardo', 'Masculina natural, adulta e firme.', 'pt-BR', ['Masculina', 'Natural', 'Adulta']),
    V('se:Ricardo@0.87', 'Ricardo grave', 'O Ricardo mais grave e imponente, estilo locutor.', 'pt-BR', ['Masculina', 'Grave', 'Adulta']),
    V('se:Ricardo@1.12', 'Ricardo jovem', 'O Ricardo com tom mais agudo, soa como um rapaz.', 'pt-BR', ['Masculina', 'Jovem']),
    # --- Português (Portugal) ---
    V('g:pt-pt', 'Google Portugal', 'Voz feminina com sotaque de Portugal.', 'pt-PT', ['Feminina']),
    V('se:Ines', 'Inês (Portugal)', 'Feminina natural, sotaque português.', 'pt-PT', ['Feminina', 'Natural']),
    V('se:Cristiano', 'Cristiano (Portugal)', 'Masculina natural, sotaque português.', 'pt-PT', ['Masculina', 'Natural', 'Adulta']),
    # --- English ---
    V('g:en-us', 'Google English (US)', 'Female voice, American accent.', 'en-US', ['Feminina']),
    V('g:en-gb', 'Google English (UK)', 'Female voice, British accent.', 'en-GB', ['Feminina']),
    V('g:en-au', 'Google English (AU)', 'Female voice, Australian accent.', 'en-AU', ['Feminina']),
    V('se:Joanna', 'Joanna (US)', 'Natural American woman, clear and friendly.', 'en-US', ['Feminina', 'Natural', 'Adulta']),
    V('se:Matthew', 'Matthew (US)', 'Natural American man, calm and steady.', 'en-US', ['Masculina', 'Natural', 'Adulta']),
    V('se:Justin', 'Justin (US)', 'Voz de garoto americano.', 'en-US', ['Masculina', 'Jovem']),
    V('se:Ivy', 'Ivy (US)', 'Voz de garota americana.', 'en-US', ['Feminina', 'Jovem']),
    V('se:Brian', 'Brian (UK)', 'Natural British man, deep and firm.', 'en-GB', ['Masculina', 'Natural', 'Grave']),
    V('se:Amy', 'Amy (UK)', 'Natural British woman.', 'en-GB', ['Feminina', 'Natural']),
    V('se:Emma', 'Emma (UK)', 'Soft British woman.', 'en-GB', ['Feminina', 'Natural', 'Suave']),
    V('se:Russell', 'Russell (AU)', 'Natural Australian man.', 'en-AU', ['Masculina', 'Natural']),
    V('se:Nicole', 'Nicole (AU)', 'Natural Australian woman.', 'en-AU', ['Feminina', 'Natural']),
    # --- Español ---
    V('g:es-es', 'Google Español (España)', 'Voz feminina, sotaque da Espanha.', 'es-ES', ['Feminina']),
    V('g:es-mx', 'Google Español (México)', 'Voz feminina, sotaque mexicano.', 'es-MX', ['Feminina']),
    V('se:Conchita', 'Conchita (España)', 'Feminina natural, espanhol da Espanha.', 'es-ES', ['Feminina', 'Natural']),
    V('se:Enrique', 'Enrique (España)', 'Masculina natural, espanhol da Espanha.', 'es-ES', ['Masculina', 'Natural', 'Adulta']),
    V('se:Penelope', 'Penélope (Latino)', 'Feminina natural, espanhol latino.', 'es-US', ['Feminina', 'Natural']),
    V('se:Miguel', 'Miguel (Latino)', 'Masculina natural, espanhol latino.', 'es-US', ['Masculina', 'Natural']),
    # --- Outros idiomas ---
    V('g:fr', 'Google Français', 'Voz feminina em francês.', 'fr-FR', ['Feminina']),
    V('se:Celine', 'Céline (Français)', 'Feminina natural em francês.', 'fr-FR', ['Feminina', 'Natural']),
    V('se:Mathieu', 'Mathieu (Français)', 'Masculina natural em francês.', 'fr-FR', ['Masculina', 'Natural']),
    V('g:it', 'Google Italiano', 'Voz feminina em italiano.', 'it-IT', ['Feminina']),
    V('se:Carla', 'Carla (Italiano)', 'Feminina natural em italiano.', 'it-IT', ['Feminina', 'Natural']),
    V('se:Giorgio', 'Giorgio (Italiano)', 'Masculina natural em italiano.', 'it-IT', ['Masculina', 'Natural']),
    V('g:de', 'Google Deutsch', 'Voz feminina em alemão.', 'de-DE', ['Feminina']),
    V('se:Marlene', 'Marlene (Deutsch)', 'Feminina natural em alemão.', 'de-DE', ['Feminina', 'Natural']),
    V('se:Hans', 'Hans (Deutsch)', 'Masculina natural em alemão.', 'de-DE', ['Masculina', 'Natural']),
    V('g:ja', 'Google 日本語', 'Voz feminina em japonês.', 'ja-JP', ['Feminina']),
    V('se:Mizuki', 'Mizuki (日本語)', 'Feminina natural em japonês.', 'ja-JP', ['Feminina', 'Natural']),
    V('g:ko', 'Google 한국어', 'Voz feminina em coreano.', 'ko-KR', ['Feminina']),
    V('g:ru', 'Google Русский', 'Voz feminina em russo.', 'ru-RU', ['Feminina']),
    V('g:zh', 'Google 中文', 'Voz feminina em chinês.', 'zh-CN', ['Feminina']),
    V('g:hi', 'Google हिन्दी', 'Voz feminina em hindi.', 'hi-IN', ['Feminina']),
    V('g:ar', 'Google العربية', 'Voz feminina em árabe.', 'ar-SA', ['Feminina']),
]
CAT_IDS = {v['id'] for v in CAT}


def bandeira(l):
    l = (l or '').lower().replace('_', '-')
    m = {'pt-br': '🇧🇷', 'pt-pt': '🇵🇹', 'en-us': '🇺🇸', 'en-gb': '🇬🇧', 'en-au': '🇦🇺', 'es-es': '🇪🇸', 'es-mx': '🇲🇽', 'es-us': '🌎'}
    if l in m:
        return m[l]
    b = {'pt': '🇧🇷', 'en': '🇺🇸', 'es': '🇪🇸', 'fr': '🇫🇷', 'it': '🇮🇹', 'de': '🇩🇪', 'ja': '🇯🇵', 'ko': '🇰🇷', 'ru': '🇷🇺', 'zh': '🇨🇳', 'hi': '🇮🇳', 'ar': '🌍'}
    return b.get(l[:2], '🌐')

# ================= TEXTO: limpeza, gírias, risadas, emojis =================
REGEX_LINK = re.compile(r'https?://\S+|www\.\S+')
IGNORAR = ['nightbot', 'streamlabs', 'streamelements', 'moobot']
TAMANHO_MAX = 200
GIRIAS = {'vc': 'você', 'vcs': 'vocês', 'tb': 'também', 'tbm': 'também', 'pq': 'porque', 'q': 'que',
          'blz': 'beleza', 'obg': 'obrigado', 'msm': 'mesmo', 'mt': 'muito', 'mto': 'muito', 'td': 'tudo', 'hj': 'hoje',
          'n': 'não', 'ngm': 'ninguém', 'cmg': 'comigo', 'flw': 'falou', 'vdd': 'verdade', 'pfv': 'por favor',
          'pf': 'por favor', 'tmj': 'tamo junto', 'sdds': 'saudades', 'kd': 'cadê'}
REGEX_RISO = re.compile(r'\b(?:[kK]{2,}|(?:[hH][aA]){2,}[hH]?|(?:[rR][sS])+|(?:[hH][eE]){2,}[hH]?)\b')
_OK_CHARS = set(",.!?;:'-")


def limpar(t):
    return REGEX_LINK.sub('', t).strip()


def extrair_id(t):
    t = (t or '').strip()
    m = re.search(r'(?:v=|youtu\.be/|/live/|/shorts/|/embed/)([A-Za-z0-9_-]{11})', t)
    if m:
        return m.group(1)
    return t if re.fullmatch(r'[A-Za-z0-9_-]{11}', t) else None


def humanizar(t, pt=True):
    t = REGEX_RISO.sub(' haha ', t)
    t = re.sub(r'([^\W\d_])\1{2,}', r'\1', t)
    t = ''.join(c if (unicodedata.category(c)[0] in 'LMN' or c.isspace() or c in _OK_CHARS or c == '_') else ' ' for c in t)
    t = t.replace('_', ' ')
    t = re.sub(r'([!?.,])\1+', r'\1', t)
    if pt:
        t = re.sub(r'\w+', lambda m: GIRIAS.get(m.group(0).lower(), m.group(0)), t)
    t = re.sub(r'(?:haha\s*){2,}', 'haha ', t)
    return re.sub(r'\s+', ' ', t).strip()


def partir(texto, n=180):
    pedacos, atual = [], ''
    for trecho in re.split(r'(?<=[.!?;:,])\s+', texto):
        palavras = [trecho] if len(trecho) <= n else re.split(r'\s+', trecho)
        for w in palavras:
            if atual and len(atual) + len(w) + 1 > n:
                pedacos.append(atual)
                atual = w
            else:
                atual = (atual + ' ' + w).strip()
    if atual:
        pedacos.append(atual)
    return pedacos


def limpar_nome(a):
    n = re.sub(r'^@', '', a)
    n = re.sub(r'-(?=[a-z0-9]*\d)[a-z0-9]{3,5}$', '', n, flags=re.I)
    n = re.sub(r'[_.]+', ' ', n)
    n = ''.join((' ' + c) if (i and n[i - 1].islower() and c.isupper()) else c for i, c in enumerate(n))
    n = re.sub(r'\d+', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    n = ' '.join((w[0] + w[1:].lower()) if (len(w) > 2 and w == w.upper()) else w for w in n.split(' '))
    return n or 'Alguém'


def texto_fala(l):
    f = re.sub(r':[A-Za-z0-9_\-]+:', '', l['m']).strip()
    if not any(c.isalnum() for c in f):
        return ''
    if not cfgv['nome']:
        return f
    n, p = limpar_nome(l['a']), (cfgv['pal'] or '').strip()
    return n + ' ' + p + ': ' + f if p else n + ', ' + f


def seguro(u):
    return isinstance(u, str) and re.match(r'^https?://', u, re.I) is not None

# ================= CHAT DO YOUTUBE =================
def info_live(vid):
    url = 'https://www.youtube.com/watch?v=' + vid
    try:
        r = requests.get('https://www.youtube.com/oembed', params={'format': 'json', 'url': url}, timeout=15)
        if not r.ok:
            return None
        d = r.json()
    except Exception:
        return None
    logo = ''
    try:
        p = requests.get(url, headers=UA, timeout=15).text
        m = re.search(r'"videoOwnerRenderer":\{"thumbnail":\{"thumbnails":\[\{"url":"([^"]+)"', p)
        if m:
            logo = m.group(1).replace('\\u0026', '&')
    except Exception:
        pass
    return {'nome': d.get('author_name', ''), 'titulo': d.get('title', ''), 'url': d.get('author_url', ''), 'logo': logo}


def api_yt(rota, params):
    params = dict(params, key=chave_yt)
    r = requests.get('https://www.googleapis.com/youtube/v3/' + rota, params=params, timeout=20)
    try:
        d = r.json()
    except Exception:
        d = {}
    if not r.ok:
        er = d.get('error', {})
        mot = ((er.get('errors') or [{}])[0]).get('reason', '')
        m = {'quotaExceeded': 'a cota diária da API do YouTube acabou (volta amanhã)',
             'liveChatEnded': 'o chat dessa live terminou', 'liveChatDisabled': 'o chat dessa live está desligado',
             'liveChatNotFound': 'não achei o chat dessa live', 'keyInvalid': 'chave da API inválida',
             'accessNotConfigured': 'ative a "YouTube Data API v3" no Google Cloud para essa chave',
             'rateLimitExceeded': 'muitas consultas seguidas, aguarde um pouco'}
        raise Exception(m.get(mot) or ('erro ' + str(r.status_code) + (': ' + er['message'] if er.get('message') else '')))
    return d


def _dados_iniciais(h):
    """Acha 'ytInitialData = {...}' no HTML da página e devolve só esse objeto JSON."""
    m = re.search(r'ytInitialData"?\]?\s*=\s*\{', h)
    if not m:
        return None
    try:
        return json.JSONDecoder().raw_decode(h[m.end() - 1:])[0]
    except ValueError:
        return None


def _achar(o, chave):
    if isinstance(o, dict):
        if chave in o:
            return o[chave]
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            r = _achar(v, chave)
            if r is not None:
                return r
    return None


class Chat:
    def __init__(self):
        self.vid = ''; self.info = None; self.itens = []; self.n = 0; self.ok = False; self.sessao = ''
        self.ativo = False; self.cont = ''; self.key = ''; self.ver = ''; self.espera = 3
        self.chat_id = ''; self.pagina = ''; self.lock = threading.Lock()

    def iniciar(self, vid, info=None):
        self.ativo = False
        self.vid = vid
        self.info = info or {'nome': '', 'titulo': '', 'url': '', 'logo': ''}
        with self.lock:
            self.itens = []
        self.n = 0; self.ok = False; self.cont = ''; self.espera = 3
        self.sessao = '%06x' % random.randrange(16 ** 6)
        self.ativo = True
        if not info or not info.get('nome'):
            def busca():
                i = info_live(vid)
                if i and self.vid == vid:
                    self.info = i
            threading.Thread(target=busca, daemon=True).start()
        threading.Thread(target=self.ciclo, args=(self.sessao,), daemon=True).start()

    def add(self, item):
        with self.lock:
            self.n += 1
            self.itens.append((self.n, item))
            if len(self.itens) > 30:
                self.itens.pop(0)

    def aviso(self, t):
        with self.lock:
            u = self.itens[-1] if self.itens else None
        if u and u[1]['t'] == 'sis' and u[1]['m'] == t:
            return
        self.add({'t': 'sis', 'm': t})

    def ler(self, desde):
        with self.lock:
            linhas = [x[1] for x in self.itens if x[0] > desde]
            return {'linhas': linhas, 'ultimo': self.n, 'chat': self.ok, 'canal': self.info, 'sessao': self.sessao}

    def ciclo(self, minha):
        vivo = lambda: self.ativo and self.sessao == minha
        while vivo():
            try:
                if not self.cont:
                    (self.conectar_api if chave_yt else self.conectar)()
                    if not vivo():
                        return
                    self.ok = True; self.espera = 3
                    self.aviso('Conectado ao chat. Aguardando comentários...')
                ms = (self.buscar_api if chave_yt else self.buscar)()
                time.sleep(max(1000, min(ms, 10000)) / 1000)
            except Exception as e:
                self.ok = False; self.cont = ''
                if not vivo():
                    return
                txt = 'sem internet ou sem acesso ao YouTube' if isinstance(e, requests.RequestException) else str(e)[:140]
                self.aviso('Chat sem conexão: ' + txt + '. Tentando de novo...')
                time.sleep(self.espera); self.espera = min(self.espera * 2, 30)

    def conectar_api(self):
        d = api_yt('videos', {'part': 'liveStreamingDetails,snippet', 'id': self.vid})
        it = (d.get('items') or [None])[0]
        if not it:
            raise Exception('não achei essa live')
        id_ = (it.get('liveStreamingDetails') or {}).get('activeLiveChatId')
        if not id_:
            raise Exception('essa live não tem chat ativo (já terminou ou o chat está desligado)')
        self.chat_id = id_; self.pagina = ''; self.cont = 'api'
        if not self.info or not self.info.get('nome'):
            s = it.get('snippet') or {}
            self.info = {'nome': s.get('channelTitle', ''), 'titulo': s.get('title', ''),
                         'url': ('https://www.youtube.com/channel/' + s['channelId']) if s.get('channelId') else '', 'logo': ''}

    def buscar_api(self):
        p = {'part': 'snippet,authorDetails', 'maxResults': 200, 'liveChatId': self.chat_id}
        if self.pagina:
            p['pageToken'] = self.pagina
        d = api_yt('liveChat/messages', p)
        self.pagina = d.get('nextPageToken') or self.pagina
        for it in d.get('items', []):
            s = it.get('snippet') or {}
            if s.get('type') != 'textMessageEvent':
                continue
            txt = limpar((s.get('textMessageDetails') or {}).get('messageText') or s.get('displayMessage') or '')
            if not txt or len(txt) > TAMANHO_MAX:
                continue
            a = it.get('authorDetails') or {}
            autor = a.get('displayName', '')
            self.add({'t': 'chat', 'a': autor, 'm': txt, 'bot': re.sub(r'^@', '', autor).lower() in IGNORAR,
                      'img': a.get('profileImageUrl', ''),
                      'url': ('https://www.youtube.com/channel/' + a['channelId']) if a.get('channelId') else ''})
        return max(d.get('pollingIntervalMillis') or 6000, 6000)  # respeita o ritmo pedido pelo YouTube (e poupa a cota)

    def conectar(self):
        cab = dict(UA, **{'Accept-Language': 'pt-BR,pt;q=0.9', 'Cookie': 'CONSENT=YES+1; SOCS=CAI'})
        cont, h = '', ''
        # 1) página do chat (popout), 2) página do vídeo: as duas trazem o "continuation" do chat
        for url in ('https://www.youtube.com/live_chat?is_popout=1&v=' + self.vid, 'https://www.youtube.com/watch?v=' + self.vid):
            h = requests.get(url, headers=cab, timeout=20).text
            d = _dados_iniciais(h)
            lc = _achar(d, 'liveChatRenderer') if d else None
            if lc:
                if lc.get('isReplay'):
                    raise Exception('essa live já terminou (só existe o replay do chat)')
                for x in lc.get('continuations', []):
                    k = x.get('invalidationContinuationData') or x.get('timedContinuationData') or x.get('reloadContinuationData')
                    if k and k.get('continuation'):
                        cont = k['continuation']; break
            if not cont:  # plano B: procura direto no texto da página
                i = h.find('"liveChatRenderer"')
                m = re.search(r'"continuation":"([^"]+)"', h[i:]) if i >= 0 else None
                cont = m.group(1) if m else ''
            if cont:
                break
        if not cont:
            raise Exception('não achei o chat dessa live (ela está ao vivo e com o chat ligado?)')
        k = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', h)
        v = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"', h)
        vd = re.search(r'"visitorData":"([^"]+)"', h) or re.search(r'"VISITOR_DATA":"([^"]+)"', h)
        self.key = k.group(1) if k else ''
        self.ver = v.group(1) if v else '2.20240101.00.00'
        self.visitor = vd.group(1) if vd else ''
        self.cont = cont

    def buscar(self):
        url = 'https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?prettyPrint=false' + ('&key=' + self.key if self.key else '')
        cli = {'clientName': 'WEB', 'clientVersion': self.ver, 'hl': 'pt-BR', 'gl': 'BR'}
        if getattr(self, 'visitor', ''):
            cli['visitorData'] = self.visitor
        r = requests.post(url, timeout=20, json={'context': {'client': cli}, 'continuation': self.cont},
                          headers=dict(UA, **{'Content-Type': 'application/json', 'Origin': 'https://www.youtube.com',
                                              'X-YouTube-Client-Name': '1', 'X-YouTube-Client-Version': self.ver,
                                              'Accept-Language': 'pt-BR,pt;q=0.9'}))
        if not r.ok:
            raise Exception('erro ' + str(r.status_code) + ' ao pedir o chat')
        d = r.json()
        c = (d.get('continuationContents') or {}).get('liveChatContinuation')
        if not c:
            er = (d.get('error') or {}).get('message')
            raise Exception('o chat terminou ou foi interrompido' + (' (' + er + ')' if er else ''))
        prox, ms = '', 1500
        for x in c.get('continuations', []):
            k = x.get('invalidationContinuationData') or x.get('timedContinuationData') or x.get('reloadContinuationData')
            if k and k.get('continuation'):
                prox = k['continuation']; ms = k.get('timeoutMs') or 1500
                break
        if not prox:
            raise Exception('o chat parou')
        self.cont = prox
        for a in c.get('actions', []):
            it = (a.get('addChatItemAction') or {}).get('item')
            m = it and it.get('liveChatTextMessageRenderer')
            if m:
                self.msg(m)
        return ms

    def msg(self, m):
        runs = (m.get('message') or {}).get('runs', [])
        partes = []
        for r in runs:
            if r.get('text'):
                partes.append(r['text'])
            elif r.get('emoji'):
                partes.append('' if r['emoji'].get('isCustomEmoji') else (r['emoji'].get('emojiId') or ''))
        txt = limpar(''.join(partes))
        if not txt or len(txt) > TAMANHO_MAX:
            return
        autor = (m.get('authorName') or {}).get('simpleText', '')
        fotos = (m.get('authorPhoto') or {}).get('thumbnails', [])
        self.add({'t': 'chat', 'a': autor, 'm': txt, 'bot': re.sub(r'^@', '', autor).lower() in IGNORAR,
                  'img': fotos[0]['url'] if fotos else '',
                  'url': ('https://www.youtube.com/channel/' + m['authorExternalChannelId']) if m.get('authorExternalChannelId') else ''})


chat = Chat()

def url_google(parte, gv):
    return ('https://translate.google.' + gv.get('tld', 'com') + '/translate_tts?ie=UTF-8&client=tw-ob&tl=' + gv.get('tl', gv['lang']) +
            '&ttsspeed=' + ('0.3' if gv.get('lenta') else '1') + '&q=' + quote(parte, safe=''))


def url_se(nome, parte):
    return 'https://api.streamelements.com/kappa/v2/speech?voice=' + quote(nome, safe='') + '&text=' + quote(parte, safe='')


def mascarar(k):
    return (k[:4] + '...' + k[-3:]) if k else ''


def plano(v, t, lang_prev=''):
    """Diz ao navegador COMO tocar: voz do aparelho, ou as partes do mp3 já limpas e cortadas."""
    id_ = str(v)
    if id_.startswith('d:'):
        return {'tipo': 'dev', 'v': id_, 'pitch': 1, 'rate': 1}
    if id_.startswith('dp:'):
        partes = id_.split(':'); e = ESTILOS.get(partes[1], {'pitch': 1, 'rate': 1})
        return {'tipo': 'dev', 'v': 'd:' + ':'.join(partes[2:]), 'pitch': e['pitch'], 'rate': e['rate']}
    if id_.startswith('se:'):
        q = id_[3:].split('@'); nome = q[0]; rate = float(q[1]) if len(q) > 1 else 1
        achada = next((x for x in CAT if x['id'] == id_), None)
        lang = (achada and achada['lang']) or lang_prev or 'pt-BR'
        pedacos = partir(humanizar(t, lang.startswith('pt')))
        return {'tipo': 'net', 'lang': lang, 'rate': rate, 'tom': rate != 1,
                'partes': ['/api/mp3?u=' + quote(url_se(nome, p), safe='') for p in pedacos]}
    gv = None
    if id_.isdigit():
        gv = GV['pt-lenta' if int(id_) == 1 else 'pt']
    elif id_.startswith('g:'):
        gv = GV.get(id_[2:])
    gv = gv or GV['pt']
    pedacos = partir(humanizar(t, gv['lang'].startswith('pt')))
    return {'tipo': 'net', 'lang': gv['lang'], 'rate': gv.get('rate', 1), 'tom': bool(gv.get('rate')) and gv['rate'] != 1,
            'partes': ['/api/mp3?u=' + quote(url_google(p, gv), safe='') for p in pedacos]}


def estado(desde):
    if not live_id:
        return {'linhas': [], 'ultimo': 0, 'chat': False, 'canal': None, 'sessao': ''}
    if chat.vid != live_id:
        chat.iniciar(live_id)
    d = chat.ler(desde)
    linhas = [dict(l, fala=texto_fala(l)) if l['t'] == 'chat' else l for l in d['linhas']]
    return {'linhas': linhas, 'ultimo': d['ultimo'], 'chat': d['chat'], 'canal': d['canal'], 'sessao': d['sessao']}


def atualizar_cfg(c):
    if 'voz' in c:
        v = c['voz']; cfgv['voz'] = int(v) if re.fullmatch(r'\d+', str(v)) else str(v)
    for k in ('vel', 'int'):
        if k in c: cfgv[k] = int(float(c[k]))
    cfgv['int'] = max(0, min(600, cfgv['int']))
    if 'vol' in c: cfgv['vol'] = max(0.0, min(1.0, float(c['vol'])))
    for k in ('nome', 'bots', 'ler', 'fundo'):
        if k in c: cfgv[k] = bool(c[k])
    if 'pal' in c: cfgv['pal'] = str(c['pal']).strip()[:20]
    salvar()


def vincular(link):
    global live_id
    l = (link or '').strip()
    if not l:
        return {'ok': False, 'msg': 'Cole o link da live primeiro.'}
    id_ = extrair_id(l)
    if not id_:
        return {'ok': False, 'msg': 'Não achei o ID da live nesse link.'}
    canal = info_live(id_)
    if not canal:
        return {'ok': False, 'msg': 'Não achei essa live. Confira o link (ou o acesso ao YouTube está bloqueado).'}
    live_id = id_; salvar(); chat.iniciar(id_, canal)
    return {'ok': True, 'live': id_, 'canal': canal}


def definir_chave(k):
    global chave_yt
    k = (k or '').strip()
    if k and len(k) < 20:
        return {'ok': False, 'msg': 'Essa chave parece curta demais. Confira e cole de novo.'}
    chave_yt = k; salvar()
    if live_id:
        chat.iniciar(live_id, chat.info)
    return {'ok': True, 'chave': mascarar(chave_yt)}


def baixar_mp3(u):
    host = (urlparse(u).hostname or '').lower()
    if urlparse(u).scheme != 'https' or not (host.startswith('translate.google.') or host == 'api.streamelements.com'):
        return None
    try:
        r = requests.get(u, headers=UA, timeout=15)
    except requests.RequestException:
        return None
    return r.content if r.ok and r.content else None


HTML = r"""<!doctype html>
<!-- Leitor de Live: site servido por Python (leitor_live_site.py). -->
<html lang="pt-BR"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
<meta name="theme-color" content="#0f1115">
<meta name="referrer" content="no-referrer">
<title>Leitor de Live</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--c2:#242934;--txt:#eef0f4;--mut:#9aa3b2;--verm:#e53935;--azul:#2f80ed;--verde:#2ecc71}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
[hidden]{display:none!important}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--txt);font-family:system-ui,Roboto,sans-serif;display:flex;flex-direction:column;height:100vh;height:100dvh;overflow:hidden}
header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 14px;background:var(--card)}
h1{font-size:18px;margin:0;white-space:nowrap}
.pills{display:flex;gap:6px;flex-wrap:nowrap;justify-content:flex-end;min-width:0}
.pill{font-size:12px;padding:4px 10px;border-radius:99px;background:#3a1717;color:#ff8a80}
.pill.on{background:#12351f;color:var(--verde)}
.pill{white-space:nowrap}
.pill.canal{display:flex;align-items:center;gap:6px;background:#1d2330;color:var(--txt);max-width:150px;text-decoration:none;min-width:0}
.pill.canal img{width:16px;height:16px;border-radius:50%;flex:none}
.pill.canal span{overflow:hidden;text-overflow:ellipsis}
.av{width:26px;height:26px;border-radius:50%;vertical-align:middle;margin-right:8px;background:var(--c2)}
.msg a{color:inherit;text-decoration:none}
#area{position:relative;flex:1;min-height:0}
#log{position:absolute;inset:0;overflow-y:auto;padding:10px 12px}
.msg{padding:9px 12px;margin-bottom:6px;background:var(--card);border-radius:12px;font-size:16px;line-height:1.35;overflow-wrap:anywhere}
.msg b{color:#8ab4ff;margin-right:6px}
.msg.bot{opacity:.5}
.sis{font-size:14px;color:var(--mut);text-align:center;margin:8px 4px;overflow-wrap:anywhere}
.sis.env{color:var(--verde)}
#fim{position:absolute;right:12px;bottom:10px;display:none;background:var(--azul);border-radius:99px;padding:10px 16px;min-height:0;box-shadow:0 2px 8px #0008}
button{font:inherit;font-size:16px;border:0;border-radius:12px;padding:12px 8px;color:#fff;background:var(--c2);min-height:48px}
button:active{filter:brightness(1.3)}
.verm{background:var(--verm)}.azul{background:var(--azul)}
nav{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;padding:8px 12px 0;background:var(--card)}
nav button{font-size:12px;padding:10px 1px}
footer{background:var(--card);padding:8px 12px calc(10px + env(safe-area-inset-bottom))}
#texto{width:100%;font-size:16px;padding:13px;border-radius:12px;border:0;background:#fff;color:#000;margin-bottom:8px}
.dupla{display:grid;grid-template-columns:1fr;gap:8px}
#folha{position:fixed;inset:0;display:none;z-index:10}
#folha.aberta{display:block}
.fundo{position:absolute;inset:0;background:#000a}
.painel{position:absolute;left:0;right:0;bottom:0;max-height:88vh;max-height:88dvh;overflow-y:auto;background:var(--card);border-radius:18px 18px 0 0;padding:14px 16px calc(18px + env(safe-area-inset-bottom))}
.topo{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.topo h2{margin:0;font-size:18px}
.x{min-height:40px;padding:6px 14px}
label.l{display:block;margin:12px 0 4px;color:var(--mut);font-size:14px}
select{width:100%;font-size:16px;padding:13px;border-radius:10px;border:0;background:var(--c2);color:var(--txt)}
input[type=range]{width:100%;height:34px;accent-color:var(--azul)}
.lin{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-top:1px solid var(--c2);font-size:16px}
.lin input{width:24px;height:24px;accent-color:var(--azul)}
.aviso{background:#2a2312;color:#ffe082;border-radius:10px;padding:12px;font-size:14px;margin:8px 0;overflow-wrap:anywhere}
ol{padding-left:20px;font-size:14px;color:var(--mut);line-height:1.5}
code{background:var(--c2);padding:2px 6px;border-radius:6px;color:var(--txt)}
#ytMsg{font-size:14px;color:#ffe082;margin:8px 0;min-height:18px}
.grande{width:100%;margin-top:8px}
.campo{width:100%;font-size:16px;padding:13px;border-radius:10px;border:0;background:#fff;color:#000}
.vatual{background:#12351f;color:var(--verde);border-radius:12px;padding:10px 12px;margin:6px 0 8px;font-size:15px;font-weight:600;overflow-wrap:anywhere}
.chips{display:flex;gap:6px;overflow-x:auto;padding:2px 0 8px;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{flex:none;min-height:36px;padding:6px 13px;border-radius:99px;font-size:13px;background:var(--c2);color:var(--txt)}
.chip.on{background:var(--azul)}
.vmsg{font-size:13px;color:#ffe082;min-height:18px;margin:2px 0 6px;overflow-wrap:anywhere}
#vozLista{max-height:50vh;max-height:50dvh;overflow-y:auto;overscroll-behavior:contain;margin:0 -4px 10px;padding:0 4px}
.vc{display:flex;align-items:center;gap:10px;background:var(--c2);border-radius:14px;padding:10px;margin-bottom:8px;border:2px solid transparent}
.vc.sel{border-color:var(--verde)}
.vc .play{flex:none;width:46px;height:46px;min-height:0;border-radius:50%;padding:0;background:var(--azul);font-size:18px}
.vc .vinfo{flex:1;min-width:0}
.vn{font-size:16px;font-weight:600;overflow-wrap:anywhere}
.vd{font-size:13px;color:var(--mut);margin-top:2px;line-height:1.3}
.tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}
.tags span{font-size:11px;padding:2px 8px;border-radius:99px;background:#2f3646;color:#c9d1e0}
.vc .usar{flex:none;min-height:40px;padding:8px 12px;font-size:13px;border-radius:10px}
.vc.sel .usar{background:var(--verde);color:#052e16;font-weight:700}
.vazio{color:var(--mut);font-size:14px;text-align:center;padding:16px 4px}
</style></head><body>
<header><h1>Leitor de Live</h1>
  <div class="pills"><span class="pill" id="pChat">Chat: offline</span><a class="pill canal" id="pCanal" hidden target="_blank" rel="noopener"><img id="pLogo" alt="" referrerpolicy="no-referrer"><span id="pNome"></span></a></div>
</header>
<div id="area"><div id="log"></div><button id="fim" onclick="irFim()">⬇ Ir para o fim</button></div>
<nav>
  <button id="bLer" onclick="alternarLer()">🔊 Lendo</button>
  <button onclick="pular()">⏭ Pular</button>
  <button onclick="abrir('voz')">🎙 Voz</button>
  <button onclick="abrir('yt')">▶ Live</button>
  <button onclick="reconectar()">🔄 Chat</button>
</nav>
<footer>
  <input type="text" id="texto" maxlength="200" placeholder="Escreva algo para falar..." enterkeyhint="send" autocomplete="off">
  <div class="dupla">
    <button class="azul" onclick="enviar('/api/falar')">🔊 Só falar</button>
    
  </div>
</footer>

<div id="folha">
  <div class="fundo" onclick="fechar()"></div>
  <div class="painel">
    <div id="pVoz">
      <div class="topo"><h2>Voz</h2><button class="x" onclick="fechar()">✕</button></div>
      <label class="l">Escolha a voz (toque em ▶ para ouvir antes)</label>
      <div id="vozAtual" class="vatual"></div>
      <div class="chips" id="vozFiltrosI"></div>
      <div class="chips" id="vozFiltrosT"></div>
      <div id="vozMsg" class="vmsg"></div>
      <div id="vozLista"></div>
      <select id="voz" onchange="cfg()" hidden></select>
      <button class="grande azul" onclick="testar()">▶ Testar voz</button>
      <label class="l">Velocidade: <span id="velv">0</span>%</label>
      <input type="range" id="vel" min="-50" max="100" value="0" oninput="velv.textContent=this.value" onchange="cfg()">
      <label class="l">Volume: <span id="volv">100</span>%</label>
      <input type="range" id="vol" min="0" max="100" value="100" oninput="volv.textContent=this.value" onchange="cfg()">
      <label class="lin"><span>Falar o nome de quem comentou</span><input type="checkbox" id="nome" checked onchange="cfg()"></label>
      <label class="l">Palavra depois do nome (ex.: disse, falou, comentou)</label>
      <input type="text" id="pal" class="campo" maxlength="20" placeholder="disse" oninput="cfg()" autocomplete="off">
      <label class="lin" style="margin-top:12px"><span>Não ler bots (Nightbot, Streamlabs...)</span><input type="checkbox" id="bots" checked onchange="cfg()"></label>
      <label class="lin"><span>Continuar lendo em segundo plano (jogo/outro app)</span><input type="checkbox" id="fundo" checked onchange="cfg()"></label>
      <label class="l">Intervalo entre as leituras</label>
      <select id="intSel" onchange="escolherInt()">
        <option value="0">Sem intervalo</option><option value="5">5 segundos</option><option value="10">10 segundos</option>
        <option value="20">20 segundos</option><option value="30">30 segundos</option><option value="60">1 minuto</option>
        <option value="-1">Personalizado</option>
      </select>
      <label class="l">Ou digite os segundos que quiser</label>
      <input type="number" id="intNum" min="0" max="600" inputmode="numeric" placeholder="Ex: 15" oninput="digitarInt()" style="width:100%;font-size:16px;padding:13px;border-radius:10px;border:0;background:#fff;color:#000">
    </div>

    <div id="painelYt" hidden>
      <div class="topo"><h2>Link da live</h2><button class="x" onclick="fechar()">✕</button></div>
      <div id="ytMsg"></div>
      <label class="l">Live do YouTube (cole o link ou o ID)</label>
      <input type="text" id="liveLink" placeholder="https://youtube.com/watch?v=..." style="width:100%;font-size:16px;padding:13px;border-radius:10px;border:0;background:#fff;color:#000">
      <button class="grande azul" onclick="vincularLive()">✔ OK</button>
      <div id="liveAtual" style="font-size:13px;color:var(--mut);margin:6px 0 12px"></div>
      <label class="l">Chave da API do YouTube (opcional)</label>
      <input type="text" id="chaveYt" class="campo" placeholder="Cole aqui a chave (AIza...)" autocomplete="off" autocapitalize="off" spellcheck="false">
      <button class="grande azul" onclick="salvarChave()">💾 Salvar chave</button>
      <div id="chaveEstado" style="font-size:13px;color:var(--mut);margin:6px 0 4px"></div>
      <ol>
        <li>Abra <code>console.cloud.google.com</code> e crie um projeto (grátis).</li>
        <li>Em <b>APIs e serviços → Biblioteca</b>, ative <b>YouTube Data API v3</b>.</li>
        <li>Em <b>Credenciais → Criar credenciais → Chave de API</b>, copie a chave e cole acima.</li>
      </ol>
      <div style="font-size:12px;color:var(--mut)">Sem a chave, o Python lê o chat direto do YouTube. A chave fica só neste aparelho.</div>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const log = $('log');
const LIMITE = 10;  // passou disso, apaga todos os comentários
const NOMES = ['Google (feminina)', 'Google lenta'];
let CAT = [];       // catálogo de vozes: vem do servidor Python (/api/vozes)
let ultimo = 0, colado = true, primeira = true, ocupado = false;
let cfgv = {voz:0, vel:0, vol:1, nome:true, bots:true, ler:true, int:0, pal:'disse', fundo:true};
let lendo = true, liveId = '', sessao = '', chaveEstado = '';
const jpost = (rota, corpo) => fetch(rota, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(corpo || {})}).then(r => r.json());
const ESTILOS = {
  grave:   {nome:'grave',   desc:'Tom bem grave e firme (depende de o aparelho aceitar ajuste de tom).', pitch:0.6,  rate:0.95, tags:['Grave','Adulta']},
  suave:   {nome:'suave',   desc:'Tom calmo e ritmo devagar, agradável de ouvir.',                      pitch:0.9,  rate:0.88, tags:['Suave']},
  jovem:   {nome:'jovem',   desc:'Tom mais agudo e animado, soa mais jovem.',                           pitch:1.4,  rate:1.08, tags:['Jovem']},
  animada: {nome:'animada', desc:'Rápida e cheia de energia.',                                          pitch:1.2,  rate:1.18, tags:['Jovem']},
  locutor: {nome:'locutor', desc:'Grave e firme, ritmo de locutor de rádio.',                           pitch:0.75, rate:1.05, tags:['Grave','Adulta']}
};
const PRE = {
  pt:'Olá! Eu sou esta voz. Posso ler os comentários da sua live.',
  en:'Hello! This is my voice. I can read your live chat comments.',
  es:'¡Hola! Esta es mi voz. Puedo leer los comentarios de tu directo.',
  fr:'Bonjour ! Voici ma voix. Je peux lire le chat de votre live.',
  it:'Ciao! Questa è la mia voce. Posso leggere i commenti della tua diretta.',
  de:'Hallo! Das ist meine Stimme. Ich kann den Chat deiner Live vorlesen.',
  ja:'こんにちは！これが私の声です。ライブのコメントを読み上げます。',
  ko:'안녕하세요! 제 목소리입니다. 라이브 채팅을 읽어 드릴게요.',
  ru:'Привет! Это мой голос. Я могу читать комментарии вашего эфира.',
  zh:'你好！这是我的声音。我可以朗读直播评论。',
  hi:'नमस्ते! यह मेरी आवाज़ है। मैं आपकी लाइव चैट पढ़ सकता हूँ।',
  ar:'مرحبًا! هذا صوتي. يمكنني قراءة تعليقات البث.'
};
function bandeira(l){
  l = (l || '').toLowerCase().replace('_', '-');
  const m = {'pt-br':'🇧🇷','pt-pt':'🇵🇹','en-us':'🇺🇸','en-gb':'🇬🇧','en-au':'🇦🇺','es-es':'🇪🇸','es-mx':'🇲🇽','es-us':'🌎'};
  if(m[l]) return m[l];
  const b = {pt:'🇧🇷', en:'🇺🇸', es:'🇪🇸', fr:'🇫🇷', it:'🇮🇹', de:'🇩🇪', ja:'🇯🇵', ko:'🇰🇷', ru:'🇷🇺', zh:'🇨🇳', hi:'🇮🇳', ar:'🌍'};
  return b[l.slice(0, 2)] || '🌐';
}
function garantirOpcao(id, rotulo){
  const sel = $('voz');
  if([...sel.options].some(o => o.value === id)) return;
  const o = document.createElement('option'); o.value = id; o.textContent = rotulo || id;
  if(id.startsWith('d:')) o.dataset.d = '1';
  sel.appendChild(o);
}
function todasVozes(){
  const lista = CAT.slice();
  if('speechSynthesis' in window){
    lista.push({id:'d:', nome:'Narrador do aparelho (padrão)', desc:'A voz padrão em português instalada no seu celular.', lang:'pt-BR', tags:['Aparelho'], motor:'dev'});
    Object.keys(ESTILOS).forEach(k => {
      const e = ESTILOS[k];
      lista.push({id:'dp:' + k + ':', nome:'Aparelho ' + e.nome, desc:e.desc, lang:'pt-BR', tags:['Aparelho'].concat(e.tags), motor:'dev'});
    });
    let vs = [];
    try{ vs = speechSynthesis.getVoices(); }catch(e){}
    vs.forEach(v => lista.push({id:'d:' + v.voiceURI, nome:v.name, desc:'Voz instalada no aparelho (' + v.lang + ')' + (v.localService ? ' - funciona sem internet.' : ' - precisa de internet.'), lang:v.lang, tags:['Aparelho'], motor:'dev'}));
  }
  return lista;
}

// ---- interface: filtros, cartões, ouvir e escolher ----
const FILTROS_I = [['todas','Todas'], ['pt','🇧🇷 Português'], ['en','🇺🇸 English'], ['es','🇪🇸 Español'], ['out','🌍 Outros idiomas'], ['ap','📱 Do aparelho']];
const FILTROS_T = ['Todas', 'Feminina', 'Masculina', 'Jovem', 'Adulta', 'Grave', 'Suave', 'Natural'];
let fI = 'todas', fT = 'Todas';
function passaI(v){
  const g = (v.lang || '').slice(0, 2).toLowerCase();
  if(fI === 'todas') return true;
  if(fI === 'ap') return v.motor === 'dev';
  if(fI === 'out') return !['pt', 'en', 'es'].includes(g);
  return g === fI;
}
function chip(rotulo, on, acao){
  const b = document.createElement('button'); b.className = 'chip' + (on ? ' on' : ''); b.textContent = rotulo; b.onclick = acao; return b;
}
function msgVoz(t){ $('vozMsg').textContent = t || ''; }
function cartao(v, atual){
  const c = document.createElement('div'); c.className = 'vc' + (v.id === atual ? ' sel' : '');
  const play = document.createElement('button'); play.className = 'play'; play.textContent = '▶'; play.setAttribute('aria-label', 'Ouvir ' + v.nome);
  play.onclick = () => ouvirVoz(v.id, play, v.lang);
  const info = document.createElement('div'); info.className = 'vinfo'; info.onclick = () => escolherVoz(v.id, v.nome);
  const n = document.createElement('div'); n.className = 'vn'; n.textContent = bandeira(v.lang) + ' ' + v.nome;
  const d = document.createElement('div'); d.className = 'vd'; d.textContent = v.desc;
  const tg = document.createElement('div'); tg.className = 'tags';
  v.tags.forEach(x => { const s = document.createElement('span'); s.textContent = x; tg.appendChild(s); });
  info.appendChild(n); info.appendChild(d); info.appendChild(tg);
  const usar = document.createElement('button'); usar.className = 'usar'; usar.textContent = v.id === atual ? '✔ Em uso' : 'Usar';
  usar.onclick = () => escolherVoz(v.id, v.nome);
  c.appendChild(play); c.appendChild(info); c.appendChild(usar);
  return c;
}
function renderVozes(){
  const box = $('vozLista'); if(!box) return;
  const atual = String(cfgv.voz), todas = todasVozes();
  const ach = todas.find(x => x.id === atual);
  $('vozAtual').textContent = '✔ Em uso: ' + (ach ? ach.nome : 'voz do aparelho');
  const cI = $('vozFiltrosI'), cT = $('vozFiltrosT'), sI = cI.scrollLeft, sT = cT.scrollLeft;
  cI.textContent = ''; cT.textContent = '';
  FILTROS_I.forEach(f => cI.appendChild(chip(f[1], fI === f[0], () => { fI = f[0]; renderVozes(); box.scrollTop = 0; })));
  FILTROS_T.forEach(r => cT.appendChild(chip(r, fT === r, () => { fT = r; renderVozes(); box.scrollTop = 0; })));
  cI.scrollLeft = sI; cT.scrollLeft = sT;
  const pos = box.scrollTop; box.textContent = '';
  const vis = todas.filter(v => passaI(v) && (fT === 'Todas' || v.tags.includes(fT)));
  if(!vis.length){ const e = document.createElement('div'); e.className = 'vazio'; e.textContent = 'Nenhuma voz com esse filtro.'; box.appendChild(e); }
  vis.forEach(v => box.appendChild(cartao(v, atual)));
  box.scrollTop = pos;
}
function escolherVoz(id, rotulo){
  garantirOpcao(id, rotulo);
  $('voz').value = id; cfg(); renderVozes(); msgVoz('');
}
function ouvirVoz(id, btn, lang){
  const frase = PRE[(lang || 'pt').slice(0, 2).toLowerCase()] || PRE.pt;
  document.querySelectorAll('#vozLista .play').forEach(b => { b.textContent = '▶'; });
  btn.textContent = '⏳'; msgVoz('');
  const volta = ok => { btn.textContent = '▶'; if(ok === false) msgVoz('Não consegui tocar essa voz agora (sem internet ou serviço fora do ar). Tente outra.'); };
  setTimeout(() => { if(btn.textContent === '⏳') btn.textContent = '▶'; }, 25000);
  fila.unshift({t: frase, v: id, lang: lang, fim: volta});
  pular(); proxima();
}



// vozes do próprio aparelho (Narrador / Google do Android etc.)
function listarAparelho(){
  const sel = $('voz');
  sel.querySelectorAll('option[data-d]').forEach(o => o.remove());
  const add = (valor, rotulo) => { const o = document.createElement('option'); o.value = valor; o.textContent = rotulo; o.dataset.d = '1'; sel.appendChild(o); };
  const salvo = String(cfgv.voz);
  if('speechSynthesis' in window){
    let vs = [];
    try{ vs = speechSynthesis.getVoices().filter(v => /^pt/i.test(v.lang)); }catch(e){}
    add('d:', '📱 Narrador do aparelho (padrão)');
    vs.forEach(v => add('d:' + v.voiceURI, '📱 ' + v.name));
  }
  sel.value = salvo;
  if(sel.value !== salvo && salvo.startsWith('d:')){ add(salvo, '📱 Voz do aparelho'); sel.value = salvo; }
  if(sel.value !== salvo) sel.value = '0';
}

log.addEventListener('scroll', () => {
  colado = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
  $('fim').style.display = colado ? 'none' : 'block';
});
function irFim(){ log.scrollTop = log.scrollHeight; }

function criar(l){
  const d = document.createElement('div');
  if(l.t === 'chat'){
    d.className = 'msg' + (l.bot ? ' bot' : '');
    const alvo = document.createElement(seguro(l.url) ? 'a' : 'span');
    if(alvo.tagName === 'A'){ alvo.href = l.url; alvo.target = '_blank'; alvo.rel = 'noopener'; }
    if(seguro(l.img)){ const im = document.createElement('img'); im.className = 'av'; im.src = l.img; im.alt = ''; im.referrerPolicy = 'no-referrer'; alvo.appendChild(im); }
    const b = document.createElement('b'); b.textContent = l.a; alvo.appendChild(b);
    d.appendChild(alvo); d.appendChild(document.createTextNode(l.m));
  } else {
    d.className = 'sis' + (l.t === 'env' ? ' env' : '');
    d.textContent = l.m;
  }
  return d;
}

function pill(id, ligado, texto){ const p = $(id); p.className = 'pill' + (ligado ? ' on' : ''); p.textContent = texto; }

// ---- áudio: toca aqui no navegador (funciona em qualquer celular) ----
const aud = new Audio(); const fila = []; let falando = false;
let fimAtual = null;   // encerra a fala que está tocando agora
let geracao = 0;       // sobe a cada Pausar/Pular: descarta o que ainda estava sendo gerado
let cortar = null;     // encerra a espera do intervalo
let keep = null, interagiu = false;
const SILENCIO = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
document.addEventListener('pointerdown', () => {
  interagiu = true; aud.src = SILENCIO; aud.play().catch(() => {}); manterAtivo();
}, {once:true});
document.addEventListener('visibilitychange', () => {
  if(!document.hidden){ manterAtivo(); atualizar(); proxima(); }
});

// Mantém o navegador "tocando" um áudio quase mudo, assim o Android não congela
// a página quando você está em outro app ou jogo (era isso que cortava a fala).
function criarSilencio(){
  const n = 8000, b = new Uint8Array(44 + n), dv = new DataView(b.buffer);
  const s = (o, t) => { for(let i = 0; i < t.length; i++) b[o + i] = t.charCodeAt(i); };
  s(0, 'RIFF'); dv.setUint32(4, 36 + n, true); s(8, 'WAVE'); s(12, 'fmt ');
  dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, 8000, true); dv.setUint32(28, 8000, true); dv.setUint16(32, 1, true); dv.setUint16(34, 8, true);
  s(36, 'data'); dv.setUint32(40, n, true);
  for(let i = 0; i < n; i++) b[44 + i] = 128 + (i % 2);
  return URL.createObjectURL(new Blob([b], {type:'audio/wav'}));
}
function manterAtivo(){
  if(!interagiu) return;
  if(cfgv.fundo && lendo){
    if(!keep){ keep = new Audio(criarSilencio()); keep.loop = true; keep.volume = 0.05; }
    keep.play().catch(() => {});
    if('mediaSession' in navigator){
      try{
        navigator.mediaSession.metadata = new MediaMetadata({title:'Leitor de Live', artist:'Lendo o chat em voz alta'});
        navigator.mediaSession.setActionHandler('nexttrack', pular);
      }catch(e){}
    }
  } else if(keep){ keep.pause(); }
}

function falar(t){ if(fila.length && fila[fila.length - 1] === t) return; if(fila.length >= (cfgv.int > 0 ? 5 : 15)) fila.shift(); fila.push(t); proxima(); }
function testar(){
  const p = (cfgv.pal || '').trim();
  falar((cfgv.nome ? (p ? 'Maria ' + p + ': ' : 'Maria, ') : '') + 'esta é a voz escolhida.');
}
function soltar(){ aud.onended = aud.onerror = aud.onpause = null; aud.pause(); aud.removeAttribute('src'); aud.load(); }
function aviso(t){ log.appendChild(criar({t:'sis', m:t})); if(colado) irFim(); }

// Toca o mp3 até o FIM de verdade. Se o sistema pausar (jogo/outro app pegou o áudio),
// tenta continuar de onde parou em vez de cortar a frase.
function tocarMp3(url, taxa){
  return new Promise(fim => {
    let feito = false, erro = false, ult = -1, parado = 0, seg = 0, vigia;
    const acabar = () => { if(feito) return; feito = true; clearInterval(vigia); if(fimAtual === acabar) fimAtual = null; fim(!erro); };
    const retomar = () => { if(!feito) aud.play().catch(() => {}); };
    fimAtual = acabar;
    aud.onended = acabar;
    aud.onerror = () => { erro = true; acabar(); };
    aud.onpause = () => { if(!feito && !aud.ended) setTimeout(retomar, 300); };
    aud.defaultPlaybackRate = taxa; aud.src = url; aud.volume = cfgv.vol; aud.playbackRate = taxa;
    vigia = setInterval(() => {
      if(feito) return;
      seg++;
      if(aud.ended){ acabar(); return; }
      if(seg >= 8 && aud.currentTime === 0){ erro = true; acabar(); return; }  // não começou a tocar: a voz não respondeu
      if(aud.paused){ retomar(); }
      else {
        if(aud.currentTime === ult) parado++; else { parado = 0; ult = aud.currentTime; }
      }
      const dur = (isFinite(aud.duration) && aud.duration > 0) ? aud.duration : 20;
      if(parado >= 15 || seg > dur / Math.max(taxa, 0.5) * 1.5 + 20) acabar();
    }, 1000);
    aud.play().catch(e => { if(e && e.name === 'NotAllowedError'){ aviso('O navegador bloqueou o áudio. Toque na tela e tente de novo.'); acabar(); } });
  });
}

// Voz do aparelho (Narrador / Google do Android)
function falarAparelho(t, taxa, v, pitch = 1, lang = 'pt-BR'){
  return new Promise(fim => {
    if(!('speechSynthesis' in window)){ aviso('Este navegador não tem a voz do aparelho.'); fim(); return; }
    let feito = false, lim;
    const acabar = () => { if(feito) return; feito = true; clearTimeout(lim); if(fimAtual === parar) fimAtual = null; fim(); };
    const parar = () => { try{ speechSynthesis.cancel(); }catch(e){} acabar(); };
    fimAtual = parar;
    const u = new SpeechSynthesisUtterance(t);
    u.lang = lang; u.rate = Math.max(0.1, Math.min(4, taxa)); u.pitch = pitch; u.volume = cfgv.vol;
    const id = v.slice(2);
    if(id){
      const achada = speechSynthesis.getVoices().find(x => x.voiceURI === id || x.name === id);
      if(achada){ u.voice = achada; u.lang = achada.lang; }
    }
    u.onend = acabar; u.onerror = acabar;
    lim = setTimeout(acabar, 8000 + t.length * 150 / taxa);
    try{ speechSynthesis.cancel(); speechSynthesis.speak(u); }catch(e){ acabar(); }
  });
}


function tomAudio(mudar){
  try{ aud.preservesPitch = !mudar; aud.webkitPreservesPitch = !mudar; aud.mozPreservesPitch = !mudar; }catch(e){}
}
async function tocarPartes(partes, mk, taxa, g, mudarTom){
  if(!partes.length) return true;
  tomAudio(mudarTom);
  let ok = true;
  for(const p of partes){
    if(g !== geracao) break;
    ok = await tocarMp3(mk(p), Math.max(0.5, Math.min(2.5, taxa)));
    soltar();
    if(!ok) break;
  }
  tomAudio(false);
  return ok;
}
async function proxima(){
  if(falando || !fila.length) return;
  falando = true;
  const item = fila.shift();
  const previa = typeof item !== 'string';
  const t = previa ? item.t : item;
  const v = previa ? item.v : cfgv.voz, g = geracao;
  const taxa = Math.max(0.5, Math.min(2, 1 + cfgv.vel / 100));
  let ok = true;
  try{
    ok = await tocarVoz(v, t, taxa, g, previa ? item.lang : '');
    if(cfgv.int > 0 && g === geracao && !previa) await esperar(cfgv.int * 1000);
  }catch(e){ soltar(); ok = false; }
  if(previa && item.fim){ try{ item.fim(ok); }catch(e){} }
  falando = false; proxima();
}
function esperar(ms){ return new Promise(r => { const t = setTimeout(() => { cortar = null; r(); }, ms); cortar = () => { clearTimeout(t); cortar = null; r(); }; }); }
function pular(){
  geracao++;
  if(fimAtual) fimAtual();
  try{ aud.pause(); }catch(e){}
  if(cortar) cortar();
}
function escolherInt(){ const v = +$('intSel').value; if(v >= 0){ $('intNum').value = v; } cfg(); }
function digitarInt(){
  const v = $('intNum').value, o = [...$('intSel').options].find(x => x.value === String(+v));
  $('intSel').value = (v !== '' && o) ? o.value : '-1'; cfg();
}

function mostrarLer(){ const b = $('bLer'); b.textContent = lendo ? '🔊 Lendo' : '🔇 Pausado'; b.className = lendo ? '' : 'verm'; }
function alternarLer(){ lendo = !lendo; if(!lendo){ fila.length = 0; pular(); } mostrarLer(); cfg(); }

function enviar(rota){
  const campo = $('texto'), t = campo.value.trim();
  if(!t) return;
  if(rota === '/api/falar'){ falar(t); campo.value = ''; return; }
  fetch(rota, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({texto: t})});
  campo.value = '';
  if(navigator.vibrate) navigator.vibrate(20);
}
$('texto').addEventListener('keydown', e => { if(e.key === 'Enter'){ enviar('/api/falar'); } });

function abrir(q){
  $('folha').classList.add('aberta');
  $('pVoz').hidden = q !== 'voz'; $('painelYt').hidden = q !== 'yt';
  if(q === 'yt') atualizarYt();
  if(q === 'voz') renderVozes();
}
function fechar(){ $('folha').classList.remove('aberta'); }
function msg(t){ $('ytMsg').textContent = t; }

function seguro(u){ return typeof u === 'string' && /^https?:\/\//i.test(u); }
function atualizarYt(){ $('liveAtual').textContent = liveId ? 'Live atual: ' + liveId : 'Nenhuma live vinculada ainda.'; }
function mostrarCanal(c){
  const p = $('pCanal');
  if(!c || !c.nome){ p.hidden = true; return; }
  p.hidden = false; $('pNome').textContent = c.nome;
  const im = $('pLogo');
  if(seguro(c.logo)){ im.src = c.logo; im.hidden = false; } else { im.hidden = true; }
  if(seguro(c.url)){ p.href = c.url; } else { p.removeAttribute('href'); }
}

// ---- o servidor Python lê o chat, limpa o texto e monta as vozes; aqui só mostra e toca ----
async function atualizar(){
  if(ocupado) return; ocupado = true;
  try{
    if(!liveId){ pill('pChat', false, 'Chat: offline'); mostrarCanal(null); return; }
    const meu = liveId;
    const d = await (await fetch('/api/estado?desde=' + ultimo)).json();
    if(meu !== liveId) return;
    pill('pChat', d.chat, d.chat ? 'Chat: online' : 'Chat: offline');
    mostrarCanal(d.canal);
    if(d.sessao && d.sessao !== sessao){ sessao = d.sessao; ultimo = 0; primeira = true; log.innerHTML = ''; return; }
    for(const l of d.linhas){
      log.appendChild(criar(l));
      if(!primeira && l.t === 'chat' && cfgv.ler && !(l.bot && cfgv.bots) && l.fala){ falar(l.fala); }
    }
    primeira = false;
    if(log.querySelectorAll('.msg').length > LIMITE){ log.innerHTML = ''; }
    if(d.linhas.length && colado){ irFim(); }
    ultimo = d.ultimo;
  }catch(e){ pill('pChat', false, 'Sem conexão'); }
  finally{ ocupado = false; }
}

// toca "t" com a voz "v": o servidor Python devolve o plano (partes do mp3 ou voz do aparelho)
async function tocarVoz(v, t, taxa, g, langPrev){
  let p = null;
  try{ p = await (await fetch('/api/plano?v=' + encodeURIComponent(v) + '&t=' + encodeURIComponent(t) + '&lang=' + encodeURIComponent(langPrev || ''))).json(); }catch(e){}
  if(p && p.tipo === 'dev'){ await falarAparelho(t, taxa * p.rate, p.v, p.pitch); return true; }
  let ok = false; const lang = (p && p.lang) || langPrev || 'pt-BR';
  if(p && p.tipo === 'net') ok = await tocarPartes(p.partes, u => u, taxa * p.rate, g, p.tom);
  if(!ok && g === geracao){
    aviso('A voz escolhida não respondeu. Usando a voz do aparelho.');
    await falarAparelho(t, taxa, 'd:', 1, lang);
  }
  return ok;
}

function cfg(){
  const vz = $('voz').value;
  cfgv = {voz: /^\d+$/.test(vz) ? +vz : (vz || 0), vel: +$('vel').value, vol: +$('vol').value / 100,
          ler: lendo, nome: $('nome').checked, bots: $('bots').checked,
          int: Math.max(0, Math.min(600, +$('intNum').value || 0)),
          pal: $('pal').value.trim().slice(0, 20), fundo: $('fundo').checked};
  aud.volume = cfgv.vol;
  jpost('/api/cfg', cfgv).catch(() => {});
  manterAtivo();
}

function mostrarChave(){
  $('chaveEstado').textContent = chaveEstado ? '✔ Chave salva neste aparelho (' + chaveEstado + ')' : 'Nenhuma chave salva.';
}
async function salvarChave(){
  const k = $('chaveYt').value.trim();
  const r = await jpost('/api/chave', {chave: k});
  if(!r.ok){ msg(r.msg); return; }
  chaveEstado = r.chave; $('chaveYt').value = ''; mostrarChave();
  msg(k ? '✔ Chave salva. Reconectando o chat...' : 'Chave removida.');
  if(liveId){ ultimo = 0; sessao = ''; primeira = true; log.innerHTML = ''; }
}

async function vincularLive(){
  const l = $('liveLink').value.trim();
  if(l) msg('Verificando...');
  try{
    const r = await jpost('/api/live', {link: l});
    if(!r.ok){ msg(r.msg); return; }
    liveId = r.live; ultimo = 0; sessao = ''; primeira = true; log.innerHTML = ''; fila.length = 0;
    $('liveLink').value = ''; mostrarCanal(r.canal); atualizarYt();
    msg('✔ Verificado! Live de ' + (r.canal.nome || 'canal') + ' vinculada.');
    falar('Live verificada!');
    setTimeout(() => { fechar(); msg(''); }, 1300);
    atualizar();
  }catch(e){ msg('Erro ao verificar o link.'); }
}
function reconectar(){
  if(!liveId){ abrir('yt'); return; }
  jpost('/api/reconectar');
}

async function iniciar(){
  const r = await (await fetch('/api/cfg')).json();
  Object.assign(cfgv, r.cfg); lendo = cfgv.ler; liveId = r.live || ''; chaveEstado = r.chave || '';
  CAT = await (await fetch('/api/vozes')).json();
  NOMES.forEach((n, i) => { const o = document.createElement('option'); o.value = i; o.textContent = n; $('voz').appendChild(o); });
  CAT.forEach(v => { if(!/^\d+$/.test(v.id)) garantirOpcao(v.id, v.nome); });
  Object.keys(ESTILOS).forEach(k => garantirOpcao('dp:' + k + ':', 'Aparelho ' + ESTILOS[k].nome));
listarAparelho();
if('speechSynthesis' in window){ speechSynthesis.onvoiceschanged = () => { listarAparelho(); renderVozes(); }; }
renderVozes();
$('vel').value = cfgv.vel; $('velv').textContent = cfgv.vel;
$('vol').value = Math.round(cfgv.vol * 100); $('volv').textContent = $('vol').value;
$('nome').checked = cfgv.nome; $('bots').checked = cfgv.bots; mostrarLer();
$('pal').value = cfgv.pal; $('fundo').checked = cfgv.fundo;
$('intNum').value = cfgv.int;
$('intSel').value = [...$('intSel').options].some(o => o.value === String(cfgv.int)) ? String(cfgv.int) : '-1';

  mostrarChave();
  if(!liveId){ aviso('Toque em ▶ Live e cole o link da sua live.'); }
  setInterval(atualizar, 1500);
  atualizar();
}
iniciar();
</script>
</body></html>
"""


class Pagina(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def enviar(self, codigo, corpo, tipo='application/json; charset=utf-8'):
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo, ensure_ascii=False)
        if isinstance(corpo, str):
            corpo = corpo.encode('utf-8')
        self.send_response(codigo)
        self.send_header('Content-Type', tipo); self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers(); self.wfile.write(corpo)

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ('/', '/index.html'):
                self.enviar(200, HTML, 'text/html; charset=utf-8')
            elif u.path == '/api/estado':
                self.enviar(200, estado(int(q.get('desde', 0) or 0)))
            elif u.path == '/api/cfg':
                self.enviar(200, {'cfg': cfgv, 'live': live_id, 'chave': mascarar(chave_yt)})
            elif u.path == '/api/vozes':
                self.enviar(200, CAT)
            elif u.path == '/api/plano':
                self.enviar(200, plano(q.get('v', '0'), q.get('t', ''), q.get('lang', '')))
            elif u.path == '/api/mp3':
                dados = baixar_mp3(q.get('u', ''))
                if dados: self.enviar(200, dados, 'audio/mpeg')
                else: self.enviar(502, {'erro': 'sem áudio'})
            else:
                self.enviar(404, {'erro': 'não encontrado'})
        except Exception as e:
            self.enviar(500, {'erro': str(e)})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get('Content-Length') or 0)
            c = json.loads(self.rfile.read(n) or b'{}')
            if u.path == '/api/cfg':
                atualizar_cfg(c); self.enviar(200, {'ok': True})
            elif u.path == '/api/live':
                self.enviar(200, vincular(c.get('link')))
            elif u.path == '/api/chave':
                self.enviar(200, definir_chave(c.get('chave')))
            elif u.path == '/api/reconectar':
                if live_id: chat.iniciar(live_id, chat.info)
                self.enviar(200, {'ok': True})
            else:
                self.enviar(404, {'erro': 'não encontrado'})
        except Exception as e:
            self.enviar(500, {'erro': str(e)})


def main():
    ap = argparse.ArgumentParser(description='Leitor de Live (site em Python)')
    ap.add_argument('--host', default='127.0.0.1'); ap.add_argument('--porta', type=int, default=8000)
    a = ap.parse_args()
    if live_id:
        chat.iniciar(live_id)
    srv = ThreadingHTTPServer((a.host, a.porta), Pagina); srv.daemon_threads = True
    url = 'http://%s:%d' % ('127.0.0.1' if a.host in ('0.0.0.0', '') else a.host, a.porta)
    print('Leitor de Live rodando em', url, '(Ctrl+C para parar)')
    try:
        if shutil.which('termux-open-url'): subprocess.Popen(['termux-open-url', url])
        else: webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nAté mais!')


if __name__ == '__main__':
    main()
