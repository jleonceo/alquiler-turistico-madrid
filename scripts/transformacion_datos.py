"""Transformación del caso: deja las cinco tablas de análisis en data/processed/, en Parquet.

Parte de anuncios_integrado y barrios_integrado y de las tablas corregidas. Calcula lado del centro, distancia al borde,
estancia, superficies, compra, rentabilidad, atractivo y las marcas de cada base, y repite las 12 repeticiones de la regla del
grupo. Si una validación falla o el grupo cambia, no guarda ninguna tabla. Escribe informes/transformacion-datos.json,
de él informes/transformacion-datos.md y config/negocio/03_riesgos_de_calidad.md.

Se lanza después de scripts/integracion_datos.py. Con --sin-riesgos no reescribe 03_riesgos_de_calidad.md, para una ejecución
cuyo alcance no llega a negocio/.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/transformacion_datos.py
"""
import json
import sys

import numpy as np
import pandas as pd
import pyproj
import shapely

import calidad_datos as cd
import reglas_caso as rc

# ---------------------------------------------------------------------------
# 1. Configuración
# ---------------------------------------------------------------------------

ETAPA = "transformacion-datos"
VERSION = "06/10/2026 (SC-64)"
SCRIPT = "scripts/transformacion_datos.py"
RIESGOS = rc.CASO / "config" / "negocio" / "03_riesgos_de_calidad.md"
CRS_METROS = 25830  # ETRS89 / UTM 30N, el sistema proyectado de Madrid
FECHA_REF = pd.Timestamp(rc.FECHA_DATOS)
TABLAS = {"anuncios": "analisis_anuncios", "barrios": "analisis_barrios", "oferta": "evolucion_oferta", "resenas": "estacionalidad_resenas", "dispo": "disponibilidad_futura"}
RENOMBRE = {"neighbourhood_cleansed": "barrio", "neighbourhood_group_cleansed": "distrito", "room_type": "tipo_alquiler", "property_type": "tipo_inmueble", "accommodates": "huespedes", "bedrooms": "dormitorios",
            "beds": "camas", "availability_365": "dias_libres_365", "number_of_reviews_ltm": "resenas_ultimo_ano", "number_of_reviews_l30d": "resenas_ultimo_mes", "latitude": "latitud", "longitude": "longitud"}
# Fórmula y columnas de origen de cada variable nueva, para el informe.
VARIABLES = [
    ("lado_centro", "punto dentro o fuera del polígono del APE 00.01", ["latitude", "longitude"], None),
    ("distancia_borde_m", "distancia en EPSG:25830 del punto al límite", ["latitude", "longitude"], "m"),
    ("lado_incierto", "distancia al borde menor de 150 m", ["distancia_borde_m"], None),
    ("estancia_noches", "la publicada; si está vacía, la menor del calendario", ["minimum_nights", "estancia_calendario"], "noches"),
    ("estancia_origen", "publicada, calendario o sin dato", ["minimum_nights", "estancia_calendario"], None),
    ("precio_eur", "precio publicado", ["price"], "EUR"),
    ("ocupacion_dias", "estimación de la fuente", ["estimated_occupancy_l365d"], "días"),
    ("ingreso_anual_eur", "precio_eur × ocupacion_dias", ["price", "estimated_occupancy_l365d"], "EUR"),
    ("superficie_valoraciones_m2", "regla de habitaciones y baños", ["bedrooms", "banos"], "m²"),
    ("superficie_oficial_m2", "superficie media del barrio; la del distrito en los barrios marcados sin dato propio", ["sup_barrio", "sup_distrito"], "m²"),
    ("precio_m2_eur", "precio del barrio; el del distrito en San Andrés, Ambroz y Aeropuerto", ["m2_barrio", "m2_distrito"], "EUR/m²"),
    ("compra_*_eur", "superficie × precio_m2_eur, con cada superficie", ["superficie_valoraciones_m2", "superficie_oficial_m2", "precio_m2_eur"], "EUR"),
    ("rent_*_pct", "100 × ingreso_anual_eur / compra_*_eur, con cada combinación", ["ingreso_anual_eur", "compra_*_eur"], "%"),
    ("precio_vivienda_comparacion_eur", "reglas §3: lleva el precio de una habitación a la vivienda", ["price", "room_type", "bedrooms", "accommodates"], "EUR"),
    ("competencia_anuncios", "anuncios del barrio en la foto", ["neighbourhood_cleansed"], "anuncios"),
    ("puntos_interes_500m", "puntos de interés a menos de 500 m, sin pesos", ["latitude", "longitude", "x", "y"], "puntos"),
    ("anuncios_anfitrion", "anuncios del anfitrión en la descarga, según la fuente", ["calculated_host_listings_count"], "anuncios"),
    ("dias_cotizacion", "días entre la descarga de septiembre y la entrada de su cotización", ["price_quote_checkin_date"], "días"),
    ("dias_cotizacion_mar", "lo mismo con la descarga de marzo", ["price_quote_checkin_date"], "días"),
    ("dias_cotizacion_jun", "lo mismo con la descarga de junio", ["price_quote_checkin_date"], "días"),
]


# ---------------------------------------------------------------------------
# 2. Cálculos
# ---------------------------------------------------------------------------

def proyectar(lon, lat):
    """Pasa coordenadas a metros, en EPSG:25830."""
    return pyproj.Transformer.from_crs(4326, CRS_METROS, always_xy=True).transform(lon, lat)


def geografia(t, limite, puntos, dec):
    """Calcula lado, distancia al borde y puntos de interés a menos del radio, en metros."""
    lon, lat = t["longitude"].to_numpy(), t["latitude"].to_numpy()
    dentro = shapely.contains_xy(limite, lon, lat)
    xs, ys = proyectar(lon, lat)
    anuncios = shapely.points(xs, ys)
    bx, by = proyectar(*np.array(limite.exterior.coords).T)
    distancia = shapely.distance(shapely.LinearRing(np.column_stack([bx, by])), anuncios)
    px, py = proyectar(puntos["x"].to_numpy(), puntos["y"].to_numpy())
    pts = shapely.points(px, py)
    radio = dec["radio_atractivo_m"]
    i, j = shapely.STRtree(pts).query(anuncios, predicate="dwithin", distance=radio)
    cerca = shapely.distance(anuncios[i], pts[j]) < radio
    return dentro, distancia, np.bincount(i[cerca], minlength=len(t)).astype("int64")


