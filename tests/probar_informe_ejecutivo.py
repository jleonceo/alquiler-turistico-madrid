"""Prueba scripts/informe_ejecutivo.py: sus guardias tienen que parar y su salida tiene que seguir hasta el JSON.

Trabaja en una carpeta temporal, con una copia de informes/indicadores.json que cada caso estropea a propósito. Sale con 0 si
pasa y con 1 si falla.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_informe_ejecutivo.py
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "informe_ejecutivo.py"
sys.path.insert(0, str(CASO / "scripts"))
FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[-500:]}"))
    if not bien:
        FALLOS.append(nombre)


def lanzar(tmp, datos):
    """Lanza el script con un JSON de indicadores propio y una carpeta de salida propia, sin PDF."""
    entrada = Path(tmp) / "indicadores.json"
    entrada.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    entorno = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--indicadores", str(entrada), "--salida", str(tmp), "--sin-pdf"], capture_output=True, text=True, encoding="utf-8", env=entorno)


def visible(html):
    """Texto visible de un HTML, sin estilos."""
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def principal():
    """Recorre las guardias y la salida buena."""
    base = json.loads((CASO / "informes" / "indicadores.json").read_text(encoding="utf-8"))

    # Casos que tienen que parar: las cifras dejan de decir lo que dice una frase.
    malos = {}
    x = copy.deepcopy(base)
    x["preguntas"][1]["firmes"] = ["Ventas"]
    malos["cambian los firmes"] = x
    x = copy.deepcopy(base)
    f = next(k for k in x["preguntas"][1]["fichas_del_grupo"] if k["barrio"] == "Ventas")
    f["cuartil_bajo_pct"] = 1.0
    malos["un firme no supera el cuartil bajo de la base"] = x
    x = copy.deepcopy(base)
    next(k for k in x["preguntas"][1]["con_un_ano_o_mas"]["barrios"] if k["barrio"] == "San Diego")["en_el_mejor_cuarto"] = True
    malos["San Diego deja de sostenerse menos"] = x
    x = copy.deepcopy(base)
    x["preguntas"][1]["que_ordena_la_lista"]["pares"][0]["se_distinguen"] = True
    malos["la lista se distingue de elegir por precio"] = x
    x = copy.deepcopy(base)
    next(k for k in x["preguntas"][2]["pares_dentro_del_grupo"] if {k["a"], k["b"]} == {"Opañel", "San Diego"})["se_distinguen"] = False
    malos["San Diego deja de quedar por debajo de Opañel"] = x
    x = copy.deepcopy(base)
    x["preguntas"][0]["sensibilidad_superficie"]["combinaciones"][0]["medianas"]["3"] = 99.0
    malos["3 habitaciones gana una combinación"] = x
    x = copy.deepcopy(base)
    x["preguntas"][1]["referencia_baratos"]["comparados"]["cuantos"] = 7
    malos["cambian los barrios baratos"] = x
    x = copy.deepcopy(base)
    x.pop("fecha_datos")
    malos["falta fecha_datos"] = x
    for nombre, datos in malos.items():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            r = lanzar(tmp, datos)
            caso(f"para si {nombre}", r.returncode != 0, r.stdout + r.stderr)
            caso(f"no deja salida si {nombre}", not (Path(tmp) / "informe_ejecutivo.html").exists())

    # La salida buena.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        r = lanzar(tmp, base)
        caso("acaba bien con los datos del caso", r.returncode == 0, r.stdout + r.stderr)
        html = (Path(tmp) / "informe_ejecutivo.html").read_text(encoding="utf-8")
        j = json.loads((Path(tmp) / "informe_ejecutivo.json").read_text(encoding="utf-8"))
        texto = visible(html)
        import cifras_informes as ci
        caso("cada cifra del texto tiene clave o constante con origen", not ci.cifras_sin_rastro(texto, [x["cifra"] for x in j["rastro"]]), ci.cifras_sin_rastro(texto, [x["cifra"] for x in j["rastro"]]))
        # Una cifra plantada tiene que saltar: si no, la comprobación de arriba no prueba nada.
        caso("una cifra sin rastro se detecta", ci.cifras_sin_rastro(texto + " 987,6 %", [x["cifra"] for x in j["rastro"]]) != [])
        for clave in ("fecha_datos", "fecha_ejecucion", "rastro", "acciones", "palabras_por_apartado"):
            caso(f"el JSON trae {clave}", clave in j)
        caso("fecha de datos igual que indicadores", j["fecha_datos"] == base["fecha_datos"])
        for nombre, tope in {"titulo_y_resumen": 300, "encontrado": 400, "limites": 100, "recomendaciones": 200, "anexo": 500}.items():
            caso(f"{nombre} dentro de su tope", j["palabras_por_apartado"][nombre] <= tope, j["palabras_por_apartado"][nombre])
        caso("el límite va antes de la primera viñeta", texto.index("lista de dónde buscar") < texto.index("10,8 %"))
        for frase in ("en el Ayuntamiento", "asesoramiento jurídico", "CC BY 4.0", "Origen de los datos: Ayuntamiento de Madrid", "Colegio de Registradores de España", "solo a Ventas", "tope de 255 días", "no es beneficio"):
            caso(f"dice «{frase}»", frase in texto)
        caso("tres acciones", len(j["acciones"]) == 3)
        for a in j["acciones"]:
            caso(f"la acción sale en resumen y en recomendaciones: {a['nombre']}", texto.count(a["nombre"]) >= 2)
        caso("el anexo empieza en página nueva", "break-before: page" in html)
        caso("sin colores por nivel ni recuadros", "box-shadow" not in html and "list-style: none" not in html)
    print(f"{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
