"""Comprueba lo que afirma el diseño del modelo del caso y deja el plan de cruces.

Comprueba columnas, claves del grano, tipos de las claves, rangos de fechas y los recuentos del registro de exclusiones.
No cruza ni guarda tablas. La aprobación se lee de config/modelo/modelo-datos.md y nunca se da por hecha.
Escribe informes/modelado-datos.json y, generado de él, informes/modelado-datos.md.

Se lanza después de scripts/correccion_datos.py.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/modelo_datos.py
"""
import json
import re

import pandas as pd
import shapely

import calidad_datos as cd
import reglas_caso as rc

# ---------------------------------------------------------------------------
# 1. Configuración, copiada del diseño de modelo-datos.md
# ---------------------------------------------------------------------------

SKILL = "modelado-datos"
VERSION = "1.0"
SCRIPT = "scripts/modelo_datos.py"
DISENO = rc.MODELO / "modelo-datos.md"
# La cadena sigue aunque el diseño no lleve aprobación: queda escrito.
SEGUIR = "la cadena sigue y el responsable lo ve en el informe"
ANUNCIO_COLS = ["id", "neighbourhood_cleansed", "neighbourhood_group_cleansed", "room_type", "property_type", "price", "estimated_occupancy_l365d", "minimum_nights", "availability_365"]

TABLAS = [
    {"tabla": "hechos_anuncios", "clave_corregida": "sep", "grano": "un anuncio en la foto del 17/09/2026", "clave_grano": ["id"], "tipo": "hechos", "columnas": ANUNCIO_COLS},
    {"tabla": "hechos_anuncios_junio", "clave_corregida": "jun", "grano": "un anuncio en la foto del 20/06/2026", "clave_grano": ["id"], "tipo": "hechos", "columnas": ["id", "price", "neighbourhood_cleansed"]},
    {"tabla": "hechos_anuncios_marzo", "clave_corregida": "mar", "grano": "un anuncio en la foto del 24/03/2026", "clave_grano": ["id"], "tipo": "hechos", "columnas": ["id", "price", "neighbourhood_cleansed"]},
    {"tabla": "hechos_anuncios_diciembre", "clave_corregida": "dic", "grano": "un anuncio en la foto del 14/12/2025, sin precio", "clave_grano": ["id"], "tipo": "hechos", "columnas": ["id", "neighbourhood_cleansed"]},
    {"tabla": "hechos_calendario", "clave_corregida": "calendario", "grano": "un anuncio y un día", "clave_grano": ["listing_id", "date"], "tipo": "hechos", "columnas": ["listing_id", "date", "available", "minimum_nights"]},
    {"tabla": "hechos_resenas", "clave_corregida": "resenas", "grano": "una reseña; anuncio y fecha se repiten y nada la identifica salvo su posición", "clave_grano": [], "tipo": "hechos", "columnas": ["listing_id", "date"]},
    {"tabla": "dim_barrio", "clave_corregida": "barrios", "grano": "un barrio de Inside Airbnb", "clave_grano": ["barrio"], "tipo": "dimension", "columnas": ["barrio", "distrito", "clave_oficial", "clave_distrito", "toma_precio_de_distrito"]},
    {"tabla": "dim_oficial", "clave_corregida": "oficial", "grano": "un barrio o un distrito oficial en 2025", "clave_grano": ["cod"], "tipo": "dimension", "columnas": ["cod", "nombre", "nivel", "m2_total", "sup_total", "ventas", "clave", "clave_distrito"]},
    {"tabla": "aux_licencias", "clave_corregida": "licencias", "grano": "una licencia, sin su número", "clave_grano": [], "tipo": "auxiliar", "columnas": ["distrito", "barrio", "planta", "viviendas"]},
    {"tabla": "aux_puntos_interes", "clave_corregida": "puntos", "grano": "un punto de interés", "clave_grano": [], "tipo": "auxiliar", "columnas": ["capa", "x", "y"]},
    {"tabla": "aux_poligonos", "clave_corregida": "poligonos", "grano": "el polígono de un barrio", "clave_grano": ["barrio"], "tipo": "auxiliar", "columnas": ["barrio", "geometria_wkb"]},
]

