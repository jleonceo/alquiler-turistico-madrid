"""Informe final del caso para la Dirección de Inversiones: un HTML de páginas de pantalla con su anexo.

Lee informes/indicadores.json, que tiene que ser más nuevo que scripts/indicadores.py, data/processed/barrios_poligonos_corregido.parquet
y data/raw/externos/ape_00_01.json, estos dos solo para el mapa. No calcula ninguna cifra de negocio y no importa ningún script
del caso que ejecute algo al importarse. Deja informes/informe_final.html, informes/informe_final_graficos.csv con las cifras de
los gráficos e informes/informe_final_rastro.json con la clave de cada cifra. Usa assets/informe.py y assets/graficos.py sin cambiarlos.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/informe_final.py
Opciones: --indicadores <json>, --salida <carpeta>. Las usa tests/probar_informe_final.py.
"""
import argparse
import csv
import datetime
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd
import shapely

import cifras_informes as ci
import mapa_barrios
from cifras_informes import CON_AVISO, FIRMES, ORDENA, PLANTA, Q2, Q3, REC, UN_ANO, exigir, ficha

# informe.py y graficos.py viven en assets/; cifras_informes ya la puso en la ruta de importación.
import graficos as g  # noqa: E402
from informe import Informe  # noqa: E402

# =====================================================================================================================
# 1. Configuración
# =====================================================================================================================

PREGUNTAS = {1: "¿Qué tipo de piso rinde más?", 2: "¿En qué barrios conviene buscarlo, fuera del centro histórico?", 3: "¿Con qué riesgo?"}
TITULO = "Dónde buscar pisos turísticos en Madrid"
MAX_PALABRAS = 140  # T2 pide unas 120 por página; se para un poco por encima
FUENTE_PISOS = "Inside Airbnb, foto del 17/09/2026; Ayuntamiento de Madrid, precio de 2025"
Q1 = "preguntas[0]"
DORM = f"{Q1}.dormitorios"
SUP = f"{Q1}.sensibilidad_superficie"
NOMBRE_DORM = {"0": "Estudio", "1": "1 habitación", "2": "2 habitaciones", "3": "3 habitaciones"}
NOMBRE_PRUEBA = {"sin_temporada": "temporada", "sin_anfitriones_grandes": "operadores grandes", "sin_cotizaciones_lejanas": "cotización lejana", "solo_1_y_2_dormitorios": "habitaciones", "sin_ocupacion_como_cero": "pisos sin ocupación"}


# =====================================================================================================================
# 2. Ayudas
# =====================================================================================================================

class Apuntes:
    """Guarda cada cifra de cada gráfico para el CSV que acompaña al informe (F3)."""

    def __init__(self):
        """Empieza sin filas."""
        self.filas = []

    def apuntar(self, pagina, grafico, grupos, medida, cifras, unidad):
        """Apunta las cifras de un gráfico, una por grupo."""
        self.filas += [(pagina, grafico, str(a), medida, g.numero(b, 2), unidad) for a, b in zip(grupos, cifras)]

    def escribir(self, ruta):
        """Escribe el CSV con punto y coma, coma decimal y marca de UTF-8."""
        with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["pagina", "grafico", "grupo", "medida", "cifra", "unidad"])
            w.writerows(self.filas)


def texto_pagina(p):
    """Texto visible de una página: título, cifras clave, párrafos, tablas y títulos de gráfico, sin los dibujos."""
    bloques = re.sub(r"<svg.*?</svg>", " ", " ".join(b["html"] for b in p.bloques), flags=re.S)
    cifras = " ".join(" ".join(x) for x in p.cifras)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", f"{p.titulo} {cifras} {bloques}"))).strip()


def palabras_propias(p):
    """Palabras del bloque de texto de una página (T2): solo los párrafos."""
    parrafos = " ".join(b["html"] for b in p.bloques if b["clase"] == "parrafo")
    return ci.palabras(re.sub(r"<[^>]+>", " ", parrafos))


def numero_celda(c, clave, decimales=1):
    """Lee una cifra para una celda de tabla o un gráfico, apuntada con su clave, y la devuelve como número."""
    c.num(clave, decimales)
    return float(c.dato(clave))


