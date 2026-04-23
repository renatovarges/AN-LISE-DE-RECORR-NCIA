"""
Exportação PNG das artes por posição — qualidade premium (3x DPR).
Uso: python exportar.py <n_jogos> <rodada> [--mando por_mando|geral] [--dpr 3]
Ex:  python exportar.py 5 12
     python exportar.py 5 12 --mando geral --dpr 4
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from painel import gerar_todas_artes

# Device Pixel Ratio (DPR): 3 = ~3240px de largura, qualidade premium para redes sociais.
# Aceita override via argumento --dpr (2 a 4 recomendado)
DEFAULT_DPR = 3

# Args Chromium que otimizam rendering de tipografia e subpixel antialiasing
_CHROME_ARGS = [
    "--font-render-hinting=none",
    "--disable-font-subpixel-positioning",
    "--disable-lcd-text",
    "--enable-font-antialiasing",
    "--force-color-profile=srgb",
]

def exportar_png(n_jogos, rodada, scouts_override=None, mando_filter="por_mando", dpr=DEFAULT_DPR):
    print(f"Gerando HTMLs: ult.{n_jogos}J - Rodada {rodada} - mando={mando_filter} - dpr={dpr}x")
    htmls = gerar_todas_artes(
        n_jogos=n_jogos, rodada=rodada,
        scouts_override=scouts_override, mando_filter=mando_filter
    )
    if not htmls:
        print("Nenhuma arte gerada.")
        return []

    from playwright.sync_api import sync_playwright

    pngs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_CHROME_ARGS)
        ctx = browser.new_context(
            viewport={"width": 1080, "height": 800},
            device_scale_factor=dpr,
            color_scheme="light",
            reduced_motion="reduce",
        )
        page = ctx.new_page()

        for html_path in htmls:
            abs_path = os.path.abspath(html_path).replace("\\", "/")
            png_path = html_path.replace(".html", ".png")

            page.goto(f"file:///{abs_path}", wait_until="networkidle")
            # aguarda webfonts totalmente carregadas
            page.evaluate("document.fonts && document.fonts.ready")
            # aguarda todas as imagens decodificarem (evita borrão em escudos/fotos)
            page.evaluate("""
              Promise.all(Array.from(document.images).map(img =>
                img.decode ? img.decode().catch(()=>{}) : Promise.resolve()
              ))
            """)
            # captura apenas o .arte-wrap em device pixel ratio elevado
            page.locator(".arte-wrap").screenshot(
                path=png_path,
                omit_background=False,
                animations="disabled",
                scale="device",      # respeita device_scale_factor
                type="png",          # lossless
            )

            size_kb = os.path.getsize(png_path) // 1024
            print(f"  {png_path}  ({size_kb} KB @ {dpr}x)")
            pngs.append(png_path)

        browser.close()

    return pngs


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        print("Uso: python exportar.py <n_jogos> <rodada> [--mando por_mando|geral]")
        print("Ex:  python exportar.py 5 12")
        sys.exit(1)
    n_jogos = int(args[0])
    rodada  = int(args[1])

    mando_filter = "por_mando"
    if "--mando" in args:
        idx = args.index("--mando")
        if idx + 1 < len(args):
            v = args[idx + 1].strip().lower()
            if v in ("geral", "por_mando"):
                mando_filter = v

    dpr = DEFAULT_DPR
    if "--dpr" in args:
        idx = args.index("--dpr")
        if idx + 1 < len(args):
            try:
                dpr = max(1, min(int(args[idx + 1]), 4))
            except ValueError:
                pass

    pngs = exportar_png(n_jogos=n_jogos, rodada=rodada, mando_filter=mando_filter, dpr=dpr)
    print(f"\n{len(pngs)} PNG(s) gerado(s) em artes/")
