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
FUENTE_PISOS = "Inside Airbnb, datos del 17/09/2026; Ayuntamiento de Madrid, precio de 2025"
Q1 = "preguntas[0]"
DORM = f"{Q1}.dormitorios"
SUP = f"{Q1}.sensibilidad_superficie"
NOMBRE_DORM = {"0": "Estudio", "1": "1 habitación", "2": "2 habitaciones", "3": "3 habitaciones"}
NOMBRE_PRUEBA = {"sin_temporada": "pisos de temporada", "sin_anfitriones_grandes": "anfitriones con 10 anuncios o más", "sin_cotizaciones_lejanas": "precios a más de 60 días", "solo_1_y_2_dormitorios": "solo 1 y 2 habitaciones", "sin_ocupacion_como_cero": "pisos sin días estimados como cero"}


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
    exigir(c.dato(f"{DORM}.tabla[grupo=3].frente_al_total") == "por debajo", "los de 3 habitaciones rinden menos que la mediana de todos los pisos")
    exigir(fichas["Ventas"]["rango_entre_fotos_puntos"] == max(fichas[b]["rango_entre_fotos_puntos"] for b in FIRMES), "entre los recomendados, Ventas es la que más cambia con la fecha del precio")
    orden = sorted(fichas, key=lambda b: -fichas[b]["rango_entre_fotos_puntos"])
    exigir(set(orden[:2]) == set(CON_AVISO), "Los barrios de Casco Histórico de Vallecas y Opañel son los que más se mueven")
    exigir(all(len(c.dato(f"{Q2}.pruebas.barrios.{b}.no_aguanta")) >= 2 for b in c.dato(f"{Q2}.segunda_linea")), "los restantes salen en dos comprobaciones o más")


# =====================================================================================================================
# 3. Páginas
# =====================================================================================================================

def pagina_resumen(inf, c):
    """Resumen: abre con la recomendación y los límites que pesan, sus cifras clave y la tabla de las tres preguntas."""
    rango = f"{Q3}.rango_de_rentabilidad_del_grupo_firme"
    p = inf.pagina("Buscar hasta 2 habitaciones en los barrios de Ventas, Numancia y San Diego", "resumen", panel="Resumen", columnas=False)
    p.cifra_clave(c.pct(f"{REC}.rentabilidad_pct"), "Rentabilidad bruta", "Mediana, antes de gastos")
    p.cifra_clave(c.num(f"{REC}.pisos"), "Anuncios en Airbnb", "No son pisos en venta")
    p.cifra_clave(c.eur(f"{REC}.compra_eur"), "Precio de compra", "Mediana por piso")
    p.cifra_clave(c.eur(f"{REC}.ingreso_anual_eur"), "Ingreso anual por piso", "Mediana, antes de gastos")
    p.texto(f"Con todos sus pisos, de cualquier tamaño, estos barrios rinden del {c.pct(rango + '.minimo')} al {c.pct(rango + '.maximo')} según la fecha del precio. "
            f"Se recomiendan porque se mantienen al repetir el cálculo, no porque rindan más. El barrio de Numancia rinde más que la mediana de todos los pisos. En los barrios de Ventas y San Diego no se puede asegurar. Los barrios de Casco Histórico de Vallecas y Opañel rinden más que el de San Diego, pero el {c.pct(Q2 + '.operadores_grandes.con_aviso_pct', 0)} de sus anuncios es de anfitriones con 10 anuncios o más.",
            f"Esta recomendación dice dónde buscar. Si un piso concreto se puede comprar para alquilarlo a turistas depende de la normativa, y se pregunta en el Ayuntamiento antes de comprar. Conviene empezar por bajos y primeras plantas con acceso independiente: {c.num(PLANTA + '.licencias')} de las {c.num(PLANTA + '.de')} licencias incluyen planta baja. "
            "Lo que ingresa un bajo no se conoce, porque los datos mezclan todas las plantas.")
    p.tabla(["Pregunta", "Respuesta", "Qué se recomienda"],
            [["1. Tipo de piso", "Hasta 2 habitaciones, sin ganador entre ellos", "Pedir su superficie real"],
             ["2. Barrios", "Tres siguen en la lista las 5 veces", "Comprobar planta y norma"],
             ["3. Riesgo", "Los tres dependen de los pisos en el máximo de días", "Repetir con los datos siguientes"]],
            fuente="Inside Airbnb, licencia CC BY 4.0; Ayuntamiento de Madrid")


