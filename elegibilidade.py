"""
Camada de elegibilidade via API do Cartola.
Conecta atletas disponíveis (provável/dúvida) às posições refinadas do motor.
"""
import urllib.request, json, os, time as _time
from collections import defaultdict

# ── ENDPOINT + CACHE ──────────────────────────────────────────────────────────
API_URL    = "https://api.cartola.globo.com/atletas/mercado"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache_mercado.json")
CACHE_TTL  = 3600  # 1 hora

STATUS_PROVAVEL = 7
STATUS_DUVIDA   = 2
STATUS_ELEGIVEL = {STATUS_PROVAVEL, STATUS_DUVIDA}

# ── MAPEAMENTO clube_id → chave do motor (norm_time) ─────────────────────────
# Derivado dos slugs da API + norm_time() do motor
CLUBE_MOTOR = {
    262:  "FLAMENGO",
    263:  "BOTAFOGO",
    264:  "CORINTHIANS",
    265:  "BAHIA",
    266:  "FLUMINENSE",
    267:  "VASCO",
    275:  "PALMEIRAS",
    276:  "SAO PAULO",        # slug: sao-paulo
    277:  "SANTOS",
    280:  "RB BRAGANTINO",    # normalizado pelo motor
    282:  "ATLETICO-MG",      # motor recebe com encoding; slug resolve
    283:  "CRUZEIRO",
    284:  "GREMIO",
    285:  "INTER",            # normalizado pelo motor
    287:  "VITORIA",
    293:  "ATHLETICO-PR",
    294:  "CORITIBA",
    315:  "CHAPECOENSE",
    364:  "REMO",
    2305: "MIRASSOL",
}

# posicao_id da API → posições brutas (sem subdivisão de lateral/meia/atacante)
# A subdivisão refinada vem dos lookups locais (mv_lookup e atk_lookup do motor)
POSID_GRUPO = {
    1: {"GOLEIRO"},
    2: {"LATERAL_D", "LATERAL_E"},
    3: {"ZAGUEIRO"},
    4: {"MEIA", "VOLANTE"},
    5: {"ATACANTE", "PONTA_D", "PONTA_E"},
    6: set(),  # técnico — ignorar
}


def buscar_mercado():
    """
    Retorna JSON do mercado Cartola.
    Ordem de tentativa:
      1. cache válido (< 1h)
      2. API ao vivo  → grava cache
      3. cache velho  → avisa mas usa
      4. falha total  → lança exceção
    Retorna (data, fonte) onde fonte in ("cache", "api", "stale").
    """
    # 1. Cache válido
    if os.path.exists(CACHE_FILE):
        age = _time.time() - os.path.getmtime(CACHE_FILE)
        if age < CACHE_TTL:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f), "cache"

    # 2. API ao vivo
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return data, "api"
    except Exception:
        pass

    # 3. Cache velho (fallback)
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f), "stale"

    raise RuntimeError("API do Cartola indisponível e sem cache local.")


def construir_lookup_elegibilidade(mv_lookup, atk_lookup, nome_id_lookup=None):
    """
    Retorna (elegivel, fonte_api):
      elegivel[motor_time][pos_refinada] = [
        {"atleta_id": int, "apelido": str, "status": "provável"|"dúvida"}
        ...
      ]
    fonte_api: "api" | "cache" | "stale"

    nome_id_lookup = {(motor_time, NOME_UPPER): atleta_id}  — chave de match robusta
    mv_lookup  = {(norm_time, NOME_UPPER): "MEIA"|"VOLANTE"}
    atk_lookup = {str(atleta_id): "ATACANTE"|"PONTA_D"|"PONTA_E"}
    """
    data, fonte = buscar_mercado()
    atletas = data["atletas"]

    # Índice inverso: atleta_id → motor_time (via nome_id_lookup)
    # Permite confirmar o time correto quando o atleta_id bate
    id_to_motor_time = {}
    if nome_id_lookup:
        for (mtime, _), aid in nome_id_lookup.items():
            id_to_motor_time[aid] = mtime

    elegivel = defaultdict(lambda: defaultdict(list))

    for a in atletas:
        if a["status_id"] not in STATUS_ELEGIVEL:
            continue

        clube_id  = a["clube_id"]
        motor_key = CLUBE_MOTOR.get(clube_id)
        if not motor_key:
            continue

        posicao_id = a["posicao_id"]
        grupos = POSID_GRUPO.get(posicao_id, set())
        if not grupos:
            continue

        atleta_id = str(a["atleta_id"])
        apelido   = a.get("apelido") or a.get("nome", "")
        nome_up   = apelido.strip().upper()
        status_label = "provável" if a["status_id"] == STATUS_PROVAVEL else "dúvida"

        entry = {
            "atleta_id":    int(atleta_id),
            "apelido":      apelido,
            "status":       status_label,
            "status_id":    a["status_id"],
            "foto":         a.get("foto", ""),
        }

        if posicao_id in (1, 3):
            # Goleiro e Zagueiro: posição direta
            for pos in grupos:
                elegivel[motor_key][pos].append(entry)

        elif posicao_id == 2:
            # Lateral: API não distingue D/E → adiciona em ambos
            for pos in grupos:
                elegivel[motor_key][pos].append(entry)

        elif posicao_id == 4:
            # Meia/Volante: refinar via mv_lookup
            pos_refinada = mv_lookup.get((motor_key, nome_up))
            if pos_refinada:
                elegivel[motor_key][pos_refinada].append(entry)
            else:
                # Fallback: adiciona em ambos
                for pos in grupos:
                    elegivel[motor_key][pos].append(entry)

        elif posicao_id == 5:
            # Atacante/Ponta: refinar via atk_lookup por ID
            pos_refinada = atk_lookup.get(atleta_id)
            if pos_refinada:
                elegivel[motor_key][pos_refinada].append(entry)
            else:
                # Fallback: adiciona em todos
                for pos in grupos:
                    elegivel[motor_key][pos].append(entry)

    # Ordenar: prováveis antes de dúvidas
    for motor_key in elegivel:
        for pos in elegivel[motor_key]:
            elegivel[motor_key][pos].sort(key=lambda x: (0 if x["status_id"] == STATUS_PROVAVEL else 1))

    return elegivel, fonte


