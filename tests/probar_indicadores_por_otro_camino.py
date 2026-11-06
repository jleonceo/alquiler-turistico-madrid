"""Rehace por otro camino las cifras principales de los indicadores, sin pandas ni numpy y sin los scripts del caso.

Lee data/processed/analisis_anuncios.parquet con pyarrow y lo recorre con la biblioteca estándar. Rehace las cifras de control, las medianas de la pregunta 1, la sensibilidad de superficie, la regla de las 12 variantes, las cinco pruebas, las
clases y los avisos, la tabla de los barrios del grupo, los dos rangos, los baratos, cada barrio frente al primero y varias de
las 16 preguntas. Después compara con
informes/indicadores.json, o con el JSON que se le pase como primer argumento. El remuestreo usa `random`, otro generador: sus
intervalos no salen iguales y se admite una diferencia pequeña. Sale con 0 si todo coincide y con 1 si algo no.

Esta prueba abre los datos reales: su trabajo es esa comprobación.
"""
import csv
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
RUTA_JSON = Path(sys.argv[1]) if len(sys.argv) > 1 else CASO / "informes" / "indicadores.json"
# Cifras de control, escritas aquí a propósito: el script no las lleva dentro.
CONTROL = {"pisos": 2940, "ingreso": 71518518.15, "barrios": 36, "comparacion": 7249,
           "grupo": ["Canillejas", "Casco Histórico de Vallecas", "Numancia", "Opañel", "Puerta del Angel", "Quintana", "San Diego", "Ventas", "Vista Alegre"],
           "firmes": ["Numancia", "San Diego", "Ventas"], "con_aviso": ["Casco Histórico de Vallecas", "Opañel"]}
ANFITRION, COTIZACION, POCOS = 10, 60, 40  # reglas §7, escritas aquí a propósito
TOL = 1e-4
TOL_REMUESTREO = 0.5  # puntos: otro generador no da el mismo extremo
FALLOS = []


def caso(nombre, obtenido, esperado, tol=0):
    """Compara dos cifras y dice si coinciden."""
    if isinstance(obtenido, (int, float)) and isinstance(esperado, (int, float)):
        bien = abs(obtenido - esperado) <= tol
    else:
        bien = obtenido == esperado
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}: {obtenido}" + ("" if bien else f" frente a {esperado}"))
    if not bien:
        FALLOS.append(nombre)


def cuantil(v, q):
    """Cuantil lineal a mano."""
    v = sorted(v)
    pos = (len(v) - 1) * q
    i = int(pos)
    return v[i] if i + 1 == len(v) else v[i] + (pos - i) * (v[i + 1] - v[i])


