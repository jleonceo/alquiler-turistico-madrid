"""Indicadores del caso: contesta las tres preguntas aprobadas y las 16 de comprobación. El caso no entrena ningún modelo.

Lo que se calcula y contra qué se compara está en config/metodo/04_planteamientos.md, escrito antes de calcular:
si falta algo, el script para. Cada cifra se rehace por otro camino y se guarda con su población, sus filas y su periodo.
Escribe informes/indicadores.json, de él informes/indicadores.md y config/metodo/06_borrador_de_hallazgos.md.

Se lanza después de scripts/analisis_exploratorio.py. Remuestreo con la semilla fija de calidad_datos.py.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/indicadores.py
"""
import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations, product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import analisis_exploratorio as eda
import calidad_datos as cd
import reglas_caso as rc
from analisis_exploratorio import dormitorios_de, n, nivel_ocupacion  # noqa: F401  (las usan también las pruebas)

# ---------------------------------------------------------------------------
# 1. Configuración
# ---------------------------------------------------------------------------

ETAPA = "indicadores-y-analisis"
VERSION = "1.0"
SCRIPT = "scripts/indicadores.py"
PLANTEAMIENTOS = rc.CASO / "config" / "metodo" / "04_planteamientos.md"
BORRADOR = rc.CASO / "config" / "metodo" / "06_borrador_de_hallazgos.md"
DATOS_NECESARIOS = rc.CASO / "config" / "fuentes" / "02_datos_necesarios.md"
PRECIOS_MERCADO = rc.CASO / "config" / "fuentes" / "precios_de_mercado.json"
MINIMO = cd.MIN_GRUPO
MINIMO_VARIANTE = min(cd.MIN_VARIANTE)
CONFIANZA = 0.95
TOPE = 255
PERIODO = "foto del 17/09/2026"
TOLERANCIA = 1e-6
ORIGEN_DEL_TEXTO = "lista de comprobación del análisis, escrita antes de calcular"
REGLA_DECISION = "base de decisión, reglas §3: pisos fuera del centro histórico con los filtros de tamaño, precio, ocupación y estancia"
REGLA_COMPARACION = "base de comparación, reglas §3: los filtros de un análisis habitual de este mercado, con los 180 días y todos los tipos de alquiler"
SUPERFICIE = "rent_valoraciones_desc_pct"
PARAMETROS = [{"nombre": "mínimo de casos por grupo o celda", "valor": str(MINIMO), "origen": "reglas §3"}, {"nombre": "mínimo en las variantes que lo fijan", "valor": str(MINIMO_VARIANTE), "origen": "reglas §3"},
              {"nombre": "confianza del intervalo", "valor": str(CONFIANZA), "origen": "04_planteamientos.md"}, {"nombre": "remuestreos", "valor": str(cd.REMUESTREOS), "origen": "04_planteamientos.md"},
              {"nombre": "semilla", "valor": str(cd.SEMILLA), "origen": "calidad_datos.py"}, {"nombre": "rango para mover los pesos", "valor": "sin valor: no hay puntuación con pesos", "origen": "no aplica"},
              {"nombre": "periodo para medir hacia adelante", "valor": "sin valor: nada de esto predice", "origen": "no aplica"}]

# Las 16 preguntas de comprobación, con su orden.
LAS_16 = [{"id": f"S{i:02d}", "bloque": b, "texto": t} for i, (b, t) in enumerate([
    ("precio", "¿Cuál es el precio medio y su rango, por distrito y por barrio?"), ("precio", "¿Cuál es el ranking de distritos y barrios por precio?"), ("precio", "¿Qué factores, aparte de la localización, van asociados al precio?"),
    ("precio", "¿Qué relación hay entre el tamaño y el precio?"), ("precio", "¿Qué influencia tiene la competencia en el precio?"), ("precio", "¿Qué precio tiene cada tipo de alquiler?"),
    ("ocupacion", "¿Cuál es la ocupación media, por distrito y por barrio?"), ("ocupacion", "¿Qué probabilidad tiene cada nivel de ocupación por distrito?"), ("ocupacion", "¿Cuál es el ranking de distritos y barrios por ocupación?"),
    ("ocupacion", "¿Qué factores van asociados a la ocupación?"), ("ocupacion", "¿Qué relación hay entre el tamaño y la ocupación?"), ("ocupacion", "¿Qué influencia tiene la competencia en la ocupación?"),
    ("compra", "¿Cuál es el ranking del m² por distrito?"), ("compra", "¿Cuál es el ranking del precio del inmueble por distrito?"), ("compra", "¿Qué relación tiene el precio de compra con el precio del alquiler, por distrito?"),
    ("compra", "¿Qué relación tiene el precio de compra con la ocupación, por distrito?")], 1)]