RELACIONES = [
    {"desde": "hechos_anuncios", "hacia": "dim_barrio", "clave_desde": ["neighbourhood_cleansed"], "clave_hacia": ["barrio"], "maestro": "dim_barrio", "cardinalidad": "N:1", "procedencia": "reglas §4 y diccionario de origen"},
    {"desde": "dim_barrio", "hacia": "dim_oficial", "clave_desde": ["clave_oficial"], "clave_hacia": ["clave"], "maestro": "dim_oficial", "cardinalidad": "1:1", "procedencia": "reglas §6 y CP-004"},
    {"desde": "dim_barrio", "hacia": "dim_oficial", "clave_desde": ["clave_distrito"], "clave_hacia": ["clave_distrito"], "maestro": "dim_oficial", "cardinalidad": "N:1", "procedencia": "reglas §4 y §6"},
    {"desde": "hechos_calendario", "hacia": "hechos_anuncios", "clave_desde": ["listing_id"], "clave_hacia": ["id"], "maestro": "hechos_anuncios", "cardinalidad": "N:1", "procedencia": "reglas §5"},
    {"desde": "hechos_resenas", "hacia": "hechos_anuncios", "clave_desde": ["listing_id"], "clave_hacia": ["id"], "maestro": "hechos_anuncios", "cardinalidad": "N:1", "procedencia": "reglas §5"},
    {"desde": "hechos_anuncios", "hacia": "hechos_anuncios_junio", "clave_desde": ["id"], "clave_hacia": ["id"], "maestro": "hechos_anuncios_junio", "cardinalidad": "1:1", "procedencia": "reglas §3: dos anuncios son distintos si tienen distinto número"},
    {"desde": "hechos_anuncios", "hacia": "hechos_anuncios_marzo", "clave_desde": ["id"], "clave_hacia": ["id"], "maestro": "hechos_anuncios_marzo", "cardinalidad": "1:1", "procedencia": "reglas §3"},
    {"desde": "aux_licencias", "hacia": "dim_barrio", "clave_desde": ["barrio"], "clave_hacia": ["barrio"], "maestro": "dim_barrio", "cardinalidad": "N:1", "procedencia": "reglas §3: la licencia no se une a un anuncio, solo a su barrio"},
]

