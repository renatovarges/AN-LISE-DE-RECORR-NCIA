"""
Painel por posição — rodada obrigatória
Uso: python painel.py <n_jogos> <rodada>
Ex:  python painel.py 5 12
     python painel.py 10 13
"""
import sys, os, unicodedata, re
sys.path.insert(0, os.path.dirname(__file__))
from collections import defaultdict
from motor import records, SCOUTS_POS, scout_hit, mv_lookup, atk_lookup, nome_id_lookup
from elegibilidade import construir_lookup_elegibilidade, STATUS_PROVAVEL

# ── PATHS (absolutos para garantir carregamento no Playwright) ─────────────────
BASE_DIR   = os.path.abspath(os.path.dirname(__file__)).replace("\\", "/")
_FONTS_URL = f"file:///{BASE_DIR}/fonts"
_LOGOS_URL = f"file:///{BASE_DIR}/logos"
_TEAMS_URL = f"file:///{BASE_DIR}/teams"

# ── CONFIG ────────────────────────────────────────────────────────────────────
AMOSTRA_MIN = 3

ORDEM_POSICOES = [
    "GOLEIRO", "LATERAL_D", "LATERAL_E", "ZAGUEIRO",
    "VOLANTE", "MEIA", "PONTA_D", "PONTA_E", "ATACANTE",
]
LABEL_POSICAO = {
    "GOLEIRO":   "Goleiros",
    "LATERAL_D": "Lateral Direito",
    "LATERAL_E": "Lateral Esquerdo",
    "ZAGUEIRO":  "Zagueiros",
    "VOLANTE":   "Volantes",
    "MEIA":      "Meias",
    "PONTA_D":   "Ponta Direita",
    "PONTA_E":   "Ponta Esquerda",
    "ATACANTE":  "Atacante Central",
}
DISPLAY_NAME = {
    "ATHLETICO-PR": "Athletico-PR",
    "ATLÉTICO-MG":  "Atlético-MG",
    "BAHIA":        "Bahia",
    "BOTAFOGO":     "Botafogo",
    "CHAPECOENSE":  "Chapecoense",
    "CORINTHIANS":  "Corinthians",
    "CORITIBA":     "Coritiba",
    "CRUZEIRO":     "Cruzeiro",
    "FLAMENGO":     "Flamengo",
    "FLUMINENSE":   "Fluminense",
    "GRÊMIO":       "Grêmio",
    "INTER":        "Internacional",
    "MIRASSOL":     "Mirassol",
    "PALMEIRAS":    "Palmeiras",
    "RB BRAGANTINO":"RB Bragantino",
    "REMO":         "Remo",
    "SANTOS":       "Santos",
    "SÃO PAULO":    "São Paulo",
    "VASCO":        "Vasco",
    "VITÓRIA":      "Vitória",
}
def dn(k): return DISPLAY_NAME.get(k, k.title())

COR_HEX = {"verde": "#22c55e", "amarelo": "#fbbf24", "vermelho": "#f87171"}

# Bridge: motor usa nomes COM acento; elegibilidade.py usa SEM acento.
# Para não tocar em elegibilidade.py, traduzimos aqui.
_MOTOR_TO_ELEG = {
    "SÃO PAULO":   "SAO PAULO",
    "GRÊMIO":      "GREMIO",
    "VITÓRIA":     "VITORIA",
    "ATLÉTICO-MG": "ATLETICO-MG",
}
def _eleg_key(team):
    return _MOTOR_TO_ELEG.get(team, team)

# ── FOTOS DOS JOGADORES (tcc_fotos_jogadores.html) ────────────────────────────
import json as _json
_FOTOS_TEAM_MAP = {
    "RB BRAGANTINO":  "BRAGANTINO",
    "INTER":          "INTERNACIONAL",
}
def _carregar_fotos():
    path = os.path.join(BASE_DIR.replace("/", os.sep), "tcc_fotos_jogadores.html")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"const CLUBES\s*=\s*(\{.*?\});\s*\n", html, re.DOTALL)
    if not m:
        return {}
    try:
        return _json.loads(m.group(1))
    except Exception:
        return {}
_FOTOS = _carregar_fotos()

def _norm_nome(s):
    s = (s or "").strip().upper()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def foto_jogador(motor_time, apelido):
    """Retorna URL da foto do jogador ou '' se não encontrado."""
    fkey = _FOTOS_TEAM_MAP.get(motor_time, motor_time)
    clube = _FOTOS.get(fkey, {})
    if not clube:
        return ""
    nome_up = (apelido or "").strip().upper()
    if nome_up in clube:
        return clube[nome_up]
    alvo = _norm_nome(apelido)
    for k, v in clube.items():
        if _norm_nome(k) == alvo:
            return v
    return ""

SCOUT_EXTENSO = {
    "50%SG": "JOGOS SEM SOFRER GOL",
    "3DEF":  "3 OU MAIS DEFESAS",
    "75%DE": "APROVEITAMENTO DE DEFESAS",
    "1PG":   "PARTICIPAÇÃO EM GOL",
    "2DS":   "DESARMES",
    "3FIN":  "FINALIZAÇÕES",
}

# ── SCOUT PARAMETRIZÁVEL ──────────────────────────────────────────────────────
# Aceita códigos de limiar arbitrários:
#   count: "NDS", "NDE", "NDEF" (=DE), "NPG", "NFIN", "NG", "NA", "NFD"
#   pct:   "N%SG" (binário SG≥1), "N%DE" (aproveitamento ≥N%)
_RE_COUNT = re.compile(r"^(\d+)([A-Z]+)$")
_RE_PCT   = re.compile(r"^(\d+)%(DE|SG)$")

_METRIC_GET = {
    "DS":  lambda r: r["DS"],
    "DE":  lambda r: r["DE"],
    "DEF": lambda r: r["DE"],
    "PG":  lambda r: r["G"] + r["A"],
    "FIN": lambda r: r["FD"] + r["FF"] + r["FT"],
    "G":   lambda r: r["G"],
    "A":   lambda r: r["A"],
    "FD":  lambda r: r["FD"],
    "FF":  lambda r: r["FF"],
    "FT":  lambda r: r["FT"],
}
_METRIC_NOME = {
    "DS":  "DESARMES",
    "DE":  "DEFESAS",
    "DEF": "DEFESAS",
    "PG":  "PARTICIPAÇÕES EM GOL",
    "FIN": "FINALIZAÇÕES",
    "G":   "GOLS",
    "A":   "ASSISTÊNCIAS",
    "FD":  "FINALIZAÇÕES CERTAS",
    "FF":  "FINALIZAÇÕES PARA FORA",
    "FT":  "FINALIZAÇÕES NA TRAVE",
}

def parse_scout(code):
    """(kind, metric, threshold) ou None."""
    m = _RE_PCT.match(code)
    if m:
        return ("pct", m.group(2), int(m.group(1)))
    m = _RE_COUNT.match(code)
    if m:
        return ("count", m.group(2), int(m.group(1)))
    return None

