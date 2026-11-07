"""Piezas comunes de la preparación de datos del caso: no hace nada al importarse.

Lo usan correccion_datos.py, modelo_datos.py, integracion_datos.py y transformacion_datos.py. Toma de calidad_datos.py lo
que ya existe (lectura de los libros, normalización de nombres, superficie, huellas): ese script guarda su trabajo
dentro de __main__, así que importarlo no lo ejecuta.
"""
import datetime as dt
import json
import platform
import re
from pathlib import Path

import pandas as pd

import calidad_datos as cd

# ---------------------------------------------------------------------------
# 1. Rutas y decisiones
# ---------------------------------------------------------------------------

CASO = Path(__file__).resolve().parents[1]
PROCESADO = CASO / "data" / "processed"
INFORMES = CASO / "informes"
MODELO = CASO / "config" / "modelo"
REGISTRO = MODELO / "registro-transformaciones.md"
DECISIONES = CASO / "scripts" / "decisiones_correccion.json"
FECHA_DATOS = cd.FECHA_DATOS
QUIEN = "Juan Luis León"
# Las cinco pruebas del grupo (reglas §3), con el nombre que llevan en los JSON.
PRUEBAS = ["sin_temporada", "sin_anfitriones_grandes", "sin_cotizaciones_lejanas", "solo_1_y_2_dormitorios", "sin_ocupacion_como_cero"]
# Cada variante mira la cotización de la foto de la que toma el precio.
DIAS_DE_LA_FOTO = {"p_mar": "dias_cotizacion_mar", "p_jun": "dias_cotizacion_jun", "precio": "dias_cotizacion"}

# 1.1 Tablas corregidas: cada una con su fichero, para no repetir nombres entre scripts.
FOTOS = cd.FOTOS
CORREGIDA = {**{clave: f"listings_{fecha}_corregido.parquet" for clave, fecha in FOTOS.items()},
             "calendario": "calendario_corregido.parquet", "resenas": "resenas_corregido.parquet", "licencias": "licencias_corregido.parquet",
             "barrios": "barrios_corregido.parquet", "oficial": "oficial_2025_corregido.parquet", "puntos": "puntos_interes_corregido.parquet",
             "poligonos": "barrios_poligonos_corregido.parquet"}


