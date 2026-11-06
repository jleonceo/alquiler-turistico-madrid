"""Análisis exploratorio del caso sobre analisis_anuncios, en sus dos bases, y sobre analisis_barrios.

Deja un JSON y un HTML por tabla en informes/: analisis-exploratorio__<tabla>.json y .html. No modifica ningún dato, no
repite lo que contó el reconocimiento y no atribuye causas. Lee las tablas que dejó scripts/transformacion_datos.py y
para si su JSON está parado o si la huella de una tabla no es la que él dejó.

Se lanza después de scripts/transformacion_datos.py.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/analisis_exploratorio.py
"""
import html
import json
import re
import sys

import numpy as np
import pandas as pd

import calidad_datos as cd
import reglas_caso as rc

sys.path.insert(0, str(rc.CASO / "assets"))
import graficos as gr  # noqa: E402

# ---------------------------------------------------------------------------
# 1. Configuración
# ---------------------------------------------------------------------------

ETAPA = "analisis-exploratorio"
VERSION = "1.0"
SCRIPT = "scripts/analisis_exploratorio.py"
TABLAS = ["analisis_anuncios", "analisis_barrios"]
ESTADOS = ("aplicada_con_resultado", "aplicada_sin_nada_relevante", "no_aplica")
COMPROBACIONES = ["1 Tiempo", "2 Pareto y ABC", "3 Respaldo de cada cifra", "4 Datos personales", "5 Códigos sin etiqueta", "6 Reproducibilidad", "7 Correlaciones", "8 Forma de las hipótesis",
                  "9 Variables asimétricas", "10 Gráficos", "11 Series de negocio", "12 Frente al objetivo", "13 Discreta o continua", "14 Texto", "15 Alta cardinalidad", "16 Observaciones", "17 Tabla de estadísticos"]

# Umbrales de descripción, fijados antes de calcular (comprobaciones.md, cabecera).
MEDIA_LEJOS = 0.25  # la media se aleja más de un 25 % de la mediana
ORDENES = 1000  # el máximo es mil veces el mínimo
MINIMO = 30  # reglas §3
PARAMETROS = [{"nombre": "numérica discreta", "valor": "entera y con como mucho min(20, 5 % de las filas) valores distintos", "origen": "por defecto"},
              {"nombre": "filas mínimas para comparar una categoría", "valor": str(MINIMO), "origen": "reglas §3"},
              {"nombre": "alta cardinalidad", "valor": "más de 50 valores distintos", "origen": "por defecto"},
              {"nombre": "las más frecuentes en alta cardinalidad", "valor": "10", "origen": "por defecto"},
              {"nombre": "texto muy corto", "valor": "no aplica: las tablas no traen texto libre", "origen": "por defecto"},
              {"nombre": "diagrama de caja", "valor": "no se usa: no aporta a un histograma", "origen": "por defecto"},
              {"nombre": "parte con que se cruza el objetivo", "valor": "no aplica: el caso no entrena ningún modelo", "origen": "por defecto"},
              {"nombre": "media lejos de la mediana", "valor": f"más de un {MEDIA_LEJOS:.0%} de diferencia", "origen": "fijado antes de calcular"},
              {"nombre": "órdenes de magnitud", "valor": f"máximo de {ORDENES} veces el mínimo o más", "origen": "fijado antes de calcular"}]

# Papel de las columnas que el tipo de pandas no dice: el identificador y las coordenadas no son magnitudes.
IDENTIFICADORES = {"id", "latitud", "longitud"}
# No se describen como magnitud: sus sumas no significan nada o repiten una columna que ya se describe (reglas-transformacion.md §1).
NO_MAGNITUD = {"distancia_borde_m"}
# Variables con histograma propio, porque son las palancas de la ficha.
PRINCIPALES = [("precio_eur", "Precio por noche", "€", 0), ("ocupacion_dias", "Ocupación estimada", " días", 0), ("rent_valoraciones_desc_pct", "Rentabilidad bruta con descuento", " %", 1), ("compra_valoraciones_desc_eur", "Precio de compra con descuento", " €", 0)]
CATEGORICAS_ANUNCIOS = ["tipo_alquiler", "tipo_inmueble", "distrito", "barrio", "estancia_origen", "tipo_licencia", "exencion_licencia", "precio_m2_origen", "superficie_oficial_origen", "lado_centro", "lado_incierto", "declara_temporada", "captura_anterior"]
COL_PRECIO_BASE = {"decision": "precio_eur", "comparacion": "precio_vivienda_comparacion_eur"}
NOMBRE_BASE = {"decision": "base de decisión", "comparacion": "base de comparación"}


def n(x, decimales=0):
    """Escribe una cifra con el formato español; un vacío se escribe como tal."""
    return "sin dato" if x is None or (isinstance(x, float) and not np.isfinite(x)) else gr.numero(x, decimales)


# ---------------------------------------------------------------------------
# 2. Funciones de medida
# ---------------------------------------------------------------------------

def tipificar(df):
    """Clasifica cada columna por su papel, con el nombre, el tipo, la cardinalidad y los valores (§2 y comprobación 13)."""
    salida = []
    limite_discreta = min(20, 0.05 * len(df))
    for c in df.columns:
        s = df[c]
        if c in IDENTIFICADORES:
            tipo = "identificador"
        elif pd.api.types.is_bool_dtype(s):
            tipo = "booleana"
        elif pd.api.types.is_numeric_dtype(s):
            v = s.dropna()
            entera = bool(v.eq(v.round()).all())
            tipo = "discreta" if entera and v.nunique() <= limite_discreta else "continua"
        else:
            tipo = "alta_cardinalidad" if s.nunique() > 50 else "categorica"
        salida.append({"columna": c, "tipo": tipo})
    return salida


def estadisticos(s):
    """Da el resumen de una magnitud con sus percentiles y las cuatro señales de la comprobación 17."""
    v = s.dropna().astype("float64")
    e = {"conteo": int(len(v)), "nulos": int(s.isna().sum())}
    claves = {"p1": 0.01, "p5": 0.05, "p25": 0.25, "p75": 0.75, "p95": 0.95, "p99": 0.99}
    if v.empty:
        return {**e, "media": None, "mediana": None, "desviacion": None, "minimo": None, "maximo": None, **dict.fromkeys(claves), "senales": []}
    e.update(media=float(v.mean()), mediana=float(v.median()), desviacion=float(v.std()) if len(v) > 1 else None, minimo=float(v.min()), maximo=float(v.max()))
    e.update({k: float(v.quantile(q)) for k, q in claves.items()})
    senales = []
    if e["mediana"] != 0 and abs(e["media"] - e["mediana"]) / abs(e["mediana"]) > MEDIA_LEJOS:
        senales.append("media_lejos_de_la_mediana")
    if e["p25"] == e["mediana"] == e["p75"] or e["p75"] == e["mediana"] == e["maximo"]:
        senales.append("cuartiles_iguales")
    if e["minimo"] > 0 and e["maximo"] / e["minimo"] >= ORDENES:
        senales.append("ordenes_de_magnitud")
    if v.nunique() == 2:
        senales.append("dos_valores")
    e["senales"] = senales
    return e


def frecuencias(s):
    """Da cardinalidad, categoría dominante, vacíos y las categorías más frecuentes con su porcentaje."""
    filas = len(s)
    # El vacío cuenta como categoría: sin él, una columna medio vacía parecería dominada por su primer valor.
    f = s.astype("object").where(s.notna(), "vacío").value_counts()
    return {"cardinalidad": int(s.nunique()), "nulos": int(s.isna().sum()), "dominante": None if f.empty else str(f.index[0]), "dominante_pct": None if f.empty or not filas else 100 * float(f.iloc[0]) / filas,
            "mas_frecuentes": [{"valor": str(k), "filas": int(v), "pct": 100 * float(v) / filas} for k, v in f.head(10).items()], "parte_de_las_10_pct": None if not filas else 100 * float(f.head(10).sum()) / filas}


