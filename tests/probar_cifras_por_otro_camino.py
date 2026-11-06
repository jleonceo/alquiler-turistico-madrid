"""Rehace por otro camino las cifras de los dos JSON, sin pandas, leyendo data/raw/ solo para mirar.

Usa gzip, csv y statistics de la biblioteca estándar. Comprueba con la misma regla y la misma población que los scripts:
filas, un recuento de vacíos, la base de decisión y la mediana de un barrio. Después compara los controles con
tests/cifras_de_referencia.json. Sale con 0 si todo coincide y con 1 si algo no.

Esta prueba abre los datos reales: su trabajo es esa comprobación. Tarda un minuto largo por el calendario.
"""
import csv
import gzip
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

CASO = Path(__file__).resolve().parents[1]
RAW = CASO / "data" / "raw"
csv.field_size_limit(10_000_000)
# La mediana de Opañel del cuaderno de reconocimiento, sección 8 bis, y su precio del m², leído de su libro abajo.
RENTABILIDAD_OPANEL = 18.7
FALLOS = []


def caso(nombre, obtenido, esperado):
    """Compara dos cifras y dice si coinciden."""
    bien = obtenido == esperado
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}: {obtenido}" + ("" if bien else f" frente a {esperado}"))
    if not bien:
        FALLOS.append(nombre)


def filas_de(ruta):
    """Recorre un CSV comprimido como diccionarios de texto."""
    with gzip.open(ruta, "rt", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def banos(texto):
    """Lee los baños del texto, igual que dicen las reglas §5."""
    t = texto.lower()
    if not t:
        return None
    if "half" in t:
        return 0.5
    if "no bathroom" in t:
        return 0.0
    numero = t.split()[0]
    return float(numero) if numero.replace(".", "").isdigit() else None


def superficie(d, b):
    """Aplica la superficie de valoraciones de las reglas §6."""
    if d > 3 or b >= 3:
        return 140.0
    if d == 3:
        return 110.0 if b >= 2 else 90.0
    return 65.0 if d == 2 else 50.0


def dentro_del_limite(x, y, anillo):
    """Dice si un punto cae dentro de un anillo, por el cruce de rayos."""
    dentro = False
    j = len(anillo) - 1
    for i in range(len(anillo)):
        xi, yi, xj, yj = anillo[i][0], anillo[i][1], anillo[j][0], anillo[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def principal():
    """Recorre las comprobaciones."""
    dicc = json.loads((CASO / "config/fuentes/diccionario-datos-origen.json").read_text(encoding="utf-8"))
    cal_json = json.loads((CASO / "informes/calidad-datos.json").read_text(encoding="utf-8"))
    tablas = {t["tabla"]: t for t in dicc["tablas"]}
    ref = json.loads((CASO / "tests/cifras_de_referencia.json").read_text(encoding="utf-8"))

    estancia_calendario, n_calendario = defaultdict(lambda: 10 ** 9), 0
    for fila in filas_de(RAW / "calendar_2026-09-17.csv.gz"):
        n_calendario += 1
        if fila["minimum_nights"]:
            estancia_calendario[fila["listing_id"]] = min(estancia_calendario[fila["listing_id"]], int(fila["minimum_nights"]))
    caso("filas del calendario", n_calendario, tablas["calendar_2026-09-17"]["filas"])
    caso("filas del calendario, control", n_calendario, ref["dias_calendario"])

    n_resenas = sum(1 for _ in filas_de(RAW / "reviews_fechas_2026-09-17.csv.gz"))
    caso("filas de las reseñas", n_resenas, tablas["reviews_fechas_2026-09-17"]["filas"])

    limite = json.loads((RAW / "externos/ape_00_01.json").read_text(encoding="utf-8"))["features"][0]["geometry"]["rings"][0]
    n, vacias, dentro, base, base_final, rent = 0, 0, 0, 0, 0, defaultdict(list)
    bathrooms_llena = 0
    for fila in filas_de(RAW / "listings_2026-09-17.csv.gz"):
        n += 1
        vacias += fila["minimum_nights"] == ""
        bathrooms_llena += fila["bathrooms"] != ""
        de_dentro = dentro_del_limite(float(fila["longitude"]), float(fila["latitude"]), limite)
        dentro += de_dentro
        if fila["room_type"] != "Entire home/apt" or de_dentro or not fila["price"]:
            continue
        precio = float(fila["price"].replace("$", "").replace(",", ""))
        b = banos(fila["bathrooms_text"])
        if not (20 <= precio <= 1000) or b is None or not fila["bedrooms"] or not fila["beds"]:
            continue
        d, camas = float(fila["bedrooms"]), float(fila["beds"])
        ocupacion = int(fila["estimated_occupancy_l365d"])
        estancia = float(fila["minimum_nights"]) if fila["minimum_nights"] else estancia_calendario.get(fila["id"], 10 ** 9)
        if int(fila["accommodates"]) > 8 or b > 5 or d > 5 or camas > 6 or ocupacion <= 0 or estancia > 3:
            continue
        base += 1
        rent[fila["neighbourhood_cleansed"]].append(precio * ocupacion / superficie(d, b))
        # CP-007 a CP-009: cero baños, tipo que no es vivienda entera y más camas o dormitorios que huéspedes.
        base_final += not (b == 0 or not fila["property_type"].startswith("Entire") or camas > int(fila["accommodates"]) or d > int(fila["accommodates"]))

    caso("filas de la foto", n, tablas["listings_2026-09-17"]["filas"])
    caso("filas de la foto, control", n, ref["anuncios_septiembre"])
    campo = next(c for c in tablas["listings_2026-09-17"]["campos"] if c["columna"] == "minimum_nights")
    caso("vacíos de la estancia", vacias, campo["nulos"])
    caso("vacíos de la estancia, control", vacias, ref["estancia_vacia_septiembre"])
    caso("bathrooms entera vacía, control", bathrooms_llena == 0, ref["bathrooms_vacia_septiembre"])
    caso("anuncios dentro del centro, control", dentro, ref["anuncios_dentro_del_centro"])
    caso("base de decisión", base, cal_json["medicion"]["base"]["pisos"])
    caso("base antes de CP-007 a CP-009, control", base, ref["base_antes_de_cp_007_a_009"])
    caso("base de decisión, control", base_final, ref["base_de_decision"])
    caso("recuento de un barrio del grupo", len(rent["Opañel"]), 60)

    # La rentabilidad mediana de un barrio se rehace con el precio del m² que da el reconocimiento aprobado.
    libro = load_workbook(RAW / "externos/E3210626_precio_declarado_2025.xlsx", read_only=True, data_only=True).worksheets[0]
    m2_opanel = next(f[2] for f in libro.iter_rows(values_only=True) if isinstance(f[1], str) and f[1].endswith(". Opañel"))
    opanel = 100 * statistics.median(rent["Opañel"]) / (m2_opanel * 0.75)
    caso("rentabilidad mediana de Opañel, en décimas", round(opanel, 1), RENTABILIDAD_OPANEL)
    control = {c["nombre"]: c for c in cal_json["controles"]}
    for nombre in ("barrios_sin_precio_propio", "barrios_con_otro_nombre", "barrios_del_grupo", "barrios_tras_temporada"):
        caso(f"control {nombre}", control[nombre]["da"], ref[nombre])

    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodos los casos pasan")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
