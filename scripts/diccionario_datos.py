"""Diccionario de datos del origen del caso.

Lee cada tabla de data/raw/ tal como llega, perfila todas sus columnas sobre el fichero completo y escribe
config/fuentes/diccionario-datos-origen.json y, a partir de él, el .md para la persona.

No corrige, no renombra y no cruza tablas. No escribe nada en data/.
Lee config/fuentes/proteccion-datos.json, que deja la entrega de los datos, fuera de este caso.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/diccionario_datos.py
"""
import codecs
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import platform
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import shapely
from openpyxl import load_workbook
from shapely.geometry import shape

# ---------------------------------------------------------------------------
# 1. Configuración del caso
# ---------------------------------------------------------------------------

# 1.1 Rutas: salen del propio script, para que funcione lo lance quien lo lance.
CASO = Path(__file__).resolve().parents[1]
RAW = CASO / "data" / "raw"
EXT = RAW / "externos"
FUENTES = CASO / "config" / "fuentes"
SALIDA_JSON = FUENTES / "diccionario-datos-origen.json"
SALIDA_MD = FUENTES / "diccionario-datos-origen.md"
PROTECCION = FUENTES / "proteccion-datos.json"

FECHA_DATOS = "2026-09-17"  # reglas §5: fecha de referencia, la de la foto principal
VERSION_SKILL = "1.0"
SKILL = "diccionario-datos"
SCRIPT = "scripts/diccionario_datos.py"

# 1.2 Parámetros. El tamaño del trozo se puede bajar en las pruebas.
CODIFICACIONES = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
FILAS_CABECERA_EXCEL = 20
MAX_VALORES_TEXTO = 15
RARA_PCT = 2.5
RARA_MIN = 5
SEGMENTO_MIN = 30
TROZO = int(os.environ.get("TROZO_FILAS", 1_000_000))
PARAMETROS = [
    {"nombre": "orden de codificaciones", "valor": ", ".join(CODIFICACIONES), "origen": "por defecto"},
    {"nombre": "filas donde buscar la cabecera de un Excel", "valor": FILAS_CABECERA_EXCEL, "origen": "por defecto"},
    {"nombre": "lista completa de valores de un texto", "valor": MAX_VALORES_TEXTO, "origen": "por defecto"},
    {"nombre": "categoría rara, porcentaje de filas", "valor": RARA_PCT, "origen": "por defecto"},
    {"nombre": "categoría rara, apariciones", "valor": RARA_MIN, "origen": "por defecto"},
    {"nombre": "apertura de bases de datos", "valor": "no hay bases de datos en el caso", "origen": "por defecto"},
    {"nombre": "ficheros de un ZIP que no se abren", "valor": "no hay ZIP en el caso", "origen": "por defecto"},
    {"nombre": "segmento mínimo para nulos concentrados", "valor": SEGMENTO_MIN, "origen": "calidad-datos, por defecto"},
]

# 1.3 Tablas que se perfilan, con lo que es una fila y su clave. La clave sale de reglas §5 o del reconocimiento.
FOTOS = ["2025-12-14", "2026-03-24", "2026-06-20", "2026-09-17"]
TABLAS_CSV = [
    *[{"tabla": f"listings_{f}", "ruta": f"listings_{f}.csv.gz", "clave": ["id"], "dims": ["neighbourhood_group_cleansed", "room_type"],
       "fila": "un anuncio en esa foto (reglas §5)"} for f in FOTOS],
    {"tabla": "calendar_2026-09-17", "ruta": "calendar_2026-09-17.csv.gz", "clave": ["listing_id", "date"], "dims": ["mes"],
     "fila": "un anuncio y un día (reglas §5)"},
    {"tabla": "reviews_fechas_2026-09-17", "ruta": "reviews_fechas_2026-09-17.csv.gz", "clave": ["listing_id", "date"], "dims": [],
     "fila": "una reseña; anuncio y fecha pueden repetirse (reglas §5)"},
    {"tabla": "licencias_vut_por_barrio", "ruta": "externos/licencias_vut_por_barrio.csv", "clave": [], "dims": ["distrito"],
     "fila": "una licencia, sin su número (proteccion-datos.md)"},
    {"tabla": "neighbourhoods", "ruta": "externos/neighbourhoods.csv", "clave": ["neighbourhood"], "dims": [],
     "fila": "un barrio de Inside Airbnb (reglas §4)"},
]
# Cada libro: las cabeceras de sus columnas de valor, en orden, tal como vienen en las filas 5 y 6.
LIBROS = {
    "E3210126_transacciones_tipo_2025": "viviendas transmitidas en 2025",
    "E3210226_transacciones_superficie_2025": "viviendas transmitidas en 2025, por tramo de superficie",
    "E3210326_superficie_media_2025": "metros cuadrados medios de las viviendas transmitidas en 2025",
    "E3210626_precio_declarado_2025": "euros por metro cuadrado declarados en 2025 y su número índice",
}
GEOMETRIAS = {
    "ape_00_01.json": "límite del centro histórico, ámbito APE 00.01 (reglas §4)",
    "neighbourhoods.geojson": "polígonos de los barrios de Inside Airbnb (reglas §4)",
    "edificios_monumentales.geojson": "puntos de interés: edificios monumentales (reglas §7)",
    "mercados_comercios.geojson": "puntos de interés: mercados y comercios (reglas §7)",
    "museos_salas.geojson": "puntos de interés: museos y salas (reglas §7)",
    "parques_jardines.geojson": "puntos de interés: parques y jardines (reglas §7)",
}
# Marco amplio de Madrid: solo sirve para ver un punto lejísimos, no para decir si está en la ciudad.
MADRID = {"lon": (-3.95, -3.45), "lat": (40.25, 40.65)}

# 1.4 Diccionario de la organización: config/fuentes/normas/vut_doc.pdf, leído entero el 06/11/2026.
DICCIONARIO_ORGANIZACION = "config/fuentes/normas/vut_doc.pdf"
DOCUMENTADAS_LICENCIAS = {"DISTRITO": "distrito", "DIRECCIÓN": None, "PLANTA": "planta", "Nº VUT": "viviendas",
                          "EXPEDIENTE": None, "RESOLUCION": None}

