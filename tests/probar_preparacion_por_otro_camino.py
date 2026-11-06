"""Rehace por otro camino las cifras de la base, sin pandas ni los scripts del caso, leyendo data/raw/ solo para mirar.

Usa gzip, csv, statistics y math de la biblioteca estándar. Con la misma regla y la misma población que la transformación
rehace: la base de decisión, la base de comparación, las 12 variantes, el grupo y las cinco pruebas. Después compara con
data/processed/analisis_anuncios.parquet, que lee con pyarrow, y con informes/transformacion-datos.json. Los puntos de
interés se rehacen con la fórmula del haversine sobre una muestra fija: la distancia no es la misma que en proyectadas y
por eso se admite una diferencia pequeña. Sale con 0 si todo coincide y con 1 si algo no.

Esta prueba abre los datos reales: su trabajo es esa comprobación. Tarda un minuto largo por el calendario.
"""
import csv
import datetime
import gzip
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
from openpyxl import load_workbook

CASO = Path(__file__).resolve().parents[1]
RAW = CASO / "data" / "raw"
csv.field_size_limit(10_000_000)
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


def plano(texto):
    """Quita tildes, mayúsculas y espacios de sobra."""
    t = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def banos(texto):
    """Lee los baños del texto (reglas §2)."""
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
    """Aplica la superficie de valoraciones (reglas §2)."""
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


def cuantil(valores, q):
    """Cuantil lineal, el mismo método por defecto de pandas."""
    v = sorted(valores)
    k = (len(v) - 1) * q
    i = math.floor(k)
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * (k - i)


def precio(texto):
    """Pasa el precio a número."""
    return float(texto.replace("$", "").replace(",", "")) if texto else None


