"""Corrección de los datos del caso: aplica CP-001 a CP-014 y deja una tabla corregida por tabla en data/processed/.

Ninguna fila desaparece de las tablas corregidas: lo que sale de la base se marca. Solo salen los puntos de interés fuera
de Madrid (CP-011). Escribe informes/correccion-datos.json y, generado de él, informes/correccion-datos.md, y añade al
registro de transformaciones las fichas que falten.

Se lanza después de scripts/calidad_datos.py, cuyo JSON comprueba.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/correccion_datos.py
"""
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd
import shapely
from shapely.geometry import shape

import calidad_datos as cd
import reglas_caso as rc

# ---------------------------------------------------------------------------
# 1. Configuración
# ---------------------------------------------------------------------------

ETAPA = "correccion-datos"
VERSION = "1.0"
SCRIPT = "scripts/correccion_datos.py"
PRECIO_VALIDO = re.compile(r"^\$\d{1,3}(,\d{3})*\.\d{2}$")
MAGNITUDES = ["estimated_occupancy_l365d", "estimated_revenue_l365d", "number_of_reviews", "accommodates"]
PARAMETROS = [{"nombre": "forma de los nombres de columna", "valor": "los del origen, ya en minúsculas; los libros, con nombres nuevos", "origen": "por defecto"},
              {"nombre": "etiqueta del vacío en una categórica", "valor": "no se usa: ningún vacío se etiqueta", "origen": "reglas §2"},
              {"nombre": "marca de lo imputado", "valor": "no se usa: no se imputa nada", "origen": "reglas §2"},
              {"nombre": "si los datos van a un modelo", "valor": "no van", "origen": "ficha §6"},
              {"nombre": "formato de la tabla corregida", "valor": "Parquet", "origen": "por defecto"}]
# Lo que leen las tres preguntas y las cinco pruebas de la foto de septiembre: sin una de ellas no se puede contestar.
COLUMNAS_PREGUNTAS = ["price", "banos", "bedrooms", "beds", "accommodates", "room_type", "property_type", "neighbourhood_cleansed", "neighbourhood_group_cleansed", "latitude", "longitude", "minimum_nights", "availability_365",
                      "estimated_occupancy_l365d", "number_of_reviews_ltm", "calculated_host_listings_count", "price_quote_checkin_date"]
CUESTIONES = cd.CASO / "docs" / "criterios_de_datos.md"


# ---------------------------------------------------------------------------
# 2. Correcciones
# ---------------------------------------------------------------------------

def censar_precio(serie):
    """Cuenta los formatos del precio y devuelve el censo y cuántos no encajan en el formato demostrado."""
    llenos = serie.dropna().astype("str")
    formas = llenos.str.replace(r"\d", "9", regex=True).value_counts()
    return {k: int(v) for k, v in formas.items()}, int((~llenos.str.match(PRECIO_VALIDO)).sum())


def suma_exacta(serie):
    """Suma el precio en texto con Decimal, por un camino distinto al de la conversión."""
    return float(sum((Decimal(v.replace("$", "").replace(",", "")) for v in serie.dropna().astype("str")), Decimal(0)))


def corregir_foto(ruta):
    """Corrige una foto: precio a número, baños del texto, marcas de calidad, captura anterior y columnas vacías."""
    bruta = pd.read_csv(ruta, low_memory=False, dtype={"price": "object"})
    df = bruta.copy()
    censo, raros = censar_precio(df["price"]) if df["price"].notna().any() else ({}, 0)
    df["price"] = cd.precio_de_texto(df["price"].astype("object").where(df["price"].notna())) if censo else df["price"].astype("float64")
    df["banos"] = df["bathrooms_text"].map(cd.banos_de_texto)
    df = pd.concat([df, rc.marcas_de_calidad(df)], axis=1)
    df["marca_estancia_larga"] = df["minimum_nights"].gt(365).fillna(False).astype("bool")
    df["captura_anterior"] = df["source"].eq("previous scrape").fillna(False).astype("bool")
    vacias = [c for c in df.columns if df[c].isna().all()]
    return bruta, df.drop(columns=vacias), censo, raros, vacias


def corregir_licencias(lic, barrios, dec):
    """Normaliza la escritura de las licencias con el maestro de distritos, sin quitar ninguna fila (CP-012)."""
    df = lic.copy()
    maestro = {cd.sin_guiones(d): d for d in barrios["distrito"].unique()}
    sin_prefijo = df["distrito"].str.replace(dec["prefijo_distrito_licencias"], "", regex=False)
    df["distrito"] = sin_prefijo.map(cd.sin_guiones).map(maestro).fillna(sin_prefijo)
    df["planta"] = df["planta"].str.upper().str.strip().str.replace(r"\s+", " ", regex=True)
    return df, int((~sin_prefijo.map(cd.sin_guiones).isin(maestro)).sum())


def corregir_barrios(crudos, dec):
    """Deja el maestro de barrios con la clave con la que casa en los libros oficiales (CP-004)."""
    df = crudos.rename(columns={"neighbourhood": "barrio", "neighbourhood_group": "distrito"}).copy()
    directa = df["barrio"].map(cd.sin_tildes)
    df["clave_oficial"] = directa.replace(dec["equivalencias_barrio"])
    df["clave_distrito"] = df["distrito"].map(cd.sin_guiones)
    df["toma_precio_de_distrito"] = df["barrio"].isin(dec["toman_el_precio_de_su_distrito"])
    return df, int(directa.ne(df["clave_oficial"]).sum())