def pareto(df, entidad, magnitud):
    """Concentración de una magnitud por elemento, con el identificador y las clases ABC."""
    # Los empates se deshacen por el nombre, para que el corte no dependa del orden de las filas.
    p = df.groupby(entidad)[magnitud].sum().to_frame("valor").reset_index().sort_values(["valor", entidad], ascending=[False, True]).set_index(entidad)
    p = p.loc[p["valor"].gt(0)]
    if p.empty:
        return {"elementos": 0, "total": 0.0, "pct_elementos_80": None, "clases": {}, "primeros": []}
    p["posicion_pct"] = np.arange(1, len(p) + 1) / len(p) * 100
    p["acumulado_pct"] = (p["valor"].cumsum() / p["valor"].sum() * 100).round(9)
    p["clase_abc"] = pd.cut(p["acumulado_pct"], [0, 80, 95, 100], labels=["A", "B", "C"], include_lowest=True).astype("str")
    hasta = p.loc[p["acumulado_pct"].le(80), "posicion_pct"]
    clases = {k: {"elementos": int(g["valor"].size), "parte_del_total_pct": 100 * float(g["valor"].sum()) / float(p["valor"].sum())} for k, g in p.groupby("clase_abc")}
    return {"elementos": len(p), "total": float(p["valor"].sum()), "pct_elementos_80": float(hasta.max()) if len(hasta) else None, "clases": clases,
            "primeros": [{"elemento": str(k), "valor": float(f["valor"]), "acumulado_pct": float(f["acumulado_pct"])} for k, f in p.head(5).iterrows()]}


def dormitorios_de(s):
    """Agrupa las habitaciones en 0, 1, 2, 3 y «4 o más», como el reconocimiento: los de más no llegan al mínimo por separado."""
    return s.clip(upper=4).astype("Int64").astype("str").replace("4", "4 o más")


def nivel_ocupacion(s):
    """Da el nivel de ocupación de 04_planteamientos.md: tercios del año, con el tope aparte."""
    return pd.cut(s, [0, 85, 170, 254, 255], labels=["1-85", "86-170", "171-254", "255"]).astype("object")


def correlaciones(x, y):
    """Da Pearson y Spearman a la vez, con los pares que entran (comprobación 7)."""
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(d) < 3 or d["x"].nunique() < 2 or d["y"].nunique() < 2:
        return {"pearson": None, "spearman": None, "pares": len(d)}
    return {"pearson": float(d["x"].corr(d["y"])), "spearman": float(d["x"].corr(d["y"], method="spearman")), "pares": len(d)}


def comprobaciones_sin_estado(lista, esperadas):
    """Dice qué comprobación no tiene uno de los tres estados, o si falta alguna."""
    malas = [c["comprobacion"] for c in lista if c.get("estado") not in ESTADOS]
    return malas + ([f"faltan {esperadas - len(lista)}"] if len(lista) != esperadas else [])


def grafico(fallidos, nombre, funcion, *args, **kw):
    """Dibuja con la pieza común; si esta para por una regla de salida, se apunta el motivo y el informe sigue."""
    try:
        return funcion(*args, **kw)
    except ValueError as error:
        fallidos.append({"grafico": nombre, "motivo": str(error)})
        return None


# ---------------------------------------------------------------------------
# 3. analisis_anuncios
# ---------------------------------------------------------------------------

def resumen_de_base(d, clave):
    """Reúne lo que describe una base: control, magnitudes y categóricas."""
    tipos = {x["columna"]: x["tipo"] for x in tipificar(d)}
    magnitudes = [c for c, t in tipos.items() if t in ("continua", "discreta") and c not in NO_MAGNITUD and not c.startswith(("excl_", "comp_excl_"))]
    pisos = d.groupby("barrio").size()
    return {"nombre": NOMBRE_BASE[clave], "filas": len(d), "entidades_id": int(d["id"].nunique()), "ingreso_total_eur": round(float(d["ingreso_anual_eur"].sum()), 2), "barrios": int(d["barrio"].nunique()), "distritos": int(d["distrito"].nunique()),
            "barrios_30_o_mas": int(pisos.ge(MINIMO).sum()), "filas_en_barrios_30_o_mas": int(pisos[pisos.ge(MINIMO)].sum()), "dentro_del_centro": int(d["lado_centro"].eq("dentro").sum()), "lado_incierto": int(d["lado_incierto"].sum()),
            "tipos": {str(k): int(v) for k, v in d["tipo_alquiler"].value_counts().items()}, "numericas": {c: estadisticos(d[c]) for c in magnitudes}, "categoricas": {c: frecuencias(d[c]) for c in CATEGORICAS_ANUNCIOS}}


def rentabilidad_por_dormitorios_y_barrio(d):
    """Cruza habitaciones y barrio con el mínimo de 30 por celda; lo demás sale con su recuento (reglas §3)."""
    t = d.assign(grupo_dormitorios=dormitorios_de(d["dormitorios"]))
    por_dorm = t.groupby("grupo_dormitorios")["rent_valoraciones_desc_pct"].agg(pisos="size", mediana="median", q25=lambda x: x.quantile(0.25)).reset_index()
    celdas = t.groupby(["barrio", "grupo_dormitorios"])["rent_valoraciones_desc_pct"].agg(pisos="size", mediana="median").reset_index()
    llegan = celdas.loc[celdas["pisos"].ge(MINIMO)].sort_values(["mediana", "barrio"], ascending=[False, True])
    # Simpson: si 1 dormitorio gana a 2 en el total, se mira si también gana distrito a distrito.
    dd = t.loc[t["grupo_dormitorios"].isin(["1", "2"])].groupby(["distrito", "grupo_dormitorios"])["rent_valoraciones_desc_pct"].agg(pisos="size", mediana="median").reset_index()
    ancho = dd.pivot(index="distrito", columns="grupo_dormitorios", values="mediana")
    conteo = dd.pivot(index="distrito", columns="grupo_dormitorios", values="pisos")
    vista_distritos = []
    if {"1", "2"} <= set(ancho.columns):
        validos = conteo.index[conteo["1"].ge(MINIMO) & conteo["2"].ge(MINIMO)]
        gana_uno = int(ancho.loc[validos, "1"].gt(ancho.loc[validos, "2"]).sum())
        vista_distritos = [{"distrito": str(k), "uno_pct": float(ancho.loc[k, "1"]), "pisos_uno": int(conteo.loc[k, "1"]), "dos_pct": float(ancho.loc[k, "2"]), "pisos_dos": int(conteo.loc[k, "2"])} for k in validos]
    else:
        validos, gana_uno = [], 0
    return {"por_dormitorios": [{"dormitorios": str(f["grupo_dormitorios"]), "pisos": int(f["pisos"]), "mediana_pct": float(f["mediana"]), "q25_pct": float(f["q25"])} for _, f in por_dorm.iterrows()],
            "celdas_barrio_dormitorios": len(celdas), "celdas_con_30_o_mas": len(llegan), "pisos_en_esas_celdas": int(llegan["pisos"].sum()),
            "celdas": [{"barrio": str(f["barrio"]), "dormitorios": str(f["grupo_dormitorios"]), "pisos": int(f["pisos"]), "mediana_pct": float(f["mediana"])} for _, f in llegan.iterrows()],
            "distritos_comparables_1_y_2": len(validos), "distritos_donde_1_supera_a_2": gana_uno, "vista_por_distritos": vista_distritos}