def leer_mapa():
    """Lee los polígonos de los barrios y el límite del centro histórico."""
    t = pd.read_parquet(ci.CASO / "data" / "processed" / "barrios_poligonos_corregido.parquet")
    poligonos = dict(zip(t["barrio"], shapely.from_wkb(t["geometria_wkb"].to_list())))
    datos = json.loads((ci.CASO / "data" / "raw" / "externos" / "ape_00_01.json").read_text(encoding="utf-8"))
    anillos = datos["features"][0]["geometry"]["rings"]
    return poligonos, shapely.Polygon(anillos[0], anillos[1:])


def comprobar_frases(c):
    """Comprueba las frases que solo dice este informe, además de la lectura común."""
    fichas = {f["barrio"]: f for f in c.dato(f"{Q3}.fichas_del_grupo")}
    exigir(c.dato(f"{DORM}.primero_en_euros") == "2" and c.dato(f"{DORM}.no_se_distinguen_del_primero_en_euros") == ["3"], "en euros encabezan los de 2 habitaciones, que no se distinguen de los de 3")
    exigir(c.dato(f"{DORM}.tabla[grupo=3].frente_al_total") == "por debajo", "los de 3 habitaciones quedan por debajo de la base de decisión")
    exigir(fichas["Ventas"]["rango_entre_fotos_puntos"] == max(fichas[b]["rango_entre_fotos_puntos"] for b in FIRMES), "entre los firmes, Ventas es la que más cambia con la foto")
    r = {(x["foto"], x["descuento"]): x["mediana"] for x in c.dato(f"{Q3}.rango_de_rentabilidad_del_grupo_firme.combinaciones")}
    por_foto = max(r[("marzo", True)], r[("junio", True)], r[("septiembre", True)]) - min(r[("marzo", True)], r[("junio", True)], r[("septiembre", True)])
    exigir(all(r[(f, True)] - r[(f, False)] > por_foto for f in ("marzo", "junio", "septiembre")), "el descuento mueve el nivel más que la foto")
    orden = sorted(fichas, key=lambda b: -fichas[b]["rango_entre_fotos_puntos"])
    exigir(set(orden[:2]) == set(CON_AVISO), "Casco Histórico de Vallecas y Opañel son los que más se mueven")
    exigir(all(len(c.dato(f"{Q2}.pruebas.barrios.{b}.no_aguanta")) >= 2 for b in c.dato(f"{Q2}.segunda_linea")), "los de segunda línea caen en dos pruebas o más")


# =====================================================================================================================
# 3. Páginas
# =====================================================================================================================

def pagina_resumen(inf, c):
    """Resumen: abre con la recomendación y los límites que pesan, sus cifras clave y la tabla de las tres preguntas."""
    rango = f"{Q3}.rango_de_rentabilidad_del_grupo_firme"
    p = inf.pagina("Buscar hasta 2 habitaciones en Ventas, Numancia y San Diego", "resumen", panel="Resumen", columnas=False)
    p.cifra_clave(c.pct(f"{REC}.rentabilidad_sin_descuento_pct"), "Rentabilidad sin descuento", "Firmes, hasta 2 habitaciones")
    p.cifra_clave(c.num(f"{REC}.pisos"), "Anuncios en Airbnb", "No son pisos en venta")
    p.cifra_clave(c.eur(f"{REC}.compra_sin_descuento_eur"), "Compra sin descuento", f"Con descuento, {c.eur(REC + '.compra_con_descuento_eur')}")
    p.cifra_clave(c.eur(f"{REC}.ingreso_anual_eur"), "Ingreso anual por piso", "Mediana, sin gastos")
    p.texto(f"Con el 25 % de descuento rinden {c.pct(REC + '.rentabilidad_con_descuento_pct')}, y todos los firmes van de {c.pct(rango + '.minimo')} a {c.pct(rango + '.maximo')} según la foto: no es beneficio. "
            f"Numancia supera la mediana de la base, y Ventas y San Diego no se distinguen de ella. San Diego queda por debajo de Casco Histórico de Vallecas y de Opañel, que dependen de operadores grandes, los anfitriones de 10 anuncios o más, el {c.pct(Q2 + '.operadores_grandes.con_aviso_pct', 0)} de sus anuncios.",
            f"Es una lista de dónde buscar: no dice si se puede comprar. Valoraciones empieza por bajos y primeras plantas con acceso independiente: {c.num(PLANTA + '.licencias')} de las {c.num(PLANTA + '.de')} licencias incluyen planta baja, {c.num(PLANTA + '.firmes.licencias')} de {c.num(PLANTA + '.firmes.de')} en los firmes. "
            "El ingreso de un bajo no se conoce. Fuera del centro histórico, en el nivel B de la zona 1, cabe hospedaje en planta baja, inferior a la baja y primera. Qué norma rige en cada barrio no se puede saber: hay que preguntarlo en el Ayuntamiento.")
    p.tabla(["Pregunta", "Respuesta", "Qué se recomienda"],
            [["1. Tipo de piso", "Hasta 2 habitaciones, sin ganador", "Pedir su superficie real"],
             ["2. Barrios", "Firmes: estables, no mejores", "Validar planta y norma"],
             ["3. Riesgo", "Los firmes dependen del tope", "Repetir con la foto siguiente"]],
            fuente="Inside Airbnb, licencia CC BY 4.0; Ayuntamiento de Madrid")