def paginas_pregunta_1(inf, c, ap):
    """Pregunta 1: los pisos de hasta 2 habitaciones y el peso del supuesto de superficie."""
    t = "Hasta 2 habitaciones rinden más que 3 en todas las superficies probadas"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[1], panel="Habitaciones")
    p.cifra_clave(c.eur(f"{DORM}.tabla[grupo=2].euros_al_ano"), "Ingreso estimado al año, 2 habitaciones", "Mediana de todos los pisos")
    p.cifra_clave(c.eur(f"{DORM}.tabla[grupo=1].euros_al_ano"), "Ingreso estimado al año, 1 habitación", "Mediana de todos los pisos")
    grupos = ["1", "2", "0", "3"]
    clave = lambda x, campo: f"{DORM}.tabla[grupo={x}].{campo}"
    etiquetas = [f"{NOMBRE_DORM[x]}, {c.num(clave(x, 'pisos'))} anuncios" for x in grupos]
    valores = [numero_celda(c, clave(x, "rentabilidad_mediana_pct")) for x in grupos]
    bajos, altos = [numero_celda(c, clave(x, "ic_bajo")) for x in grupos], [numero_celda(c, clave(x, "ic_alto")) for x in grupos]
    ref = float(c.dato(f"{Q1}.referencia.valor"))
    svg = g.barras_con_intervalo(etiquetas, valores, bajos, altos, referencia=ref, rotulo_referencia="Todos los pisos", decimales=1, unidad=" %", intervalo="intervalo de confianza del 95 %", ancho=560, destacar=[etiquetas[3]], medida="rentabilidad bruta")
    ap.apuntar(len(inf.paginas), t, grupos, "rentabilidad bruta mediana", valores, "%")
    ap.apuntar(len(inf.paginas), t, ["todos los pisos"], "referencia", [ref], "%")
    p.texto("El equipo de valoraciones puede dejar fuera los pisos de 3 habitaciones.",
            "En ingreso anual van primero los pisos de 2 habitaciones, aunque la diferencia con los de 3 podría ser cero. Es un ingreso estimado, antes de gastos.",
            f"La ventaja de 1 habitación sobre 2 no se repite en todos los distritos: gana en {c.num(Q1 + '.por_segmentos.distritos_donde_1_supera_a_2')} de {c.num(Q1 + '.por_segmentos.distritos_comparables_1_y_2')}. "
            f"El tipo de inmueble apenas marca diferencias: {c.num(Q1 + '.tipo_de_inmueble.tabla[grupo=Entire rental unit].pisos')} de los {c.num(Q1 + '.poblacion.filas')} pisos son apartamentos de alquiler.")
    p.grafico(svg, "Los pisos de 3 habitaciones rinden menos que la mediana de todos los pisos", f"Rentabilidad bruta mediana, en %. Fuente: {FUENTE_PISOS}")

    t = "El orden entre estudio, una y dos habitaciones depende de los m²"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[1], panel="Superficie supuesta", columnas=False)
    p.cifra_clave(c.num(f"{SUP}.combinaciones_que_cambian"), "Casos en que cambia el tipo más rentable", f"De {c.cuantos(SUP + '.combinaciones')} probados")
    p.texto("No hay un ganador entre estudio, una y dos habitaciones, y los pisos de 3 no son los más rentables en ningún caso. Hasta conocer la superficie real, conviene tratar los tres tipos por igual.")
    filas = []
    for i, x in enumerate(c.dato(f"{SUP}.combinaciones")):
        base = f"{SUP}.combinaciones[{i}]"
        m2 = " · ".join(c.num(f"{base}.superficies.{k}") for k in ("0", "1", "2"))
        se_dan = ", ".join(NOMBRE_DORM[k].lower() for k in x["se_dan"])
        filas.append([m2] + [numero_celda(c, f"{base}.medianas.{k}") for k in ("0", "1", "2", "3")] + [se_dan])
    p.tabla(["m² de estudio · 1 · 2 habitaciones", "Estudio (%)", "1 habitación (%)", "2 habitaciones (%)", "3 habitaciones (%)", "Más rentable y posibles empates"], filas, fuente=f"{FUENTE_PISOS}. Rentabilidad bruta mediana", decimales=[0, 1, 1, 1, 1, 0])