def scout_hit_dynamic(r, code):
    p = parse_scout(code)
    if not p:
        return scout_hit(r, code)
    kind, metric, thr = p
    if kind == "count":
        fn = _METRIC_GET.get(metric)
        return bool(fn and fn(r) >= thr)
    if metric == "SG":
        return r["SG"] >= 1
    if metric == "DE":
        denom = r["FD"] + r["GS"]
        rate = (r["FD"] / denom * 100) if denom > 0 else 0.0
        return rate >= thr
    return False

def _metric_value(r, code):
    p = parse_scout(code)
    if not p:
        if code == "1PG":   return r["G"] + r["A"]
        if code == "2DS":   return r["DS"]
        if code == "3DEF":  return r["DE"]
        if code == "3FIN":  return r["FD"] + r["FF"] + r["FT"]
        if code == "75%DE": return r["FD"]
        if code == "50%SG": return r["SG"]
        return 0.0
    _, metric, _ = p
    if metric in _METRIC_GET:
        return _METRIC_GET[metric](r)
    if metric == "SG": return r["SG"]
    return 0.0

def _is_team_only(code):
    """Scouts sempre agregados por time (nunca por jogador)."""
    p = parse_scout(code)
    if not p: return code == "50%SG"
    kind, metric, _ = p
    return kind == "pct" and metric == "SG"

def _is_team_fallback(code):
    """Scouts que aceitam time como fallback quando nenhum jogador tem recorrência."""
    p = parse_scout(code)
    if not p: return code == "1PG"
    kind, metric, _ = p
    return kind == "count" and metric == "PG"

def scout_titulo(code):
    if code in SCOUT_EXTENSO:
        return SCOUT_EXTENSO[code]
    p = parse_scout(code)
    if not p:
        return code
    kind, metric, n = p
    if kind == "count":
        nome = _METRIC_NOME.get(metric, metric)
        if metric == "PG" and n == 1:
            return "PARTICIPAÇÃO EM GOL"
        return f"{n} OU MAIS {nome}"
    if metric == "SG":
        return "JOGOS SEM SOFRER GOL"
    if metric == "DE":
        return f"APROVEITAMENTO DE DEFESAS ≥ {n}%"
    return code

# ── LEGENDA CONTEXTUAL ───────────────────────────────────────────────────────
_POS_PLURAL_LEG = {
    "GOLEIRO":   "goleiros",
    "LATERAL_D": "laterais direitos",
    "LATERAL_E": "laterais esquerdos",
    "ZAGUEIRO":  "zagueiros",
    "VOLANTE":   "volantes",
    "MEIA":      "meias",
    "PONTA_D":   "pontas direitas",
    "PONTA_E":   "pontas esquerdas",
    "ATACANTE":  "atacantes",
}

# Referência à posição adversária (para texto cedido)
_POS_ADV_LEG = {
    "GOLEIRO":   "o goleiro adversário",
    "LATERAL_D": "laterais direitos adversários",
    "LATERAL_E": "laterais esquerdos adversários",
    "ZAGUEIRO":  "zagueiros adversários",
    "VOLANTE":   "volantes adversários",
    "MEIA":      "meias adversários",
    "PONTA_D":   "pontas direitas adversárias",
    "PONTA_E":   "pontas esquerdas adversárias",
    "ATACANTE":  "atacantes adversários",
}

def _quant_scout(code):
    """Fragmento quantitativo: 'pelo menos 2 desarmes', 'jogo sem sofrer gol', etc."""
    if code == "50%SG": return "jogo sem sofrer gol"
    if code == "75%DE": return "aproveitamento de 75% ou mais nas defesas"
    if code == "3DEF":  return "pelo menos 3 defesas"
    if code == "2DS":   return "pelo menos 2 desarmes"
    if code == "1PG":   return "ao menos 1 participação em gol (gol ou assistência)"
    if code == "3FIN":  return "ao menos 3 finalizações"
    p = parse_scout(code)
    if not p:
        return code
    kind, metric, thr = p
    nome = _METRIC_NOME.get(metric, metric).lower()
    if kind == "count":
        return f"pelo menos {thr} {nome}"
    if metric == "SG":
        return "jogo sem sofrer gol"
    if metric == "DE":
        return f"aproveitamento de {thr}% ou mais nas defesas"
    return code

def _juntar_textos(lista):
    if len(lista) == 1: return lista[0]
    if len(lista) == 2: return f"{lista[0]} ou {lista[1]}"
    return ", ".join(lista[:-1]) + f" ou {lista[-1]}"

def gerar_legenda_html(pos, scouts_ativos, n_jogos, mando_filter):
    """Legenda técnica e objetiva: frase quantitativa por coluna."""
    pos_plural = _POS_PLURAL_LEG.get(pos, LABEL_POSICAO.get(pos, pos).lower() + "s")
    pos_adv    = _POS_ADV_LEG.get(pos, pos_plural + " adversários")

    if mando_filter == "por_mando":
        mando_conq = "no mando desta rodada"
        mando_ced  = "no mesmo mando desta rodada"
    else:
        mando_conq = "em geral (casa e fora)"
        mando_ced  = "em geral (casa e fora)"

    quant_parts = [f"<strong>{_quant_scout(s)}</strong>" for s in scouts_ativos]
    quant_str   = _juntar_textos(quant_parts)

    so_time = all(_is_team_only(s) for s in scouts_ativos)
    suj     = "os <strong>times</strong>" if so_time else f"os <strong>{pos_plural}</strong>"

    texto_conq = (
        f"Percentual das vezes em que {suj} em destaque <strong>conquistaram</strong> "
        f"{quant_str} nos últimos <strong>{n_jogos} jogos</strong> {mando_conq}."
    )
    texto_ced = (
        f"Percentual das vezes em que os <strong>times</strong> em destaque "
        f"<strong>cederam</strong> {quant_str} para <strong>{pos_adv}</strong> "
        f"nos últimos <strong>{n_jogos} jogos</strong> {mando_ced}."
    )
    texto_rec = (
        "Técnica avançada de análise de dados e desempenho no futebol que busca identificar "
        "<strong>padrões repetidos</strong>, comportamentos ou eventos técnico-táticos que "
        "se repetem ciclicamente ao longo de uma sequência de jogos de um time ou jogador. "
        "<span class=\"legenda-credito\">Boa parte do que aprendi sobre recorrência foi com meu amigo Fernando Pardal.</span>"
    )

    return f"""
  <div class="legenda-section">
    <div class="legenda-titulo">&#128204; COMO LER ESTA ARTE</div>
    <div class="legenda-cols">

      <div class="legenda-col">
        <div class="legenda-tag leg-conq">&#127885; CONQUISTADO</div>
        <p class="legenda-texto">{texto_conq}</p>
      </div>

      <div class="legenda-col">
        <div class="legenda-tag leg-ced">&#127919; CEDIDO</div>
        <p class="legenda-texto">{texto_ced}</p>
      </div>

      <div class="legenda-col legenda-col-rec">
        <div class="legenda-tag leg-rec">&#128260; RECORRÊNCIA</div>
        <p class="legenda-texto">{texto_rec}</p>
      </div>

    </div>
  </div>"""

