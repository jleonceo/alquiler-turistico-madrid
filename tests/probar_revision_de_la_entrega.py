"""Prueba cada error de la revisión del 07/11/2026 en lo que lee una persona: portada, informes, cuadro y datos publicados.

Cada caso nació en rojo con la versión anterior. Sale con 0 si todos pasan y con 1 si falla alguno.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_revision_de_la_entrega.py
"""
import html
import json
import re
import sys
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
INFORMES = CASO / "informes"
FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[:240]}"))
    if not bien:
        FALLOS.append(nombre)


def visible(ruta):
    """Texto visible de un HTML, con espacios normales; el cuadro añade sus textos y definiciones."""
    h = ruta.read_text(encoding="utf-8")
    extra = ""
    m = re.search(r'<script type="application/json" id="datos">(.*?)</script>', h, re.S)
    if m:
        d = json.loads(m.group(1).replace(chr(60) + chr(92) + "/", "</"))
        extra = " ".join(d["definiciones"].values()) + " " + json.dumps(d["textos"], ensure_ascii=False)
    limpio = re.sub(r"<style.*?</style>|<script.*?</script>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", limpio)) + " " + extra).replace(" ", " ")


def textos():
    """Todo lo que lee una persona."""
    t = {f.name: visible(f) for f in (INFORMES / "informe_ejecutivo.html", INFORMES / "informe_final.html", INFORMES / "cuadro_mando.html", CASO / "index.html")}
    for f in (INFORMES / "interpretacion_resultados.md", CASO / "README.md", CASO / "README.en.md", CASO / "docs" / "metodo.md", CASO / "docs" / "reglas_de_negocio.md", CASO / "docs" / "criterios_de_datos.md", CASO / "docs" / "datos.md"):
        t[f.name] = re.sub(r"\s+", " ", f.read_text(encoding="utf-8")).replace(" ", " ")
    return t


VETADAS = [r"\bfirmes?\b", r"descuento", r"\bdiscount", r"con aviso", r"con_aviso", r"de reserva", r"\bfoto\b", r"podría ser cero", r"could be zero", r"conserva su clase", r"se mantiene\b", r"se mantienen", r"Eso da", r"en todas las superficies",
           r"\d\.ª de", r"Barrios que rinden más"]

if __name__ == "__main__":
    t = textos()
    # 1. Lo que no puede salir en ningún texto
    for nombre, texto in t.items():
        for patron in VETADAS:
            halladas = [texto[max(0, m.start() - 40):m.end() + 30] for m in re.finditer(patron, texto, flags=re.I)]
            caso(f"{nombre}: sin «{patron}»", not halladas, halladas[:2])

    # 2. Ejecutivo
    e = t["informe_ejecutivo.html"]
    caso("ejecutivo: la dependencia del máximo se dice antes que las cifras", 0 <= e.find("255") < e.find("12,1 %"), (e.find("255"), e.find("12,1 %")))
    caso("ejecutivo: nombra la lista que queda sin el máximo", all(b in e for b in ("Comillas", "Cuatro Caminos", "Pinar del Rey", "San Andrés")))
    caso("ejecutivo: explica que la rentabilidad se calcula piso a piso", "piso a piso" in e)
    caso("ejecutivo: da la mediana de todos los pisos", "8,3 %" in e)
    caso("ejecutivo: da la compra según barrio y tamaño", "153.916 €" in e and "268.650 €" in e)
    caso("ejecutivo: dice que el piso mediano es de 50 m² en el barrio de Numancia", "50 m² en el barrio de Numancia" in e)
    caso("ejecutivo: explica los 280 anuncios frente a los 256", "280" in e and "256" in e)
    caso("ejecutivo: separa las dos pruebas de contar como cero", "también" in e and "sin precio" in e)

    # 3. Informe final e interpretación
    f, i = t["informe_final.html"], t["interpretacion_resultados.md"]
    for nombre, x in (("final", f), ("interpretación", i)):
        caso(f"{nombre}: dice qué superficie igualaría a los de 3 habitaciones", re.search(r"\d+ m²[^.]*2 habitaciones|2 habitaciones[^.]*\d+ m²", x) and "no se probó otra superficie" in x)
        caso(f"{nombre}: nombra la lista sin el máximo", "Pinar del Rey" in x)
        caso(f"{nombre}: explica la mediana piso a piso", "piso a piso" in x)
    caso("interpretación: no lleva rutas de claves", "preguntas[" not in i and "Inventario de evidencias" not in i)
    caso("interpretación: el rastro está en su fichero", (INFORMES / "interpretacion_rastro.json").exists())
    caso("interpretación: confianza baja en los barrios", "Confianza baja" in i and "barrios" in i[i.find("Confianza baja"):i.find("Confianza baja") + 60])

    # 4. Cuadro
    c = (INFORMES / "cuadro_mando.html").read_text(encoding="utf-8")
    d = json.loads(re.search(r'<script type="application/json" id="datos">(.*?)</script>', c, re.S).group(1).replace(chr(60) + chr(92) + "/", "</"))["textos"]
    caso("cuadro: la tabla de recomendados solo trae recomendados", "barato" not in json.dumps(d["tabla_recomendacion"], ensure_ascii=False))
    caso("cuadro: las cifras grandes dicen que son de todos los pisos", "Cifras de todos los pisos, en mediana" in c)
    caso("cuadro: puesto en masculino", "3.º de 26" in json.dumps(d["tabla_mapa"], ensure_ascii=False))
    caso("cuadro: da la dependencia del máximo arriba", "255" in d["recomendacion"])

    # 5. Datos publicados y portada
    j = (INFORMES / "indicadores.json").read_text(encoding="utf-8")
    caso("indicadores.json: sin claves con firme ni con_aviso", not re.search(r'"[^"]*(firme|con_aviso)[^"]*":', j), re.findall(r'"[^"]*(?:firme|con_aviso)[^"]*":', j)[:5])
    d2 = json.loads(j)
    caso("indicadores.json: compra por barrio y tamaño", len(d2["recomendacion"].get("compra_por_barrio", [])) == 3)
    caso("indicadores.json: superficie que iguala a los de 3 habitaciones", d2["preguntas"][0]["sensibilidad_superficie"].get("tres_habitaciones", {}).get("superficie_para_igualar_a_2_m2", 0) > 0)
    for nombre in ("README.md", "README.en.md"):
        caso(f"{nombre}: nombra la lista sin el máximo", "Pinar del Rey" in t[nombre])
    print(f"{len(FALLOS)} fallos")
    sys.exit(1 if FALLOS else 0)