def precios_oficiales(dec):
    """Lee el precio del m² de cada barrio de Airbnb, con el del distrito en los tres que lo toman."""
    libro = load_workbook(RAW / "externos/E3210626_precio_declarado_2025.xlsx", read_only=True, data_only=True).worksheets[0]
    barrio, distrito = {}, {}
    for f in libro.iter_rows(values_only=True):
        if isinstance(f[1], str) and re.match(r"^\d{2,3}\. ", f[1]):
            cod, nombre = f[1].split(". ", 1)
            (distrito if len(cod) == 2 else barrio)[plano(nombre).replace(" - ", "-")] = f[2]
    salida = {}
    with open(RAW / "externos/neighbourhoods.csv", encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            nombre = fila["neighbourhood"]
            if nombre in dec["toman_el_precio_de_su_distrito"]:
                salida[nombre] = distrito[plano(fila["neighbourhood_group"]).replace(" - ", "-")]
            else:
                clave = plano(nombre)
                salida[nombre] = barrio[dec["equivalencias_barrio"].get(clave, clave)]
    return salida


def grupo(pisos, m2, quitar, cero=False, por_foto=lambda p, clave: False):
    """Calcula las 12 variantes y devuelve los barrios en más de 6. Con cero, los pisos sin ocupación cuentan."""
    veces = Counter()
    for tope in (3, 6):
        for clave in ("p_mar", "p_jun", "precio"):
            por_barrio = defaultdict(list)
            for p in pisos:
                pr = p[clave]
                if quitar(p) or (p["ocupacion"] <= 0 and not cero) or por_foto(p, clave) or p["estancia"] > tope or pr is None or not 20 <= pr <= 1000:
                    continue
                por_barrio[p["barrio"]].append(100 * pr * p["ocupacion"] / (p["sup"] * m2[p["barrio"]] * 0.75))
            medianas = {b: (len(v), statistics.median(v)) for b, v in por_barrio.items()}
            for minimo in (30, 20):
                validos = {b: m for b, (n, m) in medianas.items() if n >= minimo}
                corte = cuantil(list(validos.values()), 0.75)
                veces.update(b for b, m in validos.items() if m >= corte)
    return sorted(b for b, n in veces.items() if n >= 7), veces


def dias_hasta(fecha, foto):
    """Días entre la foto y la fecha de la cotización; vacío si no hay cotización."""
    return (datetime.date.fromisoformat(fecha) - datetime.date.fromisoformat(foto)).days if fecha else None


def haversine(lon1, lat1, lon2, lat2):
    """Distancia en metros sobre la esfera."""
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


def principal():
    """Recorre las comprobaciones."""
    dec = json.loads((CASO / "scripts/decisiones_correccion.json").read_text(encoding="utf-8"))
    j = json.loads((CASO / "informes/transformacion-datos.json").read_text(encoding="utf-8"))
    m2 = precios_oficiales(dec)

    # El calendario solo aporta la estancia menor de cada anuncio.
    estancia = {}
    for fila in filas_de(RAW / "calendar_2026-09-17.csv.gz"):
        if fila["minimum_nights"]:
            v = int(fila["minimum_nights"])
            estancia[fila["listing_id"]] = min(v, estancia.get(fila["listing_id"], v))

    fotos = {"p_mar": "2026-03-24", "p_jun": "2026-06-20"}
    otros, dias = {}, {}
    for k, v in fotos.items():
        filas = list(filas_de(RAW / f"listings_{v}.csv.gz"))
        otros[k] = {f["id"]: precio(f["price"]) for f in filas}
        dias[k] = {f["id"]: dias_hasta(f["price_quote_checkin_date"], v) for f in filas}
    limite = json.loads((RAW / "externos/ape_00_01.json").read_text(encoding="utf-8"))["features"][0]["geometry"]["rings"][0]

    pisos, comparacion, muestra = [], 0, []
    for n, f in enumerate(filas_de(RAW / "listings_2026-09-17.csv.gz")):
        x, y = float(f["longitude"]), float(f["latitude"])
        pr, b = precio(f["price"]), banos(f["bathrooms_text"])
        d = float(f["bedrooms"]) if f["bedrooms"] else None
        camas = float(f["beds"]) if f["beds"] else None
        h = int(f["accommodates"])
        ocupacion = int(f["estimated_occupancy_l365d"])
        if n % 500 == 0:
            muestra.append((f["id"], x, y))
        tamano = b is not None and d is not None and camas is not None and h <= 8 and b <= 5 and d <= 5 and camas <= 6
        if f["room_type"] != "Hotel room" and pr is not None and 20 <= pr <= 1000 and tamano and ocupacion > 0 and int(f["availability_365"]) >= 180:
            comparacion += 1
        if f["room_type"] != "Entire home/apt" or dentro_del_limite(x, y, limite) or not tamano:
            continue
        pisos.append({"id": f["id"], "barrio": f["neighbourhood_cleansed"], "precio": pr, "p_mar": otros["p_mar"].get(f["id"]), "p_jun": otros["p_jun"].get(f["id"]), "ocupacion": ocupacion, "sup": superficie(d, b),
                      "estancia": float(f["minimum_nights"]) if f["minimum_nights"] else float(estancia.get(f["id"], 10 ** 9)), "temporada": f["licencia_exencion"] == "temporada",
                      "anfitrion": int(f["calculated_host_listings_count"]), "dormitorios": d, "dias": {"precio": dias_hasta(f["price_quote_checkin_date"], "2026-09-17"), "p_mar": dias["p_mar"].get(f["id"]), "p_jun": dias["p_jun"].get(f["id"])},
                      "marca": b == 0 or not f["property_type"].startswith("Entire") or (camas > h or d > h)})

    base = [p for p in pisos if not p["marca"] and p["ocupacion"] > 0 and p["estancia"] <= 3 and p["precio"] is not None and 20 <= p["precio"] <= 1000]
    caso("base de decisión", len(base), j["bases"]["decision"])
    caso("base de comparación", comparacion, dec["controles"]["base_comparacion_esperada"])
    g, veces = grupo(pisos, m2, lambda p: p["marca"])
    caso("grupo", g, sorted(dec["controles"]["grupo_esperado"]))
    caso("variantes de cada barrio", {k: v for k, v in sorted(veces.items())}, j["control_grupo"]["variantes_por_barrio"])
    r = dec["pruebas_del_grupo"]
    pruebas = {"sin_temporada": grupo(pisos, m2, lambda p: p["marca"] or p["temporada"])[0],
               "sin_anfitriones_grandes": grupo(pisos, m2, lambda p: p["marca"] or p["anfitrion"] >= r["anfitrion_anuncios"])[0],
               "sin_cotizaciones_lejanas": grupo(pisos, m2, lambda p: p["marca"], por_foto=lambda p, clave: p["dias"][clave] is not None and p["dias"][clave] > r["cotizacion_dias"])[0],
               "solo_1_y_2_dormitorios": grupo(pisos, m2, lambda p: p["marca"] or p["dormitorios"] not in r["dormitorios"])[0],
               "sin_ocupacion_como_cero": grupo(pisos, m2, lambda p: p["marca"], cero=True)[0]}
    aguanta = {b: sum(b in v for v in pruebas.values()) for b in g}
    caso("firmes, desde data/raw", sorted(b for b, n in aguanta.items() if n == 5), sorted(dec["controles"]["firmes_esperados"]))
    caso("con aviso, desde data/raw", sorted(b for b, n in aguanta.items() if n == 4), sorted(dec["controles"]["con_aviso_esperados"]))
    caso("firmes del JSON de la transformación", sorted(j["control_grupo"]["firmes"]), sorted(b for b, n in aguanta.items() if n == 5))
    caso("cada prueba frente al JSON", {b: sorted(x for x, v in pruebas.items() if b in v) for b in g}, {b: sorted(v) for b, v in j["control_grupo"]["pruebas_por_barrio"].items()})

    # La tabla guardada tiene que decir lo mismo, fila a fila en las cuentas de la base.
    t = pq.read_table(CASO / "data/processed/analisis_anuncios.parquet", columns=["id", "base_decision", "base_comparacion", "ingreso_anual_eur", "rent_valoraciones_desc_pct", "puntos_interes_500m", "barrio"]).to_pylist()
    ids = {str(x["id"]) for x in t if x["base_decision"]}
    caso("los mismos pisos en la tabla", ids == {p["id"] for p in base}, True)
    caso("base de comparación en la tabla", sum(x["base_comparacion"] for x in t), comparacion)
    ingreso = round(sum(x["ingreso_anual_eur"] for x in t if x["base_decision"]), 2)
    caso("ingreso de la base", ingreso, round(sum(p["precio"] * p["ocupacion"] for p in base), 2))
    opanel = statistics.median(100 * p["precio"] * p["ocupacion"] / (p["sup"] * m2["Opañel"] * 0.75) for p in base if p["barrio"] == "Opañel")
    caso("rentabilidad mediana de Opañel", round(statistics.median(x["rent_valoraciones_desc_pct"] for x in t if x["base_decision"] and x["barrio"] == "Opañel"), 6), round(opanel, 6))

    # Puntos de interés con haversine sobre la muestra.
    puntos = pq.read_table(CASO / "data/processed/puntos_interes_corregido.parquet", columns=["x", "y"]).to_pylist()
    en_tabla = {str(x["id"]): x["puntos_interes_500m"] for x in t}
    a = sum(en_tabla[i] for i, _, _ in muestra)
    b = sum(1 for _, x, y in muestra for q in puntos if haversine(x, y, q["x"], q["y"]) < 500)
    print(f"puntos de la muestra de {len(muestra)} anuncios: {a} en la tabla y {b} por haversine")
    caso("puntos de interés, diferencia menor del 2 %", abs(a - b) <= 0.02 * max(a, b), True)

    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodos los casos pasan")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