def paginas_pregunta_1(inf, c, ap):
    """Pregunta 1: los pisos de hasta 2 habitaciones y el peso del supuesto de superficie."""
    t = "Hasta 2 habitaciones rinden más que 3 en las combinaciones de m² probadas"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[1], panel="Habitaciones")
    p.cifra_clave(c.eur(f"{DORM}.tabla[grupo=2].euros_al_ano"), "Ingreso estimado al año, 2 habitaciones", "Mediana de la base de decisión")
    p.cifra_clave(c.eur(f"{DORM}.tabla[grupo=1].euros_al_ano"), "Ingreso estimado al año, 1 habitación", "Mediana de la base de decisión")
    grupos = ["1", "2", "0", "3"]
    clave = lambda x, campo: f"{DORM}.tabla[grupo={x}].{campo}"
    etiquetas = [f"{NOMBRE_DORM[x]}, {c.num(clave(x, 'pisos'))} anuncios" for x in grupos]
    valores = [numero_celda(c, clave(x, "rentabilidad_mediana_pct")) for x in grupos]
    bajos, altos = [numero_celda(c, clave(x, "ic_bajo")) for x in grupos], [numero_celda(c, clave(x, "ic_alto")) for x in grupos]
    ref = float(c.dato(f"{Q1}.referencia.valor"))
    svg = g.barras_con_intervalo(etiquetas, valores, bajos, altos, referencia=ref, rotulo_referencia="Base de decisión", decimales=1, unidad=" %", intervalo="intervalo de confianza del 95 %", ancho=560, destacar=[etiquetas[3]], medida="rentabilidad bruta")
    ap.apuntar(len(inf.paginas), t, grupos, "rentabilidad bruta mediana", valores, "%")
    ap.apuntar(len(inf.paginas), t, ["base de decisión"], "referencia", [ref], "%")
    p.texto("Valoraciones puede dejar fuera los pisos de 3 habitaciones.",
            "En ingreso al año encabezan los de 2 habitaciones, que no se distinguen de los de 3. Es ingreso estimado, antes de gastos.",
            f"La ventaja de 1 habitación sobre 2 no se repite por zonas: gana en {c.num(Q1 + '.por_segmentos.distritos_donde_1_supera_a_2')} de {c.num(Q1 + '.por_segmentos.distritos_comparables_1_y_2')} distritos. "
            f"El tipo de inmueble apenas separa: {c.num(Q1 + '.tipo_de_inmueble.tabla[grupo=Entire rental unit].pisos')} de los {c.num(Q1 + '.poblacion.filas')} pisos son apartamentos de alquiler.")
    p.grafico(svg, "Los pisos de 3 habitaciones quedan por debajo de la base", f"Rentabilidad bruta mediana con descuento, en %. Fuente: {FUENTE_PISOS}")

    t = "El orden entre estudio, una y dos habitaciones depende de los m²"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[1], panel="Supuesto de m²", columnas=False)
    p.cifra_clave(c.num(f"{SUP}.combinaciones_que_cambian"), "Combinaciones en que cambian los tipos que se dan", f"De {c.cuantos(SUP + '.combinaciones')} probadas")
    p.texto("No se da un ganador entre estudio, una y dos habitaciones. Los de 3 no llegan a ninguno de ellos. Hasta conocer la superficie real, valoraciones trata los tres tipos por igual. Se dan los tipos que no se distinguen del primero.")
    filas = []
    for i, x in enumerate(c.dato(f"{SUP}.combinaciones")):
        base = f"{SUP}.combinaciones[{i}]"
        m2 = " · ".join(c.num(f"{base}.superficies.{k}") for k in ("0", "1", "2"))
        se_dan = ", ".join(NOMBRE_DORM[k].lower() for k in x["se_dan"])
        filas.append([m2] + [numero_celda(c, f"{base}.medianas.{k}") for k in ("0", "1", "2", "3")] + [se_dan])
    p.tabla(["m² de estudio · 1 · 2", "Estudio (%)", "1 habitación (%)", "2 habitaciones (%)", "3 habitaciones (%)", "Tipos que se dan"], filas, fuente=f"{FUENTE_PISOS}. Rentabilidad bruta mediana con descuento", decimales=[0, 1, 1, 1, 1, 0])


