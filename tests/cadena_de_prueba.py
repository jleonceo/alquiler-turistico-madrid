"""Monta el caso pequeño de datos_de_prueba.py con lo plantado para la preparación y lanza la cadena de scripts.

Este módulo no hace nada al importarse. Lo usan las pruebas de la corrección, el modelo, los cruces y la transformación.

Qué se planta en la foto de septiembre, además de lo que trae datos_de_prueba.py:
- cero baños, medio baño, un precio con coma de miles, un precio vacío y una estancia vacía;
- un piso que no es vivienda y otro con más camas que huéspedes;
- una habitación privada, una compartida y una de hotel, las tres con 200 días libres;
- un anuncio dentro del centro histórico y otro sin camas;
- un anuncio de un anfitrión con 12 anuncios y otro con su cotización a 120 días de la foto.
"""
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))
import datos_de_prueba as dp  # noqa: E402

SCRIPTS = CARPETA.parent / "scripts"
NOMBRES = ["diccionario_datos.py", "calidad_datos.py", "reglas_caso.py", "correccion_datos.py", "modelo_datos.py",
           "integracion_datos.py", "transformacion_datos.py", "decisiones_correccion.json"]
SEP = "listings_2026-09-17.csv.gz"
# Identificadores plantados: el primer barrio de la lista es Ribera y sus filas empiezan en 1001.
ID = {"cero": 1003, "medio": 1004, "miles": 1005, "vacio": 1006, "estancia": 1007, "no_vivienda": 1008, "incoherente": 1009,
      "privada": 1010, "compartida": 1011, "hotel": 1012, "centro": 1013, "camas": 1014, "anfitrion": 1015, "lejana": 1016}


def plantar(caso):
    """Cambia la foto de septiembre del caso pequeño y vuelve a escribir su protección."""
    ruta = caso / "data" / "raw" / SEP
    tipos = {"bathrooms_text": "object", "price": "object", "property_type": "object", "room_type": "object"}
    t = pd.read_csv(ruta, low_memory=False, dtype=tipos).set_index("id")
    t.loc[ID["cero"], "bathrooms_text"] = "0 baths"
    t.loc[ID["medio"], "bathrooms_text"] = "Private half-bath"
    t.loc[ID["miles"], "price"] = "$1,250.00"
    t.loc[ID["vacio"], "price"] = None
    t.loc[ID["estancia"], "minimum_nights"] = None
    t.loc[ID["no_vivienda"], "property_type"] = "Room in hotel"
    t.loc[ID["incoherente"], "beds"] = 5
    t.loc[ID["incoherente"], "accommodates"] = 4
    for clave, tipo in (("privada", "Private room"), ("compartida", "Shared room"), ("hotel", "Hotel room")):
        t.loc[ID[clave], "room_type"] = tipo
        t.loc[ID[clave], "availability_365"] = 200
        t.loc[ID[clave], "price"] = "$50.00"
    t.loc[ID["privada"], "bedrooms"] = 2
    t.loc[ID["compartida"], "accommodates"] = 3
    t.loc[ID["centro"], "longitude"] = -3.72
    t.loc[ID["centro"], "latitude"] = 40.62
    t.loc[ID["camas"], "beds"] = None
    t.loc[ID["anfitrion"], "calculated_host_listings_count"] = 12
    t["price_quote_checkin_date"] = t["price_quote_checkin_date"].astype("object")
    t.loc[ID["lejana"], "price_quote_checkin_date"] = "2027-01-15"
    # La fuente publica ingreso = precio × ocupación: lo plantado tiene que seguir cumpliéndolo.
    numero = pd.to_numeric(t["price"].str.replace(r"[$,]", "", regex=True))
    t["estimated_revenue_l365d"] = numero * t["estimated_occupancy_l365d"]
    t.reset_index().to_csv(ruta, index=False, compression="gzip")
    dp._proteccion(caso)


def documentos(caso):
    """Escribe los documentos vivos que leen los scripts, con el estado que comprueba cada prueba."""
    modelo = caso / "config" / "modelo"
    modelo.mkdir(parents=True, exist_ok=True)
    (modelo / "registro-transformaciones.md").write_text("# Registro\n\n## R-001 · entrega\n<!-- clave: entrega -->\n", encoding="utf-8", newline="\n")
    (modelo / "modelo-datos.md").write_text("# Modelo\n\n## Decisiones de modelado\n\nLa cadena sigue sin esperar.\n", encoding="utf-8")
    (caso / "config" / "negocio").mkdir(parents=True, exist_ok=True)


def lanzar(caso, nombre, *argumentos):
    """Ejecuta un script del caso pequeño con -W error y devuelve el proceso."""
    return subprocess.run([sys.executable, "-W", "error", str(caso / "scripts" / nombre), *argumentos], capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONUTF8": "1", "TROZO_FILAS": "50"})


def montar(destino, hasta):
    """Crea el caso pequeño y lanza los scripts en orden hasta el indicado; devuelve el caso y el último proceso."""
    faltan = [n for n in NOMBRES if not (SCRIPTS / n).exists()]
    if faltan:
        raise FileNotFoundError(", ".join(faltan))
    caso = dp.crear_caso(Path(destino) / "caso", [SCRIPTS / n for n in NOMBRES])
    plantar(caso)
    documentos(caso)
    # El grupo del caso pequeño no es el de Madrid: la prueba que quiera un control lo escribe aparte.
    ruta = caso / "scripts" / "decisiones_correccion.json"
    dec = json.loads(ruta.read_text(encoding="utf-8"))
    dec["controles"] = {"grupo_esperado": None, "firmes_esperados": None, "base_comparacion_esperada": None}
    ruta.write_text(json.dumps(dec, ensure_ascii=False), encoding="utf-8")
    ultimo = None
    for nombre in NOMBRES[:-1]:
        if nombre == "reglas_caso.py":
            continue
        ultimo = lanzar(caso, nombre)
        if ultimo.returncode != 0:
            print(nombre, ultimo.stdout[-400:], ultimo.stderr[-1500:])
            break
        if nombre == hasta:
            break
    return caso, ultimo


def leer(caso, nombre):
    """Lee un JSON de informes/ del caso pequeño."""
    return json.loads((caso / "informes" / nombre).read_text(encoding="utf-8"))


class Prueba:
    """Apunta los casos de una prueba y dice cuáles fallan."""

    def __init__(self):
        self.fallos = []

    def caso(self, nombre, condicion, detalle=""):
        """Apunta un caso y lo imprime."""
        print(f"{'ok   ' if condicion else 'FALLA'} {nombre} {detalle if not condicion else ''}")
        if not condicion:
            self.fallos.append(nombre)

    def fin(self):
        """Imprime el resumen y devuelve el código de salida."""
        print(f"\n{len(self.fallos)} casos fallan" if self.fallos else "\ntodos los casos pasan")
        return 1 if self.fallos else 0


def huellas(caso):
    """Da la huella de cada fichero de data/raw/ del caso pequeño."""
    return {p.name: dp.huella(p) for p in (caso / "data" / "raw").rglob("*") if p.is_file()}


def gz_lineas(ruta):
    """Cuenta las filas de datos de un CSV comprimido."""
    with gzip.open(ruta, "rt", encoding="utf-8") as f:
        return sum(1 for _ in f) - 1
