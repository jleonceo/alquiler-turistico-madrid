"""Calidad de los datos del caso.

Diagnostica las tablas de data/raw/, mide en la base de decisión cada asunto sin criterio y deja
informes/calidad-datos.json y, generado de él, informes/calidad-datos.md. No corrige ningún dato.

Depende de config/fuentes/diccionario-datos-origen.json, que deja scripts/diccionario_datos.py: se lanza
después de él. Si el diccionario falta o describe otra fuente, trabaja igual y lo dice.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/calidad_datos.py
"""
import datetime as dt
import hashlib
import json
import os
import platform
import re
import unicodedata
import zlib
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pyproj
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
DICCIONARIO = FUENTES / "diccionario-datos-origen.json"
PROTECCION = FUENTES / "proteccion-datos.json"
REFERENCIA = CASO / "tests" / "cifras_de_referencia.json"
SALIDA_JSON = CASO / "informes" / "calidad-datos.json"
SALIDA_MD = CASO / "informes" / "calidad-datos.md"

ETAPA = "calidad-datos"
SCRIPT = "scripts/calidad_datos.py"
VERSION_ETAPA = "1.0"
FECHA_DATOS = "2026-09-17"  # reglas §2
TROZO = int(os.environ.get("TROZO_FILAS", 1_000_000))

# 1.2 Parámetros de la medición de calidad.
LIM_IQR = 1.5
LIM_Z = 3.5
SEGMENTO_MIN = 30
CONCENTRACION = 2
COD_PCT = 5
COLAS = 10
EXCEL = (20_000, 60_000)

# 1.3 Parámetros de la medición: los del reconocimiento y los de reglas §3.
SEMILLA = 63
REMUESTREOS = 2000
MIN_GRUPO = 30
MIN_VARIANTE = (30, 20)
ESTANCIAS = (3, 6)
MAYORIA = 7  # más de 6 de las 12 variantes
DESCUENTO = 0.75

# 1.4 Tablas.
FOTOS = {"dic": "2025-12-14", "mar": "2026-03-24", "jun": "2026-06-20", "sep": "2026-09-17"}
TABLA_FOTO = {k: f"listings_{v}" for k, v in FOTOS.items()}
CALENDARIO = "calendar_2026-09-17"
RESENAS = "reviews_fechas_2026-09-17"
LICENCIAS = "licencias_vut_por_barrio"
BARRIOS = "neighbourhoods"
LIBROS = ["E3210126_transacciones_tipo_2025", "E3210226_transacciones_superficie_2025",
          "E3210326_superficie_media_2025", "E3210626_precio_declarado_2025"]
LIBRO_PRECIO, LIBRO_SUP, LIBRO_VENTAS = LIBROS[3], LIBROS[2], LIBROS[0]
PUNTOS = ["edificios_monumentales", "mercados_comercios", "museos_salas", "parques_jardines"]
RUTAS = {**{v: f"{v}.csv.gz" for v in TABLA_FOTO.values()}, CALENDARIO: f"{CALENDARIO}.csv.gz", RESENAS: f"{RESENAS}.csv.gz",
         LICENCIAS: f"externos/{LICENCIAS}.csv", BARRIOS: f"externos/{BARRIOS}.csv"}

# 1.5 Reglas del caso que el código tiene que conocer.
SIN_PROPIO = ["San Andrés", "Ambroz"]  # reglas §2: toman el precio de su distrito
AEROPUERTO = "Aeropuerto"
CASCO_VALLECAS = "Casco Histórico de Vallecas"
EQUIV = {"concepcion": "la concepcion", "carmenes": "los carmenes", "fuentelareina": "fuentelarreina",
         "jeronimos": "los jeronimos", "los angeles": "angeles", "palos de moguer": "palos de la frontera",
         "salvador": "el salvador"}  # las siete del reconocimiento, provisionales
COD_TEXTO = {"none", "null", "n/a", "na", "-", "pendiente", "unknown", "desconocido", "sin dato", "s/d", "nan", "?"}
COD_FECHA = {"0000-00-00", "1900-01-01"}
# Códigos numéricos que ya tienen significado en las reglas o en los libros.
DOCUMENTADOS = {("estimated_occupancy_l365d", 0): "reglas §2", ("estimated_occupancy_l365d", 255): "reglas §2",
                ("availability_365", 0): "reglas §1 y §5"}

PERSONAL = {"correo": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "enlace": re.compile(r"https?://|www\.", re.I),
            "teléfono": re.compile(r"(?<![\d.])[6789]\d{8}(?![\d.])"), "documento": re.compile(r"(?<![\w.])\d{8}[A-HJ-NP-TV-Z](?!\w)"),
            "cuenta": re.compile(r"\bES\d{22}\b")}
ORDEN = re.compile(r"ignora lo anterior|recalcula|ignore (?:all )?previous", re.I)


# ---------------------------------------------------------------------------
# 2. Utilidades
# ---------------------------------------------------------------------------

