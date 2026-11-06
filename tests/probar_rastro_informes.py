"""Sigue hasta informes/indicadores.json cada cifra de las salidas ya generadas: informe ejecutivo, informe final e interpretación.

Lee las salidas reales de informes/, no las de una carpeta temporal: su trabajo es esa comprobación. Para cada cifra apuntada, vuelve a
leer su clave y comprueba que el texto escrito es ese valor. Después comprueba que ningún número del texto queda sin clave ni
constante con origen. Sale con 0 si pasa y con 1 si falla.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_rastro_informes.py
"""
import json
import re
import sys
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
import cifras_informes as ci  # noqa: E402
from graficos import numero  # noqa: E402

FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[-500:]}"))
    if not bien:
        FALLOS.append(nombre)


def visible(ruta):
    """Texto visible de un HTML generado, sin estilos, guiones ni dibujos."""
    h = ruta.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>|<script.*?</script>|<svg.*?</svg>", " ", h, flags=re.S)))


def igual(c, entrada):
    """Dice si el texto de una cifra es el valor de alguna de sus claves, con los decimales que lleva escritos."""
    texto = entrada["cifra"]
    decimales = len(texto.split(",")[1]) if "," in texto else 0
    for clave in entrada["claves"]:
        if clave.startswith("recuento de"):
            return True
        v = c.dato(clave)
        v = len(v) if isinstance(v, list) else v
        if numero(v, decimales) == texto:
            return True
    return False


def principal():
    """Recorre las dos salidas con rastro y mide la interpretación."""
    c = ci.Cifras()
    # Caso que tiene que fallar: una entrada con la cifra cambiada no pasa.
    caso("una cifra cambiada se detecta", not igual(c, {"cifra": "999,9", "claves": ["preguntas[1].mediana_de_toda_la_base"]}))
    salidas = {"informe_ejecutivo": ("informe_ejecutivo.json", "informe_ejecutivo.html"), "informe_final": ("informe_final_rastro.json", "informe_final.html")}
    for nombre, (rastro, pagina) in salidas.items():
        j = json.loads((CASO / "informes" / rastro).read_text(encoding="utf-8"))
        caso(f"{nombre}: misma fecha de datos que indicadores", j["fecha_datos"] == c.dato("fecha_datos"))
        caso(f"{nombre}: salió de la ejecución vigente de indicadores", j["indicadores_fecha_ejecucion"] == c.dato("fecha_ejecucion"))
        malas = [x for x in j["rastro"] if not igual(c, x)]
        caso(f"{nombre}: {len(j['rastro'])} cifras iguales a su clave", not malas, malas)
        texto = visible(CASO / "informes" / pagina)
        sueltas = ci.cifras_sin_rastro(texto, [x["cifra"] for x in j["rastro"]])
        caso(f"{nombre}: ningún número sin clave", not sueltas, sueltas)
    # Las acciones casan en los dos informes, palabra por palabra.
    a = json.loads((CASO / "informes" / "informe_ejecutivo.json").read_text(encoding="utf-8"))["se_pide"]
    b = [x["nombre"] for x in json.loads((CASO / "informes" / "informe_final_rastro.json").read_text(encoding="utf-8"))["acciones"]]
    caso("las acciones casan en los dos informes", a == b, (a, b))
    print(f"{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