# ── LOGOS ─────────────────────────────────────────────────────────────────────
_LOGO_MAP = {
    "athletico_pr":    "athletico_pr.png",
    "atletico_mg":     "atletico_mg.png",
    "bahia":           "bahia.png",
    "botafogo":        "botafogo.png",
    "chapecoense":     "chapecoense.png",
    "corinthians":     "corinthians.png",
    "coritiba":        "coritiba.png",
    "cruzeiro":        "cruzeiro.png",
    "flamengo":        "flamengo.png",
    "fluminense":      "fluminense.png",
    "gremio":          "gremio.png",
    "inter":           "internacional.png",
    "internacional":   "internacional.png",
    "mirassol":        "mirassol.png",
    "palmeiras":       "palmeiras.png",
    "rb_bragantino":   "red_bull_bragantino.png",
    "remo":            "remo.png",
    "santos":          "santos.png",
    "sao_paulo":       "sao_paulo.png",
    "vasco":           "vasco.png",
    "vitoria":         "vitoria.png",
}
def _slug(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "_", s.lower()).strip("_")

def get_logo_url(k):
    """Retorna URL absoluta do escudo ou None."""
    s = _slug(k)
    f = _LOGO_MAP.get(s)
    if not f:
        for key, val in _LOGO_MAP.items():
            if s.startswith(key) or key.startswith(s):
                f = val; break
    if f:
        p = os.path.join(BASE_DIR.replace("/", os.sep), "teams", f)
        if os.path.exists(p):
            return f"{_TEAMS_URL}/{f}"
    return None

def shield_img(k):
    url = get_logo_url(k)
    if url:
        return f'<div class="shield-wrap"><img src="{url}" class="shield" alt="{dn(k)}"></div>'
    return f'<div class="shield-wrap shield-empty"></div>'

# ── RODADAS ───────────────────────────────────────────────────────────────────
_NOME_MOTOR = {
    "Atlético":            "ATLÉTICO-MG",
    "Red Bull Bragantino": "RB BRAGANTINO",
    "Internacional":       "INTER",
    "São Paulo":           "SÃO PAULO",
    "Grêmio":              "GRÊMIO",
    "Vitória":             "VITÓRIA",
    "Botafogo":            "BOTAFOGO",
    "Flamengo":            "FLAMENGO",
    "Fluminense":          "FLUMINENSE",
    "Vasco":               "VASCO",
    "Santos":              "SANTOS",
    "Palmeiras":           "PALMEIRAS",
    "Corinthians":         "CORINTHIANS",
    "Bahia":               "BAHIA",
    "Athletico-PR":        "ATHLETICO-PR",
    "Cruzeiro":            "CRUZEIRO",
    "Coritiba":            "CORITIBA",
    "Chapecoense":         "CHAPECOENSE",
    "Mirassol":            "MIRASSOL",
    "Remo":                "REMO",
}

def ler_rodada(n):
    """Retorna [(mandante_norm, visitante_norm), ...] para a rodada n."""
    path = os.path.join(BASE_DIR.replace("/", os.sep), "RODADAS_BRASILEIRAO_2026.txt")
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    confrontos = []
    inside = False
    for line in lines:
        if line.startswith(f"Rodada {n} (") or line == f"Rodada {n}":
            inside = True
            continue
        if inside:
            if not line.strip():
                if confrontos: break
                continue
            if line.startswith("Rodada "):
                break
            parts = line.split(" x ", 1)
            if len(parts) == 2:
                m = _NOME_MOTOR.get(parts[0].strip(), parts[0].strip().upper())
                v = _NOME_MOTOR.get(parts[1].strip(), parts[1].strip().upper())
                confrontos.append((m, v))
    if not confrontos:
        raise ValueError(f"Rodada {n} não encontrada em RODADAS_BRASILEIRAO_2026.txt")
    return confrontos

# ── HELPERS ───────────────────────────────────────────────────────────────────
def valido(e):
    if not e: return False
    h, t = map(int, e["fracao"].split("-"))
    return t >= AMOSTRA_MIN

def scout_block_score(conqs, ceds):
    bc = max((e["pct"] for e in conqs if valido(e)), default=0)
    bd = max((e["pct"] for e in ceds  if valido(e)), default=0)
    return bc + bd