def jogadores_para_bloco(records, motor_time, pos, scout, n_jogos,
                         elegivel, scout_hit_fn, mando_filter=None):
    """
    Retorna lista de jogadores elegíveis para o bloco (time, pos, scout),
    ranqueados por frequência de acerto do scout nos últimos N jogos,
    filtrados pela elegibilidade da API.

    Retorna: [{"apelido": str, "status": str, "hits": int, "total": int}]
    """
    from datetime import datetime

    # Pegar registros individuais do time nessa posição
    recs = [r for r in records
            if r["time"] == motor_time and r["pos"] == pos]

    if mando_filter:
        recs = [r for r in recs if r["mando"] == mando_filter]

    if not recs:
        return []

    # Obter jogos únicos desse time nessa posição, ordenados por data
    datas_unicas = sorted(set(r["data"] for r in recs))
    janela_datas = set(datas_unicas[-n_jogos:]) if n_jogos else set(datas_unicas)

    # Filtrar registros da janela
    recs_janela = [r for r in recs if r["data"] in janela_datas]
    total_jogos  = len(janela_datas)

    # Contar hits por jogador
    hits_por_jogador = defaultdict(set)   # jogador -> set de datas com hit
    for r in recs_janela:
        if scout_hit_fn(r, scout):
            hits_por_jogador[r["jogador"]].add(r["data"])

    # Todos os jogadores que apareceram na janela
    todos_jogadores = set(r["jogador"] for r in recs_janela)

    # Conjunto elegível desse time/pos: indexado por atleta_id E por nome
    candidatos_por_id   = {e["atleta_id"]: e for e in elegivel.get(motor_time, {}).get(pos, [])}
    candidatos_por_nome = {e["apelido"].upper(): e for e in elegivel.get(motor_time, {}).get(pos, [])}

    resultado = []
    for jogador in todos_jogadores:
        # Buscar atleta_id do jogador no histórico (chave confiável)
        aid = next(
            (r["atleta_id"] for r in recs_janela if r["jogador"] == jogador and r["atleta_id"]),
            None
        )

        match = None

        # 1. Match por atleta_id (mais confiável)
        if aid and aid in candidatos_por_id:
            match = candidatos_por_id[aid]

        # 2. Match exato por nome (fallback)
        if not match:
            jup = jogador.upper()
            match = candidatos_por_nome.get(jup)

        # 3. Match por substring — apenas se sem ambiguidade no mesmo grupo
        if not match:
            jup = jogador.upper()
            candidatos_ss = [
                e for nome, e in candidatos_por_nome.items()
                if (jup in nome or nome in jup) and abs(len(jup) - len(nome)) <= 6
            ]
            if len(candidatos_ss) == 1:  # só entra se não houver ambiguidade
                match = candidatos_ss[0]

        if not match:
            continue  # não está elegível na API

        hits = len(hits_por_jogador.get(jogador, set()))

        # Volume bruto do scout na janela (tiebreaker): soma dos valores do scout
        def _volume(r):
            s = scout
            if s == "1PG":   return r["G"] + r["A"]
            if s == "2DS":   return r["DS"]
            if s == "3DEF":  return r["DE"]
            if s == "3FIN":  return r["FD"] + r["FF"] + r["FT"]
            if s == "75%DE": return r["FD"]
            if s == "50%SG": return r["SG"]
            return 0.0

        volume = sum(_volume(r) for r in recs_janela if r["jogador"] == jogador)

        resultado.append({
            "apelido":   match["apelido"],
            "status":    match["status"],
            "status_id": match["status_id"],
            "hits":      hits,
            "total":     total_jogos,
            "volume":    volume,
            "foto":      match.get("foto", ""),
        })

    # Critério mínimo: >= 2 hits na janela
    resultado = [r for r in resultado if r["hits"] >= 2]

    # Ordenar: prováveis antes de dúvidas → mais hits → maior volume
    resultado.sort(key=lambda x: (0 if x["status_id"] == STATUS_PROVAVEL else 1, -x["hits"], -x["volume"]))

    # Máximo 2 jogadores por bloco
    return resultado[:2]