def corregir_oficial(libros):
    """Junta precio, superficie y ventas por código y pasa a vacío el 0 que la nota (2) de los libros usa cuando no hay dato."""
    df = cd.oficial_de(libros).copy()
    df["nombre"] = df["nombre"].str.replace(r"\s+", " ", regex=True).str.strip()
    df["clave_distrito"] = df["nombre"].map(cd.sin_guiones)
    ceros = {c: int(df[c].eq(0).sum()) for c in ("m2_total", "sup_total")}
    for c in ceros:
        df[c] = df[c].where(df[c].gt(0))
    return df, ceros


def corregir_puntos(dec):
    """Quita los puntos fuera de Madrid (CP-011) y deja el código de barrio como texto."""
    p = cd.leer_puntos()
    m = dec["marco_de_madrid"]
    dentro = p["x"].between(*m["x"]) & p["y"].between(*m["y"])
    p["cod_barrio"] = p["cod_barrio"].map(lambda v: None if v is None else str(v))
    return p.loc[dentro].reset_index(drop=True), len(p), int((~dentro).sum())


def corregir_poligonos():
    """Repara el polígono inválido (CP-014) y deja cada barrio como WKB, en EPSG:4326."""
    datos = json.loads((cd.EXT / "neighbourhoods.geojson").read_text(encoding="utf-8"))
    filas, reparados = [], []
    for f in datos["features"]:
        forma = shape(f["geometry"])
        if not forma.is_valid:
            reparados.append({"barrio": f["properties"]["neighbourhood"], "area_antes": forma.area, "tipo_antes": forma.geom_type})
            forma = shapely.make_valid(forma)
            reparados[-1].update(area_despues=forma.area, tipo_despues=forma.geom_type)
        filas.append({"barrio": f["properties"]["neighbourhood"], "distrito": f["properties"]["neighbourhood_group"], "geometria_wkb": shapely.to_wkb(forma)})
    return pd.DataFrame(filas), reparados


def leer_calendario():
    """Lee el calendario con sus tipos: fecha con su patrón, disponibilidad a booleano y noches a entero."""
    df = pd.read_csv(cd.RAW / cd.RUTAS[cd.CALENDARIO], dtype={"listing_id": "int64", "date": "object", "available": "object", "minimum_nights": "Int32", "maximum_nights": "Int32"})
    libres = int(df["available"].eq("t").sum())
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df["available"] = df["available"].map({"t": True, "f": False}).astype("boolean")
    return df, libres


def leer_resenas():
    """Lee las reseñas con la fecha en su tipo."""
    df = pd.read_csv(cd.RAW / cd.RUTAS[cd.RESENAS], dtype={"listing_id": "int64", "date": "object"})
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    return df


# ---------------------------------------------------------------------------
# 3. Comprobaciones: cada una mide sobre las tablas y puede dar que no pasa
# ---------------------------------------------------------------------------

def veredicto(faltas, bien):
    """Da el resultado de una comprobación: lo medido si pasa y la lista de fallos si no."""
    return {"pasa": not faltas, "texto": "; ".join(faltas) if faltas else bien}


def medir_completitud(antes, despues, puntos_fuera):
    """Comprueba que la foto conserva sus anuncios."""
    faltas = [] if antes == despues else [f"{antes} anuncios antes y {despues} después"]
    return veredicto(faltas, f"{despues} anuncios en septiembre antes y después; solo salen {puntos_fuera} puntos de interés")


def medir_consistencia(fotos, cal, res, barrios, sin_maestro):
    """Comprueba tipos y mapeos cerrados en las tablas corregidas, no en lo que se quiso hacer con ellas."""
    faltas = [f"precio de {k} sin ser número" for k, d in fotos.items() if "price" in d and not pd.api.types.is_numeric_dtype(d["price"])]
    faltas += [f"baños de {k} sin ser número" for k, d in fotos.items() if "banos" in d and not pd.api.types.is_numeric_dtype(d["banos"])]
    for nombre, tabla in (("calendario", cal), ("reseñas", res)):
        if not pd.api.types.is_datetime64_any_dtype(tabla["date"]) or tabla["date"].isna().any():
            faltas.append(f"fechas de {nombre} sin su tipo")
    disponibles = int(cal["available"].isna().sum())
    if disponibles:
        faltas.append(f"{disponibles} días del calendario fuera del mapeo t y f")
    if sin_maestro:
        faltas.append(f"{sin_maestro} licencias con un distrito que no está en el maestro")
    sin_clave = int(barrios["clave_oficial"].isna().sum())
    if sin_clave:
        faltas.append(f"{sin_clave} barrios sin clave oficial")
    return veredicto(faltas, f"precio numérico en {sum('price' in d for d in fotos.values())} fotos, fechas en su tipo, disponibilidad solo t y f, todos los distritos en el maestro y todos los barrios con clave")


