"""Informe ejecutivo del caso: dos páginas A4 y una de anexo para el equipo directivo.

Lee informes/indicadores.json, que tiene que ser más nuevo que scripts/indicadores.py, y no calcula ninguna cifra de negocio.
Deja informes/informe_ejecutivo.html, informes/informe_ejecutivo.json con el rastro de cada cifra e informes/informe_ejecutivo.pdf.
Para sin escribir nada si una frase deja de ser cierta, si un apartado pasa de su
tope de palabras o si el texto lleva una palabra prohibida. No importa ningún script del caso que ejecute algo al importarse.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/informe_ejecutivo.py
Opciones: --indicadores <json>, --salida <carpeta>, --sin-pdf. Las usa tests/probar_informe_ejecutivo.py.
"""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import cifras_informes as ci
from cifras_informes import CON_AVISO, FIRMES, ORDENA, PLANTA, Q2, Q3, REC, UN_ANO, ficha

# =====================================================================================================================
# 1. Configuración
# =====================================================================================================================

# Topes de palabras por apartado (patrón 07, §1).
TOPES = {"titulo_y_resumen": 300, "encontrado": 400, "limites": 100, "recomendaciones": 200, "anexo": 500}
# Edge imprime el PDF sin ventana. Sin él, el informe sale igual en HTML y el PDF se queda como estaba.
EDGE = [Path(p) for p in (shutil.which("msedge"), shutil.which("microsoft-edge")) if p]
EDGE += [Path(os.environ[v]) / "Microsoft/Edge/Application/msedge.exe" for v in ("ProgramFiles(x86)", "ProgramFiles") if v in os.environ]
ESPERA_PDF = 60  # segundos: Edge puede devolver el control antes de terminar de escribir el PDF 
TITULO = "Buscar pisos de hasta 2 habitaciones en los barrios de Ventas, Numancia y San Diego"

# Hoja de impresión del patrón 07, §6: A4, 20 mm, Segoe UI a 11 pt, sin color ni recuadros. En pantalla, una hoja centrada.
ESTILO = """@page { size: A4; margin: 20mm; }
html, body { margin: 0; background: #ffffff; color: #0b0b0b; }
body { font-family: "Segoe UI", system-ui, sans-serif; font-size: 11pt; line-height: 1.4; }
h1 { font-size: 18pt; font-weight: 700; line-height: 1.2; margin: 0 0 4pt; }
h2 { font-size: 14pt; font-weight: 700; margin: 12pt 0 4pt; }
h3 { font-size: 12pt; font-weight: 700; margin: 9pt 0 3pt; }
p { margin: 0 0 5pt; }
ul, ol { margin: 0 0 5pt; padding-left: 16pt; }
li { margin: 0 0 3pt; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 5pt 0 3pt; }
th { text-align: left; font-weight: 700; border-bottom: 1px solid #0b0b0b; padding: 1pt 5pt 1pt 0; vertical-align: bottom; }
td { padding: 0.5pt 5pt 0.5pt 0; }
th.num, td.num { text-align: right; }
.nota { font-size: 9.5pt; }
.anexo { break-before: page; }
.anexo, .anexo ul, .anexo ol { font-size: 10pt; line-height: 1.3; }
.anexo h3 { font-size: 11pt; margin: 6pt 0 2pt; }
@media screen {
  html { background: #eef0f2; }
  body { box-sizing: border-box; max-width: 794px; margin: 24px auto; padding: 56px 64px; background: #ffffff; }
  .anexo { margin-top: 32pt; padding-top: 16pt; border-top: 1px solid #c8ccd0; }
}
@media screen and (max-width: 820px) {
  body { margin: 0; padding: 24px 16px; }
  table { display: block; overflow-x: auto; }
}
"""


# =====================================================================================================================
# 2. Contenido, escrito antes que el montaje
# =====================================================================================================================

def fila_barrio(c, b):
    """Fila de un barrio: veces en la lista, anuncios, rentabilidad, corte del peor 25 %, máximo y parte sin días estimados."""
    return [ci.barrio(b), c.cuantos(ficha(b, 'pruebas_que_aguanta')), c.num(ficha(b, "pisos")), c.num(ficha(b, "rentabilidad_mediana_pct"), 1), c.num(ficha(b, "cuartil_bajo_pct"), 1),
            c.num(ficha(b, "parte_en_el_tope_pct"), 1), c.num(ficha(b, "pisos_fuera_sin_ocupacion_pct", 3), 1)]


