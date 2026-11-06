"""Prueba scripts/interpretacion_resultados.py con una copia de informes/indicadores.json. Sale con 0 si pasa y con 1 si falla.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_interpretacion_resultados.py
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "interpretacion_resultados.py"
sys.path.insert(0, str(CASO / "scripts"))
FALLOS = []
SECCIONES = ["## Pregunta y objetivo", "## Grandes números", "## La historia", "## Nivel de confianza", "## Lo que no se puede afirmar", "## Decisión que permite", "## Cifras pendientes", "## Fuentes", "## Límite de este documento"]


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[-400:]}"))
    if not bien:
        FALLOS.append(nombre)


def lanzar(tmp, datos):
    """Lanza el script con un JSON propio y una carpeta de salida propia."""
    entrada = Path(tmp) / "indicadores.json"
    entrada.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--indicadores", str(entrada), "--salida", str(tmp)], capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})


def principal():
    """Recorre el caso que tiene que parar y la salida buena."""
    base = json.loads((CASO / "informes" / "indicadores.json").read_text(encoding="utf-8"))
    malo = copy.deepcopy(base)
    malo["preguntas"][1]["firmes"] = ["Numancia"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        r = lanzar(tmp, malo)
        caso("para si cambian los firmes", r.returncode != 0, r.stdout + r.stderr)
        caso("no deja documento si para", not (Path(tmp) / "interpretacion_resultados.md").exists())
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        r = lanzar(tmp, base)
        caso("acaba bien con los datos del caso", r.returncode == 0, r.stdout + r.stderr)
        md = (Path(tmp) / "interpretacion_resultados.md").read_text(encoding="utf-8")
        for s in SECCIONES:
            caso(f"trae {s}", s in md)
        caso("las secciones van en orden", [md.index(s) for s in SECCIONES] == sorted(md.index(s) for s in SECCIONES))
        caso("da nivel de confianza", "Confianza media" in md)
        import cifras_informes as ci
        cuerpo, inventario = md.split("## Inventario de evidencias")
        ci.sin_jerga(cuerpo.split("## Fuentes")[0])
        for x in base["preguntas"][1]["firmes"]:
            caso(f"nombra {x}", x in cuerpo)
        caso("el inventario da la ruta de cada cifra", "informes/indicadores.json" in inventario and inventario.count("|") > 40)
        for frase in ("en el Ayuntamiento", "asesoramiento jurídico", "CC BY 4.0", "Origen de los datos: Ayuntamiento de Madrid", "Colegio de Registradores de España", "solo a Ventas", "Datos personales"):
            caso(f"dice «{frase}»", frase in md)
    print(f"{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