def medir_utilidad(sep):
    """Comprueba que siguen, y con datos, las columnas que leen las tres preguntas y las cinco pruebas."""
    faltas = [f"falta {c}" for c in COLUMNAS_PREGUNTAS if c not in sep]
    faltas += [f"{c} viene vacía" for c in COLUMNAS_PREGUNTAS if c in sep and sep[c].isna().all()]
    return veredicto(faltas, f"las {len(COLUMNAS_PREGUNTAS)} columnas de las preguntas siguen y traen datos")


def medir_datos_personales(tablas):
    """Busca en las tablas corregidas datos con forma personal y columnas suprimidas de esa tabla que vuelvan. Solo cuenta, nunca copia un valor."""
    faltas = []
    for nombre, df, roles, suprimidas in tablas:
        faltas += [f"{nombre}.{c} es una columna suprimida" for c in suprimidas if c in df]
        frec = {c: df[c].dropna().astype("str").value_counts(sort=False) for c, rol in roles.items() if rol in ("texto_libre", "categorica") and c in df}
        faltas += [f"{x['tabla']}.{x['columna']}: {x['filas']} filas con forma de {x['clase']}" for x in cd.buscar_personal(nombre, frec, roles)]
    return veredicto(faltas, f"{len(tablas)} tablas corregidas sin datos con forma personal, y ninguna de sus {sum(len(t[3]) for t in tablas)} columnas suprimidas ha vuelto")


def contar_cuestiones(texto):
    """Lee las cuestiones de su tabla, para no llevar su número escrito."""
    return re.findall(r"^\| (CP-\d{3})", texto, flags=re.M)


# ---------------------------------------------------------------------------
# 4. Fichas del registro
# ---------------------------------------------------------------------------