def paginas_pregunta_2(inf, c, ap):
    """Pregunta 2: el mapa, el orden dentro de la lista, las comprobaciones y el peso del precio de compra."""
    poligonos, limite = leer_mapa()
    clases = c.dato(f"{Q2}.clases")
    t = "Tres barrios siguen en la lista las cinco veces y dos, cuatro veces"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[2], panel="Mapa de barrios")
    p.texto("Conviene empezar por los tres barrios recomendados. Los barrios de Casco Histórico de Vallecas y Opañel salen sin los anfitriones con 10 anuncios o más.",
            f"El cálculo se repitió 12 veces cambiando la estancia mínima, el mínimo de anuncios o la fecha del precio. Los {c.cuantos(Q2 + '.grupo')} barrios de la lista quedan en el 25 % más rentable en más de 6 de las 12.",
            "Después se repitió todo de 5 formas, quitando un grupo de anuncios cada vez. Se recomiendan los que siguen las 5 veces.")
    p.grafico(mapa_barrios.mapa(poligonos, clases, limite, ci.barrio), "Los que siguen 4 o 5 veces quedan al sur y al este del centro", f"Fuente: {FUENTE_PISOS}")
    ap.apuntar(len(inf.paginas), t, sorted(clases), "veces que sigue en la lista", [float(len(c.dato(f"{Q2}.pruebas.barrios.{b}.aguanta"))) for b in sorted(clases)], "veces")

    t = "El orden dentro de la lista no está cerrado"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[2], panel="Orden de la lista")
    orden = FIRMES + CON_AVISO + sorted(c.dato(f"{Q2}.segunda_linea"))
    etiquetas = [f"{ci.barrio(b)}, {c.num(ficha(b, 'pisos'))} anuncios" for b in orden]
    valores = [numero_celda(c, ficha(b, "rentabilidad_mediana_pct")) for b in orden]
    bajos, altos = [numero_celda(c, ficha(b, "ic_bajo")) for b in orden], [numero_celda(c, ficha(b, "ic_alto")) for b in orden]
    ref = float(c.dato(f"{Q2}.mediana_de_toda_la_base"))
    svg = g.barras_con_intervalo(etiquetas, valores, bajos, altos, referencia=ref, rotulo_referencia="Todos los pisos", decimales=1, unidad=" %", intervalo="intervalo de confianza del 95 %", ancho=640, medida="rentabilidad bruta")
    ap.apuntar(len(inf.paginas), t, orden, "rentabilidad bruta mediana", valores, "%")
    distinguen = sum(1 for x in c.dato(f"{Q3}.pares_dentro_del_grupo") if x["se_distinguen"])
    p.texto(f"La lista es un grupo, no una clasificación: de {c.cuantos(Q3 + '.pares_dentro_del_grupo')} parejas de barrios, solo en {ci.numero(distinguen)} se puede asegurar que uno rinde más que otro.",
            f"Cuando no se puede asegurar, la diferencia podría ser cero, con un 95 % de confianza. La mediana de los pisos de los tres barrios recomendados juntos es {c.pct(Q3 + '.rentabilidad_del_grupo_firme.mediana')}, que no es la media de las medianas de cada barrio.")
    c.apuntadas.setdefault(ci.numero(distinguen), set()).add(f"recuento de se_distinguen en {Q3}.pares_dentro_del_grupo")
    p.grafico(svg, "En casi ninguna pareja de barrios se puede asegurar la diferencia", f"Rentabilidad bruta mediana, en %. Fuente: {FUENTE_PISOS}")

    t = "Solo los tres recomendados siguen en la lista las cinco veces"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[2], panel="Repetir de cinco formas", columnas=False)
    p.texto("Los barrios que siguen en la lista 4 veces salen al quitar a los anfitriones con 10 anuncios o más. Los demás salen en dos o más de esas formas. El barrio de Puerta del Ángel sale en las cinco.")
    filas = []
    for b in orden:
        no = c.dato(ficha(b, "pruebas_que_no_aguanta"))
        filas.append([ci.barrio(b), c.dato(ficha(b, "clase")), ", ".join(NOMBRE_PRUEBA[x] for x in no) or "ninguna", numero_celda(c, ficha(b, "variantes_en_el_mejor_cuarto"), 0)])
    p.tabla(["Barrio", "Veces que sigue en la lista", "Sale al quitar o cambiar", "Veces de 12 en el 25 % más rentable"], filas, fuente=FUENTE_PISOS, decimales=[0, 0, 0, 0])

    baratos = f"{Q2}.referencia_baratos.comparados"
    t = "Elegir solo por m² barato podría rendir lo mismo que la lista"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[2], panel="Precio de compra")
    coinciden = c.dato(f"{baratos}.coinciden")
    p.cifra_clave(c.pct(f"{ORDENA}.m2_baratos.mediana_pct"), "Barrios de m² más barato", f"Los {c.num(baratos + '.de')} más baratos")
    p.cifra_clave(c.pct(f"{Q3}.rentabilidad_del_grupo_firme.mediana"), "Tres barrios recomendados", "Rentabilidad en mediana")
    p.cifra_clave(c.pct(f"{ORDENA}.grupo.mediana_pct"), "Barrios de la lista", "Rentabilidad en mediana")
    p.texto(f"La lista no gana rentabilidad frente a elegir por precio: {c.num(baratos + '.cuantos')} de los {c.num(baratos + '.de')} barrios coinciden y la diferencia entre las tres cifras podría ser cero. Lo que aporta es saber qué barrios se mantienen al repetir el cálculo.",
            f"Entre los {c.num(ORDENA + '.barrios')} barrios, la rentabilidad va más ligada a los días ocupados ({c.num(ORDENA + '.rentabilidad_con_ocupacion', 2)}) que al precio del m² ({c.num(ORDENA + '.rentabilidad_con_m2', 2)}), en una escala de -1 a 1, y los días ocupados son la cifra menos fiable. Es una asociación: no dice por qué esos barrios rinden más.")
    p.tabla(["Barrio de la lista", "Veces que sigue en la lista", "Entre los de m² más barato"], [[ci.barrio(b), c.dato(ficha(b, "clase")), "sí" if b in coinciden else "no"] for b in orden], fuente="Ayuntamiento de Madrid, precio de 2025; Inside Airbnb, datos del 17/09/2026", texto=False)


