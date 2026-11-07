"""Rehace las cifras de la portada desde la tabla local de data/publicado/, sin pandas y sin ningún otro script del repositorio.

Es la vía independiente: no importa nada de la cadena, recorre la tabla fila a fila con la biblioteca estándar y aplica de
nuevo las reglas de docs/reglas_de_negocio.md: las 12 variantes, las cinco pruebas y la recomendación. Imprime lo que sale.
Con --comprobar lo compara además con informes/indicadores.json y con las versiones en español e inglés de la portada, y sale con 1 si algo no coincide.

Ejecución:
  python scripts/rehacer_portada.py --comprobar
"""
import argparse
import csv
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
TABLA = CASO / "data" / "publicado" / "pisos_fuera_del_centro.csv.gz"
PRECIOS_MERCADO = CASO / "config" / "fuentes" / "precios_de_mercado.json"
INDICADORES = CASO / "informes" / "indicadores.json"
ESTANCIAS = (3, 6)
MINIMOS = (30, 20)
MAYORIA = 7
FOTOS = ("mar", "jun", "sep")
PRUEBAS = ("temporada", "anfitriones", "cotizacion", "dormitorios", "sin_ocupacion")
OTROS = "otros"
TOLERANCIA = 0.051  # las cifras se comparan a un decimal y la tabla guarda cuatro


def numero(texto):
    """Convierte una celda en número, o en None si está vacía."""
    return float(texto) if texto else None