# ── CSS EDITORIAL ─────────────────────────────────────────────────────────────
def _build_css():
    F = _FONTS_URL
    L = _LOGOS_URL
    return f"""
@font-face{{font-family:'Barlow';src:url('{F}/Barlow-Regular.ttf') format('truetype');font-weight:400;font-style:normal;}}
@font-face{{font-family:'Barlow';src:url('{F}/Barlow-Italic.ttf') format('truetype');font-weight:400;font-style:italic;}}
@font-face{{font-family:'Barlow';src:url('{F}/Barlow-SemiBold.ttf') format('truetype');font-weight:600;}}
@font-face{{font-family:'Barlow';src:url('{F}/Barlow-Bold.ttf') format('truetype');font-weight:700;}}
@font-face{{font-family:'Barlow';src:url('{F}/Barlow-ExtraBold.ttf') format('truetype');font-weight:800;}}
@font-face{{font-family:'Barlow';src:url('{F}/Barlow-Black.ttf') format('truetype');font-weight:900;}}

*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}

html{{
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
  text-rendering:geometricPrecision;
}}

body{{
  width:1080px;
  background:#f2ede4 url('{L}/background.png') center/cover no-repeat;
  font-family:'Barlow','Segoe UI',system-ui,sans-serif;
  font-size:13px;line-height:1.4;color:#0a2e14;
  overflow-x:hidden;
  font-feature-settings:'tnum','lnum','kern','ss01';
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
  text-rendering:geometricPrecision;
  font-synthesis:none;
  font-variant-ligatures:common-ligatures contextual;
}}

img{{
  image-rendering:-webkit-optimize-contrast;
  image-rendering:high-quality;
  -ms-interpolation-mode:bicubic;
}}

.arte-wrap{{width:1080px;display:flex;flex-direction:column;}}

/* ── HEADER ── */
.arte-header{{
  position:relative;
  padding:26px 40px 22px;
  display:grid;grid-template-columns:96px 1fr 96px;
  align-items:center;gap:16px;
  border-bottom:3px solid #0a5a24;
}}
.arte-header::after{{
  content:"";position:absolute;left:40px;right:40px;bottom:-6px;
  height:1px;background:linear-gradient(90deg,transparent 0%,#c9a878 20%,#c9a878 80%,transparent 100%);
  opacity:0.55;
}}
.arte-logo{{width:86px;height:86px;object-fit:contain;justify-self:start;
  filter:drop-shadow(0 2px 4px rgba(0,0,0,0.12));}}
.arte-header-text{{text-align:center;}}
.arte-pos-label{{
  font-size:46px;font-weight:900;color:#0a2e14;
  text-transform:uppercase;letter-spacing:0.05em;line-height:1.0;
  text-shadow:0 1px 0 rgba(255,255,255,0.4);
}}
.arte-sub1{{
  margin-top:8px;font-size:13px;font-weight:700;font-style:italic;
  color:#0a5a24;text-transform:uppercase;letter-spacing:0.22em;
}}
.arte-sub2{{
  margin-top:4px;font-size:11px;font-weight:700;font-style:italic;
  color:#0a5a24;text-transform:uppercase;letter-spacing:0.32em;
  opacity:0.88;
}}

/* ── CORPO ── */
.arte-corpo{{padding:26px 28px 20px;display:flex;flex-direction:column;gap:18px;}}

/* ── SCOUT BLOCK ── */
.scout-block{{
  background:
    linear-gradient(180deg,#16451f 0%,#113a19 60%,#0f3517 100%);
  border-radius:16px;overflow:hidden;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.05) inset,
    0 0 0 1px rgba(201,168,120,0.10) inset,
    0 8px 26px rgba(0,0,0,0.30),
    0 2px 6px rgba(0,0,0,0.18);
}}
.scout-block-hdr{{
  position:relative;
  background:linear-gradient(180deg,#0a2a10 0%,#06200b 100%);
  padding:15px 26px 14px;text-align:center;
  border-bottom:1px solid rgba(34,197,94,0.55);
}}
.scout-block-hdr::after{{
  content:"";position:absolute;left:0;right:0;bottom:-1px;height:1px;
  background:linear-gradient(90deg,transparent 0%,#c9a878 50%,transparent 100%);
  opacity:0.45;
}}
.scout-block-title{{
  font-size:19px;font-weight:900;color:#fff;
  letter-spacing:0.22em;text-transform:uppercase;
}}
.scout-block-title .hdr-sep{{
  color:#c9a878;font-weight:700;margin:0 0.35em;
  letter-spacing:0;display:inline-block;transform:translateY(-2px);
}}

/* ── ROW ── */
.scout-row{{
  display:grid;grid-template-columns:220px 1fr 220px;
  align-items:center;padding:18px 22px;gap:14px;
  border-bottom:1px solid rgba(255,255,255,0.05);
  min-height:110px;color:#fff;
}}
.scout-row:last-child{{border-bottom:none;}}

/* left: player(s) */
.player-cell{{
  display:flex;align-items:center;gap:12px;justify-content:flex-start;
}}
.player-photo-wrap{{
  position:relative;width:64px;height:64px;flex-shrink:0;
  background:#fff;border-radius:50%;
  box-shadow:
    0 6px 16px rgba(0,0,0,0.45),
    0 2px 5px rgba(0,0,0,0.32),
    0 0 0 1px rgba(0,0,0,0.08),
    inset 0 0 0 1px rgba(255,255,255,0.6),
    inset 0 -4px 8px rgba(0,0,0,0.08);
  display:flex;align-items:center;justify-content:center;
  overflow:visible;
}}
.player-photo{{
  width:60px;height:60px;border-radius:50%;
  object-fit:cover;object-position:top center;background:#f5f5f5;
}}
.player-badge{{
  position:absolute;bottom:-3px;right:-4px;
  width:26px;height:26px;border-radius:50%;
  background:#fff;
  box-shadow:
    0 3px 8px rgba(0,0,0,0.45),
    0 1px 2px rgba(0,0,0,0.30),
    0 0 0 1px rgba(0,0,0,0.10);
  display:flex;align-items:center;justify-content:center;padding:3px;
}}
.player-badge img{{width:100%;height:100%;object-fit:contain;}}
.player-names{{
  display:flex;flex-direction:column;gap:3px;min-width:0;
}}
.player-name{{
  font-size:13px;font-weight:800;color:#fff;
  text-transform:uppercase;letter-spacing:0.03em;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;
  text-shadow:0 1px 1px rgba(0,0,0,0.35);
}}
.player-status{{
  font-size:9px;font-weight:700;
  color:rgba(255,255,255,0.55);
  letter-spacing:0.16em;text-transform:uppercase;
}}
.empty-cell{{
  display:flex;align-items:center;justify-content:center;
  color:rgba(255,255,255,0.16);font-size:22px;min-height:54px;
}}

/* right: team */
.team-cell{{display:flex;align-items:center;gap:12px;justify-content:flex-end;}}
.team-shield-wrap{{
  width:64px;height:64px;flex-shrink:0;
  background:#fff;border-radius:50%;
  box-shadow:
    0 6px 16px rgba(0,0,0,0.45),
    0 2px 5px rgba(0,0,0,0.32),
    0 0 0 1px rgba(0,0,0,0.08),
    inset 0 0 0 1px rgba(255,255,255,0.6),
    inset 0 -4px 8px rgba(0,0,0,0.08);
  display:flex;align-items:center;justify-content:center;padding:8px;
}}
.team-shield-wrap .team-shield{{transform:scale(1.10);}}
.team-shield-wrap.empty{{background:rgba(255,255,255,0.25);}}
.team-shield{{width:100%;height:100%;object-fit:contain;
  filter:drop-shadow(0 1px 1px rgba(0,0,0,0.12));}}
.team-name{{
  font-size:13px;font-weight:800;color:#fff;
  text-transform:uppercase;letter-spacing:0.05em;
  text-shadow:0 1px 1px rgba(0,0,0,0.35);
}}

/* center: bars */
.bars-cell{{
  display:flex;flex-direction:column;gap:7px;align-items:stretch;
}}

.bars-header{{
  display:grid;grid-template-columns:56px 1fr 56px 1fr 56px;
  gap:10px;align-items:center;
  font-size:11px;font-weight:800;
  color:rgba(255,255,255,0.92);letter-spacing:0.28em;text-transform:uppercase;
}}
.bars-header .lbl{{text-align:center;text-shadow:0 1px 1px rgba(0,0,0,0.25);}}
.bars-header .x-sep{{
  text-align:center;color:#c9a878;font-weight:700;font-size:13px;
  font-style:italic;letter-spacing:0;
  text-shadow:0 1px 1px rgba(0,0,0,0.35);
}}

.bars-row{{
  display:grid;grid-template-columns:56px 1fr 56px 1fr 56px;
  gap:10px;align-items:center;
}}
.pct-cell{{
  font-size:25px;font-weight:900;letter-spacing:-0.02em;
  line-height:1;white-space:nowrap;
  font-feature-settings:'tnum','lnum';
  text-shadow:0 1px 2px rgba(0,0,0,0.45),0 0 8px rgba(0,0,0,0.25);
}}
.pct-left{{text-align:right;}}
.pct-right{{text-align:left;}}

.scout-abbrev{{
  text-align:center;font-size:14px;font-weight:900;
  color:#fff;letter-spacing:0.10em;text-transform:uppercase;
  text-shadow:0 1px 1px rgba(0,0,0,0.45);
  font-feature-settings:'tnum','lnum';
}}

.bar-track{{
  height:16px;
  background:linear-gradient(180deg,rgba(0,0,0,0.45) 0%,rgba(0,0,0,0.30) 100%);
  border-radius:8px;
  position:relative;overflow:hidden;
  box-shadow:
    inset 0 1px 2px rgba(0,0,0,0.55),
    inset 0 -1px 0 rgba(255,255,255,0.04),
    0 1px 0 rgba(255,255,255,0.03);
  display:flex;
}}
.bar-track.left{{justify-content:flex-end;}}
.bar-track.right{{justify-content:flex-start;}}
.bar-fill{{
  position:relative;height:100%;border-radius:8px;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.35),
    inset 0 -2px 3px rgba(0,0,0,0.18);
}}
.bar-fill::after{{
  content:"";position:absolute;inset:0;border-radius:8px;
  background:linear-gradient(180deg,rgba(255,255,255,0.28) 0%,rgba(255,255,255,0.06) 45%,rgba(0,0,0,0.10) 100%);
  pointer-events:none;
}}

.bars-frac{{
  display:grid;grid-template-columns:56px 1fr 56px 1fr 56px;
  gap:10px;margin-top:2px;
  font-size:10px;font-weight:600;font-style:italic;
  color:rgba(255,255,255,0.72);letter-spacing:0.04em;
  text-transform:uppercase;
}}
.frac-left{{grid-column:2;text-align:center;}}
.frac-right{{grid-column:4;text-align:center;}}

/* ── LEGENDA CONTEXTUAL ── */
.legenda-section{{
  margin:0 28px 20px;
  background:rgba(10,46,20,0.05);
  border:1px solid rgba(10,46,20,0.12);
  border-radius:14px;
  padding:20px 26px 18px;
}}
.legenda-titulo{{
  font-size:9px;font-weight:900;letter-spacing:0.30em;
  text-transform:uppercase;color:#0a5a24;
  margin-bottom:14px;
}}
.legenda-cols{{
  display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;
}}
.legenda-col{{display:flex;flex-direction:column;gap:7px;}}
.legenda-tag{{
  font-size:8px;font-weight:900;letter-spacing:0.24em;
  text-transform:uppercase;padding:3px 10px;
  border-radius:20px;display:inline-block;align-self:flex-start;
  white-space:nowrap;
}}
.leg-conq{{
  background:rgba(34,197,94,0.12);color:#0a5a24;
  border:1px solid rgba(34,197,94,0.28);
}}
.leg-ced{{
  background:rgba(248,113,113,0.12);color:#8a1a1a;
  border:1px solid rgba(248,113,113,0.28);
}}
.leg-rec{{
  background:rgba(201,168,120,0.16);color:#6a4a10;
  border:1px solid rgba(201,168,120,0.35);
}}
.legenda-texto{{
  font-size:11px;color:#3a5040;line-height:1.58;
  font-style:normal;
}}
.legenda-texto strong{{color:#0a2e14;font-weight:700;}}
.legenda-texto em{{font-style:normal;font-weight:600;color:#0a4a1c;}}
.legenda-credito{{display:block;margin-top:6px;font-size:10px;font-weight:700;
  font-style:italic;color:#7a5a20;letter-spacing:0.04em;}}

/* ── AVISO API ── */
.api-notice{{
  text-align:center;font-size:11px;font-weight:600;
  padding:8px 14px;border-radius:6px;margin-bottom:4px;
}}
.api-notice.warn{{background:rgba(245,158,11,0.14);color:#8a5a10;border:1px solid rgba(245,158,11,0.32);}}
.api-notice.error{{background:rgba(239,68,68,0.14);color:#9a1f1f;border:1px solid rgba(239,68,68,0.32);}}

/* ── FOOTER ── */
.arte-footer{{
  position:relative;
  border-top:3px solid #0a5a24;
  padding:16px 44px;
  display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:10px;
}}
.arte-footer::before{{
  content:"";position:absolute;left:40px;right:40px;top:-6px;
  height:1px;background:linear-gradient(90deg,transparent 0%,#c9a878 20%,#c9a878 80%,transparent 100%);
  opacity:0.55;
}}
.footer-legend{{display:flex;align-items:center;gap:24px;flex-wrap:wrap;}}
.leg-item{{
  display:flex;align-items:center;gap:8px;
  font-size:10px;font-weight:700;
  color:#0a2e14;
  text-transform:uppercase;letter-spacing:0.14em;
}}
.leg-dot{{
  width:10px;height:10px;border-radius:50%;flex-shrink:0;
  border:1px solid rgba(0,0,0,0.15);
  box-shadow:0 1px 2px rgba(0,0,0,0.18),inset 0 1px 0 rgba(255,255,255,0.3);
}}
.leg-dot.v{{background:#22c55e;}}
.leg-dot.a{{background:#fbbf24;}}
.leg-dot.r{{background:#f87171;}}
.footer-brand{{
  font-size:10px;font-weight:800;
  color:#0a5a24;
  letter-spacing:0.18em;text-transform:uppercase;
}}
"""