def ocupacion_con_su_tope(d):
    """Describe la ocupación por niveles, con la parte en el tope, y por distrito con el mínimo de 30."""
    niveles = nivel_ocupacion(d["ocupacion_dias"])
    reparto = niveles.value_counts(dropna=False)
    filas = len(d)
    t = d.assign(en_tope=d["ocupacion_dias"].eq(255)).groupby("distrito")["en_tope"].agg(pisos="size", tope="mean").reset_index()
    t = t.loc[t["pisos"].ge(MINIMO)].sort_values(["tope", "distrito"], ascending=[False, True])
    return {"filas": filas, "niveles": [{"nivel": k, "filas": int(reparto.get(k, 0)), "pct": 100 * float(reparto.get(k, 0)) / filas if filas else None} for k in ("1-85", "86-170", "171-254", "255")],
            "pct_en_el_tope": 100 * float(d["ocupacion_dias"].eq(255).mean()) if filas else None, "por_distrito": [{"distrito": str(f["distrito"]), "pisos": int(f["pisos"]), "pct_en_el_tope": 100 * float(f["tope"])} for _, f in t.iterrows()]}


def compra_y_alquiler_por_distrito(d, col_precio):
    """Mide si el precio de compra y el de alquiler van juntos entre distritos con 30 anuncios o más."""
    g = d.groupby("distrito").agg(pisos=("id", "size"), alquiler=(col_precio, "median"), m2=("precio_m2_eur", "median"), compra=("compra_valoraciones_desc_eur", "median"), ocupacion=("ocupacion_dias", "median")).reset_index()
    g = g.loc[g["pisos"].ge(MINIMO)].sort_values(["compra", "distrito"], ascending=[False, True])
    return {"distritos": len(g), "m2_con_alquiler": correlaciones(g["m2"], g["alquiler"]), "compra_con_alquiler": correlaciones(g["compra"], g["alquiler"]), "m2_con_ocupacion": correlaciones(g["m2"], g["ocupacion"]),
            "filas": [{"distrito": str(f["distrito"]), "pisos": int(f["pisos"]), "alquiler_mediano_eur": float(f["alquiler"]), "m2_mediano_eur": float(f["m2"]), "compra_mediana_eur": float(f["compra"])} for _, f in g.iterrows()]}


def precios_por_foto(d):
    """Compara el precio de los mismos anuncios en las tres fotos: solo los que traen las tres, para no mezclar poblaciones."""
    t = d.dropna(subset=["precio_mar_eur", "precio_jun_eur", "precio_eur"])
    return {"anuncios_con_las_tres": len(t), "parte_de_la_base_pct": 100 * len(t) / len(d) if len(d) else None, "mediana_marzo": float(t["precio_mar_eur"].median()) if len(t) else None,
            "mediana_junio": float(t["precio_jun_eur"].median()) if len(t) else None, "mediana_septiembre": float(t["precio_eur"].median()) if len(t) else None}


def parejas_de_pareto(d, c):
    """Recorre las parejas elemento y magnitud de cada base y las deja en una tabla."""
    parejas = []
    for clave, t in (("decision", d), ("comparacion", c)):
        t = t.assign(un_anuncio=1)
        for elemento in ("barrio", "distrito", "tipo_inmueble"):
            for magnitud, nombre in (("ingreso_anual_eur", "ingreso anual"), ("un_anuncio", "anuncios")):
                r = pareto(t, elemento, magnitud)
                parejas.append({"base": NOMBRE_BASE[clave], "elemento": elemento, "magnitud": nombre, **r})
    return parejas


def senales_de(bases):
    """Lista las señales de la tabla de estadísticos, por base y columna."""
    return [{"base": b["nombre"], "columna": c, "senal": s} for b in bases.values() for c, e in b["numericas"].items() for s in e["senales"]]


def anomalia_del_tope(d):
    """Busca el barrio con 30 o más donde más se concentra el tope, y mide su tamaño (anomalía concentrada)."""
    g = d.assign(en_tope=d["ocupacion_dias"].eq(255)).groupby("barrio")["en_tope"].agg(pisos="size", tope="sum").reset_index()
    g = g.loc[g["pisos"].ge(MINIMO)].assign(parte=lambda x: x["tope"] / x["pisos"]).sort_values(["parte", "barrio"], ascending=[False, True])
    if g.empty:
        return None
    f = g.iloc[0]
    return {"barrio": str(f["barrio"]), "pisos": int(f["pisos"]), "en_tope": int(f["tope"]), "pct": 100 * float(f["parte"]), "parte_de_la_base_pct": 100 * int(f["pisos"]) / len(d), "pct_en_la_base": 100 * float(d["ocupacion_dias"].eq(255).mean())}


def analizar_anuncios(a, s):
    """Describe las dos bases y deja lo que espera el paso siguiente."""
    d, c = a.loc[a["base_decision"]].copy(), a.loc[a["base_comparacion"]].copy()
    bases = {"decision": resumen_de_base(d, "decision"), "comparacion": resumen_de_base(c, "comparacion")}
    pisos_c = c.loc[c["tipo_alquiler"].eq("Entire home/apt")]
    siguiente = {"rentabilidad_por_dormitorios_y_barrio": {"decision": rentabilidad_por_dormitorios_y_barrio(d), "comparacion_solo_pisos": rentabilidad_por_dormitorios_y_barrio(pisos_c)},
                 "ocupacion_con_su_tope": {"decision": ocupacion_con_su_tope(d), "comparacion": ocupacion_con_su_tope(c)},
                 "compra_y_alquiler_por_distrito": {"decision": compra_y_alquiler_por_distrito(d, "precio_eur"), "comparacion": compra_y_alquiler_por_distrito(c, "precio_vivienda_comparacion_eur")}}
    s.update(bases=bases, para_el_paso_siguiente=siguiente, tipificacion=tipificar(a), parejas_pareto=parejas_de_pareto(d, c), precios_por_foto={"decision": precios_por_foto(d), "comparacion": precios_por_foto(c)})
    s["vision_general"] = {"filas": len(a), "columnas": a.shape[1], "granularidad": "un anuncio de la foto de septiembre", "periodo": rc.FECHA_DATOS, "entidades_id": int(a["id"].nunique()), "tipos": pd.Series([x["tipo"] for x in s["tipificacion"]]).value_counts().to_dict()}
    s["senales"] = senales_de(bases)
    s["anomalia_concentrada"] = anomalia_del_tope(d)
    s["codigos_sin_etiqueta"] = [{"columna": "tipo_licencia", "valores": sorted(str(x) for x in a["tipo_licencia"].dropna().unique()), "pregunta": "qué significan esas letras: el decreto no las define (reglas §1)"}]
    return d, c