def paginas_pregunta_2(inf, c, ap):
    """Pregunta 2: el mapa, el orden dentro del grupo, las pruebas y el peso del precio de compra."""
    poligonos, limite = leer_mapa()
    clases = c.dato(f"{Q2}.clases")
    t = "Tres barrios aguantan las cinco pruebas y dos aguantan cuatro"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[2], panel="Mapa de barrios")
    p.texto("Valoraciones puede concentrar la búsqueda en los barrios firmes y seguir por los dos con aviso, que caen al quitar a los operadores grandes.",
            f"Una variante repite el cálculo con otra estancia, otro mínimo de anuncios u otra foto de precio. Los {c.cuantos(Q2 + '.grupo')} barrios del grupo quedan en el mejor cuarto de rentabilidad bruta en más de 6 de 12 variantes.",
            f"Una prueba repite esas variantes quitando algo, y son firmes los que aguantan las cinco. Los {c.cuantos(Q2 + '.segunda_linea')} de segunda línea quedan para después.")
    p.grafico(mapa_barrios.mapa(poligonos, clases, limite, ci.barrio), "Los firmes y los con aviso quedan al sur y al este del centro", f"Barrios por clase, foto del 17/09/2026. Fuente: {FUENTE_PISOS}")
    ap.apuntar(len(inf.paginas), t, sorted(clases), "clase de barrio", [float(len(c.dato(f"{Q2}.pruebas.barrios.{b}.aguanta"))) for b in sorted(clases)], "pruebas que aguanta")

    t = "El orden dentro del grupo no está cerrado"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[2], panel="Orden del grupo")
    orden = FIRMES + CON_AVISO + sorted(c.dato(f"{Q2}.segunda_linea"))
    etiquetas = [f"{ci.barrio(b)}, {c.num(ficha(b, 'pisos'))} anuncios" for b in orden]
    valores = [numero_celda(c, ficha(b, "rentabilidad_mediana_pct")) for b in orden]
    bajos, altos = [numero_celda(c, ficha(b, "ic_bajo")) for b in orden], [numero_celda(c, ficha(b, "ic_alto")) for b in orden]
    ref = float(c.dato(f"{Q2}.mediana_de_toda_la_base"))
    svg = g.barras_con_intervalo(etiquetas, valores, bajos, altos, referencia=ref, rotulo_referencia="Base de decisión", decimales=1, unidad=" %", intervalo="intervalo de confianza del 95 %", ancho=640, medida="rentabilidad bruta")
    ap.apuntar(len(inf.paginas), t, orden, "rentabilidad bruta mediana", valores, "%")
    distinguen = sum(1 for x in c.dato(f"{Q3}.pares_dentro_del_grupo") if x["se_distinguen"])
    p.texto(f"La lista es un grupo y no un ranking: de {c.cuantos(Q3 + '.pares_dentro_del_grupo')} parejas de barrios solo se distinguen {ci.numero(distinguen)}.",
            f"No se distingue significa que la diferencia puede ser cero con un intervalo de confianza del 95 %. La mediana conjunta de los firmes, {c.pct(Q3 + '.rentabilidad_del_grupo_firme.mediana')} con descuento, no es la media de sus barrios.")
    c.apuntadas.setdefault(ci.numero(distinguen), set()).add(f"recuento de se_distinguen en {Q3}.pares_dentro_del_grupo")
    p.grafico(svg, "Casi ninguna pareja de barrios del grupo se distingue", f"Rentabilidad bruta mediana con descuento, en %. Fuente: {FUENTE_PISOS}")

    t = "Los firmes son los únicos que no caen en ninguna prueba"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[2], panel="Las cinco pruebas", columnas=False)
    p.texto("Los barrios con aviso dependen de operadores grandes, y los de segunda línea caen en dos pruebas o más. Puerta del Ángel está en el grupo y no aguanta ninguna prueba.")
    filas = []
    for b in orden:
        no = c.dato(ficha(b, "pruebas_que_no_aguanta"))
        filas.append([ci.barrio(b), c.dato(ficha(b, "clase")), numero_celda(c, f"{Q2}.pruebas.barrios.{b}.cuantas", 0), ", ".join(NOMBRE_PRUEBA[x] for x in no) or "ninguna", numero_celda(c, ficha(b, "variantes_en_el_mejor_cuarto"), 0)])
    p.tabla(["Barrio", "Clase", "Pruebas que aguanta", "En cuáles cae", "Variantes de 12"], filas, fuente=FUENTE_PISOS, decimales=[0, 0, 0, 0, 0])

    baratos = f"{Q2}.referencia_baratos.comparados"
    t = "Elegir solo por m² barato no se distingue de la lista"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[2], panel="Precio de compra")
    coinciden = c.dato(f"{baratos}.coinciden")
    p.cifra_clave(c.pct(f"{ORDENA}.m2_baratos.mediana_pct"), "Barrios de m² más barato", f"Los {c.num(baratos + '.de')} más baratos, con descuento")
    p.cifra_clave(c.pct(f"{Q3}.rentabilidad_del_grupo_firme.mediana"), "Grupo firme", "Mediana conjunta, con descuento")
    p.cifra_clave(c.pct(f"{ORDENA}.grupo.mediana_pct"), "Grupo de la lista", "Mediana conjunta, con descuento")
    p.texto(f"Valoraciones no gana rentabilidad con la lista frente a elegir por precio: {c.num(baratos + '.cuantos')} de los {c.num(baratos + '.de')} barrios coinciden y las tres cifras no se distinguen. La lista aporta saber qué barrios aguantan las pruebas.",
            f"Entre los {c.num(ORDENA + '.barrios')} barrios, la rentabilidad se asocia más con la ocupación ({c.num(ORDENA + '.rentabilidad_con_ocupacion', 2)}) que con el m² ({c.num(ORDENA + '.rentabilidad_con_m2', 2)}), en una escala de -1 a 1, y la ocupación es la cifra más débil del caso. Es una asociación: no dice por qué esos barrios rinden más.")
    p.tabla(["Barrio del grupo", "Clase", "Entre los de m² más barato"], [[ci.barrio(b), c.dato(ficha(b, "clase")), "sí" if b in coinciden else "no"] for b in orden], fuente="Ayuntamiento de Madrid, precio de 2025; Inside Airbnb, foto del 17/09/2026", texto=False)


