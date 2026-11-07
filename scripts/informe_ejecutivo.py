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
from cifras_informes import CUATRO_DE_CINCO, RECOMENDADOS, ORDENA, PLANTA, Q2, Q3, REC, UN_ANO, ficha

# =====================================================================================================================
# 1. Configuración
# =====================================================================================================================

# Topes de palabras por apartado (patrón 07, §1).
TOPES = {"titulo_y_resumen": 300, "encontrado": 400, "limites": 100, "recomendaciones": 200, "anexo": 500}
# Edge imprime el PDF sin ventana. Sin él, el informe sale igual en HTML y el PDF se queda como estaba.
EDGE = [Path(p) for p in (shutil.which("msedge"), shutil.which("microsoft-edge")) if p]
EDGE += [Path(os.environ[v]) / "Microsoft/Edge/Application/msedge.exe" for v in ("ProgramFiles(x86)", "ProgramFiles") if v in os.environ]
ESPERA_PDF = 60  # segundos: Edge puede devolver el control antes de terminar de escribir el PDF 

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
.sello { font-size: 9.5pt; font-weight: 700; margin: 0 0 6pt; }
.decide { margin-bottom: 6pt; }
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
    """Fila de la tabla: lo justo para comparar los barrios."""
    return [ci.barrio(b), c.cuantos(ficha(b, "pruebas_que_aguanta")), c.num(ficha(b, "pisos")), c.num(ficha(b, "rentabilidad_mediana_pct"), 1),
            c.num(ficha(b, "cuartil_bajo_pct"), 1), c.num(ficha(b, "parte_en_el_tope_pct"), 1), c.num(ficha(b, "pisos_fuera_sin_ocupacion_pct", 3), 1)]