# 1.5 Significado de cada columna. Procedencia: reglas, declarado, medido o sin_confirmar.
# Clave: columna; valor: rol, significado, procedencia y, si procede, cero, dominio y duda.
SC = "sin_confirmar"
SIN_FILA_FOTO = ("el anuncio no estaba publicado en esa foto, o la captura no lo vio: cada fila es un anuncio en esa fecha", "reglas §5")
CERO_SIN_RESENAS = ("no tiene reseñas en ese periodo; number_of_reviews a cero coincide con first_review vacía", "medido")
CERO_SIN_LIBRES = ("sin días libres en ese horizonte; no distingue reservado de bloqueado", "reglas §5")
C = {
    "id": {"rol": "identificador", "s": "número del anuncio; une fotos, calendario y reseñas", "p": "reglas §3"},
    "scrape_id": {"rol": "codigo", "s": "número de la captura de Inside Airbnb", "p": SC},
    "last_scraped": {"rol": "fecha", "s": "día en que se capturó el anuncio", "p": SC},
    "source": {"rol": "categorica", "s": "marca del origen de la captura; «previous scrape» lo trae de una captura anterior", "p": SC, "duda": True},
    "host_since": {"rol": "fecha", "s": "fecha de alta del anfitrión", "p": SC},
    "hosts_time_as_user_years": {"rol": "magnitud", "s": "años del anfitrión como usuario", "p": SC},
    "hosts_time_as_user_months": {"rol": "magnitud", "s": "meses, además de los años, como usuario", "p": SC},
    "hosts_time_as_host_years": {"rol": "magnitud", "s": "años del anfitrión como anfitrión", "p": SC},
    "hosts_time_as_host_months": {"rol": "magnitud", "s": "meses, además de los años, como anfitrión", "p": SC},
    "host_response_time": {"rol": "categorica", "s": "tiempo de respuesta del anfitrión", "p": SC},
    "host_response_rate": {"rol": "magnitud", "s": "tasa de respuesta del anfitrión", "p": SC},
    "host_acceptance_rate": {"rol": "magnitud", "s": "tasa de aceptación del anfitrión", "p": SC},
    "host_is_superhost": {"rol": "booleana", "s": "si el anfitrión tiene la marca de superanfitrión", "p": SC},
    "host_listings_count": {"rol": "magnitud", "s": "anuncios del anfitrión", "p": "proteccion-datos.md", "dominio": (1, None)},
    "host_total_listings_count": {"rol": "magnitud", "s": "anuncios totales del anfitrión", "p": SC},
    "host_has_profile_pic": {"rol": "booleana", "s": "si el anfitrión tiene foto de perfil", "p": SC},
    "host_identity_verified": {"rol": "booleana", "s": "si el anfitrión tiene la identidad verificada", "p": SC},
    "neighbourhood": {"rol": "texto_libre", "s": "barrio escrito por el anfitrión", "p": SC},
    "neighbourhood_cleansed": {"rol": "categorica", "s": "barrio de Inside Airbnb", "p": "reglas §4"},
    "neighbourhood_group_cleansed": {"rol": "categorica", "s": "distrito de Inside Airbnb", "p": "reglas §4"},
    "latitude": {"rol": "magnitud", "s": "latitud, desplazada hasta 150 m por la fuente", "p": "reglas §4", "dominio": (40.25, 40.65)},
    "longitude": {"rol": "magnitud", "s": "longitud, desplazada hasta 150 m por la fuente", "p": "reglas §4", "dominio": (-3.95, -3.45)},
    "property_type": {"rol": "categorica", "s": "tipo de inmueble", "p": "02_datos_necesarios.md §7"},
    "room_type": {"rol": "categorica", "s": "tipo de alquiler: piso o habitación", "p": "reglas §3"},
    "accommodates": {"rol": "magnitud", "s": "huéspedes que admite", "p": "reglas §7", "dominio": (1, None)},
    "bathrooms": {"rol": "magnitud", "s": "baños en número; vacío en septiembre, por eso se leen del texto", "p": "reglas §5"},
    "bathrooms_text": {"rol": "texto_libre", "s": "baños en texto; «medio baño» vale 0,5", "p": "reglas §5"},
    "bedrooms": {"rol": "magnitud", "s": "habitaciones", "p": "reglas §6", "dominio": (0, None)},
    "beds": {"rol": "magnitud", "s": "camas", "p": "reglas §7", "dominio": (0, None)},
    "amenities": {"rol": "texto_libre", "s": "lista de equipamiento en JSON", "p": "proteccion-datos.md"},
    "price": {"rol": "magnitud", "s": "precio por noche publicado, en euros y con símbolo $ como texto; desde 2026 es una cotización para unas fechas", "p": "reglas §6"},
    "price_quote_checkin_date": {"rol": "fecha", "s": "entrada de la cotización", "p": SC},
    "price_quote_checkout_date": {"rol": "fecha", "s": "salida de la cotización", "p": SC},
    "price_quote_total_price": {"rol": "magnitud", "s": "importe total de la cotización", "p": SC},
    "price_quote_price_per_night": {"rol": "magnitud", "s": "importe por noche de la cotización", "p": SC},
    "price_quote_raw": {"rol": "texto_libre", "s": "cotización completa en JSON", "p": SC},
    "minimum_nights": {"rol": "magnitud", "s": "estancia mínima publicada, en noches", "p": "reglas §5", "dominio": (1, None)},
    "maximum_nights": {"rol": "magnitud", "s": "estancia máxima publicada, en noches", "p": SC, "dominio": (1, None)},
    "minimum_minimum_nights": {"rol": "magnitud", "s": "la menor estancia mínima del calendario", "p": SC, "duda": True},
    "maximum_minimum_nights": {"rol": "magnitud", "s": "la mayor estancia mínima del calendario", "p": SC, "duda": True},
    "minimum_maximum_nights": {"rol": "magnitud", "s": "la menor estancia máxima del calendario", "p": SC, "duda": True},
    "maximum_maximum_nights": {"rol": "magnitud", "s": "la mayor estancia máxima del calendario", "p": SC, "duda": True},
    "minimum_nights_avg_ntm": {"rol": "magnitud", "s": "estancia mínima media; el horizonte «ntm» no está documentado", "p": SC, "duda": True},
    "maximum_nights_avg_ntm": {"rol": "magnitud", "s": "estancia máxima media; el horizonte «ntm» no está documentado", "p": SC, "duda": True},
    "calendar_updated": {"rol": "texto_libre", "s": "última actualización del calendario", "p": SC},
    "has_availability": {"rol": "booleana", "s": "marca de disponibilidad de la fuente", "p": "reglas §3"},
    "availability_30": {"rol": "magnitud", "s": "días libres de los próximos 30", "p": SC, "cero": CERO_SIN_LIBRES, "dominio": (0, 30)},
    "availability_60": {"rol": "magnitud", "s": "días libres de los próximos 60", "p": SC, "cero": CERO_SIN_LIBRES, "dominio": (0, 60)},
    "availability_90": {"rol": "magnitud", "s": "días libres de los próximos 90", "p": SC, "cero": CERO_SIN_LIBRES, "dominio": (0, 90)},
    "availability_365": {"rol": "magnitud", "s": "días libres de los próximos 365", "p": "reglas §7", "cero": CERO_SIN_LIBRES, "dominio": (0, 365)},
    "calendar_last_scraped": {"rol": "fecha", "s": "día de captura del calendario", "p": SC},
    "number_of_reviews": {"rol": "magnitud", "s": "reseñas del anuncio", "p": "reglas §5", "cero": CERO_SIN_RESENAS},
    "number_of_reviews_ltm": {"rol": "magnitud", "s": "reseñas del último año", "p": "reglas §6", "cero": CERO_SIN_RESENAS},
    "number_of_reviews_l30d": {"rol": "magnitud", "s": "reseñas de los últimos 30 días", "p": SC, "cero": CERO_SIN_RESENAS},
    "availability_eoy": {"rol": "magnitud", "s": "días libres hasta fin de año", "p": SC, "cero": CERO_SIN_LIBRES, "duda": True},
    "number_of_reviews_ly": {"rol": "magnitud", "s": "reseñas del año anterior; el periodo no está documentado", "p": SC, "cero": CERO_SIN_RESENAS, "duda": True},
    "estimated_occupancy_l365d": {"rol": "magnitud", "s": "ocupación: estimación de días al año de la fuente, con tope de 255", "p": "reglas §6",
                                  "cero": ("no hay reseñas en el último año; no quiere decir que el piso esté vacío", "reglas §5"), "dominio": (0, 255)},
    "estimated_revenue_l365d": {"rol": "magnitud", "s": "ingreso anual que publica la fuente: precio por noche × ocupación", "p": "reglas §6",
                                "cero": ("ocupación a cero: es precio × ocupación", "reglas §6")},
    "first_review": {"rol": "fecha", "s": "fecha de la primera reseña", "p": SC},
    "last_review": {"rol": "fecha", "s": "fecha de la última reseña", "p": SC},
    "review_scores_rating": {"rol": "magnitud", "s": "puntuación media de las reseñas", "p": SC, "dominio": (0, 5)},
    "review_scores_accuracy": {"rol": "magnitud", "s": "puntuación de exactitud", "p": SC, "dominio": (0, 5)},
    "review_scores_cleanliness": {"rol": "magnitud", "s": "puntuación de limpieza", "p": SC, "dominio": (0, 5)},
    "review_scores_checkin": {"rol": "magnitud", "s": "puntuación de la entrada", "p": SC, "dominio": (0, 5)},
    "review_scores_communication": {"rol": "magnitud", "s": "puntuación de la comunicación", "p": SC, "dominio": (0, 5)},
    "review_scores_location": {"rol": "magnitud", "s": "puntuación de la ubicación", "p": SC, "dominio": (0, 5)},
    "review_scores_value": {"rol": "magnitud", "s": "puntuación de calidad y precio", "p": SC, "dominio": (0, 5)},
    "instant_bookable": {"rol": "booleana", "s": "si se reserva sin esperar confirmación", "p": SC},
    "calculated_host_listings_count": {"rol": "magnitud", "s": "anuncios del anfitrión en esta foto", "p": "proteccion-datos.md"},
    "calculated_host_listings_count_entire_homes": {"rol": "magnitud", "s": "de ellos, pisos", "p": SC},
    "calculated_host_listings_count_private_rooms": {"rol": "magnitud", "s": "de ellos, habitaciones privadas", "p": SC},
    "calculated_host_listings_count_shared_rooms": {"rol": "magnitud", "s": "de ellos, habitaciones compartidas", "p": SC},
    "reviews_per_month": {"rol": "magnitud", "s": "reseñas al mes", "p": SC},
    "licencia_nacional": {"rol": "categorica", "s": "tipo del número de registro; solo su tipo, como descripción", "p": "reglas §3"},
    "licencia_exencion": {"rol": "categorica", "s": "motivo de exención que declara el anuncio; una de sus lecturas es alquiler de temporada", "p": "reglas §7"},
    "licencia_vt": {"rol": "booleana", "s": "si el anuncio publica un número de otro registro; sin número", "p": "proteccion-datos.md"},
    "licencia_otro": {"rol": "booleana", "s": "si publica otro texto de licencia; sin número", "p": "proteccion-datos.md"},
    # Calendario
    "listing_id": {"rol": "clave", "s": "número del anuncio", "p": "reglas §3"},
    "date": {"rol": "fecha", "s": "día del calendario, o día de la reseña", "p": "reglas §5"},
    "available": {"rol": "booleana", "s": "si el día está libre; no distingue reservado de bloqueado", "p": "reglas §5"},
    # Licencias
    "distrito": {"rol": "categorica", "s": "distrito municipal del local", "p": "declarado"},
    "barrio": {"rol": "categorica", "s": "barrio, calculado con el punto antes de quitarlo", "p": "proteccion-datos.md"},
    "planta": {"rol": "categorica", "s": "planta del edificio de la actividad", "p": "declarado"},
    "viviendas": {"rol": "magnitud", "s": "viviendas de uso turístico de la licencia (Nº VUT)", "p": "declarado", "dominio": (1, None)},
    # Barrios
    "neighbourhood_group": {"rol": "categorica", "s": "distrito de Inside Airbnb", "p": "reglas §4"},
}
# En el calendario y en las reseñas, tres columnas significan otra cosa o tienen otro cero.
C_CALENDARIO = {"minimum_nights": {"rol": "magnitud", "s": "estancia mínima que pide ese día", "p": "reglas §5", "dominio": (1, None)},
                "maximum_nights": {"rol": "magnitud", "s": "estancia máxima que pide ese día", "p": SC, "dominio": (1, None)}}