def paginas_pregunta_3(inf, c, ap):
    """Pregunta 3: el riesgo de cada barrio, lo que se mueve entre fotos y el nivel de la rentabilidad."""
    orden = FIRMES + CON_AVISO + sorted(c.dato(f"{Q2}.segunda_linea"))
    t = "Los tres firmes dependen del tope y su cuartil bajo supera el de la base"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[3], panel="Riesgo por barrio", columnas=False)
    p.texto(f"Valoraciones tiene que mirar cada firme piso a piso. Un barrio depende del tope si sale del grupo al quitar los pisos que llegan a 255 días; Opañel, con el {c.pct(ficha('Opañel', 'parte_en_el_tope_pct'), 0)} de sus pisos en el tope, no depende. "
            f"En uno de cada cuatro anuncios la rentabilidad no llega a {c.pct(Q2 + '.cuartil_bajo_de_toda_la_base', 2)}, el cuartil bajo de toda la base, y los tres firmes quedan por encima. "
            f"Sin ocupación queda el {c.pct(Q3 + '.pisos_fuera_sin_ocupacion.pct')} de los pisos fuera del centro.")
    filas = [[ci.barrio(b), c.dato(ficha(b, "clase")), numero_celda(c, ficha(b, "pisos"), 0), numero_celda(c, ficha(b, "cuartil_bajo_pct")), numero_celda(c, ficha(b, "parte_en_el_tope_pct")), numero_celda(c, ficha(b, "pisos_fuera_sin_ocupacion_pct", 3))] for b in orden]
    p.tabla(["Barrio", "Clase", "Anuncios", "Cuartil bajo (%)", "Pisos en el tope (%)", "Pisos sin ocupación (%)"], filas, fuente=f"{FUENTE_PISOS}. Sin ocupación: parte de los pisos fuera del centro", decimales=[0, 0, 0, 1, 1, 1])

    t = "Entre los firmes, Ventas es la que más cambia con la foto de precio"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[3], panel="Cambio entre fotos")
    valores = [numero_celda(c, ficha(b, "rango_entre_fotos_puntos", 3)) for b in orden]
    nombres = [ci.barrio(b) for b in orden]
    svg = g.barras_ordenadas(nombres, {"": valores}, decimales=1, unidad=" puntos", ancho=560, medida="rango entre fotos")
    ap.apuntar(len(inf.paginas), t, orden, "rango entre fotos", valores, "puntos")
    p.texto(f"La foto siguiente puede mover el nivel de un barrio, y por eso la lista se repite antes de comprar.",
            "Marzo y junio solo cubren los anuncios que siguen en septiembre con el mismo número, y cada foto mantiene la ocupación de septiembre.")
    p.grafico(svg, "Casco Histórico de Vallecas y Opañel son los que más se mueven", f"Rango de la mediana entre tres fotos, en puntos. Fuente: {FUENTE_PISOS}")

    t = "El descuento del 25 % mueve el nivel más que la foto de precio"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[3], panel="Nivel de la rentabilidad")
    rango = f"{Q3}.rango_de_rentabilidad_de_firmes_y_con_aviso"
    fotos = ["marzo", "junio", "septiembre"]
    r = {(x["foto"], x["descuento"]): x["mediana"] for x in c.dato(f"{Q3}.rango_de_rentabilidad_del_grupo_firme.combinaciones")}
    combinaciones = [(f, d) for f in fotos for d in (True, False)]
    nombres = [f"{f.capitalize()}, {'con' if d else 'sin'} descuento" for f, d in combinaciones]
    valores = [r[x] for x in combinaciones]
    svg = g.barras_ordenadas(nombres, {"": valores}, decimales=1, unidad=" %", ancho=560, ordenar=False, medida="rentabilidad bruta")
    ap.apuntar(len(inf.paginas), t, nombres, "rentabilidad bruta mediana del grupo firme", valores, "%")
    p.texto("El descuento es un supuesto y sube la cifra sin que el piso rinda más, de modo que la cifra sin descuento es la que hay que tener delante al negociar.",
            f"Con los dos barrios con aviso, el rango llega hasta {c.pct(rango + '.maximo')}. Ninguna de estas cifras descuenta gastos, impuestos ni comisiones.")
    p.grafico(svg, "El grupo firme baja más sin descuento que de una foto a otra", f"Rentabilidad bruta mediana del grupo firme, en %, 2026. Fuente: {FUENTE_PISOS}")

    t = "Con anuncios de un año o más, San Diego se sostiene menos"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[3], panel="Anuncios nuevos", columnas=False)
    p.texto(f"La ocupación cuenta reseñas de 12 meses y un anuncio nuevo sale bajo. Con los {c.num(UN_ANO + '.pisos')} anuncios de un año o más, entre {c.num(UN_ANO + '.barrios_comparados')} barrios con 30 o más, Numancia queda {c.num(ci.puesto('Numancia'))}.ª, Ventas {c.num(ci.puesto('Ventas'))}.ª y San Diego {c.num(ci.puesto('San Diego'))}.ª, fuera del mejor cuarto. San Diego se sostiene menos con este corte.")
    p.tabla(["Barrio", "Anuncios de un año o más", "Rentabilidad bruta con descuento (%)", "Puesto"], [[b, numero_celda(c, f"{UN_ANO}.barrios[barrio={b}].pisos", 0), numero_celda(c, f"{UN_ANO}.barrios[barrio={b}].mediana_pct"), numero_celda(c, ci.puesto(b), 0)] for b in FIRMES], fuente=FUENTE_PISOS, decimales=[0, 0, 1, 0])