CSS = _build_css()

# ── RENDER ROW ────────────────────────────────────────────────────────────────
def _pct_str(pct):
    return f"{int(pct)}%" if pct == int(pct) else f"{round(pct, 1)}%"

def _player_cell(conq_e):
    """Renderiza lado conquistado. Aceita kind='jogador' (foto) ou kind='time' (escudo)."""
    if conq_e.get("kind") == "time":
        url = get_logo_url(conq_e["time"])
        sh  = f'<img src="{url}" class="team-shield">' if url else ""
        return f"""
        <div class="player-cell">
          <div class="team-shield-wrap">{sh}</div>
          <div class="player-names">
            <span class="player-name">{dn(conq_e["time"])}</span>
            <span class="player-status">COLETIVO</span>
          </div>
        </div>"""
    nome = (conq_e.get("jogador") or "").upper()
    foto = conq_e.get("foto", "") or ""
    status = conq_e.get("status", "") or ""
    if foto:
        avatar_html = f"""
          <div class="player-photo-wrap">
            <img src="{foto}" class="player-photo" alt="{nome}" onerror="this.style.display='none'">
            <div class="player-badge">{_shield_raw(conq_e["time"])}</div>
          </div>"""
    else:
        url = get_logo_url(conq_e["time"])
        sh  = f'<img src="{url}" class="team-shield">' if url else ""
        avatar_html = f'<div class="team-shield-wrap">{sh}</div>'
    return f"""
        <div class="player-cell">
          {avatar_html}
          <div class="player-names">
            <span class="player-name">{nome}</span>
            <span class="player-status">{status}</span>
          </div>
        </div>"""

def _shield_raw(k):
    url = get_logo_url(k)
    if url:
        return f'<img src="{url}" alt="{dn(k)}">'
    return ""

def _team_cell(ced_e):
    url = get_logo_url(ced_e["time"])
    sh = f'<img src="{url}" class="team-shield">' if url else ""
    return f"""
        <div class="team-cell">
          <span class="team-name">{dn(ced_e["time"])}</span>
          <div class="team-shield-wrap">{sh}</div>
        </div>"""