def fichas_de(m):
    """Monta las fichas de la corrección con las cifras de esta ejecución."""
    deshacer = "quitar la regla de scripts/correccion_datos.py y volver a lanzarlo; data/raw/ no cambió."
    sep = "listings_2026-09-17"
    base = dict(deshacer=deshacer)
    return [
        {**base, "clave": "correccion-cp-001", "titulo": "CP-001 precio vacío y precio a número", "tabla": f"las fotos con precio, `price`", "estaba": f"texto con símbolo y comas; en septiembre, {m['precio_vacio']} vacíos.",
         "problema": "el precio no se podía usar como número.", "decision": "CP-001: el vacío sigue vacío. El símbolo es formato (reglas §2).", "hecho": "se censaron los formatos y se quitó el símbolo y las comas.",
         "codigo": "df['price'] = pd.to_numeric(df['price'].str.replace(r'[$,]', '', regex=True))", "comprobacion": f"formatos de septiembre {m['censo_sep']}; {m['precio_raros']} valores fuera del formato; suma por Decimal y por pandas iguales al céntimo.",
         "quedo": f"número, con {m['precio_vacio']} vacíos en septiembre."},
        {**base, "clave": "correccion-cp-002", "titulo": "CP-002 anuncios de captura anterior", "tabla": f"{sep}, `source`", "estaba": f"{m['captura']} anuncios con la marca de captura anterior.", "problema": "podían ser anuncios viejos.",
         "decision": "CP-002: se quedan.", "hecho": "se deja una marca, sin quitar ninguno.", "codigo": "df['captura_anterior'] = df['source'].eq('previous scrape')", "comprobacion": f"{m['captura']} marcados en septiembre.", "quedo": "columna `captura_anterior`."},
        {**base, "clave": "correccion-cp-003", "titulo": "CP-003 Aeropuerto toma el precio de su distrito", "tabla": "barrios, `toma_precio_de_distrito`", "estaba": "el libro le pone 0.", "problema": "no tenía precio oficial.",
         "decision": "CP-003 y reglas §2: precio de su distrito, igual que San Andrés y Ambroz.", "hecho": "se marca en el maestro; el precio se resuelve en la transformación.", "codigo": "df['toma_precio_de_distrito'] = df['barrio'].isin(['San Andrés', 'Ambroz', 'Aeropuerto'])",
         "comprobacion": f"{m['barrios_distrito']} barrios marcados.", "quedo": "los tres barrios marcados."},
        {**base, "clave": "correccion-cp-004", "titulo": "CP-004 siete nombres de barrio", "tabla": "barrios, `clave_oficial`", "estaba": "siete barrios con otra escritura en el libro.", "problema": "sin casar quedaban sin precio.", "decision": "CP-004: se aprueban las siete.",
         "hecho": "mapeo cerrado en scripts/decisiones_correccion.json.", "codigo": "df['clave_oficial'] = directa.replace(dec['equivalencias_barrio'])", "comprobacion": f"{m['equivalencias']} barrios cambian de clave.", "quedo": "cada barrio con su clave oficial."},
        {**base, "clave": "correccion-cp-005", "titulo": "CP-005 Casco Histórico de Vallecas, sin cambios", "tabla": "barrios", "estaba": "precio de su barrio.", "problema": "Airbnb junta en él lo que el Ayuntamiento separa.", "decision": "CP-005: precio del barrio, como riesgo.",
         "hecho": "no se cambia nada.", "codigo": "# sin código", "comprobacion": "cierre sin cambio.", "quedo": "como estaba."},
        {**base, "clave": "correccion-cp-006", "titulo": "CP-006 camas vacías, sin relleno", "tabla": f"{sep}, `beds`", "estaba": f"{m['camas_vacias']} vacías en septiembre.", "problema": "no se sabe si pasan el tope.", "decision": "CP-006: no pasan el tope.", "hecho": "se dejan vacías; la marca la pone la transformación.",
         "codigo": "# sin cambio en la corrección", "comprobacion": f"{m['camas_vacias']} vacías antes y después.", "quedo": "vacías."},
        {**base, "clave": "correccion-cp-007", "titulo": "CP-007 cero baños", "tabla": f"{sep}, `banos`, `marca_cero_banos`", "estaba": f"{m['cero_banos']} anuncios con cero baños.", "problema": "dudosos en un piso.", "decision": "CP-007: salen de la base de decisión; la fila se queda.",
         "hecho": "los baños se leen del texto (reglas §2, medio baño 0,5) y se marca el cero.", "codigo": "df['banos'] = df['bathrooms_text'].map(cd.banos_de_texto)\ndf['marca_cero_banos'] = df['banos'].eq(0)", "comprobacion": f"{m['banos_vacios']} vacíos en `banos`, los mismos que en el texto; {m['medio_bano']} con medio baño.",
         "quedo": "columna `banos` y su marca."},
        {**base, "clave": "correccion-cp-008", "titulo": "CP-008 tipo sin vivienda entera", "tabla": f"{sep}, `marca_no_vivienda`", "estaba": f"{m['no_vivienda']} pisos de un tipo que no empieza por Entire.", "problema": "contradicen ser piso.", "decision": "CP-008: salen de la base de decisión; la fila se queda.",
         "hecho": "se marcan.", "codigo": "piso & ~df['property_type'].str.startswith('Entire')", "comprobacion": f"{m['no_vivienda']} marcados.", "quedo": "columna `marca_no_vivienda`."},
        {**base, "clave": "correccion-cp-009", "titulo": "CP-009 tamaños incoherentes", "tabla": f"{sep}, `marca_tamano_incoherente`", "estaba": f"{m['incoherente']} anuncios con más camas o habitaciones que huéspedes.", "problema": "tamaño dudoso.", "decision": "CP-009: salen de la base de decisión; la fila se queda.",
         "hecho": "se marcan.", "codigo": "df['beds'].gt(df['accommodates']) | df['bedrooms'].gt(df['accommodates'])", "comprobacion": f"{m['incoherente']} marcados.", "quedo": "columna `marca_tamano_incoherente`."},
        {**base, "clave": "correccion-cp-010", "titulo": "CP-010 estancias de más de 365 noches", "tabla": f"{sep}, `marca_estancia_larga`", "estaba": f"{m['estancia_larga']} anuncios publicados con más de 365 noches.", "problema": "no son turísticos.", "decision": "CP-010: salen por el filtro de estancia, sin otra regla.", "hecho": "solo una marca informativa.",
         "codigo": "df['marca_estancia_larga'] = df['minimum_nights'].gt(365)", "comprobacion": f"{m['estancia_larga']} marcados.", "quedo": "marca informativa."},
        {**base, "clave": "correccion-cp-011", "titulo": "CP-011 puntos fuera de Madrid", "tabla": "puntos de interés", "estaba": f"{m['puntos_antes']} puntos.", "problema": "coordenadas fuera del marco de la ciudad.", "decision": "CP-011: salen. Es la única salida de filas de la corrección.", "hecho": "se quitan por el marco del fichero de decisiones.",
         "codigo": "p.loc[p['x'].between(*m['x']) & p['y'].between(*m['y'])]", "comprobacion": f"salen {m['puntos_fuera']}; no entran en la rentabilidad, de modo que no cambian ninguna respuesta.", "quedo": f"{m['puntos_antes'] - m['puntos_fuera']} puntos."},
        {**base, "clave": "correccion-cp-012", "titulo": "CP-012 escritura de las licencias", "tabla": "licencias, `distrito`, `planta`", "estaba": f"distrito en {m['distritos_antes']} formas y planta en {m['plantas_antes']}.", "problema": "el recuento por barrio y distrito se partía.", "decision": "CP-012: se normaliza.",
         "hecho": "el distrito se lleva a su nombre del maestro; la planta, a mayúsculas sin espacios de sobra.", "codigo": "sin_prefijo.map(cd.sin_guiones).map(maestro)\ndf['planta'].str.upper().str.strip()", "comprobacion": f"distrito en {m['distritos_despues']} formas y planta en {m['plantas_despues']}; {m['distritos_sin_maestro']} sin maestro; {m['licencias']} filas antes y después.",
         "quedo": "filas iguales. Las plantas escritas como texto libre siguen como están."},
        {**base, "clave": "correccion-cp-013", "titulo": "CP-013 columnas vacías enteras", "tabla": "las cuatro fotos", "estaba": f"septiembre traía {m['vacias_sep']} columnas enteras vacías.", "problema": "no traen nada.", "decision": "CP-013: salen de las tablas de trabajo.", "hecho": "se quita en cada foto la columna que no tiene ningún valor.",
         "codigo": "df.drop(columns=[c for c in df.columns if df[c].isna().all()])", "comprobacion": f"salen en septiembre: {', '.join(m['lista_vacias_sep'])}.", "quedo": "cada foto con sus columnas con dato; diciembre, sin precio."},
        {**base, "clave": "correccion-cp-014", "titulo": "CP-014 polígono inválido", "tabla": "polígonos de barrio", "estaba": f"{len(m['reparados'])} polígono inválido.", "problema": "hace falta para el mapa.", "decision": "CP-014: se repara.", "hecho": "con make_valid, solo en el inválido.", "codigo": "shapely.make_valid(forma)",
         "comprobacion": f"{m['reparados']}.", "quedo": "todos válidos, en WKB y EPSG:4326."},
        {**base, "clave": "correccion-tipos", "titulo": "Tipos del calendario, las reseñas y los libros", "tabla": "calendario, reseñas y libros oficiales", "estaba": "fechas y disponibilidad en texto; los libros, con código y nombre juntos y un 0 cuando no hay dato.", "problema": "hacen falta sus tipos para agregar y cruzar.",
         "decision": "técnicamente inequívoca: la nota (2) de los libros documenta el código de ausencia.", "hecho": "fechas con su patrón, disponibilidad a booleano, código y nombre separados y ceros de los libros a vacío.", "codigo": "pd.to_datetime(df['date'], format='%Y-%m-%d')\ndf[c].where(df[c].gt(0))",
         "comprobacion": f"calendario {m['calendario']} filas y {m['libres']} días libres antes y después; reseñas {m['resenas']} filas; ceros que pasan a vacío {m['ceros']}.", "quedo": "cada columna en su tipo. Nombres de los libros: distrito → cod y nombre; primer valor → m2_total, sup_total y ventas."},
    ]


