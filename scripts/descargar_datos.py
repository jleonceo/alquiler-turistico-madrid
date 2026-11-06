"""Descarga una vez los datos de Inside Airbnb, comprueba su huella y quita las columnas personales.

El repositorio no trae estos ficheros: Inside Airbnb pide no volver a publicar sus datos y descargarlos una sola vez, y
traen nombres de anfitriones, enlaces y textos de quien reseña. Este script los deja en data/original/, que git ignora, y
escribe en data/raw/ lo único que usa la cadena. Los ficheros del Ayuntamiento de Madrid ya vienen en data/raw/externos/.

Qué se hace con cada tabla: de las fotos salen 16 columnas y el número de licencia queda reducido a su tipo; de las reseñas
quedan el anuncio y la fecha; el calendario y los límites de barrio no traen datos personales y pasan sin cambios.

Inside Airbnb retira de su portada las fotos antiguas. Si una dirección ya no responde, el script para y lo dice: los
resultados publicados en informes/ se pueden seguir leyendo y las cifras de portada se rehacen con data/publicado/.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/descargar_datos.py
  PYTHONUTF8=1 python -W error scripts/descargar_datos.py --origen carpeta_con_los_ficheros
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 1. Fuentes, huellas y columnas
# ---------------------------------------------------------------------------

CASO = Path(__file__).resolve().parents[1]
ORIGINAL = CASO / "data" / "original"
RAW = CASO / "data" / "raw"
PROTECCION = CASO / "config" / "fuentes" / "proteccion-datos.json"
BASE = "https://data.insideairbnb.com/spain/comunidad-de-madrid/madrid"

# Cada fichero: nombre local, dirección y SHA-256 del fichero que se analizó.
FICHEROS = [
    ("listings_2025-12-14.csv.gz", f"{BASE}/2025-12-14/data/listings.csv.gz", "7044e5eb1b1a646523149fc361b3bad6519d6ced742005871c04ad241a3148cf"),
    ("listings_2026-03-24.csv.gz", f"{BASE}/2026-03-24/data/listings.csv.gz", "a9186447c246c9a567f153878102c46ca0224a6772d1d369cd8186bfabbdf631"),
    ("listings_2026-06-20.csv.gz", f"{BASE}/2026-06-20/data/listings.csv.gz", "18e0f5c631759b6588503b513f21af6045fd883467a39b2d9903bc97d36bd9a9"),
    ("listings_2026-09-17.csv.gz", f"{BASE}/2026-09-17/data/listings.csv.gz", "df7566e731727cd07925e8ad70e17e1f53ec5ac354e9e1ac2ada44c871aa4082"),
    ("calendar_2026-09-17.csv.gz", f"{BASE}/2026-09-17/data/calendar.csv.gz", "a67236bae3044d7f1f87ae0f20901076bf1566cfa3575a8a56b09317459f55cb"),
    ("reviews_2026-09-17.csv.gz", f"{BASE}/2026-09-17/data/reviews.csv.gz", "f276094a009946aad5ba1fdcd560219a80997ad9e472274d70c3af73f20f2d29"),
    ("neighbourhoods.csv", f"{BASE}/2026-09-17/visualisations/neighbourhoods.csv", "3c20e32be7600ce9dbdb3ea7d87f8322fdb8e28a43521250edaf40f486fa7587"),
    ("neighbourhoods.geojson", f"{BASE}/2026-09-17/visualisations/neighbourhoods.geojson", "eba4e3ba50a30adb95ae71b83c1ac0d1ace3e18d06c77db26230bd7195ca8c6d"),
]

COLUMNAS_FUERA = ["listing_url", "picture_url", "name", "description", "neighborhood_overview", "host_id", "host_url", "host_profile_id", "host_profile_url",
                  "host_name", "host_location", "host_about", "host_thumbnail_url", "host_picture_url", "host_neighbourhood", "host_verifications"]
NUMERO_LICENCIA = re.compile(r"ES[A-Z]{2}(TU|NT)")
PATRONES_PROHIBIDOS = {"enlace": r"airbnb\.[a-z]+/|muscache\.com", "licencia": r"ES[A-Z]{2}(?:TU|NT)", "correo": r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}"}


# ---------------------------------------------------------------------------
# 2. Descarga y huella
# ---------------------------------------------------------------------------

def huella(ruta):
    """Calcula el SHA-256 de un fichero, leyéndolo a bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def traer(nombre, direccion, esperada, origen):
    """Deja un fichero en data/original/ y para si su huella no es la del fichero analizado."""
    destino = ORIGINAL / nombre
    if not destino.exists():
        ORIGINAL.mkdir(parents=True, exist_ok=True)
        if origen:
            shutil.copyfile(Path(origen) / nombre, destino)
        else:
            print(f"Descargo {direccion}", flush=True)
            try:
                peticion = urllib.request.Request(direccion, headers={"User-Agent": "alquiler-turistico-madrid"})
                with urllib.request.urlopen(peticion, timeout=120) as r, open(destino, "wb") as f:
                    shutil.copyfileobj(r, f)
            except (urllib.error.URLError, TimeoutError) as e:
                destino.unlink(missing_ok=True)
                raise SystemExit(f"No se pudo descargar {nombre}: {e}. Inside Airbnb retira las fotos antiguas de su portada; se pueden pedir en su web.")
    obtenida = huella(destino)
    if obtenida != esperada:
        raise SystemExit(f"La huella de {nombre} no es la del fichero analizado: {obtenida}. No sigo, porque las cifras no serían comparables.")
    return destino


