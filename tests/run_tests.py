"""Pasa todas las pruebas de tests/ y dice cuántos casos ejecuta.

Cada banco se lanza con -W error, en su propio proceso. Los que abren datos que el repositorio no trae se saltan con su motivo
si faltan: se ejecutan después de `python ejecutar.py --completo`. Sale con 0 si todo lo ejecutado pasa y con 1 si algo falla.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CASO = AQUI.parent
PROCESADO = "data/processed/analisis_anuncios.parquet"
ORIGEN = "data/raw/listings_2026-09-17.csv.gz"
# Los bancos que abren datos reales, con el fichero sin el que no pueden ejecutarse.
NECESITA = {"probar_portada.py": "data/publicado/pisos_fuera_del_centro.csv.gz", "probar_cifras_por_otro_camino.py": ORIGEN, "probar_preparacion_por_otro_camino.py": ORIGEN,
            "probar_indicadores_por_otro_camino.py": PROCESADO, "probar_cuadro_mando.py": PROCESADO, "probar_frase_solo_ventas.py": PROCESADO,
            "probar_informe_final.py": "data/processed/barrios_poligonos_corregido.parquet", "probar_revision_de_la_entrega.py": "informes/indicadores.json"}


def contar(salida):
    """Cuenta los casos que un banco da por buenos."""
    return len(re.findall(r"^\s*ok\b", salida, flags=re.M))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    casos, rojos, saltados = 0, [], []
    for banco in sorted(AQUI.glob("probar_*.py")):
        falta = NECESITA.get(banco.name)
        if falta and not (CASO / falta).exists():
            saltados.append(banco.name)
            print(f"[sin datos] {banco.name}: falta {falta}", flush=True)
            continue
        inicio = time.time()
        r = subprocess.run([sys.executable, "-W", "error", str(banco)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONUTF8": "1"}, cwd=CASO)
        n = contar(r.stdout)
        casos += n
        print(f"[{'ok' if r.returncode == 0 else 'ROJO'}] {banco.name}: {n} casos, {time.time() - inicio:.0f} s", flush=True)
        if r.returncode:
            rojos.append(banco.name)
            print((r.stdout + r.stderr)[-1500:])
    if saltados:
        print(f"{len(saltados)} bancos sin ejecutar porque abren datos que el repositorio no trae: {', '.join(saltados)}")
    if rojos:
        print(f"ROJO: fallan {len(rojos)} bancos: {', '.join(rojos)}")
        sys.exit(1)
    print(f"VERDE: {casos}/{casos} casos")