def oficial_del_barrio(b):
    """Resuelve precio y superficie oficiales de cada barrio con su origen (reglas §2, CP-003)."""
    d = b.copy()
    toma = d["toma_precio_de_distrito"]
    d["precio_m2_eur"] = d["m2_distrito"].where(toma, d["m2_barrio"])
    d["precio_m2_origen"] = np.select([d["precio_m2_eur"].isna(), toma], ["sin dato", "distrito"], default="barrio")
    d["superficie_oficial_m2"] = d["sup_barrio"].where(~(toma & d["sup_barrio"].isna()), d["sup_distrito"])
    d["superficie_oficial_origen"] = np.select([d["superficie_oficial_m2"].isna(), toma & d["sup_barrio"].isna()], ["sin dato", "distrito"], default="barrio")
    return d


def precio_de_vivienda(t, tasa):
    """Lleva el precio al de la vivienda (reglas §3). Una habitación sin habitaciones conocidas queda vacía: la regla no la cubre."""
    p, d, h = t["precio"], t["bedrooms"], t["accommodates"]
    privada, compartida = t["room_type"].eq("Private room"), t["room_type"].eq("Shared room")
    condiciones = [t["room_type"].eq("Entire home/apt"), privada & d.eq(1), privada & d.gt(1), compartida & h.eq(1), compartida & h.gt(1)]
    return pd.Series(np.select(condiciones, [p, p, p * d * tasa, p, p * h * tasa], default=np.nan), index=t.index)


def anadir_compra_y_rentabilidad(df):
    """Calcula compra y rentabilidad con cada superficie (reglas §2)."""
    for sup, col in (("valoraciones", "superficie_valoraciones_m2"), ("oficial", "superficie_oficial_m2")):
        df[f"compra_{sup}_eur"] = df[col] * df["precio_m2_eur"]
        df[f"rent_{sup}_pct"] = 100 * df["ingreso_anual_eur"] / df[f"compra_{sup}_eur"]
    return df


def dias_hasta_cotizacion(fechas, foto):
    """Cuenta los días entre la descarga y la entrada de la cotización. Un anuncio sin precio no tiene cotización y queda vacío."""
    return (pd.to_datetime(fechas, format="%Y-%m-%d") - pd.Timestamp(foto)).dt.days.astype("float64")


def tabla_anuncios(t, barrios, limite, puntos, dec, cotizaciones):
    """Construye la tabla de una fila por anuncio de septiembre. cotizaciones trae la fecha de cada anuncio en marzo y en junio."""
    df = t.copy()
    df["dentro"], df["distancia_borde_m"], df["puntos_interes_500m"] = geografia(df, limite, puntos, dec)
    df["lado_centro"] = np.where(df["dentro"], "dentro", "fuera")
    df["lado_incierto"] = df["distancia_borde_m"].lt(dec["borde_incierto_m"])
    df["estancia"] = df["minimum_nights"].astype("Float64").fillna(df["estancia_calendario"].astype("Float64")).astype("float64")
    df["estancia_origen"] = np.select([df["minimum_nights"].notna(), df["estancia_calendario"].notna()], ["publicada", "calendario"], default="sin dato")
    df["precio"] = df["price"]
    df["ocupacion"] = df["estimated_occupancy_l365d"]
    df["ingreso_anual_eur"] = df["precio"] * df["ocupacion"]
    df["superficie_valoraciones_m2"] = cd.superficie_regla(df)
    df = df.merge(barrios[["barrio", "precio_m2_eur", "precio_m2_origen", "superficie_oficial_m2", "superficie_oficial_origen"]], left_on="neighbourhood_cleansed", right_on="barrio", how="left", validate="many_to_one", suffixes=("_x", ""))
    df = df.drop(columns=[c for c in df.columns if c.endswith("_x")])
    df = anadir_compra_y_rentabilidad(df)
    df["competencia_anuncios"] = df.groupby("neighbourhood_cleansed")["id"].transform("size").astype("int64")
    # Una columna entera vacía salió en la corrección (CP-013): aquí vuelve vacía, porque el análisis la espera.
    vacia = pd.Series(pd.NA, index=df.index, dtype="str")
    df["tipo_licencia"] = df["licencia_nacional"] if "licencia_nacional" in df else vacia
    df["exencion_licencia"] = df["licencia_exencion"] if "licencia_exencion" in df else vacia
    df["declara_temporada"] = df["exencion_licencia"].eq("temporada").fillna(False).astype("bool")
    df["anuncios_anfitrion"] = df["calculated_host_listings_count"].astype("int64")
    df["dias_cotizacion"] = dias_hasta_cotizacion(df["price_quote_checkin_date"], rc.FOTOS["sep"])
    for clave in ("mar", "jun"):
        df[f"dias_cotizacion_{clave}"] = df["id"].map(dias_hasta_cotizacion(cotizaciones[clave].set_index("id")["price_quote_checkin_date"], rc.FOTOS[clave]))
    df["precio_vivienda_comparacion_eur"] = precio_de_vivienda(df, dec["tasa_de_uso"])
    marcas = rc.exclusiones(df, dec)
    df = pd.concat([df, marcas], axis=1)
    df["base_decision"], df["base_comparacion"] = rc.bases(marcas)
    return df, marcas


def vista_de_calidad(df):
    """Deja las columnas con los nombres que usan las funciones de grupo de calidad_datos.py."""
    return pd.DataFrame({"id": df["id"], "barrio": df["neighbourhood_cleansed"], "piso": df["room_type"].eq("Entire home/apt"), "dentro": df["dentro"], "ocupacion": df["ocupacion"], "accommodates": df["accommodates"], "banos": df["banos"],
                         "bedrooms": df["bedrooms"], "beds": df["beds"], "estancia": df["estancia"], "precio": df["precio"], "p_mar": df["precio_mar"], "p_jun": df["precio_jun"], "sup_regla": df["superficie_valoraciones_m2"],
                         "m2": df["precio_m2_eur"], "temporada": df["declara_temporada"], "property_type": df["property_type"],
                         "anuncios_anfitrion": df["anuncios_anfitrion"], "dias_cotizacion": df["dias_cotizacion"], "dias_cotizacion_mar": df["dias_cotizacion_mar"], "dias_cotizacion_jun": df["dias_cotizacion_jun"]})