# ---------------------------------------------------------------------------
# 3. Quitar lo personal
# ---------------------------------------------------------------------------

def clasificar_licencia(texto):
    """Devuelve el tipo de licencia de un anuncio, sin ningún número."""
    if not isinstance(texto, str) or not texto.strip():
        return {"licencia_nacional": None, "licencia_exencion": None, "licencia_vt": False, "licencia_otro": False}
    nacional = NUMERO_LICENCIA.search(texto)
    exento = re.search(r"(?i)exempt[^<]*|exento[^<]*", texto)
    exencion = None
    if exento:
        motivo = exento.group(0).lower()
        if "season" in motivo or "tempor" in motivo:
            exencion = "temporada"
        elif "tourist" in motivo:
            exencion = "apartamento_turistico"
        elif "hostel" in motivo:
            exencion = "hostal"
        elif "hotel" in motivo or "motel" in motivo:
            exencion = "hotel"
        else:
            exencion = "sin_motivo"
    vt = re.search(r"VT[\s\-]*\d|VT\b", texto) is not None
    return {"licencia_nacional": nacional.group(1) if nacional else None, "licencia_exencion": exencion, "licencia_vt": vt, "licencia_otro": not (nacional or exento or vt)}


def limpiar_foto(tabla):
    """Quita las columnas personales de una foto y deja la licencia como tipo."""
    tipos = pd.DataFrame([clasificar_licencia(t) for t in tabla["license"]], index=tabla.index)
    fuera = [c for c in COLUMNAS_FUERA if c in tabla.columns] + ["license"]
    return pd.concat([tabla.drop(columns=fuera), tipos], axis=1)


def fallos_de_foto(tabla):
    """Lista lo que no puede llegar a data/raw/. Vacía si la tabla está bien."""
    fallos = [f"columna {c}" for c in COLUMNAS_FUERA + ["license"] if c in tabla.columns]
    for columna in tabla.columns:
        if tabla[columna].dtype.kind in "biuf":
            continue
        texto = tabla[columna].dropna().astype(str)
        fallos += [f"{nombre} en {columna}" for nombre, patron in PATRONES_PROHIBIDOS.items() if texto.str.contains(patron, regex=True).any()]
    return fallos


def preparar(rutas):
    """Escribe en data/raw/ las tablas sin datos personales."""
    (RAW / "externos").mkdir(parents=True, exist_ok=True)
    for nombre, ruta in rutas.items():
        if nombre.startswith("listings_"):
            crudo = pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[""])
            limpio = limpiar_foto(crudo)
            fallos = fallos_de_foto(limpio)
            if fallos or len(limpio) != len(crudo):
                raise SystemExit(f"PARADO {nombre}: {fallos}")
            limpio.to_csv(RAW / nombre, index=False, compression={"method": "gzip", "mtime": 0})
        elif nombre.startswith("reviews_"):
            crudo = pd.read_csv(ruta, dtype=str, usecols=["listing_id", "date"])
            crudo.to_csv(RAW / nombre.replace("reviews_", "reviews_fechas_"), index=False, compression={"method": "gzip", "mtime": 0})
        elif nombre.startswith("calendar_"):
            shutil.copyfile(ruta, RAW / nombre)
        else:
            shutil.copyfile(ruta, RAW / "externos" / nombre)


def comprobar_salida():
    """Compara lo escrito con las huellas guardadas y devuelve los ficheros que difieren."""
    if not PROTECCION.exists():
        return []
    tablas = json.loads(PROTECCION.read_text(encoding="utf-8"))["tablas"]
    return [t["fichero_salida"] for t in tablas if (CASO / t["fichero_salida"]).exists() and huella(CASO / t["fichero_salida"]) != t["sha256_salida"]]


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--origen", help="carpeta con los ficheros ya descargados, para no volver a pedirlos")
    o = a.parse_args()
    preparar({n: traer(n, d, h, o.origen) for n, d, h in FICHEROS})
    distintos = comprobar_salida()
    if distintos:
        print(f"AVISO: {len(distintos)} ficheros no dan la huella guardada, y puede ser por la versión de pandas: {distintos}", file=sys.stderr)
    print(f"Listo: {len(FICHEROS)} ficheros comprobados y data/raw/ preparado.")