def paginas_pregunta_3(inf, c, ap):
    """Pregunta 3: el riesgo de cada barrio, lo que se mueve con la fecha del precio y el nivel de la rentabilidad."""
    orden = FIRMES + CON_AVISO + sorted(c.dato(f"{Q2}.segunda_linea"))
    t = "Los tres recomendados dependen de los pisos en el máximo de días"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[3], panel="Riesgo por barrio", columnas=False)
    p.texto(f"Un barrio depende del máximo si sale de la lista al quitar los pisos que llegan a 255 días. El barrio de Opañel, con el {c.pct(ficha('Opañel', 'parte_en_el_tope_pct'), 0)} de sus pisos en el máximo, no depende. "
            f"De todos los pisos analizados, uno de cada cuatro rinde menos del {c.pct(Q2 + '.cuartil_bajo_de_toda_la_base', 2)}; en los tres recomendados ese corte es más alto. "
            f"El {c.pct(Q3 + '.pisos_fuera_sin_ocupacion.pct')} de los pisos fuera del centro histórico no tiene días ocupados estimados.")
    filas = [[ci.barrio(b), c.dato(ficha(b, "clase")), numero_celda(c, ficha(b, "pisos"), 0), numero_celda(c, ficha(b, "cuartil_bajo_pct")), numero_celda(c, ficha(b, "parte_en_el_tope_pct")), numero_celda(c, ficha(b, "pisos_fuera_sin_ocupacion_pct", 3))] for b in orden]
    p.tabla(["Barrio", "Veces que sigue en la lista", "Anuncios", "Peor 25 % rinde menos de (%)", "Pisos en el máximo (%)", "Sin días estimados (%)"], filas, fuente=FUENTE_PISOS, decimales=[0, 0, 0, 1, 1, 1])

    t = "El barrio de Ventas es el recomendado que más cambia con la fecha"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[3], panel="Fecha del precio")
    valores = [numero_celda(c, ficha(b, "rango_entre_fotos_puntos", 3)) for b in orden]
    nombres = [ci.barrio(b) for b in orden]
    svg = g.barras_ordenadas(nombres, {"": valores}, decimales=1, unidad=" puntos", ancho=560, medida="diferencia entre fechas de precio")
    ap.apuntar(len(inf.paginas), t, orden, "diferencia entre fechas de precio", valores, "puntos")
    p.texto("Una descarga nueva puede mover la rentabilidad, y por eso la lista se repite antes de comprar.",
            "Marzo y junio solo cubren los anuncios que siguen en septiembre, con sus días ocupados.")
    p.grafico(svg, "Cuánto cambia cada barrio con la fecha del precio", f"Mediana más alta menos la más baja, en puntos. Fuente: {FUENTE_PISOS}")

    rango = f"{Q3}.rango_de_rentabilidad_de_firmes_y_con_aviso"
    firmes = f"{Q3}.rango_de_rentabilidad_del_grupo_firme"
    t = f"Los recomendados rinden del {c.pct(firmes + '.minimo')} al {c.pct(firmes + '.maximo')} según la fecha del precio"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[3], panel="Nivel de la rentabilidad")
    r = {x["foto"]: x["mediana"] for x in c.dato(f"{firmes}.combinaciones")}
    fotos = ["marzo", "junio", "septiembre"]
    nombres = [f.capitalize() for f in fotos]
    valores = [r[f] for f in fotos]
    svg = g.barras_ordenadas(nombres, {"": valores}, decimales=1, unidad=" %", ancho=560, ordenar=False, medida="rentabilidad bruta")
    ap.apuntar(len(inf.paginas), t, nombres, "rentabilidad bruta mediana de los tres barrios recomendados", valores, "%")
    p.texto("Es la rentabilidad de todos los pisos de los tres barrios, de cualquier tamaño.",
            f"Si se añaden los barrios de Casco Histórico de Vallecas y Opañel, el máximo llega al {c.pct(rango + '.maximo')}. Ninguna de estas cifras incluye gastos, impuestos ni comisiones.")
    p.grafico(svg, "Rentabilidad de los recomendados con cada fecha del precio", f"Rentabilidad bruta mediana de los tres barrios recomendados, en %, 2026. Fuente: {FUENTE_PISOS}")

    t = "Con anuncios de un año o más, el barrio de San Diego sale del 25 % más rentable"
    p = inf.pagina(t, "pregunta", pregunta=PREGUNTAS[3], panel="Anuncios nuevos", columnas=False)
    p.texto(f"Los días ocupados salen de las reseñas del último año, y un anuncio con menos de un año ha tenido menos tiempo para recibirlas, así que parece menos ocupado. Con los {c.num(UN_ANO + '.pisos')} anuncios de un año o más, entre {c.num(UN_ANO + '.barrios_comparados')} barrios con 30 anuncios o más, los barrios de Numancia y Ventas quedan en los puestos {c.num(ci.puesto('Numancia'))} y {c.num(ci.puesto('Ventas'))}, y el de San Diego en el {c.num(ci.puesto('San Diego'))}.")
    p.tabla(["Barrio", "Anuncios de un año o más", "Rentabilidad bruta (%)", "Puesto"], [[b, numero_celda(c, f"{UN_ANO}.barrios[barrio={b}].pisos", 0), numero_celda(c, f"{UN_ANO}.barrios[barrio={b}].mediana_pct"), numero_celda(c, ci.puesto(b), 0)] for b in FIRMES], fuente=FUENTE_PISOS, decimales=[0, 0, 1, 0])