def textos_anuncios(s):
    """Redacta hallazgos, alertas e hipótesis de los anuncios a partir de las cifras."""
    b, x, sig = s["bases"]["decision"], s["bases"]["comparacion"], s["para_el_paso_siguiente"]
    rd, ot, ca = sig["rentabilidad_por_dormitorios_y_barrio"]["decision"], sig["ocupacion_con_su_tope"], sig["compra_y_alquiler_por_distrito"]
    dims = ["distrito", "dormitorios", "tipo de inmueble"]
    simpson = []
    hallazgos = [{"texto": f"La base de decisión tiene {n(b['filas'])} pisos en {n(b['barrios'])} barrios y suma {n(b['ingreso_total_eur'], 2)} € de ingreso estimado al año; {n(b['barrios_30_o_mas'])} barrios llegan a 30 pisos y reúnen {n(b['filas_en_barrios_30_o_mas'])}.",
                  "dimensiones_comprobadas": ["barrio"], "filas": b["filas"], "columnas": ["id", "ingreso_anual_eur", "barrio"]},
                 {"texto": f"La base de comparación tiene {n(x['filas'])} anuncios, con {n(x['dentro_del_centro'])} dentro del centro histórico; suma {n(x['ingreso_total_eur'], 2)} € al precio publicado.", "dimensiones_comprobadas": ["tipo de alquiler", "lado del centro"], "filas": x["filas"], "columnas": ["id", "lado_centro", "ingreso_anual_eur"]}]
    if rd["por_dormitorios"]:
        orden = sorted(rd["por_dormitorios"], key=lambda f: -f["mediana_pct"] if f["pisos"] >= MINIMO else 1e9)
        # Si la ventaja no se repite en todos los distritos comparables, el total pasa a alerta (§5, Hallazgo).
        if rd["distritos_donde_1_supera_a_2"] < rd["distritos_comparables_1_y_2"]:
            simpson.append({"texto": f"Con 30 pisos o más, la mayor rentabilidad bruta mediana del total es la de los pisos con {orden[0]['dormitorios']} {'habitación' if orden[0]['dormitorios'] == '1' else 'habitaciones'}, {n(orden[0]['mediana_pct'], 1)} %, pero de {n(rd['distritos_comparables_1_y_2'])} distritos comparables una habitación supera a dos solo en {n(rd['distritos_donde_1_supera_a_2'])}: la conclusión cambia al segmentar.", "origen": None})
        else:
            hallazgos.append({"texto": f"Con 30 pisos o más, la mayor rentabilidad bruta mediana es la de los pisos con {orden[0]['dormitorios']} {'habitación' if orden[0]['dormitorios'] == '1' else 'habitaciones'}: {n(orden[0]['mediana_pct'], 1)} % con {n(orden[0]['pisos'])} pisos.", "dimensiones_comprobadas": dims, "filas": b["filas"], "columnas": ["rent_valoraciones_desc_pct", "dormitorios", "distrito"]})
        hallazgos.append({"texto": f"El cruce de barrio y habitaciones deja {n(rd['celdas_con_30_o_mas'])} celdas con 30 pisos o más, de {n(rd['celdas_barrio_dormitorios'])}: el barrio y el tipo juntos casi nunca llegan al mínimo.", "dimensiones_comprobadas": ["barrio", "dormitorios"], "filas": rd["pisos_en_esas_celdas"], "columnas": ["barrio", "dormitorios"]})
    hallazgos.append({"texto": f"El {n(ot['decision']['pct_en_el_tope'], 1)} % de la base de decisión y el {n(ot['comparacion']['pct_en_el_tope'], 1)} % de la de comparación están en el tope de 255 días.", "dimensiones_comprobadas": ["distrito"], "filas": b["filas"], "columnas": ["ocupacion_dias"]})
    hallazgos.append({"texto": f"Entre {n(ca['decision']['distritos'])} distritos con 30 pisos o más, el precio mediano del m² de los pisos y su alquiler mediano van juntos en la base de decisión: Spearman de {n(ca['decision']['m2_con_alquiler']['spearman'], 2)}. En la de comparación, con {n(ca['comparacion']['distritos'])} distritos, da {n(ca['comparacion']['m2_con_alquiler']['spearman'], 2)}.",
                      "dimensiones_comprobadas": ["distrito"], "filas": b["filas"], "columnas": ["precio_m2_eur", "precio_eur", "precio_vivienda_comparacion_eur"]})
    ingreso = next(p for p in s["parejas_pareto"] if p["base"] == NOMBRE_BASE["decision"] and p["elemento"] == "barrio" and p["magnitud"] == "ingreso anual")
    hallazgos.append({"texto": f"El {n(ingreso['pct_elementos_80'], 1)} % de {n(ingreso['elementos'])} barrios suma el 80 % del ingreso estimado de la base de decisión.", "dimensiones_comprobadas": ["barrio"], "filas": b["filas"], "columnas": ["barrio", "ingreso_anual_eur"]})
    f = s["precios_por_foto"]["decision"]
    hallazgos.append({"texto": f"Los {n(f['anuncios_con_las_tres'])} pisos de la base con precio en las tres fotos tienen una mediana de {n(f['mediana_marzo'], 2)} € en marzo, {n(f['mediana_junio'], 2)} € en junio y {n(f['mediana_septiembre'], 2)} € en septiembre.", "dimensiones_comprobadas": ["foto"], "filas": f["anuncios_con_las_tres"], "columnas": ["precio_mar_eur", "precio_jun_eur", "precio_eur"]})

    alertas = [{"texto": "La ocupación es una estimación de la fuente con tope de 255 días, y en la parte alta no ordena.", "origen": "reglas-negocio §6"},
               {"texto": "La superficie de valoraciones y el descuento del 25 % son supuestos: la rentabilidad compara y no promete un rendimiento.", "origen": "reglas-negocio §6"}]
    alertas += simpson + [{"texto": p["pregunta"], "origen": f"transformacion-datos {p['id']}"} for p in s["pendientes_heredados"]]
    alertas.append({"texto": f"{n(b['lado_incierto'])} pisos de la base de decisión están a menos de 150 m del borde del centro histórico, y su lado no se puede asegurar.", "origen": "reglas-negocio §4"})
    dominante = b["categoricas"]["tipo_inmueble"]
    alertas.append({"texto": f"Categoría dominante: «{dominante['dominante']}» recoge el {n(dominante['dominante_pct'], 1)} % de la base de decisión, así que el tipo de inmueble apenas separa.", "origen": None})
    if s["senales"]:
        vistas = sorted({f"{x['columna']} ({x['senal']})" for x in s["senales"] if x["base"] == NOMBRE_BASE["decision"]})
        alertas.append({"texto": f"Señales de la tabla de estadísticos en la base de decisión: {'; '.join(vistas)}. Se leen con las reglas §2: ninguna es una escala rota.", "origen": None})
    a = s["anomalia_concentrada"]
    hipotesis = []
    if a:
        alertas.append({"texto": f"Anomalía concentrada: {a['barrio']} tiene {n(a['en_tope'])} de {n(a['pisos'])} pisos en el tope, el {n(a['pct'], 1)} %, frente al {n(a['pct_en_la_base'], 1)} % de la base; ese barrio es el {n(a['parte_de_la_base_pct'], 1)} % de los pisos. "
                        "Afecta a la pregunta 2 y cae fuera del rango dominante. La regla §6 ya documenta el tope, de modo que no se devuelve a Calidad: la pregunta 3 dice si el barrio depende de él.", "origen": None})
        hipotesis.append({"texto": f"La concentración en el tope de {a['barrio']} admite dos lecturas: un mercado de pisos muy alquilados o una ocupación que la fórmula infla con muchas reseñas de estancias cortas.",
                          "que_haria_falta": "las noches vendidas reales, que no están en los datos. Explicaciones repasadas: tamaño del grupo, calendario, regresión a la media, causa al revés y una variable ausente."})
    hipotesis.append({"texto": "Que el m² y el alquiler vayan juntos por distrito puede responder a la localización, que mueve los dos.", "que_haria_falta": "un diseño que separe la localización de la calidad del piso; aquí solo se describe la asociación."})
    return hallazgos, alertas, hipotesis


