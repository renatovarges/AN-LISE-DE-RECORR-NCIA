import openpyxl, csv
from collections import defaultdict
from datetime import datetime

# ── CARREGAR PLANILHA ─────────────────────────────────────────────────────────
wb = openpyxl.load_workbook("Scouts Pós R12 2026.xlsx", read_only=True, data_only=True)
ws = wb["Por jogo"]
rows = list(ws.iter_rows(values_only=True))
headers = rows[0]
data_rows = rows[1:]
col = {h: i for i, h in enumerate(headers)}
wb.close()

ADV_COL = 2  # coluna Adversário (índice fixo)

# ── NORMALIZAÇÃO DE TIMES ─────────────────────────────────────────────────────
TIME_NORM = {
    "INTERNACIONAL": "INTER",
    "RED BULL BRAGANTINO": "RB BRAGANTINO",
}
def norm_time(t):
    return TIME_NORM.get((t or "").strip().upper(), (t or "").strip().upper())

# ── LOOKUP MEIAS/VOLANTES ─────────────────────────────────────────────────────
mv_lookup = {}
with open("classificacao_meias_volantes.csv", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        key = (norm_time(row["TIME"]), row["JOGADOR"].strip().upper())
        mv_lookup[key] = row["CLASSIFICACAO"]

# ── LOOKUP ATACANTES ──────────────────────────────────────────────────────────
atk_lookup = {}
ATK_CAT = {
    "Atacante de área": "ATACANTE",
    "Ponta direita": "PONTA_D",
    "Ponta esquerda": "PONTA_E",
}
with open("separação atacantes.txt", encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="|"):
        atk_lookup[row["atleta_id"].strip()] = ATK_CAT.get(row["categoria"].strip(), "ATACANTE")

# ── MAPEAMENTO DE POSIÇÃO ─────────────────────────────────────────────────────
POSREAL_MAP = {1: "GOLEIRO", 2.2: "LATERAL_D", 2.6: "LATERAL_E", 3: "ZAGUEIRO", 6: None}

def get_pos(r):
    pr = r[col["PosReal"]]
    if pr in POSREAL_MAP:
        return POSREAL_MAP[pr]
    if pr == 4:
        key = (norm_time(r[col["Time"]]), (r[col["Nome2"]] or "").strip().upper())
        return mv_lookup.get(key, "MEIA")
    if pr == 5:
        rid = str(int(r[col["ID"]])) if r[col["ID"]] else ""
        return atk_lookup.get(rid, "ATACANTE")
    return None

def safe(v):
    return float(v) if v is not None else 0.0

# ── CONSTRUIR DATASET ─────────────────────────────────────────────────────────
records = []
for r in data_rows:
    pos = get_pos(r)
    if not pos:
        continue
    dt = r[col["Data"]]
    if not isinstance(dt, datetime):
        continue
    records.append({
        "atleta_id":  int(r[col["ID"]]) if r[col["ID"]] else None,
        "jogador":    (r[col["Nome2"]] or "").strip(),
        "time":       norm_time(r[col["Time"]]),
        "adversario": norm_time(r[ADV_COL]),
        "pos":        pos,
        "mando":      (r[col["Mand"]] or "").strip(),
        "data":       dt.date(),
        "G":  safe(r[col["G"]]),
        "A":  safe(r[col["A"]]),
        "DS": safe(r[col["DS"]]),
        "DE": safe(r[col["DE"]]),
        "FD": safe(r[col["FD"]]),
        "FF": safe(r[col["FF"]]),
        "FT": safe(r[col["FT"]]),
        "GS": safe(r[col["GS"]]),
        "SG": safe(r[col["SG"]]),
    })

# Lookup (time, nome_upper) → atleta_id — chave de match com a API
nome_id_lookup = {}
for _r in records:
    if _r["atleta_id"] and _r["jogador"]:
        nome_id_lookup[(_r["time"], _r["jogador"].upper())] = _r["atleta_id"]

# ── SCOUTS POR POSIÇÃO ────────────────────────────────────────────────────────
SCOUTS_POS = {
    "GOLEIRO":   ["50%SG", "3DEF", "75%DE"],
    "LATERAL_D": ["50%SG", "2DS", "1PG"],
    "LATERAL_E": ["50%SG", "2DS", "1PG"],
    "ZAGUEIRO":  ["50%SG", "2DS", "1PG", "3FIN"],
    "VOLANTE":   ["2DS", "3FIN"],
    "MEIA":      ["1PG", "3FIN"],
    "PONTA_D":   ["1PG", "3FIN"],
    "PONTA_E":   ["1PG", "3FIN"],
    "ATACANTE":  ["1PG", "3FIN"],
}

def scout_hit(rec, scout):
    if scout == "1PG":
        return (rec["G"] + rec["A"]) >= 1
    if scout == "2DS":
        return rec["DS"] >= 2
    if scout == "3DEF":
        return rec["DE"] >= 3
    if scout == "3FIN":
        return (rec["FD"] + rec["FF"] + rec["FT"]) >= 3
    if scout == "75%DE":
        denom = rec["FD"] + rec["GS"]
        return ((rec["FD"] / denom * 100) if denom > 0 else 0.0) >= 75
    if scout == "50%SG":
        return rec["SG"] >= 1
    return False

def cor(pct):
    if pct >= 75:   return "verde"
    if pct >= 61:   return "amarelo"
    if pct >= 50:   return "vermelho"
    return None

# ── MOTOR DE RECORRÊNCIA ──────────────────────────────────────────────────────
def calcular_recorrencia(records, mando_filter=None, n_jogos=None):
    """
    Agrega ao nível de PARTIDA antes de aplicar a janela (regra de ouro).

    Para cada jogo (time × adversario × data):
    - conquistado[time][pos]: o time gerou o scout nessa partida?
      (= qualquer jogador do time nessa pos atingiu o limiar)
    - cedido[adversario][pos]: o adversário cedeu o scout nessa partida?
      (= mesmo conjunto de registros, perspectiva invertida)

    Filtro de mando:
    - conquistado: mando do time = mando_filter
    - cedido: mando do adversário = mando_filter
      (quando time joga Fora, adversário joga Casa — mando é invertido)
    """
    # Agrupar registros por jogo único: (time, adversario, data)
    game_pool = defaultdict(list)
    for rec in records:
        game_pool[(rec["time"], rec["adversario"], rec["data"])].append(rec)

    # conquistado_games[team][pos] = lista de dicts {date, hit_por_scout}
    # cedido_games[team][pos]      = idem (team = adversário que cedeu)
    conq_games = defaultdict(lambda: defaultdict(list))
    ced_games  = defaultdict(lambda: defaultdict(list))

    for (team, adv, date), recs in game_pool.items():
        mando_team = recs[0]["mando"]          # "Casa" ou "Fora"
        mando_adv  = "Fora" if mando_team == "Casa" else "Casa"

        # Agrupar por posição dentro do jogo
        by_pos = defaultdict(list)
        for r in recs:
            by_pos[r["pos"]].append(r)

        for pos, pos_recs in by_pos.items():
            scouts = SCOUTS_POS.get(pos, [])
            hits = {s: any(scout_hit(r, s) for r in pos_recs) for s in scouts}

            # Conquistado: filtrar por mando do time
            if not mando_filter or mando_team == mando_filter:
                conq_games[team][pos].append({"date": date, "hits": hits})

            # Cedido: filtrar por mando do adversário
            if not mando_filter or mando_adv == mando_filter:
                ced_games[adv][pos].append({"date": date, "hits": hits})

    resultado = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    all_teams = set(conq_games.keys()) | set(ced_games.keys())

    for team in all_teams:
        for lado, source in [("conquistado", conq_games[team]), ("cedido", ced_games[team])]:
            for pos, game_list in source.items():
                # Ordenar por data real — regra de ouro
                sorted_games = sorted(game_list, key=lambda x: x["date"])
                window = sorted_games[-n_jogos:] if n_jogos else sorted_games
                total = len(window)
                if not total:
                    continue

                for scout in SCOUTS_POS.get(pos, []):
                    hits_count = sum(1 for g in window if g["hits"].get(scout, False))
                    pct = hits_count / total * 100
                    c = cor(pct)
                    if c:
                        resultado[team][pos][scout][lado] = {
                            "pct":    round(pct, 1),
                            "fracao": f"{hits_count}-{total}",
                            "cor":    c,
                        }

    return resultado


# ── SAÍDA DE VALIDAÇÃO ────────────────────────────────────────────────────────
if __name__ == "__main__":
    from collections import Counter

    print(f"Records válidos: {len(records)}")
    print(Counter(r["pos"] for r in records))
    print()

    # Contagem de sinais por configuração
    for mando_label, mando_val in [("TODOS", None), ("CASA", "Casa"), ("FORA", "Fora")]:
        for janela in [5, 10]:
            res = calcular_recorrencia(records, mando_filter=mando_val, n_jogos=janela)
            total = sum(
                len(res[t][p][s])
                for t in res for p in res[t] for s in res[t][p]
            )
            print(f"[mando={mando_label:4s}, janela=ult.{janela}J] => {total:3d} lados com sinal (>= 50%)")

    print()
    print("=" * 85)
    print("SAÍDA BRUTA — últimos 5 jogos, sem filtro de mando (primeiros 50 sinais)")
    print("=" * 85)

    res5 = calcular_recorrencia(records, mando_filter=None, n_jogos=5)
    count = 0
    for time in sorted(res5.keys()):
        for pos in sorted(res5[time].keys()):
            for scout in sorted(res5[time][pos].keys()):
                entry = res5[time][pos][scout]
                conq = entry.get("conquistado")
                ced  = entry.get("cedido")
                if conq or ced:
                    c_str = f"{conq['pct']}% {conq['fracao']} [{conq['cor']}]" if conq else "—"
                    d_str = f"{ced['pct']}% {ced['fracao']} [{ced['cor']}]"    if ced  else "—"
                    print(f"{time:28s}| {pos:10s}| {scout:6s}| "
                          f"CONQ: {c_str:28s}| CED: {d_str}")
                    count += 1
        if count >= 50:
            break

    print()
    print("=== EXEMPLOS ESPECÍFICOS (ult. 5J, todos os mandos) ===")
    exemplos = [
        ("FLAMENGO",   "ATACANTE",  "1PG"),
        ("PALMEIRAS",  "GOLEIRO",   "50%SG"),
        ("BOTAFOGO",   "VOLANTE",   "2DS"),
        ("BAHIA",      "MEIA",      "1PG"),
        ("FLUMINENSE", "ZAGUEIRO",  "2DS"),
        ("CRUZEIRO",   "MEIA",      "1PG"),
        ("CORINTHIANS","GOLEIRO",   "3DEF"),
    ]
    for time, pos, scout in exemplos:
        entry = res5.get(time, {}).get(pos, {}).get(scout, {})
        conq = entry.get("conquistado")
        ced  = entry.get("cedido")
        print(f"\n  {time} | {pos} | {scout}")
        print(f"    conquistado: {conq}")
        print(f"    cedido:      {ced}")

    print()
    print("=== CRUZAMENTO: Flamengo ATACANTE 1PG (conq) x adversário cedeu (ced) ===")
    res_casa = calcular_recorrencia(records, mando_filter="Casa", n_jogos=5)
    res_fora = calcular_recorrencia(records, mando_filter="Fora", n_jogos=5)
    print("Flamengo ATACANTE 1PG conquistado (ult.5J, Casa):",
          res_casa.get("FLAMENGO", {}).get("ATACANTE", {}).get("1PG", {}).get("conquistado"))
    print("Flamengo ATACANTE 1PG conquistado (ult.5J, Fora):",
          res_fora.get("FLAMENGO", {}).get("ATACANTE", {}).get("1PG", {}).get("conquistado"))
    print("Botafogo ATACANTE 1PG cedido (ult.5J, Casa):",
          res_casa.get("BOTAFOGO", {}).get("ATACANTE", {}).get("1PG", {}).get("cedido"))

    print()
    print("=== VERIFICAÇÃO: número de jogos únicos por time na janela ===")
    res_check = calcular_recorrencia(records, mando_filter=None, n_jogos=5)
    # Mostrar fração para confirmar que total <= 5
    for time in ["FLAMENGO", "PALMEIRAS", "BOTAFOGO", "BAHIA"]:
        entry = res_check.get(time, {})
        for pos in entry:
            for scout in entry[pos]:
                for lado in entry[pos][scout]:
                    frac = entry[pos][scout][lado]["fracao"]
                    total_j = int(frac.split("-")[1])
                    if total_j > 5:
                        print(f"  ALERTA: {time} {pos} {scout} {lado} = {frac} (>{5})")
    print("  (sem alertas = janela correta)")