def paginas_cierre(inf, c):
    """Límites y decisiones propuestas: una tabla cada una, en el orden de lo que hay en juego."""
    p = inf.pagina("Lo que puede cambiar estas conclusiones", "limites", panel="Límites")
    p.tabla(["Decisión a la que afecta", "Límite"], [
        ["Comprar un piso", "Estar fuera del centro histórico no significa que se pueda comprar para este uso. En el nivel B de la zona 1, el hospedaje se admite en planta baja, en la inferior a la baja y en la primera, siempre con acceso independiente. Planta, acceso y norma se comprueban en el Ayuntamiento. Esto no es asesoramiento jurídico."],
        ["Dónde buscar", "Los días ocupados son una estimación con máximo de 255, y entre los pisos más ocupados no sirven para ordenar."],
        ["Dónde buscar", "Si los pisos sin días ocupados ni precio se contaran como cero, solo seguiría en la lista el barrio de Ventas."],
        ["Qué tipo buscar", "La superficie es un supuesto del equipo de valoraciones, y el dato oficial es igual para todos los pisos del barrio."],
        ["Cuánto rinde", f"El precio de compra es el declarado en 2025 y la inversión total no consta. Con los precios que piden hoy Fotocasa e Idealista, la compra sube a {c.eur('recomendacion.precio_de_mercado.fuentes[fuente=Fotocasa].compra_mediana_eur')} y {c.eur('recomendacion.precio_de_mercado.fuentes[fuente=Idealista].compra_mediana_eur')}, y la rentabilidad baja a {c.pct('recomendacion.precio_de_mercado.fuentes[fuente=Fotocasa].rentabilidad_mediana_pct')} y {c.pct('recomendacion.precio_de_mercado.fuentes[fuente=Idealista].rentabilidad_mediana_pct')}. No se ha medido si cambiarían los barrios."],
        ["Barrio de Casco Histórico de Vallecas", "Airbnb junta en él lo que el Ayuntamiento separa, y su precio oficial puede no representar todo el barrio."],
        ["Por qué ocurre", "Son asociaciones sobre una descarga: no dicen por qué un barrio rinde más. El calendario no distingue reservado de bloqueado."],
    ], fuente="reglas de negocio y datos del 17/09/2026")

    p = inf.pagina("Decisiones propuestas", "decision", panel="Decisiones propuestas")
    p.texto("La Dirección de Inversiones tiene que aprobar estas tres acciones. Ninguna tiene fecha fijada. La primera empieza por bajos y primeras plantas.")
    p.tabla(["Decisión", "Quién", "Plazo", "Por qué"], [[a["nombre"], a["quien"], a["cuando"][0].upper() + a["cuando"][1:], a["por_que"]] for a in ci.acciones(c)], fuente="informe ejecutivo y páginas de este informe")