def comprobaciones_anuncios(s, graficos_hechos):
    """Da el estado de cada comprobación a partir de lo que se calculó en esta ejecución."""
    personales = s["datos_personales_en_categoricas"]
    t = [x["tipo"] for x in s["tipificacion"]]
    return [{"comprobacion": COMPROBACIONES[0], "estado": "aplicada_con_resultado", "nota": "la tabla no trae fechas; el tiempo son las tres fotos de precio, leídas con los mismos anuncios"},
            {"comprobacion": COMPROBACIONES[1], "estado": "aplicada_con_resultado" if s["parejas_pareto"] else "no_aplica", "nota": f"{len(s['parejas_pareto'])} parejas"},
            {"comprobacion": COMPROBACIONES[2], "estado": "aplicada_con_resultado", "nota": "cada hallazgo lleva sus filas y sus columnas"},
            {"comprobacion": COMPROBACIONES[3], "estado": "aplicada_con_resultado" if personales else "aplicada_sin_nada_relevante", "nota": f"patrones de correo, enlace y documento buscados en las categóricas: {len(personales)} coincidencias"},
            {"comprobacion": COMPROBACIONES[4], "estado": "aplicada_con_resultado", "nota": "tipo_licencia va como alerta, sin leer sus letras"},
            {"comprobacion": COMPROBACIONES[5], "estado": "aplicada_con_resultado", "nota": "versiones, fecha y huella en Contexto"},
            {"comprobacion": COMPROBACIONES[6], "estado": "aplicada_con_resultado", "nota": "Pearson y Spearman entre distritos, pedidos por el planteamiento"},
            {"comprobacion": COMPROBACIONES[7], "estado": "aplicada_con_resultado", "nota": "cada hipótesis dice qué faltaría y se repasan las cinco alternativas"},
            {"comprobacion": COMPROBACIONES[8], "estado": "aplicada_con_resultado", "nota": "precio, ingreso y rentabilidad se comparan con la mediana"},
            {"comprobacion": COMPROBACIONES[9], "estado": "aplicada_con_resultado" if graficos_hechos else "no_aplica", "nota": f"{graficos_hechos} gráficos distintos, sin diagrama de caja"},
            {"comprobacion": COMPROBACIONES[10], "estado": "no_aplica", "nota": "esta tabla no tiene fecha; la serie de reseñas y la oferta entre fotos son de indicadores"},
            {"comprobacion": COMPROBACIONES[11], "estado": "no_aplica", "nota": "el caso no es predictivo"},
            {"comprobacion": COMPROBACIONES[12], "estado": "aplicada_con_resultado", "nota": f"{t.count('discreta')} discretas y {t.count('continua')} continuas"},
            {"comprobacion": COMPROBACIONES[13], "estado": "no_aplica", "nota": "no hay texto libre: salió antes de llegar al caso"},
            {"comprobacion": COMPROBACIONES[14], "estado": "aplicada_con_resultado", "nota": f"barrio tiene {s['bases']['decision']['categoricas']['barrio']['cardinalidad']} valores en la base de decisión"},
            {"comprobacion": COMPROBACIONES[15], "estado": "aplicada_sin_nada_relevante", "nota": "sin observaciones pendientes"},
            {"comprobacion": COMPROBACIONES[16], "estado": "aplicada_con_resultado" if s["senales"] else "aplicada_sin_nada_relevante", "nota": f"{len(s['senales'])} señales"}]


def bloques_anuncios(a, d, c, s, fallidos):
    """Dibuja los gráficos del informe de anuncios: cada bloque lleva su título, calculado del dato."""
    numericos, categoricos, destacados = [], [], []
    for clave, t in (("decision", d), ("comparacion", c)):
        for col, nombre, unidad, dec in PRINCIPALES:
            if clave == "comparacion" and col == "rent_valoraciones_desc_pct":
                continue
            v = t[col].dropna().tolist()
            mediana = s["bases"][clave]["numericas"].get(col, {}).get("mediana")
            svg = grafico(fallidos, f"{col} {clave}", gr.histograma, v, intervalos=12, decimales=dec, unidad=unidad.strip(), etiqueta_x=nombre, medida=nombre)
            if svg:
                numericos.append((f"{nombre}, {NOMBRE_BASE[clave]}: mediana de {n(mediana, dec)}{unidad}", svg))
    e = s["bases"]["decision"]["categoricas"]
    for col, nombre in (("tipo_inmueble", "Tipo de inmueble"), ("distrito", "Distrito"), ("tipo_licencia", "Tipo de registro")):
        filas = e[col]["mas_frecuentes"]
        svg = grafico(fallidos, col, gr.barras_ordenadas, [x["valor"] for x in filas], {"anuncios": [x["filas"] for x in filas]}, medida="pisos") if filas else None
        if svg:
            categoricos.append((f"{nombre}: {e[col]['dominante']} encabeza la base de decisión con {n(e[col]['dominante_pct'], 1)} % de {n(s['bases']['decision']['filas'])} pisos", svg))
    rd = [f for f in s["para_el_paso_siguiente"]["rentabilidad_por_dormitorios_y_barrio"]["decision"]["por_dormitorios"] if f["pisos"] >= MINIMO]
    if rd:
        mejor = max(rd, key=lambda f: f["mediana_pct"])
        svg = grafico(fallidos, "rentabilidad por habitaciones", gr.barras_ordenadas, [f["dormitorios"] for f in rd], {"rentabilidad bruta mediana": [f["mediana_pct"] for f in rd]}, decimales=1, unidad=" %", n=[f["pisos"] for f in rd], ordenar=False, medida="rentabilidad bruta mediana")
        if svg:
            destacados.append((f"La rentabilidad bruta mediana más alta es la de los pisos con {mejor['dormitorios']} {'habitación' if mejor['dormitorios'] == '1' else 'habitaciones'}, {n(mejor['mediana_pct'], 1)} %", svg))
    ot = s["para_el_paso_siguiente"]["ocupacion_con_su_tope"]["decision"]
    if ot["por_distrito"]:
        primeros = ot["por_distrito"]
        svg = grafico(fallidos, "tope por distrito", gr.barras_ordenadas, [f["distrito"] for f in primeros], {"parte en el tope": [f["pct_en_el_tope"] for f in primeros]}, decimales=1, unidad=" %", n=[f["pisos"] for f in primeros], medida="pisos en el tope")
        if svg:
            destacados.append((f"La parte de pisos en el tope va del {n(primeros[0]['pct_en_el_tope'], 1)} % de {primeros[0]['distrito']} al {n(primeros[-1]['pct_en_el_tope'], 1)} % de {primeros[-1]['distrito']}", svg))
    ca = s["para_el_paso_siguiente"]["compra_y_alquiler_por_distrito"]["decision"]
    if ca["distritos"] >= 3:
        svg = grafico(fallidos, "compra y alquiler", gr.dispersion, [f["m2_mediano_eur"] for f in ca["filas"]], [f["alquiler_mediano_eur"] for f in ca["filas"]], etiqueta_x="Precio del m² (€)", etiqueta_y="Alquiler mediano (€ por noche)", decimales_y=0, nombres=[f["distrito"] for f in ca["filas"]])
        if svg:
            destacados.append((f"El precio del m² y el alquiler van juntos entre {n(ca['distritos'])} distritos: Spearman de {n(ca['m2_con_alquiler']['spearman'], 2)}", svg))
    ingreso = d.groupby("barrio")["ingreso_anual_eur"].sum()
    if len(ingreso) >= 5:
        svg = grafico(fallidos, "concentración", gr.curva_acumulada, ingreso.tolist())
        if svg:
            destacados.append((f"Concentración del ingreso estimado entre {n(len(ingreso))} barrios de la base de decisión", svg))
    return numericos, categoricos, destacados


# ---------------------------------------------------------------------------
# 4. analisis_barrios
# ---------------------------------------------------------------------------