def _frac_texto(frac):
    """ '4-5' -> 'EM 4 DOS ÚLT. 5 JOGOS' """
    try:
        h, t = frac.split("-")
        return f"EM {h} DOS ÚLT. {t} JOGOS"
    except Exception:
        return frac

CINZA_NEUTRO = "#9ca3af"  # sinal fraco (pct >= amostra_min mas < 50%)

def render_row(conq_e, ced_e, scout):
    conq_ok = bool(conq_e) and valido(conq_e)
    ced_ok  = bool(ced_e)  and valido(ced_e)

    left_html  = _player_cell(conq_e) if conq_ok else '<div class="empty-cell">—</div>'
    right_html = _team_cell(ced_e)    if ced_ok  else '<div class="empty-cell">—</div>'

    if conq_ok:
        cor_l  = COR_HEX.get(conq_e.get("cor"), CINZA_NEUTRO)
        pct_l  = conq_e["pct"]
        pct_ls = _pct_str(pct_l)
        frac_l = _frac_texto(conq_e["fracao"])
        pct_left_html = f'<span class="pct-cell pct-left" style="color:{cor_l}">{pct_ls}</span>'
        bar_left_html = (
            f'<div class="bar-track left">'
            f'<div class="bar-fill" style="width:{pct_l}%;'
            f'background:linear-gradient(270deg,{cor_l} 0%,{cor_l} 55%,{cor_l}66 100%);"></div>'
            f'</div>'
        )
    else:
        pct_left_html = '<span class="pct-cell pct-left"></span>'
        bar_left_html = '<div class="bar-track left"></div>'
        frac_l = ""

    if ced_ok:
        cor_r  = COR_HEX.get(ced_e.get("cor"), CINZA_NEUTRO)
        pct_r  = ced_e["pct"]
        pct_rs = _pct_str(pct_r)
        frac_r = _frac_texto(ced_e["fracao"])
        pct_right_html = f'<span class="pct-cell pct-right" style="color:{cor_r}">{pct_rs}</span>'
        bar_right_html = (
            f'<div class="bar-track right">'
            f'<div class="bar-fill" style="width:{pct_r}%;'
            f'background:linear-gradient(90deg,{cor_r} 0%,{cor_r} 55%,{cor_r}66 100%);"></div>'
            f'</div>'
        )
    else:
        pct_right_html = '<span class="pct-cell pct-right"></span>'
        bar_right_html = '<div class="bar-track right"></div>'
        frac_r = ""

    bars_html = f"""
      <div class="bars-cell">
        <div class="bars-header">
          <span></span>
          <span class="lbl">CONQUISTADO</span>
          <span class="x-sep">x</span>
          <span class="lbl">CEDIDO</span>
          <span></span>
        </div>
        <div class="bars-row">
          {pct_left_html}
          {bar_left_html}
          <span class="scout-abbrev">{scout}</span>
          {bar_right_html}
          {pct_right_html}
        </div>
        <div class="bars-frac">
          <span class="frac-left">{frac_l}</span>
          <span class="frac-right">{frac_r}</span>
        </div>
      </div>"""

    return f"""
    <div class="scout-row">
      {left_html}
      {bars_html}
      {right_html}
    </div>"""


# ── RECORRÊNCIA POR JOGADOR ───────────────────────────────────────────────────
SCOUTS_TIME_ONLY = {"50%SG"}   # sempre time
SCOUTS_TIME_FALLBACK = {"1PG"} # time se nenhum jogador tiver recorrência

def _cor_faixa(pct):
    if pct >= 75: return "verde"
    if pct >= 61: return "amarelo"
    if pct >= 50: return "vermelho"
    return None

def _conquistadores_jogador(team, pos, scout, mando, n_jogos, elegivel, api_ok, mando_filter="por_mando"):
    """Cada jogador com recorrência ≥50% (mín. 3 jogos jogados) vira uma entrada.

    mando_filter:
      'por_mando' (default): apenas jogos no mando dado (Casa/Fora)
      'geral':               todos os jogos do time, independente de mando
    """
    if mando_filter == "geral":
        recs = [r for r in records
                if r["time"] == team and r["pos"] == pos]
    else:
        recs = [r for r in records
                if r["time"] == team and r["pos"] == pos and r["mando"] == mando]
    if not recs:
        return []
    datas_time = sorted(set(r["data"] for r in recs))
    janela = set(datas_time[-n_jogos:])
    recs_j = [r for r in recs if r["data"] in janela]

    por_jog = defaultdict(list)
    for r in recs_j:
        por_jog[r["jogador"]].append(r)

    elegiveis_pos = elegivel.get(_eleg_key(team), {}).get(pos, []) if api_ok else []
    cand_id   = {e["atleta_id"]: e for e in elegiveis_pos}
    cand_nome = {e["apelido"].upper(): e for e in elegiveis_pos}

    out = []
    for jog, rs in por_jog.items():
        datas_j = set(r["data"] for r in rs)
        played  = len(datas_j)
        if played < AMOSTRA_MIN:
            continue
        hits = len(set(r["data"] for r in rs if scout_hit_dynamic(r, scout)))
        pct  = hits / played * 100
        cor  = _cor_faixa(pct)
        if not cor:
            continue
        # Volume desempata em caso de empate de pct
        vol = sum(_metric_value(r, scout) for r in rs) / max(played, 1)

        match = None
        if api_ok:
            aid = next((r["atleta_id"] for r in rs if r.get("atleta_id")), None)
            if aid and aid in cand_id:
                match = cand_id[aid]
            elif jog.upper() in cand_nome:
                match = cand_nome[jog.upper()]
            else:
                jup = jog.upper()
                cands = [e for n, e in cand_nome.items()
                         if (jup in n or n in jup) and abs(len(jup)-len(n)) <= 6]
                if len(cands) == 1:
                    match = cands[0]
            if not match:
                continue
        apelido = match["apelido"] if match else jog
        status  = match["status"]  if match else ""
        sid     = match.get("status_id") if match else None
        out.append({
            "kind": "jogador",
            "time": team,
            "jogador": apelido,
            "foto": foto_jogador(team, apelido),
            "status": status,
            "status_id": sid,
            "hits": hits, "total": played, "pct": pct, "cor": cor,
            "fracao": f"{hits}-{played}",
            "volume": vol,
        })
    out.sort(key=lambda x: (0 if x.get("status_id") == STATUS_PROVAVEL else 1,
                            -x["pct"], -x.get("volume", 0), -x["hits"]))
    return out