def paginas_anexo(inf, c):
    """Anexo: método de cada pregunta, fuentes de cada cifra y datos personales."""
    p = inf.pagina("Método de cada pregunta", "anexo", panel="Método", columnas=False)
    p.texto("Rentabilidad bruta: ingreso anual estimado dividido entre el precio de compra. Días ocupados: días al año que estima Inside Airbnb, con máximo de 255. Precio de compra: superficie por precio oficial del m² del barrio.",
            "Pisos analizados: fuera del centro histórico, con precio por noche entre 20 y 1.000 €, hasta 8 huéspedes, días ocupados mayor que cero y estancia mínima de hasta 3 noches.",
            f"Pregunta 1: medianas por habitaciones con 30 pisos o más e intervalo de confianza del 95 %, el rango en que probablemente está la diferencia, calculado con 2.000 remuestreos. La superficie supuesta se movió en las {c.cuantos(SUP + '.combinaciones')} combinaciones de sus extremos.",
            "Pregunta 2: el 25 % más rentable en más de 6 de 12 repeticiones. Las 5 formas de repetir el cálculo: sin pisos de temporada; sin anfitriones con 10 anuncios o más; sin precios para fechas a más de 60 días; solo con 1 y 2 habitaciones; contando como cero los pisos sin días estimados.",
            "Pregunta 3: por barrio, número de anuncios, corte del peor 25 %, parte en el máximo, parte sin días estimados y diferencia entre fechas de precio.")
    # Contexto del mercado: la oferta de cada descarga, sin comparar causas.
    oferta = [[f"{ci.fecha_es(x['foto'])}", numero_celda(c, f"evolucion_oferta.fotos[foto={x['foto']}].anuncios", 0), numero_celda(c, f"evolucion_oferta.fotos[foto={x['foto']}].pisos_completos", 0)] for x in c.dato("evolucion_oferta.fotos")]
    p = inf.pagina("Contexto del mercado", "anexo", panel="Contexto", columnas=False)
    p.tabla(["Descarga de Inside Airbnb", "Anuncios", "Pisos"], [["Junio de 2025", numero_celda(c, "evolucion_oferta.junio_2025.anuncios", 0), None]] + oferta, fuente="Inside Airbnb. Un cambio entre descargas no dice por qué ocurre. De junio de 2025 solo consta el recuento", decimales=[0, 0, 0])
    p.texto(f"Las reseñas alcanzan su índice más alto en junio, {c.num('estacionalidad.indice_mas_alto', 2)}, y el más bajo en febrero, {c.num('estacionalidad.indice_mas_bajo', 2)}, en {c.num('estacionalidad.meses')} meses completos. No todas las estancias dejan reseña.",
            f"El registro municipal tiene {c.num('licencias_y_registro.totales.licencias')} licencias y {c.num('licencias_y_registro.totales.viviendas_con_licencia')} viviendas. Una licencia no se puede unir a un anuncio: solo se cuenta por barrio.")
    p = inf.pagina("Fuentes de cada cifra", "anexo", panel="Fuentes", columnas=False)
    p.tabla(["Cifra", "Fichero de informes/", "Fecha de los datos"], [
        ["Todas las de este informe", "indicadores.json", ci.fecha_es(c.dato("fecha_datos"))],
        ["Ruta de cada cifra", "informe_final_rastro.json", ci.fecha_es(c.dato("fecha_datos"))],
        ["Cifras de cada gráfico", "informe_final_graficos.csv", ci.fecha_es(c.dato("fecha_datos"))]], fuente="carpeta informes/ del repositorio", texto=False)
    p.texto(*ci.ATRIBUCION, "Plan RESIDE, BOCM 226 de 22/09/2025.")
    p = inf.pagina("Datos personales", "anexo", panel="Datos personales", columnas=False)
    p.texto("Qué traían los datos. Los anuncios traían columnas que identifican al anfitrión, enlaces, fotos, nombre, descripción y número de licencia. Las reseñas traían texto, nombre y código de quien reseña. Las licencias traían dirección, punto y números de expediente.",
            "Qué se hizo. Se borraron esas columnas sin sustituirlas por códigos, así que no hay seudonimización. Del número de licencia queda solo su tipo.",
            "Cuándo. Se decidió el 06/11/2026, antes de que los datos entraran en el análisis, que trabajó siempre sin esas columnas.",
            "Lo que queda. El número del anuncio, con el que se llega a su página pública, las coordenadas, desplazadas hasta 150 m, y el recuento de anuncios por anfitrión, que no dice quién es. Por eso los resultados se dan por barrio y tipo de piso, con un mínimo de 30 pisos. Ninguno decide sobre una persona.")


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