def contenido(c):
    """Escribe el informe como datos: cada cifra se lee del JSON y queda apuntada con su clave."""
    rango = f"{Q3}.rango_de_rentabilidad_del_grupo_firme"
    fot, ide = "recomendacion.precio_de_mercado.fuentes[fuente=Fotocasa]", "recomendacion.precio_de_mercado.fuentes[fuente=Idealista]"
    dorm = lambda g, campo: f"preguntas[0].dormitorios.tabla[grupo={g}].{campo}"
    acciones = ci.acciones(c)

    # Antes de las viñetas va lo que limita la recomendación: la normativa y la planta.
    limite = (f"Esta recomendación dice dónde buscar. No dice si un piso concreto se puede comprar para alquilarlo a turistas: eso depende de la normativa y se pregunta en el Ayuntamiento antes de comprar. "
              f"Conviene empezar por bajos y primeras plantas con acceso independiente, porque <b>{c.num(PLANTA + '.licencias')}</b> de las {c.num(PLANTA + '.de')} licencias incluyen planta baja. "
              "Lo que ingresa un bajo no se conoce: los datos mezclan todas las plantas.")

    # Resumen: cinco viñetas, la primera en dinero.
    resumen = [
        f"Un piso de hasta 2 habitaciones en estos barrios costaría <b>{c.eur(REC + '.compra_eur')}</b> e ingresaría {c.eur(REC + '.ingreso_anual_eur')} al año. Eso da un <b>{c.pct(REC + '.rentabilidad_pct')}</b> de rentabilidad en mediana, antes de gastos e impuestos. A los precios que se piden hoy baja al {c.pct(fot + '.rentabilidad_mediana_pct')} en Fotocasa y al {c.pct(ide + '.rentabilidad_mediana_pct')} en Idealista.",
        "Se recomiendan porque el resultado se mantiene: el cálculo se repitió de cinco formas, quitando cada vez un grupo de anuncios, y estos tres barrios siguieron entre los más rentables las cinco veces. Eso no significa que rindan más que los demás de la lista.",
        f"Los barrios de Casco Histórico de Vallecas y Opañel rinden más que el de San Diego, pero el <b>{c.pct(Q2 + '.operadores_grandes.con_aviso_pct', 0)}</b> de sus anuncios es de anfitriones con 10 anuncios o más. Sin esos anfitriones, salen de la lista.",
        "Los días ocupados son una estimación con un máximo de <b>255</b> al año. Si se quitan los pisos que llegan a ese máximo, los tres barrios salen de la lista.",
        "Entre estudio, una y dos habitaciones no hay ganador: depende de la superficie supuesta.",
    ]

    # Lo encontrado: una evidencia por viñeta, en el mismo orden, con su base y sin repetir la frase.
    encontrado = [
        f"Las cifras de compra e ingreso son medianas de {c.num(REC + '.pisos')} anuncios en Airbnb, no de pisos en venta. La rentabilidad bruta es el ingreso anual dividido entre el precio de compra. Con todos los pisos de estos barrios, de cualquier tamaño, va del {c.pct(rango + '.minimo')} al {c.pct(rango + '.maximo')} según la fecha del precio.",
        f"Para elegirlos se partió de {c.num('preguntas[0].poblacion.filas')} pisos fuera del centro histórico. El cálculo se repitió 12 veces cambiando la estancia mínima, el mínimo de anuncios por barrio o la fecha del precio. {c.cuantos(Q2 + '.grupo')} barrios quedaron en el 25 % más rentable en más de la mitad de las repeticiones, y esa es la lista.",
        "El barrio de Numancia rinde más que la mediana de todos los pisos. En los barrios de Ventas y San Diego no se puede asegurar: la diferencia podría ser cero, con un 95 % de confianza.",
        f"El barrio de San Diego es el más débil de los tres. Los días ocupados salen de las reseñas del último año, y un anuncio con menos de un año ha tenido menos tiempo para recibirlas, así que parece menos ocupado. Con los anuncios de un año o más, los barrios de Numancia y Ventas quedan en los puestos {c.num(ci.puesto('Numancia'))} y {c.num(ci.puesto('Ventas'))} de {c.num(UN_ANO + '.barrios_comparados')}, y el de San Diego en el {c.num(ci.puesto('San Diego'))}.",
        f"Entre los {c.num(ORDENA + '.barrios')} barrios comparados, la rentabilidad va más ligada a los días ocupados ({c.num(ORDENA + '.rentabilidad_con_ocupacion', 2)}) que al precio del m² ({c.num(ORDENA + '.rentabilidad_con_m2', 2)}), en una escala de -1 a 1. Los días ocupados son la cifra menos fiable de este análisis.",
        f"En todos los pisos analizados, 1 habitación rinde {c.pct(dorm(1, 'rentabilidad_mediana_pct'))} y 2 habitaciones, {c.pct(dorm(2, 'rentabilidad_mediana_pct'))}, frente a {c.pct(dorm(3, 'rentabilidad_mediana_pct'))} con 3.",
    ]
    filas = [fila_barrio(c, b) for b in FIRMES + CON_AVISO]

    limites = [
        "Los días ocupados son una estimación, no noches vendidas.",
        "Si los pisos sin días ocupados ni precio se contaran como cero, solo seguiría en la lista el barrio de Ventas.",
        "La superficie de cada piso es un supuesto. La rentabilidad bruta no incluye gastos ni impuestos.",
        f"El precio de compra es el declarado en 2025. A lo que se pide hoy sube a {c.eur(fot + '.compra_mediana_eur')} en Fotocasa y {c.eur(ide + '.compra_mediana_eur')} en Idealista. No se midió si cambiarían los barrios.",
        "Una diferencia entre barrios no explica por qué ocurre. Este informe no es asesoramiento jurídico.",
    ]

    # Anexo para el equipo: tablas, pasos, consultas, protección de datos, fichero de cifras y fuentes.
    s08 = "las_16[id=S08].base_decision.datos.toda_la_base.255"
    oferta = "evolucion_oferta"
    consultas = [
        ("¿Cuántos anuncios hay en Madrid?", f"{c.num(oferta + '.fotos[foto=2026-09-17].anuncios')} en la descarga del 17/09/2026 y {c.num(oferta + '.junio_2025.anuncios')} en la descarga de Inside Airbnb de junio de 2025. El cambio no dice por qué ocurre."),
        ("¿Cuántos pisos se analizaron?", f"{c.num('preguntas[0].poblacion.filas')}, en {c.num(Q2 + '.cobertura.barrios_con_pisos')} barrios."),
        ("¿Cuántos pisos fuera del centro histórico no tienen días ocupados estimados?", f"{c.num(Q3 + '.pisos_fuera_sin_ocupacion.pisos')}, el {c.pct(Q3 + '.pisos_fuera_sin_ocupacion.pct')}. Quedan fuera de la lista."),
        ("¿Qué parte de los pisos llega al máximo?", f"El {c.pct(s08)} de los analizados."),
        ("¿En qué mes hay más reseñas?", f"En junio, con un índice de {c.num('estacionalidad.indice_mas_alto', 2)}, y menos en febrero, con {c.num('estacionalidad.indice_mas_bajo', 2)}. Son {c.num('estacionalidad.meses')} meses completos."),
        ("¿Cuántas licencias municipales hay?", f"{c.num('licencias_y_registro.totales.licencias')}, con {c.num('licencias_y_registro.totales.viviendas_con_licencia')} viviendas. Una licencia no se puede unir a un anuncio."),
    ]
    anexo = {
        "tablas": ("Anuncios de Inside Airbnb del 14/12/2025, 24/03/2026, 20/06/2026 y 17/09/2026; calendario y reseñas de la última; precio y superficie oficiales de 2025; "
                   "límite del centro histórico, licencias y puntos de interés del Ayuntamiento de Madrid."),
        "pasos": ("Se limpiaron y unieron los datos, se calculó la rentabilidad bruta de cada piso y se repitió el cálculo como se explica arriba. Las comparaciones entre barrios llevan un intervalo de confianza del 95 %. "
                  "Las cinco formas de repetirlo quitan los pisos de temporada, quitan a los anfitriones con 10 anuncios o más, quitan los precios para fechas a más de 60 días, dejan solo 1 y 2 habitaciones o cuentan como cero los pisos sin días estimados."),
        "consultas": consultas,
        "datos": ("Son datos públicos. Antes de llegar al análisis se suprimieron las columnas que identifican al anfitrión, los enlaces, las fotos, los textos y el número de licencia, del que queda su tipo. "
                  "Se borraron sin sustituirlas por códigos, así que no hay seudonimización. Quedan el número del anuncio, con el que se llega a su página pública, las coordenadas, desplazadas hasta 150 m, y el recuento de anuncios por anfitrión. "
                  "Se decidió el 06/11/2026 y el análisis trabajó siempre sin esas columnas. El apartado entero va en el informe final."),
        "fichero": "Cada cifra de este informe sale de los cálculos publicados en la carpeta informes/ del repositorio.",
        "fuentes": ci.ATRIBUCION + ["Plan RESIDE, BOCM 226 de 22/09/2025."],
    }
    return {"limite": limite, "resumen": resumen, "encontrado": encontrado, "filas": filas, "limites": limites, "acciones": acciones, "anexo": anexo}