def control_del_grupo(df, marcas, dec):
    """Repite las 12 repeticiones sin los pisos que quitan CP-007 a CP-009, compara con intervalo y clasifica el grupo con las cinco pruebas."""
    L = vista_de_calidad(df)
    quitados = marcas["excl_cero_banos"] | marcas["excl_no_vivienda"] | marcas["excl_tamano_incoherente"]
    antes, despues = cd.medir(L), cd.medir(L, excluir=quitados)
    comparacion = cd.comparar(antes, despues)
    pruebas = rc.pruebas_del_grupo(L, quitados, dec["pruebas_del_grupo"])
    return {"pisos_antes": antes["pisos"], "pisos_despues": despues["pisos"], "grupo": despues["grupo"], "firmes": pruebas["firmes"], "con_aviso": pruebas["con_aviso"], "segunda_linea": pruebas["segunda_linea"],
            "pruebas_por_barrio": {b: x["aguanta"] for b, x in pruebas["barrios"].items()},
            "variantes_por_barrio": despues["variantes_por_barrio"], "variantes_antes": antes["variantes_por_barrio"], "barrios_comparados": despues["barrios_comparados"], "grupo_antes": antes["grupo"], "tras_temporada_antes": antes["firmes"], "tras_temporada_despues": despues["firmes"],
            "comparacion_con_intervalo": {"veredicto": cd.veredicto_de(comparacion), **{k: comparacion[k] for k in ("cambia_grupo", "cambia_firmes", "cambia_tipo", "grupo_entran", "grupo_salen", "firmes_entran", "firmes_salen", "pares_entran_salen", "pares_que_cambian", "pares_del_grupo_que_cambian")}}}


def embudo_y_exclusiones(df, marcas):
    """Cuenta qué quita cada regla en orden y cruza cada exclusión con si deja fuera a los más alquilados."""
    de_decision = [c for c, *_, base in rc.EXCLUSIONES if base in ("decision", "ambas")]
    vivo = pd.Series(True, index=df.index)
    embudo = []
    for c in de_decision:
        quita = int((vivo & marcas[c]).sum())
        vivo &= ~marcas[c]
        embudo.append({"regla": c, "quita": quita, "quedan": int(vivo.sum())})
    # «Los más alquilados»: el cuarto de pisos con más ocupación, y por separado con más reseñas en el último mes, porque la ocupación se infla con estancias largas.
    # Se mira qué parte de ellos quita cada regla frente a qué parte de todos quita: si quita más de ellos, los deja fuera.
    con_ocupacion = df["ocupacion"].gt(0)
    pisos = df["room_type"].eq("Entire home/apt") & ~df["dentro"] & con_ocupacion
    umbral = float(df.loc[pisos, "ocupacion"].quantile(0.75)) if pisos.any() else None
    umbral_resenas = float(df.loc[pisos, "number_of_reviews_l30d"].quantile(0.75)) if pisos.any() else None
    filas = []
    for c, que, *_ in rc.EXCLUSIONES:
        m = marcas[c]
        otras = [o for o in de_decision if o != c]
        solo = int((m & ~marcas[otras].any(axis=1)).sum()) if c in de_decision else None
        # El universo de cada regla es donde puede actuar: las dos primeras definen el piso de fuera; la de ocupación no tiene más alquilados que quitar.
        universo = con_ocupacion if c in ("excl_no_piso_completo", "excl_dentro_centro") else pisos
        if c == "excl_sin_ocupacion" or not universo.any():
            quita = altos = resenas_altas = None
        else:
            quita = round(100 * float(m[universo].mean()), 2)
            alto = universo & df["ocupacion"].ge(umbral)
            activo = universo & df["number_of_reviews_l30d"].ge(umbral_resenas)
            altos = round(100 * float(m[alto].mean()), 2) if alto.any() else None
            resenas_altas = round(100 * float(m[activo].mean()), 2) if activo.any() else None
        filas.append({"clase": c, "que_sale": que, "filas": int(m.sum()), "solo_por_esta": solo, "ocupacion_mediana": float(df.loc[m, "ocupacion"].median()) if m.any() else None,
                      "resenas_ultimo_mes_mediana": float(df.loc[m, "number_of_reviews_l30d"].median()) if m.any() else None, "quita_pct": quita, "mas_alquilados_pct": altos, "mas_resenas_pct": resenas_altas,
                      "deja_fuera_a_los_mas_alquilados": bool(altos is not None and altos > quita)})
    return embudo, filas, {"umbral_ocupacion_mas_alquilados": umbral, "umbral_resenas_ultimo_mes": umbral_resenas, "universo": "pisos fuera del centro con ocupación; todos los anuncios con ocupación en las dos primeras reglas"}


def tabla_barrios(b, df):
    """Construye la tabla de una fila por barrio con su recuento y lo oficial, incluidas las licencias."""
    d = b.copy()
    g = df.groupby("neighbourhood_cleansed")
    d = d.set_index("barrio")
    d["anuncios"] = g.size().reindex(d.index).fillna(0).astype("int64")
    d["pisos_completos"] = df.loc[df["room_type"].eq("Entire home/apt")].groupby("neighbourhood_cleansed").size().reindex(d.index).fillna(0).astype("int64")
    d["anuncios_dentro_centro"] = df.loc[df["dentro"]].groupby("neighbourhood_cleansed").size().reindex(d.index).fillna(0).astype("int64")
    d["pisos_base_decision"] = df.loc[df["base_decision"]].groupby("neighbourhood_cleansed").size().reindex(d.index).fillna(0).astype("int64")
    d["anuncios_base_comparacion"] = df.loc[df["base_comparacion"]].groupby("neighbourhood_cleansed").size().reindex(d.index).fillna(0).astype("int64")
    # Un barrio que no sale en el registro de licencias no tiene ninguna en él: es un recuento, no un dato que falte.
    d["licencias"] = d["licencias"].fillna(0).astype("int64")
    d["viviendas_licencia"] = d["viviendas_licencia"].fillna(0).astype("int64")
    columnas = ["distrito", "anuncios", "pisos_completos", "anuncios_dentro_centro", "pisos_base_decision", "anuncios_base_comparacion", "precio_m2_eur", "precio_m2_origen", "superficie_oficial_m2", "superficie_oficial_origen", "ventas_barrio", "licencias", "viviendas_licencia"]
    return d[columnas].reset_index()


def tabla_oferta(fotos, barrios):
    """Cuenta anuncios y pisos por descarga y barrio; todos los barrios en todas las fotos, porque un recuento de una descarga entera sí vale cero."""
    filas = []
    for clave, t in fotos.items():
        g = t.groupby("neighbourhood_cleansed")
        x = barrios[["barrio", "distrito"]].copy()
        x["foto"] = pd.Timestamp(rc.FOTOS[clave])
        x["anuncios"] = x["barrio"].map(g.size()).fillna(0).astype("int64")
        x["pisos_completos"] = x["barrio"].map(t.loc[t["room_type"].eq("Entire home/apt")].groupby("neighbourhood_cleansed").size()).fillna(0).astype("int64")
        filas.append(x)
    return pd.concat(filas, ignore_index=True)[["foto", "barrio", "distrito", "anuncios", "pisos_completos"]]


