"""Prueba que scripts/rehacer_portada.py rehace la portada, y que da rojo cuando una cifra o la tabla cambian.

Usa la tabla local de data/publicado/, que deja `python ejecutar.py --completo`, los dos README e informes/indicadores.json. Sale con 0 si pasa.
"""
import copy
import json
import sys
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
import rehacer_portada as rp  # noqa: E402

FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[:300]}"))
    if not bien:
        FALLOS.append(nombre)


filas = rp.leer()
r = rp.calcular(filas)
j = json.loads(rp.INDICADORES.read_text(encoding="utf-8"))

# Lo que tiene que salir.
caso("sin número de anuncio ni coordenadas en la tabla", not ({"id", "latitud", "longitud", "anuncios_anfitrion"} & set(filas[0])), set(filas[0]))
caso("coincide con indicadores.json", not rp.contra_indicadores(r, j), rp.contra_indicadores(r, j))
caso("los dos README llevan las cifras", not rp.contra_readme(r), rp.contra_readme(r))
caso("los recomendados son tres", r["firmes"] == ["Numancia", "San Diego", "Ventas"], r["firmes"])
caso("ningún barrio con menos de 20 pisos lleva su nombre", min(sum(1 for x in filas if x["barrio"] == b) for b in {x["barrio"] for x in filas}) >= 20)

# Controles que tienen que salir en rojo.
tocado = copy.deepcopy(r)
tocado["ingreso_anual"] += 500
caso("rojo si el ingreso cambia", rp.contra_indicadores(tocado, j))
tocado = copy.deepcopy(r)
tocado["firmes"] = ["Numancia", "Ventas"]
caso("rojo si cae un barrio recomendado", rp.contra_indicadores(tocado, j))
tocado = copy.deepcopy(r)
tocado["rentabilidad"] += 1
caso("rojo si el README no lleva la cifra", rp.contra_readme(tocado))
sin_filas = rp.calcular([x for x in filas if not (x["barrio"] == "San Diego" and x["dormitorios"] == 1)])
caso("rojo si faltan filas de un barrio recomendado", rp.contra_indicadores(sin_filas, j))

print("VERDE" if not FALLOS else f"ROJO: {FALLOS}")
sys.exit(1 if FALLOS else 0)