# =====================================================================================================================
# 3. Montaje
# =====================================================================================================================

def lista(items, etiqueta="ul"):
    """Monta una lista con sus marcas; los textos ya vienen con su negrita."""
    return f"<{etiqueta}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{etiqueta}>"


def tabla_riesgo(filas):
    """Monta la tabla de barrios, con los números a la derecha."""
    cab = ["Barrio", "Veces en la lista (de 5)", "Anuncios", "Rentabilidad (%)", "Uno de cada cuatro rinde menos de (%)", "Pisos en el máximo de días (%)", "Pisos sin días estimados (%)"]
    num = [False, False, True, True, True, True, True]
    th = "".join(f'<th{" class=\"num\"" if n else ""}>{t}</th>' for t, n in zip(cab, num))
    td = "".join("<tr>" + "".join(f'<td{" class=\"num\"" if n else ""}>{html.escape(str(v))}</td>' for v, n in zip(f, num)) + "</tr>" for f in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{td}</tbody></table>"


def montar(t, c, emision):
    """Monta el HTML A4 y devuelve el documento y el texto de cada apartado."""
    fecha = ci.fecha_es(c.dato("fecha_datos"))
    meta = f"Informe para la dirección. Datos de anuncios de Airbnb del {fecha}. Emisión: {emision}."
    aprobar = f"<p>Se piden {ci.numero(len(t["acciones"]))} acciones:</p>" + lista([a["nombre"] for a in t["acciones"]], "ol")
    resumen = f"<h2>Resumen ejecutivo</h2><p>{t['limite']}</p>{lista(t['resumen'])}{aprobar}"
    sin_ocupacion = c.pct(f"{Q3}.pisos_fuera_sin_ocupacion.pct")
    encontrado = ("<h3>Lo que hemos encontrado</h3>" + lista(t["encontrado"]) + tabla_riesgo(t["filas"])
                  + f'<p class="nota">Rentabilidad: mediana de cada barrio. Pisos sin días estimados: {sin_ocupacion} en todos los pisos fuera del centro histórico. Fuente: Inside Airbnb y Ayuntamiento de Madrid, datos del 17/09/2026.</p>')
    limites = "<h3>Límites</h3>" + lista(t["limites"])
    recomendaciones = "<h3>Recomendaciones</h3>" + lista([f"<b>{a['nombre']}.</b> {a['que']} Quién: {a['quien']}; {a['cuando']}. Motivo: {a['por_que'][0].lower() + a['por_que'][1:]}" for a in t["acciones"]], "ol")
    x = t["anexo"]
    anexo = ('<section class="anexo"><h2>Anexo: trabajo realizado</h2>'
             f"<h3>Datos usados</h3><p>{x['tablas']}</p><h3>Pasos seguidos</h3><p>{x['pasos']}</p>"
             "<h3>Consultas</h3>" + lista([f"{q} {r}" for q, r in x["consultas"]]) +
             f"<h3>Datos personales</h3><p>{x['datos']}</p><h3>Origen de las cifras</h3><p>{x['fichero']}</p>"
             "<h3>Fuentes externas</h3>" + lista(x["fuentes"], "ol") + "</section>")
    documento = (f'<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Informe ejecutivo</title>\n<style>\n{ESTILO}</style>\n</head>\n<body>\n'
                 f"<h1>{TITULO}</h1><p>{meta}</p>{resumen}<h2>Conclusiones y recomendaciones</h2>{encontrado}{limites}{recomendaciones}{anexo}\n</body>\n</html>\n")
    apartados = {"titulo_y_resumen": TITULO + " " + meta + " " + resumen, "encontrado": encontrado, "limites": limites, "recomendaciones": recomendaciones, "anexo": anexo}
    return documento, apartados


def texto_de(fragmento):
    """Quita las etiquetas y deja el texto visible."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def imprimir_pdf(ruta_html, ruta_pdf):
    """Imprime el HTML a PDF con Edge sin ventana y espera a que el PDF exista y deje de crecer."""
    edge = next((e for e in EDGE if e.exists()), None)
    if edge is None:
        print("AVISO: no hay Edge en este equipo y el PDF no sale")
        return False
    ruta_pdf.unlink(missing_ok=True)
    subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={ruta_pdf}", ruta_html.resolve().as_uri()], capture_output=True, timeout=ESPERA_PDF)
    tam, limite = -1, time.time() + ESPERA_PDF
    while time.time() < limite:
        ahora = ruta_pdf.stat().st_size if ruta_pdf.exists() else 0
        if ahora and ahora == tam:
            return True
        tam = ahora
        time.sleep(1)
    print("AVISO: Edge no dejó el PDF a tiempo")
    return False


def comprobar_pdf(ruta_pdf):
    """Comprueba con pypdf que todo menos el anexo cabe en dos páginas y que el total no pasa de tres."""
    from pypdf import PdfReader
    paginas = PdfReader(str(ruta_pdf)).pages
    textos = [p.extract_text() for p in paginas]
    if len(paginas) != 3:
        raise SystemExit(f"El PDF tiene {len(paginas)} páginas y tienen que ser tres")
    if not textos[2].lstrip().startswith("Anexo") or "Anexo: trabajo realizado" in textos[0] + textos[1]:
        raise SystemExit("El anexo tiene que empezar en la tercera página, sola")
    if "Recomendaciones" not in textos[0] + textos[1] or "Repetir el análisis" not in textos[1]:
        raise SystemExit("Las recomendaciones tienen que acabar en la segunda página")
    return len(paginas)


# =====================================================================================================================
# 4. Principal
# =====================================================================================================================

def principal():
    """Lee, comprueba, escribe y deja el rastro de cada cifra."""
    a = argparse.ArgumentParser()
    a.add_argument("--indicadores", default=str(ci.INDICADORES))
    a.add_argument("--salida", default=str(ci.CASO / "informes"))
    a.add_argument("--sin-pdf", action="store_true")
    o = a.parse_args()
    c = ci.Cifras(o.indicadores)
    # El JSON por defecto tiene que ser más nuevo que su script.
    if o.indicadores == str(ci.INDICADORES) and ci.INDICADORES.stat().st_mtime < (ci.CASO / "scripts" / "indicadores.py").stat().st_mtime:
        raise SystemExit("informes/indicadores.json es más viejo que scripts/indicadores.py: lanza antes el script")
    ci.comprobar_lectura(c)
    emision = datetime.date.today().strftime("%d/%m/%Y")
    t = contenido(c)
    documento, apartados = montar(t, c, emision)

    # Se valida antes de guardar: palabras, jerga y rastro de cada cifra.
    cuenta = {k: ci.palabras(texto_de(v)) for k, v in apartados.items()}
    pasan = {k: n for k, n in cuenta.items() if n > TOPES[k]}
    if pasan:
        raise SystemExit(f"Apartados por encima de su tope de palabras: {pasan}, topes {TOPES}")
    visible = " ".join(texto_de(v) for v in apartados.values())
    ci.sin_jerga(visible)
    sueltas = ci.cifras_sin_rastro(visible, list(c.apuntadas))
    if sueltas:
        raise SystemExit(f"Cifras sin clave en el texto: {sueltas}")

    salida = Path(o.salida)
    ruta = salida / "informe_ejecutivo.html"
    ruta.write_text(documento, encoding="utf-8")
    fecha_ejecucion = datetime.datetime.now().isoformat(timespec="seconds")
    resultado = {"fecha_datos": c.dato("fecha_datos"), "fecha_ejecucion": fecha_ejecucion, "script": "scripts/informe_ejecutivo.py", "indicadores": "informes/indicadores.json", "indicadores_fecha_ejecucion": c.dato("fecha_ejecucion"),
                 "lector": "equipo directivo", "se_pide": [x["nombre"] for x in t["acciones"]], "acciones": t["acciones"], "consultas": [{"pregunta": q, "respuesta": r} for q, r in t["anexo"]["consultas"]],
                 "palabras_por_apartado": cuenta, "topes": TOPES, "rastro": c.rastro(), "constantes": ci.CONSTANTES}
    if not o.sin_pdf:
        pdf = salida / "informe_ejecutivo.pdf"
        resultado["paginas_pdf"] = comprobar_pdf(pdf) if imprimir_pdf(ruta, pdf) else None
    (salida / "informe_ejecutivo.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Informe ejecutivo en {ruta}. Palabras: {cuenta}. Páginas del PDF: {resultado.get('paginas_pdf', 'sin PDF')}")


if __name__ == "__main__":
    principal()