def huella(ruta):
    """Devuelve el SHA-256 de un fichero, leyéndolo a bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def huellas_de_raw():
    """Calcula la huella de todo data/raw/."""
    return {p.relative_to(CASO).as_posix(): huella(p) for p in sorted(q for q in RAW.rglob("*") if q.is_file())}


def sin_tildes(texto):
    """Normaliza un nombre para compararlo: sin tildes, sin mayúsculas y sin espacios de sobra."""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def sin_guiones(texto):
    """Iguala los distritos escritos con o sin espacios alrededor del guion."""
    return sin_tildes(texto).replace(" - ", "-")


def nombre_normalizado(columna):
    """Calcula el nombre de columna en minúsculas, sin tildes y con guion bajo."""
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes(columna)).strip("_")


def numeros_de(frecuencias):
    """Pasa a número una tabla de frecuencias de texto, sin tocar el dato: quita símbolo, comas y porcentaje."""
    if frecuencias.empty:
        return pd.Series(dtype="float64")
    indice = pd.Series(frecuencias.index.astype("str"), index=frecuencias.index)
    limpio = indice.str.replace(r"[$,%]", "", regex=True)
    valores = pd.to_numeric(limpio, errors="coerce")
    tabla = pd.DataFrame({"v": valores.to_numpy(), "n": frecuencias.to_numpy()}).dropna(subset="v")
    return tabla.groupby("v")["n"].sum().sort_index()


def cuantiles(numeros, qs):
    """Da cuantiles de una tabla de frecuencias, repitiendo cada valor las veces que aparece."""
    return np.quantile(np.repeat(numeros.index.to_numpy(), numeros.to_numpy().astype("int64")), qs)


def banos_de_texto(valor):
    """Lee los baños del texto del anuncio (reglas §2): medio baño vale 0,5 y «No bathroom», 0."""
    if pd.isna(valor):
        return np.nan
    t = str(valor).lower()
    if "half" in t:
        return 0.5
    if "no bathroom" in t:
        return 0.0
    m = re.search(r"\d+(\.\d+)?", t)
    return float(m.group()) if m else np.nan


def p(n, total):
    """Da un porcentaje con dos decimales, o null si el total es cero."""
    return round(100 * n / total, 2) if total else None


# ---------------------------------------------------------------------------
# 3. Lectura
# ---------------------------------------------------------------------------

def leer_csv_entero(tabla):
    """Lee una tabla como la lee el análisis y como llega en bruto, para que un N/A no se confunda con un vacío."""
    ruta = RAW / RUTAS[tabla]
    return pd.read_csv(ruta, low_memory=False), pd.read_csv(ruta, dtype="str", keep_default_na=False)


def frecuencias_de(bruta):
    """Cuenta los valores en bruto de cada columna."""
    return {c: bruta[c].value_counts(sort=False) for c in bruta.columns}


def sumar_frecuencias(acumulado, trozo):
    """Suma al acumulado las frecuencias en bruto de un trozo."""
    for c in trozo.columns:
        acumulado[c].update(trozo[c].value_counts(sort=False).to_dict())


def leer_calendario():
    """Recorre el calendario por trozos y agrega por anuncio sin cargarlo entero."""
    frec, partes, por_mes, vacios_fila = defaultdict(Counter), [], Counter(), Counter()
    lector = pd.read_csv(RAW / RUTAS[CALENDARIO], dtype="str", keep_default_na=False, chunksize=TROZO)
    for trozo in lector:
        sumar_frecuencias(frec, trozo)
        vacios_fila.update(trozo.eq("").sum(axis=1).value_counts().to_dict())
        t = trozo.assign(libre=trozo["available"].eq("t"), noches=pd.to_numeric(trozo["minimum_nights"], errors="coerce"),
                         mes=trozo["date"].str[:7])
        partes.append(t.groupby("listing_id").agg(dias=("date", "size"), libres=("libre", "sum"), est_min=("noches", "min"),
                                                  primera=("date", "min"), ultima=("date", "max")))
        por_mes.update({("filas", m): int(n) for m, n in t.groupby("mes").size().items()})
        for c in ("minimum_nights", "maximum_nights", "available"):
            por_mes.update({(c, m): int(n) for m, n in t.loc[t[c].eq("")].groupby("mes").size().items()})
    cal = pd.concat(partes).groupby(level=0).agg(dias=("dias", "sum"), libres=("libres", "sum"), est_min=("est_min", "min"),
                                                 primera=("primera", "min"), ultima=("ultima", "max"))
    cal.index = cal.index.astype("int64")
    return {c: pd.Series(v, dtype="int64") for c, v in frec.items()}, cal, por_mes, vacios_fila


def leer_resenas():
    """Recorre las reseñas por trozos y agrega por anuncio."""
    frec, partes, repetidas_por_anuncio = defaultdict(Counter), [], Counter()
    for trozo in pd.read_csv(RAW / RUTAS[RESENAS], dtype="str", keep_default_na=False, chunksize=TROZO):
        sumar_frecuencias(frec, trozo)
        partes.append(trozo.groupby("listing_id").agg(resenas=("date", "size"), primera=("date", "min"), ultima=("date", "max"),
                                                      ultimo_ano=("date", lambda s: int(s.gt("2025-09-17").sum()))))
        for par, n in trozo.groupby(["listing_id", "date"]).size().items():
            repetidas_por_anuncio[par] += int(n)
    rev = pd.concat(partes).groupby(level=0).agg(resenas=("resenas", "sum"), primera=("primera", "min"), ultima=("ultima", "max"),
                                                 ultimo_ano=("ultimo_ano", "sum"))
    rev.index = rev.index.astype("int64")
    repetidas = sum(n - 1 for n in repetidas_por_anuncio.values())
    return {c: pd.Series(v, dtype="int64") for c, v in frec.items()}, rev, repetidas


def leer_libro(nombre, posiciones):
    """Lee la tabla de distritos y barrios con las posiciones que dejó el diccionario."""
    hoja = load_workbook(EXT / f"{nombre}.xlsx", data_only=True).worksheets[0]
    filas = [f for f in hoja.iter_rows(values_only=True) if isinstance(f[1], str) and re.match(r"^\d{2,3}\. ", f[1])]
    if not posiciones:
        posiciones = [[j, f"columna_{j}"] for j in range(1, len(filas[0])) if any(f[j] is not None for f in filas)]
    return pd.DataFrame([[f[j] for j, _ in posiciones] for f in filas], columns=[n for _, n in posiciones])


def oficial_de(libros):
    """Separa barrios y distritos oficiales, con el primer valor de cada libro: precio, superficie y ventas."""
    tablas = []
    for nombre, valor in [(LIBRO_PRECIO, "m2_total"), (LIBRO_SUP, "sup_total"), (LIBRO_VENTAS, "ventas")]:
        t = libros[nombre]
        partes = t.iloc[:, 0].str.split(". ", n=1, regex=False)
        tablas.append(pd.DataFrame({"cod": partes.str[0], "nombre": partes.str[1], valor: pd.to_numeric(t.iloc[:, 1])}))
    of = tablas[0].merge(tablas[1][["cod", "sup_total"]], on="cod", validate="one_to_one").merge(tablas[2][["cod", "ventas"]], on="cod", validate="one_to_one")
    of["nivel"] = np.where(of["cod"].str.len() == 2, "distrito", "barrio")
    of["clave"] = of["nombre"].map(sin_tildes)
    return of


def leer_limite():
    """Lee el polígono del centro histórico, con todos sus anillos."""
    datos = json.loads((EXT / "ape_00_01.json").read_text(encoding="utf-8"))
    anillos = datos["features"][0]["geometry"]["rings"]
    return shapely.Polygon(anillos[0], anillos[1:])


def leer_poligonos():
    """Lee los polígonos de los barrios y repara en memoria el inválido, solo para poder preguntar por un punto."""
    datos = json.loads((EXT / "neighbourhoods.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["neighbourhood"]: shapely.make_valid(shape(f["geometry"])) for f in datos["features"]}


def leer_puntos():
    """Lee los puntos de interés con sus propiedades."""
    filas = []
    for capa in PUNTOS:
        for f in json.loads((EXT / f"{capa}.geojson").read_text(encoding="utf-8"))["features"]:
            c = f["geometry"]["coordinates"]
            filas.append({"capa": capa, "cod_barrio": f["properties"].get("COD_BARRIO"), "x": c[0], "y": c[1]})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 4. Comprobaciones por columna
# ---------------------------------------------------------------------------

def tipo_que_toca(rol):
    """Dice el tipo que toca a una columna por su rol."""
    return {"magnitud": "float", "fecha": "datetime", "booleana": "bool", "identificador": "int", "clave": "int"}.get(rol, "str")


def fila_de_tipos(tabla, columna, rol, frec, leido):
    """Compara el tipo leído con el que toca por el rol y busca avisos de la tabla de tipos."""
    llenos = frec.drop("", errors="ignore")
    total = int(llenos.sum())
    valores = pd.Series(llenos.index.astype("str"), index=llenos.index)
    toca = tipo_que_toca(rol)
    aviso = None
    no_convierte = None
    if total:
        if rol == "magnitud":
            convertidos = pd.to_numeric(valores, errors="coerce")
            no_convierte = llenos[convertidos.isna().to_numpy()].sum()
            if no_convierte:
                aviso = "texto_con_numero"
        elif rol == "fecha":
            convertidos = pd.to_datetime(valores, format="%Y-%m-%d", errors="coerce")
            no_convierte = llenos[convertidos.isna().to_numpy()].sum()
            numeros = pd.to_numeric(valores, errors="coerce")
            if numeros.between(*EXCEL).any():
                aviso = "fecha_excel"
        elif rol == "booleana":
            no_convierte = llenos[~valores.isin(["t", "f", "True", "False"]).to_numpy()].sum()
            if valores.isin(["t", "f"]).any():
                aviso = "booleano_enmascarado"
        elif rol == "codigo" and pd.to_numeric(valores, errors="coerce").notna().all():
            aviso = "codigo_numerico"
        elif columna == "bathrooms_text":
            aviso = "texto_con_numero"
    muestra = [] if rol == "dato_personal" else [v[:40] for v in llenos.sort_values(ascending=False).index.astype("str")[:3]]
    return {"tabla": tabla, "columna": columna, "leido": leido, "rol": rol, "toca": toca,
            "pct_no_convierte": p(int(no_convierte), total) if no_convierte is not None else None, "muestra": muestra, "aviso": aviso}


def escala_de(tabla, columna, numeros):
    """Cuenta las cifras enteras de cada valor y busca dos masas separadas por un hueco: una escala perdida."""
    valores = numeros.index.to_numpy()
    cifras = np.where(np.abs(valores) >= 1, np.floor(np.log10(np.maximum(np.abs(valores), 1))).astype("int64") + 1, 1)
    conteo = pd.Series(numeros.to_numpy(), index=cifras).groupby(level=0).sum()
    menor, mayor = int(conteo.index.min()), int(conteo.index.max())
    salto = mayor - menor >= 2
    factor = uniforme = None
    hueco = any(k not in conteo.index for k in range(menor + 1, mayor))
    total = conteo.sum()
    if salto and hueco and conteo[menor] / total >= 0.05 and conteo[mayor] / total >= 0.05:
        baja = numeros[cifras == menor]
        alta = numeros[cifras == mayor]
        mediana_baja = cuantiles(baja, [0.5])[0]
        razon = float(cuantiles(alta, [0.5])[0] / mediana_baja) if mediana_baja > 0 else None
        factor = int(10 ** round(np.log10(razon))) if razon else None
        uniforme = bool(abs(razon / factor - 1) < 0.1) if razon else None
    return {"tabla": tabla, "columna": columna, "cifras": {str(k): int(v) for k, v in conteo.items()}, "salto": bool(salto), "hueco": bool(hueco),
            "factor": factor, "factor_uniforme": uniforme}


def colas_de(tabla, columna, numeros):
    """Deja los diez valores más bajos y más altos, con su recuento, y el mayor salto entre dos seguidos."""
    def lista(serie):
        return [{"valor": (int(v) if float(v).is_integer() else float(v)), "filas": int(n)} for v, n in serie.items()]

    valores = numeros.index.to_numpy()
    salto = None
    if len(valores) > 1:
        i = int(np.argmax(np.diff(valores)))
        salto = {"desde": float(valores[i]), "hasta": float(valores[i + 1])}
    return {"tabla": tabla, "columna": columna, "bajos": lista(numeros.head(COLAS)), "altos": lista(numeros.tail(COLAS)), "mayor_salto": salto}


def atipicos_de(tabla, columna, numeros):
    """Cuenta los atípicos por rango intercuartílico y por z robusto; solo detectan, no deciden."""
    q1, mediana, q3 = cuantiles(numeros, [0.25, 0.5, 0.75])
    ric = q3 - q1
    v = numeros.index.to_numpy()
    n = numeros.to_numpy()
    distancia = pd.Series(n, index=np.abs(v - mediana)).groupby(level=0).sum().sort_index()
    dam = float(cuantiles(distancia, [0.5])[0])
    fuera_ric = (v < q1 - LIM_IQR * ric) | (v > q3 + LIM_IQR * ric) if ric > 0 else np.zeros(len(v), dtype=bool)
    fuera_z = 0.6745 * np.abs(v - mediana) / dam > LIM_Z if dam > 0 else np.zeros(len(v), dtype=bool)
    sin_dispersion = bool(ric == 0 and dam == 0)
    return {"tabla": tabla, "columna": columna, "iqr": int(n[fuera_ric].sum()) if ric > 0 else None,
            "z_robusto": int(n[fuera_z].sum()) if dam > 0 else None, "los_dos": int(n[fuera_ric & fuera_z].sum()) if ric > 0 and dam > 0 else None,
            "limite_iqr": LIM_IQR, "limite_z": LIM_Z, "sin_dispersion": sin_dispersion, "minimo": float(v.min()), "maximo": float(v.max()),
            "mediana": float(mediana), "q1": float(q1), "q3": float(q3)}


def codigos_de(tabla, columna, rol, frec, filas):
    """Busca códigos de ausencia en texto, en fecha y en número."""
    salida = []
    for valor, n in frec.items():
        texto = str(valor)
        if sin_tildes(texto) in COD_TEXTO or (texto.strip() == "" and texto != "") or texto in COD_FECHA:
            salida.append({"tabla": tabla, "columna": columna, "codigo": texto, "tipo": "texto", "filas": int(n), "pct_filas": p(int(n), filas),
                           "documentado": False, "coincide_con": "", "mismas_filas_que": []})
    if rol == "magnitud":
        numeros = numeros_de(frec.drop("", errors="ignore"))
        if len(numeros) > 2:
            for extremo in (numeros.index.min(), numeros.index.max()):
                n = int(numeros.loc[extremo])
                if 100 * n / filas >= COD_PCT:
                    cod = int(extremo) if float(extremo).is_integer() else float(extremo)
                    fuente = DOCUMENTADOS.get((columna, cod))
                    if tabla in (LIBRO_PRECIO, LIBRO_SUP) and cod == 0:
                        fuente = "nota (2) del libro"
                    salida.append({"tabla": tabla, "columna": columna, "codigo": cod, "tipo": "número", "filas": n, "pct_filas": p(n, filas),
                                   "documentado": fuente is not None, "fuente": fuente, "coincide_con": "", "mismas_filas_que": []})
    return salida


def reparto_de_nulos(tabla, columna, t, dimensiones):
    """Calcula el veredicto del reparto de nulos de una columna con vacíos."""
    vacio = t[columna].isna()
    global_pct = p(int(vacio.sum()), len(t))
    filas, segmentos_validos = [], 0
    for dim in dimensiones:
        g = pd.DataFrame({"v": vacio.to_numpy(), "d": t[dim].to_numpy()}).groupby("d", dropna=False)["v"].agg(["sum", "size"])
        for seg, fila in g.iterrows():
            if fila["size"] >= SEGMENTO_MIN:
                segmentos_validos += 1
                pct = p(int(fila["sum"]), int(fila["size"]))
                if pct >= CONCENTRACION * global_pct:
                    filas.append({"dimension": dim, "segmento": str(seg), "pct": pct, "filas": int(fila["size"])})
    if not dimensiones or not segmentos_validos:
        veredicto = "no_se_puede_saber"
    else:
        veredicto = "concentrados" if filas else "repartidos"
    return {"tabla": tabla, "columna": columna, "global_pct": global_pct, "dimensiones": dimensiones, "veredicto": veredicto, "segmentos": filas}


def vacios_por_fila(tabla, t):
    """Cuenta las filas con 0, 1, 2… vacíos, con todas las columnas y sin las casi vacías."""
    casi = [c for c in t.columns if t[c].isna().mean() > 0.9]
    con = t.isna().sum(axis=1).value_counts().sort_index()
    sin = t.drop(columns=casi).isna().sum(axis=1).value_counts().sort_index()
    return {"tabla": tabla, "con_todas": {str(k): int(v) for k, v in con.items()}, "sin_casi_vacias": {str(k): int(v) for k, v in sin.items()}, "excluidas": casi}


def duplicados_de(tabla, t, clave, identificadores):
    """Cuenta filas iguales con y sin los identificadores, y repetidos por clave."""
    sin = [c for c in t.columns if c not in identificadores]
    return {"tabla": tabla, "exactos": int(t.duplicated().sum()), "exactos_sin_identificadores": int(t[sin].duplicated().sum()),
            "identificadores_quitados": list(identificadores), "clave": clave, "clave_unica": bool(not t.duplicated(clave).any()) if clave else None,
            "por_clave": int(t.duplicated(clave).sum()) if clave else None, "casi_duplicados": None, "logicos": None}


def buscar_personal(tabla, frec, roles):
    """Busca datos personales en claro en las columnas de texto; solo cuenta, nunca copia el valor."""
    salida = []
    for columna, f in frec.items():
        if roles.get(columna) not in ("texto_libre", "categorica"):
            continue
        for clase, patron in PERSONAL.items():
            n = sum(int(v) for k, v in f.items() if patron.search(str(k)))
            if n:
                salida.append({"tabla": tabla, "columna": columna, "clase": clase, "filas": n})
    return salida


# ---------------------------------------------------------------------------
# 5. La tabla de trabajo y la medición en la base de decisión
# ---------------------------------------------------------------------------

def tabla_de_barrios(barrios, oficial, equivalencias=True):
    """Da el precio del m² de cada barrio de Airbnb con las reglas §2. Aeropuerto llega con 0 y queda vacío."""
    of_b = oficial.query('nivel == "barrio"')
    of_d = oficial.query('nivel == "distrito"').assign(clave_d=lambda x: x["nombre"].map(sin_guiones))
    b = barrios.rename(columns={"neighbourhood": "barrio", "neighbourhood_group": "distrito"}).copy()
    b["clave_directa"] = b["barrio"].map(sin_tildes)
    b["clave"] = b["clave_directa"].replace(EQUIV) if equivalencias else b["clave_directa"]
    b = b.merge(of_b[["clave", "cod", "m2_total", "sup_total", "ventas"]], on="clave", how="left", validate="one_to_one")
    b["clave_d"] = b["distrito"].map(sin_guiones)
    b = b.merge(of_d[["clave_d", "m2_total"]].rename(columns={"m2_total": "m2_distrito"}), on="clave_d", how="left", validate="many_to_one")
    b["m2"] = b["m2_total"].where(b["m2_total"].gt(0))
    b["m2"] = b["m2"].mask(b["barrio"].isin(SIN_PROPIO), b["m2_distrito"])
    return b


def superficie_regla(t):
    """Aplica la superficie de valoraciones (reglas §2), de menor a mayor para que lo último mande."""
    b, d = t["banos"], t["bedrooms"]
    s = pd.Series(np.nan, index=t.index, dtype="float64")
    s = s.mask(d <= 1, 50.0).mask(d == 2, 65.0).mask((d == 3) & (b < 2), 90.0).mask((d == 3) & (b >= 2), 110.0)
    return s.mask((d > 3) | (b >= 3), 140.0)


def precio_de_texto(serie):
    """Quita el símbolo y las comas del precio sin cambiar el valor."""
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype("float64")
    return pd.to_numeric(serie.str.replace(r"[$,]", "", regex=True), errors="coerce")


def preparar_trabajo(fotos, cal, limite, b):
    """Monta en memoria la tabla de trabajo de septiembre, sin escribir nada."""
    L = fotos["sep"].copy()
    L["precio"] = precio_de_texto(L["price"])
    L["banos"] = L["bathrooms_text"].map(banos_de_texto)
    L = L.rename(columns={"neighbourhood_cleansed": "barrio", "neighbourhood_group_cleansed": "distrito",
                          "estimated_occupancy_l365d": "ocupacion", "room_type": "tipo_alquiler"})
    L["dentro"] = shapely.contains_xy(limite, L["longitude"].to_numpy(), L["latitude"].to_numpy())
    L["est_min"] = L["id"].map(cal["est_min"])
    L["estancia"] = L["minimum_nights"].fillna(L["est_min"])  # reglas §2
    for clave, col in (("mar", "p_mar"), ("jun", "p_jun")):
        L[col] = L["id"].map(fotos[clave].assign(p=precio_de_texto(fotos[clave]["price"])).set_index("id")["p"])
    L["piso"] = L["tipo_alquiler"].eq("Entire home/apt")
    L["sup_regla"] = superficie_regla(L)
    L = L.merge(b[["barrio", "m2", "m2_distrito"]], on="barrio", how="left", validate="many_to_one")
    L["captura_anterior"] = L["source"].notna()
    L["temporada"] = L["licencia_exencion"].eq("temporada")
    return L


def mascara_fija(L, excluir=None, camas_vacias=False, cero=False):
    """Une los filtros de la base que no cambian entre variantes: piso, lado, tamaño y ocupación. Con cero entran los pisos sin ocupación."""
    m = L["piso"] & ~L["dentro"] & (L["ocupacion"].ge(0) if cero else L["ocupacion"].gt(0)) & L["accommodates"].le(8) & L["banos"].le(5) & L["bedrooms"].le(5)
    m &= (L["beds"].le(6) | L["beds"].isna()) if camas_vacias else L["beds"].le(6)
    return m & ~excluir if excluir is not None else m


def rentabilidad(t, col_precio="precio", desc=DESCUENTO):
    """Calcula la rentabilidad bruta de las reglas §2, en porcentaje."""
    return 100 * t[col_precio] * t["ocupacion"] / (t["sup_regla"] * t["m2"] * desc)


def grupo_de(L, excluir=None, camas_vacias=False, por_foto=None, cero=False):
    """Calcula las doce variantes de las reglas §3 y devuelve los barrios en la mayoría.

    por_foto quita pisos solo en las variantes que usan el precio de esa columna; cero cuenta los pisos sin ocupación.
    """
    fija = mascara_fija(L, excluir, camas_vacias, cero)
    veces = Counter()
    for est in ESTANCIAS:
        for col in ("p_mar", "p_jun", "precio"):
            filas = fija & L["estancia"].le(est) & L[col].between(20, 1000)
            t = L.loc[filas & ~por_foto[col] if por_foto else filas].copy()
            t["r"] = rentabilidad(t, col)
            g = t.groupby("barrio")["r"].agg(pisos="size", mediana="median").dropna(subset="mediana")
            for minimo in MIN_VARIANTE:
                h = g.loc[g["pisos"].ge(minimo)]
                if len(h):
                    veces.update(h.index[h["mediana"].ge(h["mediana"].quantile(0.75))].tolist())
    return sorted(k for k, v in veces.items() if v >= MAYORIA), veces


def medianas_remuestreadas(valores, nombre):
    """Remuestrea la mediana con una semilla ligada al nombre: lo que no cambia da exactamente lo mismo."""
    x = np.sort(np.asarray(valores, dtype="float64"))
    rng = np.random.default_rng(SEMILLA + zlib.crc32(str(nombre).encode("utf-8")))
    return np.median(rng.choice(x, size=(REMUESTREOS, len(x)), replace=True), axis=1)


def pares_distintos(t, columna, minimo=MIN_GRUPO):
    """Devuelve los pares de grupos cuya diferencia de medianas tiene un intervalo del 95 % que no cruza el cero."""
    grupos = {k: g["r"].to_numpy() for k, g in t.dropna(subset="r").groupby(columna) if len(g) >= minimo}
    remuestreo = {k: medianas_remuestreadas(v, k) for k, v in grupos.items()}
    pares = []
    for a, b in combinations(sorted(remuestreo), 2):
        bajo, alto = np.quantile(remuestreo[a] - remuestreo[b], [0.025, 0.975])
        if bajo > 0 or alto < 0:
            pares.append([a, b])
    return pares, {k: float(np.median(v)) for k, v in grupos.items()}


def medir(L, excluir=None, camas_vacias=False):
    """Mide una versión de la base: pisos, grupo, grupo firme, tipo de piso y pares que se distinguen."""
    fija = mascara_fija(L, excluir, camas_vacias)
    bd = L.loc[fija & L["estancia"].le(3) & L["precio"].between(20, 1000)].copy()
    bd["r"] = rentabilidad(bd)
    bd["dormitorios"] = bd["bedrooms"].clip(upper=4).astype("int").astype("str").replace("4", "4 o más")
    grupo, veces = grupo_de(L, excluir, camas_vacias)
    sin_temporada = L["temporada"] if excluir is None else (excluir | L["temporada"])
    firmes = sorted(set(grupo) & set(grupo_de(L, sin_temporada, camas_vacias)[0]))
    pares, _ = pares_distintos(bd, "barrio")
    tipo = {}
    for dim in ("dormitorios", "property_type"):
        pares_t, medianas = pares_distintos(bd, dim)
        orden = sorted(medianas, key=medianas.get, reverse=True)
        ganador = orden[0] if orden else None
        segundo = orden[1] if len(orden) > 1 else None
        tipo[dim] = {"ganador": ganador, "segundo": segundo, "medianas": {k: round(v, 2) for k, v in medianas.items()}, "pares": pares_t,
                     "ganador_se_distingue_del_segundo": sorted([ganador, segundo]) in pares_t if segundo else None}
    return {"pisos": len(bd), "grupo": grupo, "variantes_por_barrio": {k: int(v) for k, v in sorted(veces.items())}, "firmes": firmes,
            "pares_que_se_distinguen": pares, "barrios_comparados": int(bd.dropna(subset="r")["barrio"].value_counts().ge(MIN_GRUPO).sum()),
            "lista_de_comparados": sorted(bd.dropna(subset="r")["barrio"].value_counts().loc[lambda x: x.ge(MIN_GRUPO)].index), "tipo": tipo}


def comparar(base, otra):
    """Dice qué cambia frente a la base: el grupo, los firmes, el tipo y qué pares se distinguen, nunca el orden."""
    pares_b = {tuple(x) for x in base["pares_que_se_distinguen"]}
    pares_o = {tuple(x) for x in otra["pares_que_se_distinguen"]}
    cambian = sorted(pares_b ^ pares_o)
    gb, go = set(base["grupo"]), set(otra["grupo"])
    fb, fo = set(base["firmes"]), set(otra["firmes"])
    implicados = (gb ^ go) | (fb ^ fo)
    comparados_b, comparados_o = set(base["lista_de_comparados"]), set(otra["lista_de_comparados"])

    def distinguidos(a, b, pares, comparados):
        """Dice si dos barrios se distinguen; null si alguno no llega a 30 pisos."""
        return tuple(sorted((a, b))) in pares if a in comparados and b in comparados else None

    # Cada barrio que sale se compara con cada barrio que entra, en las dos versiones de la base.
    entran_salen = [{"entra": e, "sale": s, "se_distinguen_en_la_base": distinguidos(e, s, pares_b, comparados_b),
                     "se_distinguen_en_la_variante": distinguidos(e, s, pares_o, comparados_o)} for s in sorted(gb - go) for e in sorted(go - gb)]
    if gb - go and not go - gb:
        entran_salen = [{"entra": None, "sale": s, "se_distinguen_en_la_base": None, "se_distinguen_en_la_variante": None} for s in sorted(gb - go)]
    tipo = {}
    for dim in base["tipo"]:
        a, b = base["tipo"][dim], otra["tipo"][dim]
        cambia = a["ganador"] != b["ganador"]
        distinto = sorted([a["ganador"], b["ganador"]]) in b["pares"] if cambia else False
        tipo[dim] = {"ganador": b["ganador"], "ganador_antes": a["ganador"], "cambia_ganador": cambia, "nuevo_se_distingue_del_anterior": distinto,
                     "cambia_de_verdad": cambia and distinto, "ganador_se_distingue_del_segundo": b["ganador_se_distingue_del_segundo"],
                     "pares_que_cambian": sorted(map(list, {tuple(x) for x in a["pares"]} ^ {tuple(x) for x in b["pares"]}))}
    return {"pisos": otra["pisos"], "cambio_de_pisos": otra["pisos"] - base["pisos"], "grupo_entran": sorted(go - gb), "grupo_salen": sorted(gb - go),
            "cambia_grupo": gb != go, "firmes_entran": sorted(fo - fb), "firmes_salen": sorted(fb - fo), "cambia_firmes": fb != fo,
            "pares_entran_salen": entran_salen, "pares_que_cambian": len(cambian), "pares_del_grupo_que_cambian": sum(1 for x in cambian if set(x) & (gb | go)),
            "pares_con_barrios_afectados": [list(x) for x in cambian if set(x) & implicados][:20], "muestra_de_pares": [list(x) for x in cambian[:10]], "tipo": tipo,
            "cambia_tipo": any(v["cambia_de_verdad"] for v in tipo.values()), "cambia_primer_tipo": any(v["cambia_ganador"] for v in tipo.values()),
            "cambian_pares_de_tipo": any(v["pares_que_cambian"] for v in tipo.values())}


def veredicto_de(m):
    """Escribe en una frase lo que cambia, para la tabla de decisiones."""
    trozos = []
    if m["cambia_grupo"]:
        trozos.append(f"cambia el grupo: entran {', '.join(m['grupo_entran']) or 'ninguno'} y salen {', '.join(m['grupo_salen']) or 'ninguno'}")
        for x in m["pares_entran_salen"]:
            if x["entra"]:
                lectura = {True: "se distinguen", False: "no se distinguen", None: "no se comparan, porque uno no llega a 30 pisos"}
                trozos.append(f"{x['entra']} y {x['sale']}: en la base {lectura[x['se_distinguen_en_la_base']]}; en la variante {lectura[x['se_distinguen_en_la_variante']]}")
    if m["cambia_firmes"]:
        trozos.append(f"cambian los firmes: entran {', '.join(m['firmes_entran']) or 'ninguno'} y salen {', '.join(m['firmes_salen']) or 'ninguno'}")
    if m["cambia_tipo"]:
        trozos.append("cambia el tipo que rinde más: " + "; ".join(f"{k}, de {v['ganador_antes']} a {v['ganador']}" for k, v in m["tipo"].items() if v["cambia_de_verdad"]))
    elif m["cambia_primer_tipo"]:
        trozos.append("el tipo no cambia con intervalo: " + "; ".join(f"{k}, primero {v['ganador']} en vez de {v['ganador_antes']}, sin distinguirse de él" for k, v in m["tipo"].items() if v["cambia_ganador"]))
    if not (m["cambia_grupo"] or m["cambia_firmes"] or m["cambia_tipo"]):
        trozos.insert(0, "no cambia el grupo ni los firmes ni el tipo")
    trozos.append(f"pares de barrios que cambian al distinguirse: {m['pares_que_cambian']}, de ellos con algún barrio del grupo: {m['pares_del_grupo_que_cambian']}")
    if m["cambian_pares_de_tipo"]:
        trozos.append(f"pares de tipos que cambian: {sum(len(v['pares_que_cambian']) for v in m['tipo'].values())}")
    return "; ".join(trozos)


# ---------------------------------------------------------------------------
# 6. Reglas documentadas, reglas candidatas y cruces
# ---------------------------------------------------------------------------

def reglas_documentadas(L, fotos, b, cal):
    """Comprueba las reglas escritas contra los datos."""
    publicada = L["minimum_nights"].notna()
    formula = (L["number_of_reviews_ltm"] * 2 * L["minimum_nights"].clip(lower=3)).clip(upper=255)
    salida = [
        {"regla": "reglas §2: ocupación = reseñas del último año × 2 × el mayor entre 3 y la estancia, con tope de 255", "filas": int(publicada.sum()),
         "filas_que_incumplen": int((formula[publicada] != L.loc[publicada, "ocupacion"]).sum())},
        {"regla": "reglas §2: ingreso anual = precio × ocupación", "filas": int(L["estimated_revenue_l365d"].notna().sum()),
         "filas_que_incumplen": int(((L["precio"] * L["ocupacion"] - L["estimated_revenue_l365d"]).abs() > 1).sum())},
        {"regla": "reglas §1: 128 barrios y 21 distritos", "filas": len(b),
         "filas_que_incumplen": int(abs(b["neighbourhood"].nunique() - 128) + abs(b["neighbourhood_group"].nunique() - 21))},
        {"regla": "reglas §2: ocupación con tope de 255", "filas": len(L), "filas_que_incumplen": int(L["ocupacion"].gt(255).sum())},
    ]
    pisos = mascara_fija(L) & L["precio"].between(20, 1000) & publicada & L["est_min"].notna()
    t = L.loc[pisos]
    return salida, {"pisos_con_las_dos": len(t), "coincide_pct": p(int(t["minimum_nights"].eq(t["est_min"]).sum()), len(t)),
                    "mismo_lado_de_3_pct": p(int(t["minimum_nights"].le(3).eq(t["est_min"].le(3)).sum()), len(t))}


def reglas_candidatas(L, rev, cal):
    """Propone reglas que se ven en los datos, sin ejecutarlas como comprobación del caso."""
    n_resenas = L["id"].map(rev["resenas"]).fillna(0)
    suma = L["calculated_host_listings_count_entire_homes"] + L["calculated_host_listings_count_private_rooms"] + L["calculated_host_listings_count_shared_rooms"]
    fr, lr = pd.to_datetime(L["first_review"], format="%Y-%m-%d"), pd.to_datetime(L["last_review"], format="%Y-%m-%d")
    candidatas = [
        (["beds", "accommodates"], "las camas no superan a los huéspedes", int(L["beds"].gt(L["accommodates"]).sum())),
        (["bedrooms", "accommodates"], "las habitaciones no superan a los huéspedes", int(L["bedrooms"].gt(L["accommodates"]).sum())),
        (["room_type", "bathrooms_text"], "un piso no lleva baño compartido", int((L["piso"] & L["bathrooms_text"].str.contains("shared", case=False, na=False)).sum())),
        (["calculated_host_listings_count"], "el total de anuncios del anfitrión es la suma de sus tres tipos", int(L["calculated_host_listings_count"].ne(suma).sum())),
        (["availability_30", "availability_60", "availability_90", "availability_365"], "los días libres crecen con el horizonte",
         int((L["availability_30"].gt(L["availability_60"]) | L["availability_60"].gt(L["availability_90"]) | L["availability_90"].gt(L["availability_365"])).sum())),
        (["number_of_reviews_l30d", "number_of_reviews_ltm", "number_of_reviews"], "las reseñas de un periodo no superan a las de otro mayor",
         int((L["number_of_reviews_l30d"].gt(L["number_of_reviews_ltm"]) | L["number_of_reviews_ltm"].gt(L["number_of_reviews"])).sum())),
        (["minimum_nights", "maximum_nights"], "la estancia mínima no supera a la máxima", int(L["minimum_nights"].gt(L["maximum_nights"]).sum())),
        (["first_review", "last_review"], "la primera reseña no va después de la última", int((fr > lr).sum())),
        (["number_of_reviews", "first_review"], "cero reseñas si y solo si no hay primera reseña", int(L["number_of_reviews"].eq(0).ne(L["first_review"].isna()).sum())),
        (["has_availability", "availability_365"], "marca de sin disponibilidad, cero días libres", int((L["has_availability"].eq("f") & L["availability_365"].gt(0)).sum())),
        (["number_of_reviews", "reseñas"], "el contador coincide con las filas de reseñas del anuncio", int(L["number_of_reviews"].ne(n_resenas).sum())),
        (["availability_365", "calendario"], "los días libres coinciden con los del calendario", int(L["availability_365"].ne(L["id"].map(cal["libres"])).sum())),
    ]
    return [{"id": f"RC-{i:02d}", "tabla": TABLA_FOTO["sep"], "columnas": c, "regla": r, "filas_que_incumplen": n, "aprobada": False}
            for i, (c, r, n) in enumerate(candidatas, 1)]


def cruce(izq, der, clave, cardinalidad, a, b, supuesta=False, antes=None, unica=None, formato=False):
    """Cuenta las claves sin pareja de cada lado de una relación."""
    a, b = set(a), set(b)
    fila = {"izquierda": izq, "derecha": der, "clave": clave, "cardinalidad_esperada": cardinalidad, "supuesta": supuesta,
            "izquierda_distintas": len(a), "derecha_distintas": len(b),
            "sin_pareja_izquierda": len(a - b), "sin_pareja_derecha": len(b - a), "sin_pareja_izquierda_pct": p(len(a - b), len(a)),
            "sin_pareja_derecha_pct": p(len(b - a), len(b)), "formato_distinto": formato, "unica_en_maestro": unica}
    if antes:
        fila["sin_pareja_izquierda_antes"] = len(set(antes[0]) - set(antes[1]))
        fila["sin_pareja_derecha_antes"] = len(set(antes[1]) - set(antes[0]))
    return fila


def cruces_de(fotos, cal, rev, b, oficial, licencias, poligonos, L):
    """Revisa cada relación, documentada o evidente, sin guardar ninguna tabla cruzada."""
    sep = set(fotos["sep"]["id"])
    of_b = oficial.query('nivel == "barrio"')
    of_d = oficial.query('nivel == "distrito"')
    con_equiv = b["clave_directa"].replace(EQUIV)
    salida = [
        cruce(f"{TABLA_FOTO['sep']}.id", f"{CALENDARIO}.listing_id", ["id"], "1:N", sep, cal.index, unica=True),
        cruce(f"{TABLA_FOTO['sep']}.id", f"{RESENAS}.listing_id", ["id"], "1:N", sep, rev.index, unica=True),
    ]
    for clave in ("jun", "mar", "dic"):
        salida.append(cruce(f"{TABLA_FOTO['sep']}.id", f"{TABLA_FOTO[clave]}.id", ["id"], "1:1", sep, fotos[clave]["id"], unica=True))
    for clave, t in fotos.items():
        salida.append(cruce(f"{TABLA_FOTO[clave]}.neighbourhood_cleansed", f"{BARRIOS}.neighbourhood", ["barrio"], "N:1", t["neighbourhood_cleansed"].dropna(),
                            b["barrio"], unica=bool(b["barrio"].is_unique)))
    salida.append(cruce(f"{BARRIOS}.neighbourhood", f"{LIBRO_PRECIO}.barrio", ["nombre normalizado"], "1:1", con_equiv, of_b["clave"], supuesta=True,
                        antes=(b["clave_directa"], of_b["clave"]), unica=bool(of_b["clave"].is_unique), formato=True))
    salida.append(cruce(f"{BARRIOS}.neighbourhood_group", f"{LIBRO_PRECIO}.distrito", ["nombre normalizado"], "N:1", b["distrito"].map(sin_guiones), of_d["nombre"].map(sin_guiones),
                        supuesta=True, antes=(b["distrito"].map(sin_tildes), of_d["clave"]), unica=True, formato=True))
    distrito_lic = licencias["distrito"].str.replace("Distrito de ", "", regex=False)
    salida.append(cruce(f"{LICENCIAS}.distrito", f"{BARRIOS}.neighbourhood_group", ["distrito"], "N:1", distrito_lic.map(sin_guiones), b["distrito"].map(sin_guiones), supuesta=True,
                        antes=(licencias["distrito"], b["distrito"]), unica=None, formato=True))
    salida.append(cruce(f"{LICENCIAS}.barrio", f"{BARRIOS}.neighbourhood", ["barrio"], "N:1", licencias["barrio"].dropna(), b["barrio"], supuesta=True, unica=True))
    salida.append(cruce(f"{BARRIOS}.neighbourhood", "neighbourhoods.geojson.neighbourhood", ["barrio"], "1:1", b["barrio"], poligonos.keys(), unica=True))
    return salida


def punto_en_su_barrio(L, poligonos):
    """Cuenta los anuncios cuyo punto no cae dentro del polígono de su barrio."""
    fuera = 0
    for barrio, g in L.groupby("barrio"):
        if barrio in poligonos:
            fuera += int((~shapely.contains_xy(poligonos[barrio], g["longitude"].to_numpy(), g["latitude"].to_numpy())).sum())
    return fuera


# ---------------------------------------------------------------------------
# 7. La tabla de decisiones
# ---------------------------------------------------------------------------

def asuntos_de(L, fotos, b, oficial, licencias, puntos, resenas_rep, base_m, dicc_vacias, medidor, duplicados, n_fuera_barrio, geom_invalidos):
    """Monta una fila por asunto que necesita criterio: con su decisión si existe, o con opciones y medición."""
    en_base = mascara_fija(L) & L["estancia"].le(3) & L["precio"].between(20, 1000)
    fuera = L["piso"] & ~L["dentro"]
    a_utm = pyproj.Transformer.from_crs(4326, 25830, always_xy=True)
    xs, ys = a_utm.transform(L["longitude"].to_numpy(), L["latitude"].to_numpy())
    limite = leer_limite()
    bx, by = a_utm.transform(*np.array(limite.exterior.coords).T)
    cerca = pd.Series(shapely.distance(shapely.LinearRing(np.column_stack([bx, by])), shapely.points(xs, ys)) < 150, index=L.index)
    vacia_precio = L["precio"].isna()
    no_vivienda = L["piso"] & ~L["property_type"].str.startswith("Entire")
    incoherente = L["beds"].gt(L["accommodates"]) | L["bedrooms"].gt(L["accommodates"])
    cero_banos = L["banos"].eq(0)
    camas_vacias = L["beds"].isna()
    tam_vacio = L["bedrooms"].isna() | L["banos"].isna()
    larga = L["estancia"].gt(365)
    nombres_equiv = sorted(b.loc[b["clave_directa"].isin(EQUIV), "barrio"])
    en_equiv = L["barrio"].isin(nombres_equiv)
    aero = L["barrio"].eq(AEROPUERTO)
    casco = L["barrio"].eq(CASCO_VALLECAS)
    sin_propio = L["barrio"].isin(SIN_PROPIO)
    of_d = oficial.query('nivel == "distrito"').assign(c=lambda x: x["nombre"].map(sin_guiones)).set_index("c")
    of_b = oficial.query('nivel == "barrio"').set_index("cod")
    d_casco = L.loc[casco, "distrito"].iloc[0] if casco.any() else None
    fila_oficial = of_b.loc[of_b["nombre"].str.strip().eq(AEROPUERTO)]
    ventas_aero = int(fila_oficial["ventas"].iloc[0]) if len(fila_oficial) else None
    vacias = [k for k, v in dicc_vacias.items() if k != "bathrooms"]
    claves_airbnb = set(b["clave_directa"].replace(EQUIV))
    sin_pareja_oficial = "; ".join(sorted(re.sub(r"\s+", " ", n).strip() for n, c, nv in zip(oficial["nombre"], oficial["clave"], oficial["nivel"])
                                          if nv == "barrio" and c not in claves_airbnb))
    plantas = licencias["planta"].astype("str").str.upper().str.strip()

    def precio_recuperado():
        """Toma de junio, y si no de marzo, el precio que falta en septiembre."""
        t = L.copy()
        t["precio"] = t["precio"].fillna(t["p_jun"]).fillna(t["p_mar"])
        return medidor(t)

    def m2_cambiado(mascara, columna="m2_distrito"):
        """Cambia el precio del m² de unos barrios y mide."""
        t = L.copy()
        t["m2"] = t["m2"].mask(mascara, t[columna])
        return medidor(t)

    def m2_vacio(mascara):
        """Deja sin precio del m² unos barrios y mide."""
        t = L.copy()
        t["m2"] = t["m2"].mask(mascara)
        return medidor(t)

    A = []

    def anadir(clave, tabla, columna, filas, mascara=None, decision=None, opciones=None, medicion=None, no_medible=None, bloque="3.10", nota=""):
        """Añade un asunto con sus filas en la tabla y en la base."""
        A.append({"clave": clave, "tabla": tabla, "columna": columna, "filas_afectadas": filas,
                  "en_base": int((mascara & en_base).sum()) if mascara is not None else None, "decision": decision, "opciones": opciones or [],
                  "medicion": medicion, "no_medible": no_medible, "bloque": bloque, "nota": nota})

    sep = TABLA_FOTO["sep"]
    # 7.1 Sin decisión escrita: la lista del paso 3 del cuaderno y lo que ha salido al recorrer las tablas.
    anadir("precio_vacio", sep, "price", int(vacia_precio.sum()), vacia_precio, opciones=["sigue vacío y el anuncio queda fuera (reglas §2: un vacío no se rellena)", "se toma el de junio y, si no, el de marzo"],
           medicion=precio_recuperado(), bloque="3.4",
           nota=f"Lista del cuaderno. Son {int((vacia_precio & fuera).sum())} pisos fuera del centro; {int((vacia_precio & fuera & (L['p_jun'].notna() | L['p_mar'].notna())).sum())} tienen precio en junio o marzo.")
    anadir("captura_anterior", sep, "source", int(L["captura_anterior"].sum()), L["captura_anterior"], opciones=["se quedan", "salen de la base"],
           medicion=medidor(L, excluir=L["captura_anterior"]), bloque="3.4",
           nota=f"Lista del cuaderno. En septiembre el vacío de source es la captura nueva; en marzo y junio esa marca viene escrita. De los {int(L['minimum_nights'].isna().sum())} anuncios de estancia vacía, {int((L['minimum_nights'].isna() & L['captura_anterior']).sum())} son de captura anterior.")
    anadir("aeropuerto", LIBRO_PRECIO, "Euros/m2 · Total", int(aero.sum()), aero, opciones=["queda sin precio y sin rentabilidad", "toma el precio de su distrito, como San Andrés y Ambroz"],
           medicion=m2_cambiado(aero), bloque="3.10",
           nota=f"Lista del cuaderno. El libro le pone 0 y su nota dice que no muestra el dato con menos de 15 casos, y sin embargo cuenta {ventas_aero} ventas.")
    anadir("equivalencias", f"{BARRIOS}, {LIBRO_PRECIO}", "neighbourhood", len(nombres_equiv), en_equiv, opciones=["se aprueban las siete equivalencias", "esos barrios quedan sin precio oficial"],
           medicion=m2_vacio(en_equiv), bloque="3.11", nota=f"Lista del cuaderno. Barrios: {', '.join(nombres_equiv)}. Las filas son barrios; en la base, pisos.")
    if casco.any():
        m2_d = float(of_d.loc[sin_guiones(d_casco), "m2_total"])
        m2_b = float(L.loc[casco, "m2"].iloc[0])
        anadir("casco_vallecas", f"{BARRIOS}, {LIBRO_PRECIO}", "neighbourhood", int(casco.sum()), casco,
               opciones=["usa el precio del barrio con su mismo nombre", "usa el precio de su distrito, como San Andrés y Ambroz"],
               medicion=m2_cambiado(casco), bloque="3.11",
               nota=f"Nuevo. Airbnb tiene 2 barrios en Villa de Vallecas y el libro 3: Ensanche de Vallecas no tiene pareja. Que su suelo caiga dentro del barrio de Airbnb es una deducción sin confirmar. Precio del barrio, {m2_b:.2f} €/m²; del distrito, {m2_d:.2f} €/m².")
    anadir("camas_vacias", sep, "beds", int(camas_vacias.sum()), camas_vacias, opciones=["un vacío no pasa el tope de 6 camas", "un vacío pasa el tope"],
           medicion=medidor(L, camas_vacias=True), bloque="3.4", nota=f"El filtro quita {int((camas_vacias & fuera & L['ocupacion'].gt(0) & L['precio'].between(20, 1000)).sum())} pisos con ocupación por estar vacío.")
    anadir("banos_cero", sep, "bathrooms_text", int(cero_banos.sum()), cero_banos, opciones=["se quedan", "salen de la base"], medicion=medidor(L, excluir=cero_banos), bloque="3.8",
           nota="Las reglas dicen cómo leer el texto y no qué significa un cero.")
    anadir("no_vivienda", sep, "property_type", int(no_vivienda.sum()), no_vivienda, opciones=["se quedan: la regla mira el tipo de alquiler", "salen los inmuebles que no empiezan por «Entire»"],
           medicion=medidor(L, excluir=no_vivienda), bloque="3.10", nota="Son aparthoteles, autocaravanas, yurtas y similares con tipo de alquiler de piso.")
    anadir("tamano_incoherente", sep, "beds, bedrooms, accommodates", int(incoherente.sum()), incoherente, opciones=["se quedan", "salen de la base"], medicion=medidor(L, excluir=incoherente), bloque="3.10",
           nota="Más camas o habitaciones que huéspedes. Son las reglas candidatas RC-01 y RC-02.")
    anadir("estancia_larga", sep, "minimum_nights", int(larga.sum()), larga, opciones=["se quedan en la tabla", "salen de la tabla de trabajo"],
           no_medible="No entran en la base: el filtro de hasta 3 noches, o de 6 en las variantes, ya los quita.", bloque="3.8", nota="Lista del cuaderno.")
    pf = puntos.loc[~puntos["x"].between(-3.95, -3.45) | ~puntos["y"].between(40.25, 40.65)]
    anadir("puntos_de_interes", "puntos de interés", "coordenadas, COD_BARRIO", len(pf), opciones=["se quitan esos puntos", "se buscan sus coordenadas"],
           no_medible="La rentabilidad no usa los puntos de interés: no pueden cambiar el grupo ni el tipo. Afectan al atractivo, que aún no tiene distancia ni peso (reglas §3).", bloque="3.8",
           nota=f"Lista del cuaderno. Además, {int(puntos['cod_barrio'].isna().sum())} puntos no traen COD_BARRIO.")
    anadir("licencias_escritura", LICENCIAS, "distrito, planta", int(licencias.duplicated().sum()), opciones=["se normaliza la escritura", "se deja como llega, porque es contexto"],
           no_medible="La licencia no se une a ningún anuncio (reglas §1): no entra en la rentabilidad.", bloque="3.7",
           nota=f"Lista del cuaderno. Distrito en {licencias['distrito'].nunique()} formas y planta en {plantas.nunique()} tras igualar mayúsculas. Las filas son las iguales a otra; sin número no se puede saber si son licencias distintas.")
    anadir("columnas_vacias", sep, ", ".join(vacias), len(L), opciones=["salen de las tablas de trabajo", "se quedan vacías"], no_medible="Ninguna entra en el cálculo.", bloque="3.2",
           nota="Las filas son las de la foto: la columna falta entera.")
    anadir("poligono_invalido", "neighbourhoods.geojson", "geometry", geom_invalidos, opciones=["se repara el polígono", "no se usa"], no_medible="El barrio del anuncio sale de su columna y no del polígono: no entra en la rentabilidad.", bloque="3.2",
           nota=f"{n_fuera_barrio} anuncios de septiembre no caen dentro del polígono de su barrio, reparado en memoria para medirlo.")

    # 7.2 Con decisión escrita: se cita dónde está y no se mide.
    existe = [
        ("estancia_vacia", sep, "minimum_nights", int(L["minimum_nights"].isna().sum()), L["minimum_nights"].isna(), "reglas §2: la menor del calendario de los próximos 12 meses", "3.4"),
        ("banos_vacio", sep, "bathrooms", len(L), None, "reglas §2: los baños se leen del texto; medio baño vale 0,5", "3.2"),
        ("tamano_vacio", sep, "bedrooms, bathrooms_text", int(tam_vacio.sum()), tam_vacio, "reglas §2: un vacío no se rellena; sin habitaciones o baños no hay superficie y quedan fuera", "3.4"),
        ("disponibilidad_vacia", sep, "has_availability", int(L["has_availability"].isna().sum()), L["has_availability"].isna(), "reglas §2: un vacío significa que no consta; la base no filtra por esta marca", "3.4"),
        ("sin_precio_propio", f"{BARRIOS}, {LIBRO_PRECIO}", "neighbourhood", int(sin_propio.sum()), sin_propio, "reglas §2: San Andrés y Ambroz toman el precio de su distrito. Sin pareja del lado oficial quedan: " + sin_pareja_oficial, "3.11"),
        ("precio_texto", sep, "price", int(L["price"].notna().sum()), None, "reglas §2: el precio publicado, en euros; el símbolo $ es formato", "3.3"),
        ("ocupacion_cero", sep, "estimated_occupancy_l365d", int(L["ocupacion"].eq(0).sum()), None, "reglas §2 y §7: fuera del ranking, con su peso como riesgo", "3.4"),
        ("ocupacion_tope", sep, "estimated_occupancy_l365d", int(L["ocupacion"].eq(255).sum()), L["ocupacion"].eq(255), "reglas §2: tope de la fuente; en la parte alta no ordena", "3.8"),
        ("precio_extremo", sep, "price", int((L["precio"].notna() & ~L["precio"].between(20, 1000)).sum()), None, "reglas §3: precio entre 20 y 1.000 €", "3.8"),
        ("dormitorios_cero", sep, "bedrooms", int(L["bedrooms"].eq(0).sum()), L["bedrooms"].eq(0), "reglas §2: hasta 1 habitación, 50 m²", "3.8"),
        ("anuncio_lleno", sep, "availability_365", int((L["availability_365"].eq(0) & L["number_of_reviews_ltm"].gt(0)).sum()), L["availability_365"].eq(0), "reglas §1 y §7: se quedan", "3.10"),
        ("temporada", sep, "licencia_exencion", int(L["temporada"].sum()), L["temporada"], "reglas §3: se quedan; deciden grupo firme y segunda línea", "3.10"),
        ("borde", sep, "latitude, longitude", int(cerca.sum()), cerca, "reglas §1: cerca del borde su lado no se puede asegurar y se cuentan", "3.10"),
        ("foto_sin_precio", TABLA_FOTO["dic"], "price", len(fotos["dic"]), None, "briefing, alcance: diciembre mide la oferta y no trae precio", "3.2"),
        ("dos_anuncios_iguales", sep, "id", duplicados, None, "reglas §1: dos anuncios son distintos si tienen distinto número", "3.5"),
        ("resenas_repetidas", RESENAS, "listing_id, date", resenas_rep, None, "cuaderno, sección 2: son reseñas distintas del mismo día y se cuentan por filas", "3.6"),
    ]
    for clave, tabla, columna, filas, mascara, decision, bloque in existe:
        anadir(clave, tabla, columna, filas, mascara, decision=decision, bloque=bloque)
    # Una fila sin ningún registro afectado no es un asunto: no pide criterio.
    A = [f for f in A if f["filas_afectadas"]]
    for i, fila in enumerate(A, 1):
        fila["id"] = f"C-{i:02d}"
        fila["veredicto"] = veredicto_de(fila["medicion"]) if fila["medicion"] else None
    return A


# ---------------------------------------------------------------------------
# 8. Informe para la persona, generado del JSON
# ---------------------------------------------------------------------------

def celda(texto):
    """Prepara un texto para una celda de tabla."""
    return "" if texto is None else str(texto).replace("|", "/").replace("\n", " ")


def informe(s):
    """Genera el Markdown a partir del diccionario que se guarda en el JSON."""
    if s["resultado"]["estado"] == "PARADO":
        return "# Calidad de datos\n\n" + s["resultado"]["resumen"] + "\n"
    r = ["# Calidad de datos", "", "Diagnóstico de las tablas tal como llegan. No se ha corregido ningún dato.", "", "## Fuente analizada", ""]
    r += [f"- Ejecución: {s['fecha_ejecucion']}, con Python {s['python']} y pandas {s['pandas']}.",
          f"- Fecha de los datos: {s['fecha_datos']}.",
          f"- Se partió del diccionario del origen: {'sí' if s['con_diccionario'] else 'no'}.", ""]
    r += [f"- `{e['ruta']}`: {e['bytes']} bytes, huella {e['sha256']}." for e in s["entradas"]]
    r += ["", "## Resumen", "", s["resultado"]["resumen"], "", "Controles de la lectura de los datos:", ""]
    for c in s["controles"]:
        da = ", ".join(c["da"]) if isinstance(c["da"], list) else c["da"]
        estado = {True: "sale", False: f"NO SALE, se esperaba {c['esperado']}", None: "sin referencia"}[c["sale"]]
        r.append(f"- {c['nombre']}: {da}; {estado}.")
    r += ["", "Los problemas que más pesan:", ""]
    for f in s["tabla_de_decisiones"]:
        if f["medicion"] and (f["medicion"]["cambia_grupo"] or f["medicion"]["cambia_firmes"] or f["medicion"]["cambia_tipo"]):
            r.append(f"- {f['id']}, {f['clave']}: {f['veredicto']}.")
    r += ["", "## Inspección general", ""]
    r += [f"- `{t['tabla']}`: {t['filas']} filas y {t['columnas']} columnas; una fila es {t['que_es_una_fila']}." for t in s["inspeccion"]]
    r += ["", "Geometrías:", ""] + [f"- `{g['fichero']}`: {g['elementos']} elementos, {g['invalidos']} inválidos y {g['fuera_de_madrid']} fuera del marco de Madrid." for g in s["geometrias"]]
    r += ["", "## Estructura", ""]
    for t in s["estructura"]:
        r.append(f"- `{t['tabla']}`: {len(t['vacias'])} columnas enteras vacías ({', '.join(t['vacias']) or 'ninguna'}); casi vacías: {', '.join(t['casi_vacias']) or 'ninguna'}; "
                 f"constantes: {', '.join(t['constantes']) or 'ninguna'}.")
    cambian = Counter(n["tabla"] for n in s["nombres"] if n["columna"] != n["normalizado"])
    colisiones = [n for n in s["nombres"] if n["colision_con"]]
    r += [f"- Nombres de columna que cambiarían al normalizar: {sum(cambian.values())}, en {', '.join(sorted(cambian)) or 'ninguna tabla'}; colisiones: {len(colisiones)}.",
          f"- Forma de la tabla: {s['forma_de_la_tabla']}"]
    r += ["", "## Tipos y formatos", ""]
    avisos = Counter(t["aviso"] for t in s["tipos"] if t["aviso"])
    r += [f"- {k}: {v} columnas." for k, v in sorted(avisos.items())]
    r.append(f"- Columnas con algún valor que no convierte al tipo que toca: {sum(1 for t in s['tipos'] if t['pct_no_convierte'])}.")
    saltos = [e for e in s["escala"] if e["salto"]]
    perdidas = [e for e in s["escala"] if e["factor"]]
    r.append(f"- Escala: {len(saltos)} de {len(s['escala'])} magnitudes abarcan tres órdenes de magnitud o más. Sin dos masas separadas por un hueco de cifras se leen como colas largas. "
             f"Posibles escalas perdidas: {len(perdidas)}.")
    r += [f"  - `{e['tabla']}.{e['columna']}`: factor {e['factor']}, uniforme {e['factor_uniforme']}, cifras {e['cifras']}." for e in perdidas]
    r += ["", "## Valores ausentes", ""]
    veredictos = Counter(n["veredicto"] for n in s["nulos_por_segmento"])
    r.append("Reparto de vacíos: " + ", ".join(f"{k} {v}" for k, v in sorted(veredictos.items())) + ".")
    r += [""]
    for n in s["nulos_por_segmento"]:
        if n["tabla"] == TABLA_FOTO["sep"] and n["veredicto"] == "concentrados":
            seg = "; ".join(f"{x['dimension']}={x['segmento']} {x['pct']} %" for x in n["segmentos"][:3])
            r.append(f"- `{n['columna']}`: {n['global_pct']} % global; {seg}.")
    r += ["", "Códigos de ausencia:", ""]
    candidatos = Counter(c["tabla"] for c in s["codigos_de_ausencia"] if c["tipo"] == "número" and not c["documentado"])
    r += [f"- `{t}`: {n} valores numéricos en un extremo con el 5 % de las filas o más, sin documentar; casi todos son el menor valor posible de la columna y están en el JSON." for t, n in sorted(candidatos.items())]
    for c in s["codigos_de_ausencia"]:
        if c["tipo"] == "texto" or c["documentado"]:
            r.append(f"- `{c['tabla']}.{c['columna']}` = {c['codigo']}: {c['filas']} filas ({c['pct_filas']} %), documentado {c['documentado']}.")
    juntas = [c for c in s["codigos_de_ausencia"] if c["tipo"] == "vacío en las mismas filas" and c["tabla"] == TABLA_FOTO["sep"]]
    r += [f"- En septiembre, `{c['columna']}` y {', '.join(f'`{x}`' for x in c['mismas_filas_que'])} están vacías en las mismas {c['filas']} filas: es una ausencia de la fila." for c in juntas]
    r += ["", "Vacíos por fila, en la foto principal:", ""]
    v = next(x for x in s["vacios_por_fila"] if x["tabla"] == TABLA_FOTO["sep"])
    r += [f"- Sin las columnas casi vacías, {v['sin_casi_vacias'].get('0', 0)} filas no tienen ningún vacío; se excluyen {', '.join(v['excluidas'])}."]
    r += ["", "## Duplicados", ""]
    for d in s["duplicados"]:
        r.append(f"- `{d['tabla']}`: {d['exactos']} filas iguales; {d['exactos_sin_identificadores']} sin los identificadores; por clave, {d['por_clave']}.")
    r += ["", "## Claves y granularidad", ""]
    for t in s["inspeccion"]:
        r.append(f"- `{t['tabla']}`: clave {', '.join(t['clave']) or 'ninguna'}; única: {t['clave_unica']}.")
    r += ["", "## Categóricas y texto", ""]
    por_col = Counter((c["tabla"], c["columna"]) for c in s["categorias_raras"])
    r += [f"- `{t}.{c}`: {n} categorías raras." for (t, c), n in sorted(por_col.items()) if t == TABLA_FOTO["sep"] or t == LICENCIAS]
    r.append(f"- Textos con forma de orden: {len(s['instrucciones_en_texto'])}.")
    r += ["", "## Numéricas y outliers", ""]
    for o in s["outliers"]:
        if o["tabla"] == TABLA_FOTO["sep"] or o["tabla"] == CALENDARIO:
            r.append(f"- `{o['tabla']}.{o['columna']}`: de {o['minimo']} a {o['maximo']}, mediana {o['mediana']}; intercuartílico {o['iqr']}, z robusto {o['z_robusto']}, los dos {o['los_dos']}.")
    r += ["", "Los límites solo detectan. Las colas de cada magnitud están en el JSON."]
    r += ["", "## Fechas", ""]
    for f in s["fechas"]:
        r.append(f"- `{f['tabla']}.{f['columna']}`: de {f['minimo']} a {f['maximo']}; {f['invalidas']} inválidas; {f['futuras']} futuras.")
    r += [""] + [f"- {x}" for x in s["fechas_notas"]]
    r += ["", "## Reglas lógicas e integridad", ""]
    r += [f"- {x['regla']}: {x['filas_que_incumplen']} de {x['filas']} no la cumplen." for x in s["reglas_documentadas"]]
    e = s["estancia_regla"]
    r.append(f"- reglas §2, estancia del calendario: sobre {e['pisos_con_las_dos']} pisos con las dos, coincide el {e['coincide_pct']} % y el lado de las 3 noches, el {e['mismo_lado_de_3_pct']} %.")
    r += ["", "## Cruces entre tablas", ""]
    for c in s["cruces"]:
        extra = f" Antes de igualar el formato: {c['sin_pareja_izquierda_antes']} y {c['sin_pareja_derecha_antes']}." if "sin_pareja_izquierda_antes" in c else ""
        r.append(f"- `{c['izquierda']}` y `{c['derecha']}`: sin pareja {c['sin_pareja_izquierda']} a la izquierda y {c['sin_pareja_derecha']} a la derecha.{extra}" + (" Relación supuesta." if c["supuesta"] else ""))
    x = s["cruces_magnitudes"]
    r += ["", f"De los {x['anuncios']} anuncios de septiembre, el contador de reseñas coincide con las filas en {x['resenas_que_cuadran_con_su_contador']}, los días libres coinciden con el calendario en "
          f"{x['dias_libres_que_cuadran_con_el_calendario']} y {x['anuncios_fuera_del_poligono_de_su_barrio']} caen fuera del polígono de su barrio. Las coordenadas vienen desplazadas hasta 150 m (reglas §1)."]
    r += ["", "## Reglas candidatas para aprobar", ""]
    r += [f"- {c['id']}: {c['regla']} ({', '.join(c['columnas'])}). La incumplirían {c['filas_que_incumplen']} filas." for c in s["reglas_candidatas"]]
    r += ["", "## Resumen de problemas detectados", ""]
    r += [f"- {x['id']}, {x['tabla']}, {x['columna']}: {x['resultado']}." for x in s["problemas"]]
    r += ["", "## Posibles acciones", ""]
    r += [f"- {x['id']}: {x['posible_accion']}." for x in s["problemas"] if x["posible_accion"]]
    r += ["", "## Parámetros usados", ""]
    r += [f"- {x['nombre']}: {x['valor']} ({x['origen']})." for x in s["parametros"]]
    r += ["", "## Datos personales", ""] + s["datos_personales_texto"]
    r += ["", "## Límites de esta revisión", ""]
    r.append(f"- Relaciones revisadas en el bloque 3.11: {len(s['cruces'])}; las supuestas van marcadas.")
    r.append(f"- Dimensiones usadas para segmentar los vacíos: {', '.join(s['dimensiones_de_nulos'])}. Un segmento no revisado puede esconder una concentración.")
    r += [f"- No aplicado, {x['control']}: {x['motivo']}." for x in s["no_aplicado"]]
    if s["avisos"]:
        r.append(f"- Magnitudes enteras vacías, sin escala ni colas: {len(s['avisos'])}; están en `avisos` del JSON.")
    r += ["", "## Tabla de decisiones", "",
          f"La base de referencia tiene {s['medicion']['base']['pisos']} pisos y su grupo son {len(s['medicion']['base']['grupo'])} barrios: {', '.join(s['medicion']['base']['grupo'])}. "
          f"Los firmes son {', '.join(s['medicion']['base']['firmes'])}. Se distinguen {len(s['medicion']['base']['pares_que_se_distinguen'])} pares de los {s['medicion']['base']['barrios_comparados']} barrios con 30 pisos o más. "
          "Dos barrios se distinguen si el intervalo del 95 % de su diferencia de medianas no cruza el cero. Un cambio en pocos pares puede venir de un intervalo que ya rozaba el cero. "
          "Esta es la única tabla del informe, porque aquí hay que comparar y decidir.", "",
          "| Id | Tabla y columna | Filas | En la base | Decisión que existe | Opciones | Qué cambia en la base | Nota |", "|---|---|---|---|---|---|---|---|"]
    for f in s["tabla_de_decisiones"]:
        cambia = f["veredicto"] or (f["no_medible"] or ("no se mide: ya hay decisión" if f["decision"] else ""))
        r.append("| " + " | ".join(celda(x) for x in [f["id"], f"{f['tabla']} · {f['columna']}", f["filas_afectadas"], f["en_base"], f["decision"] or "no existe", " / ".join(f["opciones"]), cambia, f["nota"]]) + " |")
    r += ["", "Ninguna opción está elegida. Cada fila sin decisión la resuelve la persona responsable."]
    return "\n".join(r) + "\n"


def texto_datos_personales(proteccion):
    """Redacta el apartado de datos personales desde proteccion-datos.json."""
    if proteccion is None:
        return ["No existe `proteccion-datos.json`: los datos no pasaron por la protección."]
    tecnicas = defaultdict(set)
    for t in proteccion["tablas"]:
        for c in t["campos"]:
            tecnicas[(c["tecnica"], c["resultado"])].add(c["columna"])
    lineas = [f"Son datos {proteccion.get('datos', 'sin calificar')}. La protección se aplica al recibir los datos, antes de cualquier análisis. "
              "Se quitaron columnas: es una supresión sin códigos con clave, de modo que no hay seudonimización que deshacer. "
              "En el trabajo local quedan el número del anuncio, las coordenadas y el recuento de anuncios por anfitrión; lo que se publica los deja fuera, como explica `docs/datos.md`.", ""]
    lineas += [f"- {t}, {r}: {', '.join(sorted(c))}." for (t, r), c in sorted(tecnicas.items())]
    lineas += ["", "Este paso no copia ningún valor de `licencia_nacional`, `licencia_exencion`, `licencia_vt` ni `licencia_otro`. Usa `licencia_exencion` solo para saber qué pisos "
               "declaran alquiler de temporada, como pide la regla del grupo firme."]
    return lineas


# ---------------------------------------------------------------------------
# 9. Comprobaciones que paran con ERROR
# ---------------------------------------------------------------------------

def comprobar(s, huellas_antes):
    """Aplica las comprobaciones de salida y devuelve los fallos."""
    fallos = []
    con_veredicto = {(n["tabla"], n["columna"]) for n in s["nulos_por_segmento"]}
    for tabla, columnas in s["columnas_con_vacios"].items():
        for c in columnas:
            if (tabla, c) not in con_veredicto:
                fallos.append(f"{tabla}.{c}: sin veredicto de reparto")
    for c in s["cruces"]:
        if c["sin_pareja_izquierda"] is None or c["sin_pareja_derecha"] is None:
            fallos.append(f"{c['izquierda']}: cruce sin recuento")
    if huellas_de_raw() != huellas_antes:
        fallos.append("data/raw/ ha cambiado durante la ejecución")
    escala = {(e["tabla"], e["columna"]) for e in s["escala"]}
    colas = {(e["tabla"], e["columna"]) for e in s["colas"]}
    for t in s["roles_de_magnitud"]:
        for c in t["columnas"]:
            if (t["tabla"], c["columna"]) not in escala or (t["tabla"], c["columna"]) not in colas:
                fallos.append(f"{t['tabla']}.{c['columna']}: magnitud sin escala o sin colas")
    if len(s["parametros"]) < 9:
        fallos.append("faltan parámetros en el JSON")
    return fallos


# ---------------------------------------------------------------------------
# 10. Ejecución
# ---------------------------------------------------------------------------

def sin_nan(valor):
    """Cambia por null lo que no se pudo calcular: un JSON no lleva NaN."""
    if isinstance(valor, dict):
        return {k: sin_nan(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [sin_nan(v) for v in valor]
    if isinstance(valor, float) and not np.isfinite(valor):
        return None
    return valor


def guardar(s):
    """Escribe el JSON y, de él, el Markdown."""
    limpio = sin_nan(s)
    SALIDA_JSON.write_text(json.dumps(limpio, ensure_ascii=False, indent=1, allow_nan=False, default=str), encoding="utf-8")
    SALIDA_MD.write_text(informe(limpio), encoding="utf-8")


def controles_de(L, cal_filas, rev_filas, b, oficial, base_m):
    """Mide los controles de la lectura de los datos y los compara con las cifras aprobadas, si están."""
    referencia = json.loads(REFERENCIA.read_text(encoding="utf-8")) if REFERENCIA.exists() else {}
    of = set(oficial.query('nivel == "barrio"')["clave"])
    con_otro = sorted(b.loc[~b["clave_directa"].isin(of) & b["clave_directa"].replace(EQUIV).isin(of), "barrio"])
    sin_precio = sorted(set(b.loc[~b["clave_directa"].replace(EQUIV).isin(of), "barrio"]) | set(b.loc[b["m2_total"].eq(0), "barrio"]))
    medido = {"anuncios_septiembre": len(L), "dias_calendario": cal_filas, "resenas": rev_filas, "estancia_vacia_septiembre": int(L["minimum_nights"].isna().sum()),
              "bathrooms_vacia_septiembre": bool(L["bathrooms"].isna().all()), "barrios_sin_precio_propio": sin_precio, "barrios_con_otro_nombre": con_otro,
              "anuncios_dentro_del_centro": int(L["dentro"].sum()), "base_antes_de_cp_007_a_009": base_m["pisos"], "barrios_del_grupo": len(base_m["grupo"]), "barrios_tras_temporada": len(base_m["firmes"])}
    return [{"nombre": k, "da": v, "esperado": referencia.get(k), "sale": (v == referencia[k]) if k in referencia else None} for k, v in medido.items()]


def principal():
    """Hace el diagnóstico de principio a fin."""
    antes = huellas_de_raw()
    s = {"etapa": ETAPA, "version_etapa": VERSION_ETAPA, "script": SCRIPT, "fecha_datos": FECHA_DATOS,
         "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"), "python": platform.python_version(), "pandas": pd.__version__,
         "con_diccionario": False, "plan_aprobado": {"por": "", "fecha": ""}, "avisos": []}
    s["entradas"] = [{"ruta": r, "sha256": h, "bytes": (CASO / r).stat().st_size, "filas": None, "columnas": None} for r, h in antes.items()]

    # 10.1 Al empezar: un diccionario parado detiene el trabajo; uno de otra fuente no se usa.
    dicc = json.loads(DICCIONARIO.read_text(encoding="utf-8")) if DICCIONARIO.exists() else None
    if dicc and dicc["resultado"]["estado"] in ("PARADO", "ERROR"):
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "El diccionario paró: calidad no empieza.", "artefactos": [], "siguiente": "repetir diccionario-datos"}
        guardar(s)
        return 0
    if dicc and {e["ruta"]: e["sha256"] for e in dicc["entradas"]} == antes:
        s["con_diccionario"] = True
    elif dicc:
        s["avisos"].append("El diccionario describe otra fuente: su huella no coincide, y no se toman sus cifras.")
        dicc = None
    else:
        s["avisos"].append("No hay diccionario del origen.")
    fichas = {t["tabla"]: t for t in dicc["tablas"]} if dicc else {}
    proteccion = json.loads(PROTECCION.read_text(encoding="utf-8")) if PROTECCION.exists() else None

    # 10.2 Lectura de todo.
    fotos, frec = {}, {}
    for clave, tabla in TABLA_FOTO.items():
        fotos[clave], bruta = leer_csv_entero(tabla)
        frec[tabla] = frecuencias_de(bruta)
    licencias, bruta_lic = leer_csv_entero(LICENCIAS)
    frec[LICENCIAS] = frecuencias_de(bruta_lic)
    b_cruda, bruta_b = leer_csv_entero(BARRIOS)
    frec[BARRIOS] = frecuencias_de(bruta_b)
    frec[CALENDARIO], cal, cal_mes, cal_vacios = leer_calendario()
    frec[RESENAS], rev, repetidas_rev = leer_resenas()
    libros = {n: leer_libro(n, (fichas.get(n, {}).get("lectura") or {}).get("posiciones")) for n in LIBROS}
    for n, t in libros.items():
        frec[n] = {c: t[c].map(lambda x: "" if x is None or pd.isna(x) else str(x)).value_counts(sort=False) for c in t.columns}
    oficial = oficial_de(libros)
    limite = leer_limite()
    poligonos = leer_poligonos()
    puntos = leer_puntos()

    # 10.3 Roles: los del diccionario; sin él, por el tipo y el nombre.
    def roles_de(tabla):
        """Devuelve el rol de cada columna de una tabla."""
        if tabla in fichas:
            return {c["columna"]: c["rol"] for c in fichas[tabla]["campos"]}
        return {c: ("fecha" if "date" in c or "review" in c and "number" not in c else "magnitud" if pd.to_numeric(f.index.astype("str").str.replace(r"[$,%]", "", regex=True), errors="coerce").notna().mean() > 0.9 else "categorica")
                for c, f in frec[tabla].items()}

    roles = {t: roles_de(t) for t in frec}
    filas = {t: int(next(iter(f.values())).sum()) for t, f in frec.items()}

    # 10.4 Un dato personal en claro para el trabajo (reglas §4); solo se cuenta, sin copiarlo.
    personales = [x for t in frec for x in buscar_personal(t, frec[t], roles[t])]
    s["datos_personales_en_claro"] = personales
    if personales:
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "Hay datos con forma de dato personal en claro: " + "; ".join(f"{x['tabla']}.{x['columna']}, {x['clase']}, {x['filas']} filas" for x in personales),
                          "artefactos": ["informes/calidad-datos.json", "informes/calidad-datos.md"], "siguiente": "avisar a la persona responsable (reglas §4)"}
        guardar(s)
        print(s["resultado"]["estado"], s["resultado"]["resumen"])
        return 0

    for e in s["entradas"]:
        for t, ruta in RUTAS.items():
            if e["ruta"] == f"data/raw/{ruta}":
                e.update(filas=filas[t], columnas=len(frec[t]))

    # 10.5 Tablas de trabajo y comprobaciones por columna.
    for clave, t in fotos.items():
        t["lado"] = np.where(shapely.contains_xy(limite, t["longitude"].to_numpy(), t["latitude"].to_numpy()), "dentro", "fuera")
        t["marca"] = t["source"].fillna("sin marca")
    dfs = {**{TABLA_FOTO[k]: v for k, v in fotos.items()}, LICENCIAS: licencias, BARRIOS: b_cruda, **libros}
    dimensiones = {**{TABLA_FOTO[k]: ["neighbourhood_group_cleansed", "room_type", "marca", "lado"] for k in fotos}, LICENCIAS: ["distrito"], BARRIOS: []}
    tipos, escala, colas, outliers, codigos, nombres, raras, reparto, por_fila, estructura = [], [], [], [], [], [], [], [], [], []
    magnitudes = []
    con_vacios = {}
    for tabla in frec:
        magn = []
        n = filas[tabla]
        normalizados = Counter(nombre_normalizado(c) for c in frec[tabla])
        for columna, f in frec[tabla].items():
            rol = roles[tabla].get(columna, "categorica")
            leido = next((c["tipo_leido"] for c in fichas.get(tabla, {}).get("campos", []) if c["columna"] == columna), "str")
            tipos.append(fila_de_tipos(tabla, columna, rol, f, leido))
            nombres.append({"tabla": tabla, "columna": columna, "normalizado": nombre_normalizado(columna),
                            "colision_con": nombre_normalizado(columna) if normalizados[nombre_normalizado(columna)] > 1 else ""})
            codigos += codigos_de(tabla, columna, rol, f, n)
            if rol == "magnitud":
                numeros = numeros_de(f.drop("", errors="ignore"))
                if numeros.empty:
                    s["avisos"].append(f"{tabla}.{columna}: magnitud sin ningún valor")
                    magn.append(columna)
                    escala.append({"tabla": tabla, "columna": columna, "cifras": {}, "salto": False, "factor": None, "factor_uniforme": None})
                    colas.append({"tabla": tabla, "columna": columna, "bajos": [], "altos": [], "mayor_salto": None})
                    continue
                magn.append(columna)
                escala.append(escala_de(tabla, columna, numeros))
                colas.append(colas_de(tabla, columna, numeros))
                outliers.append(atipicos_de(tabla, columna, numeros))
        magnitudes.append({"tabla": tabla, "columnas": [{"columna": c} for c in magn]})
        for c in fichas.get(tabla, {}).get("campos", []):
            raras += [{"tabla": tabla, "columna": c["columna"], "categoria": x["valor"], "filas": x["frecuencia"], "pct": p(x["frecuencia"], n), "de_diccionario": True} for x in c.get("categorias_raras", [])]
        if tabla in dfs:
            t = dfs[tabla]
            originales = [c for c in t.columns if c not in ("lado", "marca")]
            vacias = [c for c in originales if t[c].isna().all()]
            estructura.append({"tabla": tabla, "vacias": vacias, "casi_vacias": [c for c in originales if 0.9 < t[c].isna().mean() < 1],
                               "constantes": [c for c in originales if t[c].nunique() == 1]})
            con_nulos = [c for c in originales if t[c].isna().any()]
            con_vacios[tabla] = con_nulos
            for c in con_nulos:
                reparto.append(reparto_de_nulos(tabla, c, t, dimensiones.get(tabla, [])))
            por_fila.append(vacios_por_fila(tabla, t[originales]))
    con_nulos_cal = [c for c in ("minimum_nights", "maximum_nights", "available") if frec[CALENDARIO][c].get("", 0)]
    con_vacios[CALENDARIO] = con_nulos_cal
    for c in con_nulos_cal:
        total = int(frec[CALENDARIO][c].get("", 0))
        global_pct = p(total, filas[CALENDARIO])
        meses = [{"dimension": "mes", "segmento": m, "pct": p(cal_mes[(c, m)], cal_mes[("filas", m)]), "filas": cal_mes[("filas", m)]}
                 for (x, m) in cal_mes if x == c and cal_mes[("filas", m)] >= SEGMENTO_MIN and p(cal_mes[(c, m)], cal_mes[("filas", m)]) >= CONCENTRACION * global_pct]
        reparto.append({"tabla": CALENDARIO, "columna": c, "global_pct": global_pct, "dimensiones": ["mes"], "veredicto": "concentrados" if meses else "repartidos", "segmentos": meses})
    por_fila.append({"tabla": CALENDARIO, "con_todas": {str(k): int(v) for k, v in sorted(cal_vacios.items())}, "sin_casi_vacias": {str(k): int(v) for k, v in sorted(cal_vacios.items())}, "excluidas": []})

    # Si un código cae en las mismas filas en dos columnas, es una ausencia de la fila.
    for clave, t in fotos.items():
        tabla = TABLA_FOTO[clave]
        marcas = {}
        for c in [c for c in t.columns if t[c].isna().any() and 0 < t[c].isna().mean() < 1]:
            marcas.setdefault(hashlib.sha256(t[c].isna().to_numpy().tobytes()).hexdigest(), []).append(c)
        for grupo in marcas.values():
            if len(grupo) > 1:
                codigos.append({"tabla": tabla, "columna": grupo[0], "codigo": "vacío", "tipo": "vacío en las mismas filas", "filas": int(t[grupo[0]].isna().sum()),
                                "pct_filas": p(int(t[grupo[0]].isna().sum()), len(t)), "documentado": False, "coincide_con": "", "mismas_filas_que": grupo[1:]})

    # 10.6 Duplicados y claves.
    duplicados = []
    for clave, t in fotos.items():
        base = t[[c for c in t.columns if c not in ("lado", "marca")]]
        fila = duplicados_de(TABLA_FOTO[clave], base, ["id"], ["id"])
        fila["logicos"] = int(base.duplicated(["latitude", "longitude", "property_type", "accommodates", "bedrooms"]).sum())
        fila["nota_logicos"] = "misma coordenada, tipo y tamaño con distinto número; un mismo piso puede tener varios anuncios y no se puede saber (reglas §1)"
        duplicados.append(fila)
    duplicados.append(duplicados_de(LICENCIAS, licencias, [], []))
    duplicados.append(duplicados_de(BARRIOS, b_cruda, ["neighbourhood"], []))
    for n, t in libros.items():
        duplicados.append(duplicados_de(n, t, [t.columns[0]], []))
    duplicados.append({"tabla": CALENDARIO, "exactos": fichas.get(CALENDARIO, {}).get("repetidas_por_clave"), "exactos_sin_identificadores": None, "identificadores_quitados": [],
                       "clave": ["listing_id", "date"], "clave_unica": fichas.get(CALENDARIO, {}).get("clave_unica"), "por_clave": fichas.get(CALENDARIO, {}).get("repetidas_por_clave"), "casi_duplicados": None, "logicos": None})
    duplicados.append({"tabla": RESENAS, "exactos": repetidas_rev, "exactos_sin_identificadores": repetidas_rev, "identificadores_quitados": [], "clave": ["listing_id", "date"],
                       "clave_unica": repetidas_rev == 0, "por_clave": repetidas_rev, "casi_duplicados": None, "logicos": None})

    # 10.7 Fechas.
    fechas = []
    hoy = s["fecha_ejecucion"][:10]
    for tabla in frec:
        for columna, f in frec[tabla].items():
            if roles[tabla].get(columna) != "fecha":
                continue
            llenos = f.drop("", errors="ignore")
            if llenos.empty:
                fechas.append({"tabla": tabla, "columna": columna, "minimo": None, "maximo": None, "invalidas": 0, "futuras": None, "convencion": None, "demostrada": None})
                continue
            indice = pd.Series(llenos.index.astype("str"), index=llenos.index)
            validas = pd.to_datetime(indice, format="%Y-%m-%d", errors="coerce").notna()
            fechas.append({"tabla": tabla, "columna": columna, "minimo": indice[validas].min(), "maximo": indice[validas].max(), "invalidas": int(llenos[~validas.to_numpy()].sum()),
                           "futuras": int(llenos[indice.gt(hoy).to_numpy()].sum()) if columna not in ("date", "price_quote_checkin_date", "price_quote_checkout_date") or tabla == RESENAS else None,
                           "convencion": "anio_mes_dia", "demostrada": True})
    L_rev = fotos["sep"]
    capturas = {clave: (t["last_scraped"].min(), t["last_scraped"].max()) for clave, t in fotos.items()}
    notas_fechas = [f"Foto {TABLA_FOTO[k]}: nominal {FOTOS[k]}, capturada de {v[0]} a {v[1]}." for k, v in capturas.items()]
    notas_fechas.append(f"Calendario: de {cal['primera'].min()} a {cal['ultima'].max()}, con {int(cal['dias'].min())} a {int(cal['dias'].max())} días por anuncio; "
                        f"{int(((pd.to_datetime(cal['ultima']) - pd.to_datetime(cal['primera'])).dt.days + 1).ne(cal['dias']).sum())} anuncios con huecos.")
    notas_fechas.append(f"Reseñas posteriores a la fecha de referencia ({FECHA_DATOS}): {int(frec[RESENAS]['date'][pd.Index(frec[RESENAS]['date'].index.astype('str')).to_series().gt(FECHA_DATOS).to_numpy()].sum())} filas.")
    notas_fechas.append(f"Última reseña posterior a la captura del propio anuncio: {int(L_rev['last_review'].fillna('').gt(L_rev['last_scraped']).sum())} anuncios.")
    notas_fechas.append("Las fechas son siempre año-mes-día: no hay día y mes intercambiables.")
    notas_fechas.append(f"Fechas futuras: frente a la fecha de ejecución, {hoy}, porque el caso no da otro horizonte. El calendario y las cotizaciones miran al futuro por definición y no se cuentan.")

    # 10.8 Tabla de trabajo, reglas, cruces.
    b_medida = tabla_de_barrios(b_cruda, oficial)
    L = preparar_trabajo(fotos, cal, limite, b_medida)
    documentadas, estancia_regla = reglas_documentadas(L, fotos, b_cruda, cal)
    candidatas = reglas_candidatas(L, rev, cal)
    cruces = cruces_de(fotos, cal, rev, b_medida, oficial, licencias, poligonos, L)
    resenas_por_anuncio = L.set_index("id")["number_of_reviews"]
    disponibles = L.set_index("id")["availability_365"]
    libres_calendario = cal["libres"].reindex(disponibles.index)
    reseñas_cuadran = int(rev["resenas"].reindex(resenas_por_anuncio.index).fillna(0).eq(resenas_por_anuncio).sum())
    notas_cruce = {"resenas_que_cuadran_con_su_contador": reseñas_cuadran, "anuncios": len(L),
                   "dias_libres_que_cuadran_con_el_calendario": int(libres_calendario.eq(disponibles).sum()),
                   "anuncios_fuera_del_poligono_de_su_barrio": punto_en_su_barrio(L, poligonos)}

    # 10.9 Medición en la base.
    base_m = medir(L)

    def medidor(tabla, excluir=None, camas_vacias=False):
        """Mide una versión de la base y la compara con la de referencia."""
        return comparar(base_m, medir(tabla, excluir, camas_vacias))

    vacias_sep = next(e for e in estructura if e["tabla"] == TABLA_FOTO["sep"])["vacias"]
    dup_sep = next(d for d in duplicados if d["tabla"] == TABLA_FOTO["sep"])["exactos_sin_identificadores"]
    geom = fichas and next((g for g in dicc["geometrias"] if g["fichero"].endswith("neighbourhoods.geojson")), None)
    tabla_d = asuntos_de(L, fotos, b_medida, oficial, licencias, puntos, repetidas_rev, base_m, {c: True for c in vacias_sep}, medidor, dup_sep,
                         notas_cruce["anuncios_fuera_del_poligono_de_su_barrio"], geom["invalidos"] if geom else None)

    # 10.10 Problemas y pendientes.
    problemas = []
    for f in tabla_d:
        resultado = f"{f['filas_afectadas']} filas" + (f", {f['en_base']} en la base" if f["en_base"] is not None else "")
        problemas.append({"id": f["id"], "bloque": f["bloque"], "tabla": f["tabla"], "columna": f["columna"], "resultado": resultado, "filas_afectadas": f["filas_afectadas"],
                          "pct_filas": None, "observacion": f["nota"], "posible_accion": ("; ".join(f["opciones"]) if not f["decision"] else ""),
                          "decision_de_negocio": not f["decision"]})
    pendientes = [{"id": f["id"].replace("C-", "P-"), "tabla": f["tabla"], "columna": f["columna"], "pregunta": f"¿Qué se hace con {f['clave']}?", "opciones": f["opciones"]}
                  for f in tabla_d if not f["decision"]]
    pendientes += [{"id": c["id"], "tabla": c["tabla"], "columna": ", ".join(c["columnas"]), "pregunta": f"¿Se aprueba la regla: {c['regla']}?", "opciones": ["se aprueba", "no se aprueba"]}
                   for c in candidatas if not c["aprobada"]]

    inspeccion = []
    for tabla in frec:
        ficha = fichas.get(tabla, {})
        inspeccion.append({"tabla": tabla, "filas": filas[tabla], "columnas": len(frec[tabla]), "clave": ficha.get("clave", []), "clave_unica": ficha.get("clave_unica"),
                           "que_es_una_fila": ficha.get("que_es_una_fila", "sin diccionario")})
    instrucciones = [{"tabla": t["tabla"], **i} for t in (dicc["tablas"] if dicc else []) for i in t.get("instrucciones_en_texto", [])]
    es_doble = float(np.mean([bool(re.match(r"^\d{2,3}\. ", str(v))) for v in libros[LIBRO_PRECIO].iloc[:, 0]]) * 100)
    parametros = [
        {"nombre": "límite del rango intercuartílico", "valor": LIM_IQR, "origen": "por defecto"},
        {"nombre": "límite del z robusto", "valor": LIM_Z, "origen": "por defecto"},
        {"nombre": "segmento mínimo para el reparto de nulos", "valor": SEGMENTO_MIN, "origen": "por defecto"},
        {"nombre": "concentración de nulos en un segmento", "valor": CONCENTRACION, "origen": "por defecto"},
        {"nombre": "categoría rara", "valor": "menos del 2,5 % de las filas o menos de cinco apariciones", "origen": "por defecto, de diccionario-datos"},
        {"nombre": "código de ausencia numérico candidato", "valor": COD_PCT, "origen": "por defecto"},
        {"nombre": "colas de cada magnitud", "valor": COLAS, "origen": "por defecto"},
        {"nombre": "fecha de Excel candidata", "valor": list(EXCEL), "origen": "por defecto"},
        {"nombre": "horizonte de fechas futuras", "valor": hoy, "origen": "por defecto: la fecha de ejecución"},
        {"nombre": "semilla y remuestreos", "valor": [SEMILLA, REMUESTREOS], "origen": "los del reconocimiento"},
        {"nombre": "mínimo por grupo, variantes y mayoría", "valor": [MIN_GRUPO, list(MIN_VARIANTE), MAYORIA], "origen": "reglas §3"},
    ]
    s.update(
        controles=controles_de(L, filas[CALENDARIO], filas[RESENAS], b_medida, oficial, base_m), inspeccion=inspeccion, geometrias=dicc["geometrias"] if dicc else [],
        estructura=estructura, forma_de_la_tabla=f"la primera columna de los libros lleva código y nombre juntos en el {es_doble:.1f} % de sus valores; amenities y price_quote_raw guardan JSON dentro de una celda.",
        problemas=problemas, nulos_por_segmento=reparto, codigos_de_ausencia=codigos, duplicados=duplicados, escala=escala, colas=colas, tipos=tipos, vacios_por_fila=por_fila,
        nombres=nombres, categorias_raras=raras, reglas_candidatas=candidatas, reglas_documentadas=documentadas, estancia_regla=estancia_regla, parametros=parametros,
        outliers=outliers, fechas=fechas, fechas_notas=notas_fechas, cruces=cruces, cruces_magnitudes=notas_cruce, riesgos_modelo=[], instrucciones_en_texto=instrucciones,
        datos_personales=[{"tabla": t, "columna": c} for t in roles for c, r in roles[t].items() if r == "dato_personal"], roles_de_magnitud=magnitudes, columnas_con_vacios=con_vacios,
        dimensiones_de_nulos=sorted({d for v in dimensiones.values() for d in v} | {"mes"}), datos_personales_texto=texto_datos_personales(proteccion),
        medicion={"base": base_m, "criterio": "dos grupos se distinguen si el intervalo del 95 % de la diferencia de sus medianas no cruza el cero; 2.000 remuestreos, semilla 63 más el nombre del grupo"},
        tabla_de_decisiones=tabla_d, pendientes=pendientes,
        no_aplicado=[{"control": "riesgos para un modelo (comprobaciones §2)", "motivo": "el caso no entrena ningún modelo"},
                     {"control": "correlación entre variables", "motivo": "ninguna decisión de esta fase depende de ella; sí se comprobó la columna calculada de ingreso"},
                     {"control": "casi duplicados por clave", "motivo": "id es único en las cuatro fotos: no hay dos filas con la misma clave"},
                     {"control": "duplicados exactos del calendario y las reseñas sin clave propia", "motivo": "sus filas son solo la clave y sus atributos; se cuentan por clave"},
                     {"control": "reparto de vacíos en las reseñas", "motivo": "no tiene vacíos"}])

    # 10.11 Se comprueba antes de dar por bueno.
    fallos = comprobar(s, antes)
    decisiones_abiertas = sum(1 for f in tabla_d if not f["decision"])
    cambian = [f["id"] for f in tabla_d if f["medicion"] and (f["medicion"]["cambia_grupo"] or f["medicion"]["cambia_firmes"] or f["medicion"]["cambia_tipo"])]
    no_salen = [c["nombre"] for c in s["controles"] if c["sale"] is False]
    s["resultado"] = {
        "estado": "ERROR" if fallos else "AVISO", "riesgo": "alto" if fallos else "medio",
        "resumen": (f"{len(tabla_d)} asuntos con criterio, {decisiones_abiertas} sin decisión; {len(cambian)} de los medidos cambian el grupo, los firmes o el tipo ({', '.join(cambian) or 'ninguno'}). "
                    "El plan se escribió antes de calcular." + (f" Controles que no salen: {', '.join(no_salen)}." if no_salen else "") + (" Fallos: " + "; ".join(fallos) if fallos else "")),
        "artefactos": ["informes/calidad-datos.json", "informes/calidad-datos.md"], "siguiente": "la persona resuelve la tabla de decisiones; después, correccion-datos"}
    guardar(s)
    print(s["resultado"]["estado"], s["resultado"]["resumen"])
    return 1 if fallos else 0


def ejecutar():
    """Lanza el diagnóstico y, si algo falla, deja el JSON con estado ERROR antes de avisar."""
    try:
        return principal()
    except Exception as error:
        SALIDA_JSON.write_text(json.dumps({"etapa": ETAPA, "script": SCRIPT, "fecha_datos": FECHA_DATOS, "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
                                           "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": f"Fallo técnico: {error!r}", "artefactos": [], "siguiente": "arreglar el fallo"}},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(ejecutar())