def contenido(c):
    """Escribe el informe como datos: cada cifra se lee del JSON y queda apuntada con su clave."""
    rango = f"{Q3}.rango_de_rentabilidad_de_recomendados"
    SUP3 = "preguntas[0].sensibilidad_superficie.tres_habitaciones"
    fot, ide_ = "recomendacion.precio_de_mercado.fuentes[fuente=Fotocasa]", "recomendacion.precio_de_mercado.fuentes[fuente=Idealista]"
    dorm = lambda g, campo: f"preguntas[0].dormitorios.tabla[grupo={g}].{campo}"
    rent = c.pct(REC + ".rentabilidad_pct")
    titulo = "Empezar la búsqueda por pisos de hasta 2 habitaciones en los barrios de Ventas, Numancia y San Diego"
    decide = ("La dirección invertirá en Madrid y necesita decir a valoraciones qué pisos buscar y en qué barrios, fuera del centro histórico, "
              "donde ya no se admiten pisos turísticos en edificios residenciales. Este informe propone dónde empezar y qué comprobar antes de comprar.")
    conclusiones = [
        f"En mediana, un piso de esta lista costaría <b>{c.eur(REC + '.compra_eur')}</b> e ingresaría <b>{c.eur(REC + '.ingreso_anual_eur')}</b> al año. Son 50 m² en el barrio de Numancia, con una compra entre {c.eur(REC + '.compra_minima_eur')} y {c.eur(REC + '.compra_maxima_eur')} según barrio y tamaño.",
        f"Estos pisos rinden un <b>{rent}</b> bruto, frente al {c.pct(Q2 + '.mediana_de_toda_la_base')} de todos los pisos analizados, antes de gastos e impuestos y con días ocupados estimados. A los precios de hoy bajan a {c.pct(fot + '.rentabilidad_mediana_pct')} en Fotocasa y {c.pct(ide_ + '.rentabilidad_mediana_pct')} en Idealista.",
        "Los tres barrios son los únicos que siguen en la lista en las cinco repeticiones del cálculo. Por eso se eligieron, lo que no significa que rindan más.",
        f"La lista es provisional: sin los pisos que llegan al máximo de <b>255</b> días ocupados, ninguno de los tres sigue y salen {c.cuantos(Q2 + '.grupo_sin_los_pisos_en_el_tope')} barrios distintos ({ci.lista_sin_maximo(c)}).",
        "Ningún piso se puede comprar sin comprobar antes la norma con el Ayuntamiento y el acuerdo de su comunidad de propietarios, por tres quintos.",
    ]
    detalle = [
        f"<b>Con 3 habitaciones se rinde bastante menos.</b> En todos los pisos, 1 habitación rinde {c.pct(dorm(1, 'rentabilidad_mediana_pct'))} y 2 habitaciones, {c.pct(dorm(2, 'rentabilidad_mediana_pct'))}, frente al {c.pct(dorm(3, 'rentabilidad_mediana_pct'))} con 3. Entre 1 y 2 no hay ganador claro. Los tamaños son un supuesto: 3 habitaciones se calculan con 90 m² o más y 2, con 65 m². Para igualar a los de 2, los de 3 tendrían que medir unos {c.num(SUP3 + '.superficie_para_igualar_a_2_m2')} m².",
        f"<b>Tres barrios aguantan las cinco pruebas, no la del máximo de días (Tabla 1).</b> Se partió de {c.num('preguntas[0].poblacion.filas')} pisos fuera del centro histórico y se quedaron en el 25 % más rentable en las cinco. Con pisos de cualquier tamaño, suman {c.num(Q2 + '.pisos_de_recomendados')} anuncios y una rentabilidad mediana del {c.pct(Q3 + '.rentabilidad_de_recomendados.mediana')}, entre {c.pct(rango + '.minimo')} y {c.pct(rango + '.maximo')} según la fecha del precio. El barrio de Numancia rinde más que la mediana de todos los pisos; en los barrios de Ventas y San Diego esa diferencia no se puede asegurar con un 95 % de confianza.",
        f"<b>Dos barrios rinden más y quedan fuera.</b> Los barrios de Casco Histórico de Vallecas y Opañel superan al de San Diego, pero el {c.pct(Q2 + '.operadores_grandes.cuatro_de_cinco_pct', 0)} de sus anuncios es de anfitriones con 10 anuncios o más, y sin ellos salen de la lista.",
        f"<b>Los días ocupados son la cifra menos fiable.</b> Entre {c.num(ORDENA + '.barrios')} barrios, la rentabilidad va más ligada a los días ocupados que al precio del m²: {c.num(ORDENA + '.rentabilidad_con_ocupacion', 2)} frente a {c.num(ORDENA + '.rentabilidad_con_m2', 2)}, en una escala de −1 a 1. Esos días son una estimación, no noches vendidas.",
        f"<b>Los anuncios nuevos parecen menos ocupados.</b> Reciben menos reseñas. Con los anuncios de un año o más, los barrios de Numancia y Ventas quedan en los puestos {c.num(ci.puesto('Numancia'))} y {c.num(ci.puesto('Ventas'))} de {c.num(UN_ANO + '.barrios_comparados')}, y el de San Diego, en el {c.num(ci.puesto('San Diego'))}.",
    ]
    filas = [fila_barrio(c, b) for b in RECOMENDADOS + CUATRO_DE_CINCO]
    limites = [
        f"El {rent} sale de {c.num(REC + '.pisos')} anuncios en Airbnb de hasta 2 habitaciones, no de pisos en venta. La superficie es un supuesto.",
        "Si se cuentan como cero los pisos sin días ocupados, los tres siguen. Si también se cuentan así los pisos sin precio, solo sigue el barrio de Ventas.",
        f"La compra es el precio declarado en 2025. Hoy se piden {c.eur(fot + '.compra_mediana_eur')} en Fotocasa y {c.eur(ide_ + '.compra_mediana_eur')} en Idealista. No se midió si cambiarían los barrios.",
        "No se conoce lo que ingresa un bajo.",
        "Una diferencia entre barrios no explica por qué ocurre. No es asesoramiento jurídico.",
    ]
    # Las licencias son contexto: una licencia no se une a un anuncio, así que no prueban que un bajo rinda más.
    acciones = ci.acciones(c)
    acciones[0] = {**acciones[0], "por_que": f"Lo pide la norma; como contexto, {c.num(PLANTA + '.licencias')} de las {c.num(PLANTA + '.de')} licencias municipales incluyen planta baja, aunque una licencia no se puede unir a un anuncio."}
    anexo = {
        "tablas": "Anuncios de Inside Airbnb del 14/12/2025, 24/03/2026, 20/06/2026 y 17/09/2026; calendario y reseñas de la última; precio y superficie oficiales de 2025; límite del centro histórico y licencias del Ayuntamiento de Madrid.",
        "pasos": ("Se limpiaron y unieron los datos, se calculó la rentabilidad de cada piso, ingreso anual entre compra, y se repitió el cálculo 12 veces cambiando la estancia mínima, el mínimo de anuncios o la fecha del precio. "
                  "La rentabilidad se calcula piso a piso: dividir las dos medianas no da la misma cifra. Las cinco pruebas quitan los pisos de temporada, a los anfitriones con 10 anuncios o más y los precios a más de 60 días, dejan solo 1 y 2 habitaciones o cuentan como cero los pisos sin días estimados."),
        "base": [
            f"Línea base por piso, en mediana: compra de {c.eur(REC + '.compra_eur')} e ingreso de {c.eur(REC + '.ingreso_anual_eur')} al año.",
            "Supuestos usados: la superficie de cada piso y los días ocupados estimados.",
            "Faltan gastos, impuestos, comunidad, limpieza, comisiones y el coste del proyecto, que no están en los datos.",
            "No se calcula lo que ganaría la inversión hasta tener esos datos y el número de pisos que se comprarían.",
        ],
        "datos": ("Son datos públicos. Antes del análisis se suprimieron, sin sustituirlas por códigos, las columnas que identifican al anfitrión, los enlaces, las fotos, los textos y el número de licencia. "
                  "Quedan el número del anuncio, las coordenadas desplazadas hasta 150 m y el recuento de anuncios por anfitrión."),
        "fichero": "Cada cifra tiene su rastro en el fichero de cálculos del caso.",
        "fuentes": ci.ATRIBUCION + ["Plan RESIDE, BOCM 226 de 22/09/2025."],
    }
    return {"titulo": titulo, "decide": decide, "conclusiones": conclusiones, "detalle": detalle, "filas": filas, "limites": limites, "acciones": acciones, "anexo": anexo}


