"""
Plataforma de Análise de Recorrência — Cartola FC
Uso:  python app.py
Abre: http://localhost:5000
"""
import sys, os, importlib, json, re, io, zipfile
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_file, send_from_directory

app = Flask(__name__, static_folder=None)
BASE_DIR  = os.path.abspath(os.path.dirname(__file__))
XLSX_NAME = "Scouts Pós R12 2026.xlsx"

# ── carrega módulos na inicialização ──────────────────────────────────────────
import motor  as _motor
import painel as _painel

def _reload_modules():
    """Recarrega motor + painel após trocar a planilha."""
    importlib.reload(_motor)
    importlib.reload(_painel)

# ── helpers ───────────────────────────────────────────────────────────────────
def _ler_rodadas():
    path = os.path.join(BASE_DIR, "RODADAS_BRASILEIRAO_2026.txt")
    nums = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"Rodada\s+(\d+)", line)
            if m:
                nums.append(int(m.group(1)))
    return sorted(set(nums))

def _xlsx_info():
    p = os.path.join(BASE_DIR, XLSX_NAME)
    if not os.path.exists(p):
        return {"existe": False, "mtime": None, "rodadas_xlsx": 0}
    import openpyxl
    from datetime import datetime
    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    ws = wb["Por jogo"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    headers = rows[0]
    col_data = {h: i for i, h in enumerate(headers)}.get("Data")
    max_rod = 0
    if col_data is not None:
        for r in rows[1:]:
            v = r[col_data]
            if isinstance(v, datetime):
                max_rod += 1
    return {"existe": True, "mtime": os.path.getmtime(p), "rodadas_xlsx": max_rod}

# ── static assets ─────────────────────────────────────────────────────────────
@app.route("/fonts/<path:n>")
def serve_font(n):    return send_from_directory(os.path.join(BASE_DIR, "fonts"), n)

@app.route("/logos/<path:n>")
def serve_logo(n):    return send_from_directory(os.path.join(BASE_DIR, "logos"), n)

@app.route("/teams/<path:n>")
def serve_team(n):    return send_from_directory(os.path.join(BASE_DIR, "teams"), n)

@app.route("/artes/<path:n>")
def serve_arte(n):    return send_from_directory(os.path.join(BASE_DIR, "artes"), n)

# ── frontend ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_file(os.path.join(BASE_DIR, "plataforma.html"))

# ── API ───────────────────────────────────────────────────────────────────────
@app.route("/api/info")
def api_info():
    rodadas = _ler_rodadas()
    xlsx    = _xlsx_info()
    return jsonify({
        "xlsx_nome":      XLSX_NAME,
        "xlsx_existe":    xlsx["existe"],
        "xlsx_mtime":     xlsx["mtime"],
        "rodadas":        rodadas,
        "scouts_default": _motor.SCOUTS_POS,
    })

@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("planilha")
    if not f:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400
    if not f.filename.endswith(".xlsx"):
        return jsonify({"erro": "Envie um arquivo .xlsx"}), 400
    dest = os.path.join(BASE_DIR, XLSX_NAME)
    f.save(dest)
    try:
        _reload_modules()
        return jsonify({"ok": True, "nome": f.filename})
    except Exception as ex:
        import traceback
        return jsonify({"erro": str(ex), "trace": traceback.format_exc()}), 500

@app.route("/api/gerar", methods=["POST"])
def api_gerar():
    d            = request.get_json() or {}
    n_jogos      = int(d.get("n_jogos", 5))
    rodada       = int(d.get("rodada", 12))
    scouts_str   = (d.get("scouts") or "").strip()
    mando_filter = (d.get("mando_filter") or "por_mando").strip().lower()
    dpr          = int(d.get("dpr") or 3)
    dpr          = max(1, min(dpr, 4))
    if mando_filter not in ("por_mando", "geral"):
        mando_filter = "por_mando"

    try:
        from exportar import exportar_png
        scouts_override = _painel._parse_scouts_arg(scouts_str) if scouts_str else {}
        png_paths = exportar_png(
            n_jogos=n_jogos, rodada=rodada,
            scouts_override=scouts_override, mando_filter=mando_filter, dpr=dpr
        )
        if not png_paths:
            return jsonify({"ok": True, "artes": [],
                            "msg": "Nenhum sinal encontrado para esta rodada/janela."})

        pngs = [os.path.basename(p) for p in png_paths]
        return jsonify({"ok": True, "artes": pngs,
                        "n_jogos": n_jogos, "rodada": rodada})
    except Exception as ex:
        import traceback
        return jsonify({"erro": str(ex), "trace": traceback.format_exc()}), 500

@app.route("/api/download_zip")
def api_download_zip():
    rodada  = request.args.get("rodada", "")
    n_jogos = request.args.get("n", "")
    sufixo  = f"r{rodada}_ult{n_jogos}"
    artes_dir = os.path.join(BASE_DIR, "artes")
    files = sorted(
        f for f in os.listdir(artes_dir)
        if f.endswith(".png") and sufixo in f
    )
    if not files:
        return jsonify({"erro": "Nenhum PNG encontrado."}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(os.path.join(artes_dir, f), f)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True,
        download_name=f"artes_{sufixo}.zip",
        mimetype="application/zip"
    )

# ── entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Abre navegador só quando rodando localmente (não em servidor na nuvem)
    if port == 5000 and not os.environ.get("RAILWAY_ENVIRONMENT"):
        import webbrowser, threading
        def _abrir():
            import time; time.sleep(0.9)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=_abrir, daemon=True).start()
    print("=" * 54)
    print(f"  Plataforma iniciada na porta {port}")
    print("  Ctrl+C para encerrar")
    print("=" * 54)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