# Rasgos para buscar asociaciones, los mismos del reconocimiento; los circulares salen de la lectura de la ocupación.
RASGOS = ["huespedes", "dormitorios", "camas", "banos", "equipamientos", "number_of_reviews", "review_scores_rating", "review_scores_location", "calculated_host_listings_count", "estancia_noches", "dias_libres_365"]
CIRCULARES = {"number_of_reviews", "dias_libres_365"}  # la ocupación se calcula con las reseñas, y los días libres dependen de lo reservado
NOMBRE_RASGO = {"huespedes": "los huéspedes", "dormitorios": "las habitaciones", "camas": "las camas", "banos": "los baños", "equipamientos": "los equipamientos", "review_scores_rating": "la valoración", "review_scores_location": "la valoración de la ubicación", "calculated_host_listings_count": "los anuncios del anfitrión", "estancia_noches": "la estancia mínima"}
NOMBRE_PRUEBA = {"sin_temporada": "temporada", "sin_anfitriones_grandes": "anfitriones", "sin_cotizaciones_lejanas": "cotización", "solo_1_y_2_dormitorios": "habitaciones", "sin_ocupacion_como_cero": "sin ocupación"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ETIQUETA = {"toda_la_foto": "Toda la foto", "base_de_decision": "Base de decisión", "grupo_firme": "Grupo firme", "base_decision": "Base de decisión", "base_comparacion": "Base de comparación"}
SI_NO = ["aire", "ascensor", "lavadora", "parking", "superanfitrion", "lleva_registro"]
CLAVES_ESCRITAS = ["unidad", "minimo", "empates", "referencia", "azar_en_grupos", "pesos", "hacia_adelante", "cobertura", "periodos", "planteamiento_completo", "cifras_con_poblacion", "segunda_via", "minimo_respetado",
                   "con_referencia", "comprobaciones_calculadas", "reproducible", "sin_resultados_escritos", "raw_intacto"]


# ---------------------------------------------------------------------------
# 2. Funciones del capítulo 42 y cálculos sin pandas para la segunda vía
# ---------------------------------------------------------------------------

def intervalo_wilson(si, n_casos, confianza=CONFIANZA):
    """Intervalo de Wilson de una proporción, que se porta bien con pocos casos y con proporciones extremas (42.6)."""
    z = stats.norm.ppf(1 - (1 - confianza) / 2)
    p = si / n_casos
    centro = (p + z**2 / (2 * n_casos)) / (1 + z**2 / n_casos)
    margen = z * np.sqrt(p * (1 - p) / n_casos + z**2 / (4 * n_casos**2)) / (1 + z**2 / n_casos)
    return centro - margen, centro + margen


def comparar_con_total(df, grupo, objetivo, minimo=MINIMO, confianza=CONFIANZA):
    """Parte de «sí» de cada grupo, su intervalo y si queda por encima o por debajo del total (42.6, tal como está)."""
    total = df[objetivo].mean()
    t = df.groupby(grupo)[objetivo].agg(n="size", si="sum")
    t = t[t["n"] >= minimo].copy()
    if t.empty:
        return t.assign(pct=[], desde=[], hasta=[], frente_al_total=[]), 0.0
    t["pct"] = 100 * t["si"] / t["n"]
    lim = t.apply(lambda r: intervalo_wilson(r["si"], r["n"], confianza), axis=1, result_type="expand")
    t["desde"], t["hasta"] = 100 * lim[0], 100 * lim[1]
    t["frente_al_total"] = np.select([t["desde"] > 100 * total, t["hasta"] < 100 * total], ["por encima", "por debajo"], "no se distingue")
    return t, round(len(t) * (1 - confianza), 1)


def intervalo_mediana(valores, nombre):
    """Intervalo del 95 % de una mediana, con el remuestreo de la cadena."""
    return tuple(float(x) for x in np.quantile(cd.medianas_remuestreadas(valores, nombre), [0.025, 0.975]))


def diferencia_de_medianas(a, b, nombre_a, nombre_b):
    """Intervalo del 95 % de la diferencia de dos medianas: si no cruza el cero, los dos grupos se distinguen."""
    bajo, alto = np.quantile(cd.medianas_remuestreadas(a, nombre_a) - cd.medianas_remuestreadas(b, nombre_b), [0.025, 0.975])
    return {"a": str(nombre_a), "b": str(nombre_b), "diferencia": float(np.median(a) - np.median(b)), "bajo": float(bajo), "alto": float(alto), "se_distinguen": bool(bajo > 0 or alto < 0)}


def mediana(valores):
    """Mediana escrita a mano, para la segunda vía."""
    v = sorted(valores)
    k = len(v) // 2
    return v[k] if len(v) % 2 else (v[k - 1] + v[k]) / 2


def cuantil(valores, q):
    """Cuantil con interpolación lineal escrito a mano, para la segunda vía."""
    v = sorted(valores)
    pos = (len(v) - 1) * q
    i = math.floor(pos)
    return v[i] if i + 1 == len(v) else v[i] + (pos - i) * (v[i + 1] - v[i])


def rangos(v):
    """Da el rango medio de cada valor, con los empates repartidos, para Spearman a mano."""
    orden = sorted(range(len(v)), key=lambda i: v[i])
    salida = [0.0] * len(v)
    i = 0
    while i < len(orden):
        j = i
        while j + 1 < len(orden) and v[orden[j + 1]] == v[orden[i]]:
            j += 1
        for k in range(i, j + 1):
            salida[orden[k]] = (i + j) / 2 + 1
        i = j + 1
    return salida


def pearson(x, y):
    """Pearson escrito a mano, para la segunda vía."""
    mx, my = math.fsum(x) / len(x), math.fsum(y) / len(y)
    sxy = math.fsum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / math.sqrt(math.fsum((a - mx) ** 2 for a in x) * math.fsum((b - my) ** 2 for b in y))


def por_grupo(df, grupo, medida, minimo=MINIMO):
    """Resume una medida por grupo; los que no llegan al mínimo salen aparte, con su recuento y sin conclusión."""
    v = df.dropna(subset=[grupo, medida])
    g = v.groupby(grupo)[medida]
    t = g.agg(casos="size", media="mean", mediana="median", minimo="min", maximo="max")
    t["q25"], t["q75"] = g.quantile(0.25), g.quantile(0.75)
    t = t.reset_index().rename(columns={grupo: "grupo"}).sort_values(["mediana", "grupo"], ascending=[False, True])
    filas = [{"grupo": str(f["grupo"]), "casos": int(f["casos"]), "media": float(f["media"]), "mediana": float(f["mediana"]), "q25": float(f["q25"]), "q75": float(f["q75"]), "minimo": float(f["minimo"]), "maximo": float(f["maximo"])} for _, f in t.iterrows() if f["casos"] >= minimo]
    fuera = [{"grupo": str(f["grupo"]), "casos": int(f["casos"])} for _, f in t.iterrows() if f["casos"] < minimo]
    return filas, sorted(fuera, key=lambda x: (-x["casos"], x["grupo"]))


def comprobar_por_grupo(nombre, filas, df, grupo, medida):
    """Rehace la tabla sin pandas, recorriendo las filas una a una, y dice la mayor diferencia."""
    listas = defaultdict(list)
    for k, x in zip(df[grupo].tolist(), df[medida].tolist()):
        if k is not None and x is not None and k == k and x == x:
            listas[str(k)].append(float(x))
    maxima = 0.0
    for f in filas:
        v = listas[f["grupo"]]
        pares = [(f["casos"], len(v)), (f["mediana"], mediana(v)), (f["q25"], cuantil(v, 0.25)), (f["media"], math.fsum(v) / len(v))]
        maxima = max(maxima, *(abs(a - b) for a, b in pares))
    return {"tabla": nombre, "celdas": 4 * len(filas), "diferencia_maxima": maxima, "coinciden": maxima < TOLERANCIA}


class Registro:
    """Apunta cada cifra con su segunda vía: lo que no coincide acaba en la validación 3."""

    def __init__(self):
        self.vias = []

    def tabla(self, nombre, df, grupo, medida, minimo=MINIMO):
        """Da la tabla por grupo y apunta su comprobación."""
        filas, fuera = por_grupo(df, grupo, medida, minimo)
        self.vias.append(comprobar_por_grupo(nombre, filas, df, grupo, medida))
        return filas, fuera

    def correlacion(self, nombre, x, y):
        """Da Pearson y Spearman y los rehace a mano."""
        r = eda.correlaciones(x, y)
        d = pd.DataFrame({"x": x, "y": y}).dropna()
        if r["spearman"] is None:
            self.vias.append({"tabla": nombre, "celdas": 0, "diferencia_maxima": 0.0, "coinciden": True, "nota": "sin pares suficientes"})
            return r
        a, b = d["x"].astype("float64").tolist(), d["y"].astype("float64").tolist()
        maxima = max(abs(r["pearson"] - pearson(a, b)), abs(r["spearman"] - pearson(rangos(a), rangos(b))))
        self.vias.append({"tabla": nombre, "celdas": 2, "diferencia_maxima": maxima, "coinciden": maxima < TOLERANCIA})
        return r

    def cifra(self, nombre, valor, segunda, filas, poblacion, periodo=PERIODO):
        """Da una cifra suelta con sus dos vías, su población, sus filas y su periodo."""
        coinciden = (valor is None and segunda is None) or (valor is not None and segunda is not None and abs(valor - segunda) < max(TOLERANCIA, 1e-9 * abs(valor)))
        self.vias.append({"tabla": nombre, "celdas": 1, "diferencia_maxima": None if valor is None or segunda is None else abs(valor - segunda), "coinciden": bool(coinciden)})
        return {"nombre": nombre, "valor": valor, "filas": filas, "poblacion": poblacion, "periodo": periodo, "segunda_via": segunda, "coinciden": bool(coinciden)}

    def resumen(self, nombre, serie, poblacion):
        """Da el recuento, la media, la mediana, el rango y los cuartiles de una serie, cada uno con su segunda vía."""
        s = serie.dropna().astype("float64")
        v = s.tolist()
        if not v:
            return {"casos": 0, "media": None, "mediana": None, "minimo": None, "maximo": None, "q25": None, "q75": None}, []
        pares = [("media", float(s.mean()), math.fsum(v) / len(v)), ("mediana", float(s.median()), mediana(v)), ("minimo", float(s.min()), min(v)), ("maximo", float(s.max()), max(v)), ("q25", float(s.quantile(0.25)), cuantil(v, 0.25)), ("q75", float(s.quantile(0.75)), cuantil(v, 0.75))]
        return {"casos": len(v), **{k: a for k, a, _ in pares}}, [self.cifra(f"{nombre}: {k}", a, b, len(v), poblacion) for k, a, b in pares]


def mejor_cuarto(medianas):
    """Marca los grupos en el mejor cuarto: el mismo valor recibe la misma marca, porque el corte es el valor."""
    return medianas.ge(medianas.quantile(0.75))


def empates_bien(medianas, marcas):
    """Comprueba con lo ejecutado que dos barrios con el mismo valor tienen la misma marca."""
    por_valor = defaultdict(set)
    for b, v in medianas.items():
        por_valor[v].add(bool(marcas[b]))
    return all(len(x) == 1 for x in por_valor.values())


def unidad_correcta(df):
    """Comprueba que la medida cuenta anuncios: la clave no se repite."""
    return bool(df["id"].is_unique)


def lleva_aviso(cuartil_bajo, cuartil_base):
    """Dice si un barrio lleva el aviso: su cuartil bajo no supera el cuartil bajo de toda la base (reglas §3)."""
    return bool(cuartil_bajo <= cuartil_base)


def escritos_a_mano(codigo, resultados):
    """Busca en el código una comprobación con un sí escrito a mano o un resultado de una ejecución (validación 8)."""
    hallados = []
    for clave in CLAVES_ESCRITAS:
        if re.search(rf"[\"']{clave}[\"']\s*:\s*True\b", codigo):
            hallados.append(f"{clave} escrito como sí")
    hallados += [f"resultado escrito: {r}" for r in resultados if str(r) in codigo]
    return hallados


def falta_en_planteamiento(texto):
    """Dice qué falta en el planteamiento de cada pregunta; lista vacía si está completo."""
    bloques = re.split(r"^## ", texto, flags=re.M)
    preguntas = {b.split(" ")[1]: b for b in bloques if b.startswith("Pregunta ")}
    faltas = [f"pregunta {i}: no está" for i in ("1", "2", "3") if i not in preguntas]
    for i, b in preguntas.items():
        faltas += [f"pregunta {i}: {c}" for c in ("Decisión:", "Medida:", "Referencia:", "Mínimo:", "Qué cambia la decisión:") if c not in b]
    if "población" not in texto.lower():
        faltas.append("la población")
    return faltas


def vista(a):
    """Deja los anuncios con los nombres que usan las funciones de grupo de calidad_datos.py."""
    return pd.DataFrame({"id": a["id"], "barrio": a["barrio"], "piso": a["tipo_alquiler"].eq("Entire home/apt"), "dentro": a["lado_centro"].eq("dentro"), "ocupacion": a["ocupacion_dias"], "accommodates": a["huespedes"], "banos": a["banos"], "bedrooms": a["dormitorios"], "beds": a["camas"],
                         "estancia": a["estancia_noches"], "precio": a["precio_eur"], "p_mar": a["precio_mar_eur"], "p_jun": a["precio_jun_eur"], "sup_regla": a["superficie_valoraciones_m2"], "m2": a["precio_m2_eur"], "temporada": a["declara_temporada"], "property_type": a["tipo_inmueble"],
                         "anuncios_anfitrion": a["anuncios_anfitrion"], "dias_cotizacion": a["dias_cotizacion"], "dias_cotizacion_mar": a["dias_cotizacion_mar"], "dias_cotizacion_jun": a["dias_cotizacion_jun"]})


def grupo_y_firmes(L, quitados, reglas):
    """Aplica la regla §7: el grupo en más de 6 de las 12 variantes y, de él, los que aguantan las cinco pruebas."""
    pruebas = rc.pruebas_del_grupo(L, quitados, reglas)
    return pruebas["grupo"], pruebas["firmes"], cd.grupo_de(L, excluir=quitados)[1]


def avisos_del_barrio(pisos, cuartil_bajo, cuartil_base, sigue_sin_el_tope, pocos):
    """Da los tres avisos de las reglas §3: depende del tope, pocos anuncios y cuartil bajo."""
    return {"depende_del_tope": not sigue_sin_el_tope, "pocos_anuncios": pisos <= pocos, "cuartil_bajo": lleva_aviso(cuartil_bajo, cuartil_base)}


def variantes_a_mano(L, quitados, reglas, prueba):
    """Rehace sin pandas las 12 variantes de una prueba, recorriendo los pisos uno a uno."""
    filas = list(zip(L["barrio"].tolist(), L["piso"].tolist(), L["dentro"].tolist(), L["ocupacion"].tolist(), L["accommodates"].tolist(), L["banos"].tolist(), L["bedrooms"].tolist(), L["beds"].tolist(), L["estancia"].tolist(), L["precio"].tolist(), L["p_mar"].tolist(), L["p_jun"].tolist(), L["sup_regla"].tolist(), L["m2"].tolist(),
                     L["temporada"].tolist(), L["anuncios_anfitrion"].tolist(), L["dias_cotizacion"].tolist(), L["dias_cotizacion_mar"].tolist(), L["dias_cotizacion_jun"].tolist(), quitados.tolist()))
    veces = Counter()
    for est, i_precio in product(cd.ESTANCIAS, (10, 11, 9)):
        i_dias = {10: 17, 11: 18, 9: 16}[i_precio]
        por_barrio = defaultdict(list)
        for f in filas:
            ocu, h, ba, dor, cam, es, pre = f[3], f[4], f[5], f[6], f[7], f[8], f[i_precio]
            if not f[1] or f[2] or f[19] or not (h <= 8 and ba <= 5 and dor <= 5 and cam <= 6 and es <= est and 20 <= pre <= 1000) or (ocu <= 0 and prueba != "sin_ocupacion_como_cero"):
                continue
            if (prueba == "sin_temporada" and f[14]) or (prueba == "sin_anfitriones_grandes" and f[15] >= reglas["anfitrion_anuncios"]) or (prueba == "solo_1_y_2_dormitorios" and dor not in reglas["dormitorios"]) or (prueba == "sin_cotizaciones_lejanas" and f[i_dias] > reglas["cotizacion_dias"]):
                continue
            por_barrio[f[0]].append(100 * pre * ocu / (f[12] * f[13] * cd.DESCUENTO))
        for minimo in cd.MIN_VARIANTE:
            medianas = {b: mediana(v) for b, v in por_barrio.items() if len(v) >= minimo}
            if medianas:
                corte = cuantil(list(medianas.values()), 0.75)
                veces.update(b for b, m in medianas.items() if m >= corte)
    return veces


def superficie_movida(grupo, superficie, nuevas, regla):
    """Cambia la superficie solo a los pisos que la regla deja en la de su grupo: el que llega a 140 m² por sus baños no se mueve."""
    s = superficie.copy()
    for g, m2 in nuevas.items():
        s = s.mask(grupo.eq(g) & superficie.eq(regla[g]), float(m2))
    return s


def tipos_que_se_dan(t, grupo, medida):
    """Da el primero y los que no se distinguen de él con el intervalo de la diferencia de medianas."""
    g = t.dropna(subset=[medida]).groupby(grupo)[medida].agg(["size", "median"])
    g = g.loc[g["size"].ge(MINIMO)]
    orden = sorted(g.index, key=lambda k: (-g.loc[k, "median"], k))
    if not orden:
        return {"medianas": {}, "se_dan": []}
    pares = pares_de(t, grupo, medida, orden)
    empatados = [p["b"] if p["a"] == orden[0] else p["a"] for p in pares if orden[0] in (p["a"], p["b"]) and not p["se_distinguen"]]
    return {"medianas": {str(k): float(g.loc[k, "median"]) for k in orden}, "se_dan": [str(orden[0])] + sorted(str(x) for x in empatados)}


def sensibilidad_superficie(d, rangos, cd_descuento=cd.DESCUENTO):
    """Repite la pregunta 1 en cada combinación de los extremos de superficie y dice si cambian los tipos que se dan."""
    nombres = sorted(rangos)
    regla = {g: float(cd.superficie_regla(pd.DataFrame({"bedrooms": [float(g)], "banos": [1.0]})).iloc[0]) for g in nombres}

    def medir(superficie):
        """Calcula la rentabilidad con una superficie y mira qué tipos se dan."""
        t = d.assign(rent_s=100 * d["ingreso_anual_eur"] / (superficie * d["precio_m2_eur"] * cd_descuento))
        salida = tipos_que_se_dan(t, "grupo_dormitorios", "rent_s")
        if "tipo_inmueble" in t:
            salida["tipo_de_inmueble_se_dan"] = tipos_que_se_dan(t, "tipo_inmueble", "rent_s")["se_dan"]
        return salida

    base = medir(d["superficie_valoraciones_m2"])
    combinaciones = []
    for extremos in product(*(rangos[g] for g in nombres)):
        nuevas = dict(zip(nombres, extremos))
        combinaciones.append({"superficies": nuevas, **medir(superficie_movida(d["grupo_dormitorios"], d["superficie_valoraciones_m2"], nuevas, regla))})
    cambia = [c for c in combinaciones if set(c["se_dan"]) != set(base["se_dan"])]
    cambia_i = [c for c in combinaciones if set(c.get("tipo_de_inmueble_se_dan", [])) != set(base.get("tipo_de_inmueble_se_dan", []))]
    return {"regla": regla, "se_dan_con_la_regla": base["se_dan"], "tipo_de_inmueble_con_la_regla": base.get("tipo_de_inmueble_se_dan", []), "medianas_con_la_regla": base["medianas"], "combinaciones": combinaciones, "cambia": bool(cambia), "combinaciones_que_cambian": len(cambia),
            "tipos_que_aparecen": sorted({tuple(c["se_dan"]) for c in combinaciones}), "cambia_tipo_de_inmueble": bool(cambia_i), "combinaciones_que_cambian_el_inmueble": len(cambia_i)}


def comparar_con_baratos(grupo, precios):
    """Compara el grupo con tantos barrios de m² más barato como barrios tiene; un empate se deshace por el nombre."""
    baratos = sorted(precios.index, key=lambda b: (precios[b], b))[:len(grupo)]
    coinciden = sorted(set(baratos) & set(grupo))
    return {"baratos": baratos, "coinciden": coinciden, "cuantos": len(coinciden), "de": len(grupo), "barrios_entre_los_que_se_elige": len(precios)}


def incluye_planta_baja(planta):
    """Marca las licencias que nombran la planta baja, sola o con otras: la columna es texto libre y no se interpreta más."""
    return planta.str.contains("BAJA", regex=False, na=False).astype("bool")


def puestos_con_un_ano(t, medida, fecha, minimo=MINIMO):
    """Repite el orden de los barrios con los pisos cuya primera reseña tiene un año o más: la ocupación cuenta reseñas de 12 meses y un anuncio nuevo sale bajo."""
    corte = pd.Timestamp(fecha) - pd.DateOffset(years=1)
    x = t.loc[pd.to_datetime(t["first_review"], format="%Y-%m-%d").le(corte)]
    g = x.groupby("barrio")[medida].agg(["size", "median"])
    g = g.loc[g["size"].ge(minimo)]
    orden = sorted(g.index, key=lambda b: (-g.loc[b, "median"], b))
    marcas = mejor_cuarto(g["median"]) if len(g) else pd.Series(dtype="bool")
    barrios = [{"barrio": str(b), "pisos": int(g.loc[b, "size"]), "mediana_pct": float(g.loc[b, "median"]), "puesto": i, "en_el_mejor_cuarto": bool(marcas[b])} for i, b in enumerate(orden, 1)]
    return {"corte": corte.strftime("%Y-%m-%d"), "pisos": len(x), "barrios_comparados": len(barrios), "barrios": barrios}


def cifras_de_la_recomendacion(t):
    """Da las cifras de los pisos que se recomiendan: recuento y, en mediana, rentabilidad, compra e ingreso, con y sin descuento."""
    campos = {"rentabilidad_sin_descuento_pct": "rent_valoraciones_sin_pct", "rentabilidad_con_descuento_pct": "rent_valoraciones_desc_pct", "compra_sin_descuento_eur": "compra_valoraciones_sin_eur", "compra_con_descuento_eur": "compra_valoraciones_desc_eur", "ingreso_anual_eur": "ingreso_anual_eur"}
    return {"pisos": len(t), **{k: float(t[c].median()) if len(t) else None for k, c in campos.items()}}


def precio_de_mercado(t):
    """Repite la compra y la rentabilidad de los pisos recomendados con los precios del m² que piden hoy los portales."""
    if not PRECIOS_MERCADO.exists():
        return {"consulta": None, "fuentes": []}
    cfg = json.loads(PRECIOS_MERCADO.read_text(encoding="utf-8"))
    fuentes = []
    for f in cfg["fuentes"]:
        if not len(t) or not set(t["barrio"]) <= set(f["barrios"]):
            continue
        compra = t["compra_valoraciones_sin_eur"] * t["barrio"].map(f["barrios"]) / t["precio_m2_eur"]
        rent = 100 * t["ingreso_anual_eur"] / compra
        barrios = [{"barrio": b, "precio_m2_oficial_eur": float(t.loc[x.index[0], "precio_m2_eur"]), "precio_m2_mercado_eur": float(f["barrios"][b]),
                    "subida_pct": 100 * (f["barrios"][b] / float(t.loc[x.index[0], "precio_m2_eur"]) - 1), "compra_mediana_eur": float(compra[x.index].median()), "rentabilidad_mediana_pct": float(rent[x.index].median())}
                   for b, x in t.groupby("barrio")]
        fuentes.append({"fuente": f["fuente"], "compra_mediana_eur": float(compra.median()), "rentabilidad_mediana_pct": float(rent.median()),
                        "rebaja_que_supone_el_descuento_pct": 100 * (1 - float(t["compra_valoraciones_desc_eur"].median()) / float(compra.median())), "barrios": barrios})
    return {"consulta": cfg["consulta"], "fuentes": fuentes}


def parte_de_operadores_grandes(t, barrios, anuncios):
    """Da qué parte de los pisos de unos barrios son de anfitriones con ese número de anuncios o más."""
    x = t.loc[t["barrio"].isin(barrios), "anuncios_anfitrion"]
    return 100 * float(x.ge(anuncios).sum()) / len(x) if len(x) else None


def rentabilidad_de_barrios(d, barrios, nombre):
    """Da la mediana conjunta de los pisos de unos barrios, con su recuento y su intervalo."""
    v = d.loc[d["barrio"].isin(barrios), SUPERFICIE].to_numpy()
    if not len(v):
        return {"pisos": 0, "mediana_pct": None, "ic_bajo": None, "ic_alto": None}
    bajo, alto = intervalo_mediana(v, nombre)
    return {"pisos": len(v), "mediana_pct": float(np.median(v)), "ic_bajo": bajo, "ic_alto": alto}


def rango_de_rentabilidad(t):
    """Da la mediana conjunta de unos pisos en cada combinación de foto y descuento, y la peor y la mejor (planteamiento, pregunta 3)."""
    combinaciones = []
    for foto, col in (("marzo", "p_mar"), ("junio", "p_jun"), ("septiembre", "precio")):
        x = t.loc[t[col].between(20, 1000)]
        for con_descuento, factor in ((True, cd.DESCUENTO), (False, 1.0)):
            r = cd.rentabilidad(x, col, factor)
            combinaciones.append({"foto": foto, "descuento": con_descuento, "pisos": len(x), "mediana": float(r.median()) if len(x) else None})
    validas = [c for c in combinaciones if c["mediana"] is not None]
    if not validas:
        return {"minimo": None, "maximo": None, "peor": None, "mejor": None, "combinaciones": combinaciones}
    peor, mejor = min(validas, key=lambda c: c["mediana"]), max(validas, key=lambda c: c["mediana"])
    return {"minimo": peor["mediana"], "maximo": mejor["mediana"], "peor": {k: peor[k] for k in ("foto", "descuento")}, "mejor": {k: mejor[k] for k in ("foto", "descuento")}, "combinaciones": combinaciones}


def comparar_medianas_con_total(df, grupo, medida, referencia, minimo=MINIMO):
    """Adapta comparar_con_total a una mediana: el intervalo sale del remuestreo y el grupo se pone frente a la de toda la base."""
    v = df.dropna(subset=[medida])
    filas = {}
    for k, g in v.groupby(grupo):
        if len(g) >= minimo:
            bajo, alto = intervalo_mediana(g[medida].to_numpy(), k)
            filas[str(k)] = {"ic_bajo": bajo, "ic_alto": alto, "frente_al_total": "por encima" if bajo > referencia else "por debajo" if alto < referencia else "no se distingue"}
    return filas, round(len(filas) * (1 - CONFIANZA), 1)


def pares_de(df, grupo, medida, nombres):
    """Compara cada par de grupos con el intervalo de la diferencia de medianas."""
    valores = {k: df.loc[df[grupo].eq(k), medida].dropna().to_numpy() for k in nombres}
    return [diferencia_de_medianas(valores[a], valores[b], a, b) for a, b in combinations(nombres, 2)]


# ---------------------------------------------------------------------------
# 3. Las tres preguntas
# ---------------------------------------------------------------------------

def tabla_de_tipos(d, grupo, reg, nombre, base_mediana):
    """Compara tipos de piso: rentabilidad con intervalo, la misma sin descuento, euros al año y contraste con la superficie oficial."""
    filas, fuera = reg.tabla(f"P1 {nombre}: rentabilidad", d, grupo, SUPERFICIE)
    euros, _ = reg.tabla(f"P1 {nombre}: euros", d, grupo, "ingreso_anual_eur")
    sin, _ = reg.tabla(f"P1 {nombre}: sin descuento", d, grupo, "rent_valoraciones_sin_pct")
    oficial, _ = reg.tabla(f"P1 {nombre}: superficie oficial", d, grupo, "rent_oficial_desc_pct")
    intervalos, azar_total = comparar_medianas_con_total(d, grupo, SUPERFICIE, base_mediana)
    e, s, o = ({f["grupo"]: f for f in x} for x in (euros, sin, oficial))
    salida = [{"grupo": f["grupo"], "pisos": f["casos"], "rentabilidad_mediana_pct": f["mediana"], "cuartil_bajo_pct": f["q25"], **intervalos[f["grupo"]], "sin_descuento_pct": s[f["grupo"]]["mediana"], "euros_al_ano": e[f["grupo"]]["mediana"], "superficie_oficial_pct": o[f["grupo"]]["mediana"]} for f in filas]
    nombres = [f["grupo"] for f in salida]
    pares = pares_de(d, grupo, SUPERFICIE, nombres)
    pares_euros = pares_de(d, grupo, "ingreso_anual_eur", nombres)
    primero = nombres[0] if nombres else None
    empatados = [p["b"] if p["a"] == primero else p["a"] for p in pares if primero in (p["a"], p["b"]) and not p["se_distinguen"]]
    mejor_euros = max(salida, key=lambda f: f["euros_al_ano"])["grupo"] if salida else None
    empatados_euros = [p["b"] if p["a"] == mejor_euros else p["a"] for p in pares_euros if mejor_euros in (p["a"], p["b"]) and not p["se_distinguen"]]
    return {"tabla": salida, "sin_conclusion": fuera, "primero": primero, "no_se_distinguen_del_primero": empatados, "se_dan": ([primero] + empatados) if primero else [], "pares": pares, "pares_probados": len(pares), "pares_que_saldrian_por_azar": round(len(pares) * (1 - CONFIANZA), 1), "grupos_frente_al_total_por_azar": azar_total,
            "primero_en_euros": mejor_euros, "no_se_distinguen_del_primero_en_euros": empatados_euros, "pares_euros": pares_euros}


def pregunta_1(d, reg, planteamiento, rangos):
    """Qué tipo de piso rinde más: por habitaciones y por tipo de inmueble, con la mediana de toda la base como referencia."""
    pobl = "base de decisión"
    vistos = d.assign(grupo_dormitorios=dormitorios_de(d["dormitorios"]))
    resumen, cifras = reg.resumen("rentabilidad de toda la base", d[SUPERFICIE], pobl)
    base_mediana = resumen["mediana"]
    euros, cif_e = reg.resumen("euros al año de toda la base", d["ingreso_anual_eur"], pobl)
    dorm = tabla_de_tipos(vistos, "grupo_dormitorios", reg, "dormitorios", base_mediana)
    inm = tabla_de_tipos(vistos, "tipo_inmueble", reg, "tipo de inmueble", base_mediana)
    cruzada, sin_cruz = reg.tabla("P1 habitaciones y tipo de inmueble", vistos.assign(tipo_piso=vistos["grupo_dormitorios"] + " habitaciones, " + vistos["tipo_inmueble"]), "tipo_piso", SUPERFICIE)
    simpson = eda.rentabilidad_por_dormitorios_y_barrio(d)
    sensibilidad = sensibilidad_superficie(vistos, rangos)
    cifras += cif_e
    con_minimo = sum(f["pisos"] for f in dorm["tabla"])
    return {"id": "P1", "pregunta": "¿Qué tipo de piso rinde más?", "decision": planteamiento["P1"], "planteamiento": "metodo/04_planteamientos.md §Pregunta 1", "funcion": "comparar_con_total", "funcion_adaptada": "la medida es una mediana y no una parte de «sí»: el intervalo sale del remuestreo en lugar de Wilson; la lectura frente al total y el número esperado por azar son los del 42.6",
            "poblacion": {"regla": REGLA_DECISION, "periodo": PERIODO, "filas": len(d), "unidad": "anuncio", "entidades": int(d["id"].nunique())}, "cifras": cifras, "referencia": {"que_es": "mediana de toda la base", "valor": base_mediana, "filas": len(d)},
            "dormitorios": dorm, "tipo_de_inmueble": inm, "sensibilidad_superficie": sensibilidad, "cruce_dormitorios_e_inmueble": cruzada, "cruce_sin_conclusion": sin_cruz, "euros_toda_la_base": euros,
            "por_segmentos": {"distritos_comparables_1_y_2": simpson["distritos_comparables_1_y_2"], "distritos_donde_1_supera_a_2": simpson["distritos_donde_1_supera_a_2"]},
            "comprobaciones": {"unidad": unidad_correcta(d), "minimo": all(f["pisos"] >= MINIMO for f in dorm["tabla"] + inm["tabla"]), "empates": None, "referencia": len(d) == resumen["casos"], "azar_en_grupos": dorm["pares_que_saldrian_por_azar"] is not None, "pesos": None, "hacia_adelante": None, "cobertura": con_minimo + sum(x["casos"] for x in dorm["sin_conclusion"]) == len(d), "periodos": None},
            "cobertura": {"pisos_en_grupos_de_30_o_mas": con_minimo, "pct": 100 * con_minimo / len(d) if len(d) else None}, "sin_conclusion": dorm["sin_conclusion"] + inm["sin_conclusion"],
            "limites": ["empates: no hay tramos ni puestos que repartir, se comparan medianas con intervalo.", "pesos: no hay puntuación con pesos.", "hacia_adelante: la pregunta describe una foto y no predice.", "periodos: la pregunta usa una sola foto; las demás van en la pregunta 3.",
                        f"La ventaja de una habitación sobre dos no se repite en todos los distritos: de {n(simpson['distritos_comparables_1_y_2'])} comparables, gana en {n(simpson['distritos_donde_1_supera_a_2'])}.",
                        "La superficie de valoraciones es un supuesto, y la oficial no sirve para comparar tipos porque es igual para todos los pisos del barrio: va solo como contraste.", "La rentabilidad bruta no incluye gastos, impuestos ni comisiones y no implica beneficio."]}


def fila_de_barrio(b, f, veces, tope, intervalos, pruebas):
    """Monta la fila de un barrio con todo lo que pide la pregunta 2."""
    t = tope.loc[b] if b in tope.index else None
    clase = pruebas["barrios"][b]["clase"] if b in pruebas["barrios"] else "fuera del grupo"
    return {"barrio": b, "clase": clase, "pisos": f["casos"], "rentabilidad_mediana_pct": f["mediana"], "cuartil_bajo_pct": f["q25"], "ic_bajo": intervalos[b]["ic_bajo"], "ic_alto": intervalos[b]["ic_alto"], "frente_a_la_base": intervalos[b]["frente_al_total"], "variantes_en_el_mejor_cuarto": int(veces.get(b, 0)),
            "pisos_en_el_tope": None if t is None else int(t["si"]), "parte_en_el_tope_pct": None if t is None else float(t["pct"]), "tope_frente_a_la_base": None if t is None else str(t["frente_al_total"])}


def texto_de_avisos(f, cuartil_base):
    """Escribe los avisos que lleva un barrio del grupo."""
    a = f["avisos_del_barrio"]
    salida = []
    if a["depende_del_tope"]:
        salida.append(f"depende del tope: sale del grupo sin los pisos en {TOPE} días")
    if a["pocos_anuncios"]:
        salida.append(f"pocos anuncios: {n(f['pisos'])} pisos")
    if a["cuartil_bajo"]:
        salida.append(f"cuartil bajo: {n(f['cuartil_bajo_pct'], 1)} %, que no supera el cuartil bajo de toda la base, {n(cuartil_base, 2)} %")
    return salida


def pregunta_2(a, d, L, quitados, reg, planteamiento, controles, reglas, extra):
    """En qué barrios: firmes, con aviso y segunda línea, cada barrio con sus pruebas, su recuento, su cuartil bajo y sus avisos."""
    pobl = "base de decisión"
    resumen, cifras = reg.resumen("rentabilidad de toda la base, pregunta 2", d[SUPERFICIE], pobl)
    mediana_base, cuartil_base = resumen["mediana"], resumen["q25"]
    pruebas = rc.pruebas_del_grupo(L, quitados, reglas)
    grupo, firmes, con_aviso, segunda = pruebas["grupo"], pruebas["firmes"], pruebas["con_aviso"], pruebas["segunda_linea"]
    veces = cd.grupo_de(L, excluir=quitados)[1]
    for prueba in rc.PRUEBAS:
        a_mano = variantes_a_mano(L, quitados, reglas, prueba)
        de_pandas = pruebas["variantes_por_prueba"][prueba]
        distintas = sum(1 for b in set(a_mano) | set(de_pandas) if a_mano.get(b, 0) != de_pandas.get(b, 0))
        reg.vias.append({"tabla": f"prueba {prueba}", "celdas": len(de_pandas), "diferencia_maxima": distintas, "coinciden": distintas == 0})
    filas, fuera = reg.tabla("P2 barrios", d, "barrio", SUPERFICIE)
    filas_20, _ = por_grupo(d, "barrio", SUPERFICIE, MINIMO_VARIANTE)
    medianas = pd.Series({f["grupo"]: f["mediana"] for f in filas}, dtype="float64")
    ref = float(medianas.median()) if len(medianas) else None
    cifras.append(reg.cifra("mediana de los barrios con 30 o más", ref, mediana(medianas.tolist()) if len(medianas) else None, len(medianas), "barrios con 30 pisos o más de la base de decisión"))
    marcas = mejor_cuarto(medianas) if len(medianas) else pd.Series(dtype="bool")
    tope, azar_tope = comparar_con_total(d.assign(en_tope=d["ocupacion_dias"].eq(TOPE)), "barrio", "en_tope")
    intervalos, azar = comparar_medianas_con_total(d, "barrio", SUPERFICIE, mediana_base)
    tabla = [fila_de_barrio(f["grupo"], f, veces, tope, intervalos, pruebas) for f in filas]
    por_nombre = {f["barrio"]: f for f in tabla}
    para_grupo = [por_nombre[b] for b in grupo if b in por_nombre]

    # Los tres avisos. El del tope repite las 12 variantes sin los pisos en 255 días de toda la base; al lado se deja lo que da quitando solo los del barrio.
    en_tope = L["ocupacion"].eq(TOPE)
    grupo_sin_tope = cd.grupo_de(L, excluir=quitados | en_tope)[0]
    for f in para_grupo:
        b = f["barrio"]
        f.update(pruebas_que_aguanta=pruebas["barrios"][b]["aguanta"], pruebas_que_no_aguanta=pruebas["barrios"][b]["no_aguanta"], avisos_del_barrio=avisos_del_barrio(f["pisos"], f["cuartil_bajo_pct"], cuartil_base, b in grupo_sin_tope, reglas["pocos_anuncios"]),
                 sale_quitando_solo_sus_pisos_en_el_tope=b not in cd.grupo_de(L, excluir=quitados | (en_tope & L["barrio"].eq(b)))[0])
        f["avisos_en_texto"] = texto_de_avisos(f, cuartil_base)

    # Referencia: los barrios de m² más barato, entre los comparados y en toda la ciudad.
    precios_m2 = a.groupby("barrio")["precio_m2_eur"].first()
    baratos = {"comparados": comparar_con_baratos(grupo, precios_m2.loc[precios_m2.index.isin(medianas.index)]), "toda_la_ciudad": comparar_con_baratos(grupo, precios_m2)}
    pisos_firmes = int(d["barrio"].isin(firmes).sum())
    pisos_grupo = int(d["barrio"].isin(grupo).sum())

    # Lo que deja ver si la lista se sostiene: cuántos barrios avisarían, el corte de los anuncios nuevos y quién tiene operadores grandes.
    aviso_del_cuartil = {"barrios_comparados": len(tabla), "no_superan_la_mediana": sum(1 for f in tabla if f["cuartil_bajo_pct"] <= mediana_base), "no_superan_el_cuartil_bajo": sum(1 for f in tabla if lleva_aviso(f["cuartil_bajo_pct"], cuartil_base))}
    con_un_ano = puestos_con_un_ano(d.merge(extra[["id", "first_review"]], on="id", how="left", validate="one_to_one"), SUPERFICIE, rc.FECHA_DATOS)
    anuncios = reglas["anfitrion_anuncios"]
    de_operadores = parte_de_operadores_grandes(d, con_aviso, anuncios)
    pisos_con_aviso = [x for x in zip(d["barrio"].tolist(), d["anuncios_anfitrion"].tolist()) if x[0] in set(con_aviso)]
    cifras.append(reg.cifra("parte de operadores grandes en los barrios con aviso", de_operadores, 100 * sum(1 for x in pisos_con_aviso if x[1] >= anuncios) / len(pisos_con_aviso) if pisos_con_aviso else None, len(pisos_con_aviso), "pisos de los barrios con aviso"))
    operadores = {"anuncios_desde": anuncios, "con_aviso_pct": de_operadores, "por_barrio": {b: parte_de_operadores_grandes(d, [b], anuncios) for b in firmes + con_aviso + segunda}}

    # Qué ordena la lista: entre barrios, con qué se asocia la rentabilidad, y cuánto rinden los barrios de m² más barato frente a la lista.
    nombres_comparados = list(medianas.index)
    ocupacion_barrio = d.groupby("barrio")["ocupacion_dias"].median().reindex(nombres_comparados)
    con_ocupacion = reg.correlacion("P2 rentabilidad y ocupación entre barrios", medianas.to_numpy(), ocupacion_barrio.to_numpy())
    con_m2 = reg.correlacion("P2 rentabilidad y m² entre barrios", medianas.to_numpy(), precios_m2.reindex(nombres_comparados).to_numpy())
    lista_barata = baratos["comparados"]["baratos"]
    conjuntos = {"m2_baratos": lista_barata, "firmes": firmes, "grupo": grupo}
    que_ordena = {"barrios": len(medianas), "rentabilidad_con_ocupacion": con_ocupacion["spearman"], "rentabilidad_con_m2": con_m2["spearman"], **{k: rentabilidad_de_barrios(d, v, k) for k, v in conjuntos.items()}, "pares": []}
    for k, v in conjuntos.items():
        cifras.append(reg.cifra(f"rentabilidad conjunta: {k}", que_ordena[k]["mediana_pct"], mediana(d.loc[d["barrio"].isin(v), SUPERFICIE].tolist()) if que_ordena[k]["pisos"] else None, que_ordena[k]["pisos"], f"pisos de {k}"))
    if que_ordena["m2_baratos"]["pisos"] and pisos_firmes:
        valores_de = {k: d.loc[d["barrio"].isin(v), SUPERFICIE].to_numpy() for k, v in conjuntos.items()}
        que_ordena["pares"] = [diferencia_de_medianas(valores_de[k], valores_de["m2_baratos"], k, "m2_baratos") for k in ("firmes", "grupo")]

    un_barrio_20 = sorted({f["grupo"] for f in filas_20} - {f["grupo"] for f in filas})
    cifras += [reg.cifra("pisos del grupo", pisos_grupo, sum(1 for b in d["barrio"].tolist() if b in set(grupo)), len(d), pobl), reg.cifra("pisos del grupo firme", pisos_firmes, sum(1 for b in d["barrio"].tolist() if b in set(firmes)), len(d), pobl)]
    comprobar_control = {"grupo": {"esperado": controles.get("grupo_esperado"), "obtenido": grupo, "coincide": None if controles.get("grupo_esperado") is None else sorted(controles["grupo_esperado"]) == grupo},
                         "firmes": {"esperado": controles.get("firmes_esperados"), "obtenido": firmes, "coincide": None if controles.get("firmes_esperados") is None else sorted(controles["firmes_esperados"]) == firmes},
                         "con_aviso": {"esperado": controles.get("con_aviso_esperados"), "obtenido": con_aviso, "coincide": None if controles.get("con_aviso_esperados") is None else sorted(controles["con_aviso_esperados"]) == con_aviso}}
    casos_base = sum(f["casos"] for f in filas)
    return {"id": "P2", "pregunta": "¿En qué barrios conviene buscarlo, fuera del centro histórico?", "decision": planteamiento["P2"], "planteamiento": "metodo/04_planteamientos.md §Pregunta 2", "funcion": "comparar_con_total", "funcion_adaptada": "en la parte de pisos en el tope se usa tal cual; en la rentabilidad, adaptada a la mediana con remuestreo",
            "poblacion": {"regla": REGLA_DECISION, "periodo": PERIODO, "filas": len(d), "unidad": "anuncio", "entidades": int(d["id"].nunique())}, "cifras": cifras, "referencia": {"que_es": "mediana de los barrios con 30 anuncios o más", "valor": ref, "filas": casos_base, "barrios": len(medianas)}, "mediana_de_toda_la_base": mediana_base,
            "grupo": grupo, "firmes": firmes, "con_aviso": con_aviso, "segunda_linea": segunda, "clases": {b: x["clase"] for b, x in pruebas["barrios"].items()}, "pruebas": {k: v for k, v in pruebas.items() if k != "grupo"}, "pisos_del_grupo": pisos_grupo, "pisos_del_grupo_firme": pisos_firmes, "fichas_del_grupo": para_grupo,
            "grupo_sin_los_pisos_en_el_tope": grupo_sin_tope, "referencia_baratos": baratos, "cuartil_bajo_de_toda_la_base": cuartil_base, "aviso_del_cuartil": aviso_del_cuartil, "con_un_ano_o_mas": con_un_ano, "operadores_grandes": operadores, "que_ordena_la_lista": que_ordena,
            "tabla_barrios": tabla, "barrios_en_el_mejor_cuarto_de_septiembre": sorted(medianas.index[marcas]) if len(medianas) else [], "variantes_por_barrio": {k: int(v) for k, v in sorted(veces.items())}, "azar_barrios_frente_a_la_base": azar, "azar_tope_frente_a_la_base": azar_tope, "barrios_por_encima_de_la_base": sum(1 for f in tabla if f["frente_a_la_base"] == "por encima"), "barrios_por_debajo_de_la_base": sum(1 for f in tabla if f["frente_a_la_base"] == "por debajo"),
            "tope_por_encima_de_la_base": sum(1 for f in tabla if f["tope_frente_a_la_base"] == "por encima"), "barrios_con_20_a_29_pisos": un_barrio_20, "controles": comprobar_control,
            "comprobaciones": {"unidad": unidad_correcta(d) and set(d["id"]) == set(L.loc[cd.mascara_fija(L, quitados) & L["estancia"].le(3) & L["precio"].between(20, 1000), "id"]), "minimo": all(f["pisos"] >= MINIMO for f in tabla), "empates": empates_bien(medianas, marcas) if len(medianas) else None, "referencia": ref is not None, "azar_en_grupos": azar is not None and azar_tope is not None, "pesos": None, "hacia_adelante": None, "cobertura": casos_base + sum(x["casos"] for x in fuera) == len(d), "periodos": all(L[c].notna().any() for c in ("p_mar", "p_jun", "precio")) or None},
            "cobertura": {"pisos_en_barrios_comparados": casos_base, "pct": 100 * casos_base / len(d) if len(d) else None, "barrios_comparados": len(tabla), "barrios_con_pisos": int(d["barrio"].nunique())}, "sin_conclusion": fuera,
            "limites": ["pesos: el grupo cuenta variantes y no suma componentes con pesos.", "hacia_adelante: la pregunta no predice; las variantes de marzo y junio miden cuánto depende del momento, con la ocupación de septiembre.",
                        "Un barrio que no llega a 30 pisos en ninguna variante solo se mide en las seis de mínimo 20 y no puede llegar a siete.", "El resultado no dice si un piso concreto cumple la norma.", "Competencia cuenta solo anuncios de Airbnb, y un anuncio no es un inmueble."]}


def parte_sin_ocupacion(L, quitados):
    """Cuenta por barrio los pisos sin ocupación que pasan los demás filtros de la base, y su parte."""
    t = L.loc[cd.mascara_fija(L, quitados, cero=True) & L["estancia"].le(3) & L["precio"].between(20, 1000)]
    g = t.assign(sin=t["ocupacion"].eq(0)).groupby("barrio")["sin"].agg(["size", "sum"])
    return {b: {"pisos": int(f["sum"]), "de": int(f["size"]), "pct": 100 * float(f["sum"]) / float(f["size"])} for b, f in g.iterrows()}


def medianas_por_foto(L, quitados):
    """Da la mediana de rentabilidad por barrio en cada foto; una foto sin el mínimo de sus variantes no da cifra."""
    fija = cd.mascara_fija(L, quitados) & L["estancia"].le(3)
    salida = {}
    for foto, col in (("marzo", "p_mar"), ("junio", "p_jun"), ("septiembre", "precio")):
        t = L.loc[fija & L[col].between(20, 1000)]
        r = cd.rentabilidad(t, col)
        g = r.groupby(t["barrio"]).agg(["size", "median"])
        salida[foto] = {"barrios": g.loc[g["size"].ge(MINIMO_VARIANTE), "median"].to_dict(), "pisos": g["size"].to_dict(), "toda_la_base": float(r.median()) if len(r) else None, "pisos_base": len(r)}
    return salida


def rango_entre_fotos(valores):
    """Da la distancia entre la mayor y la menor de las medianas que hay."""
    v = [x for x in valores if x is not None]
    return float(max(v) - min(v)) if len(v) >= 2 else None


def pregunta_3(a, d, L, quitados, reg, planteamiento, q2):
    """Con qué riesgo: recuento, cuartil bajo, rango entre fotos, barrios distinguibles del primero y rango del grupo firme."""
    pobl = "base de decisión"
    resumen, cifras = reg.resumen("rentabilidad de toda la base, pregunta 3", d[SUPERFICIE], pobl)
    fotos = medianas_por_foto(L, quitados)
    nombres_fotos = ("marzo", "junio", "septiembre")
    filas = q2["tabla_barrios"]
    fuera_centro = a.loc[a["tipo_alquiler"].eq("Entire home/apt") & a["lado_centro"].eq("fuera")]
    sin_ocupacion = fuera_centro.assign(sin=fuera_centro["ocupacion_dias"].eq(0)).groupby("barrio")["sin"].agg(["size", "sum"])
    primero = filas[0]["barrio"] if filas else None
    valores = {f["barrio"]: d.loc[d["barrio"].eq(f["barrio"]), SUPERFICIE].to_numpy() for f in filas}
    frente = {f["barrio"]: diferencia_de_medianas(valores[primero], valores[f["barrio"]], primero, f["barrio"]) for f in filas if f["barrio"] != primero}
    tabla = []
    for f in filas:
        b = f["barrio"]
        por_foto = {x: fotos[x]["barrios"].get(b) for x in nombres_fotos}
        tabla.append({"barrio": b, "clase": f["clase"], "pisos": f["pisos"], "cuartil_bajo_pct": f["cuartil_bajo_pct"], "mediana_pct": f["rentabilidad_mediana_pct"], "medianas_por_foto": por_foto, "pisos_por_foto": {x: int(fotos[x]["pisos"].get(b, 0)) for x in nombres_fotos}, "rango_entre_fotos_puntos": rango_entre_fotos(por_foto.values()), "parte_en_el_tope_pct": f["parte_en_el_tope_pct"],
                      "pisos_fuera_sin_ocupacion_pct": 100 * float(sin_ocupacion.loc[b, "sum"]) / float(sin_ocupacion.loc[b, "size"]) if b in sin_ocupacion.index else None, "se_distingue_del_primero": None if b == primero else frente[b]["se_distinguen"], "diferencia_con_el_primero": None if b == primero else frente[b]})
    medidas = list(frente.values())
    no_distintos = sorted(x["b"] for x in medidas if not x["se_distinguen"])
    # La ficha contó los intervalos que se tocan: se deja al lado para explicar la diferencia con el intervalo de la diferencia.
    solape = sum(1 for f in filas if f["barrio"] != primero and f["ic_alto"] >= filas[0]["ic_bajo"])
    distintos = sorted(x["b"] for x in medidas if x["se_distinguen"])
    por_base = {x: fotos[x]["toda_la_base"] for x in nombres_fotos}

    # 3.1 Riesgo de cada barrio del grupo, con los avisos que dejó la pregunta 2 y su parte de pisos sin ocupación.
    por_nombre = {f["barrio"]: f for f in tabla}
    del_grupo = {f["barrio"]: f for f in q2["fichas_del_grupo"]}
    sin_ocupacion_base = parte_sin_ocupacion(L, quitados)
    fichas = []
    for b in q2["firmes"] + q2["con_aviso"] + q2["segunda_linea"]:
        f = por_nombre.get(b)
        if f is None:
            continue
        sin_tope = d.loc[d["barrio"].eq(b) & d["ocupacion_dias"].lt(TOPE), SUPERFICIE]
        g = del_grupo.get(b, {})
        so = sin_ocupacion_base.get(b, {"pisos": 0, "de": 0, "pct": None})
        fichas.append({**{k: f[k] for k in ("barrio", "clase", "pisos", "cuartil_bajo_pct", "rango_entre_fotos_puntos", "parte_en_el_tope_pct", "pisos_fuera_sin_ocupacion_pct", "se_distingue_del_primero")}, "pruebas_que_aguanta": g.get("pruebas_que_aguanta"), "pruebas_que_no_aguanta": g.get("pruebas_que_no_aguanta"), "avisos_del_barrio": g.get("avisos_del_barrio"), "avisos_en_texto": g.get("avisos_en_texto"),
                       "pisos_sin_el_tope": len(sin_tope), "sin_el_tope_no_llega_al_minimo_de_variantes": len(sin_tope) < MINIMO_VARIANTE, "mediana_sin_el_tope_pct": float(sin_tope.median()) if len(sin_tope) else None, "mitad_o_mas_en_el_tope": bool(f["parte_en_el_tope_pct"] is not None and f["parte_en_el_tope_pct"] >= 50),
                       "sale_quitando_solo_sus_pisos_en_el_tope": g.get("sale_quitando_solo_sus_pisos_en_el_tope"), "pisos_sin_ocupacion_misma_base": so["pisos"], "sin_ocupacion_misma_base_pct": so["pct"]})
    firmes_d = d.loc[d["barrio"].isin(q2["firmes"])]
    firmes_L = L.loc[cd.mascara_fija(L, quitados) & L["estancia"].le(3) & L["barrio"].isin(q2["firmes"])]
    rango = rango_de_rentabilidad(firmes_L)
    con_aviso_L = L.loc[cd.mascara_fija(L, quitados) & L["estancia"].le(3) & L["barrio"].isin(q2["firmes"] + q2["con_aviso"])]
    rango_con_aviso = rango_de_rentabilidad(con_aviso_L)
    cifras.append(reg.cifra("rango del grupo firme: mínimo", rango["minimo"], rango_a_mano(firmes_L)[0], len(firmes_L), "pisos del grupo firme con precio en cada foto"))
    cifras.append(reg.cifra("rango del grupo firme: máximo", rango["maximo"], rango_a_mano(firmes_L)[1], len(firmes_L), "pisos del grupo firme con precio en cada foto"))
    cifras.append(reg.cifra("rango de firmes y con aviso: mínimo", rango_con_aviso["minimo"], rango_a_mano(con_aviso_L)[0], len(con_aviso_L), "pisos de firmes y con aviso con precio en cada foto"))
    cifras.append(reg.cifra("rango de firmes y con aviso: máximo", rango_con_aviso["maximo"], rango_a_mano(con_aviso_L)[1], len(con_aviso_L), "pisos de firmes y con aviso con precio en cada foto"))
    por_barrio = {b: rango_de_rentabilidad(L.loc[cd.mascara_fija(L, quitados) & L["estancia"].le(3) & L["barrio"].eq(b)]) for b in q2["firmes"] + q2["con_aviso"]}
    grupo_presente = [b for b in q2["grupo"] if b in valores]
    pares_grupo = [diferencia_de_medianas(valores[x], valores[y], x, y) for x, y in combinations(grupo_presente, 2)]
    medios_firmes, cif_f = reg.resumen("rentabilidad del grupo firme", firmes_d[SUPERFICIE], "pisos del grupo firme")
    cifras += cif_f
    sin_oc = int((fuera_centro["ocupacion_dias"].eq(0)).sum())
    cifras.append(reg.cifra("pisos fuera del centro sin ocupación", sin_oc, sum(1 for x in fuera_centro["ocupacion_dias"].tolist() if x == 0), len(fuera_centro), "pisos fuera del centro"))
    return {"id": "P3", "pregunta": "¿Con qué riesgo?", "decision": planteamiento["P3"], "planteamiento": "metodo/04_planteamientos.md §Pregunta 3", "funcion": "comparar_con_total", "funcion_adaptada": "se compara con el primer barrio y no con el total, con el intervalo de la diferencia de medianas que fija el planteamiento",
            "poblacion": {"regla": REGLA_DECISION, "periodo": "fotos del 24/03, 20/06 y 17/09/2026; la ocupación es la de septiembre", "filas": len(d), "unidad": "anuncio", "entidades": int(d["id"].nunique())}, "cifras": cifras,
            "referencia": {"que_es": "el mismo cálculo para toda la base", "valor": resumen["q25"], "filas": len(d), "pisos": len(d), "cuartil_bajo_pct": resumen["q25"], "medianas_por_foto": por_base, "pisos_por_foto": {x: fotos[x]["pisos_base"] for x in nombres_fotos}, "rango_entre_fotos_puntos": rango_entre_fotos(por_base.values())},
            "primero": primero, "barrios_comparados": len(filas), "no_se_distinguen_del_primero": no_distintos, "se_distinguen_del_primero": distintos, "comparaciones_con_el_primero": len(medidas), "barrios_cuyo_intervalo_toca_el_del_primero": solape, "saldrian_por_azar": round(len(medidas) * (1 - CONFIANZA), 1), "tabla_riesgo": tabla, "fichas_del_grupo": fichas,
            "rango_de_rentabilidad_del_grupo_firme": rango, "rango_de_rentabilidad_de_firmes_y_con_aviso": rango_con_aviso, "rango_por_barrio": por_barrio, "rentabilidad_del_grupo_firme": medios_firmes, "pares_dentro_del_grupo": pares_grupo,
            "pisos_fuera_sin_ocupacion": {"pisos": sin_oc, "de": len(fuera_centro), "pct": 100 * sin_oc / len(fuera_centro) if len(fuera_centro) else None},
            "comprobaciones": {"unidad": unidad_correcta(d), "minimo": all(f["pisos"] >= MINIMO for f in tabla), "empates": None, "referencia": resumen["casos"] == len(d), "azar_en_grupos": (len(medidas) > 0) or None, "pesos": None, "hacia_adelante": None, "cobertura": all(f["rango_entre_fotos_puntos"] is not None for f in fichas), "periodos": all(fotos[x]["pisos_base"] > 0 for x in nombres_fotos) or None},
            "cobertura": {"barrios_con_rango_completo": sum(1 for f in tabla if all(v is not None for v in f["medianas_por_foto"].values())), "barrios_comparados": len(tabla)}, "sin_conclusion": q2["sin_conclusion"],
            "limites": ["empates: no hay tramos que repartir.", "pesos: el riesgo se da con sus medidas sueltas, sin puntuación.", "hacia_adelante: el rango entre fotos describe tres fechas y no predice otras.", "azar_en_grupos: con un solo barrio no hay comparación.",
                        "Marzo y junio solo cubren los anuncios que siguen en septiembre con el mismo número, y cada foto mantiene la ocupación de septiembre.", "Una foto con menos de 20 pisos en un barrio no da cifra, y el rango de ese barrio sale de las que quedan.", "La ocupación es una estimación y el calendario no distingue reservado de bloqueado."]}


def rango_a_mano(t):
    """Rehace el rango de rentabilidad sin pandas, recorriendo los pisos uno a uno."""
    medianas = []
    columnas = [t[c].tolist() for c in ("p_mar", "p_jun", "precio")]
    ocu, sup, m2 = t["ocupacion"].tolist(), t["sup_regla"].tolist(), t["m2"].tolist()
    for precios in columnas:
        for factor in (cd.DESCUENTO, 1.0):
            v = [100 * p * o / (s * m * factor) for p, o, s, m in zip(precios, ocu, sup, m2) if p == p and 20 <= p <= 1000]
            if v:
                medianas.append(mediana(v))
    return (min(medianas), max(medianas)) if medianas else (None, None)


# ---------------------------------------------------------------------------
# 4. Las 16 preguntas
# ---------------------------------------------------------------------------

def preparar_factores(t, extra):
    """Añade rasgos del anuncio para buscar asociaciones, como en el reconocimiento: equipamiento, valoración y anfitrión."""
    x = t.merge(extra, on="id", how="left", validate="one_to_one")
    am = x["amenities"].fillna("").str.lower() if "amenities" in x else pd.Series("", index=x.index)
    con_lista = am.ne("")
    return x.assign(equipamientos=(am.str.count('", "') + 1).where(con_lista), aire=am.str.contains("air conditioning", regex=False), ascensor=am.str.contains("elevator", regex=False), lavadora=am.str.contains('"washer"', regex=False), parking=am.str.contains("free parking", regex=False),
                    superanfitrion=x["host_is_superhost"].eq("t").fillna(False).astype("bool") if "host_is_superhost" in x else False, lleva_registro=x["tipo_licencia"].notna())


def factores(t, medida, reg, etiqueta):
    """Mide cada rasgo con la medida, también dentro del barrio, y cada rasgo de sí o no con el mínimo de 30 a cada lado."""
    filas = []
    centrada = t[medida] - t.groupby("barrio")[medida].transform("median")
    grande = t.groupby("barrio")["id"].transform("size").ge(MINIMO)
    for c in RASGOS:
        if c not in t or t[c].notna().sum() < 3:
            continue
        r = reg.correlacion(f"{etiqueta} con {c}", t[c].astype("float64"), t[medida])
        dentro = reg.correlacion(f"{etiqueta} con {c}, dentro del barrio", t.loc[grande, c].astype("float64"), centrada[grande])
        filas.append({"rasgo": c, "spearman": r["spearman"], "pearson": r["pearson"], "pares": r["pares"], "spearman_dentro_del_barrio": dentro["spearman"], "circular": medida == "ocupacion_dias" and c in CIRCULARES})
    filas.sort(key=lambda f: -abs(f["spearman"] or 0))
    si_no = []
    for c in SI_NO:
        marca = t[c].astype("bool")
        con, sin = t.loc[marca, medida].dropna(), t.loc[~marca, medida].dropna()
        conclusion = min(len(con), len(sin)) >= MINIMO
        si_no.append({"rasgo": c, "con": len(con), "sin": len(sin), "mediana_con": float(con.median()) if len(con) else None, "mediana_sin": float(sin.median()) if len(sin) else None, "diferencia_pct": 100 * (float(con.median()) / float(sin.median()) - 1) if conclusion and sin.median() else None, "con_conclusion": conclusion})
    si_no.sort(key=lambda f: -abs(f["diferencia_pct"] or 0))
    return {"correlaciones": filas, "si_o_no": si_no}


def tramos_de_tamano(t, medida, reg, etiqueta):
    """Da la medida por habitaciones y por huéspedes, y su correlación con los huéspedes."""
    x = t.assign(grupo_dormitorios=dormitorios_de(t["dormitorios"]), grupo_huespedes=pd.cut(t["huespedes"], [0, 2, 4, 6, 8, 100], labels=["1-2", "3-4", "5-6", "7-8", "más de 8"]).astype("object"))
    dorm, fd = reg.tabla(f"{etiqueta} por habitaciones", x, "grupo_dormitorios", medida)
    hues, fh = reg.tabla(f"{etiqueta} por huéspedes", x, "grupo_huespedes", medida)
    return {"por_dormitorios": sorted(dorm, key=lambda f: f["grupo"]), "por_huespedes": sorted(hues, key=lambda f: f["grupo"]), "spearman_huespedes": reg.correlacion(f"{etiqueta} con huéspedes", t["huespedes"].astype("float64"), t[medida]), "spearman_dormitorios": reg.correlacion(f"{etiqueta} con habitaciones", t["dormitorios"].astype("float64"), t[medida]), "sin_conclusion": fd + fh}


def competencia(t, medida, reg, etiqueta):
    """Correlaciona, entre barrios con 30 o más, la mediana de una medida con los anuncios del barrio."""
    g = t.dropna(subset=[medida]).groupby("barrio").agg(casos=("id", "size"), mediana=(medida, "median"), competencia=("competencia_anuncios", "first"))
    g = g.loc[g["casos"].ge(MINIMO)]
    return {"barrios": len(g), **reg.correlacion(f"{etiqueta} con la competencia", g["competencia"].astype("float64"), g["mediana"])}


def dorm_texto(g):
    """Escribe un grupo de habitaciones con su concordancia."""
    return "1 habitación" if g == "1" else f"{g} habitaciones"


def lista_y(v):
    """Une una lista con comas y una «y» final."""
    v = [str(x) for x in v]
    return "ninguno" if not v else v[0] if len(v) == 1 else ", ".join(v[:-1]) + " y " + v[-1]


def texto_comprobaciones(q):
    """Escribe las comprobaciones de una pregunta en una línea; un vacío es que no toca, con su motivo en Límites."""
    return "; ".join(f"{k.replace('_', ' ')}, {'no toca' if v is None else 'pasa' if v else 'falla'}" for k, v in q["comprobaciones"].items())


def extremos(filas, dec=2, unidad=" €"):
    """Escribe el primero y el último de una tabla ordenada, con su cifra."""
    if not filas:
        return "ningún grupo llega a 30"
    return f"de {filas[0]['grupo']} ({n(filas[0]['mediana'], dec)}{unidad}) a {filas[-1]['grupo']} ({n(filas[-1]['mediana'], dec)}{unidad})"


def ranking(filas):
    """Pone el puesto a una tabla ya ordenada: el mismo valor, el mismo puesto."""
    salida, anterior, puesto = [], None, 0
    for i, f in enumerate(filas, 1):
        puesto = puesto if f["mediana"] == anterior else i
        anterior = f["mediana"]
        salida.append({"puesto": puesto, **f})
    return salida


def leer_factor(f, circular=False):
    """Escribe el rasgo que más se asocia, sin contar los circulares."""
    v = [x for x in f["correlaciones"] if not x["circular"] and x["spearman"] is not None]
    if not v:
        return "no hay pares suficientes"
    d = [x for x in v if x["spearman_dentro_del_barrio"] is not None]
    texto = f"se asocia sobre todo con {NOMBRE_RASGO.get(v[0]['rasgo'], v[0]['rasgo'])} ({n(v[0]['spearman'], 2)} en correlación por rangos)"
    return texto + (f"; dentro del barrio esa cifra es {n(d[0]['spearman_dentro_del_barrio'], 2)}" if d and d[0]["rasgo"] == v[0]["rasgo"] else "")


def oficial_por_distrito(o, t, reg, clave):
    """Da el m² y el inmueble oficial de cada distrito, con lo que la base aporta a cada uno."""
    d = o.loc[o["nivel"].eq("distrito")].copy()
    d["clave_nombre"] = d["nombre"].map(cd.sin_guiones)
    d["inmueble_oficial_eur"] = d["m2_total"] * d["sup_total"]
    g = t.assign(clave_nombre=t["distrito"].map(cd.sin_guiones)).groupby("clave_nombre").agg(casos=("id", "size"), compra_valoraciones_sin=("compra_valoraciones_sin_eur", "median"), compra_oficial_sin=("compra_oficial_sin_eur", "median"), ocupacion=("ocupacion_dias", "median"))
    d = d.merge(g, on="clave_nombre", how="left", validate="one_to_one")
    d["casos"] = d["casos"].fillna(0).astype("int64")
    d["puesto_m2"] = d["m2_total"].rank(method="min", ascending=False).astype("int64")
    d["puesto_inmueble"] = d["inmueble_oficial_eur"].rank(method="min", ascending=False).astype("int64")
    # Segunda vía: el producto y el puesto se rehacen recorriendo la tabla.
    m2, sup = d["m2_total"].tolist(), d["sup_total"].tolist()
    valor = [a * b for a, b in zip(m2, sup)]
    maxima = max([abs(a - b) for a, b in zip(valor, d["inmueble_oficial_eur"].tolist())] + [abs((1 + sum(1 for x in valor if x > v)) - p) for v, p in zip(valor, d["puesto_inmueble"].tolist())], default=0.0)
    reg.vias.append({"tabla": f"oficial por distrito, {clave}", "celdas": 2 * len(d), "diferencia_maxima": maxima, "coinciden": maxima < TOLERANCIA})
    return d


def responder_16(t, col, clave, reg, oficial):
    """Contesta las 16 preguntas en una base y deja texto, población y filas."""
    nombre = {"base_decision": "base de decisión", "base_comparacion": "base de comparación"}[clave]
    regla = REGLA_DECISION if clave == "base_decision" else REGLA_COMPARACION
    medida_precio = "precio por noche" if clave == "base_decision" else "precio de vivienda de las reglas §3"
    x = t.dropna(subset=[col])
    pisos = x if clave == "base_decision" else x.loc[x["tipo_alquiler"].eq("Entire home/apt")]
    r = {}

    def anota(i, respuesta, datos, filas=None, poblacion=None):
        """Guarda la respuesta de una pregunta con su población y sus filas."""
        r[i] = {"respuesta": respuesta, "poblacion": poblacion or f"{regla}", "periodo": PERIODO, "filas": len(t) if filas is None else filas, "datos": datos}

    # 4.1 Precio
    g, cif = reg.resumen(f"{clave} precio", x[col], nombre)
    pd_, fd = reg.tabla(f"{clave} precio por distrito", x, "distrito", col)
    pb, fb = reg.tabla(f"{clave} precio por barrio", x, "barrio", col)
    publicado = {"mediana": float(t["precio_eur"].median()) if len(t) else None, "media": float(t["precio_eur"].mean()) if len(t) else None} if clave == "base_comparacion" else None
    anota("S01", f"Con {n(g['casos'])} anuncios, el {medida_precio} tiene media de {n(g['media'], 2)} € y mediana de {n(g['mediana'], 2)} €, con rango de {n(g['minimo'], 2)} a {n(g['maximo'], 2)} €.", {"global": g, "cifras": cif, "por_distrito": pd_, "por_barrio": pb, "sin_conclusion_distrito": fd, "sin_conclusion_barrio": fb, "precio_publicado": publicado}, g["casos"])
    anota("S02", f"Entre {n(len(pd_))} distritos con 30 o más, {extremos(pd_)}. Entre {n(len(pb))} barrios, {extremos(pb)}. El orden no dice qué barrios se distinguen.", {"distritos": ranking(pd_), "barrios": ranking(pb)}, g["casos"])
    f = factores(pisos, col, reg, f"{clave} precio")
    anota("S03", f"Son asociaciones, sobre {n(len(pisos))} pisos: el precio {leer_factor(f)}.", f, len(pisos), f"pisos de la {nombre}")
    tam = tramos_de_tamano(pisos, col, reg, f"{clave} precio")
    orden = " · ".join(f"{dorm_texto(a['grupo'])}: {n(a['mediana'], 2)} € ({n(a['casos'])})" for a in tam["por_dormitorios"])
    anota("S04", f"Precio mediano por tamaño, sobre {n(len(pisos))} pisos. {orden}. Correlación por rangos con los huéspedes: {n(tam['spearman_huespedes']['spearman'], 2)}.", tam, len(pisos), f"pisos de la {nombre}")
    co = competencia(x, col, reg, f"{clave} precio")
    anota("S05", f"Es una asociación entre {n(co['barrios'])} barrios con 30 anuncios o más: la correlación por rangos entre su precio mediano y sus anuncios en Airbnb es {n(co['spearman'], 2)}.", co, g["casos"])
    ta, fa = reg.tabla(f"{clave} precio por tipo de alquiler", x, "tipo_alquiler", col)
    ti, fi = reg.tabla(f"{clave} precio por tipo de inmueble", x, "tipo_inmueble", col)
    tipos = " · ".join(f"{a['grupo']}: {n(a['mediana'], 2)} € ({n(a['casos'])})" for a in ta) or "ningún tipo llega a 30"
    anota("S06", f"Por tipo de alquiler: {tipos}." + (" La base solo tiene pisos." if clave == "base_decision" else " Las habitaciones van con el precio llevado a la vivienda por las reglas §3.") + f" Entre {n(len(ti))} tipos de inmueble con 30 o más, {extremos(ti)}.", {"por_tipo_de_alquiler": ta, "por_tipo_de_inmueble": ti, "sin_conclusion": fa + fi}, g["casos"])

    # 4.2 Ocupación
    o, cif_o = reg.resumen(f"{clave} ocupación", t["ocupacion_dias"], nombre)
    od, fod = reg.tabla(f"{clave} ocupación por distrito", t, "distrito", "ocupacion_dias")
    ob, fob = reg.tabla(f"{clave} ocupación por barrio", t, "barrio", "ocupacion_dias")
    anota("S07", f"Con {n(o['casos'])} anuncios, la ocupación estimada tiene media de {n(o['media'], 1)} días y mediana de {n(o['mediana'])}. Por distrito, {extremos(od, 1, ' días')}. Por barrio, {extremos(ob, 1, ' días')}.", {"global": o, "cifras": cif_o, "por_distrito": od, "por_barrio": ob, "sin_conclusion_distrito": fod, "sin_conclusion_barrio": fob})
    niveles = t.assign(nivel=nivel_ocupacion(t["ocupacion_dias"]))
    filas_n = []
    for d_, h in niveles.groupby("distrito"):
        if len(h) >= MINIMO:
            c = h["nivel"].value_counts()
            a_mano = Counter(h["nivel"].tolist())
            filas_n.append({"distrito": str(d_), "anuncios": len(h), **{k: 100 * int(c.get(k, 0)) / len(h) for k in ("1-85", "86-170", "171-254", "255")}})
            reg.vias.append({"tabla": f"{clave} niveles de {d_}", "celdas": 4, "diferencia_maxima": max(abs(int(c.get(k, 0)) - a_mano.get(k, 0)) for k in ("1-85", "86-170", "171-254", "255")), "coinciden": all(int(c.get(k, 0)) == a_mano.get(k, 0) for k in ("1-85", "86-170", "171-254", "255"))})
    filas_n.sort(key=lambda a: (-a["255"], a["distrito"]))
    total_n = {k: 100 * float(niveles["nivel"].eq(k).mean()) if len(t) else None for k in ("1-85", "86-170", "171-254", "255")}
    txt = f"Parte de anuncios en cada nivel, en toda la base: 1-85 días, {n(total_n['1-85'], 1)} %; 86-170, {n(total_n['86-170'], 1)} %; 171-254, {n(total_n['171-254'], 1)} %; tope de 255, {n(total_n['255'], 1)} %."
    if filas_n:
        txt += f" El tope va del {n(filas_n[0]['255'], 1)} % de {filas_n[0]['distrito']} al {n(filas_n[-1]['255'], 1)} % de {filas_n[-1]['distrito']}."
    anota("S08", txt, {"toda_la_base": total_n, "por_distrito": filas_n, "niveles": "1-85, 86-170, 171-254 y 255 días, de 04_planteamientos.md"})
    anota("S09", f"Por distrito, {extremos(od, 1, ' días')}. Por barrio, {extremos(ob, 1, ' días')}. En la parte alta el orden no dice nada, por el tope.", {"distritos": ranking(od), "barrios": ranking(ob)})
    fo = factores(pisos, "ocupacion_dias", reg, f"{clave} ocupación")
    anota("S10", f"Son asociaciones, sobre {n(len(pisos))} pisos. Sin contar las reseñas y los días libres, que son circulares, la ocupación {leer_factor(fo)}.", fo, len(pisos), f"pisos de la {nombre}")
    tamo = tramos_de_tamano(pisos, "ocupacion_dias", reg, f"{clave} ocupación")
    orden = " · ".join(f"{dorm_texto(a['grupo'])}: {n(a['mediana'], 1)} días ({n(a['casos'])})" for a in tamo["por_dormitorios"])
    anota("S11", f"{orden}. Correlación por rangos con los huéspedes: {n(tamo['spearman_huespedes']['spearman'], 2)}.", tamo, len(pisos), f"pisos de la {nombre}")
    coo = competencia(t, "ocupacion_dias", reg, f"{clave} ocupación")
    anota("S12", f"Es una asociación entre {n(coo['barrios'])} barrios con 30 anuncios o más: la correlación por rangos entre su ocupación mediana y sus anuncios en Airbnb es {n(coo['spearman'], 2)}.", coo)

    # 4.3 Precio de compra
    d = oficial_por_distrito(oficial, t, reg, clave).sort_values(["puesto_m2", "nombre"])
    fila = lambda z: {"distrito": z["nombre"], "m2_eur": float(z["m2_total"]), "superficie_oficial_m2": float(z["sup_total"]), "inmueble_oficial_eur": float(z["inmueble_oficial_eur"]), "puesto_m2": int(z["puesto_m2"]), "puesto_inmueble": int(z["puesto_inmueble"]), "anuncios_de_la_base": int(z["casos"]),
                      "compra_mediana_valoraciones_sin_descuento_eur": None if pd.isna(z["compra_valoraciones_sin"]) else float(z["compra_valoraciones_sin"]), "compra_mediana_oficial_sin_descuento_eur": None if pd.isna(z["compra_oficial_sin"]) else float(z["compra_oficial_sin"])}
    filas_d = [fila(z) for _, z in d.iterrows()]
    if filas_d:
        anota("S13", f"El m² oficial de 2025 va de {n(filas_d[0]['m2_eur'])} € en {filas_d[0]['distrito']} a {n(filas_d[-1]['m2_eur'])} € en {filas_d[-1]['distrito']}, en {n(len(filas_d))} distritos. El dato es de la ciudad y es el mismo en las dos bases; cambia cuántos anuncios aporta cada distrito.", {"distritos": filas_d}, len(filas_d), "distritos del libro oficial de 2025")
        por_i = sorted(filas_d, key=lambda z: z["puesto_inmueble"])
        anota("S14", f"El inmueble oficial, m² por superficie media, va de {n(por_i[0]['inmueble_oficial_eur'])} € en {por_i[0]['distrito']} a {n(por_i[-1]['inmueble_oficial_eur'])} € en {por_i[-1]['distrito']}.", {"distritos": por_i}, len(filas_d), "distritos del libro oficial de 2025")
    else:
        anota("S13", "El libro oficial no trae distritos.", {"distritos": []}, 0)
        anota("S14", "El libro oficial no trae distritos.", {"distritos": []}, 0)
    h = t.assign(clave_nombre=t["distrito"].map(cd.sin_guiones)).groupby("clave_nombre").agg(casos=("id", "size"), alquiler=(col, "median"), ocupacion=("ocupacion_dias", "median")).reset_index()
    u = h.merge(d[["clave_nombre", "m2_total", "inmueble_oficial_eur"]], on="clave_nombre", how="left", validate="one_to_one")
    u = u.loc[u["casos"].ge(MINIMO)]
    rm, ri = reg.correlacion(f"{clave} m² con alquiler", u["m2_total"], u["alquiler"]), reg.correlacion(f"{clave} inmueble con alquiler", u["inmueble_oficial_eur"], u["alquiler"])
    om, oi = reg.correlacion(f"{clave} m² con ocupación", u["m2_total"], u["ocupacion"]), reg.correlacion(f"{clave} inmueble con ocupación", u["inmueble_oficial_eur"], u["ocupacion"])
    anota("S15", f"Es una asociación entre {n(len(u))} distritos con 30 anuncios o más: el m² y el alquiler mediano dan {n(rm['spearman'], 2)} en correlación por rangos, y el inmueble oficial, {n(ri['spearman'], 2)}.", {"distritos": len(u), "m2": rm, "inmueble": ri}, int(u["casos"].sum()))
    anota("S16", f"Es una asociación entre {n(len(u))} distritos con 30 anuncios o más: el m² y la ocupación mediana dan {n(om['spearman'], 2)} en correlación por rangos, y el inmueble oficial, {n(oi['spearman'], 2)}.", {"distritos": len(u), "m2": om, "inmueble": oi}, int(u["casos"].sum()))
    return r


def las_16(d, c, extra, oficial, reg):
    """Contesta una a una las 16 preguntas en las dos bases y conserva su texto."""
    a = responder_16(preparar_factores(d, extra), "precio_eur", "base_decision", reg, oficial)
    b = responder_16(preparar_factores(c, extra), "precio_vivienda_comparacion_eur", "base_comparacion", reg, oficial)
    return [{**q, "origen_del_texto": ORIGEN_DEL_TEXTO, "base_decision": a[q["id"]], "base_comparacion": b[q["id"]]} for q in LAS_16]


# ---------------------------------------------------------------------------
# 5. Lo descriptivo: oferta, reseñas, disponibilidad, atractivo y licencias
# ---------------------------------------------------------------------------

def evolucion_de_la_oferta(e, q2, reg):
    """Describe la oferta en cada foto, sin buscar causa: un anuncio es un nivel y no se suma entre fotos."""
    g = e.groupby("foto").agg(anuncios=("anuncios", "sum"), pisos_completos=("pisos_completos", "sum")).reset_index().sort_values("foto")
    a_mano = defaultdict(int)
    for f, x in zip(e["foto"].tolist(), e["anuncios"].tolist()):
        a_mano[f] += x
    reg.vias.append({"tabla": "oferta por foto", "celdas": len(g), "diferencia_maxima": max([abs(a_mano[f] - x) for f, x in zip(g["foto"].tolist(), g["anuncios"].tolist())], default=0), "coinciden": all(a_mano[f] == x for f, x in zip(g["foto"].tolist(), g["anuncios"].tolist()))})
    fotos = [{"foto": f["foto"].strftime("%Y-%m-%d"), "anuncios": int(f["anuncios"]), "pisos_completos": int(f["pisos_completos"])} for _, f in g.iterrows()]
    for i in range(1, len(fotos)):
        fotos[i]["cambio_anuncios_pct"] = 100 * (fotos[i]["anuncios"] / fotos[i - 1]["anuncios"] - 1) if fotos[i - 1]["anuncios"] else None
    grupo = e.loc[e["barrio"].isin(q2["grupo"])].pivot_table(index="barrio", columns="foto", values="anuncios", aggfunc="sum")
    junio = None
    if DATOS_NECESARIOS.exists():
        m = re.search(r"junio de 2025,\s*([\d.]+)\s*anuncios", DATOS_NECESARIOS.read_text(encoding="utf-8"))
        junio = {"anuncios": int(m.group(1).replace(".", "")), "origen": "02_datos_necesarios.md: recuento anotado cuando esa foto se podía consultar, que ya no se puede descargar"} if m else None
    return {"poblacion": "todos los anuncios de cada foto de Madrid", "fotos": fotos, "junio_2025": junio, "grupo_por_foto": [{"barrio": b, **{c.strftime("%Y-%m-%d"): int(v) for c, v in f.items()}} for b, f in grupo.iterrows()], "limites": "Una foto no se compara con otra sin decirlo: es la misma ciudad en otra fecha, y un cambio entre fotos no dice por qué ocurre."}


def estacionalidad(r, reg):
    """Describe el reparto de reseñas por mes natural con los dos últimos años completos, sin el mes incompleto."""
    completos = r.loc[~r["mes_incompleto"]].sort_values("mes")
    ventana = completos.tail(24).assign(mes_natural=lambda x: x["mes"].dt.month)
    medio = ventana.groupby("mes_natural")["resenas"].mean()
    indice = medio / medio.mean() if len(medio) else medio
    listas = defaultdict(list)
    for m, v in zip(ventana["mes_natural"].tolist(), ventana["resenas"].tolist()):
        listas[m].append(v)
    medias = {m: math.fsum(v) / len(v) for m, v in listas.items()}
    global_ = math.fsum(medias.values()) / len(medias) if medias else None
    maxima = max([abs(indice[m] - medias[m] / global_) for m in medias], default=0.0)
    reg.vias.append({"tabla": "índice de reseñas por mes", "celdas": len(medias), "diferencia_maxima": float(maxima), "coinciden": bool(maxima < TOLERANCIA)})
    anual = completos.assign(ano=completos["mes"].dt.year).groupby("ano").agg(resenas=("resenas", "sum"), meses=("resenas", "size"))
    return {"poblacion": "reseñas de los anuncios de la foto de septiembre", "ventana": None if ventana.empty else [ventana["mes"].min().strftime("%Y-%m"), ventana["mes"].max().strftime("%Y-%m")], "resenas_de_la_ventana": int(ventana["resenas"].sum()), "meses": len(ventana), "indice_por_mes": [{"mes": int(k), "indice": float(v)} for k, v in indice.items()],
            "mes_mas_alto": None if indice.empty else int(indice.idxmax()), "indice_mas_alto": None if indice.empty else float(indice.max()), "mes_mas_bajo": None if indice.empty else int(indice.idxmin()), "indice_mas_bajo": None if indice.empty else float(indice.min()), "por_ano_completo": [{"ano": int(k), "resenas": int(f["resenas"])} for k, f in anual.iterrows() if f["meses"] == 12],
            "mes_incompleto_fuera": r.loc[r["mes_incompleto"], "mes"].dt.strftime("%Y-%m").tolist(), "limites": "Una reseña es una estancia con opinión, no todas dejan reseña, y su fecha no es la de la estancia. Solo llegan las reseñas de anuncios que siguen publicados."}


def disponibilidad_futura(dispo, a, q2, reg):
    """Describe la parte de días libres por mes completo, sin decir por qué: el calendario no distingue reservado de bloqueado."""
    x = dispo.loc[dispo["mes_completo"]]
    grupos = {"toda_la_foto": x, "base_de_decision": x.loc[x["id"].isin(a.loc[a["base_decision"], "id"])], "grupo_firme": x.loc[x["id"].isin(a.loc[a["barrio"].isin(q2["firmes"]) & a["base_decision"], "id"])]}
    salida = {}
    for clave, t in grupos.items():
        g = t.groupby("mes")[["dias_libres", "dias_calendario"]].sum()
        libres, dias = defaultdict(int), defaultdict(int)
        for m, u, v in zip(t["mes"].tolist(), t["dias_libres"].tolist(), t["dias_calendario"].tolist()):
            libres[m] += u
            dias[m] += v
        filas = [{"mes": k.strftime("%Y-%m"), "parte_libre_pct": 100 * float(f["dias_libres"]) / float(f["dias_calendario"]), "anuncios": int(t["id"].loc[t["mes"].eq(k)].nunique())} for k, f in g.iterrows()]
        maxima = max([abs(100 * libres[k] / dias[k] - f["parte_libre_pct"]) for k, f in zip(g.index, filas)], default=0.0)
        reg.vias.append({"tabla": f"disponibilidad, {clave}", "celdas": len(filas), "diferencia_maxima": maxima, "coinciden": maxima < TOLERANCIA})
        salida[clave] = filas
    return {"poblacion": "meses enteros del calendario; el primero y el último no están completos", "series": salida, "limites": "El calendario no distingue reservado de bloqueado, así que un día no libre no es una reserva."}


def atractivo_y_competencia(a, d, q2, reg):
    """Mide atractivo y competencia como asociación, en la base y dentro del grupo; ninguna cifra entra en la rentabilidad."""
    base_at = reg.correlacion("atractivo con rentabilidad", d["puntos_interes_500m"].astype("float64"), d[SUPERFICIE])
    base_co = competencia(d, SUPERFICIE, reg, "rentabilidad")
    medida = d.assign(atractivo=d["puntos_interes_500m"]).groupby("barrio").agg(casos=("id", "size"), atractivo=("atractivo", "median"), rentabilidad=(SUPERFICIE, "median"), competencia=("competencia_anuncios", "first")).reset_index()
    medida = medida.loc[medida["casos"].ge(MINIMO)]
    barrios_at = reg.correlacion("atractivo mediano con rentabilidad, entre barrios", medida["atractivo"].astype("float64"), medida["rentabilidad"])
    g = d.loc[d["barrio"].isin(q2["grupo"])]
    dentro = {"pisos": len(g), "barrios": int(g["barrio"].nunique())}
    if len(g) >= 2 * MINIMO:
        corte = float(g["puntos_interes_500m"].median())
        mas, menos = g.loc[g["puntos_interes_500m"].gt(corte), SUPERFICIE].to_numpy(), g.loc[g["puntos_interes_500m"].le(corte), SUPERFICIE].to_numpy()
        centrada = g[SUPERFICIE] - g.groupby("barrio")[SUPERFICIE].transform("median")
        dentro.update(corte_puntos=corte, pisos_con_mas_puntos=len(mas), pisos_con_menos_puntos=len(menos), con_mas_puntos=float(np.median(mas)) if len(mas) else None, con_menos_puntos=float(np.median(menos)) if len(menos) else None, diferencia=diferencia_de_medianas(mas, menos, "con más puntos", "con menos puntos") if min(len(mas), len(menos)) >= MINIMO else None,
                      spearman_dentro_del_barrio=reg.correlacion("atractivo dentro del grupo", g["puntos_interes_500m"].astype("float64"), centrada))
    fichas = [{"barrio": f["barrio"], "clase": q2["clases"][f["barrio"]], "pisos": int(f["casos"]), "puntos_medianos_500m": float(f["atractivo"]), "competencia_anuncios": int(f["competencia"])} for _, f in medida.iterrows() if f["barrio"] in q2["grupo"]]
    if dentro.get("diferencia"):
        cambia = "dentro del grupo, los pisos con más puntos se distinguen de los demás" if dentro["diferencia"]["se_distinguen"] else "dentro del grupo, los pisos con más puntos no se distinguen de los demás"
    else:
        cambia = "no hay pisos suficientes para comparar dentro del grupo"
    return {"base": {"atractivo_con_rentabilidad": base_at, "competencia_con_rentabilidad_entre_barrios": base_co, "atractivo_con_rentabilidad_entre_barrios": barrios_at}, "dentro_del_grupo": dentro, "fichas_del_grupo": fichas, "lectura": cambia, "limites": "Son asociaciones. Competencia cuenta solo anuncios de Airbnb, y el atractivo es un recuento sin pesos de puntos a menos de 500 m, un supuesto. Con tan pocos barrios, las cifras por barrio del grupo no sacan conclusión."}


def licencias_y_registro(a, b, q2, reg, lic):
    """Describe las licencias por barrio y los tipos de registro de cada base: solo el tipo, sin leer sus letras."""
    # Cuántas licencias nombran la planta baja: de la columna de planta solo se usa eso, porque es texto libre.
    baja = incluye_planta_baja(lic["planta"])
    en_firmes = lic["barrio"].isin(q2["firmes"])
    planta_baja = {"licencias": int(baja.sum()), "de": len(lic), "firmes": {"licencias": int((baja & en_firmes).sum()), "de": int(en_firmes.sum())}}
    a_mano = sum(1 for x in lic["planta"].tolist() if isinstance(x, str) and "BAJA" in x)
    reg.vias.append({"tabla": "licencias con planta baja", "celdas": 1, "diferencia_maxima": abs(planta_baja["licencias"] - a_mano), "coinciden": planta_baja["licencias"] == a_mano})
    grupo = b.loc[b["barrio"].isin(q2["grupo"])].sort_values("barrio")
    fichas = [{"barrio": f["barrio"], "clase": q2["clases"][f["barrio"]], "anuncios": int(f["anuncios"]), "pisos_completos": int(f["pisos_completos"]), "licencias": int(f["licencias"]), "viviendas_con_licencia": int(f["viviendas_licencia"])} for _, f in grupo.iterrows()]
    totales = {"barrios": len(b), "licencias": int(b["licencias"].sum()), "viviendas_con_licencia": int(b["viviendas_licencia"].sum()), "barrios_sin_licencias": int(b["licencias"].eq(0).sum()), "anuncios": int(b["anuncios"].sum())}
    reg.vias.append({"tabla": "licencias totales", "celdas": 2, "diferencia_maxima": abs(totales["licencias"] - sum(b["licencias"].tolist())), "coinciden": totales["licencias"] == sum(b["licencias"].tolist())})
    totales["anuncios_por_vivienda_con_licencia"] = totales["anuncios"] / totales["viviendas_con_licencia"] if totales["viviendas_con_licencia"] else None
    registro = {}
    for clave, m in (("base_decision", a["base_decision"]), ("base_comparacion", a["base_comparacion"])):
        t = a.loc[m]
        tipos = t["tipo_licencia"].fillna("sin registro").value_counts()
        exencion = t["exencion_licencia"].fillna("sin exención").value_counts()
        c = Counter("sin registro" if x is None or x != x else x for x in t["tipo_licencia"].tolist())
        reg.vias.append({"tabla": f"registro, {clave}", "celdas": len(tipos), "diferencia_maxima": max([abs(int(v) - c[k]) for k, v in tipos.items()], default=0), "coinciden": all(int(v) == c[k] for k, v in tipos.items())})
        registro[clave] = {"filas": len(t), "tipo": [{"tipo": str(k), "anuncios": int(v), "pct": 100 * int(v) / len(t)} for k, v in tipos.items()], "exencion": [{"tipo": str(k), "anuncios": int(v), "pct": 100 * int(v) / len(t)} for k, v in exencion.items()], "declaran_temporada": int(t["declara_temporada"].sum())}
    return {"totales": totales, "planta_baja": planta_baja, "fichas_del_grupo": fichas, "registro": registro, "limites": "Una licencia no se une a un anuncio: solo se cuenta por barrio. Leer TU como turístico y NT como no turístico es una interpretación, porque el decreto no define esas letras, y el registro estatal fue anulado por el Tribunal Supremo en mayo de 2026."}


# ---------------------------------------------------------------------------
# 6. El cálculo completo
# ---------------------------------------------------------------------------

def calcular(entrada, planteamiento, dec):
    """Hace todo el cálculo; se ejecuta dos veces para comprobar que da lo mismo."""
    a, b, oferta, res, dispo, oficial, extra, lic = entrada
    reg = Registro()
    L = vista(a)
    quitados = a["excl_cero_banos"] | a["excl_no_vivienda"] | a["excl_tamano_incoherente"]
    d, c = a.loc[a["base_decision"]].copy(), a.loc[a["base_comparacion"]].copy()
    p1 = pregunta_1(d, reg, planteamiento, dec["sensibilidad_superficie"])
    p2 = pregunta_2(a, d, L, quitados, reg, planteamiento, dec["controles"], dec["pruebas_del_grupo"], extra)
    p3 = pregunta_3(a, d, L, quitados, reg, planteamiento, p2)

    # La cifra de la recomendación: los pisos de hasta 2 dormitorios de los barrios firmes, rehecha sin pandas.
    recomendados = d.loc[d["barrio"].isin(p2["firmes"]) & d["dormitorios"].le(2)]
    recomendacion = {"dormitorios_hasta": 2, **cifras_de_la_recomendacion(recomendados), "precio_de_mercado": precio_de_mercado(recomendados)}
    for clave, columna in (("rentabilidad_sin_descuento_pct", "rent_valoraciones_sin_pct"), ("rentabilidad_con_descuento_pct", "rent_valoraciones_desc_pct"), ("compra_sin_descuento_eur", "compra_valoraciones_sin_eur"), ("compra_con_descuento_eur", "compra_valoraciones_desc_eur"), ("ingreso_anual_eur", "ingreso_anual_eur")):
        p3["cifras"].append(reg.cifra(f"recomendación: {clave}", recomendacion[clave], mediana(recomendados[columna].tolist()) if len(recomendados) else None, len(recomendados), "pisos de hasta 2 habitaciones del grupo firme"))
    r = {"preguntas": [p1, p2, p3], "recomendacion": recomendacion, "las_16": las_16(d, c, extra, oficial, reg), "evolucion_oferta": evolucion_de_la_oferta(oferta, p2, reg), "estacionalidad": estacionalidad(res, reg), "disponibilidad": disponibilidad_futura(dispo, a, p2, reg),
         "atractivo_y_competencia": atractivo_y_competencia(a, d, p2, reg), "licencias_y_registro": licencias_y_registro(a, b, p2, reg, lic), "controles": p2["controles"]}
    ingreso = math.fsum(d["ingreso_anual_eur"].tolist())
    r["cifras_de_control"] = {"pisos_base_decision": len(d), "ingreso_base_decision_eur": round(float(d["ingreso_anual_eur"].sum()), 2), "ingreso_segunda_via_eur": round(ingreso, 2), "barrios_con_30_o_mas": p2["cobertura"]["barrios_comparados"], "anuncios_base_comparacion": len(c)}
    r["segunda_via"] = reg.vias
    return r


def redondear(x):
    """Quita el ruido de la última cifra: dos ejecuciones se comparan y se guardan con seis decimales."""
    if isinstance(x, dict):
        return {k: redondear(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [redondear(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return round(float(x), 6)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    return x


# ---------------------------------------------------------------------------
# 7. Validaciones
# ---------------------------------------------------------------------------

def recorrer_cifras(r):
    """Devuelve las cifras sueltas de las preguntas y de las 16."""
    salida = [c for q in r["preguntas"] for c in q["cifras"]]
    for q in r["las_16"]:
        for clave in ("base_decision", "base_comparacion"):
            salida += q[clave]["datos"].get("cifras", [])
    return salida


def validaciones(r, repetido, huellas_iguales, codigo, faltas):
    """Calcula las nueve validaciones: ninguna lleva un sí escrito."""
    cifras = recorrer_cifras(r)
    grupos = [f["pisos"] for q in r["preguntas"] for f in q.get("tabla_barrios", []) + q.get("tabla_riesgo", [])] + [f["pisos"] for f in r["preguntas"][0]["dormitorios"]["tabla"] + r["preguntas"][0]["tipo_de_inmueble"]["tabla"]]
    resultados = r["preguntas"][1]["grupo"] + r["preguntas"][1]["firmes"] + [x for x in (str(r["cifras_de_control"]["pisos_base_decision"]), str(r["cifras_de_control"]["ingreso_base_decision_eur"])) if len(x) >= 4]
    comprobaciones_ok = all(v is not None or any(k in x for x in q["limites"]) for q in r["preguntas"] for k, v in q["comprobaciones"].items())
    return {"planteamiento_completo": not faltas, "cifras_con_poblacion": all(c["poblacion"] and c["periodo"] and c["filas"] is not None for c in cifras) and all(x[k]["poblacion"] and x[k]["periodo"] and x[k]["filas"] is not None for x in r["las_16"] for k in ("base_decision", "base_comparacion")),
            "segunda_via": all(v["coinciden"] for v in r["segunda_via"]) and all(c["coinciden"] for c in cifras) and r["cifras_de_control"]["ingreso_base_decision_eur"] == r["cifras_de_control"]["ingreso_segunda_via_eur"], "minimo_respetado": all(g >= MINIMO for g in grupos),
            "con_referencia": all(q["referencia"]["que_es"] and q["referencia"]["filas"] is not None for q in r["preguntas"]), "comprobaciones_calculadas": comprobaciones_ok and all(v is not False for q in r["preguntas"] for v in q["comprobaciones"].values()), "reproducible": repetido, "sin_resultados_escritos": escritos_a_mano(codigo, resultados) == [], "raw_intacto": huellas_iguales}


# ---------------------------------------------------------------------------
# 8. Informe y borrador
# ---------------------------------------------------------------------------

def texto_sensibilidad(s):
    """Escribe en una frase qué pasa con los tipos al mover la superficie."""
    uno = f"Con la superficie de la regla se dan los de {lista_y(s['se_dan_con_la_regla'])} habitaciones. Al mover la superficie del estudio, de 1 y de 2 habitaciones entre sus extremos, "
    if not s["cambia"]:
        return uno + f"los tipos que se dan no cambian en ninguna de las {n(len(s['combinaciones']))} combinaciones."
    otros = "; ".join(lista_y("estudio" if x == "0" else x for x in t) for t in s["tipos_que_aparecen"])
    return uno + f"cambian en {n(s['combinaciones_que_cambian'])} de las {n(len(s['combinaciones']))} combinaciones. Según la combinación se dan: {otros}."


def texto_p1(q):
    """Escribe la sección de la pregunta 1."""
    d, i = q["dormitorios"], q["tipo_de_inmueble"]
    filas = "\n".join(f"| {f['grupo']} | {n(f['pisos'])} | {n(f['rentabilidad_mediana_pct'], 1)} % | {n(f['ic_bajo'], 1)} a {n(f['ic_alto'], 1)} | {n(f['sin_descuento_pct'], 1)} % | {n(f['euros_al_ano'])} € | {f['frente_al_total']} |" for f in d["tabla"])
    filas_i = "\n".join(f"| {f['grupo']} | {n(f['pisos'])} | {n(f['rentabilidad_mediana_pct'], 1)} % | {n(f['ic_bajo'], 1)} a {n(f['ic_alto'], 1)} | {n(f['sin_descuento_pct'], 1)} % | {n(f['euros_al_ano'])} € | {f['frente_al_total']} |" for f in i["tabla"])
    return f"""## Pregunta 1 · Qué tipo de piso rinde más

Con la superficie de valoraciones y el descuento, se dan los pisos de {lista_y(d['se_dan'])} habitaciones, porque no se distinguen entre sí. La referencia es la mediana de toda la base, {n(q['referencia']['valor'], 1)} %, con {n(q['referencia']['filas'])} pisos. En euros al año encabezan los de {d['primero_en_euros']} habitaciones, que no se distinguen de los de {lista_y(d['no_se_distinguen_del_primero_en_euros'])}.

| Habitaciones | Pisos | Rentabilidad bruta | Intervalo del 95 % | Sin descuento | Euros al año | Frente a la base |
|---|---|---|---|---|---|---|
{filas}

Por tipo de inmueble, se dan {lista_y(i['se_dan'])}.

| Tipo de inmueble | Pisos | Rentabilidad bruta | Intervalo del 95 % | Sin descuento | Euros al año | Frente a la base |
|---|---|---|---|---|---|---|
{filas_i}

De {n(q['por_segmentos']['distritos_comparables_1_y_2'])} distritos con 30 pisos de uno y de dos habitaciones, uno supera a dos en {n(q['por_segmentos']['distritos_donde_1_supera_a_2'])}. {texto_sensibilidad(q['sensibilidad_superficie'])} Se probaron {n(d['pares_probados'])} pares de habitaciones: por azar saldrían distintos unos {n(d['pares_que_saldrian_por_azar'], 1)}.

Comprobaciones: {texto_comprobaciones(q)}."""


def texto_que_ordena(q):
    """Dice con qué se asocia la rentabilidad entre barrios y cuánto rinden los de m² más barato frente a la lista."""
    x = q["que_ordena_la_lista"]
    if x["rentabilidad_con_ocupacion"] is None or x["m2_baratos"]["mediana_pct"] is None or x["firmes"]["mediana_pct"] is None:
        return "Con estos datos no se puede decir qué ordena la lista."
    return (f"Entre {n(x['barrios'])} barrios, la rentabilidad se asocia con la ocupación ({n(x['rentabilidad_con_ocupacion'], 2)} en correlación por rangos) y con el m² ({n(x['rentabilidad_con_m2'], 2)}). "
            f"La mediana conjunta con descuento es de {n(x['m2_baratos']['mediana_pct'], 1)} % en los barrios de m² más barato, {n(x['firmes']['mediana_pct'], 1)} % en los firmes y {n(x['grupo']['mediana_pct'], 1)} % en el grupo.")


def texto_con_un_ano(q):
    """Dice el puesto de cada firme con los pisos de un año o más."""
    u = q["con_un_ano_o_mas"]
    puestos = {x["barrio"]: x for x in u["barrios"]}
    partes = [f"{b}, {n(puestos[b]['puesto'])}.º con {n(puestos[b]['mediana_pct'], 1)} %" for b in q["firmes"] if b in puestos]
    return f"Con los pisos de un año o más ({n(u['pisos'])}, primera reseña hasta el {u['corte']}), entre {n(u['barrios_comparados'])} barrios con 30 pisos o más: {'; '.join(partes) or 'ningún firme llega al mínimo'}."


def texto_p2(q):
    """Escribe la sección de la pregunta 2."""
    orden = {"firme": 0, "con aviso": 1, "segunda línea": 2}
    filas = "\n".join(f"| {f['barrio']} | {f['clase']} | {n(len(f['pruebas_que_aguanta']))} | {', '.join(NOMBRE_PRUEBA[x] for x in f['pruebas_que_no_aguanta']) or 'ninguna'} | {n(f['pisos'])} | {n(f['rentabilidad_mediana_pct'], 1)} % | {n(f['cuartil_bajo_pct'], 1)} % | {n(f['parte_en_el_tope_pct'], 1)} % | {n(f['variantes_en_el_mejor_cuarto'])} |" for f in sorted(q["fichas_del_grupo"], key=lambda x: (orden[x["clase"]], x["barrio"])))
    avisos = "\n".join(f"- {f['barrio']}: {'; '.join(f['avisos_en_texto'])}." for f in q["fichas_del_grupo"] if f["avisos_en_texto"]) or "Ningún barrio del grupo lleva aviso."
    b, c = q["referencia_baratos"]["comparados"], q["referencia_baratos"]["toda_la_ciudad"]
    return f"""## Pregunta 2 · En qué barrios

El grupo tiene {n(len(q['grupo']))} barrios y {n(q['pisos_del_grupo'])} pisos. Son firmes, porque aguantan las cinco pruebas, {lista_y(q['firmes'])}, con {n(q['pisos_del_grupo_firme'])} pisos. Van con aviso, porque aguantan cuatro, {lista_y(q['con_aviso'])}. Van en segunda línea {lista_y(q['segunda_linea'])}. La referencia es la mediana de {n(q['referencia']['barrios'])} barrios con 30 pisos o más, {n(q['referencia']['valor'], 1)} %, y la mediana de toda la base es {n(q['mediana_de_toda_la_base'], 1)} %.

| Barrio | Clase | Pruebas que aguanta | Las que no | Pisos | Rentabilidad bruta | Cuartil bajo | Parte en el tope | Variantes de 12 |
|---|---|---|---|---|---|---|---|---|
{filas}

Avisos de las reglas §3:

{avisos}

Frente a una lista hecha solo por precio, entre los {n(b['barrios_entre_los_que_se_elige'])} barrios comparados coinciden {n(b['cuantos'])} de los {n(b['de'])} de m² más barato ({lista_y(b['coinciden'])}), y en toda la ciudad, {n(c['cuantos'])}.

{texto_que_ordena(q)}

{texto_con_un_ano(q)}

Frente a la mediana de toda la base, {n(q['barrios_por_encima_de_la_base'])} barrios quedan por encima y {n(q['barrios_por_debajo_de_la_base'])} por debajo; por azar saldrían distintos unos {n(q['azar_barrios_frente_a_la_base'], 1)}. Con más parte de pisos en el tope que la base hay {n(q['tope_por_encima_de_la_base'])} barrios, y por azar saldrían unos {n(q['azar_tope_frente_a_la_base'], 1)}.

Comprobaciones: {texto_comprobaciones(q)}."""


def texto_p3(q):
    """Escribe la sección de la pregunta 3."""
    si = lambda v: "sí" if v else "no"
    filas = "\n".join(f"| {f['barrio']} | {f['clase']} | {n(f['pisos'])} | {n(f['cuartil_bajo_pct'], 1)} % | {n(f['rango_entre_fotos_puntos'], 1)} | {si(f['se_distingue_del_primero'])} | {si(f['avisos_del_barrio']['depende_del_tope'])} | {si(f['avisos_del_barrio']['pocos_anuncios'])} | {si(f['avisos_del_barrio']['cuartil_bajo'])} | {n(f['pisos_sin_ocupacion_misma_base'])} ({n(f['sin_ocupacion_misma_base_pct'], 1)} %) |" for f in q["fichas_del_grupo"])

    def rango_en_texto(r):
        """Escribe un rango de rentabilidad con su peor y su mejor combinación."""
        return f"va de {n(r['minimo'], 1)} % a {n(r['maximo'], 1)} %: la peor combinación es {r['peor']['foto']} {'con' if r['peor']['descuento'] else 'sin'} descuento y la mejor, {r['mejor']['foto']} {'con' if r['mejor']['descuento'] else 'sin'} descuento" if r["minimo"] is not None else "no se puede dar"

    rango, rango_aviso = rango_en_texto(q["rango_de_rentabilidad_del_grupo_firme"]), rango_en_texto(q["rango_de_rentabilidad_de_firmes_y_con_aviso"])
    b = q["referencia"]
    return f"""## Pregunta 3 · Con qué riesgo

{n(len(q['no_se_distinguen_del_primero']))} de los {n(q['comparaciones_con_el_primero'])} barrios comparados con el primero, {q['primero']}, no se distinguen de él con el intervalo de la diferencia; entre las que sí, por azar saldrían unas {n(q['saldrian_por_azar'], 1)}. Si se cuentan los intervalos que se tocan, como hizo el reconocimiento, son {n(q['barrios_cuyo_intervalo_toca_el_del_primero'])}. La rentabilidad bruta del grupo firme {rango}. La de firmes más con aviso {rango_aviso}. Toda la base tiene un cuartil bajo de {n(b['cuartil_bajo_pct'], 1)} % y un rango entre fotos de {n(b['rango_entre_fotos_puntos'], 1)} puntos.

| Barrio | Clase | Pisos | Cuartil bajo | Rango entre fotos, puntos | Se distingue del primero | Depende del tope | Pocos anuncios | Cuartil bajo sin superar la base | Pisos sin ocupación |
|---|---|---|---|---|---|---|---|---|---|
{filas}

Los pisos sin ocupación de la tabla son los que pasan los demás filtros de la base, y su parte es sobre esos pisos más los de la base. Fuera del centro, {n(q['pisos_fuera_sin_ocupacion']['pisos'])} pisos no tienen ocupación, el {n(q['pisos_fuera_sin_ocupacion']['pct'], 1)} %, y quedan fuera del ranking.

Comprobaciones: {texto_comprobaciones(q)}."""


def informe(s):
    """Genera el Markdown a partir del diccionario que se guarda en el JSON."""
    r = ["# Indicadores del caso", "", f"Ejecución: {s['fecha_ejecucion']}. Fecha de los datos: {s['fecha_datos']}.", "", s["resultado"]["resumen"], "", "## Las preguntas y su planteamiento", ""]
    for q in s.get("preguntas", []):
        r.append(f"- {q['id']}, {q['pregunta']} Decisión: {q['decision']} Población: {n(q['poblacion']['filas'])} anuncios de la base de decisión, {q['poblacion']['periodo']}. Referencia: {q['referencia']['que_es']}.")
    r += [""]
    if s.get("preguntas"):
        p1, p2, p3 = s["preguntas"]
        r += [texto_p1(p1), "", texto_p2(p2), "", texto_p3(p3), "", "## Las 16 preguntas de comprobación", ""]
        for q in s["las_16"]:
            r += [f"### {q['id']} · {q['texto']}", "", f"- Base de decisión: {q['base_decision']['respuesta']}", f"- Base de comparación: {q['base_comparacion']['respuesta']}", ""]
        e = s["evolucion_oferta"]
        r += ["## Lo descriptivo", "", "### Oferta entre fotos", ""] + [f"- {f['foto']}: {n(f['anuncios'])} anuncios y {n(f['pisos_completos'])} pisos." for f in e["fotos"]]
        if e["junio_2025"]:
            r += [f"- Junio de 2025: {n(e['junio_2025']['anuncios'])} anuncios, recuento anotado de una foto que ya no se puede descargar."]
        z = s["estacionalidad"]
        r += ["", e["limites"], "", "### Estacionalidad por reseñas", "", f"En {n(z['meses'])} meses completos, el índice va de {n(z['indice_mas_bajo'], 2)} en {MESES[z['mes_mas_bajo'] - 1]} a {n(z['indice_mas_alto'], 2)} en {MESES[z['mes_mas_alto'] - 1]}, con {n(z['resenas_de_la_ventana'])} reseñas. {z['limites']}", "", "### Disponibilidad futura", ""]
        for k, v in s["disponibilidad"]["series"].items():
            if v:
                r.append(f"- {ETIQUETA[k]}: del {n(min(x['parte_libre_pct'] for x in v), 1)} % al {n(max(x['parte_libre_pct'] for x in v), 1)} % de días libres, en {n(len(v))} meses completos.")
        at = s["atractivo_y_competencia"]
        lic = s["licencias_y_registro"]
        r += ["", s["disponibilidad"]["limites"], "", "### Atractivo y competencia", "", f"Entre pisos de la base, la correlación por rangos del atractivo con la rentabilidad es {n(at['base']['atractivo_con_rentabilidad']['spearman'], 2)}, y entre barrios la competencia da {n(at['base']['competencia_con_rentabilidad_entre_barrios']['spearman'], 2)}. {at['lectura'].capitalize()}. {at['limites']}", "",
              "### Licencias y registro", "", f"El registro municipal tiene {n(lic['totales']['licencias'])} licencias y {n(lic['totales']['viviendas_con_licencia'])} viviendas, frente a {n(lic['totales']['anuncios'])} anuncios. {lic['limites']}", ""]
        r += [f"- {ETIQUETA[k]}: " + ", ".join(f"{x['tipo']} {n(x['anuncios'])} ({n(x['pct'], 1)} %)" for x in v["tipo"]) + "." for k, v in lic["registro"].items()]
        r += [""]
    r += ["## Lo que no saca conclusión", ""]
    for q in s.get("preguntas", [])[:2]:
        lista = ", ".join(f"{x['grupo']} ({x['casos']})" for x in q["sin_conclusion"])
        r.append(f"- {q['id']} y siguiente: {lista or 'ninguno'}." if q["id"] == "P2" else f"- {q['id']}: {lista or 'ninguno'}.")
    r += ["", "## Validaciones", ""] + [f"- {k.replace('_', ' ')}: {'pasa' if v else 'falla'}." for k, v in s.get("validaciones", {}).items()]
    r += ["", "## Parámetros usados", ""] + [f"- {p['nombre']}: {p['valor']} ({p['origen']})." for p in s.get("parametros", [])]
    r += ["", "## Datos personales", "", rc.texto_personales("Este paso usa `declara_temporada` y el tipo de registro, solo como tipo, y no deja ninguna columna con datos personales: sus resultados van por barrio y tipo de piso.")]
    r += ["", "## Límites", ""]
    for q in s.get("preguntas", []):
        r += [f"- {q['id']}, {x}" for x in q["limites"]]
    r += [f"- Pendiente {p['id']}: {p['pregunta']}" for p in s["pendientes"]]
    return "\n".join(r) + "\n"


def borrador(s, exploratorios):
    """Escribe el borrador de hallazgos con cada dato, su base y su JSON de origen, separados hallazgo, alerta e hipótesis."""
    p1, p2, p3 = s["preguntas"]
    j = "`informes/indicadores.json`"
    d, i = p1["dormitorios"], p1["tipo_de_inmueble"]
    r = p3["rango_de_rentabilidad_del_grupo_firme"]
    r2 = p3["rango_de_rentabilidad_de_firmes_y_con_aviso"]
    h = [f"Pregunta 1: se dan los pisos de {lista_y(d['se_dan'])} habitaciones, que no se distinguen entre sí; la referencia es {n(p1['referencia']['valor'], 1)} %. Base de decisión, {n(p1['poblacion']['filas'])} pisos. Dos vías. {j}, `preguntas[0].dormitorios`.",
         f"Pregunta 1: en euros al año encabezan los de {d['primero_en_euros']} habitaciones. Base de decisión. Dos vías. {j}, `preguntas[0].dormitorios`.", f"Pregunta 1: por tipo de inmueble se dan {lista_y(i['se_dan'])}. Base de decisión. Dos vías. {j}, `preguntas[0].tipo_de_inmueble`.",
         f"Pregunta 1: {texto_sensibilidad(p1['sensibilidad_superficie'])} Base de decisión. Medianas por dos vías. {j}, `preguntas[0].sensibilidad_superficie`.",
         f"Pregunta 2: grupo de {n(len(p2['grupo']))} barrios y {n(p2['pisos_del_grupo'])} pisos; firmes, con las cinco pruebas: {lista_y(p2['firmes'])}; con aviso, con cuatro: {lista_y(p2['con_aviso'])}; segunda línea: {lista_y(p2['segunda_linea'])}. Base de decisión. Dos vías. {j}, `preguntas[1].pruebas`.",
         f"Pregunta 2: frente a los {n(p2['referencia_baratos']['comparados']['de'])} barrios de m² más barato, coinciden {n(p2['referencia_baratos']['comparados']['cuantos'])} entre los comparados y {n(p2['referencia_baratos']['toda_la_ciudad']['cuantos'])} en toda la ciudad. Dos vías. {j}, `preguntas[1].referencia_baratos`.",
         f"Pregunta 3: {n(len(p3['no_se_distinguen_del_primero']))} de {n(p3['comparaciones_con_el_primero'])} barrios no se distinguen del primero, {p3['primero']}. Base de decisión. Una vía para el remuestreo en el script y otra en `tests/probar_indicadores_por_otro_camino.py`. {j}, `preguntas[2]`."]
    if r["minimo"] is not None:
        h.append(f"Pregunta 3: la rentabilidad bruta del grupo firme va de {n(r['minimo'], 1)} % a {n(r['maximo'], 1)} %. Pisos del grupo firme con precio en cada foto. Dos vías. {j}, `preguntas[2].rango_de_rentabilidad_del_grupo_firme`.")
    if r2["minimo"] is not None:
        h.append(f"Pregunta 3: la de firmes más con aviso va de {n(r2['minimo'], 1)} % a {n(r2['maximo'], 1)} %. Pisos de esos barrios con precio en cada foto. Dos vías. {j}, `preguntas[2].rango_de_rentabilidad_de_firmes_y_con_aviso`.")
    rec = s["recomendacion"]
    if rec["pisos"]:
        h.append(f"Recomendación: pisos de hasta 2 habitaciones del grupo firme, {n(rec['pisos'])} anuncios en Airbnb: {n(rec['rentabilidad_sin_descuento_pct'], 1)} % sin descuento y {n(rec['rentabilidad_con_descuento_pct'], 1)} % con él; {n(rec['compra_sin_descuento_eur'])} € de compra sin descuento, {n(rec['compra_con_descuento_eur'])} € con él y {n(rec['ingreso_anual_eur'])} € de ingreso anual, en mediana y sin gastos. Dos vías. {j}, `recomendacion`.")
    h.append(f"Pregunta 2: {texto_que_ordena(p2)} Dos vías. {j}, `preguntas[1].que_ordena_la_lista`.")
    h.append(f"Pregunta 2: {texto_con_un_ano(p2)} {j}, `preguntas[1].con_un_ano_o_mas`.")
    pb = s["licencias_y_registro"]["planta_baja"]
    h.append(f"Licencias: {n(pb['licencias'])} de {n(pb['de'])} incluyen planta baja, y {n(pb['firmes']['licencias'])} de {n(pb['firmes']['de'])} en los barrios firmes. Dos vías. {j}, `licencias_y_registro.planta_baja`.")
    h += [f"{q['id']}, base de decisión: {q['base_decision']['respuesta']} Dos vías. {j}, `las_16`." for q in s["las_16"]]
    h += [f"{q['id']}, base de comparación, para comparar: {q['base_comparacion']['respuesta']} Dos vías. {j}, `las_16`." for q in s["las_16"]]
    e, z = s["evolucion_oferta"], s["estacionalidad"]
    h += [f"Oferta: {n(f['anuncios'])} anuncios el {f['foto']}. Todos los anuncios de esa foto. Dos vías. {j}, `evolucion_oferta`." for f in e["fotos"]]
    if z["indice_mas_alto"] is not None:
        h.append(f"Reseñas: en {n(z['meses'])} meses completos, el índice va de {n(z['indice_mas_bajo'], 2)} en {MESES[z['mes_mas_bajo'] - 1]} a {n(z['indice_mas_alto'], 2)} en {MESES[z['mes_mas_alto'] - 1]}. Reseñas de los anuncios de septiembre. Dos vías. {j}, `estacionalidad`.")
    h.append(f"Atractivo y competencia: {s['atractivo_y_competencia']['lectura']}. Pisos del grupo. {j}, `atractivo_y_competencia`.")
    lic = s["licencias_y_registro"]["totales"]
    h.append(f"Licencias: {n(lic['licencias'])} licencias y {n(lic['viviendas_con_licencia'])} viviendas, frente a {n(lic['anuncios'])} anuncios de la foto. Dos vías. {j}, `licencias_y_registro`.")
    for tabla, e in exploratorios.items():
        h += [f"{x['id']} de {tabla}: {x['texto']} Una vía: se cruza antes de entrar. `informes/analisis-exploratorio__{tabla}.json`." for x in e["hallazgos"]]
    a = [f"{f['barrio']} ({f['clase']}): {'; '.join(f['avisos_en_texto'])}. Base de decisión. {j}, `preguntas[1].fichas_del_grupo`." for f in p2["fichas_del_grupo"] if f["avisos_en_texto"]]
    a += [f"{f['barrio']} ({f['clase']}): {n(f['pisos_sin_ocupacion_misma_base'])} pisos sin ocupación pasan los demás filtros, el {n(f['sin_ocupacion_misma_base_pct'], 1)} % de los que los pasan. Dos vías. {j}, `preguntas[2].fichas_del_grupo`." for f in p3["fichas_del_grupo"] if f["sin_ocupacion_misma_base_pct"] is not None]
    a += [f"{q['id']}, {x}" for q in s["preguntas"] for x in q["limites"] if not re.match(r"(empates|pesos|hacia_adelante|periodos|azar_en_grupos):", x)]
    for tabla, e in exploratorios.items():
        a += [f"{x['id']} de {tabla}: {x['texto']} `informes/analisis-exploratorio__{tabla}.json`." for x in e["alertas"]]
    hi = [f"{x['id']} de {tabla}: {x['texto']} Haría falta: {x['que_haria_falta']}" for tabla, e in exploratorios.items() for x in e["hipotesis"]]
    cabeza = ["---", "titulo: Borrador de hallazgos del caso, con cada dato que irá al informe final y su origen", f"estado: generado por `scripts/indicadores.py` el {s['fecha_ejecucion'][:10]}; generado por la cadena", f"fecha_documento: {s['fecha_ejecucion'][:10]}", "dueno: Juan Luis León", "fuente: `informes/indicadores.json`, `informes/analisis-exploratorio__analisis_anuncios.json`, `informes/analisis-exploratorio__analisis_barrios.json`", "---", "",
              "# Borrador de hallazgos del caso", "", "Es la lista de la que parte el informe final. Cada línea dice su base y su JSON. Las de una sola vía se cruzan antes de entrar. Ninguna dice por qué ocurre algo.", ""]
    return "\n".join(cabeza + ["## Hallazgos", ""] + [f"- {x}" for x in h] + ["", "## Alertas", ""] + [f"- {x}" for x in a] + ["", "## Hipótesis", ""] + [f"- {x}" for x in hi or ["No hay."]]) + "\n"


# ---------------------------------------------------------------------------
# 9. Ejecución
# ---------------------------------------------------------------------------

def planteamiento_de(texto):
    """Saca la decisión de cada pregunta del documento, para no escribirla aquí."""
    salida = {}
    for b in re.split(r"^## ", texto, flags=re.M):
        m = re.match(r"Pregunta (\d)", b)
        if m:
            d = re.search(r"- Decisión:\s*(.+)", b)
            salida[f"P{m.group(1)}"] = d.group(1).strip() if d else ""
    return salida


def leer_entrada():
    """Lee las tablas de análisis, lo oficial y los rasgos del anuncio."""
    columnas = ["id", "amenities", "review_scores_rating", "review_scores_location", "calculated_host_listings_count", "host_is_superhost", "number_of_reviews", "first_review"]
    ruta = rc.PROCESADO / "anuncios_integrado.parquet"
    disponibles = pd.read_parquet(ruta).columns
    return (pd.read_parquet(rc.PROCESADO / "analisis_anuncios.parquet"), pd.read_parquet(rc.PROCESADO / "analisis_barrios.parquet"), pd.read_parquet(rc.PROCESADO / "evolucion_oferta.parquet"), pd.read_parquet(rc.PROCESADO / "estacionalidad_resenas.parquet"),
            pd.read_parquet(rc.PROCESADO / "disponibilidad_futura.parquet"), pd.read_parquet(rc.PROCESADO / rc.CORREGIDA["oficial"]), pd.read_parquet(ruta, columns=[c for c in columnas if c in disponibles]), pd.read_parquet(rc.PROCESADO / rc.CORREGIDA["licencias"]))


def parar(s, resumen, siguiente, faltas=()):
    """Deja el JSON en PARADO con lo que falta."""
    s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": resumen, "artefactos": ["informes/indicadores.json", "informes/indicadores.md"], "siguiente": siguiente}
    s["pendientes"] = [{"id": f"P-{i:02d}", "tabla": "", "columna": "", "pregunta": x, "opciones": []} for i, x in enumerate(faltas, 1)]
    rc.guardar(s, "indicadores", informe)
    return s


def principal(s):
    """Comprueba la entrada, calcula dos veces, valida y guarda."""
    faltas = falta_en_planteamiento(PLANTEAMIENTOS.read_text(encoding="utf-8")) if PLANTEAMIENTOS.exists() else ["no existe 04_planteamientos.md"]
    if faltas:
        return parar(s, "El planteamiento no está completo.", "completar metodo/04_planteamientos.md", faltas)
    exploratorios = {}
    for tabla in eda.TABLAS:
        ruta = rc.INFORMES / f"analisis-exploratorio__{tabla}.json"
        if not ruta.exists():
            return parar(s, f"Falta el exploratorio de {tabla}.", "analisis-exploratorio")
        exploratorios[tabla] = json.loads(ruta.read_text(encoding="utf-8"))
        if exploratorios[tabla]["resultado"]["estado"] in ("PARADO", "ERROR"):
            return parar(s, f"El exploratorio de {tabla} está en {exploratorios[tabla]['resultado']['estado']}.", "analisis-exploratorio")
    t = json.loads((rc.INFORMES / "transformacion-datos.json").read_text(encoding="utf-8"))
    for x in t["salidas"]:
        if cd.huella(rc.CASO / x["ruta"]) != x["sha256"]:
            return parar(s, f"La huella de {x['ruta']} no es la que dejó la transformación.", "repetir transformacion-datos")

    antes = cd.huellas_de_raw()
    entrada = leer_entrada()
    s["entradas"] = [rc.entrada(rc.PROCESADO / f"{x['tabla']}.parquet", d) for x, d in zip(t["salidas"], entrada[:5])] + [rc.entrada(rc.PROCESADO / rc.CORREGIDA["oficial"], entrada[5]), rc.entrada(rc.PROCESADO / "anuncios_integrado.parquet", entrada[6]), rc.entrada(rc.PROCESADO / rc.CORREGIDA["licencias"], entrada[7])]
    plant = planteamiento_de(PLANTEAMIENTOS.read_text(encoding="utf-8"))
    dec = rc.leer_decisiones()
    r1 = redondear(calcular(entrada, plant, dec))
    r2 = redondear(calcular(entrada, plant, dec))
    repetido = json.dumps(r1, sort_keys=True, default=str) == json.dumps(r2, sort_keys=True, default=str)
    s.update(cd.sin_nan(r1))
    s["parametros"] = PARAMETROS
    codigo = Path(__file__).read_text(encoding="utf-8")
    s["validaciones"] = validaciones(r1, repetido, cd.huellas_de_raw() == antes, codigo, faltas)
    s["decisiones_propias"] = [
        "Texto de las 16 preguntas: la lista de comprobación del análisis.",
        "El rango del grupo firme es la mediana conjunta de sus pisos en cada una de las seis combinaciones; también se da barrio a barrio.",
        "Rango entre fotos: mediana del barrio con estancia de hasta 3 noches, y una foto con menos de 20 pisos no da cifra, el mínimo de las variantes.",
        "«Depende del tope»: el barrio sale del grupo al repetir las 12 variantes sin los pisos en 255 días de toda la base, porque así se mide cada prueba. Al lado va lo que da quitando solo los del barrio.",
        "Anuncios del anfitrión: `calculated_host_listings_count`, el recuento de la foto.",
        "Cotización a más de 60 días: cada variante mira la foto de la que toma el precio. Una cotización vacía no se cuenta como lejana.",
        "Pisos sin ocupación como cero: se les aplican los demás filtros de cada variante, también el del precio.",
        "Sensibilidad de superficie: las ocho combinaciones de los extremos, el estudio es el piso sin habitación, y los pisos que la regla lleva a otra superficie por sus baños no se mueven.",
        "Barrios baratos: tantos como barrios tiene el grupo, entre los comparados con 30 pisos o más y, aparte, en toda la ciudad.",
        "La pregunta 1 no agrupa los pisos sin habitación con los de uno, aunque la superficie sea la misma.",
        "Factores y tamaño de la base de comparación: solo sus pisos, como el reconocimiento, porque una habitación no se compara con una vivienda.",
        "Precio de la base de comparación: el de vivienda de las reglas §3, y el publicado al lado en la pregunta S01.",
        "Atractivo dentro del grupo: se parte en dos por la mediana de puntos del grupo, y se resta la mediana del barrio para mirarlo dentro de cada uno.",
        "Estacionalidad: los últimos 24 meses completos, la misma ventana del reconocimiento.",
        "Pisos de un año o más: primera reseña en la fecha de la foto menos un año o antes; es la única fecha de antigüedad del anuncio en los datos.",
        "Licencias con planta baja: las que nombran BAJA en su texto, sola o con otras plantas. La columna es texto libre y solo se le pregunta eso.",
        "Cifra de la recomendación: mediana conjunta de los pisos de 2 habitaciones o menos de los tres firmes, estudios incluidos.",
        "Barrios de m² más barato frente a la lista: los 9 de los comparados; sus pares se miden aunque compartan barrios con la lista, de modo que el intervalo es orientativo."]
    s["pendientes_resueltos"] = [{"id": "P-01", "pregunta": "Cuándo un barrio depende del tope y cuándo tiene pocos anuncios.", "resuelto_por": "reglas §3, con las cinco pruebas y los tres avisos"}]
    s["pendientes"] = [{**p, "id": f"P-{i:02d}"} for i, p in enumerate(t.get("pendientes", []), 2)]
    fallan = [k for k, v in s["validaciones"].items() if v is not True]
    control_mal = [k for k, v in s["controles"].items() if v["coincide"] is False]
    if control_mal:
        s["controles"]["que_pasa"] = f"No salió lo esperado en: {', '.join(control_mal)}. No se ajusta nada: el resultado es el calculado."
    estado = "ERROR" if fallan else "AVISO" if control_mal or s["pendientes"] else "OK"
    p1, p2, p3 = s["preguntas"]
    resumen = f"Validaciones que fallan: {', '.join(fallan)}." if fallan else f"Tres preguntas y 16 comprobaciones contestadas sobre {n(p1['poblacion']['filas'])} pisos: {n(len(p2['grupo']))} barrios en el grupo, {n(len(p2['firmes']))} firmes y {n(len(p2['con_aviso']))} con aviso."
    s["resultado"] = {"estado": estado, "riesgo": "medio" if estado != "ERROR" else "alto", "resumen": resumen, "artefactos": ["informes/indicadores.json", "informes/indicadores.md", "config/metodo/06_borrador_de_hallazgos.md"], "siguiente": "interpretacion-resultados" if not fallan else "arreglar el fallo"}
    rc.guardar(s, "indicadores", informe)
    BORRADOR.parent.mkdir(parents=True, exist_ok=True)
    BORRADOR.write_text(borrador(s, exploratorios), encoding="utf-8", newline="\n")
    return s


if __name__ == "__main__":
    salida = rc.bloque_comun(ETAPA, VERSION, SCRIPT)
    principal(salida)