PLAN_CRUCES = [
    {"orden": 1, "partida": "dim_barrio", "se_une": "dim_oficial (barrios)", "clave_partida": ["clave_oficial"], "clave_une": ["clave"], "cardinalidad": "1:1", "tipo_cruce": "left", "magnitudes_control": [], "agregar_antes": None},
    {"orden": 2, "partida": "dim_barrio", "se_une": "dim_oficial (distritos)", "clave_partida": ["clave_distrito"], "clave_une": ["clave_distrito"], "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": [], "agregar_antes": None},
    {"orden": 3, "partida": "dim_barrio", "se_une": "aux_licencias", "clave_partida": ["barrio"], "clave_une": ["barrio"], "cardinalidad": "1:1", "tipo_cruce": "left", "magnitudes_control": ["licencias", "viviendas_licencia"],
     "agregar_antes": {"grano": "barrio", "medidas": {"licencias": "recuento de filas", "viviendas_licencia": "suma de viviendas"}}},
    {"orden": 4, "partida": "hechos_anuncios", "se_une": "dim_barrio", "clave_partida": ["neighbourhood_cleansed"], "clave_une": ["barrio"], "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["price", "estimated_occupancy_l365d"], "agregar_antes": None},
    {"orden": 5, "partida": "hechos_anuncios", "se_une": "hechos_calendario", "clave_partida": ["id"], "clave_une": ["listing_id"], "cardinalidad": "1:1", "tipo_cruce": "left", "magnitudes_control": ["price", "dias_calendario"],
     "agregar_antes": {"grano": "listing_id", "medidas": {"estancia_calendario": "mínimo de minimum_nights", "dias_calendario": "recuento de días"}}},
    {"orden": 6, "partida": "hechos_anuncios", "se_une": "hechos_anuncios_junio", "clave_partida": ["id"], "clave_une": ["id"], "cardinalidad": "1:1", "tipo_cruce": "left", "magnitudes_control": ["price"], "agregar_antes": None},
    {"orden": 7, "partida": "hechos_anuncios", "se_une": "hechos_anuncios_marzo", "clave_partida": ["id"], "clave_une": ["id"], "cardinalidad": "1:1", "tipo_cruce": "left", "magnitudes_control": ["price"], "agregar_antes": None},
]


# ---------------------------------------------------------------------------
# 2. Comprobaciones
# ---------------------------------------------------------------------------

def leer_aprobacion():
    """Lee solo la línea de aprobación de la persona responsable; sin ella, no hay aprobación."""
    texto = DISENO.read_text(encoding="utf-8") if DISENO.exists() else ""
    m = re.search(r"^Aprobado: sí · (.+) · (\d{4}-\d{2}-\d{2})\s*$", texto, flags=re.M)
    return {"aprobado": bool(m), "fecha": m.group(2) if m else None, "quien": m.group(1) if m else None}


def comprobar_tabla(cfg):
    """Comprueba una tabla del diseño sin cargarla entera más de lo que pide su clave."""
    ruta = rc.PROCESADO / rc.CORREGIDA[cfg["clave_corregida"]]
    df = pd.read_parquet(ruta, columns=cfg["columnas"])
    fila = {k: cfg[k] for k in ("tabla", "grano", "clave_grano", "tipo")}
    fila.update(fichero=ruta.relative_to(rc.CASO).as_posix(), filas=len(df), clave_unica=None, filas_repetidas=None,
                columnas_que_faltan=[c for c in cfg["columnas"] if c not in df.columns])
    if cfg["clave_grano"]:
        repetidas = int(df.duplicated(cfg["clave_grano"]).sum())
        fila.update(clave_unica=repetidas == 0, filas_repetidas=repetidas)
    return fila, df


def recuentos_de_exclusiones(sep, cal, dec):
    """Cuenta cada clase del registro de exclusiones; mira el calendario por clave, sin unir filas."""
    t = sep.assign(precio=sep["price"], ocupacion=sep["estimated_occupancy_l365d"])
    t["dentro"] = shapely.contains_xy(cd.leer_limite(), t["longitude"].to_numpy(), t["latitude"].to_numpy())
    t["estancia"] = t["minimum_nights"].fillna(t["id"].map(cal.groupby("listing_id")["minimum_nights"].min()))
    m = rc.exclusiones(t, dec)
    ingreso = t["precio"] * t["ocupacion"]
    filas = []
    for columna, que, calculo, trato, porque, recupera, _ in rc.EXCLUSIONES:
        filas.append({"clase": columna, "que_sale": que, "de_que_calculo": calculo, "como_se_trata": trato, "por_que": porque, "recuperable": recupera,
                      "filas": int(m[columna].sum()), "ingreso_eur": round(float(ingreso[m[columna]].sum()), 2)})
    return filas


# ---------------------------------------------------------------------------
# 3. Informe
# ---------------------------------------------------------------------------

def informe(s):
    """Genera el Markdown a partir del diccionario que se guarda en el JSON."""
    r = ["# Modelado de datos · caso", "", s["resultado"].get("resumen", ""), "", "## Tablas", ""]
    r += [f"- `{t['tabla']}` ({t['tipo']}): {t['filas']} filas; {t['grano']}; clave {', '.join(t['clave_grano']) or 'ninguna'}, única {t['clave_unica']}." for t in s.get("tablas", [])]
    r += ["", "## Relaciones", ""] + [f"- {x['desde']} → {x['hacia']}: {x['cardinalidad']}, mismo tipo {x.get('mismo_tipo')}; {x['procedencia']}." for x in s.get("relaciones", [])]
    r += ["", "## Fechas", ""] + [f"- {k}: {v}." for k, v in s.get("fechas", {}).items()]
    r += ["", "## Plan de cruces", ""] + [f"- {c['orden']}. {c['partida']} con {c['se_une']}, {c['cardinalidad']}, por {', '.join(c['clave_partida'])}." for c in s.get("plan_cruces", [])]
    r += ["", "## Registro de exclusiones", "", "| Clase | Qué sale | De qué cálculo | Cómo se trata | Por qué | Se recupera | Filas | Ingreso (€) |", "|---|---|---|---|---|---|---|---|"]
    r += [f"| {e['clase']} | {e['que_sale']} | {e['de_que_calculo']} | {e['como_se_trata']} | {e['por_que']} | {e['recuperable']} | {e['filas']} | {e['ingreso_eur']} |" for e in s.get("registro_exclusiones", [])]
    r += ["", "## Aprobación", "", f"Aprobado: {s.get('aprobado', {}).get('aprobado')}. Se sigue por: {s.get('seguir_sin_aprobacion')}.", "",
          "",
          "## Datos personales", "", rc.texto_personales("Este paso solo mira claves y recuentos: no copia ningún valor de las columnas de licencia."), "",
          "## Observaciones", "", "- El script comprueba el grano y los tipos de las claves; si las claves casan entre tablas lo mide `integracion-datos`.",
          "- En pandas, a diferencia de SQL, las claves vacías se emparejan entre sí al cruzar.", "- Un maestro que cambia con el tiempo se modela con la versión que hay, no con la vigente en la fecha de cada hecho.", ""]
    return "\n".join(r)


# ---------------------------------------------------------------------------
# 4. Ejecución
# ---------------------------------------------------------------------------

def principal(s):
    """Comprueba el diseño y escribe el plan de cruces."""
    correccion = json.loads((rc.INFORMES / "correccion-datos.json").read_text(encoding="utf-8"))
    if correccion["resultado"]["estado"] in ("PARADO", "ERROR"):
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "La corrección está parada.", "artefactos": [], "siguiente": "repetir correccion-datos"}
        return s
    dec = rc.leer_decisiones()
    tablas, datos = [], {}
    for cfg in TABLAS:
        fila, df = comprobar_tabla(cfg)
        tablas.append(fila)
        datos[cfg["tabla"]] = df
    s["tablas"] = tablas
    s["entradas"] = [{"ruta": x["ruta"], "sha256": x["sha256"], "filas": x["filas"], "columnas": x["columnas"]} for x in correccion["salidas"]]

    # 4.1 Las claves de cada relación tienen que tener el mismo tipo a los dos lados.
    relaciones = []
    for x in RELACIONES:
        a = datos[x["desde"]][x["clave_desde"][0]].dtype
        b = datos[x["hacia"]][x["clave_hacia"][0]].dtype
        relaciones.append({**x, "mismo_tipo": str(a) == str(b)})
    s["relaciones"] = relaciones

    # 4.2 Fechas: rango y periodos completos. No hace falta tabla Calendario: las dos tablas mensuales ya llevan su mes.
    cal, res = datos["hechos_calendario"], datos["hechos_resenas"]
    desde, hasta = cal["date"].min(), cal["date"].max()
    s["fechas"] = {"calendario_desde": desde.date().isoformat(), "calendario_hasta": hasta.date().isoformat(), "calendario_primer_mes_completo": bool(desde.day == 1),
                   "calendario_ultimo_mes_completo": bool(hasta.is_month_end), "resenas_desde": res["date"].min().date().isoformat(), "resenas_hasta": res["date"].max().date().isoformat()}
    s["calendario"] = {"periodo": "mes", "desde": s["fechas"]["resenas_desde"], "hasta": s["fechas"]["calendario_hasta"], "primer_periodo_completo": False, "ultimo_periodo_completo": False, "fichero": None}

    # 4.3 Registro de exclusiones, con los recuentos sacados del código.
    sep = pd.read_parquet(rc.PROCESADO / rc.CORREGIDA["sep"])
    s["registro_exclusiones"] = recuentos_de_exclusiones(sep, cal, dec)
    s["forma_entrega"] = "tablas_separadas"
    s["plan_cruces"] = PLAN_CRUCES
    s["diseno"] = "config/modelo/modelo-datos.md"
    s["aprobado"] = leer_aprobacion()
    s["seguir_sin_aprobacion"] = None if s["aprobado"]["aprobado"] else SEGUIR
    faltan = [t["tabla"] for t in tablas if t["columnas_que_faltan"]]
    repetidas = [t["tabla"] for t in tablas if t["clave_unica"] is False]
    tipos_mal = [f"{x['desde']}→{x['hacia']}" for x in relaciones if not x["mismo_tipo"]]
    if faltan or repetidas or tipos_mal:
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": f"El diseño no se cumple. Columnas: {faltan}; claves repetidas: {repetidas}; tipos: {tipos_mal}.", "artefactos": ["informes/modelado-datos.json", "informes/modelado-datos.md"], "siguiente": "revisar el diseño"}
        return s
    estado = "OK" if s["aprobado"]["aprobado"] else "AVISO"
    s["resultado"] = {"estado": estado, "riesgo": "bajo" if estado == "OK" else "medio", "resumen": f"El diseño se cumple en {len(tablas)} tablas y deja {len(PLAN_CRUCES)} cruces. " + ("Está aprobado." if estado == "OK" else f"Sin aprobación escrita: {SEGUIR}."),
                      "artefactos": ["informes/modelado-datos.json", "informes/modelado-datos.md"], "siguiente": "integracion-datos"}
    return s


def ejecutar():
    """Lanza la comprobación y, si algo falla, deja el JSON con estado ERROR antes de avisar."""
    s = rc.bloque_comun(SKILL, VERSION, SCRIPT)
    try:
        s = principal(s)
    except Exception as error:
        rc.parar_con_error(s, "modelado-datos", error, informe)
        raise
    rc.guardar(s, "modelado-datos", informe)
    print(s["resultado"]["estado"], s["resultado"]["resumen"])
    return 0


if __name__ == "__main__":
    raise SystemExit(ejecutar())