def leer_decisiones():
    """Lee el fichero de decisiones del proyecto."""
    return json.loads(DECISIONES.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 2. Las marcas de calidad y las exclusiones de cada base
# ---------------------------------------------------------------------------

def marcas_de_calidad(t):
    """Marca lo que sale de la base de decisión por CP-007, CP-008 y CP-009, sin quitar ninguna fila."""
    piso = t["room_type"].eq("Entire home/apt")
    salida = pd.DataFrame(index=t.index)
    salida["marca_cero_banos"] = t["banos"].eq(0).fillna(False).astype("bool")
    salida["marca_no_vivienda"] = (piso & ~t["property_type"].fillna("").str.startswith("Entire")).astype("bool")
    salida["marca_tamano_incoherente"] = (t["beds"].gt(t["accommodates"]) | t["bedrooms"].gt(t["accommodates"])).fillna(False).astype("bool")
    return salida


# Cada exclusión: columna, qué sale, de qué cálculo, cómo se trata, por qué, si se recupera y la base a la que afecta.
EXCLUSIONES = [
    ("excl_no_piso_completo", "habitaciones privadas, compartidas y de hotel", "base de decisión", "marcadas, siguen en la tabla", "reglas §1: el piso se analiza aparte", "no aplica: son otro producto", "decision"),
    ("excl_dentro_centro", "anuncios dentro del APE 00.01", "base de decisión", "marcados, siguen en la tabla", "reglas §1 y §7: fuera del centro histórico", "no aplica: es la norma", "decision"),
    ("excl_precio_vacio", "anuncios sin precio en septiembre", "ambas bases", "el vacío se queda (CP-001)", "reglas §2: un vacío no se rellena", "no: otra foto es otra cotización", "ambas"),
    ("excl_precio_fuera_rango", "precio fuera de 20 a 1.000 €", "ambas bases", "marcados", "reglas §3", "no aplica: valor correcto fuera del rango", "ambas"),
    ("excl_mas_de_8_huespedes", "más de 8 huéspedes", "ambas bases", "marcados", "reglas §3", "no aplica", "ambas"),
    ("excl_mas_de_5_banos", "más de 5 baños", "ambas bases", "marcados", "reglas §3", "no aplica", "ambas"),
    ("excl_mas_de_5_dormitorios", "más de 5 habitaciones", "ambas bases", "marcados", "reglas §3", "no aplica", "ambas"),
    ("excl_mas_de_6_camas", "más de 6 camas", "ambas bases", "marcados", "reglas §3", "no aplica", "ambas"),
    ("excl_tamano_vacio", "habitaciones o baños vacíos", "ambas bases", "el vacío se queda", "reglas §2: sin ellos no hay superficie", "no", "ambas"),
    ("excl_camas_vacias", "camas vacías", "ambas bases", "el vacío se queda (CP-006)", "CP-006: un vacío no pasa el tope", "no", "ambas"),
    ("excl_sin_ocupacion", "sin reseñas en el último año", "ambas bases", "marcados; su peso va como riesgo", "reglas §2 y §7", "no: no hay ingreso que medir", "ambas"),
    ("excl_estancia_mas_de_3", "estancia de más de 3 noches", "base de decisión", "marcados; también recoge CP-010", "reglas §3 y CP-010", "no aplica", "decision"),
    ("excl_estancia_vacia", "sin estancia publicada ni en el calendario", "base de decisión", "marcados", "reglas §2", "no", "decision"),
    ("excl_cero_banos", "cero baños en un anuncio", "base de decisión", "marcados (CP-007)", "CP-007: dudosos en un piso", "no", "decision"),
    ("excl_no_vivienda", "piso que no es vivienda entera", "base de decisión", "marcados (CP-008)", "CP-008", "no aplica", "decision"),
    ("excl_tamano_incoherente", "más camas o habitaciones que huéspedes", "base de decisión", "marcados (CP-009)", "CP-009", "no", "decision"),
    ("comp_excl_habitacion_hotel", "habitaciones de hotel", "base de comparación", "marcadas", "reglas §3", "no aplica", "comparacion"),
    ("comp_excl_menos_de_180_dias", "menos de 180 días disponibles", "base de comparación", "marcados", "reglas §3: solo para comparar; deja fuera a los más alquilados", "no aplica", "comparacion"),
]


def exclusiones(t, dec):
    """Calcula una marca por exclusión. Pide las columnas room_type, dentro, precio, banos, estancia, ocupacion y las marcas de calidad."""
    u = dec["poblacion"]
    m = pd.DataFrame(index=t.index)
    m["excl_no_piso_completo"] = t["room_type"].ne("Entire home/apt")
    m["excl_dentro_centro"] = t["dentro"]
    m["excl_precio_vacio"] = t["precio"].isna()
    m["excl_precio_fuera_rango"] = t["precio"].notna() & ~t["precio"].between(u["precio_min"], u["precio_max"])
    m["excl_mas_de_8_huespedes"] = t["accommodates"].gt(u["huespedes_max"])
    m["excl_mas_de_5_banos"] = t["banos"].gt(u["banos_max"])
    m["excl_mas_de_5_dormitorios"] = t["bedrooms"].gt(u["dormitorios_max"])
    m["excl_mas_de_6_camas"] = t["beds"].gt(u["camas_max"])
    m["excl_tamano_vacio"] = t["bedrooms"].isna() | t["banos"].isna()
    m["excl_camas_vacias"] = t["beds"].isna()
    m["excl_sin_ocupacion"] = ~t["ocupacion"].gt(0)
    m["excl_estancia_mas_de_3"] = t["estancia"].gt(u["estancia_max"])
    m["excl_estancia_vacia"] = t["estancia"].isna()
    m["excl_cero_banos"] = t["marca_cero_banos"]
    m["excl_no_vivienda"] = t["marca_no_vivienda"]
    m["excl_tamano_incoherente"] = t["marca_tamano_incoherente"]
    m["comp_excl_habitacion_hotel"] = t["room_type"].eq("Hotel room")
    m["comp_excl_menos_de_180_dias"] = ~t["availability_365"].ge(u["dias_comparacion"])
    return m.fillna(False).astype("bool")


def bases(m):
    """Da las dos bases a partir de las marcas: cada una con las exclusiones que le tocan."""
    de_decision = [c for c, *_, base in EXCLUSIONES if base in ("decision", "ambas")]
    de_comparacion = [c for c, *_, base in EXCLUSIONES if base in ("comparacion", "ambas")]
    return ~m[de_decision].any(axis=1), ~m[de_comparacion].any(axis=1)


# ---------------------------------------------------------------------------
# 3. El JSON, el informe y lo común a todos
# ---------------------------------------------------------------------------

def bloque_comun(etapa, version, script):
    """Crea el diccionario con el bloque común de la cadena."""
    return {"etapa": etapa, "version_etapa": version, "script": script, "fecha_datos": FECHA_DATOS, "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
            "python": platform.python_version(), "pandas": pd.__version__, "entradas": [], "resultado": {}, "pendientes": []}


def entrada(ruta, df=None):
    """Describe un fichero de entrada con su huella y, si se le da, sus filas y columnas."""
    return {"ruta": Path(ruta).relative_to(CASO).as_posix(), "sha256": cd.huella(ruta), "filas": None if df is None else len(df),
            "columnas": None if df is None else df.shape[1]}


def guardar(s, nombre, texto):
    """Escribe el JSON sin NaN y el Markdown generado de él."""
    limpio = cd.sin_nan(s)
    INFORMES.mkdir(exist_ok=True)
    (INFORMES / f"{nombre}.json").write_text(json.dumps(limpio, ensure_ascii=False, indent=1, allow_nan=False, default=str), encoding="utf-8")
    (INFORMES / f"{nombre}.md").write_text(texto(limpio), encoding="utf-8")


def parar_con_error(s, nombre, error, texto):
    """Deja el JSON con estado ERROR cuando algo falla por dentro."""
    s["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"Fallo técnico: {error!r}", "artefactos": [], "siguiente": "arreglar el fallo"}
    guardar(s, nombre, texto)


def texto_personales(extra):
    """Redacta el apartado de datos personales desde proteccion-datos.json."""
    ruta = cd.PROTECCION
    proteccion = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return "\n".join(l for l in cd.texto_datos_personales(proteccion)[:-1]) + "\n\n" + extra


# ---------------------------------------------------------------------------
# 4. El registro de transformaciones: solo acumula
# ---------------------------------------------------------------------------

def anadir_fichas(fichas):
    """Añade las fichas cuya clave aún no está en el registro y devuelve el número de cada clave."""
    # Se lee y se escribe sin traducir los saltos de línea, para que el fichero conserve los suyos.
    # El registro nace con la cadena: en un repositorio recién clonado todavía no existe.
    if not REGISTRO.exists():
        REGISTRO.parent.mkdir(parents=True, exist_ok=True)
        REGISTRO.write_text("# Registro de transformaciones\n", encoding="utf-8", newline="\n")
    bruto = REGISTRO.read_bytes().decode("utf-8")
    salto = "\r\n" if "\r\n" in bruto else "\n"
    texto = bruto.replace("\r\n", "\n")
    numeros = [int(n) for n in re.findall(r"^## R-(\d+)", texto, flags=re.M)]
    siguiente = max(numeros, default=0) + 1
    existentes = dict(re.findall(r"^## (R-\d+) · .*\n<!-- clave: (.*?) -->", texto, flags=re.M))
    existentes = {v: k for k, v in existentes.items()}
    nuevas, salida = [], {}
    hoy = dt.date.today().isoformat()
    for f in fichas:
        if f["clave"] in existentes:
            salida[f["clave"]] = existentes[f["clave"]]
            continue
        numero = f"R-{siguiente:03d}"
        siguiente += 1
        salida[f["clave"]] = numero
        nuevas.append(f"\n## {numero} · {f['titulo']}\n<!-- clave: {f['clave']} -->\n\nFecha: {hoy}.\n\n"
                      f"- **Tabla y columna:** {f['tabla']}\n- **Cómo estaba:** {f['estaba']}\n- **Problema o finalidad:** {f['problema']}\n"
                      f"- **Decisión:** {f['decision']}\n- **Qué se hizo:** {f['hecho']}\n\n```python\n{f['codigo']}\n```\n\n"
                      f"- **Quién:** {f.get('quien', QUIEN)}.\n- **Comprobación:** {f['comprobacion']}\n- **Cómo quedó:** {f['quedo']}\n- **Cómo se deshace:** {f['deshacer']}\n")
    if nuevas:
        REGISTRO.write_bytes((texto.rstrip("\n") + "\n" + "".join(nuevas)).replace("\n", salto).encode("utf-8"))
    return salida


# ---------------------------------------------------------------------------
# 5. Las cinco pruebas del grupo (reglas §3)
# ---------------------------------------------------------------------------

def clase_del_barrio(aguantadas):
    """Da la clase de un barrio del grupo por las pruebas que aguanta."""
    if aguantadas == len(PRUEBAS):
        return "5 de 5 veces"
    return "4 de 5 veces" if aguantadas == len(PRUEBAS) - 1 else "menos de 4 veces"


def pruebas_del_grupo(L, excluir, reglas):
    """Repite las 12 variantes con cada prueba y clasifica los barrios del grupo. Ningún piso sale de la base: solo se mide si la lista aguanta."""
    grupo, _ = cd.grupo_de(L, excluir=excluir)
    lejanas = {col: L[dias].gt(reglas["cotizacion_dias"]) for col, dias in DIAS_DE_LA_FOTO.items()}
    medidas = {"sin_temporada": cd.grupo_de(L, excluir=excluir | L["temporada"]),
               "sin_anfitriones_grandes": cd.grupo_de(L, excluir=excluir | L["anuncios_anfitrion"].ge(reglas["anfitrion_anuncios"])),
               "sin_cotizaciones_lejanas": cd.grupo_de(L, excluir=excluir, por_foto=lejanas),
               "solo_1_y_2_dormitorios": cd.grupo_de(L, excluir=excluir | ~L["bedrooms"].isin(reglas["dormitorios"])),
               "sin_ocupacion_como_cero": cd.grupo_de(L, excluir=excluir, cero=True)}
    barrios = {}
    for b in grupo:
        aguanta = [p for p in PRUEBAS if b in medidas[p][0]]
        barrios[b] = {"aguanta": aguanta, "no_aguanta": [p for p in PRUEBAS if p not in aguanta], "cuantas": len(aguanta), "clase": clase_del_barrio(len(aguanta))}
    de_clase = lambda clase: sorted(b for b, x in barrios.items() if x["clase"] == clase)
    return {"grupo": grupo, "barrios": barrios, "firmes": de_clase("5 de 5 veces"), "con_aviso": de_clase("4 de 5 veces"), "segunda_linea": de_clase("menos de 4 veces"),
            "por_prueba": {p: sorted(set(grupo) & set(medidas[p][0])) for p in PRUEBAS}, "variantes_por_prueba": {p: {k: int(v) for k, v in sorted(medidas[p][1].items())} for p in PRUEBAS}}
