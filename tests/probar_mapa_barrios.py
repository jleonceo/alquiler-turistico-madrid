"""Prueba scripts/mapa_barrios.py con polígonos pequeños escritos aquí. Sale con 0 si pasa y con 1 si falla.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_mapa_barrios.py
"""
import re
import sys
from pathlib import Path

import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[-300:]}"))
    if not bien:
        FALLOS.append(nombre)


def principal():
    """Recorre el mapa bueno y los que tienen que parar."""
    import mapa_barrios as mb
    cuadrado = lambda x, y: shapely.box(x, y, x + 0.01, y + 0.01)
    poligonos = {"Norte": cuadrado(-3.70, 40.46), "Sur": cuadrado(-3.70, 40.40), "Este": cuadrado(-3.60, 40.43), "Otro": cuadrado(-3.75, 40.43)}
    clases = {"Norte": "5 de 5 veces", "Sur": "4 de 5 veces", "Este": "menos de 4 veces"}
    limite = cuadrado(-3.72, 40.42)
    svg = mb.mapa(poligonos, clases, limite)
    caso("empieza por <svg", svg.lstrip().startswith("<svg"))
    caso("un dato con etiqueta por barrio del grupo", svg.count('class="dato"') == 3, svg.count('class="dato"'))
    caso("cada barrio del grupo lleva su clase en la etiqueta", "<title>Norte: 5 de 5 veces</title>" in svg and "<title>Sur: 4 de 5 veces</title>" in svg)
    caso("el barrio sin clase va sin etiqueta", "<title>Otro" not in svg)
    caso("cada barrio del grupo lleva su nombre escrito", all(f">{b}</text>" in svg for b in clases))
    caso("cada clase sale en la leyenda", all(f">{c}</text>" in svg for c in ("5 de 5 veces", "4 de 5 veces", "Menos de 4 veces")))
    caso("rotula el centro histórico", ">Centro histórico</text>" in svg)
    ids = re.findall(r'\bid="([^"]+)"', svg)
    caso("identificadores únicos", len(ids) == len(set(ids)), ids)
    caso("sin color fuera de la paleta", set(re.findall(r'#[0-9a-f]{6}', svg)) <= {"#2a78d6", "#eb6834", "#1baf7a", "#e1e0d9", "#ffffff", "#0b0b0b", "#52514e", "#898781"}, set(re.findall(r'#[0-9a-f]{6}', svg)))
    caso("el naranja es de los barrios que siguen en la lista 4 veces, y los de 5 de 5 van en azul", re.search(r'<title>Sur: 4 de 5 veces</title><path[^>]*fill="#eb6834"', svg) is not None and re.search(r'<title>Norte: 5 de 5 veces</title><path[^>]*fill="#2a78d6"', svg) is not None)
    try:
        mb.mapa(poligonos, {"Falta": "5 de 5 veces"}, limite)
        caso("para si un barrio del grupo no tiene polígono", False)
    except ValueError:
        caso("para si un barrio del grupo no tiene polígono", True)
    try:
        mb.mapa(poligonos, {"Norte": "dudoso"}, limite)
        caso("para con una clase desconocida", False)
    except ValueError:
        caso("para con una clase desconocida", True)
    print(f"{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