def tabla_resenas(res):
    """Cuenta reseñas por mes, sin rellenar los meses sin reseñas: no se sabe si no hubo actividad."""
    t = res.assign(mes=res["date"].dt.to_period("M").dt.to_timestamp()).groupby("mes", as_index=False).agg(resenas=("date", "size")).sort_values("mes").reset_index(drop=True)
    t["mes_incompleto"] = t["mes"].ge(FECHA_REF.to_period("M").to_timestamp())
    todos = pd.date_range(t["mes"].min(), t["mes"].max(), freq="MS")
    return t, len(todos) - len(t)


def tabla_disponibilidad(cal):
    """Cuenta días y días libres por anuncio y mes, y marca los meses que el calendario no cubre enteros."""
    t = cal.assign(mes=cal["date"].dt.to_period("M").dt.to_timestamp())
    d = t.groupby(["listing_id", "mes"], as_index=False).agg(dias_calendario=("date", "size"), dias_libres=("available", "sum"))
    d = d.rename(columns={"listing_id": "id"})
    d["dias_libres"] = d["dias_libres"].astype("int64")
    d["mes_completo"] = d["dias_calendario"].eq(d["mes"].dt.days_in_month)
    return d


# ---------------------------------------------------------------------------
# 3. Fichas, riesgos e informe
# ---------------------------------------------------------------------------

def fichas_de(s):
    """Monta las fichas de la transformación con las cifras de esta ejecución."""
    deshacer = "quitar la regla de scripts/transformacion_datos.py y volver a lanzarlo; las tablas de entrada no cambian."
    f = {x["tabla"]: x["filas"] for x in s["salidas"]}
    g = s["control_grupo"]
    comun = dict(estaba="tablas corregidas e integradas.", deshacer=deshacer)
    return [
        {**comun, "clave": "transformacion-anuncios", "titulo": "Tabla de análisis por anuncio", "tabla": "analisis_anuncios.parquet, todas", "problema": "las tres preguntas piden una fila por piso de septiembre.", "decision": "reglas §1 a §7 y reglas-transformacion.md §1.",
         "hecho": "lado, distancia, estancia, ingreso, superficies, compra, rentabilidad, licencia y marcas de exclusión.", "codigo": "df['ingreso_anual_eur'] = df['precio'] * df['ocupacion']\ndf[f'rent_{sup}_{clave}_pct'] = 100 * df['ingreso_anual_eur'] / df[f'compra_{sup}_{clave}_eur']",
         "comprobacion": f"{f['analisis_anuncios']} filas, tantas como anuncios; id único.", "quedo": f"{f['analisis_anuncios']} filas."},
        {**comun, "clave": "transformacion-bases", "titulo": "Base de decisión y base de comparación", "tabla": "analisis_anuncios.parquet, `base_decision`, `base_comparacion`, `excl_*`, `comp_excl_*`", "problema": "cada uso tiene su población.", "decision": "reglas §3 y CP-001, CP-006 a CP-010. CP-007 a CP-009 valen solo para la base de decisión.",
         "hecho": "una marca por exclusión; ninguna fila sale de la tabla.", "codigo": "base_decision = ~marcas[de_decision].any(axis=1)", "comprobacion": f"base de decisión {s['bases']['decision']}; base de comparación {s['bases']['comparacion']}; 12 repeticiones repetidas: {g['comparacion_con_intervalo']['veredicto']}.",
         "quedo": f"grupo de {len(g['grupo'])} barrios y {len(g['firmes'])} firmes."},
        {**comun, "clave": "transformacion-atractivo", "titulo": "Atractivo: puntos a menos de 500 m", "tabla": "analisis_anuncios.parquet, `puntos_interes_500m`", "problema": "reglas §3 deja la distancia y el peso al planteamiento.", "decision": "**Supuesto**: recuento simple a menos de 500 m, unos seis minutos andando, sin pesos, porque no hay base para fijarlos. No entra en la rentabilidad.",
         "hecho": "recuento con coordenadas en EPSG:25830.", "codigo": "i, j = shapely.STRtree(pts).query(anuncios, predicate='dwithin', distance=500)\ncerca = shapely.distance(anuncios[i], pts[j]) < 500", "comprobacion": f"mediana {s['atractivo']['mediana']}, máximo {s['atractivo']['maximo']}; {s['atractivo']['puntos']} puntos.", "quedo": "una columna entera, sin vacíos."},
        {**comun, "clave": "transformacion-barrios", "titulo": "Tabla de análisis por barrio", "tabla": "analisis_barrios.parquet", "problema": "competencia, contexto oficial y licencias van por barrio.", "decision": "reglas §1, §6 y §7. La superficie oficial de un barrio marcado sin dato propio toma la de su distrito (**Supuesto**, igual que el reconocimiento).", "hecho": "recuentos y datos oficiales con su origen.",
         "codigo": "d['precio_m2_eur'] = d['m2_distrito'].where(toma, d['m2_barrio'])", "comprobacion": f"{f['analisis_barrios']} barrios; los anuncios suman la descarga y las licencias suman su fuente.", "quedo": f"{f['analisis_barrios']} filas."},
        {**comun, "clave": "transformacion-oferta", "titulo": "Evolución de la oferta", "tabla": "evolucion_oferta.parquet", "problema": "la pregunta 3 mira el rango entre descargas.", "decision": "reglas §3; una descarga no se compara con otra sin decirlo.", "hecho": "anuncios y pisos por descarga y barrio.", "codigo": "t.groupby('neighbourhood_cleansed').size()",
         "comprobacion": f"{f['evolucion_oferta']} filas; cada descarga suma sus anuncios.", "quedo": f"{f['evolucion_oferta']} filas."},
        {**comun, "clave": "transformacion-resenas", "titulo": "Estacionalidad de las reseñas", "tabla": "estacionalidad_resenas.parquet", "problema": "estacionalidad.", "decision": "datos necesarios §2. La reseña es un flujo; un mes sin reseñas no se rellena, porque no se sabe si no hubo actividad.", "hecho": "reseñas por mes.", "codigo": "res.groupby(mes).size()",
         "comprobacion": f"{s['resenas']['total']} reseñas antes y después; {s['resenas']['meses_sin_resenas']} meses sin reseñas dentro del rango.", "quedo": f"{f['estacionalidad_resenas']} meses."},
        {**comun, "clave": "transformacion-disponibilidad", "titulo": "Disponibilidad futura", "tabla": "disponibilidad_futura.parquet", "problema": "días libres de los próximos 12 meses.", "decision": "El calendario no distingue reservado de bloqueado (reglas §2).", "hecho": "días y días libres por anuncio y mes, con marca de mes completo.", "codigo": "t.groupby(['listing_id', 'mes']).agg(...)",
         "comprobacion": f"{s['disponibilidad']['dias']} días y {s['disponibilidad']['libres']} libres antes y después.", "quedo": f"{f['disponibilidad_futura']} filas."},
        {**comun, "clave": "transformacion-cinco-pruebas", "titulo": "Columnas para las cinco pruebas del grupo", "tabla": "analisis_anuncios.parquet, `anuncios_anfitrion`, `dias_cotizacion`, `dias_cotizacion_mar`, `dias_cotizacion_jun`", "problema": "reglas §3: el grupo recomendado se decide con cinco pruebas, y dos de ellas piden datos que la tabla no traía.",
         "decision": "reglas §3. Anuncios del anfitrión: `calculated_host_listings_count`, el recuento de la descarga. Cotización: cada descarga con su fecha, porque cada repetición usa el precio de una descarga. Ninguna fila sale de la base.", "hecho": "se añaden cuatro columnas; una cotización que falta queda vacía.",
         "codigo": "df['anuncios_anfitrion'] = df['calculated_host_listings_count']\ndf['dias_cotizacion'] = (pd.to_datetime(df['price_quote_checkin_date']) - foto).dt.days", "comprobacion": f"{s['cotizacion']['con_fecha']} anuncios con cotización de septiembre y {s['cotizacion']['sin_fecha_con_precio']} con precio sin fecha; {s['cotizacion']['lejanas']} a más de {s['cotizacion']['umbral_dias']} días; {s['cotizacion']['anfitriones_grandes']} anuncios de anfitriones con {s['cotizacion']['umbral_anuncios']} o más.",
         "quedo": f"{f['analisis_anuncios']} filas y cuatro columnas más; {len(g['firmes'])} firmes, {len(g['con_aviso'])} que siguen en la lista 4 veces y {len(g['segunda_linea'])} en resto del grupo.", "quien": "Juan Luis León"},
    ]