def rangos(v):
    """Rango medio con empates."""
    orden = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[orden[j + 1]] == v[orden[i]]:
            j += 1
        for k in range(i, j + 1):
            r[orden[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    """Correlación por rangos a mano."""
    return statistics.correlation(rangos(x), rangos(y))


def leer():
    """Lee las columnas que hacen falta como filas de diccionarios."""
    columnas = ["id", "barrio", "distrito", "tipo_alquiler", "tipo_inmueble", "lado_centro", "ocupacion_dias", "huespedes", "banos", "dormitorios", "camas", "estancia_noches", "precio_eur", "precio_mar_eur", "precio_jun_eur", "superficie_valoraciones_m2", "precio_m2_eur",
                "declara_temporada", "anuncios_anfitrion", "dias_cotizacion", "dias_cotizacion_mar", "dias_cotizacion_jun", "excl_cero_banos", "excl_no_vivienda", "excl_tamano_incoherente", "base_decision", "base_comparacion", "ingreso_anual_eur", "precio_vivienda_comparacion_eur", "rent_valoraciones_desc_pct", "rent_valoraciones_sin_pct", "compra_valoraciones_sin_eur", "compra_valoraciones_desc_eur"]
    t = pq.read_table(CASO / "data" / "processed" / "analisis_anuncios.parquet", columns=columnas).to_pylist()
    for f in t:
        for c, v in f.items():
            if isinstance(v, float) and v != v:
                f[c] = None
    return t


def fija(f, cero=False):
    """Filtros de la base que no cambian entre variantes (reglas §7), con CP-007 a CP-009. Con cero entran los pisos sin ocupación."""
    return (f["tipo_alquiler"] == "Entire home/apt" and f["lado_centro"] == "fuera" and (cero or f["ocupacion_dias"] > 0) and f["huespedes"] <= 8 and f["banos"] is not None and f["banos"] <= 5 and f["dormitorios"] is not None and f["dormitorios"] <= 5
            and f["camas"] is not None and f["camas"] <= 6 and not (f["excl_cero_banos"] or f["excl_no_vivienda"] or f["excl_tamano_incoherente"]))


def rent(f, col, factor=0.75):
    """Rentabilidad bruta de las reglas §6."""
    return 100 * f[col] * f["ocupacion_dias"] / (f["superficie_valoraciones_m2"] * f["precio_m2_eur"] * factor)


def en_precio(f, col):
    """Precio de esa foto dentro del rango."""
    return f[col] is not None and 20 <= f[col] <= 1000


DIAS_DE = {"precio_mar_eur": "dias_cotizacion_mar", "precio_jun_eur": "dias_cotizacion_jun", "precio_eur": "dias_cotizacion"}


def variantes(t, excluir=lambda f: False, cero=False, lejos=False):
    """Cuenta en cuántas de las 12 variantes queda cada barrio en el mejor cuarto."""
    veces = Counter()
    base = [f for f in t if fija(f, cero) and not excluir(f)]
    for est in (3, 6):
        for col in ("precio_mar_eur", "precio_jun_eur", "precio_eur"):
            g = defaultdict(list)
            for f in base:
                if f["estancia_noches"] is not None and f["estancia_noches"] <= est and en_precio(f, col) and not (lejos and f[DIAS_DE[col]] is not None and f[DIAS_DE[col]] > COTIZACION):
                    g[f["barrio"]].append(rent(f, col))
            for minimo in (30, 20):
                med = {b: statistics.median(v) for b, v in g.items() if len(v) >= minimo}
                corte = cuantil(list(med.values()), 0.75)
                veces.update(b for b, v in med.items() if v >= corte)
    return veces


def remuestreo(v, generador, veces=2000):
    """Medianas remuestreadas con random, otro generador que el del script."""
    return [statistics.median(generador.choices(v, k=len(v))) for _ in range(veces)]


def principal():
    """Rehace y compara."""
    j = json.loads(RUTA_JSON.read_text(encoding="utf-8"))
    t = leer()
    d = [f for f in t if f["base_decision"]]
    c = [f for f in t if f["base_comparacion"]]
    p1, p2, p3 = j["preguntas"]

    # Cifras de control.
    caso("pisos de la base de decisión", len(d), CONTROL["pisos"])
    caso("ingreso de la base", round(math.fsum(f["ingreso_anual_eur"] for f in d), 2), CONTROL["ingreso"], 0.005)
    caso("anuncios de la comparación", len(c), CONTROL["comparacion"])
    por_barrio = defaultdict(list)
    for f in d:
        por_barrio[f["barrio"]].append(f)
    caso("barrios con 30 o más", sum(1 for v in por_barrio.values() if len(v) >= 30), CONTROL["barrios"])
    caso("la regla y la marca dan los mismos pisos", {f["id"] for f in t if fija(f) and f["estancia_noches"] is not None and f["estancia_noches"] <= 3 and en_precio(f, "precio_eur")}, {f["id"] for f in d})
    caso("control del JSON: pisos", j["cifras_de_control"]["pisos_base_decision"], CONTROL["pisos"])
    caso("control del JSON: ingreso", j["cifras_de_control"]["ingreso_base_decision_eur"], CONTROL["ingreso"], 0.005)

    # Pregunta 1.
    grupo_d = defaultdict(list)
    for f in d:
        grupo_d["4 o más" if f["dormitorios"] >= 4 else str(int(f["dormitorios"]))].append(f)
    caso("referencia de la pregunta 1", statistics.median(f["rent_valoraciones_desc_pct"] for f in d), p1["referencia"]["valor"], TOL)
    for x in p1["dormitorios"]["tabla"]:
        v = grupo_d[x["grupo"]]
        caso(f"{x['grupo']} habitaciones, recuento", len(v), x["pisos"])
        caso(f"{x['grupo']} habitaciones, rentabilidad", statistics.median(rent(f, "precio_eur") for f in v), x["rentabilidad_mediana_pct"], TOL)
        caso(f"{x['grupo']} habitaciones, sin descuento", statistics.median(rent(f, "precio_eur", 1.0) for f in v), x["sin_descuento_pct"], TOL)
        caso(f"{x['grupo']} habitaciones, euros", statistics.median(f["ingreso_anual_eur"] for f in v), x["euros_al_ano"], TOL)
    # Sensibilidad de superficie: las medianas de cada combinación, a mano.
    regla_sup = {"0": 50.0, "1": 50.0, "2": 65.0}
    for comb in p1["sensibilidad_superficie"]["combinaciones"]:
        for g_, v in grupo_d.items():
            if g_ in comb["medianas"]:
                val = [f["ingreso_anual_eur"] * 100 / ((comb["superficies"][g_] if g_ in comb["superficies"] and f["superficie_valoraciones_m2"] == regla_sup[g_] else f["superficie_valoraciones_m2"]) * f["precio_m2_eur"] * 0.75) for f in v]
                caso(f"sensibilidad {comb['superficies']}, {g_} habitaciones", statistics.median(val), comb["medianas"][g_], TOL)

    gen = random.Random(63)
    res = {x["grupo"]: remuestreo([rent(f, "precio_eur") for f in grupo_d[x["grupo"]]], gen) for x in p1["dormitorios"]["tabla"]}
    for x in p1["dormitorios"]["pares"]:
        dif = sorted(a - b for a, b in zip(res[x["a"]], res[x["b"]]))
        bajo, alto = dif[50], dif[1949]
        caso(f"{x['a']} frente a {x['b']}, bajo", bajo, x["bajo"], TOL_REMUESTREO)
        caso(f"{x['a']} frente a {x['b']}, alto", alto, x["alto"], TOL_REMUESTREO)

    # Pregunta 2: las 12 variantes.
    veces = variantes(t)
    grupo = sorted(b for b, v in veces.items() if v >= 7)
    pruebas = {"sin_temporada": variantes(t, lambda f: f["declara_temporada"]), "sin_anfitriones_grandes": variantes(t, lambda f: f["anuncios_anfitrion"] >= ANFITRION), "sin_cotizaciones_lejanas": variantes(t, lejos=True),
               "solo_1_y_2_dormitorios": variantes(t, lambda f: f["dormitorios"] not in (1, 2)), "sin_ocupacion_como_cero": variantes(t, cero=True)}
    aguanta = {b: sorted(x for x, v in pruebas.items() if v[b] >= 7) for b in grupo}
    firmes = sorted(b for b, x in aguanta.items() if len(x) == 5)
    con_aviso = sorted(b for b, x in aguanta.items() if len(x) == 4)
    ref = json.loads((CASO / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))
    caso("grupo rehecho frente al control", grupo, CONTROL["grupo"])
    caso("firmes rehechos frente al control", firmes, CONTROL["firmes"])
    caso("con aviso rehechos frente al control", con_aviso, CONTROL["con_aviso"])
    caso("barrios del grupo frente a la referencia", len(grupo), ref["barrios_del_grupo"])
    caso("barrios firmes frente a la referencia", len(firmes), ref["barrios_firmes"])
    caso("grupo del JSON", p2["grupo"], grupo)
    caso("firmes del JSON", p2["firmes"], firmes)
    caso("con aviso del JSON", p2["pruebas"]["con_aviso"], con_aviso)
    caso("segunda línea del JSON", p2["pruebas"]["segunda_linea"], sorted(set(grupo) - set(firmes) - set(con_aviso)))
    for nombre, v in pruebas.items():
        caso(f"variantes de la prueba {nombre}", p2["pruebas"]["variantes_por_prueba"][nombre], dict(sorted(v.items())))
    for b, x in aguanta.items():
        caso(f"{b}, pruebas que aguanta", sorted(p2["pruebas"]["barrios"][b]["aguanta"]), x)
    caso("variantes por barrio del JSON", p2["variantes_por_barrio"], dict(sorted((k, v) for k, v in veces.items())))
    caso("mediana de los barrios", statistics.median(statistics.median(f["rent_valoraciones_desc_pct"] for f in v) for v in por_barrio.values() if len(v) >= 30), p2["referencia"]["valor"], TOL)
    sin_tope = variantes(t, lambda f: f["ocupacion_dias"] == 255)
    for x in p2["fichas_del_grupo"]:
        v = por_barrio[x["barrio"]]
        r = [f["rent_valoraciones_desc_pct"] for f in v]
        caso(f"{x['barrio']}, pisos", len(v), x["pisos"])
        caso(f"{x['barrio']}, mediana", statistics.median(r), x["rentabilidad_mediana_pct"], TOL)
        caso(f"{x['barrio']}, cuartil bajo", cuantil(r, 0.25), x["cuartil_bajo_pct"], TOL)
        caso(f"{x['barrio']}, tope", 100 * sum(1 for f in v if f["ocupacion_dias"] == 255) / len(v), x["parte_en_el_tope_pct"], TOL)
        caso(f"{x['barrio']}, aviso de cuartil bajo", cuantil(r, 0.25) <= cuantil([f["rent_valoraciones_desc_pct"] for f in d], 0.25), x["avisos_del_barrio"]["cuartil_bajo"])
        caso(f"{x['barrio']}, aviso de pocos anuncios", len(v) <= POCOS, x["avisos_del_barrio"]["pocos_anuncios"])
        caso(f"{x['barrio']}, aviso del tope", sin_tope[x["barrio"]] < 7, x["avisos_del_barrio"]["depende_del_tope"])

    # Pregunta 3: rango del grupo firme, rango entre fotos y barrios frente al primero.
    fil = [f for f in t if fija(f) and f["estancia_noches"] is not None and f["estancia_noches"] <= 3 and f["barrio"] in firmes]
    meds = []
    for foto, col in (("marzo", "precio_mar_eur"), ("junio", "precio_jun_eur"), ("septiembre", "precio_eur")):
        for factor in (0.75, 1.0):
            meds.append(statistics.median(rent(f, col, factor) for f in fil if en_precio(f, col)))
    r = p3["rango_de_rentabilidad_del_grupo_firme"]
    caso("rango del grupo firme, mínimo", min(meds), r["minimo"], TOL)
    caso("rango del grupo firme, máximo", max(meds), r["maximo"], TOL)
    fil2 = [f for f in t if fija(f) and f["estancia_noches"] is not None and f["estancia_noches"] <= 3 and f["barrio"] in firmes + con_aviso]
    meds2 = [statistics.median(rent(f, col, factor) for f in fil2 if en_precio(f, col)) for col in ("precio_mar_eur", "precio_jun_eur", "precio_eur") for factor in (0.75, 1.0)]
    r2 = p3["rango_de_rentabilidad_de_firmes_y_con_aviso"]
    caso("rango de firmes y con aviso, mínimo", min(meds2), r2["minimo"], TOL)
    caso("rango de firmes y con aviso, máximo", max(meds2), r2["maximo"], TOL)

    # Pisos sin ocupación, con los mismos filtros de la base y sin el de la ocupación.
    for x in p3["fichas_del_grupo"]:
        misma = [f for f in t if f["barrio"] == x["barrio"] and fija(f, True) and f["estancia_noches"] is not None and f["estancia_noches"] <= 3 and en_precio(f, "precio_eur")]
        caso(f"{x['barrio']}, parte sin ocupación", 100 * sum(1 for f in misma if f["ocupacion_dias"] == 0) / len(misma), x["sin_ocupacion_misma_base_pct"], TOL)

    # La referencia: los barrios de m² más barato, con el empate deshecho por el nombre.
    m2 = {}
    for f in t:
        m2[f["barrio"]] = f["precio_m2_eur"]
    comparados = [b for b, v in por_barrio.items() if len(v) >= 30]
    baratos = sorted(comparados, key=lambda b: (m2[b], b))[:len(grupo)]
    caso("baratos entre los comparados", p2["referencia_baratos"]["comparados"]["baratos"], baratos)
    caso("coinciden con el grupo", p2["referencia_baratos"]["comparados"]["cuantos"], len(set(baratos) & set(grupo)))
    baratos_c = sorted(m2, key=lambda b: (m2[b], b))[:len(grupo)]
    caso("coinciden con el grupo, en toda la ciudad", p2["referencia_baratos"]["toda_la_ciudad"]["cuantos"], len(set(baratos_c) & set(grupo)))
    todos = [f for f in t if fija(f) and f["estancia_noches"] is not None and f["estancia_noches"] <= 3]
    for x in p3["fichas_del_grupo"]:
        por_foto = []
        for col in ("precio_mar_eur", "precio_jun_eur", "precio_eur"):
            v = [rent(f, col) for f in todos if f["barrio"] == x["barrio"] and en_precio(f, col)]
            if len(v) >= 20:
                por_foto.append(statistics.median(v))
        caso(f"{x['barrio']}, rango entre fotos", max(por_foto) - min(por_foto), x["rango_entre_fotos_puntos"], TOL)
    primero = p3["primero"]
    gen = random.Random(630)
    base_primero = remuestreo([f["rent_valoraciones_desc_pct"] for f in por_barrio[primero]], gen)
    distinguen = 0
    for x in p3["tabla_riesgo"]:
        if x["barrio"] == primero:
            continue
        otro = remuestreo([f["rent_valoraciones_desc_pct"] for f in por_barrio[x["barrio"]]], gen)
        dif = sorted(a - b for a, b in zip(base_primero, otro))
        distinguen += dif[50] > 0 or dif[1949] < 0
    caso("barrios que se distinguen del primero, con otro generador", distinguen, len(p3["se_distinguen_del_primero"]), 2)

    # La recomendación, el cuartil de la base, los baratos frente a la lista, el orden entre barrios y los pisos de un año o más.
    rec = [f for f in d if f["barrio"] in firmes and f["dormitorios"] <= 2]
    caso("recomendación, pisos", len(rec), j["recomendacion"]["pisos"])
    for clave, col in (("rentabilidad_sin_descuento_pct", "rent_valoraciones_sin_pct"), ("rentabilidad_con_descuento_pct", "rent_valoraciones_desc_pct"), ("compra_sin_descuento_eur", "compra_valoraciones_sin_eur"), ("compra_con_descuento_eur", "compra_valoraciones_desc_eur"), ("ingreso_anual_eur", "ingreso_anual_eur")):
        caso(f"recomendación, {clave}", statistics.median(f[col] for f in rec), j["recomendacion"][clave], TOL)
    caso("cuartil bajo de toda la base", cuantil([f["rent_valoraciones_desc_pct"] for f in d], 0.25), p2["cuartil_bajo_de_toda_la_base"], TOL)
    caso("barrios sin superar la mediana", sum(1 for b in comparados if cuantil([f["rent_valoraciones_desc_pct"] for f in por_barrio[b]], 0.25) <= statistics.median(f["rent_valoraciones_desc_pct"] for f in d)), p2["aviso_del_cuartil"]["no_superan_la_mediana"])
    q = p2["que_ordena_la_lista"]
    for nombre, barrios in (("m2_baratos", baratos), ("firmes", firmes), ("grupo", grupo)):
        caso(f"rentabilidad conjunta de {nombre}", statistics.median(f["rent_valoraciones_desc_pct"] for f in d if f["barrio"] in barrios), q[nombre]["mediana_pct"], TOL)
    medianas = [statistics.median(f["rent_valoraciones_desc_pct"] for f in por_barrio[b]) for b in comparados]
    caso("rentabilidad y ocupación entre barrios", spearman(medianas, [statistics.median(f["ocupacion_dias"] for f in por_barrio[b]) for b in comparados]), q["rentabilidad_con_ocupacion"], TOL)
    caso("rentabilidad y m² entre barrios", spearman(medianas, [m2[b] for b in comparados]), q["rentabilidad_con_m2"], TOL)
    con_aviso_d = [f for f in d if f["barrio"] in con_aviso]
    caso("operadores grandes en los barrios con aviso", 100 * sum(1 for f in con_aviso_d if f["anuncios_anfitrion"] >= ANFITRION) / len(con_aviso_d), p2["operadores_grandes"]["con_aviso_pct"], TOL)
    # La primera reseña no está en la tabla de análisis: se lee de la foto corregida, por el número del anuncio.
    primera = dict(zip(*(pq.read_table(CASO / "data" / "processed" / "anuncios_integrado.parquet", columns=["id", "first_review"]).column(c).to_pylist() for c in ("id", "first_review"))))
    un_ano = defaultdict(list)
    for f in d:
        if primera[f["id"]] is not None and primera[f["id"]] <= "2025-09-17":
            un_ano[f["barrio"]].append(f["rent_valoraciones_desc_pct"])
    orden_un_ano = sorted((b for b, v in un_ano.items() if len(v) >= 30), key=lambda b: (-statistics.median(un_ano[b]), b))
    caso("barrios con 30 anuncios de un año o más", len(orden_un_ano), p2["con_un_ano_o_mas"]["barrios_comparados"])
    for x in p2["con_un_ano_o_mas"]["barrios"]:
        caso(f"{x['barrio']}, puesto con un año o más", orden_un_ano.index(x["barrio"]) + 1, x["puesto"])
    # Las licencias con planta baja se cuentan desde el fichero en bruto, con otra lectura de la columna.
    with open(CASO / "data" / "raw" / "externos" / "licencias_vut_por_barrio.csv", encoding="utf-8") as fichero:
        licencias = list(csv.DictReader(fichero))
    caso("licencias con planta baja", sum(1 for f in licencias if "BAJA" in f["planta"].upper()), j["licencias_y_registro"]["planta_baja"]["licencias"])
    caso("licencias con planta baja, en los firmes", sum(1 for f in licencias if "BAJA" in f["planta"].upper() and f["barrio"] in firmes), j["licencias_y_registro"]["planta_baja"]["firmes"]["licencias"])

    # Las 16: las que dan una cifra sola, en las dos bases.
    s = {q["id"]: q for q in j["las_16"]}
    precio_c = [f["precio_vivienda_comparacion_eur"] for f in c if f["precio_vivienda_comparacion_eur"] is not None]
    caso("S01, media en decisión", statistics.fmean(f["precio_eur"] for f in d), s["S01"]["base_decision"]["datos"]["global"]["media"], TOL)
    caso("S01, mediana en comparación", statistics.median(precio_c), s["S01"]["base_comparacion"]["datos"]["global"]["mediana"], TOL)
    caso("S01, anuncios con precio de vivienda", len(precio_c), s["S01"]["base_comparacion"]["datos"]["global"]["casos"])
    caso("S07, media en decisión", statistics.fmean(f["ocupacion_dias"] for f in d), s["S07"]["base_decision"]["datos"]["global"]["media"], TOL)
    caso("S07, mediana en comparación", statistics.median(f["ocupacion_dias"] for f in c), s["S07"]["base_comparacion"]["datos"]["global"]["mediana"], TOL)
    caso("S08, parte en el tope", 100 * sum(1 for f in d if f["ocupacion_dias"] == 255) / len(d), s["S08"]["base_decision"]["datos"]["toda_la_base"]["255"], TOL)
    g = defaultdict(list)
    for f in d:
        g[f["barrio"]].append(f["precio_eur"])
    comp = Counter(f["barrio"] for f in t)
    med = {b: statistics.median(v) for b, v in g.items() if len(v) >= 30}
    caso("S05, competencia y precio", spearman(list(med.values()), [comp[b] for b in med]), s["S05"]["base_decision"]["datos"]["spearman"], TOL)

    # La propia prueba tiene que poder dar rojo.
    tamano_fallos = len(FALLOS)
    caso("(rojo a propósito: tiene que FALLAR) dos cifras distintas", 1.0, 1.1, TOL)
    if len(FALLOS) != tamano_fallos + 1:
        print("FALLA la comparación no detecta una diferencia")
        return 1
    FALLOS.pop()
    print(f"\n{len(FALLOS)} casos fallan: {FALLOS}" if FALLOS else "\ntodos los casos pasan")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
