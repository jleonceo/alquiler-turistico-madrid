"""Punto de entrada del repositorio.

  python ejecutar.py             pasa las pruebas que no necesitan los datos de Inside Airbnb
  python ejecutar.py --completo  descarga las fotos una vez y repite la cadena entera, hasta las tres salidas
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

CASO = Path(__file__).resolve().parent
CADENA = ["descargar_datos", "diccionario_datos", "calidad_datos", "correccion_datos", "modelo_datos", "integracion_datos", "transformacion_datos",
          "analisis_exploratorio", "indicadores", "interpretacion_resultados", "informe_ejecutivo", "informe_final", "cuadro_mando", "tabla_publicada"]


def lanzar(*orden):
    """Ejecuta un paso y para la cadena si falla."""
    print(f"\n>> {' '.join(orden)}", flush=True)
    r = subprocess.run([sys.executable, "-W", "error", *orden], cwd=CASO, env={**os.environ, "PYTHONUTF8": "1"})
    if r.returncode:
        sys.exit(r.returncode)


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--completo", action="store_true", help="descarga los datos y repite la cadena entera")
    a.add_argument("--origen", help="carpeta con los ficheros de Inside Airbnb ya descargados")
    o = a.parse_args()
    if o.completo:
        for paso in CADENA:
            lanzar(f"scripts/{paso}.py", *(["--origen", o.origen] if paso == "descargar_datos" and o.origen else []))
    if (CASO / "data" / "publicado" / "pisos_fuera_del_centro.csv.gz").exists():
        lanzar("scripts/rehacer_portada.py", "--comprobar")
    lanzar("tests/run_tests.py")