def lista_si(valor, vacio="ninguno"):
    """Une una lista para un texto."""
    return ", ".join(valor) if valor else vacio


def miles(n):
    """Escribe un entero con el punto de los miles."""
    return f"{n:,}".replace(",", ".")


def riesgos(s):
    """Redacta los riesgos de calidad en ocho familias, con las cifras de esta ejecución."""
    c, g, b, e = s["calidad"], s["control_grupo"], s["bases"], {x["clase"]: x for x in s["exclusiones"]}
    return f"""---
titulo: Riesgos de calidad de los datos del caso, en las ocho familias de la lista de comprobación
estado: generado por `scripts/transformacion_datos.py` el {s['fecha_ejecucion'][:10]}; generado por la cadena
fecha_documento: {s['fecha_ejecucion'][:10]}
dueno: Juan Luis León
fuente: `informes/calidad-datos.json`, `informes/correccion-datos.json`, `informes/transformacion-datos.json`
---

# Riesgos de calidad del caso

El riesgo que más pesa es de negocio: la ocupación es una estimación de la fuente y la superficie es un supuesto, de modo que la rentabilidad sirve para comparar barrios y no para prometer un rendimiento. Quien use las tablas de análisis debe leer cada cifra con esta lista delante.

## Esquema

Los libros oficiales llevaban código y nombre en una celda y se separaron. Las columnas `amenities` y `price_quote_raw` siguen guardando JSON dentro de una celda: ninguna pregunta las usa. Las fotos no tienen las mismas columnas, porque cada una pierde las que trae vacías, y diciembre no tiene precio.

## Valores

Quedan {miles(c['precio_vacio'])} anuncios de septiembre sin precio y no se rellenan. Las camas vacías son {miles(c['camas_vacias'])} y no pasan el máximo. El precio desde 2026 es un precio para unas fechas, con descuentos dentro, y no el precio medio del año.

## Registros

Hay {miles(c['captura'])} anuncios de captura anterior que se quedan, porque están entre los más alquilados. Un anuncio no es un inmueble: un piso puede tener varios anuncios y no se puede saber cuántos.

## Relaciones

Los cruces conservan filas y sumas. Airbnb junta en Casco Histórico de Vallecas lo que el Ayuntamiento separa, y por eso su precio oficial puede no representar todo su suelo. Las licencias no se unen a un anuncio: solo se cuentan por barrio. San Andrés, Ambroz y Aeropuerto llevan el precio de su distrito.

## Tiempo

Cada descarga es parcial respecto al año y no dice nada de la temporada de otros meses. La descarga de marzo y la de junio solo cubren los anuncios que siguen en septiembre con el mismo número. El primer mes y el último del calendario no están completos. Las reseñas de {s['resenas']['mes_incompleto']} son un mes incompleto.

## Negocio

- La ocupación tiene tope de 255 días y en la parte alta no ordena.
- La superficie de valoraciones es un supuesto.
- {miles(b['sin_ocupacion_pisos_fuera'])} pisos fuera del centro no tienen ocupación y quedan fuera del ranking: no hay ingreso que medir. Es un riesgo que hay que dar al lado de la cifra.
- {miles(e['excl_estancia_mas_de_3']['filas'])} anuncios tienen más de 3 noches de estancia y salen de la base de decisión.
- Cerca del borde del centro histórico hay {miles(b['lado_incierto'])} anuncios cuyo lado no se puede asegurar, porque las coordenadas vienen desplazadas hasta 150 m.
- Los datos no dicen si un piso concreto cumple la norma ni cuántas noches vendió.

## Modelado

El caso no entrena ningún modelo, así que no hay fuga ni desbalanceo que vigilar. Sí hay deriva entre descargas, y por eso el grupo se mide con el precio de marzo, junio y septiembre. La regla de los 180 días se queda solo en la base de comparación: quita el {e['comp_excl_menos_de_180_dias']['quita_pct']} % de los pisos fuera del centro con ocupación y el {e['comp_excl_menos_de_180_dias']['mas_alquilados_pct']} % de los más alquilados.

## Gobernanza

Cada cifra sale de un script de `scripts/` y cada regla tiene su ficha en el registro de transformaciones. El remuestreo que compara barrios lleva semilla fija ({cd.SEMILLA}). Los datos llegaron sin nombres ni textos libres, y quedan el número del anuncio, las coordenadas y el recuento de anuncios por anfitrión. El atractivo es un supuesto: {s['radio']} m, sin pesos. El diseño del modelo se usó sin la línea de aprobación de Juan, por orden del encargo.

## Límites

La base de decisión tiene {miles(b['decision'])} pisos y el grupo tiene {len(g['grupo'])} barrios, de los que {len(g['firmes'])} son firmes con las cinco pruebas: {lista_si(g['firmes'])}; {len(g['con_aviso'])} superan 4 pruebas: {lista_si(g['con_aviso'])}. Qué barrios se distinguen entre sí con intervalo se contesta en el análisis. Qué tiene realmente reservado un calendario no se puede saber: no distingue reservado de bloqueado. En la base de comparación, {s['sin_precio_de_vivienda']['anuncios_base_comparacion']} habitaciones quedan sin precio de vivienda, porque la regla no dice qué hacer con cero habitaciones.
"""