def leer(ruta=TABLA):
    """Lee la tabla publicada como una lista de diccionarios."""
    with gzip.open(ruta, "rt", encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    for x in filas:
        for c in x:
            if c != "barrio":
                x[c] = numero(x[c])
    return filas


def cuantil(valores, q):
    """Cuantil con interpolación lineal."""
    v = sorted(valores)
    pos = (len(v) - 1) * q
    i = int(pos)
    return v[i] if i + 1 == len(v) else v[i] + (v[i + 1] - v[i]) * (pos - i)


def entra(x, foto, estancia, prueba):
    """Dice si un piso entra en una variante, con la prueba que se esté repitiendo."""
    r = x[f"rent_{foto}_pct"]
    if r is None or (estancia == 3 and not x["estancia_hasta_3"]):
        return False
    if r == 0 and prueba != "sin_ocupacion":
        return False
    if prueba == "temporada" and x["temporada"]:
        return False
    if prueba == "anfitriones" and x["anfitrion_10_o_mas"]:
        return False
    if prueba == "cotizacion" and x[f"lejana_{foto}"]:
        return False
    return not (prueba == "dormitorios" and x["dormitorios"] not in (1, 2))


def barrios_en_mayoria(filas, prueba=None):
    """Cuenta en cuántas de las 12 variantes queda cada barrio en el mejor cuarto y devuelve los de la mayoría."""
    veces = Counter()
    for estancia in ESTANCIAS:
        for foto in FOTOS:
            por_barrio = defaultdict(list)
            for x in filas:
                if x["barrio"] != OTROS and entra(x, foto, estancia, prueba):
                    por_barrio[x["barrio"]].append(x[f"rent_{foto}_pct"])
            for minimo in MINIMOS:
                medianas = {b: statistics.median(v) for b, v in por_barrio.items() if len(v) >= minimo}
                if medianas:
                    corte = cuantil(medianas.values(), 0.75)
                    veces.update(b for b, m in medianas.items() if m >= corte)
    return sorted(b for b, k in veces.items() if k >= MAYORIA)


def calcular(filas):
    """Rehace la lista de barrios y las cifras de la recomendación."""
    grupo = barrios_en_mayoria(filas)
    aguantan = Counter()
    for p in PRUEBAS:
        aguantan.update(set(grupo) & set(barrios_en_mayoria(filas, p)))
    recomendados = sorted(b for b in grupo if aguantan[b] == len(PRUEBAS))
    cuatro_de_cinco = sorted(b for b in grupo if aguantan[b] == len(PRUEBAS) - 1)
    base = [x for x in filas if x["estancia_hasta_3"] and x["rent_sep_pct"]]
    pisos_rec = [x for x in base if x["barrio"] in recomendados and x["dormitorios"] <= 2]
    rango = []
    for foto in FOTOS:
        v = [x[f"rent_{foto}_pct"] for x in filas if x["barrio"] in recomendados and x["estancia_hasta_3"] and x[f"rent_{foto}_pct"]]
        rango.append(statistics.median(v))
    cfg = json.loads(PRECIOS_MERCADO.read_text(encoding="utf-8"))
    mercado = {}
    if {x["barrio"] for x in pisos_rec} <= set(cfg["oficial_2025"]):
        for f in cfg["fuentes"]:
            compra = [x["compra_eur"] * f["barrios"][x["barrio"]] / cfg["oficial_2025"][x["barrio"]] for x in pisos_rec]
            rent = [100 * x["ingreso_sep_eur"] / c for x, c in zip(pisos_rec, compra)]
            mercado[f["fuente"]] = {"compra": statistics.median(compra), "rent": statistics.median(rent)}
    return {"mercado": mercado, "pisos_base": len(base), "barrios_grupo": len(grupo), "grupo": grupo, "recomendados": recomendados, "cuatro_de_cinco": cuatro_de_cinco, "pisos_recomendados": len(pisos_rec),
            "rentabilidad": statistics.median(x["rent_sep_pct"] for x in pisos_rec),
            "compra": statistics.median(x["compra_eur"] for x in pisos_rec), "ingreso_anual": statistics.median(x["ingreso_sep_eur"] for x in pisos_rec),
            "rango_minimo": min(rango), "rango_maximo": max(rango)}


def es(valor, decimales=0):
    """Escribe un número a la española."""
    return f"{valor:,.{decimales}f}".replace(",", "#").replace(".", ",").replace("#", ".")


def en(valor, decimales=0):
    """Escribe un número a la inglesa."""
    return f"{valor:,.{decimales}f}"


def lista(nombres):
    """Une nombres con comas y una y griega final."""
    return " y ".join([", ".join(nombres[:-1]), nombres[-1]]) if len(nombres) > 1 else "".join(nombres)


def imprimir(r):
    """Imprime el resultado para quien ejecuta el repositorio."""
    print(f"Pisos analizados, datos del 17/09/2026: {es(r['pisos_base'])}")
    print(f"Barrios en la lista: {r['barrios_grupo']}")
    print(f"Barrios que siguen en la lista en las 5 repeticiones: {lista(r['recomendados'])}")
    print(f"Barrios que siguen en 4 de 5: {lista(r['cuatro_de_cinco'])}")
    print()
    print(f"Pisos de hasta 2 habitaciones en los barrios de {lista(r['recomendados'])}: {es(r['pisos_recomendados'])} anuncios")
    print(f"  Precio de compra, en mediana: {es(r['compra'])} €")
    print(f"  Ingreso al año, en mediana: {es(r['ingreso_anual'])} €")
    print(f"  Rentabilidad bruta: {es(r['rentabilidad'], 1)} %")
    for fuente, m in r["mercado"].items():
        print(f"  Con los precios que pide hoy {fuente}: compra de {es(m['compra'])} € y rentabilidad bruta de {es(m['rent'], 1)} %")
    print(f"  Rentabilidad de los pisos de esos barrios con estancia de hasta 3 noches, de cualquier tamaño, según la fecha del precio: de {es(r['rango_minimo'], 1)} % a {es(r['rango_maximo'], 1)} %")
    print()


def contra_indicadores(r, j):
    """Compara lo rehecho con lo que imprimió la cadena y devuelve las diferencias."""
    p2, rec, rango = j["preguntas"][1], j["recomendacion"], j["preguntas"][2]["rango_de_rentabilidad_de_recomendados"]
    pares = [("pisos de la base", r["pisos_base"], j["preguntas"][0]["poblacion"]["filas"], 0), ("pisos recomendados", r["pisos_recomendados"], rec["pisos"], 0),
             ("rentabilidad", r["rentabilidad"], rec["rentabilidad_pct"], TOLERANCIA),
             ("compra", r["compra"], rec["compra_eur"], 1), ("ingreso anual", r["ingreso_anual"], rec["ingreso_anual_eur"], 1),
             ("rango mínimo", r["rango_minimo"], rango["minimo"], TOLERANCIA), ("rango máximo", r["rango_maximo"], rango["maximo"], TOLERANCIA)]
    for f in rec["precio_de_mercado"]["fuentes"]:
        m = r["mercado"].get(f["fuente"], {"compra": 0, "rent": 0})
        pares += [(f"compra con {f['fuente']}", m["compra"], f["compra_mediana_eur"], 1), (f"rentabilidad con {f['fuente']}", m["rent"], f["rentabilidad_mediana_pct"], TOLERANCIA)]
    fallos = [f"{n}: {a} frente a {b}" for n, a, b, tol in pares if abs(a - b) > tol]
    for nombre, clave in (("grupo", "grupo"), ("recomendados", "recomendados"), ("4 de 5 veces", "cuatro_de_cinco")):
        if sorted(p2[clave]) != r[clave]:
            fallos.append(f"{nombre}: {r[clave]} frente a {sorted(p2[clave])}")
    return fallos


def contra_readme(r):
    """Comprueba que las dos versiones de la portada llevan las cifras rehechas, cada uno con su formato."""
    cifras = {"README.md": [es(r["pisos_base"]), es(r["pisos_recomendados"]), es(r["rentabilidad"], 1) + " %", es(r["compra"]) + " €", es(r["ingreso_anual"]) + " €"],
              "README.en.md": [en(r["pisos_base"]), en(r["pisos_recomendados"]), en(r["rentabilidad"], 1) + "%", "€" + en(r["compra"]), "€" + en(r["ingreso_anual"])]}
    for m in r["mercado"].values():
        cifras["README.md"] += [es(m["compra"]) + " €", es(m["rent"], 1) + " %"]
        cifras["README.en.md"] += ["€" + en(m["compra"]), en(m["rent"], 1) + "%"]
    fallos = []
    for nombre, lista in cifras.items():
        texto = (CASO / nombre).read_text(encoding="utf-8")
        fallos += [f"{nombre} no lleva {c}" for c in lista if c not in texto]
    return fallos


def comprobar(r):
    """Reúne las diferencias con la cadena y con los README."""
    return contra_indicadores(r, json.loads(INDICADORES.read_text(encoding="utf-8"))) + contra_readme(r)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--comprobar", action="store_true", help="compara con informes/indicadores.json y con los dos README")
    o = a.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    resultado = calcular(leer())
    imprimir(resultado)
    if o.comprobar:
        fallos = comprobar(resultado)
        for f in fallos:
            print(f"NO COINCIDE {f}")
        print("Estas cifras coinciden con las del análisis y con las de esta página, en español y en inglés." if not fallos else f"{len(fallos)} cifras no coinciden.")
        sys.exit(1 if fallos else 0)