def paginas_cierre(inf, c):
    """Límites y decisiones propuestas: una tabla cada una, en el orden de lo que hay en juego."""
    p = inf.pagina("Lo que puede cambiar estas conclusiones", "limites", panel="Límites")
    p.tabla(["Decisión a la que afecta", "Límite"], [
        ["Comprar un piso", "Estar fuera del centro histórico no significa que se pueda comprar para este uso. Planta, acceso y norma se comprueban en el Ayuntamiento. Esto no es asesoramiento jurídico."],
        ["Dónde buscar", "La ocupación es una estimación con tope de 255 días, y en la parte alta no ordena."],
        ["Dónde buscar", "Contar además los pisos sin ocupación ni precio dejaría solo a Ventas como firme."],
        ["Qué tipo buscar", "La superficie es un supuesto de valoraciones, y el dato oficial es igual para todos los pisos del barrio."],
        ["Cuánto rinde", "El precio de compra es el declarado en 2025, y el descuento del 25 % es un supuesto sin apoyo en los datos. La inversión total no consta."],
        ["Casco Histórico de Vallecas", "Airbnb junta en él lo que el Ayuntamiento separa, y su precio oficial puede no representar todo el barrio."],
        ["Por qué ocurre", "Son asociaciones sobre una foto: no dicen por qué un barrio rinde más. El calendario no distingue reservado de bloqueado."],
    ], fuente="reglas del caso y datos de la foto del 17/09/2026")

    p = inf.pagina("Decisiones propuestas", "decision", panel="Decisiones propuestas")
    p.texto("La Dirección de Inversiones tiene que aprobar estas tres acciones. La fecha de ninguna consta. La primera empieza por bajos y primeras plantas.")
    p.tabla(["Decisión", "Quién", "Plazo", "Por qué"], [[a["nombre"], a["quien"], a["cuando"][0].upper() + a["cuando"][1:], f"{a['por_que']} Página: {a['pagina']}."] for a in ci.acciones(c)], fuente="informe ejecutivo y páginas de este informe")