def informe(s):
    """Genera el Markdown a partir del diccionario que se guarda en el JSON."""
    r = ["# Informe de transformación de datos", "", "## Fuente", "", f"- Ejecución: {s['fecha_ejecucion']}, con Python {s['python']} y pandas {s['pandas']}.", "- Contexto: reglas-negocio.md, reglas-transformacion.md y modelo-datos.md.", ""]
    r += [f"- Entrada `{e['ruta']}`: {e['filas']} filas, huella {e['sha256']}." for e in s["entradas"]]
    r += ["", "## Objetivo", "", "Dejar las cinco tablas de análisis que piden las tres preguntas de la ficha.", "", s["resultado"].get("resumen", ""), "", "## Transformaciones aplicadas", ""]
    r += [f"- {t['id']}, {t['transformacion']}: {t['resultado']} Ficha {t['ficha']}." for t in s.get("transformaciones", [])]
    r += ["", "## Variables generadas", ""] + [f"- `{v['columna']}`: {v['formula']}. Sale de {', '.join(v['columnas_origen'])}. Unidad: {v['unidad']}." for v in s.get("variables_generadas", [])]
    r += ["- Marca de información posterior: ninguna variable se usa en un modelo, porque no lo hay. La ocupación y el ingreso miran el último año.", "", "## Transformaciones pendientes", ""]
    r += [f"- {p['id']}: {p['pregunta']}" for p in s["pendientes"]] or ["No hay."]
    r += ["", "## Cambios estructurales", ""]
    r += [f"- {c['antes']} → {c['despues']}: {[(x['magnitud'], x['antes'], x['despues'], x['coincide']) for x in c['sumas_control']]}." for c in s.get("cambios_granularidad", [])]
    r += ["", "### Cuántos quita cada regla, en orden", ""] + [f"- {x['regla']}: quita {x['quita']}; quedan {x['quedan']}." for x in s.get("embudo", [])]
    m = s.get("mas_alquilados", {})
    r += ["", "### Si cada exclusión deja fuera a los más alquilados", "", f"Más alquilados: ocupación de {m.get('umbral_ocupacion_mas_alquilados')} días o más; también se mira {m.get('umbral_resenas_ultimo_mes')} reseñas o más en el último mes. Universo: {m.get('universo')}. Una regla los deja fuera si quita más parte de ellos que del total.", ""]
    r += ["| Exclusión | Filas | Solo por esta | Ocupación mediana | Quita del total (%) | Quita de los más alquilados (%) | Quita de los de más reseñas (%) | Los deja fuera |", "|---|---|---|---|---|---|---|---|"]
    r += [f"| {x['clase']} | {x['filas']} | {x['solo_por_esta']} | {x['ocupacion_mediana']} | {x['quita_pct']} | {x['mas_alquilados_pct']} | {x['mas_resenas_pct']} | {x['deja_fuera_a_los_mas_alquilados']} |" for x in s.get("exclusiones", [])]
    g = s.get("control_grupo", {})
    r += ["", "### El grupo tras quitar CP-007, CP-008 y CP-009", ""]
    if g:
        r += [f"- Pisos: de {g['pisos_antes']} a {g['pisos_despues']}.", f"- Grupo: {lista_si(g['grupo'])}.", f"- Firmes: {lista_si(g['firmes'])}.", f"- De reserva: {lista_si(g['con_aviso'])}.", f"- Resto del grupo: {lista_si(g['segunda_linea'])}.", f"- Variantes por barrio: {g['variantes_por_barrio']}.", f"- Con intervalo: {g['comparacion_con_intervalo']['veredicto']}."]
    r += ["", "## Validación", ""] + [f"- {v['validacion']}: {v['resultado']}." for v in s.get("validaciones", [])]
    r += ["", "", "## Dataset generado", ""]
    r += [f"- `{x['ruta']}`: {x['filas']} filas y {x['columnas']} columnas; una fila es {x['que_es_una_fila']}." for x in s.get("salidas", [])] or ["No se guardó ninguna tabla."]
    r += ["", "## Datos personales", "", rc.texto_personales("Este paso usa `licencia_exencion` para saber qué pisos declaran temporada y deja el tipo de `licencia_nacional`, como descripción. No hay ningún número de licencia en los datos."), ""]
    return "\n".join(r)


# ---------------------------------------------------------------------------
# 4. Ejecución
# ---------------------------------------------------------------------------