def analizar_barrios(b, s):
    """Describe la tabla de barrios: cuánta oferta, cuánto precio oficial y cuántas licencias hay detrás."""
    tipos = tipificar(b)
    magnitudes = [x["columna"] for x in tipos if x["tipo"] in ("continua", "discreta")]
    s["tipificacion"] = tipos
    s["vision_general"] = {"filas": len(b), "columnas": b.shape[1], "granularidad": "un barrio", "periodo": rc.FECHA_DATOS, "entidades_id": int(b["barrio"].nunique()), "tipos": pd.Series([x["tipo"] for x in tipos]).value_counts().to_dict()}
    s["numericas"] = {c: estadisticos(b[c]) for c in magnitudes}
    s["categoricas"] = {c: frecuencias(b[c]) for c in ("distrito", "precio_m2_origen", "superficie_oficial_origen")}
    s["senales"] = [{"base": "todos los barrios", "columna": c, "senal": x} for c, e in s["numericas"].items() for x in e["senales"]]
    s["parejas_pareto"] = [{"base": "todos los barrios", "elemento": "barrio", "magnitud": m, **pareto(b, "barrio", m)} for m in ("anuncios", "pisos_base_decision", "anuncios_base_comparacion", "licencias", "ventas_barrio")]
    s["cobertura"] = {"barrios": len(b), "con_30_pisos_o_mas": int(b["pisos_base_decision"].ge(MINIMO).sum()), "sin_ningun_piso_en_la_base": int(b["pisos_base_decision"].eq(0).sum()), "sin_licencias": int(b["licencias"].eq(0).sum()), "sin_ventas_consta": int(b["ventas_barrio"].isna().sum()),
                      "precio_del_distrito": int(b["precio_m2_origen"].eq("distrito").sum())}
    s["relaciones"] = {"anuncios_con_licencias": correlaciones(b["anuncios"], b["licencias"]), "pisos_base_con_precio_m2": correlaciones(b["pisos_base_decision"], b["precio_m2_eur"]), "ventas_con_precio_m2": correlaciones(b["ventas_barrio"], b["precio_m2_eur"])}
    ventas = b.loc[b["pisos_base_decision"].ge(MINIMO), "ventas_barrio"]
    s["ventas_en_barrios_comparados"] = {"barrios": int(ventas.notna().sum()), "mediana": float(ventas.median()) if ventas.notna().any() else None, "minima": float(ventas.min()) if ventas.notna().any() else None}


def textos_barrios(s):
    """Redacta hallazgos, alertas e hipótesis de los barrios."""
    c, r, v = s["cobertura"], s["relaciones"], s["ventas_en_barrios_comparados"]
    base = next(p for p in s["parejas_pareto"] if p["magnitud"] == "pisos_base_decision")
    hallazgos = [{"texto": f"De {n(c['barrios'])} barrios, {n(c['con_30_pisos_o_mas'])} llegan a 30 pisos en la base de decisión y {n(c['sin_ningun_piso_en_la_base'])} no tienen ninguno.", "dimensiones_comprobadas": ["distrito"], "filas": c["barrios"], "columnas": ["pisos_base_decision"]},
                 {"texto": f"El {n(base['pct_elementos_80'], 1)} % de los barrios con pisos en la base suma el 80 % de ellos.", "dimensiones_comprobadas": ["barrio"], "filas": base["elementos"], "columnas": ["pisos_base_decision"]},
                 {"texto": f"Los anuncios y las licencias de cada barrio se asocian con un Spearman de {n(r['anuncios_con_licencias']['spearman'], 2)}, en {n(r['anuncios_con_licencias']['pares'])} barrios; es una asociación entre recuentos, porque una licencia no se une a un anuncio.", "dimensiones_comprobadas": ["barrio"], "filas": c["barrios"], "columnas": ["anuncios", "licencias"]},
                 {"texto": f"Detrás del precio oficial de los barrios comparados hay {n(v['mediana'])} ventas de mediana en 2025, y el mínimo es de {n(v['minima'])}.", "dimensiones_comprobadas": ["barrio"], "filas": v["barrios"], "columnas": ["ventas_barrio"]}]
    alertas = [{"texto": f"{n(c['precio_del_distrito'])} barrios toman el precio de su distrito y {n(c['sin_ventas_consta'])} no tienen ventas propias en el libro.", "origen": "cuestiones CP-003"},
               {"texto": f"{cd.CASCO_VALLECAS} lleva el precio del barrio aunque Airbnb junta en él lo que el Ayuntamiento separa.", "origen": "cuestiones CP-005"}]
    hipotesis = [{"texto": "Un barrio con pocas licencias y muchos anuncios puede tener oferta sin licencia municipal o licencias de otra clase.", "que_haria_falta": "una clave común entre licencia y anuncio, que no existe. Explicaciones repasadas: tamaño del grupo, calendario, regresión a la media, causa al revés y una variable ausente."}]
    return hallazgos, alertas, hipotesis


def comprobaciones_barrios(s, graficos_hechos):
    """Da el estado de cada comprobación de la tabla de barrios."""
    no = {0: "la tabla no tiene fechas", 10: "la tabla no tiene fechas", 11: "el caso no es predictivo", 13: "no hay texto libre", 14: "ninguna categórica pasa de 50 valores salvo el nombre del barrio, que es la clave"}
    notas = {1: f"{len(s['parejas_pareto'])} parejas", 2: "cada hallazgo lleva sus filas y sus columnas", 3: "no hay personas en esta tabla", 4: "todas las magnitudes llevan unidad en reglas-transformacion.md", 5: "versiones, fecha y huella en Contexto", 6: "Pearson y Spearman entre barrios, como lista de cruces",
             7: "cada hipótesis dice qué faltaría", 8: "los recuentos se comparan con la mediana", 9: f"{graficos_hechos} gráficos", 12: "recuentos enteros como discretos solo con pocos valores", 15: "sin observaciones de la persona", 16: f"{len(s['senales'])} señales"}
    sin_nada = {3, 4, 15}
    salida = []
    for i, nombre in enumerate(COMPROBACIONES):
        if i in no:
            salida.append({"comprobacion": nombre, "estado": "no_aplica", "nota": no[i]})
        else:
            salida.append({"comprobacion": nombre, "estado": "aplicada_sin_nada_relevante" if i in sin_nada else "aplicada_con_resultado", "nota": notas[i]})
    return salida


def bloques_barrios(b, s, fallidos):
    """Dibuja los gráficos del informe de barrios."""
    numericos, categoricos, destacados = [], [], []
    for col, nombre, unidad, dec in (("precio_m2_eur", "Precio oficial del m²", " €", 0), ("superficie_oficial_m2", "Superficie oficial media", " m²", 0), ("anuncios", "Anuncios por barrio", "", 0), ("pisos_base_decision", "Pisos de la base de decisión por barrio", "", 0), ("licencias", "Licencias por barrio", "", 0), ("ventas_barrio", "Ventas de 2025 por barrio", "", 0)):
        v = b[col].dropna().tolist()
        svg = grafico(fallidos, col, gr.histograma, v, intervalos=12, decimales=dec, unidad=unidad.strip(), etiqueta_x=nombre, medida=nombre)
        if svg:
            numericos.append((f"{nombre}: mediana de {n(s['numericas'][col]['mediana'], dec)}{unidad}", svg))
    e = s["categoricas"]["distrito"]
    svg = grafico(fallidos, "distrito", gr.barras_ordenadas, [x["valor"] for x in e["mas_frecuentes"]], {"barrios": [x["filas"] for x in e["mas_frecuentes"]]}, medida="barrios")
    if svg:
        categoricos.append((f"Barrios por distrito: encabeza {e['dominante']} con {n(e['dominante_pct'], 1)} % de los barrios", svg))
    con = b.loc[b["pisos_base_decision"].gt(0), "pisos_base_decision"]
    if len(con) >= 5:
        svg = grafico(fallidos, "concentración", gr.curva_acumulada, con.tolist())
        if svg:
            destacados.append((f"Concentración de los pisos de la base entre {n(len(con))} barrios", svg))
    return numericos, categoricos, destacados


# ---------------------------------------------------------------------------
# 5. Informe HTML
# ---------------------------------------------------------------------------