def paginas_anexo(inf, c):
    """Anexo: método de cada pregunta, fuentes de cada cifra y datos personales."""
    p = inf.pagina("Método de cada pregunta", "anexo", panel="Método", columnas=False)
    p.texto("Rentabilidad bruta: ingreso anual estimado entre precio de compra. Ocupación: días al año que estima Inside Airbnb, con tope de 255. Precio de compra: superficie por precio oficial del m² del barrio, por 0,75 con el descuento del 25 %.",
            "Base de decisión: pisos fuera del centro histórico con precio entre 20 y 1.000 €, hasta 8 huéspedes, ocupación mayor que cero y estancia mínima de hasta 3 noches.",
            f"Pregunta 1: medianas por habitaciones con 30 pisos o más, e intervalo de confianza del 95 % (el rango en que probablemente está la diferencia), con 2.000 remuestreos y semilla 63. El supuesto de m² se movió en las {c.cuantos(SUP + '.combinaciones')} combinaciones de sus extremos.",
            "Pregunta 2: mejor cuarto en más de 6 de 12 variantes; cada prueba repite esas variantes y cambia una cosa.",
            "Pregunta 3: recuento, cuartil bajo, parte en el tope, parte sin ocupación y rango entre fotos, por barrio.")
    # Contexto del mercado: la oferta de cada foto, sin comparar causas.
    oferta = [[f"{ci.fecha_es(x['foto'])}", numero_celda(c, f"evolucion_oferta.fotos[foto={x['foto']}].anuncios", 0), numero_celda(c, f"evolucion_oferta.fotos[foto={x['foto']}].pisos_completos", 0)] for x in c.dato("evolucion_oferta.fotos")]
    p = inf.pagina("Contexto del mercado", "anexo", panel="Contexto", columnas=False)
    p.tabla(["Foto de Inside Airbnb", "Anuncios", "Pisos"], [["Junio de 2025", numero_celda(c, "evolucion_oferta.junio_2025.anuncios", 0), None]] + oferta, fuente="Inside Airbnb. Un cambio entre fotos no dice por qué ocurre. Junio de 2025 es una foto de Inside Airbnb de la que solo consta el recuento", decimales=[0, 0, 0])
    p.texto(f"Las reseñas alcanzan su índice más alto en junio, {c.num('estacionalidad.indice_mas_alto', 2)}, y el más bajo en febrero, {c.num('estacionalidad.indice_mas_bajo', 2)}, en {c.num('estacionalidad.meses')} meses completos. No todas las estancias dejan reseña.",
            f"El registro municipal tiene {c.num('licencias_y_registro.totales.licencias')} licencias y {c.num('licencias_y_registro.totales.viviendas_con_licencia')} viviendas. Una licencia no se puede unir a un anuncio: solo se cuenta por barrio.")
    p = inf.pagina("Fuentes de cada cifra", "anexo", panel="Fuentes", columnas=False)
    p.tabla(["Cifra", "Fichero de informes/", "Fecha de los datos"], [
        ["Todas las de este informe", "indicadores.json", ci.fecha_es(c.dato("fecha_datos"))],
        ["Ruta de cada cifra", "informe_final_rastro.json", ci.fecha_es(c.dato("fecha_datos"))],
        ["Cifras de cada gráfico", "informe_final_graficos.csv", ci.fecha_es(c.dato("fecha_datos"))]], fuente="carpeta informes/ del caso", texto=False)
    p.texto(*ci.ATRIBUCION, "Plan RESIDE, BOCM 226 de 22/09/2025.")
    p = inf.pagina("Datos personales", "anexo", panel="Datos personales", columnas=False)
    p.texto("Qué traía el caso. Los anuncios traían columnas que identifican al anfitrión, enlaces, fotos, nombre, descripción y número de licencia. Las reseñas traían texto, nombre y código de quien reseña. Las licencias traían dirección, punto y números de expediente.",
            "Qué se hizo. Se suprimieron esas columnas, y del número de licencia queda solo su tipo. Es una supresión, sin seudonimización.",
            "Quién y cuándo. La persona responsable del proyecto lo decidió el 06/11/2026, antes de que los datos entraran en el caso. Quien analizó nunca vio los originales.",
            "Lo que queda. El número del anuncio, con el que se llega a su página pública, las coordenadas, desplazadas hasta 150 m, y el recuento de anuncios por anfitrión, que no dice quién es. Por eso los resultados se dan por barrio y tipo de piso, con un mínimo de 30 pisos, y ninguno decide sobre una persona.")