# =====================================================================================================================
# 3. Montaje
# =====================================================================================================================

def lista(items, etiqueta="ul"):
    """Monta una lista con sus marcas; los textos ya vienen con su negrita."""
    return f"<{etiqueta}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{etiqueta}>"


def tabla(filas):
    """Monta la Tabla 1, con los números a la derecha."""
    cab = ["Barrio", "Veces en la lista (de 5)", "Anuncios", "Rentabilidad (%)", "Uno de cada cuatro rinde menos de (%)", "En el máximo de días (%)", "Sin días estimados (%)"]
    num = [False, False, True, True, True, True, True]
    clase = lambda n: ' class="num"' if n else ""
    th = "".join(f"<th{clase(n)}>{t}</th>" for t, n in zip(cab, num))
    td = "".join("<tr>" + "".join(f"<td{clase(n)}>{v}</td>" for v, n in zip(f, num)) + "</tr>" for f in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{td}</tbody></table>"


def montar(t, c, emision):
    """Monta el HTML A4 y devuelve el documento y el texto de cada apartado."""
    fecha = ci.fecha_es(c.dato("fecha_datos"))
    meta = f"Informe para la dirección. Datos de anuncios de Airbnb del {fecha}. Emisión: {emision}."
    sello = "Preliminar: primera criba, sin gastos ni visitas a los pisos. Depende de los pisos que llegan al máximo de 255 días ocupados."
    aprobar = f"<p>Se pide aprobar {ci.numero(len(t['acciones']))} acciones, en este orden:</p>" + lista([a["nombre"] for a in t["acciones"]], "ol")
    resumen = (f'<h2>Qué se decide</h2><p class="decide">{t["decide"]}</p><h2>Conclusiones ejecutivas</h2>{lista(t["conclusiones"])}{aprobar}')
    pie = f"Tabla 1. Rentabilidad: mediana de cada barrio, con pisos de cualquier tamaño. Pisos sin días estimados: {c.pct(Q3 + '.pisos_fuera_sin_ocupacion.pct')} en todos los pisos fuera del centro histórico. Fuente: Inside Airbnb y Ayuntamiento de Madrid, datos del 17/09/2026."
    detalle = "<h2>Detalle de las conclusiones</h2>" + lista(t["detalle"]) + tabla(t["filas"]) + f'<p class="nota">{pie}</p>'
    limites = "<h3>Límites</h3>" + lista(t["limites"])
    recomendaciones = "<h3>Recomendaciones</h3>" + lista([f"<b>{a['nombre']}.</b> {a['que']} Quién: {a['quien']}; {a['cuando']}. Motivo: {a['por_que'][0].lower() + a['por_que'][1:]}" for a in t["acciones"]], "ol")
    x = t["anexo"]
    anexo = ('<section class="anexo"><h2>Anexo: trabajo realizado</h2>'
             f"<h3>Base para el caso de negocio</h3>{lista(x['base'])}"
             f"<h3>Datos usados</h3><p>{x['tablas']}</p><h3>Pasos seguidos</h3><p>{x['pasos']}</p>"
             f"<h3>Datos personales</h3><p>{x['datos']}</p><h3>Origen de las cifras</h3><p>{x['fichero']}</p>"
             "<h3>Fuentes externas</h3>" + lista(x["fuentes"], "ol") + "</section>")
    documento = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                 f"<title>Informe ejecutivo</title>\n<style>\n{ESTILO}</style>\n</head>\n<body>\n"
                 f'<h1>{t["titulo"]}</h1><p>{meta}</p><p class="sello">{sello}</p>{resumen}{detalle}{limites}{recomendaciones}{anexo}\n</body>\n</html>\n')
    apartados = {"titulo_y_resumen": f"{t['titulo']} {meta} {sello} {resumen}", "encontrado": detalle, "limites": limites, "recomendaciones": recomendaciones, "anexo": anexo}
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
                 "lector": "equipo directivo", "se_pide": [x["nombre"] for x in t["acciones"]], "acciones": t["acciones"],
                 "palabras_por_apartado": cuenta, "topes": TOPES, "rastro": c.rastro(), "constantes": ci.CONSTANTES}
    if not o.sin_pdf:
        pdf = salida / "informe_ejecutivo.pdf"
        resultado["paginas_pdf"] = comprobar_pdf(pdf) if imprimir_pdf(ruta, pdf) else None
    (salida / "informe_ejecutivo.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Informe ejecutivo en {ruta}. Palabras: {cuenta}. Páginas del PDF: {resultado.get('paginas_pdf', 'sin PDF')}")


if __name__ == "__main__":
    principal()