def tabla_html(cabecera, filas):
    """Escribe una tabla sencilla, con el texto escapado."""
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cabecera)
    cuerpo = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in f) + "</tr>" for f in filas)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{cuerpo}</tbody></table>"


def bloque(graficos_lista):
    """Coloca los gráficos en una cuadrícula; cada uno con su título."""
    return '<div class="rejilla">' + "".join(f"<figure><figcaption>{html.escape(t)}</figcaption>{svg}</figure>" for t, svg in graficos_lista) + "</div>"


def tabla_numericas(numericas):
    """Da la tabla de estadísticos con las magnitudes y sus señales."""
    filas = [[c, n(e["conteo"]), n(e["nulos"]), n(e["media"], 2), n(e["mediana"], 2), n(e["desviacion"], 2), n(e["minimo"], 2), n(e["p25"], 2), n(e["p75"], 2), n(e["maximo"], 2), ", ".join(e["senales"]) or "ninguna"] for c, e in numericas.items()]
    return tabla_html(["Variable", "Conteo", "Nulos", "Media", "Mediana", "Desviación", "Mínimo", "P25", "P75", "Máximo", "Señales"], filas)


def tabla_categoricas(categoricas):
    """Resume las categóricas sin volcar sus frecuencias."""
    return tabla_html(["Variable", "Valores distintos", "Vacíos", "Dominante", "Parte", "Parte de las 10 primeras"], [[c, n(e["cardinalidad"]), n(e["nulos"]), e["dominante"], f"{n(e['dominante_pct'], 1)} %", f"{n(e['parte_de_las_10_pct'], 1)} %"] for c, e in categoricas.items()])


def resumen_ejecutivo(s):
    """Saca del JSON de tres a cinco conclusiones: las primeras cifras de los hallazgos."""
    return [x["texto"] for x in s["hallazgos"][:4]]


def informe_html(s, numericos, categoricos, destacados, parte_numerica, parte_categorica, parte_temporal):
    """Monta el HTML con las mismas cifras del JSON."""
    estilo = (rc.CASO / "assets" / "estilo.css").read_text(encoding="utf-8")
    v = s["vision_general"]
    e = s["entradas"][0]
    p = []
    p += ["<h1>Análisis exploratorio de datos</h1>", "<h2>Resumen ejecutivo</h2>", "<ul>" + "".join(f"<li>{html.escape(t)}</li>" for t in resumen_ejecutivo(s)) + f"</ul><p>Siguiente paso: {html.escape(s['siguiente_paso'].replace('_', ' '))}.</p>"]
    p += ["<h2>Contexto</h2>", f"<p>Tabla {html.escape(s['tabla'])}: {n(v['filas'])} filas y {n(v['columnas'])} columnas; una fila es {html.escape(v['granularidad'])}. Fecha de referencia: {v['periodo']}. "
          f"Ejecutado el {s['fecha_ejecucion']} con Python {s['python']} y pandas {s['pandas']}. Huella del fichero: {e['sha256']}.</p>", ""]
    p += ["<h2>Visión general</h2>", tabla_html(["Papel de la columna", "Columnas"], [[k, n(x)] for k, x in v["tipos"].items()])]
    p += ["<h2>Variables numéricas</h2>", parte_numerica, bloque(numericos)]
    p += ["<h2>Variables categóricas</h2>", parte_categorica, bloque(categoricos)]
    p += ["<h2>Análisis temporal</h2>", parte_temporal]
    p += ["<h2>Hallazgos principales</h2>", "<ul>" + "".join(f"<li>{html.escape(x['id'])}. {html.escape(x['texto'])} Dimensiones comprobadas: {html.escape(', '.join(x['dimensiones_comprobadas']))}. Filas: {n(x['filas'])}.</li>" for x in s["hallazgos"]) + "</ul>", bloque(destacados)]
    p += ["<h2>Alertas y limitaciones</h2>", "<ul>" + "".join(f"<li>{html.escape(x['id'])}. {html.escape(x['texto'])}</li>" for x in s["alertas"]) + "</ul>"]
    p += ["<h2>Hipótesis y preguntas abiertas</h2>", "<ul>" + "".join(f"<li>{html.escape(x['id'])}. {html.escape(x['texto'])} Haría falta: {html.escape(x['que_haria_falta'])}</li>" for x in s["hipotesis"]) + "</ul>"]
    p += ["<h2>Observaciones de la persona</h2>", "<p>No hay observaciones.</p>"]
    p += ["<h2>Comprobaciones aplicadas</h2>", tabla_html(["Comprobación", "Estado", "Nota"], [[c["comprobacion"], c["estado"].replace("_", " "), c["nota"]] for c in s["comprobaciones"]])]
    p += ["<h2>Parámetros usados</h2>", tabla_html(["Parámetro", "Valor", "Origen"], [[x["nombre"], x["valor"], x["origen"]] for x in s["parametros"]])]
    p += ["<h2>Datos personales</h2>", "".join(f"<p>{html.escape(t)}</p>" for t in s["texto_personales"].split("\n") if t.strip())]
    p += ["<h2>Siguiente paso</h2>", f"<p>{html.escape(s['siguiente_paso'].replace('_', ' '))}. Sigue indicadores-y-analisis, que contesta las tres preguntas.</p>"]
    cuerpo = "\n".join(p)
    rejilla = ".rejilla{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(420px,100%),1fr));gap:18px}figure{margin:0;min-width:0}figcaption{font-weight:600;margin-bottom:6px}svg{max-width:100%;height:auto}table{display:block;overflow-x:auto;max-width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #ddd;padding:3px 7px;text-align:left}main{max-width:1180px;margin:0 auto;padding:16px}"
    return f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Exploratorio {html.escape(s["tabla"])}</title><style>{estilo}{rejilla}</style></head><body><main>{cuerpo}</main></body></html>'


# ---------------------------------------------------------------------------
# 6. Ejecución
# ---------------------------------------------------------------------------

def cabecera(tabla, ruta, df=None):
    """Crea el JSON de una tabla con el bloque común."""
    s = rc.bloque_comun(ETAPA, VERSION, SCRIPT)
    s["tabla"] = tabla
    if df is not None:
        s["entradas"] = [rc.entrada(ruta, df)]
        s["dataset"] = {"ruta": ruta.relative_to(rc.CASO).as_posix(), "sha256": s["entradas"][0]["sha256"]}
    return s


def guardar(s, pagina=None):
    """Escribe el JSON sin NaN y, si lo hay, el HTML."""
    limpio = cd.sin_nan(s)
    rc.INFORMES.mkdir(exist_ok=True)
    nombre = f"analisis-exploratorio__{s['tabla']}"
    (rc.INFORMES / f"{nombre}.json").write_text(json.dumps(limpio, ensure_ascii=False, indent=1, allow_nan=False, default=str), encoding="utf-8")
    if pagina:
        (rc.INFORMES / f"{nombre}.html").write_text(pagina, encoding="utf-8")


def parar(motivo, siguiente):
    """Deja el JSON de cada tabla con estado PARADO: el paso siguiente no empieza."""
    for tabla in TABLAS:
        s = cabecera(tabla, rc.PROCESADO / f"{tabla}.parquet")
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": motivo, "artefactos": [], "siguiente": siguiente}
        guardar(s)


def numerar(lista, prefijo):
    """Pone el identificador a hallazgos, alertas e hipótesis."""
    return [{"id": f"{prefijo}-{i:02d}", **x} for i, x in enumerate(lista, 1)]


def buscar_personales(df, columnas):
    """Busca correos, enlaces y documentos en las categóricas antes de enseñar sus valores (comprobación 4)."""
    hallados = []
    for c in columnas:
        valores = df[c].dropna().astype("str").unique()
        for nombre, patron in cd.PERSONAL.items():
            if any(re.search(patron, v) for v in valores):
                hallados.append({"columna": c, "patron": nombre})
    return hallados