def _agregar_por_time(recs_j, scout, require_color=True):
    """Agrega recorrência por time a partir de recs já filtrados pela janela.

    require_color=True (default): retorna None se pct < 50% (comportamento clássico).
    require_color=False: retorna data com cor=None se pct < 50% — útil para
    "sinal fraco espelhado por um cedido forte" (ver _scout_data_para_pos).
    """
    if not recs_j:
        return None
    datas = sorted(set(r["data"] for r in recs_j))
    played = len(datas)
    if played < AMOSTRA_MIN:
        return None
    # Um jogo conta como hit se QUALQUER registro daquela data bater o scout
    por_data = defaultdict(list)
    for r in recs_j:
        por_data[r["data"]].append(r)
    hits = 0
    vol_total = 0.0
    for d, rs in por_data.items():
        if any(scout_hit_dynamic(r, scout) for r in rs):
            hits += 1
        # soma do volume do melhor registro do dia (proxy do time nesse jogo)
        vol_total += max((_metric_value(r, scout) for r in rs), default=0)
    pct = hits / played * 100
    cor = _cor_faixa(pct)
    if require_color and not cor:
        return None
    return {
        "hits": hits, "total": played, "pct": pct, "cor": cor,
        "fracao": f"{hits}-{played}",
        "volume": vol_total / max(played, 1),
    }

def _conquistado_time_painel(team, pos, scout, mando, n_jogos, mando_filter="por_mando", require_color=True):
    """Agregação coletiva do time. Em 'geral' ignora o filtro de mando."""
    if mando_filter == "geral":
        recs = [r for r in records
                if r["time"] == team and r["pos"] == pos]
    else:
        recs = [r for r in records
                if r["time"] == team and r["pos"] == pos and r["mando"] == mando]
    if not recs:
        return None
    datas = sorted(set(r["data"] for r in recs))
    janela = set(datas[-n_jogos:])
    recs_j = [r for r in recs if r["data"] in janela]
    base = _agregar_por_time(recs_j, scout, require_color=require_color)
    if not base:
        return None
    return {"kind": "time", "time": team, **base}

def _cedido_time_painel(team, pos, scout, mando_team, n_jogos, mando_filter="por_mando", require_color=True):
    """
    Cedido pelo time. Em 'por_mando' usa perspectiva do adversário (mando invertido).
    Em 'geral' agrega todos os jogos do time independente de mando.
    """
    if mando_filter == "geral":
        recs = [r for r in records
                if r["adversario"] == team and r["pos"] == pos]
    else:
        mando_adv = "Fora" if mando_team == "Casa" else "Casa"
        recs = [r for r in records
                if r["adversario"] == team and r["pos"] == pos and r["mando"] == mando_adv]
    if not recs:
        return None
    datas = sorted(set(r["data"] for r in recs))
    janela = set(datas[-n_jogos:])
    recs_j = [r for r in recs if r["data"] in janela]
    base = _agregar_por_time(recs_j, scout, require_color=require_color)
    if not base:
        return None
    return {"kind": "time", "time": team, **base}

def _build_conquistadores(team, pos, scout, mando, n_jogos, elegivel, api_ok, mando_filter="por_mando"):
    if _is_team_only(scout):
        t = _conquistado_time_painel(team, pos, scout, mando, n_jogos, mando_filter)
        return [t] if t else []
    jogs = _conquistadores_jogador(team, pos, scout, mando, n_jogos, elegivel, api_ok, mando_filter)
    if jogs:
        return jogs
    if _is_team_fallback(scout):
        t = _conquistado_time_painel(team, pos, scout, mando, n_jogos, mando_filter)
        return [t] if t else []
    return []

# ── SCOUT DATA POR POSIÇÃO ────────────────────────────────────────────────────
def _is_strong(e):
    """True se o registro tem sinal (cor definida = pct >= 50%)."""
    return bool(e and e.get("cor"))

def _scout_data_para_pos(pos, confrontos, n_jogos, elegivel, api_ok,
                          scouts_custom=None, mando_filter="por_mando"):
    """
    Pareia CONQUISTADO × CEDIDO por confronto.

    Nova regra (corrigida): o par é mantido se PELO MENOS UM LADO tem sinal forte
    (>= 50%). Quando um lado é forte mas o outro é fraco/ausente, o lado fraco é
    exibido em neutro (cinza) para preservar o contexto sem enganar o leitor.
    """
    scouts = scouts_custom if scouts_custom else SCOUTS_POS.get(pos, [])
    scout_data = []
    for s in scouts:
        pairs = []
        for (mandante, visitante) in confrontos:
            # CEDIDO sempre team-level. Coletamos versões fraca (require_color=False)
            # pra podermos espelhar quando o outro lado for forte.
            ced_mand_w = _cedido_time_painel(mandante,  pos, s, "Casa", n_jogos, mando_filter, require_color=False)
            ced_vis_w  = _cedido_time_painel(visitante, pos, s, "Fora", n_jogos, mando_filter, require_color=False)

            cqs_home = _build_conquistadores(mandante, pos, s, "Casa", n_jogos, elegivel, api_ok, mando_filter)
            cqs_away = _build_conquistadores(visitante, pos, s, "Fora", n_jogos, elegivel, api_ok, mando_filter)

            # --- lado mandante (CONQUISTADO) x visitante (CEDIDO) ---
            if cqs_home:
                # Há CONQUISTADOR(ES) forte(s). Pareia com CEDIDO (forte ou fraco).
                for cq in cqs_home:
                    if ced_vis_w:
                        pairs.append((cq, ced_vis_w))
            elif _is_strong(ced_vis_w):
                # Sem CONQUISTADOR forte, mas CEDIDO do visitante é forte.
                # Fallback: mostra o TIME mandante (mesmo fraco) como CONQUISTADO.
                cq_team = _conquistado_time_painel(mandante, pos, s, "Casa", n_jogos, mando_filter, require_color=False)
                if cq_team:
                    pairs.append((cq_team, ced_vis_w))
                else:
                    # nem dados do mandante — ainda assim preserva o CEDIDO forte
                    pairs.append((None, ced_vis_w))

            # --- lado visitante (CONQUISTADO) x mandante (CEDIDO) ---
            if cqs_away:
                for cq in cqs_away:
                    if ced_mand_w:
                        pairs.append((cq, ced_mand_w))
            elif _is_strong(ced_mand_w):
                cq_team = _conquistado_time_painel(visitante, pos, s, "Fora", n_jogos, mando_filter, require_color=False)
                if cq_team:
                    pairs.append((cq_team, ced_mand_w))
                else:
                    pairs.append((None, ced_mand_w))

        # Filtro final: pelo menos um lado precisa ter cor (>= 50%).
        pairs = [(cq, ced) for (cq, ced) in pairs if _is_strong(cq) or _is_strong(ced)]
        if not pairs:
            continue

        def _sum_pct(p):
            a = p[0]["pct"] if p[0] else 0
            b = p[1]["pct"] if p[1] else 0
            return a + b

        pairs.sort(key=lambda p: -_sum_pct(p))
        scout_data.append({
            "scout": s,
            "pairs": pairs,
            "score": sum(_sum_pct(p) for p in pairs[:3]),
        })
    scout_data.sort(key=lambda x: -x["score"])
    return scout_data


