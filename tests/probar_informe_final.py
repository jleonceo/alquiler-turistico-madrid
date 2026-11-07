"""Prueba scripts/informe_final.py: sus guardias tienen que parar y su salida tiene que seguir hasta el JSON.

Trabaja en una carpeta temporal, con una copia de informes/indicadores.json que cada caso estropea a propósito. Sale con 0 si
pasa y con 1 si falla.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_informe_final.py
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
SCRIPT = CASO / "scripts" / "informe_final.py"
sys.path.insert(0, str(CASO / "scripts"))
FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[-600:]}"))
    if not bien:
        FALLOS.append(nombre)


def lanzar(tmp, datos):
    """Lanza el script con un JSON de indicadores propio y una carpeta de salida propia."""
    entrada = Path(tmp) / "indicadores.json"
    entrada.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    entorno = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--indicadores", str(entrada), "--salida", str(tmp)], capture_output=True, text=True, encoding="utf-8", env=entorno)


def visible(html):
    """Texto visible de un HTML, sin estilos, guiones ni dibujos."""
    html = re.sub(r"<style.*?</style>|<script.*?</script>|<svg.*?</svg>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def principal():
    """Recorre las guardias y la salida buena."""
    base = json.loads((CASO / "informes" / "indicadores.json").read_text(encoding="utf-8"))

    # Casos que tienen que parar.
    malos = {}
    x = copy.deepcopy(base)
    x["preguntas"][1]["cuatro_de_cinco"] = ["Opañel"]
    malos["cambian los que siguen en la lista 4 veces"] = x
    x = copy.deepcopy(base)
    x["preguntas"][2]["pares_dentro_del_grupo"][0]["se_distinguen"] = True
    malos["cambian los pares que se distinguen"] = x
    x = copy.deepcopy(base)
    x.pop("fecha_datos")
    malos["falta fecha_datos"] = x
    for nombre, datos in malos.items():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            r = lanzar(tmp, datos)
            caso(f"para si {nombre}", r.returncode != 0, r.stdout + r.stderr)
            caso(f"no deja salida si {nombre}", not (Path(tmp) / "informe_final.html").exists())

    # La salida buena.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        r = lanzar(tmp, base)
        caso("acaba bien con los datos del caso", r.returncode == 0, r.stdout + r.stderr)
        html = (Path(tmp) / "informe_final.html").read_text(encoding="utf-8")
        rastro = json.loads((Path(tmp) / "informe_final_rastro.json").read_text(encoding="utf-8"))
        csv = (Path(tmp) / "informe_final_graficos.csv").read_text(encoding="utf-8-sig")
        texto = visible(html)
        import cifras_informes as ci
        faltan = ci.cifras_sin_rastro(texto, [x["cifra"] for x in rastro["rastro"]])
        caso("cada cifra del texto tiene clave o constante con origen", not faltan, faltan)
        caso("una cifra sin rastro se detecta", ci.cifras_sin_rastro(texto + " 987,6 %", [x["cifra"] for x in rastro["rastro"]]) != [])
        paginas = rastro["paginas"]
        sin_anexo = [p for p in paginas if p["tipo"] != "anexo"]
        caso("15 páginas como mucho sin el anexo", len(sin_anexo) <= 15, len(sin_anexo))
        caso("unas 120 palabras por página de pregunta", all(p["palabras"] <= 140 for p in paginas if p["tipo"] == "pregunta"), [(p["titulo"], p["palabras"]) for p in paginas if p["palabras"] > 140 and p["tipo"] == "pregunta"])
        caso("ningún título con dos puntos", not [p["titulo"] for p in paginas if ":" in p["titulo"]], [p["titulo"] for p in paginas])
        caso("el mapa está en el informe", html.count('aria-label="Los recomendados') >= 1 or "Centro histórico</text>" in html)
        caso("cada barrio del grupo lleva su etiqueta en el mapa", all(f"{b.replace('Angel', 'Ángel')}: " in html for b in base["preguntas"][1]["grupo"]))
        caso("el CSV de los gráficos trae cabecera", csv.startswith("pagina;grafico;grupo;medida;cifra;unidad"))
        caso("el CSV trae filas", len(csv.splitlines()) > 20, len(csv.splitlines()))
        caso("resumen abre con el límite antes de las preguntas", texto.index("primera criba") < texto.index("Pregunta Respuesta"))
        for frase in ("en el Ayuntamiento", "asesoramiento jurídico", "CC BY 4.0", "Origen de los datos: Ayuntamiento de Madrid", "Colegio de Registradores de España", "solo sigue el barrio de Ventas", "máximo de 255", "gastos, impuestos ni comisiones", "Datos personales", "seudonimización", "Inside Airbnb, Madrid, descarga"):
            caso(f"dice «{frase}»", frase in texto)
        caso("nombra las tres acciones del ejecutivo", all(a["nombre"] in texto for a in rastro["acciones"]))
    print(f"{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