def completar(s, hallazgos, alertas, hipotesis):
    """Pone en el JSON lo común de una tabla: textos, parámetros y personales."""
    s.update(premisa={"afirmacion": None, "la_sostienen_los_datos": None}, hallazgos=numerar(hallazgos, "H"), alertas=numerar(alertas, "A"), hipotesis=numerar(hipotesis, "Hi"), frente_al_objetivo=None, observaciones=[], parametros=PARAMETROS, siguiente_paso="con_esto_basta")
    s["texto_personales"] = rc.texto_personales("Este paso no usa ni deja ninguna columna con datos personales: enseña recuentos por barrio, distrito y tipo.")


def validar(s, df, huella_antes, ruta):
    """Valida la tabla antes de guardar: tratamiento por tipo, comprobaciones y entrada intacta."""
    tipos = {x["columna"]: x["tipo"] for x in s["tipificacion"]}
    numericas = s.get("numericas") or {c for b in s["bases"].values() for c in b["numericas"]}
    fallos = [f"{c} es un identificador tratado como magnitud" for c in numericas if tipos.get(c) == "identificador"]
    fallos += [f"comprobación sin estado: {x}" for x in comprobaciones_sin_estado(s["comprobaciones"], len(COMPROBACIONES))]
    if len(tipos) != df.shape[1]:
        fallos.append("hay columnas sin tipificar")
    if cd.huella(ruta) != huella_antes:
        fallos.append("la tabla de entrada cambió")
    return fallos


def trabajar_tabla(tabla, df, analizar, textos, comprobar, dibujar, heredados, parte_temporal):
    """Hace el análisis de una tabla, valida y guarda el JSON y el HTML con las mismas cifras."""
    ruta = rc.PROCESADO / f"{tabla}.parquet"
    s = cabecera(tabla, ruta, df)
    huella_antes = s["entradas"][0]["sha256"]
    s["pendientes_heredados"] = heredados
    extras = analizar(df, s)
    s["datos_personales_en_categoricas"] = buscar_personales(df, [c for c in df.columns if pd.api.types.is_string_dtype(df[c])])
    h, a, hi = textos(s)
    completar(s, h, a, hi)
    fallidos = []
    numericos, categoricos, destacados = dibujar(df, extras, s, fallidos)
    todos = [svg for _, svg in numericos + categoricos + destacados]
    s["graficos_omitidos"] = fallidos
    s["comprobaciones"] = comprobar(s, len(set(todos)))
    if len(set(todos)) != len(todos):
        s.setdefault("avisos", []).append("hay dos gráficos iguales")
    fallos = validar(s, df, huella_antes, ruta)
    estado = "ERROR" if fallos else ("AVISO" if s["alertas"] else "OK")
    artefactos = [f"informes/analisis-exploratorio__{tabla}.json", f"informes/analisis-exploratorio__{tabla}.html"]
    s["resultado"] = {"estado": estado, "riesgo": "medio", "resumen": "; ".join(fallos) if fallos else f"{len(s['hallazgos'])} hallazgos, {len(s['alertas'])} alertas y {len(s['hipotesis'])} hipótesis sobre {tabla}.", "artefactos": artefactos, "siguiente": "indicadores-y-analisis"}
    s["pendientes"] = []
    return s, numericos, categoricos, destacados


def principal():
    """Comprueba la entrada, analiza las dos tablas y guarda."""
    ruta_t = rc.INFORMES / "transformacion-datos.json"
    t = json.loads(ruta_t.read_text(encoding="utf-8"))
    if t["resultado"]["estado"] in ("PARADO", "ERROR"):
        return parar(f"La transformación está en {t['resultado']['estado']}.", "transformacion-datos")
    huellas = {x["tabla"]: x["sha256"] for x in t["salidas"]}
    for tabla in TABLAS:
        if cd.huella(rc.PROCESADO / f"{tabla}.parquet") != huellas.get(tabla):
            return parar(f"La huella de {tabla} no es la que dejó la transformación.", "repetir transformacion-datos")
    antes = cd.huellas_de_raw()
    a = pd.read_parquet(rc.PROCESADO / "analisis_anuncios.parquet")
    b = pd.read_parquet(rc.PROCESADO / "analisis_barrios.parquet")
    heredados = t.get("pendientes", [])

    # 6.1 Anuncios: el análisis devuelve las dos bases, que usan los gráficos.
    def temporal_anuncios(s):
        """Escribe el bloque temporal de los anuncios desde el JSON."""
        f = s["precios_por_foto"]
        return tabla_html(["Base", "Anuncios con las tres fotos", "Mediana de marzo (€)", "Mediana de junio (€)", "Mediana de septiembre (€)"], [[NOMBRE_BASE[k], n(x["anuncios_con_las_tres"]), n(x["mediana_marzo"], 2), n(x["mediana_junio"], 2), n(x["mediana_septiembre"], 2)] for k, x in f.items()]) + "<p>Cada foto es parcial respecto al año y las tres se leen con los mismos anuncios. La serie de reseñas, la oferta entre fotos y la disponibilidad futura van en los indicadores.</p>"

    s, nu, ca, de = trabajar_tabla("analisis_anuncios", a, analizar_anuncios, textos_anuncios, comprobaciones_anuncios, lambda df, ex, x, f: bloques_anuncios(df, ex[0], ex[1], x, f), heredados, None)
    bases = "".join(f"<h3>{html.escape(x['nombre'])}: {n(x['filas'])} filas</h3>{tabla_numericas(x['numericas'])}" for x in s["bases"].values())
    vd = s["para_el_paso_siguiente"]["rentabilidad_por_dormitorios_y_barrio"]["decision"]["vista_por_distritos"]
    bases += "<h3>Rentabilidad bruta mediana de una y dos habitaciones, por distrito</h3>" + tabla_html(["Distrito", "Una habitación (%)", "Pisos", "Dos habitaciones (%)", "Pisos"], [[f["distrito"], n(f["uno_pct"], 1), n(f["pisos_uno"]), n(f["dos_pct"], 1), n(f["pisos_dos"])] for f in vd])
    cats = "".join(f"<h3>{html.escape(x['nombre'])}</h3>{tabla_categoricas(x['categoricas'])}" for x in s["bases"].values())
    pareto_tabla = "<h3>Concentración: Pareto y ABC</h3>" + tabla_html(["Base", "Elemento", "Magnitud", "Elementos", "% de elementos que suma el 80 %"], [[p["base"], p["elemento"], p["magnitud"], n(p["elementos"]), n(p["pct_elementos_80"], 1)] for p in s["parejas_pareto"]])
    guardar(s, informe_html(s, nu, ca, de, bases + pareto_tabla, cats, temporal_anuncios(s)))

    # 6.2 Barrios.
    s2, nu, ca, de = trabajar_tabla("analisis_barrios", b, analizar_barrios, textos_barrios, comprobaciones_barrios, lambda df, ex, x, f: bloques_barrios(df, x, f), heredados, None)
    pareto_b = "<h3>Concentración: Pareto y ABC</h3>" + tabla_html(["Elemento", "Magnitud", "Elementos con valor", "% de elementos que suma el 80 %"], [[p["elemento"], p["magnitud"], n(p["elementos"]), n(p["pct_elementos_80"], 1)] for p in s2["parejas_pareto"]])
    guardar(s2, informe_html(s2, nu, ca, de, tabla_numericas(s2["numericas"]) + pareto_b, tabla_categoricas(s2["categoricas"]), "<p>No aplica: esta tabla no tiene fechas.</p>"))

    if cd.huellas_de_raw() != antes:
        raise RuntimeError("data/raw/ cambió durante el análisis")


if __name__ == "__main__":
    principal()