def principal(s, con_riesgos=True):
    """Transforma, valida y guarda solo si todo pasa."""
    integ = json.loads((rc.INFORMES / "integracion-datos.json").read_text(encoding="utf-8"))
    if integ["resultado"]["estado"] in ("PARADO", "ERROR"):
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "Los cruces están parados.", "artefactos": [], "siguiente": "integracion-datos"}
        return s
    dec = rc.leer_decisiones()
    rutas = {"anuncios": rc.PROCESADO / "anuncios_integrado.parquet", "barrios": rc.PROCESADO / "barrios_integrado.parquet", **{k: rc.PROCESADO / rc.CORREGIDA[k] for k in ("calendario", "resenas", "puntos", "dic", "mar", "jun", "sep")}}
    huellas = {x["ruta"]: x["sha256"] for x in integ["salidas"]}
    for clave in ("anuncios", "barrios"):
        relativa = rutas[clave].relative_to(rc.CASO).as_posix()
        if cd.huella(rutas[clave]) != huellas.get(relativa):
            s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": f"La huella de {relativa} no es la que dejó la integración.", "artefactos": [], "siguiente": "repetir integracion-datos"}
            return s

    # 4.1 Lectura.
    t = pd.read_parquet(rutas["anuncios"])
    b = oficial_del_barrio(pd.read_parquet(rutas["barrios"]))
    cal = pd.read_parquet(rutas["calendario"])
    res = pd.read_parquet(rutas["resenas"])
    puntos = pd.read_parquet(rutas["puntos"])
    fotos = {k: pd.read_parquet(rutas[k], columns=["id", "neighbourhood_cleansed", "room_type"]) for k in ("dic", "mar", "jun", "sep")}
    s["entradas"] = [{**rc.entrada(rutas["anuncios"], t)}, {**rc.entrada(rutas["barrios"], b)}, rc.entrada(rutas["calendario"], cal), rc.entrada(rutas["resenas"], res), rc.entrada(rutas["puntos"], puntos)]
    s["radio"] = dec["radio_atractivo_m"]
    cotizaciones = {k: pd.read_parquet(rutas[k], columns=["id", "price_quote_checkin_date"]) for k in ("mar", "jun")}

    # 4.2 Las cinco tablas.
    df, marcas = tabla_anuncios(t, b, cd.leer_limite(), puntos, dec, cotizaciones)
    barrios = tabla_barrios(b, df)
    oferta = tabla_oferta(fotos, b)
    resenas, huecos = tabla_resenas(res)
    dispo = tabla_disponibilidad(cal)
    salida = df.drop(columns="barrio").rename(columns=RENOMBRE)
    salida = salida.rename(columns={"estancia": "estancia_noches", "precio": "precio_eur", "ocupacion": "ocupacion_dias", "precio_jun": "precio_jun_eur", "precio_mar": "precio_mar_eur", "banos": "banos"})
    columnas = ["id", "barrio", "distrito", "latitud", "longitud", "tipo_alquiler", "tipo_inmueble", "huespedes", "banos", "dormitorios", "camas", "lado_centro", "distancia_borde_m", "lado_incierto", "estancia_noches", "estancia_origen",
                "precio_eur", "ocupacion_dias", "ingreso_anual_eur", "dias_libres_365", "resenas_ultimo_ano", "resenas_ultimo_mes", "superficie_valoraciones_m2", "superficie_oficial_m2", "superficie_oficial_origen", "precio_m2_eur", "precio_m2_origen",
                "compra_valoraciones_eur", "compra_oficial_eur", "rent_valoraciones_pct", "rent_oficial_pct",
                "precio_mar_eur", "precio_jun_eur", "precio_vivienda_comparacion_eur", "competencia_anuncios", "puntos_interes_500m", "tipo_licencia", "exencion_licencia", "declara_temporada", "anuncios_anfitrion", "dias_cotizacion", "dias_cotizacion_mar", "dias_cotizacion_jun", "captura_anterior", *marcas.columns, "base_decision", "base_comparacion"]
    anuncios = salida[columnas]

    # 4.3 Control del grupo y cruce de cada exclusión.
    s["control_grupo"] = control_del_grupo(df, marcas, dec)
    r_pruebas = dec["pruebas_del_grupo"]
    s["cotizacion"] = {"con_fecha": int(df["dias_cotizacion"].notna().sum()), "sin_fecha_con_precio": int((df["precio"].notna() & df["dias_cotizacion"].isna()).sum()), "umbral_dias": r_pruebas["cotizacion_dias"], "lejanas": int(df["dias_cotizacion"].gt(r_pruebas["cotizacion_dias"]).sum()), "umbral_anuncios": r_pruebas["anfitrion_anuncios"], "anfitriones_grandes": int(df["anuncios_anfitrion"].ge(r_pruebas["anfitrion_anuncios"]).sum())}
    s["embudo"], s["exclusiones"], s["mas_alquilados"] = embudo_y_exclusiones(df, marcas)
    fuera = df["room_type"].eq("Entire home/apt") & ~df["dentro"]
    s["bases"] = {"decision": int(df["base_decision"].sum()), "comparacion": int(df["base_comparacion"].sum()), "sin_ocupacion_pisos_fuera": int((fuera & marcas["excl_sin_ocupacion"]).sum()), "lado_incierto": int(df["lado_incierto"].sum())}
    s["atractivo"] = {"puntos": len(puntos), "mediana": float(anuncios["puntos_interes_500m"].median()), "maximo": int(anuncios["puntos_interes_500m"].max()), "sin_ninguno": int(anuncios["puntos_interes_500m"].eq(0).sum())}
    s["resenas"] = {"total": len(res), "meses_sin_resenas": huecos, "mes_incompleto": resenas["mes"].max().strftime("%Y-%m")}
    s["disponibilidad"] = {"dias": len(cal), "libres": int(cal["available"].sum()), "meses_incompletos": int((~dispo["mes_completo"]).sum())}
    privadas = df["base_comparacion"] & df["precio_vivienda_comparacion_eur"].isna()
    s["sin_precio_de_vivienda"] = {"anuncios_base_comparacion": int(privadas.sum()), "con_cero_dormitorios": int((privadas & df["bedrooms"].eq(0)).sum()), "con_dormitorios_vacios": int((privadas & df["bedrooms"].isna()).sum())}

    # 4.4 Validaciones: si una falla, no se guarda nada.
    con = dec["controles"]
    ingreso_ok = int(((df["ingreso_anual_eur"] - df["estimated_revenue_l365d"]).abs() > 1).sum()) if "estimated_revenue_l365d" in df else None
    pruebas = [("una fila por anuncio y sin repetidos", len(anuncios) == len(t) and anuncios["id"].is_unique),
               ("los anuncios por barrio suman la foto", int(barrios["anuncios"].sum()) == len(t)), ("una fila por barrio", len(barrios) == len(b) and barrios["barrio"].is_unique),
               ("las licencias suman su fuente", int(barrios["licencias"].sum()) == len(pd.read_parquet(rc.PROCESADO / rc.CORREGIDA["licencias"], columns=["barrio"]))),
               ("cada foto suma sus anuncios", all(int(oferta.loc[oferta["foto"].eq(pd.Timestamp(rc.FOTOS[k])), "anuncios"].sum()) == len(v) for k, v in fotos.items())),
               ("las reseñas suman", int(resenas["resenas"].sum()) == len(res)), ("los días del calendario suman", int(dispo["dias_calendario"].sum()) == len(cal)), ("los días libres suman", int(dispo["dias_libres"].sum()) == int(cal["available"].sum())),
               ("una fila por anuncio y mes", not dispo.duplicated(["id", "mes"]).any()), ("el ingreso coincide con el de la fuente", ingreso_ok == 0), ("todos los barrios tienen precio del m²", b["precio_m2_eur"].notna().all()),
               ("el embudo acaba en la base de decisión", s["embudo"][-1]["quedan"] == s["bases"]["decision"]), ("la base de decisión es la que repiten las 12 variantes", s["bases"]["decision"] == s["control_grupo"]["pisos_despues"]),
               ("ninguna rentabilidad infinita", bool(np.isfinite(anuncios["rent_valoraciones_pct"].dropna()).all())), ("todos los anuncios tienen distancia al borde", anuncios["distancia_borde_m"].notna().all()),
               ("cada precio de septiembre tiene su fecha de cotización", s["cotizacion"]["sin_fecha_con_precio"] == 0), ("ninguna cotización es anterior a su foto", not any(anuncios[c].lt(0).any() for c in ("dias_cotizacion", "dias_cotizacion_mar", "dias_cotizacion_jun")))]
    if con["base_comparacion_esperada"] is not None:
        pruebas.append((f"base de comparación {con['base_comparacion_esperada']}", s["bases"]["comparacion"] == con["base_comparacion_esperada"]))
    if con["firmes_esperados"] is not None:
        pruebas.append(("firmes esperados", sorted(s["control_grupo"]["firmes"]) == sorted(con["firmes_esperados"])))
    if con.get("con_aviso_esperados") is not None:
        pruebas.append(("que siguen en la lista 4 veces esperados", sorted(s["control_grupo"]["con_aviso"]) == sorted(con["con_aviso_esperados"])))
    grupo_ok = con["grupo_esperado"] is None or sorted(s["control_grupo"]["grupo"]) == sorted(con["grupo_esperado"])
    pruebas.append(("grupo esperado", grupo_ok))
    s["validaciones"] = [{"validacion": n, "resultado": "pasa" if bool(ok) else "falla"} for n, ok in pruebas]
    fallan = [v["validacion"] for v in s["validaciones"] if v["resultado"] == "falla"]
    if fallan:
        s["salidas"] = []
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "No se guarda ninguna tabla. Fallan: " + "; ".join(fallan) + ". Con intervalo: " + s["control_grupo"]["comparacion_con_intervalo"]["veredicto"], "artefactos": ["informes/transformacion-datos.json", "informes/transformacion-datos.md"], "siguiente": "decisión de quien dirige el proyecto"}
        return s

    # 4.5 Guardar.
    filas_de = {"analisis_anuncios": "un anuncio de la descarga de septiembre", "analisis_barrios": "un barrio", "evolucion_oferta": "un barrio en una foto", "estacionalidad_resenas": "un mes con reseñas", "disponibilidad_futura": "un anuncio en un mes del calendario"}
    s["salidas"] = []
    for clave, tabla in (("anuncios", anuncios), ("barrios", barrios), ("oferta", oferta), ("resenas", resenas), ("dispo", dispo)):
        ruta = rc.PROCESADO / f"{TABLAS[clave]}.parquet"
        tabla.to_parquet(ruta, index=False)
        s["salidas"].append({"tabla": TABLAS[clave], "ruta": ruta.relative_to(rc.CASO).as_posix(), "sha256": cd.huella(ruta), "filas": len(tabla), "columnas": tabla.shape[1], "que_es_una_fila": filas_de[TABLAS[clave]]})

    # 4.6 Registro, riesgos y lo que queda.
    fichas = rc.anadir_fichas(fichas_de(s))
    quedo = {f["clave"]: (f["titulo"], f["quedo"]) for f in fichas_de(s)}
    s["transformaciones"] = [{"id": f"T-{i:02d}", "transformacion": quedo[clave][0], "columnas": [], "regla": "reglas-transformacion.md", "ficha": ficha, "resultado": quedo[clave][1]} for i, (clave, ficha) in enumerate(fichas.items(), 1)]
    s["variables_generadas"] = [{"columna": c, "formula": f, "columnas_origen": o, "unidad": u, "informacion_posterior": False, "sale_del_objetivo": False, "suma_de_otras": False} for c, f, o, u in VARIABLES]
    s["cambios_granularidad"] = [{"antes": "un anuncio y un día", "despues": "un anuncio y un mes", "sumas_control": [{"magnitud": "dias_libres", "antes": s["disponibilidad"]["libres"], "despues": int(dispo["dias_libres"].sum()), "coincide": s["disponibilidad"]["libres"] == int(dispo["dias_libres"].sum())}]},
                                 {"antes": "una reseña", "despues": "un mes", "sumas_control": [{"magnitud": "resenas", "antes": len(res), "despues": int(resenas["resenas"].sum()), "coincide": len(res) == int(resenas["resenas"].sum())}]}]
    s["cruces"] = [{"partida": "analisis_anuncios", "se_une": "precio y superficie oficiales de barrios_integrado", "clave": ["neighbourhood_cleansed", "barrio"], "cardinalidad_esperada": "N:1", "filas_antes": len(t), "filas_despues": len(anuncios)},
                   {"partida": "analisis_anuncios", "se_une": "puntos de interés", "clave": ["cruce espacial, sin unir filas"], "cardinalidad_esperada": "recuento", "filas_antes": len(t), "filas_despues": len(anuncios)}]
    s["pendiente_modelo"] = []
    s["particion"] = None
    calidad = json.loads((rc.INFORMES / "correccion-datos.json").read_text(encoding="utf-8"))["medida"]
    s["calidad"] = {k: calidad[k] for k in ("precio_vacio", "camas_vacias", "captura")}
    if s["sin_precio_de_vivienda"]["anuncios_base_comparacion"]:
        n = s["sin_precio_de_vivienda"]
        s["pendientes"].append({"id": "P-01", "tabla": "analisis_anuncios", "columna": "precio_vivienda_comparacion_eur", "pregunta": f"{n['anuncios_base_comparacion']} anuncios de la base de comparación quedan sin precio de vivienda: la regla habla de uno o más habitaciones y {n['con_cero_dormitorios']} tienen cero y {n['con_dormitorios_vacios']} vacío.",
                                "opciones": ["siguen vacíos", "se les aplica el caso de una habitación"]})
    if con_riesgos:
        RIESGOS.parent.mkdir(parents=True, exist_ok=True)
        RIESGOS.write_text(riesgos(s), encoding="utf-8", newline="\n")
    estado = "AVISO" if s["pendientes"] else "OK"
    g = s["control_grupo"]
    s["resultado"] = {"estado": estado, "riesgo": "medio", "resumen": f"Cinco tablas guardadas. Base de decisión de {s['bases']['decision']} pisos, de {g['pisos_antes']} antes de CP-007 a CP-009; grupo de {len(g['grupo'])} barrios, {len(g['firmes'])} firmes y {len(g['con_aviso'])} que siguen en la lista 4 veces; {g['comparacion_con_intervalo']['veredicto']}.",
                      "artefactos": [x["ruta"] for x in s["salidas"]] + ["informes/transformacion-datos.json", "informes/transformacion-datos.md"] + (["config/negocio/03_riesgos_de_calidad.md"] if con_riesgos else []), "siguiente": "analisis-exploratorio"}
    return s


def ejecutar():
    """Lanza la transformación y, si algo falla, deja el JSON con estado ERROR antes de avisar."""
    s = rc.bloque_comun(ETAPA, VERSION, SCRIPT)
    try:
        s = principal(s, con_riesgos="--sin-riesgos" not in sys.argv[1:])
    except Exception as error:
        rc.parar_con_error(s, "transformacion-datos", error, informe)
        raise
    rc.guardar(s, "transformacion-datos", informe)
    print(s["resultado"]["estado"], s["resultado"]["resumen"])
    return 0


if __name__ == "__main__":
    raise SystemExit(ejecutar())