# ---------------------------------------------------------------------------
# 5. Informe
# ---------------------------------------------------------------------------

def informe(s):
    """Genera el Markdown a partir del diccionario que se guarda en el JSON."""
    r = ["# Informe de corrección de datos", "", "## Fuente", ""]
    r += [f"- Ejecución: {s['fecha_ejecucion']}, con Python {s['python']}, pandas {s['pandas']} y pyarrow {s.get('pyarrow')}.", f"- JSON de calidad: `informes/calidad-datos.json`, con estado {s.get('estado_calidad')}.", ""]
    r += [f"- Entrada `{e['ruta']}`: huella {e['sha256']}." for e in s["entradas"]]
    r += [f"- Salida `{e['ruta']}`: {e['filas']} filas, {e['columnas']} columnas, huella {e['sha256']}." for e in s.get("salidas", [])]
    r += ["", s["resultado"].get("resumen", ""), "", "## Correcciones aplicadas", ""]
    r += [f"- {c['id']} ({c['problema_calidad']}), `{c['tabla']}.{c['columna']}`: {c['correccion']}. Criterio: {c['criterio']}. De {c['antes']} a {c['despues']}. Ficha {c['ficha']}." for c in s.get("correcciones", [])]
    r += ["", "## Decisiones del usuario", ""]
    r += [f"- {d['pendiente']}: {d['decision']} ({d['fecha']})." for d in s.get("decisiones_usuario", [])] or ["No hay."]
    r += ["", "## Elementos mantenidos sin cambios", ""] + [f"- {x['problema_calidad']}: {x['motivo']}" for x in s.get("sin_cambios", [])]
    r += ["", "## Decisiones pendientes", "", f"No hay: {len(s.get('cuestiones', []))} cuestiones en cuestiones-pendientes.md, todas con su decisión." if not s["pendientes"] else ""]
    r += ["## Validación", ""] + [f"- Suma de `{x['columna']}`: {x['antes']} antes y {x['despues']} después; coincide: {x['coincide']}." for x in s.get("sumas_control", [])]
    r += [f"- {k}: {v}." for k, v in s.get("comprobaciones", {}).items()] + [f"- Estado final: {s['resultado'].get('estado')}.", ""]
    r += ["", "## Datos personales", "", rc.texto_personales("Esta corrección no copia ningún valor de `licencia_nacional`, `licencia_exencion`, `licencia_vt` ni `licencia_otro`: las deja como llegan.")]
    r += ["", "## Límites", "", "La corrección mira una tabla. Una clave huérfana o repetida al otro lado de un cruce no se ve ni se corrige aquí.", ""]
    return "\n".join(r)


# ---------------------------------------------------------------------------
# 6. Ejecución
# ---------------------------------------------------------------------------