# Lecturas posibles de cada motivo de decisión de negocio, para los pendientes.
LECTURAS = {
    "cero": ["el cero es un dato de la columna", "el cero significa que no consta"],
    "fila": ["la fila que falta significa cero", "la fila que falta significa que no consta"],
    "dominio": ["los valores fuera de dominio son errores", "son casos reales y extremos"],
    "variantes": ["las variantes son el mismo valor", "son valores distintos"],
    "raras": ["las categorías raras se quedan", "se juntan en la preparación"],
    "concentrados": ["el vacío responde a una regla de la fuente", "el vacío es un hueco casual"],
}

CODIGO_OPERACION = re.compile(r"ignora lo anterior|recalcula|ignore (?:all )?previous", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 2. Funciones de lectura
# ---------------------------------------------------------------------------

def huella(ruta):
    """Devuelve el SHA-256 de un fichero, leyéndolo a bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def abrir_binario(ruta):
    """Abre un fichero en binario, comprimido o no."""
    return gzip.open(ruta, "rb") if str(ruta).endswith(".gz") else open(ruta, "rb")


def detectar_codificacion(ruta):
    """Prueba las codificaciones en orden, sobre el fichero entero y sin reemplazar nada."""
    with abrir_binario(ruta) as f:
        if f.read(3) == codecs.BOM_UTF8:
            return "utf-8-sig", ["el fichero empieza por la marca BOM"]
    for cod in CODIFICACIONES:
        decodificador = codecs.getincrementaldecoder(cod)()
        try:
            with abrir_binario(ruta) as f:
                for bloque in iter(lambda: f.read(1 << 20), b""):
                    decodificador.decode(bloque)
                decodificador.decode(b"", final=True)
        except UnicodeDecodeError:
            continue
        return cod, ([] if cod == "utf-8" else [f"hubo que salir de utf-8: {cod}"])
    raise ValueError(f"ninguna codificación lee {ruta}")


def detectar_separador(ruta, codificacion):
    """Mira la cabecera y elige el separador que más columnas da."""
    with abrir_binario(ruta) as f:
        cabecera = f.readline().decode(codificacion)
    return max([",", ";", "\t", "|"], key=cabecera.count)


def normalizar(texto):
    """Quita tildes, mayúsculas y espacios de sobra, solo para comparar."""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


# ---------------------------------------------------------------------------
# 3. Acumulador por columna
# ---------------------------------------------------------------------------
# Cada columna guarda sus frecuencias: con ellas salen distintos, mínimo, máximo y lista, y sirven igual para una tabla
# entera o leída por trozos.

class Columna:
    """Acumula lo que hace falta para perfilar una columna leyendo por trozos."""

    def __init__(self, nombre):
        self.nombre = nombre
        self.nulos = 0
        self.vacios = 0
        self.espacios = 0
        self.frecuencias = Counter()
        self.tipos = set()
        self.no_numericos = Counter()

    def sumar(self, serie):
        """Suma un trozo de la columna."""
        self.tipos.add(str(serie.dtype))
        self.nulos += int(serie.isna().sum())
        presentes = serie.dropna()
        if pd.api.types.is_string_dtype(presentes.dtype) or presentes.dtype == object:
            texto = presentes.astype("str")
            self.vacios += int(texto.str.strip().eq("").sum())
            self.espacios += int(texto.ne(texto.str.strip()).sum())
        for valor, veces in presentes.value_counts(sort=False).items():
            self.frecuencias[valor.item() if hasattr(valor, "item") else valor] += int(veces)

    def cuantil(self, q):
        """Da el cuantil de una columna numérica a partir de sus frecuencias."""
        total = sum(self.frecuencias.values())
        acumulado = 0
        for valor in sorted(self.frecuencias):
            acumulado += self.frecuencias[valor]
            if acumulado >= q * total:
                return valor
        return None


def leer_csv(definicion):
    """Lee una tabla CSV entera por trozos y devuelve sus columnas, sus cuentas por segmento y lo decidido al leer."""
    ruta = RAW / definicion["ruta"]
    codificacion, avisos = detectar_codificacion(ruta)
    separador = detectar_separador(ruta, codificacion)
    columnas, filas = {}, 0
    segmentos = defaultdict(lambda: defaultdict(Counter))
    instrucciones = []
    # La clave se comprueba con un conjunto: sus valores repetidos pueden caer en trozos distintos.
    claves_vistas = set() if len(definicion["clave"]) == 1 else None
    repetidas = 0
    pares = Counter()
    lector = pd.read_csv(ruta, sep=separador, encoding=codificacion, chunksize=TROZO, low_memory=False, keep_default_na=True)
    for trozo in lector:
        if not columnas:
            columnas = {c: Columna(c) for c in trozo.columns}
        for nombre, col in columnas.items():
            col.sumar(trozo[nombre])
        if "date" in trozo.columns and "mes" in definicion["dims"]:
            trozo = trozo.assign(mes=trozo["date"].astype("str").str[:7])
        for dim in definicion["dims"]:
            for nombre in columnas:
                if trozo[nombre].isna().any():
                    grupo = trozo.groupby(dim, dropna=False)[nombre]
                    for seg, n, nulos in zip(grupo.size().index, grupo.size(), grupo.size() - grupo.count()):
                        segmentos[dim][nombre]["|" + str(seg)] += int(nulos)
                        segmentos[dim][nombre]["#" + str(seg)] += int(n)
        if len(definicion["clave"]) == 1:
            valores = trozo[definicion["clave"][0]]
            repetidas += int(len(valores) - valores.nunique())
            repetidas += int(valores.drop_duplicates().isin(claves_vistas).sum())
            claves_vistas.update(valores.tolist())
        elif definicion["clave"]:
            for par, veces in trozo.groupby(definicion["clave"]).size().items():
                pares[par] += int(veces)
        for nombre, col in columnas.items():
            if C.get(nombre, {}).get("rol") in ("texto_libre", "categorica") and not pd.api.types.is_numeric_dtype(trozo[nombre]):
                marca = trozo[nombre].astype("str").str.contains(CODIGO_OPERACION, regex=True)
                instrucciones += [{"columna": nombre, "fila": int(i)} for i in trozo.index[marca]]
        filas += len(trozo)
    if pares:
        repetidas = sum(v - 1 for v in pares.values())
    lectura = {"codificacion": codificacion, "separador": separador, "decimal": ".", "hoja": None, "fila_cabecera": 0,
               "avisos": avisos, "trozos_de": TROZO}
    return columnas, filas, segmentos, lectura, repetidas, instrucciones


def leer_libro(nombre):
    """Lee la tabla de distritos y barrios de un libro E32, con su cabecera de dos filas, sin corregir ningún valor."""
    ruta = EXT / f"{nombre}.xlsx"
    libro = load_workbook(ruta, data_only=True)
    hoja = libro.worksheets[0]
    filas = list(hoja.iter_rows(min_row=1, max_row=hoja.max_row, values_only=True))
    fila_cab = next((i for i, f in enumerate(filas[:FILAS_CABECERA_EXCEL]) if isinstance(f[1], str) and f[1].startswith("Distrito")), None)
    fila_sub = fila_cab + 1
    posicion, arriba = [], None
    # La cabecera combina dos filas: la de arriba, a veces celda combinada, y la de debajo.
    for j in range(1, len(filas[fila_cab])):
        a, b = filas[fila_cab][j], filas[fila_sub][j]
        arriba = a if a is not None else arriba
        if b is not None:
            posicion.append((j, f"{arriba} · {b}" if arriba and arriba != b and not arriba.startswith("Distrito") else str(b)))
        elif a is not None:
            posicion.append((j, str(a)))
    # Una columna sin datos en ninguna fila de barrio no es una columna: el libro deja huecos de separación.
    datos = [f for f in filas[fila_sub + 1:] if isinstance(f[1], str) and re.match(r"^\d{2,3}\. ", f[1])]
    posicion = [(j, n) for j, n in posicion if any(f[j] is not None for f in datos)]
    nombres = [n for _, n in posicion]
    vistos = Counter()
    unicos = []
    for n in nombres:
        vistos[n] += 1
        unicos.append(n if vistos[n] == 1 else f"{n} ({vistos[n]})")
    tabla = pd.DataFrame([[f[j] for j, _ in posicion] for f in datos], columns=unicos)
    notas = [str(f[1]) for f in filas if isinstance(f[1], str) and f[1].startswith(("(1)", "(2)", "FUENTE"))]
    total_ciudad = sum(1 for f in filas if f[1] == "Ciudad de Madrid")
    lectura = {"codificacion": None, "separador": None, "decimal": None, "hoja": hoja.title, "hojas": libro.sheetnames,
               "fila_cabecera": fila_cab + 1, "posiciones": [[j, n] for (j, _), n in zip(posicion, unicos)], "avisos": [
                   f"la hoja {hoja.title} es la única del libro y por eso se usa",
                   f"cabecera en dos filas, {fila_cab + 1} y {fila_sub + 1}, con {len(hoja.merged_cells.ranges)} celdas combinadas",
                   f"{total_ciudad} fila de total de la ciudad fuera de la tabla; se leen solo las que empiezan por código",
                   "la columna Distrito lleva código y nombre juntos: 2 cifras distrito, 3 cifras barrio",
                   f"{len(notas)} notas al pie, sin mezclar con los datos"]}
    libro.close()
    return tabla, lectura, notas


# ---------------------------------------------------------------------------
# 4. Geometrías: solo qué son, cuántos elementos traen y si son válidas
# ---------------------------------------------------------------------------

def describir_geometria(nombre, descripcion):
    """Cuenta los elementos de un GeoJSON o del JSON del límite y comprueba su geometría."""
    datos = json.loads((EXT / nombre).read_text(encoding="utf-8"))
    if "features" in datos and "geometryType" in datos:
        geometrias = [shapely.Polygon(a[0], a[1:]) for a in (f["geometry"]["rings"] for f in datos["features"])]
        tipo = datos["geometryType"]
        anillos = sum(len(f["geometry"]["rings"]) for f in datos["features"])
        sistema = datos.get("spatialReference")
    else:
        geometrias = [shape(f["geometry"]) for f in datos["features"]]
        tipo = ", ".join(sorted({f["geometry"]["type"] for f in datos["features"]}))
        anillos = None
        sistema = datos.get("crs")
    invalidas = [i for i, g in enumerate(geometrias) if not shapely.is_valid(g)]
    limites = [g.bounds for g in geometrias]
    fuera = sum(1 for b in limites if not (MADRID["lon"][0] <= b[0] and b[2] <= MADRID["lon"][1]
                                           and MADRID["lat"][0] <= b[1] and b[3] <= MADRID["lat"][1]))
    resultado = {"fichero": f"data/raw/externos/{nombre}", "que_es": descripcion, "formato": tipo, "elementos": len(geometrias),
                 "invalidos": len(invalidas), "fuera_de_madrid": fuera, "anillos": anillos, "sistema_de_coordenadas": sistema,
                 "propiedades": sorted({k for f in datos["features"] for k in (f.get("properties") or {})}) if "geometryType" not in datos else None}
    if "neighbourhood" in (resultado["propiedades"] or []):
        resultado["invalidos_nombres"] = [datos["features"][i]["properties"]["neighbourhood"] for i in invalidas]
    return resultado


# ---------------------------------------------------------------------------
# 5. Ficha de cada columna
# ---------------------------------------------------------------------------

def ficha_de(nombre, tabla):
    """Devuelve la descripción de una columna: el bloque propio de su tabla manda sobre el común."""
    if tabla.startswith("calendar") and nombre in C_CALENDARIO:
        return C_CALENDARIO[nombre]
    return C.get(nombre)


def protegidas(proteccion, fichero):
    """Devuelve las columnas protegidas de un fichero con su técnica, saltándose las de técnica ninguna."""
    tabla = next((t for t in proteccion["tablas"] if t["fichero_salida"] == fichero), None)
    salida = {}
    for campo in (tabla or {}).get("campos", []):
        if campo["tecnica"] == "ninguna":
            continue
        nombres = [campo["columna"]] if not campo["columna_salida"] else [n.strip() for n in campo["columna_salida"].split(",")]
        for n in nombres:
            salida[n] = {"tecnica": campo["tecnica"], "resultado": campo["resultado"], "motivo": campo["motivo"]}
    return salida


def valores_numericos(col):
    """Dice si todos los valores de la columna son números."""
    return bool(col.frecuencias) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in col.frecuencias)


def columna_en_numeros(col):
    """Pasa a número las frecuencias de una magnitud que llega como texto, sin tocar el dato: quita símbolo y comas."""
    numerica = Columna(col.nombre)
    numerica.nulos, numerica.vacios, numerica.espacios, numerica.tipos = col.nulos, col.vacios, col.espacios, col.tipos
    for valor, veces in col.frecuencias.items():
        limpio = re.sub(r"[$,%]", "", str(valor))
        if re.fullmatch(r"-?\d+(\.\d+)?", limpio):
            numerica.frecuencias[float(limpio)] += veces
        else:
            numerica.no_numericos[str(valor)] += veces
    return numerica


def clase_de(campo, col, descripcion, filas, tabla, segmentos):
    """Aplica las reglas de clasificación y devuelve la clase y sus motivos."""
    motivos = []
    if col.nulos == filas:
        return "no_se_puede_saber", ["columna entera vacía"]
    if campo["rol"] == "dato_personal":
        return "resuelto", []
    rol = campo["rol"]
    if rol in ("categorica", "texto_libre", "codigo") and len(col.frecuencias) <= 500:
        normalizados = defaultdict(list)
        for v in col.frecuencias:
            normalizados[normalizar(v)].append(v)
        juntas = sum(1 for lista in normalizados.values() if len(lista) > 1)
        if juntas:
            campo["variantes_que_colapsan"] = juntas
            motivos.append("variantes")
    if rol == "categorica":
        raras = [{"valor": str(v), "frecuencia": n} for v, n in sorted(col.frecuencias.items(), key=lambda x: (x[1], str(x[0])))
                 if n < RARA_MIN or 100 * n / filas < RARA_PCT]
        if raras:
            campo["categorias_raras"] = raras
            motivos.append("raras")
    if rol == "magnitud" and valores_numericos(col):
        dom = (descripcion or {}).get("dominio")
        if dom:
            fuera = sum(n for v, n in col.frecuencias.items() if (dom[0] is not None and v < dom[0]) or (dom[1] is not None and v > dom[1]))
            campo["fuera_de_dominio"] = fuera
            if fuera:
                motivos.append("dominio")
        p99 = col.cuantil(0.99)
        if p99 and p99 > 0 and max(col.frecuencias) > 10 * p99:
            campo["desborda_el_resto"] = {"p99": p99, "maximo": max(col.frecuencias)}
            if "dominio" not in motivos:
                motivos.append("dominio")
        ceros = col.frecuencias.get(0, 0)
        if ceros and campo["significado_cero"] is None:
            motivos.append("cero")
        campo["ceros"] = ceros
    if col.nulos:
        global_pct = 100 * col.nulos / filas
        for dim, por_columna in segmentos.items():
            cuentas = por_columna.get(campo["columna"], {})
            for clave in [k for k in cuentas if k.startswith("|")]:
                n = cuentas["#" + clave[1:]]
                if n >= SEGMENTO_MIN and 100 * cuentas[clave] / n >= 2 * global_pct:
                    campo.setdefault("nulos_concentrados_en", []).append({"dimension": dim, "segmento": clave[1:], "pct": round(100 * cuentas[clave] / n, 2), "filas": n})
        if "nulos_concentrados_en" in campo:
            motivos.append("concentrados")
    return ("decision_de_negocio" if motivos else "resuelto"), motivos


def perfilar(nombre, col, filas, tabla, proteccion, sin_fila, segmentos, cero_libro=None):
    """Monta la ficha de una columna con la estructura de resultado.md."""
    descripcion = ficha_de(nombre, tabla) or cero_libro
    protegida = proteccion.get(nombre)
    rol = "dato_personal" if protegida else (descripcion or {}).get("rol") or "sin_clasificar"
    if rol == "magnitud" and col.frecuencias and not valores_numericos(col):
        col = columna_en_numeros(col)
    numerica = valores_numericos(col)
    minimo = maximo = None
    if rol in ("magnitud", "fecha") and col.frecuencias:
        claves = sorted(col.frecuencias, key=lambda v: (str(type(v)), v))
        minimo, maximo = (min(claves), max(claves)) if numerica or all(isinstance(v, str) for v in claves) else (None, None)
    valores = None
    if rol != "dato_personal" and not numerica and col.frecuencias and len(col.frecuencias) <= MAX_VALORES_TEXTO:
        valores = [{"valor": str(v), "frecuencia": n} for v, n in sorted(col.frecuencias.items(), key=lambda x: (-x[1], str(x[0])))]
    campo = {
        "columna": nombre, "tipo_leido": " | ".join(sorted(col.tipos)), "tipo_declarado": None, "rol": rol,
        "nulos": col.nulos, "nulos_pct": round(100 * col.nulos / filas, 2) if filas else None, "vacios": col.vacios,
        "espacios": col.espacios, "distintos": len(col.frecuencias), "minimo": minimo, "maximo": maximo, "valores": valores,
        "clase": None, "significado": (descripcion or {}).get("s", "sin descripción: columna que no estaba prevista"),
        "procedencia": (descripcion or {}).get("p", SC),
        "proteccion": {"tecnica": protegida["tecnica"], "resultado": protegida["resultado"]} if protegida else None,
        "significado_cero": None, "significado_sin_fila": None, "observaciones": [],
    }
    if protegida:
        campo["significado"] = protegida["motivo"]
        campo["procedencia"] = "proteccion-datos.json"
    if rol == "magnitud":
        cero = (descripcion or {}).get("cero")
        campo["significado_cero"] = {"texto": cero[0], "procedencia": cero[1]} if cero else None
        if not col.frecuencias.get(0):
            campo["significado_cero"] = {"texto": "la columna no trae ceros", "procedencia": "medido"}
        campo["significado_sin_fila"] = {"texto": sin_fila[0], "procedencia": sin_fila[1]}
    campo["clase"], campo["motivos_clase"] = clase_de(campo, col, descripcion, filas, tabla, segmentos)
    if col.no_numericos:
        campo["observaciones"].append("valores que no son número: " + ", ".join(f"{k} ({v})" for k, v in col.no_numericos.most_common(5)))
    if col.vacios:
        campo["observaciones"].append(f"{col.vacios} cadenas vacías")
    if col.espacios:
        campo["observaciones"].append(f"{col.espacios} valores con espacios al principio o al final")
    if (descripcion or {}).get("duda"):
        campo["duda"] = True
    return campo


# ---------------------------------------------------------------------------
# 6. Recorrido de las tablas
# ---------------------------------------------------------------------------

def tabla_csv(definicion, proteccion_datos):
    """Perfila una tabla CSV entera."""
    columnas, filas, segmentos, lectura, repetidas, instrucciones = leer_csv(definicion)
    fichero = f"data/raw/{definicion['ruta']}"
    if definicion["tabla"].startswith("listings"):
        sin_fila = SIN_FILA_FOTO
    elif definicion["tabla"].startswith("calendar"):
        sin_fila = ("no consta ese día para ese anuncio; el reconocimiento no vio huecos", "medido")
    else:
        sin_fila = ("no consta en esta fuente", SC)
    protegidas_tabla = protegidas(proteccion_datos, fichero)
    campos = [perfilar(n, c, filas, definicion["tabla"], protegidas_tabla, sin_fila, segmentos) for n, c in columnas.items()]
    return {
        "tabla": definicion["tabla"], "fichero": fichero, "lectura": lectura, "que_es_una_fila": definicion["fila"],
        "filas": filas, "columnas": len(campos), "clave": definicion["clave"],
        "clave_unica": (repetidas == 0) if definicion["clave"] else None,
        "repetidas_por_clave": repetidas if definicion["clave"] else None, "campos": campos, "instrucciones_en_texto": instrucciones,
    }


def tabla_libro(nombre):
    """Perfila la tabla de distritos y barrios de un libro E32."""
    tabla, lectura, notas = leer_libro(nombre)
    columnas = {c: Columna(c) for c in tabla.columns}
    for c, col in columnas.items():
        col.sumar(tabla[c])
    if any("(2)" in n for n in notas):
        cero = ("el dato por barrio no se muestra si hay menos de 15 casos, según la nota (2) del libro", "declarado")
    else:
        cero = None
    campos = []
    for n, col in columnas.items():
        if n.startswith("Distrito"):
            descripcion = {"rol": "categorica", "s": "código y nombre del distrito (2 cifras) o del barrio (3 cifras)", "p": "medido"}
        else:
            descripcion = {"rol": "magnitud", "s": f"{LIBROS[nombre]}: {n}", "p": "declarado", "cero": cero}
        sin_fila = ("el barrio no consta en el libro de ese año", SC)
        campos.append(perfilar(n, col, len(tabla), nombre, {}, sin_fila, {}, descripcion))
    distinta = tabla.iloc[:, 0].nunique() == len(tabla)
    return {"tabla": nombre, "fichero": f"data/raw/externos/{nombre}.xlsx", "lectura": lectura,
            "que_es_una_fila": "un distrito o un barrio oficial en 2025", "filas": len(tabla), "columnas": len(campos),
            "clave": [tabla.columns[0]], "clave_unica": bool(distinta), "repetidas_por_clave": int(len(tabla) - tabla.iloc[:, 0].nunique()),
            "campos": campos, "notas": notas, "instrucciones_en_texto": []}


def filtros_de_negocio(tablas):
    """Cuenta en la foto principal lo que quita cada filtro de reglas §7 que se mide en una sola tabla."""
    sep = next((t for t in tablas if t["tabla"] == "listings_2026-09-17"), None)
    if sep is None:
        return []
    tabla = pd.read_csv(RAW / "listings_2026-09-17.csv.gz", low_memory=False,
                        usecols=["room_type", "price", "accommodates", "bedrooms", "beds", "bathrooms_text", "estimated_occupancy_l365d"])
    precio = pd.to_numeric(tabla["price"].astype("str").str.replace(r"[$,]", "", regex=True), errors="coerce")
    return [
        {"regla": "Piso: quita las habitaciones (reglas §3 y §7)", "filas_afectadas": int(tabla["room_type"].ne("Entire home/apt").sum())},
        {"regla": "Precio entre 20 y 1.000 €: fuera de rango o vacío (reglas §7)", "filas_afectadas": int((~precio.between(20, 1000)).sum())},
        {"regla": "Hasta 8 huéspedes (reglas §7)", "filas_afectadas": int(tabla["accommodates"].gt(8).sum())},
        {"regla": "Hasta 5 habitaciones (reglas §7)", "filas_afectadas": int(tabla["bedrooms"].gt(5).sum())},
        {"regla": "Hasta 6 camas (reglas §7)", "filas_afectadas": int(tabla["beds"].gt(6).sum())},
        {"regla": "Ocupación mayor que cero (reglas §7)", "filas_afectadas": int(tabla["estimated_occupancy_l365d"].eq(0).sum())},
        {"regla": "Hasta 5 baños, leídos del texto (reglas §5 y §7): se mide en calidad-datos, que lee el texto", "filas_afectadas": None},
        {"regla": "Fuera del centro histórico (reglas §4 y §7): pide cruzar con el límite, se mide en calidad-datos", "filas_afectadas": None},
        {"regla": "Estancia de hasta 3 noches (reglas §5 y §7): pide cruzar con el calendario, se mide en calidad-datos", "filas_afectadas": None},
    ]


def contradicciones(tablas):
    """Compara las licencias con la ficha del conjunto de datos del Ayuntamiento."""
    lic = next((t for t in tablas if t["tabla"] == "licencias_vut_por_barrio"), None)
    if lic is None:
        return []
    presentes = {c["columna"] for c in lic["campos"]}
    salida = []
    for documentada, en_datos in DOCUMENTADAS_LICENCIAS.items():
        if en_datos is None:
            salida.append({"tabla": lic["tabla"], "columna": documentada, "que_dice_el_documento": "columna del fichero",
                           "que_dicen_los_datos": "no llega: se quitó en la protección o no es del fichero entregado"})
        elif en_datos != documentada:
            salida.append({"tabla": lic["tabla"], "columna": documentada, "que_dice_el_documento": f"se llama {documentada}",
                           "que_dicen_los_datos": f"llega como {en_datos}"})
    for columna in presentes - {v for v in DOCUMENTADAS_LICENCIAS.values() if v}:
        salida.append({"tabla": lic["tabla"], "columna": columna, "que_dice_el_documento": "no la documenta",
                       "que_dicen_los_datos": "la añadió la entrega, calculada con el punto antes de quitarlo"})
    viv = next(c for c in lic["campos"] if c["columna"] == "viviendas")
    if "float" in viv["tipo_leido"]:
        salida.append({"tabla": lic["tabla"], "columna": "viviendas", "que_dice_el_documento": "Número",
                       "que_dicen_los_datos": f"se lee como {viv['tipo_leido']}, con {viv['nulos']} vacíos"})
    return salida


def columnas_que_no_llegan(proteccion_datos):
    """Lista lo que la protección quitó: no hay código de carga en el caso que descarte nada más."""
    salida = []
    for tabla in proteccion_datos["tablas"]:
        for campo in tabla["campos"]:
            salida.append({"tabla": tabla["fichero_salida"], "columna": campo["columna"],
                           "motivo": f"{campo['resultado']}: {campo['motivo']}"})
    return salida


def pendientes_de(tablas):
    """Agrupa por columna y motivo las columnas de decisión de negocio, para no repetirlas en cada foto."""
    grupos = defaultdict(list)
    for t in tablas:
        for c in t["campos"]:
            if c["clase"] == "decision_de_negocio":
                grupos[(c["columna"], tuple(c["motivos_clase"]))].append(t["tabla"])
    salida = []
    for i, ((columna, motivos), lista) in enumerate(sorted(grupos.items()), 1):
        opciones = [lectura for m in motivos for lectura in LECTURAS[m]]
        salida.append({"id": f"P-{i:02d}", "tabla": ", ".join(lista), "columna": columna, "motivos": list(motivos),
                       "pregunta": f"¿Cómo se lee {columna}? Motivo: {', '.join(motivos)}", "opciones": opciones})
    return salida


# ---------------------------------------------------------------------------
# 7. Comprobaciones antes de guardar
# ---------------------------------------------------------------------------

def validar(salida):
    """Comprueba el resultado y devuelve la lista de fallos."""
    fallos = []
    for t in salida["tablas"]:
        if len(t["campos"]) != t["columnas"]:
            fallos.append(f"{t['tabla']}: columnas sin ficha")
        for c in t["campos"]:
            if not c["procedencia"]:
                fallos.append(f"{t['tabla']}.{c['columna']}: sin procedencia")
            if c["rol"] == "dato_personal" and (c["valores"] is not None or c["minimo"] is not None or "categorias_raras" in c):
                fallos.append(f"{t['tabla']}.{c['columna']}: dato personal con valores")
            if c["rol"] == "sin_clasificar":
                fallos.append(f"{t['tabla']}.{c['columna']}: columna sin rol")
    return fallos


# ---------------------------------------------------------------------------
# 8. Informe para la persona, generado del JSON
# ---------------------------------------------------------------------------

def formato(v):
    """Escribe un valor para una celda de tabla, sin saltos ni barras."""
    if v is None:
        return ""
    return str(v).replace("|", "/").replace("\n", " ")


def informe(s):
    """Genera el Markdown a partir del diccionario que se guarda en el JSON."""
    r = [f"# Diccionario de datos del origen · caso", "",
         f"Comprobado el {s['fecha_ejecucion'][:10]} sobre los ficheros de `data/raw/`, con Python {s['python']} y pandas {s['pandas']}.", "",
         s["resultado"]["resumen"], "", "## Cabecera", "",
         f"- Fuente: {len(s['entradas'])} ficheros, {sum(e['bytes'] for e in s['entradas'])} bytes.",
         "- Contexto usado: reglas de negocio, briefing, ficha, datos necesarios, protección de datos y la ficha del "
         "Ayuntamiento sobre las licencias (`normas/vut_doc.pdf`).",
         f"- Parámetros: {', '.join(str(p['nombre']) + ' = ' + str(p['valor']) for p in s['parametros'])}.", ""]
    if s["avisos"]:
        r += ["Avisos de esta ejecución:", ""] + [f"- {a}" for a in s["avisos"]] + [""]
    r += ["## Lectura", ""]
    for t in s["tablas"]:
        l = t["lectura"]
        r.append(f"- **{t['tabla']}**: codificación {l['codificacion']}, separador {l['separador']!r}, hoja {l['hoja']}, "
                 f"cabecera en la fila {l['fila_cabecera']}." + (" " + "; ".join(l["avisos"]) + "." if l["avisos"] else ""))
    r += ["", "## Resumen", "", "| Tabla | Filas | Columnas | Clave | Clave única |", "|---|---|---|---|---|"]
    for t in s["tablas"]:
        r.append(f"| {t['tabla']} | {t['filas']} | {t['columnas']} | {', '.join(t['clave']) or 'no tiene'} | {t['clave_unica']} |")
    r += ["", "Geometrías, solo qué son, cuántos elementos traen y si son válidas:", ""]
    for g in s["geometrias"]:
        extra = f" Inválidos: {', '.join(g['invalidos_nombres'])}." if g.get("invalidos_nombres") else ""
        r.append(f"- `{g['fichero']}`: {g['que_es']}; {g['formato']}, {g['elementos']} elementos, {g['invalidos']} inválidos y "
                 f"{g['fuera_de_madrid']} fuera del marco de Madrid.{extra}")
    for t in s["tablas"]:
        r += ["", f"## {t['tabla']}", "", f"Una fila es {t['que_es_una_fila']}. Son {t['filas']} filas.", "",
              "| Columna | Tipo | Rol | Nulos | % | Vacíos | Espacios | Distintos | Mín | Máx | Clase | Significado | Procedencia | Cero | Sin fila |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in t["campos"]:
            cero = (c["significado_cero"] or {}).get("texto") if c["significado_cero"] else ""
            sin = (c["significado_sin_fila"] or {}).get("texto") if c["significado_sin_fila"] else ""
            r.append("| " + " | ".join(formato(x) for x in [
                c["columna"], c["tipo_leido"], c["rol"], c["nulos"], c["nulos_pct"], c["vacios"], c["espacios"], c["distintos"],
                c["minimo"], c["maximo"], c["clase"], c["significado"], c["procedencia"], cero, sin]) + " |")
        listas = [c for c in t["campos"] if c["valores"]]
        if listas:
            r += ["", "Valores de los textos con 15 o menos:", ""]
            for c in listas:
                r.append(f"- `{c['columna']}`: " + ", ".join(f"{v['valor']} ({v['frecuencia']})" for v in c["valores"]))
        if t.get("notas"):
            r += ["", "Notas del libro:", ""] + [f"- {n}" for n in t["notas"]]
    r += ["", "## Contradicciones con el diccionario de la organización", ""]
    r.append(f"Solo hay ficha de la organización para las licencias: `{s['diccionario_organizacion']}`. Inside Airbnb no trae "
             "diccionario en el caso, y los libros oficiales solo traen sus notas al pie.")
    r += [""] + [f"- **{c['columna']}** ({c['tabla']}): {c['que_dice_el_documento']}; {c['que_dicen_los_datos']}." for c in s["contradicciones"]]
    r += ["", "## Columnas que no llegan al análisis", "",
          "El caso no tiene todavía código de carga. Lo único que no llega es lo que quitó la protección:", ""]
    agrupadas = defaultdict(set)
    for c in s["columnas_que_no_llegan"]:
        agrupadas[c["motivo"]].add(c["columna"])
    r += [f"- {', '.join(sorted(v))}: {k}." for k, v in sorted(agrupadas.items())]
    r += ["", "## Filtros de negocio", ""]
    r += [f"- {f['regla']}: {f['filas_afectadas'] if f['filas_afectadas'] is not None else 'sin recuento aquí'}." for f in s["filtros_de_negocio"]]
    r += ["", "## Decisiones de negocio pendientes", "",
          "Salen de las reglas aplicadas columna a columna. Son señales para preguntar y ninguna decide un tratamiento. "
          "Las que afectan al análisis están medidas en la tabla de decisiones de `informes/calidad-datos.md`.", ""]
    r += [f"- **{p['id']} · {p['columna']}** ({p['tabla']}): {', '.join(p['motivos'])}. Lecturas: {'; '.join(p['opciones'])}." for p in s["pendientes"]]
    r += ["", "## Lo que no se puede saber", ""]
    vacias = defaultdict(list)
    for t in s["tablas"]:
        for c in t["campos"]:
            if c["clase"] == "no_se_puede_saber":
                vacias[c["columna"]].append(t["tabla"])
    r += [f"- `{k}`: entera vacía en {', '.join(v)}." for k, v in sorted(vacias.items())]
    dudas = sorted({c["columna"] for t in s["tablas"] for c in t["campos"] if c.get("duda")})
    r += ["", "Significados sin confirmar con nombre opaco, que no se usan como regla: " + ", ".join(f"`{d}`" for d in dudas) + "."]
    r += ["", "## Datos personales", ""] + s["datos_personales_texto"]
    r += ["", "## Límites", "",
          "- El diccionario describe una tabla cada vez; las claves huérfanas o repetidas entre tablas se ven primero en el apartado «Cruces entre tablas» de `calidad-datos` y se controlan al cruzarlas con `integracion-datos`.",
          "- La detección de datos personales mira columnas enteras; un nombre dentro de texto libre no lo caza.",
          "- Las descripciones «sin confirmar» son deducciones y no se usan como regla."]
    return "\n".join(r) + "\n"


def texto_datos_personales(proteccion_datos, tablas):
    """Redacta el apartado de datos personales desde proteccion-datos.json."""
    tecnicas = defaultdict(set)
    for t in proteccion_datos["tablas"]:
        for c in t["campos"]:
            tecnicas[(c["tecnica"], c["resultado"])].add(c["columna"])
    lineas = ["La protección se aplica al recibir los datos, antes de cualquier análisis. "
              f"Es una entrega de datos {proteccion_datos.get('datos', 'sin calificar')} y su resumen dice: "
              f"«{proteccion_datos['resultado']['resumen']}». El detalle está en "
              "`docs/datos.md`. El resultado no es seudonimización: "
              "no hay códigos con clave, de modo que las columnas quitadas no se pueden recuperar.", ""]
    for (tecnica, resultado), columnas in sorted(tecnicas.items()):
        lineas.append(f"- {tecnica}, {resultado}: {', '.join(sorted(columnas))}.")
    usadas = sorted({c["columna"] for t in tablas for c in t["campos"] if c["rol"] == "dato_personal"})
    lineas += ["", f"Este diccionario deja de esas columnas solo tipo, nulos y distintos: {', '.join(usadas) or 'ninguna'}. "
               "Las coordenadas, el número del anuncio y el número de anuncios por anfitrión se quedan, por lo que dice "
               "`proteccion-datos.md`."]
    return lineas


# ---------------------------------------------------------------------------
# 9. Ejecución
# ---------------------------------------------------------------------------

def guardar(salida):
    """Escribe el JSON y, de él, el Markdown."""
    SALIDA_JSON.write_text(json.dumps(salida, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    SALIDA_MD.write_text(informe(salida) if salida["tablas"] else "# Diccionario de datos del origen\n\n" + salida["resultado"]["resumen"] + "\n", encoding="utf-8")


def principal():
    """Hace el diccionario de principio a fin."""
    base = {"skill": SKILL, "version_skill": VERSION_SKILL, "script": SCRIPT, "fecha_datos": FECHA_DATOS,
            "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"), "python": platform.python_version(),
            "pandas": pd.__version__, "parametros": PARAMETROS, "avisos": [], "entradas": [], "tablas": [], "geometrias": [],
            "pendientes": [], "diccionario_organizacion": DICCIONARIO_ORGANIZACION, "contradicciones": [],
            "columnas_que_no_llegan": [], "filtros_de_negocio": [], "datos_personales_texto": []}
    ficheros = sorted(p for p in RAW.rglob("*") if p.is_file())
    huellas = {p.relative_to(CASO).as_posix(): huella(p) for p in ficheros}

    # 9.1 Al empezar: sin protección no se abre ningún dato.
    proteccion = json.loads(PROTECCION.read_text(encoding="utf-8")) if PROTECCION.exists() else None
    if proteccion is None:
        base["avisos"].append("No existe proteccion-datos.json: los datos no pasaron por la protección.")
        proteccion = {"tablas": [], "resultado": {"resumen": "no hubo paso de protección"}}
    elif proteccion["estado"] in ("PARADO", "ERROR"):
        base["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": f"La protección está en estado {proteccion['estado']}: no se abre ningún dato.",
                             "artefactos": [], "siguiente": "repetir la entrega de los datos"}
        guardar(base)
        return 0
    esperadas = {t["fichero_salida"]: t["sha256_salida"] for t in proteccion["tablas"]}
    for ruta, h in huellas.items():
        if ruta in esperadas and esperadas[ruta] != h:
            base["avisos"].append(f"{ruta}: su huella no es la de proteccion-datos.json; el fichero cambió después de protegerlo")
        if ruta not in esperadas and esperadas:
            base["avisos"].append(f"{ruta}: no está en proteccion-datos.json")

    # 9.2 Tablas y geometrías.
    tablas = [tabla_csv(d, proteccion) for d in TABLAS_CSV]
    tablas += [tabla_libro(n) for n in LIBROS]
    geometrias = [describir_geometria(n, d) for n, d in GEOMETRIAS.items()]
    filas_por_ruta = {t["fichero"]: t for t in tablas}
    base["entradas"] = [{"ruta": r, "sha256": h, "bytes": (CASO / r).stat().st_size,
                         "filas": filas_por_ruta[r]["filas"] if r in filas_por_ruta else None,
                         "columnas": filas_por_ruta[r]["columnas"] if r in filas_por_ruta else None} for r, h in huellas.items()]
    base.update(tablas=tablas, geometrias=geometrias, contradicciones=contradicciones(tablas),
                columnas_que_no_llegan=columnas_que_no_llegan(proteccion), filtros_de_negocio=filtros_de_negocio(tablas),
                pendientes=pendientes_de(tablas), datos_personales_texto=texto_datos_personales(proteccion, tablas))

    # 9.3 Se valida antes de guardar y se comprueba que los datos no se han tocado.
    fallos = validar(base)
    despues = {p.relative_to(CASO).as_posix(): huella(p) for p in sorted(q for q in RAW.rglob("*") if q.is_file())}
    if despues != huellas:
        fallos.append("data/raw/ ha cambiado durante la ejecución")
    n_decision = sum(1 for t in tablas for c in t["campos"] if c["clase"] == "decision_de_negocio")
    n_campos = sum(len(t["campos"]) for t in tablas)
    estado = "ERROR" if fallos else ("AVISO" if base["pendientes"] or base["avisos"] else "OK")
    base["resultado"] = {
        "estado": estado, "riesgo": "alto" if fallos else "medio",
        "resumen": (f"{len(tablas)} tablas y {n_campos} columnas descritas sobre los ficheros completos, con {len(geometrias)} geometrías. "
                    f"{n_decision} fichas de columna llevan una señal de decisión de negocio, agrupadas en {len(base['pendientes'])} pendientes."
                    + (" Fallos: " + "; ".join(fallos) if fallos else "")),
        "artefactos": ["config/fuentes/diccionario-datos-origen.json", "config/fuentes/diccionario-datos-origen.md"],
        "siguiente": "calidad-datos"}
    guardar(base)
    print(base["resultado"]["estado"], base["resultado"]["resumen"])
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(principal())