# ── GERADOR HTML POR POSIÇÃO ──────────────────────────────────────────────────
def gerar_arte_posicao(pos, confrontos, janela_label, rodada,
                        elegivel, api_ok, n_jogos, aviso_html="", scouts_custom=None,
                        mando_filter="por_mando"):
    """Retorna HTML fechado de 1080px para uma posição. None se sem sinal."""
    scout_data = _scout_data_para_pos(
        pos, confrontos, n_jogos, elegivel, api_ok,
        scouts_custom=scouts_custom, mando_filter=mando_filter
    )
    if not scout_data:
        return None

    MAX_ROWS  = 3
    corpo_html = ""
    for sd in scout_data:
        pairs = sd["pairs"][:MAX_ROWS]
        rows_html = ""
        for (conq_e, ced_e) in pairs:
            rows_html += render_row(conq_e, ced_e, sd["scout"])
        titulo = f'{scout_titulo(sd["scout"])} <span class="hdr-sep">•</span> ÚLTIMOS {n_jogos} JOGOS'
        corpo_html += f"""
    <div class="scout-block">
      <div class="scout-block-hdr">
        <span class="scout-block-title">{titulo}</span>
      </div>
      {rows_html}
    </div>"""

    # scouts que realmente apareceram (para legenda contextual)
    scouts_ativos = [sd["scout"] for sd in scout_data]
    legenda_html  = gerar_legenda_html(pos, scouts_ativos, n_jogos, mando_filter)

    mando_label = "POR MANDO" if mando_filter == "por_mando" else "GERAL"
    pos_label  = LABEL_POSICAO[pos].upper()
    logo_url   = f"{_LOGOS_URL}/logo_tcc.png"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1080">
<title>{pos_label} · R{rodada} · {janela_label}</title>
<style>{CSS}</style>
</head>
<body><div class="arte-wrap">

  <header class="arte-header">
    <img src="{logo_url}" class="arte-logo" alt="TCC">
    <div class="arte-header-text">
      <div class="arte-pos-label">{pos_label}</div>
      <div class="arte-sub1">ANÁLISE DE RECORRÊNCIA · ÚLTIMOS {n_jogos} JOGOS · {mando_label}</div>
      <div class="arte-sub2">RODADA {rodada}</div>
    </div>
    <div></div>
  </header>

  <div class="arte-corpo">
    {aviso_html}
    {corpo_html}
  </div>

  {legenda_html}

  <footer class="arte-footer">
    <div class="footer-legend">
      <span class="leg-item"><span class="leg-dot v"></span>≥ 75%&nbsp;Forte</span>
      <span class="leg-item"><span class="leg-dot a"></span>≥ 61%&nbsp;Médio</span>
      <span class="leg-item"><span class="leg-dot r"></span>≥ 50%&nbsp;Sinal</span>
    </div>
    <div class="footer-brand">Treinando Campeões de Cartola</div>
  </footer>

</div></body>
</html>"""


# ── GERAR TODAS ───────────────────────────────────────────────────────────────
def gerar_todas_artes(n_jogos, rodada, scouts_override=None, mando_filter="por_mando"):
    """
    Gera um HTML fechado por posição em artes/, baseado nos confrontos da rodada.
    scouts_override: dict {POS: [codigo_scout, ...]} para sobrescrever SCOUTS_POS.
    mando_filter: 'por_mando' (default) ou 'geral'.
    """
    confrontos   = ler_rodada(rodada)
    janela_label = f"últ. {n_jogos}J"
    scouts_override = scouts_override or {}

    print(f"  Rodada {rodada}: {len(confrontos)} confrontos carregados")
    for m, v in confrontos:
        print(f"    {m} (Casa) x {v} (Fora)")

    aviso_html = ""
    api_ok     = False
    elegivel   = {}
    try:
        elegivel, api_fonte = construir_lookup_elegibilidade(mv_lookup, atk_lookup, nome_id_lookup)
        api_ok = True
        if api_fonte == "stale":
            aviso_html = '<p class="api-notice warn">Status dos atletas desatualizado — usando cache anterior.</p>'
    except Exception as ex:
        aviso_html = f'<p class="api-notice error">API do Cartola indisponível. ({ex})</p>'

    os.makedirs("artes", exist_ok=True)
    sufixo  = f"r{rodada}_ult{n_jogos}"
    gerados = []

    for pos in ORDEM_POSICOES:
        scouts_custom = scouts_override.get(pos)
        html = gerar_arte_posicao(
            pos, confrontos, janela_label, rodada,
            elegivel, api_ok, n_jogos, aviso_html,
            scouts_custom=scouts_custom, mando_filter=mando_filter
        )
        if html is None:
            continue
        nome = os.path.join("artes", f"arte_{pos}_{sufixo}.html")
        with open(nome, "w", encoding="utf-8") as f:
            f.write(html)
        gerados.append(nome)
        print(f"  {nome}")

    return gerados


# ── CLI HELPERS ───────────────────────────────────────────────────────────────
def _parse_scouts_arg(raw):
    """
    Ex: 'ZAGUEIRO=3DS,1PG;GOLEIRO=80%SG,4DEF'
    Retorna dict {POS: [codigos]}. Códigos inválidos são ignorados com aviso.
    """
    out = {}
    if not raw:
        return out
    for bloco in raw.split(";"):
        bloco = bloco.strip()
        if not bloco or "=" not in bloco:
            continue
        pos, codes = bloco.split("=", 1)
        pos = pos.strip().upper()
        lst = []
        for c in codes.split(","):
            c = c.strip().upper()
            if not c:
                continue
            if parse_scout(c) or c in SCOUT_EXTENSO:
                lst.append(c)
            else:
                print(f"  ⚠ scout ignorado (formato inválido): {c}")
        if lst:
            out[pos] = lst
    return out


# ── ENTRYPOINT ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        print("Uso: python painel.py <n_jogos> <rodada> [--scouts POS=COD1,COD2;POS2=COD3]")
        print("Ex:  python painel.py 5 12")
        print("     python painel.py 5 12 --scouts ZAGUEIRO=3DS,1PG;GOLEIRO=80%SG,4DEF")
        sys.exit(1)
    n_jogos = int(args[0])
    rodada  = int(args[1])

    scouts_override = {}
    if "--scouts" in args:
        idx = args.index("--scouts")
        if idx + 1 < len(args):
            scouts_override = _parse_scouts_arg(args[idx + 1])

    mando_filter = "por_mando"
    if "--mando" in args:
        idx = args.index("--mando")
        if idx + 1 < len(args):
            v = args[idx + 1].strip().lower()
            if v in ("geral", "por_mando"):
                mando_filter = v

    print(f"Gerando artes: ult.{n_jogos}J - Rodada {rodada} - mando={mando_filter}")
    if scouts_override:
        print(f"  Scouts custom: {scouts_override}")
    gerados = gerar_todas_artes(n_jogos=n_jogos, rodada=rodada,
                                 scouts_override=scouts_override, mando_filter=mando_filter)
    print(f"\n{len(gerados)} arte(s) gerada(s) em artes/")