# =====================================================================================================================
# 4. Principal
# =====================================================================================================================

def principal():
    """Lee, comprueba, monta en el orden de S2, pasa las guardias y escribe."""
    a = argparse.ArgumentParser()
    a.add_argument("--indicadores", default=str(ci.INDICADORES))
    a.add_argument("--salida", default=str(ci.CASO / "informes"))
    o = a.parse_args()
    c = ci.Cifras(o.indicadores)
    if o.indicadores == str(ci.INDICADORES) and ci.INDICADORES.stat().st_mtime < (ci.CASO / "scripts" / "indicadores.py").stat().st_mtime:
        raise SystemExit("informes/indicadores.json es más viejo que scripts/indicadores.py: lanza antes el script")
    ci.comprobar_lectura(c)
    comprobar_frases(c)

    inf = Informe(TITULO, f"Datos a {ci.fecha_es(c.dato('fecha_datos'))}")
    ap = Apuntes()
    pagina_resumen(inf, c)
    paginas_pregunta_1(inf, c, ap)
    paginas_pregunta_2(inf, c, ap)
    paginas_pregunta_3(inf, c, ap)
    paginas_cierre(inf, c)
    paginas_anexo(inf, c)

    # Se valida antes de guardar: informe.py comprueba S3 y D7 al pedir el HTML; aquí, palabras, jerga y rastro.
    documento = inf.html()
    paginas = [{"id": p.id, "titulo": p.titulo, "tipo": p.tipo, "palabras": palabras_propias(p), "alto_estimado": p.alto(), "cifras_clave": len(p.cifras)} for p in inf.paginas]
    largas = [(x["titulo"], x["palabras"]) for x in paginas if x["tipo"] == "pregunta" and x["palabras"] > MAX_PALABRAS]
    if largas:
        raise SystemExit(f"Páginas con más de {MAX_PALABRAS} palabras: {largas}")
    visible = " ".join(texto_pagina(p) for p in inf.paginas)
    ci.sin_jerga(visible)
    sueltas = ci.cifras_sin_rastro(visible, list(c.apuntadas))
    if sueltas:
        raise SystemExit(f"Cifras sin clave en el texto: {sueltas}")

    salida = Path(o.salida)
    (salida / "informe_final.html").write_text(documento, encoding="utf-8")
    ap.escribir(salida / "informe_final_graficos.csv")
    rastro = {"fecha_datos": c.dato("fecha_datos"), "fecha_ejecucion": datetime.datetime.now().isoformat(timespec="seconds"), "script": "scripts/informe_final.py", "indicadores": "informes/indicadores.json",
              "indicadores_fecha_ejecucion": c.dato("fecha_ejecucion"), "lector": "Dirección de Inversiones", "paginas": paginas, "acciones": ci.acciones(c), "rastro": c.rastro(), "constantes": ci.CONSTANTES}
    (salida / "informe_final_rastro.json").write_text(json.dumps(rastro, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in paginas:
        print(f"{x['id']:4} {x['tipo']:9} {x['alto_estimado']:4} px {x['palabras']:4} palabras  {x['titulo']}")
    print(f"Sin el anexo: {sum(1 for x in paginas if x['tipo'] != 'anexo')} páginas; con él: {len(paginas)}")


if __name__ == "__main__":
    principal()