def principal(s):
    """Corrige todas las tablas en la misma ejecución."""
    import pyarrow
    s["pyarrow"] = pyarrow.__version__
    antes = cd.huellas_de_raw()
    s["entradas"] = [{"ruta": r, "sha256": h, "filas": None, "columnas": None} for r, h in antes.items()]

    # 5.1 Al empezar: sin diagnóstico válido no se corrige.
    if not cd.SALIDA_JSON.exists():
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "Falta informes/calidad-datos.json.", "artefactos": [], "siguiente": "lanzar calidad-datos"}
        return s
    calidad = json.loads(cd.SALIDA_JSON.read_text(encoding="utf-8"))
    s["estado_calidad"] = calidad["resultado"]["estado"]
    if s["estado_calidad"] in ("PARADO", "ERROR") or {e["ruta"]: e["sha256"] for e in calidad["entradas"]} != antes:
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "El diagnóstico está parado o describe otra fuente.", "artefactos": [], "siguiente": "repetir calidad-datos"}
        return s
    id_de = {f["clave"]: f["id"] for f in calidad["tabla_de_decisiones"]}
    dec = rc.leer_decisiones()
    dicc = json.loads(cd.DICCIONARIO.read_text(encoding="utf-8"))
    fichas_dic = {t["tabla"]: t for t in dicc["tablas"]}

    # 5.2 Las cuatro fotos.
    fotos, brutas, censos, vacias, raros = {}, {}, {}, {}, 0
    for clave, tabla in cd.TABLA_FOTO.items():
        brutas[clave], fotos[clave], censos[clave], r, vacias[clave] = corregir_foto(cd.RAW / cd.RUTAS[tabla])
        raros += r

    # 5.3 Un dato personal en claro para el trabajo antes de escribir nada; solo se cuenta.
    personales = []
    for clave, tabla in cd.TABLA_FOTO.items():
        roles = {c["columna"]: c["rol"] for c in fichas_dic.get(tabla, {}).get("campos", [])}
        frec = {c: brutas[clave][c].dropna().astype("str").value_counts(sort=False) for c, rol in roles.items() if rol in ("texto_libre", "categorica") and c in brutas[clave]}
        personales += cd.buscar_personal(tabla, frec, roles)
    if personales:
        s["datos_personales_en_claro"] = personales
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "Hay datos con forma de dato personal en claro: " + "; ".join(f"{x['tabla']}.{x['columna']}, {x['filas']} filas" for x in personales),
                          "artefactos": [], "siguiente": "avisar a la persona responsable (reglas §4)"}
        return s

    # 5.4 El resto de tablas.
    barrios, n_equiv = corregir_barrios(pd.read_csv(cd.RAW / cd.RUTAS[cd.BARRIOS]), dec)
    lic_cruda = pd.read_csv(cd.RAW / cd.RUTAS[cd.LICENCIAS])
    lic, sin_maestro = corregir_licencias(lic_cruda, barrios, dec)
    libros = {n: cd.leer_libro(n, (fichas_dic.get(n, {}).get("lectura") or {}).get("posiciones")) for n in cd.LIBROS}
    oficial, ceros = corregir_oficial(libros)
    puntos, n_puntos, n_fuera = corregir_puntos(dec)
    poligonos, reparados = corregir_poligonos()
    cal, libres = leer_calendario()
    res = leer_resenas()

    # 5.5 Validaciones antes de guardar: filas y sumas por dos caminos, en cada foto.
    sumas, fallos = [], []
    for clave in fotos:
        b, d = brutas[clave], fotos[clave]
        if len(b) != len(d):
            fallos.append(f"{clave}: cambian las filas")
        if "price" in d:
            a, c = round(suma_exacta(b["price"]), 2), round(float(d["price"].sum()), 2)
            sumas.append({"columna": f"{clave}.price", "antes": a, "despues": c, "coincide": a == c})
        for col in MAGNITUDES:
            if col in d:
                a, c = float(b[col].sum()), float(d[col].sum())
                sumas.append({"columna": f"{clave}.{col}", "antes": a, "despues": c, "coincide": a == c})
    a, c = float(lic_cruda["viviendas"].sum()), float(lic["viviendas"].sum())
    sumas.append({"columna": "licencias.viviendas", "antes": a, "despues": c, "coincide": a == c})
    sumas.append({"columna": "calendario.dias_libres", "antes": libres, "despues": int(cal["available"].sum()), "coincide": libres == int(cal["available"].sum())})
    fallos += [f"suma de {x['columna']}" for x in sumas if not x["coincide"]]
    if raros:
        fallos.append(f"{raros} precios fuera del formato demostrado")
    if len(lic) != len(lic_cruda):
        fallos.append("cambian las filas de las licencias")
    if not bool(shapely.is_valid(shapely.from_wkb(poligonos["geometria_wkb"].to_numpy())).all()):
        fallos.append("queda un polígono inválido")
    if cal["date"].isna().any() or res["date"].isna().any():
        fallos.append("hay fechas sin convertir")

    # Las cuatro comprobaciones miden lo que se va a guardar; una que no pasa impide guardar.
    proteccion = json.loads(cd.PROTECCION.read_text(encoding="utf-8")) if cd.PROTECCION.exists() else {"tablas": []}
    suprimidas = {Path(t["fichero_salida"]).name.split(".")[0]: [c["columna"] for c in t.get("campos", []) if c.get("tecnica") == "supresion"] for t in proteccion["tablas"]}
    con_roles = [(n, d, {c["columna"]: c["rol"] for c in fichas_dic.get(n, {}).get("campos", [])}, suprimidas.get(n, [])) for n, d in [(cd.TABLA_FOTO[k], v) for k, v in fotos.items()] + [(cd.LICENCIAS, lic)]]
    medidas = {"completitud": medir_completitud(len(brutas["sep"]), len(fotos["sep"]), n_fuera), "consistencia": medir_consistencia(fotos, cal, res, barrios, sin_maestro), "utilidad": medir_utilidad(fotos["sep"]), "datos_personales": medir_datos_personales(con_roles)}
    fallos += [f"{k}: {v['texto']}" for k, v in medidas.items() if not v["pasa"]]
    if fallos:
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "No se guarda: " + "; ".join(fallos), "artefactos": [], "siguiente": "revisar la corrección"}
        return s

    # 5.6 Guardar, con el diccionario de cada tabla corregida.
    sep, sep_bruta = fotos["sep"], brutas["sep"]
    tablas = {**{k: v for k, v in fotos.items()}, "calendario": cal, "resenas": res, "licencias": lic, "barrios": barrios, "oficial": oficial, "puntos": puntos, "poligonos": poligonos}
    medida = {"precio_vacio": int(sep["price"].isna().sum()), "censo_sep": censos["sep"], "precio_raros": raros, "captura": int(sep["captura_anterior"].sum()), "barrios_distrito": int(barrios["toma_precio_de_distrito"].sum()),
              "equivalencias": n_equiv, "camas_vacias": int(sep["beds"].isna().sum()), "cero_banos": int(sep["marca_cero_banos"].sum()), "banos_vacios": int(sep["banos"].isna().sum()),
              "medio_bano": int(sep["banos"].eq(0.5).sum()), "no_vivienda": int(sep["marca_no_vivienda"].sum()), "incoherente": int(sep["marca_tamano_incoherente"].sum()), "estancia_larga": int(sep["marca_estancia_larga"].sum()),
              "puntos_antes": n_puntos, "puntos_fuera": n_fuera, "distritos_antes": int(lic_cruda["distrito"].nunique()), "distritos_despues": int(lic["distrito"].nunique()), "plantas_antes": int(lic_cruda["planta"].nunique()),
              "plantas_despues": int(lic["planta"].nunique()), "distritos_sin_maestro": sin_maestro, "licencias": len(lic), "vacias_sep": len(vacias["sep"]), "lista_vacias_sep": vacias["sep"], "reparados": reparados,
              "calendario": len(cal), "libres": libres, "resenas": len(res), "ceros": ceros}
    fichas = rc.anadir_fichas(fichas_de(medida))
    regla_col = {"price": "correccion-cp-001", "banos": "correccion-cp-007", "marca_cero_banos": "correccion-cp-007", "marca_no_vivienda": "correccion-cp-008", "marca_tamano_incoherente": "correccion-cp-009",
                 "marca_estancia_larga": "correccion-cp-010", "captura_anterior": "correccion-cp-002", "clave_oficial": "correccion-cp-004", "toma_precio_de_distrito": "correccion-cp-003",
                 "planta": "correccion-cp-012", "distrito": "correccion-cp-012", "geometria_wkb": "correccion-cp-014", "date": "correccion-tipos", "available": "correccion-tipos", "m2_total": "correccion-tipos", "sup_total": "correccion-tipos"}
    rc.PROCESADO.mkdir(parents=True, exist_ok=True)
    s["salidas"] = []
    for clave, df in tablas.items():
        ruta = rc.PROCESADO / rc.CORREGIDA[clave]
        df.to_parquet(ruta, index=False)
        campos = [{"columna": c, "tipo": str(df[c].dtype), "nulos": int(df[c].isna().sum()), "distintos": int(df[c].astype("object").nunique()) if c != "geometria_wkb" else len(df),
                   "regla_aplicada": fichas.get(regla_col.get(c, ""))} for c in df.columns]
        s["salidas"].append({"tabla": clave, "ruta": ruta.relative_to(rc.CASO).as_posix(), "sha256": cd.huella(ruta), "filas": len(df), "columnas": df.shape[1], "campos_salida": campos})

    # 5.7 Lo que cambió de verdad, lo que se deja y las comprobaciones.
    def correccion(clave_calidad, tabla, columna, texto, criterio, clave_ficha, antes_, despues_):
        """Devuelve una corrección para el JSON, solo si cambió algo."""
        return {"problema_calidad": id_de.get(clave_calidad), "tabla": tabla, "columna": columna, "correccion": texto, "criterio": criterio, "ficha": fichas[clave_ficha], "antes": antes_, "despues": despues_} if antes_ != despues_ else None

    filas_sep = len(sep)
    lista = [correccion("precio_texto", "sep", "price", "texto a número", "regla_documentada", "correccion-cp-001", "texto", "número"),
             correccion("banos_vacio", "sep", "banos", "baños leídos del texto; vacíos en la columna numérica antes y después en `banos`", "regla_documentada", "correccion-cp-007", int(sep_bruta["bathrooms"].isna().sum()), medida["banos_vacios"]),
             correccion("banos_cero", "sep", "marca_cero_banos", "marcados", "usuario", "correccion-cp-007", 0, medida["cero_banos"]),
             correccion("no_vivienda", "sep", "marca_no_vivienda", "marcados", "usuario", "correccion-cp-008", 0, medida["no_vivienda"]),
             correccion("tamano_incoherente", "sep", "marca_tamano_incoherente", "marcados", "usuario", "correccion-cp-009", 0, medida["incoherente"]),
             correccion("captura_anterior", "sep", "captura_anterior", "marcados, se quedan", "usuario", "correccion-cp-002", 0, medida["captura"]),
             correccion("estancia_larga", "sep", "marca_estancia_larga", "marca informativa", "usuario", "correccion-cp-010", 0, medida["estancia_larga"]),
             correccion("puntos_de_interes", "puntos", "fila", "fuera de Madrid", "usuario", "correccion-cp-011", n_puntos, len(puntos)),
             correccion("licencias_escritura", "licencias", "distrito", "al nombre del maestro", "usuario", "correccion-cp-012", medida["distritos_antes"], medida["distritos_despues"]),
             correccion("licencias_escritura", "licencias", "planta", "mayúsculas sin espacios de sobra", "usuario", "correccion-cp-012", medida["plantas_antes"], medida["plantas_despues"]),
             correccion("equivalencias", "barrios", "clave_oficial", "barrios con otra escritura", "usuario", "correccion-cp-004", 0, n_equiv),
             correccion("aeropuerto", "barrios", "toma_precio_de_distrito", "barrios que toman el precio de su distrito", "usuario", "correccion-cp-003", 0, medida["barrios_distrito"]),
             correccion("columnas_vacias", "sep", "columnas", "columnas enteras vacías fuera", "usuario", "correccion-cp-013", sep_bruta.shape[1], sep_bruta.shape[1] - len(vacias["sep"])),
             correccion("poligono_invalido", "poligonos", "geometria", "polígonos inválidos reparados", "usuario", "correccion-cp-014", len(reparados), 0),
             correccion(None, "oficial", "m2_total, sup_total", "el 0 de la nota (2) pasa a vacío", "tecnicamente_inequivoca", "correccion-tipos", sum(ceros.values()), 0)]
    s["correcciones"] = [dict(c, id=f"K-{i:02d}") for i, c in enumerate((c for c in lista if c), 1)]
    s["sin_cambios"] = [{"problema_calidad": id_de.get("precio_vacio"), "motivo": f"CP-001: {medida['precio_vacio']} precios vacíos siguen vacíos en septiembre."},
                        {"problema_calidad": id_de.get("casco_vallecas"), "motivo": "CP-005: Casco Histórico de Vallecas usa el precio del barrio; va como riesgo."},
                        {"problema_calidad": id_de.get("camas_vacias"), "motivo": f"CP-006: {medida['camas_vacias']} camas vacías siguen vacías y no pasan el tope."},
                        {"problema_calidad": "fechas de las fotos", "motivo": "first_review, last_review y las del precio siguen en texto ISO: ningún cálculo las usa."},
                        {"problema_calidad": "plantas", "motivo": "las plantas escritas como texto libre no se interpretan; los informes solo cuentan las licencias que nombran la baja."},
                        {"problema_calidad": "reglas candidatas", "motivo": "RC-01, RC-02, RC-04, RC-10 y RC-12 no se aprueban (cuestiones-pendientes.md)."}]
    s["cuestiones"] = contar_cuestiones(CUESTIONES.read_text(encoding="utf-8")) if CUESTIONES.exists() else []
    tramo = f"{s['cuestiones'][0]} a {s['cuestiones'][-1]}" if s["cuestiones"] else "ninguna leída"
    s["decisiones_usuario"] = [{"pendiente": tramo, "decision": "resueltas en docs/criterios_de_datos.md, fijadas con datos, con buenas prácticas y con su refutación", "fecha": "2026-11-06"}]
    s["nombres"] = [{"tabla": "barrios", "antes": "neighbourhood", "despues": "barrio", "ficha": fichas["correccion-tipos"]}, {"tabla": "barrios", "antes": "neighbourhood_group", "despues": "distrito", "ficha": fichas["correccion-tipos"]}]
    s["sumas_control"] = sumas
    s["va_a_modelo"] = False
    s["parametros"] = PARAMETROS
    s["medida"] = {k: v for k, v in medida.items() if k not in ("censo_sep",)}
    s["vacias_por_foto"] = vacias
    s["comprobaciones"] = {k: f"{'pasa' if v['pasa'] else 'falla'}: {v['texto']}" for k, v in medidas.items()}
    artefactos = [x["ruta"] for x in s["salidas"]] + ["informes/correccion-datos.json", "informes/correccion-datos.md"]
    s["resultado"] = {"estado": "OK", "riesgo": "bajo", "resumen": f"Se corrigieron {len(tablas)} tablas con {len(s['cuestiones'])} cuestiones resueltas. La foto de septiembre conserva sus {filas_sep} anuncios; solo salen {n_fuera} puntos de interés.",
                      "artefactos": artefactos, "siguiente": "modelado-datos"}
    if cd.huellas_de_raw() != antes:
        s["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": "data/raw/ ha cambiado durante la ejecución.", "artefactos": [], "siguiente": "revisar"}
    return s


def ejecutar():
    """Lanza la corrección y, si algo falla, deja el JSON con estado ERROR antes de avisar."""
    s = rc.bloque_comun(ETAPA, VERSION, SCRIPT)
    try:
        s = principal(s)
    except Exception as error:
        rc.parar_con_error(s, "correccion-datos", error, informe)
        raise
    rc.guardar(s, "correccion-datos", informe)
    print(s["resultado"]["estado"], s["resultado"]["resumen"])
    return 0 if s["resultado"]["estado"] != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(ejecutar())
