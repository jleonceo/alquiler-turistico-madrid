"""Cuadro de mando del caso para el equipo de valoraciones: un HTML que filtra por distrito, barrio y habitaciones.

Lee informes/indicadores.json, data/processed/analisis_anuncios.parquet, data/processed/analisis_barrios.parquet y
data/raw/externos/neighbourhoods.geojson. Deja informes/cuadro_mando.html e informes/cuadro_mando.json.

Depende del orden: se lanza después de scripts/indicadores.py, y para si una entrada es más vieja que el script que la crea.
Para también si una cifra no coincide con indicadores.json, si un total no casa con la suma de sus partes, si entra un dato
de un anuncio suelto, si sale un dato personal, si la fecha de los datos no es la del caso o si cambia la huella de data/.

Datos del HTML: recuentos por barrio y habitaciones, y cifras ya calculadas para cada selección posible de los filtros. Una
selección de menos de 30 pisos guarda solo su recuento: su mediana podría ser el precio de un solo anuncio.

Prueba: tests/probar_cuadro_mando.py.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/cuadro_mando.py
"""
import hashlib
import html
import json
import math
import platform
import re
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))

from graficos import numero  # noqa: E402  (la pieza común vive en assets/)
import cifras_informes as ci  # noqa: E402  (no hace nada al importarse: da el orden de los recomendados, la primera acción y el nombre visible)

# ---------------------------------------------------------------------------
# 1. Configuración
# ---------------------------------------------------------------------------

SCRIPT = "scripts/cuadro_mando.py"
INDICADORES = CASO / "informes" / "indicadores.json"
ANUNCIOS = CASO / "data" / "processed" / "analisis_anuncios.parquet"
BARRIOS = CASO / "data" / "processed" / "analisis_barrios.parquet"
GEOJSON = CASO / "data" / "raw" / "externos" / "neighbourhoods.geojson"
ESTILO = CASO / "assets" / "estilo.css"
SALIDA_HTML = CASO / "informes" / "cuadro_mando.html"
SALIDA_JSON = CASO / "informes" / "cuadro_mando.json"
FECHA_DEL_CASO = "2026-09-17"

# Mínimo de pisos para dar una cifra (reglas §3) y campos que se calculan para cada selección
MINIMO = 30
CAMPOS = {"rent": "rent_valoraciones_pct", "precio": "precio_eur", "ocupacion": "ocupacion_dias",
          "compra": "compra_valoraciones_eur"}
TODOS = "Todos"
TRAMOS = ["0", "1", "2", "3", "4 o más"]
NOMBRE_TRAMO = {"0": "Estudio", "1": "1 habitación", "2": "2 habitaciones", "3": "3 habitaciones", "4 o más": "4 o más habitaciones"}

# Columnas de un anuncio que nunca pueden entrar en los datos del HTML
PROHIBIDAS = {"id", "latitud", "longitud", "anuncios_anfitrion", "distancia_borde_m"}

# Clases del mapa: el orden es el de la leyenda y el de la tabla (reglas §3)
ORDEN_CLASES = ["5 de 5 veces", "4 de 5 veces", "menos de 4 veces", "fuera de la lista", "menos de 30"]
COLOR_CLASE = {"5 de 5 veces": "#2a78d6", "4 de 5 veces": "#eb6834", "menos de 4 veces": "#1baf7a", "fuera de la lista": "#898781", "menos de 30": "url(#rayado)"}

# Nombre para el lector de las cinco pruebas de las reglas §3
PRUEBAS = {"sin_temporada": ("pisos de temporada", "sin los pisos que declaran temporada"), "sin_anfitriones_grandes": ("anfitriones con 10 anuncios o más", "sin los anfitriones con 10 anuncios o más"),
           "sin_cotizaciones_lejanas": ("precios a más de 60 días", "sin los precios para fechas a más de 60 días"), "solo_1_y_2_dormitorios": ("solo 1 y 2 habitaciones", "solo con 1 y 2 habitaciones"),
           "sin_ocupacion_como_cero": ("pisos sin días estimados", "con los pisos sin días estimados contados como cero")}
AVISO_CORTO = {"depende_del_tope": "depende del máximo de días", "pocos_anuncios": "pocos anuncios", "cuartil_bajo": "uno de cada cuatro rinde poco"}

# Definición de cada cifra, de una línea, con las palabras de las reglas §1, §6, §7 y §12
DEFINICIONES = {
    "piso": "Piso: anuncio de una vivienda fuera del centro histórico que cumple los filtros del análisis. Un mismo inmueble puede tener varios anuncios. La planta y el acceso no constan.",
    "precio": "Precio por noche: el publicado en el anuncio, en mediana. Es un precio para unas fechas concretas. No es el precio medio del año.",
    "ocupacion": "Días ocupados: días al año que estima Inside Airbnb, en mediana. Salen de las reseñas del último año, con máximo de 255. No son noches vendidas y es la cifra menos fiable del análisis.",
    "compra": "Precio de compra: superficie del piso por el precio oficial del m² del barrio en 2025, en mediana. La superficie es un supuesto del equipo de valoraciones.",
    "rent": "Rentabilidad bruta: precio por noche por días ocupados, entre precio de compra, en porcentaje y en mediana. No incluye gastos, impuestos, comunidad, limpieza ni comisiones.",
    "cuartil": "Uno de cada cuatro rinde menos de: el 25 % de los anuncios no llega a esa rentabilidad.",
    "clase": "Veces que sigue en la lista: el cálculo se repitió de 5 formas, quitando cada vez un grupo de anuncios. Se recomiendan los barrios que siguen entre los más rentables las 5 veces. La lista reúne los barrios en el 25 % más rentable en más de 6 de 12 repeticiones, que cambian la estancia, el mínimo de anuncios o la fecha del precio.",
    "pruebas": "Las 5 formas de repetir el cálculo: sin los pisos que declaran temporada; sin los anfitriones con 10 anuncios o más; sin los precios para fechas a más de 60 días; solo con 1 y 2 habitaciones; con los pisos sin días estimados contados como cero. Solo se miden en los barrios de la lista.",
    "avisos": "Avisos: depende del máximo si sale de la lista al quitar los pisos que llegan a 255 días; pocos anuncios si tiene 40 o menos; uno de cada cuatro rinde poco si ese corte no supera el de todos los pisos.",
    "distingue": "Cuando no se puede asegurar, la diferencia podría ser cero, con un 95 % de confianza.",
    "minimo": "Mínimo: una selección de menos de 30 pisos no se ordena y no da cifras, solo su recuento.",
}


# ---------------------------------------------------------------------------
# 2. Ayudas
# ---------------------------------------------------------------------------

def exigir(cumple, mensaje):
    """Para el script con un mensaje si no se cumple una condición."""
    if not cumple:
        raise ValueError(mensaje)


def seis(x):
    """Deja un número con seis decimales, los de indicadores.json, redondeando como Excel."""
    return float(Decimal(repr(float(x))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def sha256(ruta):
    """Calcula la huella de un fichero."""
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def huella_de_datos():
    """Calcula una sola huella de todo data/, para saber si el script lo ha tocado."""
    h = hashlib.sha256()
    for ruta in sorted(p for p in (CASO / "data").rglob("*") if p.is_file()):
        h.update(str(ruta.relative_to(CASO)).encode("utf-8"))
        h.update(sha256(ruta).encode("utf-8"))
    return h.hexdigest()


def leer_json(ruta):
    """Lee un JSON en UTF-8."""
    return json.loads(ruta.read_text(encoding="utf-8"))


def entrada_vieja(tiempo_entrada, tiempo_script):
    """Dice si una entrada es más vieja que el script que la crea: daría cifras viejas."""
    return tiempo_entrada < tiempo_script


def comprobar_orden():
    """Para si indicadores.json o la tabla de anuncios son más viejos que el script que los crea."""
    pares = [(INDICADORES, CASO / "scripts" / "indicadores.py"), (ANUNCIOS, CASO / "scripts" / "transformacion_datos.py")]
    for entrada, origen in pares:
        exigir(entrada.exists(), f"falta {entrada.name}")
        exigir(not entrada_vieja(entrada.stat().st_mtime, origen.stat().st_mtime), f"{entrada.name} es más viejo que {origen.name}: hay que lanzar antes lo que lo crea")


def misma_entrada(entradas, ruta, huella):
    """Para si una tabla no es, byte a byte, la que usó indicadores.json.

    Se mira la huella y no la hora: volver a generar una tabla con el mismo contenido cambia la hora y ninguna cifra.
    """
    usada = next((e["sha256"] for e in entradas if e["ruta"] == ruta), None)
    exigir(usada is not None, f"indicadores.json no dice qué {ruta} usó")
    exigir(usada == huella, f"{ruta} no es la tabla que usó indicadores.json: hay que lanzar antes scripts/indicadores.py")


def comprobar_fecha(fecha, esperada):
    """Para si la fecha de los datos no es la de referencia del caso."""
    exigir(fecha == esperada, f"la fecha de los datos es {fecha} y la del caso es {esperada}")


def lista_y(nombres):
    """Escribe una lista con comas y una «y» final."""
    nombres = list(nombres)
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def fecha_espanola(iso):
    """Pasa una fecha de AAAA-MM-DD a DD/MM/AAAA."""
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# 3. Agregados por selección de los filtros
# ---------------------------------------------------------------------------

def tramo_dormitorios(x):
    """Agrupa las habitaciones en 0, 1, 2, 3 y «4 o más», los mismos grupos de indicadores.json."""
    return "4 o más" if x >= 4 else str(int(x))


def clave(distrito, barrio, dormitorios):
    """Construye la clave de una selección: un barrio manda sobre su distrito."""
    ambito = f"B:{barrio}" if barrio != TODOS else (f"D:{distrito}" if distrito != TODOS else TODOS)
    return f"{ambito}|{dormitorios}"


def cifras_de(t):
    """Calcula las cifras de una selección; con menos de 30 pisos solo da el recuento (reglas §3 y §9)."""
    salida = {"pisos": len(t)}
    if len(t) < MINIMO:
        return salida
    for nombre, columna in CAMPOS.items():
        salida[nombre] = seis(t[columna].median())
    salida["cuartil"] = seis(t[CAMPOS["rent"]].quantile(0.25))
    return salida


def agregar(d, distritos):
    """Calcula cada selección posible y las celdas de barrio y habitaciones con su recuento.

    Una mediana no se puede sumar: por eso cada selección se calcula sobre sus pisos y el navegador solo la busca.
    """
    t = d.assign(tramo=d["dormitorios"].map(tramo_dormitorios))
    selecciones = {}
    # Cada distrito, cada barrio y la ciudad entera, cada uno con todos los dormitorios y con cada grupo
    ambitos = [(TODOS, TODOS, t)]
    for distrito, barrios in distritos.items():
        ambitos.append((distrito, TODOS, t[t["barrio"].isin(barrios)]))
        ambitos += [(distrito, b, t[t["barrio"].eq(b)]) for b in barrios]
    for distrito, barrio, parte in ambitos:
        if len(parte):
            selecciones[clave(distrito, barrio, TODOS)] = cifras_de(parte)
        for tramo, grupo in parte.groupby("tramo"):
            selecciones[clave(distrito, barrio, tramo)] = cifras_de(grupo)
    # Las celdas no llevan más que barrio, dormitorios y recuento
    cuenta = t.groupby(["barrio", "tramo"]).size().reset_index(name="pisos").sort_values(["barrio", "tramo"])
    celdas = [[str(f.barrio), str(f.tramo), int(f.pisos)] for f in cuenta.itertuples()]
    return selecciones, celdas


def resumen(datos, distrito, barrio, dormitorios):
    """Da las cifras de una selección; la que no tiene pisos no se guarda y vale cero."""
    return datos["selecciones"].get(clave(distrito, barrio, dormitorios), {"pisos": 0})


def suma_celdas(datos, distrito, barrio, dormitorios):
    """Suma los recuentos de las celdas de una selección."""
    if barrio != TODOS:
        barrios = {barrio}
    elif distrito != TODOS:
        barrios = set(datos["distritos"][distrito])
    else:
        barrios = {b for lista in datos["distritos"].values() for b in lista}
    return sum(c[2] for c in datos["celdas"] if c[0] in barrios and dormitorios in (TODOS, c[1]))


# ---------------------------------------------------------------------------
# 4. Comprobaciones
# ---------------------------------------------------------------------------

def comprobar_totales(datos):
    """Para si el total de una selección no casa con la suma de sus celdas."""
    for k, v in datos["selecciones"].items():
        ambito, dormitorios = k.split("|")
        distrito, barrio = TODOS, TODOS
        if ambito.startswith("D:"):
            distrito = ambito[2:]
        elif ambito.startswith("B:"):
            barrio = ambito[2:]
        suma = suma_celdas(datos, distrito, barrio, dormitorios)
        exigir(suma == v["pisos"], f"{k}: el total es {v['pisos']} y sus celdas suman {suma}")


def comparar(datos, esperadas):
    """Compara cifras del cuadro con su fuente; `esperadas` son filas de (clave, campo, valor, nombre)."""
    for k, campo, valor, nombre in esperadas:
        exigir(k in datos["selecciones"] and campo in datos["selecciones"][k], f"{nombre}: {k} no da {campo} en el cuadro")
        propio = datos["selecciones"][k][campo]
        exigir(abs(propio - valor) <= 2e-4 if campo.startswith("compra") else abs(propio - valor) <= 2e-6, f"{nombre}: el cuadro da {propio} y la fuente {valor}")
    return len(esperadas)


def cifras_a_comparar(ind, distritos):
    """Reúne las cifras que el cuadro repite de indicadores.json, cada una con su clave.

    Las fuentes escriben distinto tres distritos («Moncloa-Aravaca» y «Moncloa - Aravaca»): se casan sin los espacios.
    """
    nombre_distrito = {d.replace(" ", ""): d for d in distritos}
    p = {q["id"]: q for q in ind["preguntas"]}
    s = {x["id"]: x["base_decision"]["datos"] for x in ind["las_16"]}
    salida = [("Todos|Todos", "pisos", p["P1"]["poblacion"]["filas"], "pisos de la base")]
    cifras_p1 = {c["nombre"]: c["valor"] for c in p["P1"]["cifras"]}
    salida.append(("Todos|Todos", "rent", cifras_p1["rentabilidad de toda la base: mediana"], "rentabilidad de la base"))
    salida.append(("Todos|Todos", "cuartil", cifras_p1["rentabilidad de toda la base: q25"], "cuartil bajo de la base"))
    salida.append(("Todos|Todos", "precio", s["S01"]["global"]["mediana"], "precio de la base"))
    salida.append(("Todos|Todos", "ocupacion", s["S07"]["global"]["mediana"], "ocupación de la base"))
    # Filas de dormitorios y de barrios
    for f in p["P1"]["dormitorios"]["tabla"]:
        k = f"Todos|{f['grupo']}"
        salida += [(k, "pisos", f["pisos"], f"pisos de {f['grupo']}"), (k, "rent", f["rentabilidad_mediana_pct"], f"rentabilidad de {f['grupo']}"),
                   (k, "cuartil", f["cuartil_bajo_pct"], f"cuartil de {f['grupo']}")]
    for f in p["P2"]["tabla_barrios"]:
        k = f"B:{f['barrio']}|Todos"
        salida += [(k, "pisos", f["pisos"], f"pisos de {f['barrio']}"), (k, "rent", f["rentabilidad_mediana_pct"], f"rentabilidad de {f['barrio']}"),
                   (k, "cuartil", f["cuartil_bajo_pct"], f"cuartil de {f['barrio']}")]
    # Precio, ocupación y compra por distrito y por barrio
    for pregunta, campo in (("S01", "precio"), ("S07", "ocupacion")):
        salida += [(f"D:{f['grupo']}|Todos", campo, f["mediana"], f"{campo} de {f['grupo']}") for f in s[pregunta]["por_distrito"]]
        salida += [(f"B:{f['grupo']}|Todos", campo, f["mediana"], f"{campo} de {f['grupo']}") for f in s[pregunta]["por_barrio"]]
    salida += [(f"D:{nombre_distrito[f['distrito'].replace(' ', '')]}|Todos", "compra", f["compra_mediana_valoraciones_eur"], f"compra de {f['distrito']}")
               for f in s["S14"]["distritos"] if f["anuncios_de_la_base"] >= MINIMO]
    return salida


def comprobar_grupos(datos, ind):
    """Para si los recuentos del grupo y de los barrios comparados no son los de indicadores.json."""
    p2 = next(q for q in ind["preguntas"] if q["id"] == "P2")
    pisos = lambda barrios: sum(resumen(datos, TODOS, b, TODOS)["pisos"] for b in barrios)
    exigir(pisos(p2["grupo"]) == p2["pisos_del_grupo"], "los pisos del grupo no coinciden")
    exigir(pisos(p2["firmes"]) == p2["pisos_del_grupo_firme"], "los pisos del grupo recomendado no coinciden")
    exigir(pisos(f["barrio"] for f in p2["tabla_barrios"]) == p2["referencia"]["filas"], "los pisos de los barrios comparados no coinciden")
    exigir(len({c[0] for c in datos["celdas"]}) == p2["cobertura"]["barrios_con_pisos"], "los barrios con pisos no coinciden")


def sin_anuncios_sueltos(datos):
    """Para si en los datos del HTML entra algo de un anuncio: una columna suya o una cifra de menos de 30 pisos."""
    for k, v in datos["selecciones"].items():
        exigir(not set(v) & PROHIBIDAS, f"{k}: lleva una columna de anuncio")
        exigir(v["pisos"] >= MINIMO or set(v) == {"pisos"}, f"{k}: tiene {v['pisos']} pisos y lleva cifras")
    exigir(all(len(c) == 3 for c in datos["celdas"]), "una celda trae algo más que barrio, habitaciones y recuento")


def buscar_datos_personales(texto):
    """Para si el HTML lleva algo con forma de correo, DNI, teléfono o IBAN."""
    patrones = {"correo": r"[\w.+-]+@[\w-]+\.[\w.]+", "DNI": r"\b\d{8}[A-HJ-NP-TV-Z]\b", "teléfono": r"\b[6-9]\d{8}\b", "IBAN": r"\bES\d{22}\b"}
    for nombre, patron in patrones.items():
        exigir(not re.search(patron, texto), f"el HTML lleva algo con forma de {nombre}")


# ---------------------------------------------------------------------------
# 5. Mapa
# ---------------------------------------------------------------------------

def anillos(geometria):
    """Devuelve los anillos de un MultiPolygon."""
    return [anillo for poligono in geometria["coordinates"] for anillo in poligono]


def centroide(anillo):
    """Calcula el centro de un anillo con la fórmula del área; con área nula, la media de sus puntos."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(anillo, anillo[1:]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if a == 0:
        return sum(p[0] for p in anillo) / len(anillo), sum(p[1] for p in anillo) / len(anillo)
    return cx / (3 * a), cy / (3 * a)


def mapa_svg(geo, clases, distrito_de, grupo, alto=360, margen=190):
    """Dibuja los barrios por clase, con un trazado por barrio y el nombre de los del grupo a los lados con una línea.

    Los nombres van fuera del dibujo porque los barrios del grupo están pegados y dentro se pisarían.
    """
    nombres = {f["properties"]["neighbourhood"] for f in geo["features"]}
    exigir(set(clases) == nombres, f"barrios sin límite o sin clase: {sorted(set(clases) ^ nombres)}")
    # Proyección plana: a la latitud de Madrid un grado de longitud mide lo que dice su coseno
    puntos = [p for f in geo["features"] for a in anillos(f["geometry"]) for p in a]
    lon0, lon1 = min(p[0] for p in puntos), max(p[0] for p in puntos)
    lat0, lat1 = min(p[1] for p in puntos), max(p[1] for p in puntos)
    escala = (alto - 8) / (lat1 - lat0)
    coseno = math.cos(math.radians((lat0 + lat1) / 2))
    ancho_mapa = (lon1 - lon0) * coseno * escala
    ancho = ancho_mapa + 2 * margen

    def proyectar(p):
        """Pasa un punto de longitud y latitud a píxeles del SVG."""
        return margen + (p[0] - lon0) * coseno * escala, 4 + (lat1 - p[1]) * escala

    trazados, centros = [], {}
    for f in sorted(geo["features"], key=lambda x: ORDEN_CLASES.index(clases[x["properties"]["neighbourhood"]]), reverse=True):
        barrio = f["properties"]["neighbourhood"]
        partes = []
        for anillo in anillos(f["geometry"]):
            plano = [(round(x, 1), round(y, 1)) for x, y in map(proyectar, anillo)]
            sin_repetir = [p for i, p in enumerate(plano) if i == 0 or p != plano[i - 1]]
            # La coma separa x de y: con un espacio, un par de coordenadas se lee como un número de identidad.
            partes.append("M" + "L".join(f"{x},{y}" for x, y in sin_repetir) + "Z")
        mayor = max(anillos(f["geometry"]), key=len)
        centros[barrio] = proyectar(centroide(mayor))
        trazados.append(f'<path d="{"".join(partes)}" fill="{COLOR_CLASE[clases[barrio]]}" data-barrio="{html.escape(barrio)}" data-distrito="{html.escape(distrito_de.get(barrio, ""))}" data-clase="{clases[barrio]}" tabindex="0"/>')
    # Nombres de los barrios del grupo: a cada lado, de arriba abajo, sin pisarse
    rotulos = []
    for lado in ("izquierda", "derecha"):
        mitad = margen + ancho_mapa / 2
        presentes = sorted((b for b in grupo if (centros[b][0] < mitad) == (lado == "izquierda")), key=lambda b: centros[b][1])
        y_previa = -100.0
        colocados = []
        for b in presentes:
            y = max(centros[b][1], y_previa + 20)
            colocados.append((b, y))
            y_previa = y
        # Si la columna se sale por abajo, sube entera
        exceso = max(0.0, (colocados[-1][1] if colocados else 0) - (alto - 8))
        for b, y in colocados:
            x_texto = margen - 14 if lado == "izquierda" else margen + ancho_mapa + 14
            ancla = "end" if lado == "izquierda" else "start"
            cx, cy = centros[b]
            rotulos.append(f'<line x1="{x_texto:.1f}" y1="{y - exceso:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" stroke="#0b0b0b" stroke-width="0.7"/>'
                           f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2" fill="#0b0b0b"/>'
                           f'<text x="{x_texto + (-4 if lado == "izquierda" else 4):.1f}" y="{y - exceso + 4:.1f}" text-anchor="{ancla}" font-size="13" fill="#0b0b0b" data-rotulo="{html.escape(b)}">{html.escape(ci.barrio(b))}</text>')
    rayado = '<defs><pattern id="rayado" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="#898781" stroke-width="1"/></pattern></defs>'
    return (f'<svg id="mapa" viewBox="0 0 {ancho:.0f} {alto}" width="{ancho:.0f}" height="{alto}" role="img" aria-label="Mapa de los barrios de Madrid por clase">{rayado}'
            f'<g stroke="#ffffff" stroke-width="0.6" fill-rule="evenodd">{"".join(trazados)}</g>{"".join(rotulos)}</svg>')


# ---------------------------------------------------------------------------
# 6. Datos del HTML
# ---------------------------------------------------------------------------

def fichas_de_barrios(ind):
    """Prepara lo que la tabla dice de cada barrio con 30 pisos o más: clase, pruebas y avisos."""
    p2 = next(q for q in ind["preguntas"] if q["id"] == "P2")
    fichas = {}
    for f in p2["tabla_barrios"]:
        en_grupo = "pruebas_que_aguanta" in f
        avisos = []
        if en_grupo:
            # Los dos recuentos de avisos tienen que casar: si no, un aviso se perdería sin decirlo
            activos = [k for k, v in f["avisos_del_barrio"].items() if v]
            exigir(len(activos) == len(f["avisos_en_texto"]), f"{f['barrio']}: los avisos no casan con su texto")
            avisos = [{"corto": AVISO_CORTO[k], "texto": t} for k, t in zip(activos, f["avisos_en_texto"])]
            exigir(all(a["texto"].startswith(a["corto"]) for a in avisos), f"{f['barrio']}: un aviso corto no es el de su texto")
        fichas[f["barrio"]] = {"clase": f["clase"], "en_grupo": en_grupo, "aguanta": len(f.get("pruebas_que_aguanta", [])),
                               "no_aguanta": [{"corto": PRUEBAS[x][0], "texto": PRUEBAS[x][1]} for x in f.get("pruebas_que_no_aguanta", [])], "avisos": avisos}
    return fichas


def clases_del_mapa(barrios, fichas):
    """Da la clase de cada barrio de Madrid: la suya si tiene 30 pisos o más; si no, «menos de 30»."""
    return {b: fichas[b]["clase"] if b in fichas else "menos de 30" for b in barrios}


def textos(ind):
    """Monta los textos de las pestañas desde indicadores.json, cada frase con la condición que la sostiene."""
    p = {q["id"]: q for q in ind["preguntas"]}
    sens, p2, p3 = p["P1"]["sensibilidad_superficie"], p["P2"], p["P3"]
    r, rango, firme = ind["recomendacion"], p3["rango_de_rentabilidad_del_grupo_firme"], p3["rentabilidad_del_grupo_firme"]
    exigir(sorted(p2["firmes"]) == sorted(ci.FIRMES), "la recomendación espera los tres barrios recomendados de los informes")
    exigir(p2["pisos_del_grupo_firme"] == firme["casos"], "el grupo recomendado tiene dos recuentos")
    pct = lambda x, d=1: numero(x, d, " %")
    pb = ind["licencias_y_registro"]["planta_baja"]
    q = p2["que_ordena_la_lista"]
    # Lo que debilita la conclusión va arriba (D2), y solo si es cierto de todos los barrios recomendados
    fichas = {f["barrio"]: f for f in p3["fichas_del_grupo"]}
    fichas_p2 = {f["barrio"]: f for f in p2["fichas_del_grupo"]}
    depende = all(fichas_p2[b]["avisos_del_barrio"]["depende_del_tope"] for b in ci.FIRMES)
    u = {x["barrio"]: x for x in p2["con_un_ano_o_mas"]["barrios"]}
    # El título del gráfico concluye solo si, de verdad, no hay un tipo que gane en todas las combinaciones
    sin_ganador = sens["cambia"] and len(sens["tipos_que_aparecen"]) > 1
    return {"titulo_recomendacion": f"Pisos de hasta {numero(r['dormitorios_hasta'])} habitaciones en los barrios de {lista_y(ci.FIRMES)}",
            "recomendacion": f"Son {numero(r['pisos'])} anuncios. Rentabilidad bruta del {pct(r['rentabilidad_pct'])} en mediana, sin gastos. Se recomiendan porque se mantienen al repetir el cálculo, no porque rindan más.",
            "limite": f"Dice dónde buscar, no si un piso se puede alquilar a turistas. Primera acción: {ci.acciones(ci.Cifras(INDICADORES))[0]['nombre']}.",
            "titulo_dormitorios": "Sin ganador entre estudio, una y dos" if sin_ganador else "Rentabilidad bruta por habitaciones",
            "titulo_barrios": f"{len(p2['grupo'])} barrios forman la lista y {len(p2['firmes'])} siguen en ella las 5 veces",
            "tabla_recomendacion": [["Recomendados de hasta 2 habitaciones", "Cifra"], ["Anuncios en Airbnb", numero(r["pisos"])], ["Compra por piso", numero(r["compra_eur"], 0, " €")], ["Ingreso anual por piso", numero(r["ingreso_anual_eur"], 0, " €")],
                                    ["Licencias con planta baja", f"{numero(pb['licencias'])} de {numero(pb['de'])}"], ["Licencias con planta baja, barrios recomendados", f"{numero(pb['firmes']['licencias'])} de {numero(pb['firmes']['de'])}"], ["Rentabilidad de los barrios de m² más barato", pct(q["m2_baratos"]["mediana_pct"])]],
            "nota_recomendacion": f"Con los precios que piden hoy Fotocasa e Idealista, la compra sube a {numero(r['precio_de_mercado']['fuentes'][0]['compra_mediana_eur'], 0, ' €')} y {numero(r['precio_de_mercado']['fuentes'][1]['compra_mediana_eur'], 0, ' €')}, y la rentabilidad baja a {pct(r['precio_de_mercado']['fuentes'][0]['rentabilidad_mediana_pct'])} y {pct(r['precio_de_mercado']['fuentes'][1]['rentabilidad_mediana_pct'])}. Con todos los pisos de estos barrios, va del {pct(rango['minimo'])} al {pct(rango['maximo'])} según la fecha del precio. Conviene empezar por bajos y primeras plantas con acceso independiente. Lo que ingresa un bajo no se conoce, porque los datos mezclan todas las plantas. Qué norma rige en cada barrio se pregunta en el Ayuntamiento antes de comprar. "
                                  f"Entre barrios, la rentabilidad va más ligada a los días ocupados ({numero(q['rentabilidad_con_ocupacion'], 2)}) que al precio del m² ({numero(q['rentabilidad_con_m2'], 2)}). Los días ocupados son la cifra menos fiable.",
            "texto_mapa": f"El barrio de Numancia rinde más que la mediana de todos los pisos. En los barrios de Ventas y San Diego no se puede asegurar. <button class=\"def\" type=\"button\" data-def=\"distingue\">Qué significa</button>",
            "tabla_mapa": [["Recomendados", "Peor 25 % rinde menos de", "Sin días estimados", "Puesto, un año o más"]] + [[b, pct(fichas[b]["cuartil_bajo_pct"]), pct(fichas[b]["pisos_fuera_sin_ocupacion_pct"]), f"{numero(u[b]['puesto'])}.ª de {numero(p2['con_un_ano_o_mas']['barrios_comparados'])}"] for b in ci.FIRMES] + [["Todos los pisos", pct(p2["cuartil_bajo_de_toda_la_base"], 2), pct(p3["pisos_fuera_sin_ocupacion"]["pct"]), "—"]],
            "nota_mapa": f"Los barrios de Casco Histórico de Vallecas y Opañel rinden más, pero el {pct(p2['operadores_grandes']['con_aviso_pct'], 0)} de sus anuncios es de anfitriones con 10 anuncios o más. El puesto cuenta solo anuncios de un año o más, porque uno más nuevo parece menos ocupado.",
            "texto_barrios": ("Los tres recomendados salen de la lista al quitar los pisos que llegan a 255 días. " if depende else "") + "El barrio de Puerta del Ángel sale en las 5 formas de repetir el cálculo."}


def titulo_mapa():
    """Nombra los barrios recomendados, en el orden de los informes."""
    return f"Los barrios recomendados son {lista_y(ci.FIRMES)}"


def tabla_fija(cabecera, filas):
    """Escribe una tabla que no cambia con los filtros; la primera columna es el rótulo y las demás, cifras."""
    cab = "".join(f'<th{" class=\"num\"" if i else ""}>{html.escape(c)}</th>' for i, c in enumerate(cabecera))
    cuerpo = "".join("<tr>" + "".join(f'<td{" class=\"num\"" if i else ""}>{html.escape(str(v))}</td>' for i, v in enumerate(f)) + "</tr>" for f in filas)
    return f"<table><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table>"


def comprobar_recomendacion(anuncios, ind):
    """Para si la cifra de la recomendación no sale de los pisos de hasta 2 habitaciones de los recomendados."""
    p2 = next(q for q in ind["preguntas"] if q["id"] == "P2")
    t = anuncios[anuncios["base_decision"] & anuncios["barrio"].isin(p2["firmes"]) & anuncios["dormitorios"].le(2)]
    r = ind["recomendacion"]
    exigir(len(t) == r["pisos"], "los pisos de la recomendación no coinciden")
    for clave_r, columna in (("rentabilidad_pct", "rent_valoraciones_pct"), ("compra_eur", "compra_valoraciones_eur"), ("ingreso_anual_eur", "ingreso_anual_eur")):
        exigir(abs(seis(t[columna].median()) - r[clave_r]) <= 2e-4, f"{clave_r} no coincide con indicadores.json")


def preparar_datos(ind, anuncios, barrios):
    """Reúne todo lo que el navegador necesita para filtrar sin volver a Python."""
    distritos = {d: sorted(g["barrio"]) for d, g in barrios.groupby("distrito")}
    selecciones, celdas = agregar(anuncios[anuncios["base_decision"]], distritos)
    return {"fecha_datos": ind["fecha_datos"], "fecha_texto": fecha_espanola(ind["fecha_datos"]), "minimo": MINIMO,
            "distritos": distritos, "tramos": [[t, NOMBRE_TRAMO[t]] for t in TRAMOS], "selecciones": selecciones, "celdas": celdas,
            "barrios": fichas_de_barrios(ind), "definiciones": DEFINICIONES, "nombres": ci.NOMBRE_VISIBLE}


# ---------------------------------------------------------------------------
# 7. HTML
# ---------------------------------------------------------------------------

CSS = """
/* El cuadro va sin panel lateral: las pestañas ocupan la fila de arriba (CM1). */
main { margin: 0; padding: 0 24px; max-width: none; }
.pagina { max-width: 1300px; }
h1 { margin: 10px 0 6px; font-size: 24px; }
.barra { display: flex; align-items: baseline; gap: 28px; padding: 8px 24px 0; }
.barra .nombre { font-weight: 700; font-size: 16px; }
.barra .fecha { margin-left: auto; font-size: 13px; color: #52514e; }
.pestanas { display: flex; gap: 20px; }
.pestanas button { font: inherit; background: none; border: 0; padding: 2px 0; cursor: pointer; color: #0b0b0b; }
.pestanas button[aria-selected="true"] { font-weight: 700; text-decoration: underline; }
.filtros { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; padding: 6px 24px; font-size: 13px; border-bottom: 1px solid #e1e0d9; }
.filtros select { font: inherit; max-width: 200px; }
#viendo { margin: 0; font-size: 13px; }
#quitar { font: inherit; font-size: 13px; margin-left: 8px; }
.cifras { margin: 6px 0 6px; gap: 24px; }
button.cifra-clave { all: unset; display: block; cursor: pointer; min-width: 0; }
.cifra-clave span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cifra-clave .etiqueta { text-decoration: underline dotted; }
button.cifra-clave:focus-visible, button.def:focus-visible { outline: 2px solid #0b0b0b; }
.definicion { margin: 0 0 8px; font-size: 13px; max-width: 110ch; }
.definicion[hidden] { display: none; }
.pagina p.texto { margin: 0 0 6px; max-width: 110ch; }
.pagina p.limite { font-weight: 600; }
.grafico { margin: 8px 0 0; }
.g-titulo { font-size: 18px; }
.g-subtitulo { font-size: 13px; margin: 0 0 4px; }
.lado-mapa { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 16px; align-items: start; }
.leyenda { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 13px; margin: 6px 0; }
.leyenda svg { vertical-align: -1px; margin-right: 4px; }
#mapa { display: block; max-width: 100%; height: auto; }
#mapa path { cursor: default; }
#mapa path.apagado { opacity: 0.15; }
#mapa path:focus { outline: none; stroke: #0b0b0b; stroke-width: 1.5; }
.lado-reco { display: grid; grid-template-columns: minmax(0, 640px) minmax(0, 1fr); gap: 28px; align-items: start; }
.fija table { margin: 0 0 4px; width: 100%; font-size: 13px; }
.fija td, .fija th { padding: 1px 8px 1px 0; }
.fija .g-fuente { margin: 4px 0 6px; max-width: none; }
.tabla-larga { max-height: calc(100vh - 402px); min-height: 150px; overflow: auto; margin-top: 4px; }
.tabla-larga table { margin: 0; width: 100%; }
.tabla-larga th { position: sticky; top: 0; background: #ffffff; z-index: 1; }
.tabla-larga td:nth-child(2) { white-space: nowrap; }
.tabla-larga td { padding-top: 3px; padding-bottom: 3px; }
button.def { all: unset; font-weight: 700; text-decoration: underline dotted; cursor: pointer; }
tr.total td { position: sticky; bottom: 0; background: #ffffff; }
.g-fuente { margin: 6px 0 4px; }
svg .dato:focus { outline: none; stroke: #0b0b0b; }
"""

CUERPO = """
<div id="cuadro" data-estado="cargando">
<div class="barra">
  <span class="nombre">Mercado turístico de Madrid</span>
  <div class="pestanas" role="tablist">
    <button role="tab" id="t-recomendacion" aria-controls="p-recomendacion" data-pestana="recomendacion">Recomendación</button>
    <button role="tab" id="t-mapa" aria-controls="p-mapa" data-pestana="mapa">Mapa</button>
    <button role="tab" id="t-barrios" aria-controls="p-barrios" data-pestana="barrios">Barrios</button>
  </div>
  <span class="fecha">Datos del __FECHA__</span>
</div>
<div class="filtros">
  <label>Distrito <select id="f-distrito"></select></label>
  <label>Barrio <select id="f-barrio"></select></label>
  <label>Habitaciones <select id="f-dorm"></select></label>
  <p id="viendo"><span id="viendo-texto"></span><button id="quitar" type="button">Quitar filtros</button></p>
</div>
<main>
<section class="pagina" id="p-recomendacion" role="tabpanel" aria-labelledby="t-recomendacion">
  <h1>__TITULO_RECOMENDACION__</h1>
  <p class="texto">__RECOMENDACION__</p>
  <p class="texto limite">__LIMITE__</p>
  <div class="cifras" id="cifras-recomendacion"></div>
  <p class="definicion" id="def-recomendacion" hidden></p>
  <div class="lado-reco">
    <div class="grafico" id="g-dormitorios">
      <p class="g-titulo" id="g-dormitorios-titulo"></p>
      <p class="g-subtitulo">Mediana de rentabilidad en %; en gris, menos de 30 pisos</p>
      <div id="g-dormitorios-dibujo"></div>
      <p class="g-fuente">__FUENTE__</p>
    </div>
    <div class="fija">__TABLA_RECOMENDACION__<p class="g-fuente">__NOTA_RECOMENDACION__</p></div>
  </div>
</section>
<section class="pagina" id="p-mapa" role="tabpanel" aria-labelledby="t-mapa" hidden>
  <h1>__TITULO_MAPA__</h1>
  <p class="texto">__TEXTO_MAPA__</p>
  <div class="cifras" id="cifras-mapa"></div>
  <p class="definicion" id="def-mapa" hidden></p>
  <div class="lado-mapa">
    __MAPA__
    <div>
      <p class="g-subtitulo">Veces que cada barrio sigue en la lista al repetir el cálculo de 5 formas.</p>
      <div class="leyenda">__LEYENDA__</div>
      <div class="fija">__TABLA_MAPA__<p class="g-fuente">__NOTA_MAPA__</p></div>
      <p class="g-fuente">__FUENTE__</p>
    </div>
  </div>
</section>
<section class="pagina" id="p-barrios" role="tabpanel" aria-labelledby="t-barrios" hidden>
  <h1>__TITULO_BARRIOS__</h1>
  <p class="texto">__TEXTO_BARRIOS__</p>
  <div class="cifras" id="cifras-barrios"></div>
  <p class="definicion" id="def-barrios" hidden></p>
  <p class="g-subtitulo" id="barrios-subtitulo"></p>
  <div class="tabla-larga" tabindex="0"><table id="tabla-barrios"></table></div>
  <p class="g-fuente">__FUENTE__</p>
</section>
</main>
<div class="etiqueta-dato" id="etiqueta" hidden></div>
</div>
"""

JS = r"""
"use strict";
// ---- Constantes y estado ----
const D = JSON.parse(document.getElementById("datos").textContent);
const AZUL = "#2a78d6", TODOS = "Todos", MIN = D.minimo;
const ORDEN_CLASE = {"5 de 5 veces": 0, "4 de 5 veces": 1, "menos de 4 veces": 2, "fuera de la lista": 3};
const estado = {pestana: "recomendacion", distrito: TODOS, barrio: TODOS, dorm: TODOS};
const $ = id => document.getElementById(id);
const PESTANAS = ["recomendacion", "mapa", "barrios"];
const BARRIO_DISTRITO = {};
Object.entries(D.distritos).forEach(([d, bs]) => bs.forEach(b => { BARRIO_DISTRITO[b] = d; }));

// ---- Números y textos a la española, con el redondeo de Excel ----
function num(x, dec = 0) {
  const f = Math.pow(10, dec);
  const r = Math.round(Math.abs(x) * f + 1e-9) / f;
  const [e, d] = r.toFixed(dec).split(".");
  const m = e.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return (x < 0 ? "−" : "") + m + (d ? "," + d : "");
}
const eur = x => num(x) + " €", pct = x => num(x, 1) + " %";
const esc = t => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// ---- Selección ----
function clave(distrito, barrio, dorm) {
  const ambito = barrio !== TODOS ? "B:" + barrio : (distrito !== TODOS ? "D:" + distrito : TODOS);
  return ambito + "|" + dorm;
}
const seleccion = (dorm = estado.dorm) => D.selecciones[clave(estado.distrito, estado.barrio, dorm)] || {pisos: 0};
function barriosVistos() {
  if (estado.barrio !== TODOS) return [estado.barrio];
  if (estado.distrito !== TODOS) return D.distritos[estado.distrito];
  return Object.keys(BARRIO_DISTRITO);
}
const pisosBarrio = b => (D.selecciones["B:" + b + "|" + estado.dorm] || {pisos: 0}).pisos;
const visible = b => D.nombres[b] || b;
function textoPisos(n) { return num(n) + (n === 1 ? " piso" : " pisos"); }
function nombreDorm(t) { return (D.tramos.find(x => x[0] === t) || [t, t])[1]; }
function textoViendo() {
  const partes = [];
  if (estado.barrio !== TODOS) partes.push(visible(estado.barrio));
  else if (estado.distrito !== TODOS) partes.push(estado.distrito);
  else partes.push("toda la ciudad");
  if (estado.dorm !== TODOS) partes.push(nombreDorm(estado.dorm).toLowerCase());
  const s = seleccion(), total = D.selecciones["Todos|Todos"].pisos;
  partes.push(num(s.pisos) + " de " + textoPisos(total));
  if (s.pisos > 0 && s.pisos < MIN) partes.push("menos de 30 pisos: no se ordena");
  return "Viendo: " + partes.join(" · ");
}

// ---- Dirección de la página ----
function leerDireccion() {
  const p = new URLSearchParams(location.hash.slice(1));
  estado.pestana = PESTANAS.includes(p.get("pestana")) ? p.get("pestana") : "recomendacion";
  const b = p.get("barrio"), d = p.get("distrito"), t = p.get("dorm");
  estado.barrio = BARRIO_DISTRITO[b] ? b : TODOS;
  estado.distrito = estado.barrio !== TODOS ? BARRIO_DISTRITO[estado.barrio] : (D.distritos[d] ? d : TODOS);
  estado.dorm = D.tramos.some(x => x[0] === t) ? t : TODOS;
}
function escribirDireccion() {
  const partes = ["pestana=" + estado.pestana];
  if (estado.distrito !== TODOS) partes.push("distrito=" + encodeURIComponent(estado.distrito));
  if (estado.barrio !== TODOS) partes.push("barrio=" + encodeURIComponent(estado.barrio));
  if (estado.dorm !== TODOS) partes.push("dorm=" + encodeURIComponent(estado.dorm));
  try { history.replaceState(null, "", "#" + partes.join("&")); } catch (e) { location.hash = partes.join("&"); }
}

// ---- Piezas ----
function cifra(c) {
  const hay = c.valor !== null && c.valor !== undefined;
  const contexto = hay ? c.contexto : (seleccion().pisos === 0 ? "sin pisos" : "no concluyente");
  const tip = hay ? c.etiqueta + ": " + c.texto + " · " + c.tip : c.etiqueta + ": " + contexto;
  return `<button class="cifra-clave" type="button" data-def="${c.def}" data-tip="${esc(tip)}">` +
    `<span class="numero" id="${c.id}" data-valor="${hay ? c.valor : ""}">${hay ? c.texto : "—"}</span>` +
    `<span class="etiqueta">${esc(c.etiqueta)}</span>` +
    `<span class="contexto" id="${c.id}-contexto" data-texto="${esc(contexto)}">${esc(contexto)}</span></button>`;
}
function ponerOpciones(sel, valores, valor) {
  sel.innerHTML = valores.map(([v, t]) => `<option value="${esc(v)}"${v === valor ? " selected" : ""}>${esc(t)}</option>`).join("");
}

// ---- Pestaña de la recomendación ----
function dibujarRecomendacion() {
  const s = seleccion(), base = D.selecciones["Todos|Todos"];
  const filtrado = estado.distrito !== TODOS || estado.barrio !== TODOS || estado.dorm !== TODOS;
  $("cifras-recomendacion").innerHTML = [
    {id: "c-precio", etiqueta: "Precio por noche", valor: s.precio, texto: s.precio !== undefined ? eur(s.precio) : "", contexto: filtrado ? "todos los pisos: " + eur(base.precio) : "mediana", def: "precio", tip: "mediana del precio publicado"},
    {id: "c-ocupacion", etiqueta: "Días ocupados", valor: s.ocupacion, texto: s.ocupacion !== undefined ? num(s.ocupacion, s.ocupacion % 1 ? 1 : 0) + " días" : "", contexto: filtrado ? "todos los pisos: " + num(base.ocupacion) + " días" : "al año, máximo 255", def: "ocupacion", tip: "mediana de los días que estima la fuente"},
    {id: "c-compra", etiqueta: "Precio de compra", valor: s.compra, texto: s.compra !== undefined ? eur(s.compra) : "", contexto: "", def: "compra", tip: "mediana de superficie por precio del m²"},
    {id: "c-rent", etiqueta: "Rentabilidad bruta", valor: s.rent, texto: s.rent !== undefined ? pct(s.rent) : "", contexto: "", def: "rent", tip: "mediana de ingreso anual entre precio de compra"},
  ].map(cifra).join("");
  // Gráfico por habitaciones: cada grupo de la selección de distrito o barrio; bajo el mínimo, gris y sin cifra
  const filas = D.tramos.map(([t, nombre]) => ({t, nombre, s: D.selecciones[clave(estado.distrito, estado.barrio, t)] || {pisos: 0}}));
  const conCifra = filas.filter(f => f.s.rent !== undefined);
  const sinFiltro = estado.distrito === TODOS && estado.barrio === TODOS;
  $("g-dormitorios-titulo").textContent = sinFiltro ? D.textos.titulo_dormitorios : (conCifra.length ? "Rentabilidad bruta por habitaciones" : "Ningún grupo llega a 30 pisos");
  $("g-dormitorios").dataset.base = conCifra.reduce((a, f) => a + f.s.pisos, 0);
  const izq = 150, ancho = 640, alto = 26, tope = Math.max(base.rent, ...conCifra.map(f => f.s.rent)) * 1.02;
  const finBarras = ancho - 64, x = v => izq + v / tope * (finBarras - izq);
  let svg = `<svg viewBox="0 0 ${ancho} ${filas.length * alto + 20}" width="${ancho}" height="${filas.length * alto + 20}" role="img" aria-label="Rentabilidad bruta por habitaciones">`;
  filas.forEach((f, i) => {
    const y = 18 + i * alto, sel = f.t === estado.dorm;
    svg += `<text x="${izq - 8}" y="${y + 13}" text-anchor="end" font-size="13" fill="#0b0b0b"${sel ? ' font-weight="700"' : ""}>${esc(f.nombre)}</text>`;
    if (f.s.rent !== undefined) {
      const tip = `${f.nombre} · rentabilidad bruta: ${pct(f.s.rent)} · ${textoPisos(f.s.pisos)}`;
      svg += `<g class="dato" tabindex="0" data-tip="${esc(tip)}"><rect x="${izq}" y="${y}" width="${x(f.s.rent) - izq}" height="18" fill="${AZUL}"></rect>` +
        `<text x="${ancho - 4}" y="${y + 13}" text-anchor="end" font-size="13" fill="#0b0b0b">${pct(f.s.rent)}</text></g>`;
    } else {
      const aviso = f.s.pisos ? `${textoPisos(f.s.pisos)}, menos de 30: no concluyente` : "sin pisos";
      svg += `<g class="dato" tabindex="0" data-tip="${esc(f.nombre + " · " + aviso)}"><rect x="${izq}" y="${y + 7}" width="6" height="4" fill="#898781"></rect>` +
        `<text x="${izq + 12}" y="${y + 13}" font-size="13" fill="#52514e">${esc(aviso)}</text></g>`;
    }
  });
  // La referencia solo se dibuja si hay barras con las que compararla
  if (conCifra.length) {
    const xr = x(base.rent);
    svg += `<line x1="${xr}" y1="14" x2="${xr}" y2="${18 + filas.length * alto}" stroke="#898781" stroke-width="1" stroke-dasharray="4 3"></line>` +
      `<text x="${xr}" y="11" text-anchor="end" font-size="13" fill="#52514e">todos los pisos</text>`;
  }
  svg += "</svg>";
  $("g-dormitorios-dibujo").innerHTML = svg;
}

// ---- Pestaña del mapa ----
function dibujarMapa() {
  const vistos = barriosVistos(), conjunto = new Set(vistos);
  const clases = b => (D.barrios[b] || {}).clase;
  const de = c => vistos.filter(b => clases(b) === c);
  const enGrupo = vistos.filter(b => (D.barrios[b] || {}).en_grupo);
  const pisosGrupo = enGrupo.reduce((a, b) => a + pisosBarrio(b), 0);
  const fila = (id, etiqueta, valor, contexto, def, tip) => ({id, etiqueta, valor, texto: num(valor), contexto, def, tip});
  $("cifras-mapa").innerHTML = [
    fila("c-firmes", "Barrios recomendados", de("5 de 5 veces").length, "siguen en la lista las 5 veces", "clase", "barrios recomendados en esta selección"),
    fila("c-aviso", "Barrios que siguen 4 veces", de("4 de 5 veces").length, "salen 1 de las 5 veces", "clase", "barrios que siguen en la lista 4 veces en esta selección"),
    fila("c-segunda", "Otros barrios de la lista", de("menos de 4 veces").length, "siguen menos de 4 veces", "clase", "otros barrios de la lista en esta selección"),
    fila("c-pisos-grupo", "Pisos en esos barrios", pisosGrupo, "con las habitaciones elegidas", "piso", "suma de los pisos de la selección en los barrios de la lista"),
  ].map(cifra).join("");
  document.querySelectorAll("#mapa path").forEach(p => {
    const b = p.dataset.barrio, clase = p.dataset.clase === "menos de 30" ? "menos de 30 pisos, no concluyente" : p.dataset.clase;
    p.classList.toggle("apagado", !conjunto.has(b));
    p.dataset.tip = `${visible(b)} · ${p.dataset.distrito} · ${clase} · ${textoPisos(pisosBarrio(b))}`;
  });
  document.querySelectorAll("#mapa [data-rotulo]").forEach(t => { t.setAttribute("opacity", conjunto.has(t.dataset.rotulo) ? 1 : 0.25); });
}

// ---- Pestaña de los barrios ----
function dibujarBarrios() {
  const vistos = barriosVistos();
  const filas = [], menos = [];
  vistos.forEach(b => {
    const s = D.selecciones["B:" + b + "|" + estado.dorm];
    if (!s) return;
    if (s.pisos >= MIN) filas.push({b, s, f: D.barrios[b]}); else menos.push({b, s});
  });
  // La tabla va por clase y por nombre: el grupo no tiene un orden cerrado (reglas §3)
  filas.sort((a, b) => ORDEN_CLASE[a.f.clase] - ORDEN_CLASE[b.f.clase] || a.b.localeCompare(b.b, "es"));
  const suma = filas.reduce((a, x) => a + x.s.pisos, 0), sumaMenos = menos.reduce((a, x) => a + x.s.pisos, 0);
  const cifraPlana = (id, etiqueta, valor, contexto, def, tip) => ({id, etiqueta, valor, texto: num(valor), contexto, def, tip});
  $("cifras-barrios").innerHTML = [
    cifraPlana("c-comparados", "Barrios con 30 pisos o más", filas.length, "salen en la tabla", "minimo", "barrios de la selección que llegan al mínimo"),
    cifraPlana("c-pisos-comp", "Pisos en esos barrios", suma, "suma de la tabla", "piso", "suma de los pisos de la tabla"),
    cifraPlana("c-menos", "Barrios con menos de 30", menos.length, "se cuentan y no se ordenan", "minimo", "barrios con algún piso que no llegan al mínimo"),
    cifraPlana("c-pisos-menos", "Pisos en esos barrios", sumaMenos, "fuera de la tabla", "piso", "suma de los pisos de los barrios que no llegan al mínimo"),
  ].map(cifra).join("");
  $("barrios-subtitulo").textContent = (estado.dorm === TODOS ? "" : "Pisos y rentabilidad de " + nombreDorm(estado.dorm).toLowerCase() + ". ") +
    "Veces en la lista y avisos: del barrio, con todos sus pisos.";
  const cab = [["Barrio", ""], ["Veces que sigue en la lista", "clase"], ["Pisos", "piso", 1], ["Rentabilidad bruta (%)", "rent", 1], ["Uno de cada cuatro rinde menos de (%)", "cuartil", 1], ["Sale al quitar o cambiar", "pruebas"], ["Avisos", "avisos"]];
  let h = "<thead><tr>" + cab.map(c => `<th${c[2] ? ' class="num"' : ""}>${c[1] ? `<button class="def" type="button" data-def="${c[1]}">${c[0]}</button>` : c[0]}</th>`).join("") + "</tr></thead><tbody>";
  if (!filas.length) h += `<tr><td colspan="7">${vistos.length === 1 ? esc(vistos[0]) + " no llega" : "Ningún barrio de esta selección llega"} a 30 pisos: no se ordena.</td></tr>`;
  filas.forEach(({b, s, f}) => {
    const avisos = f.avisos.map(a => `<span data-tip="${esc(a.texto)}" tabindex="0">${esc(a.corto)}</span>`).join("; ") || (f.en_grupo ? "ninguno" : "—");
    h += `<tr data-barrio="${esc(b)}" data-pisos="${s.pisos}"><td>${esc(visible(b))}</td><td>${esc(f.clase)}</td><td class="num">${num(s.pisos)}</td>` +
      `<td class="num" data-tip="${esc(b)} · rentabilidad bruta: ${pct(s.rent)}">${num(s.rent, 1)}</td>` +
      `<td class="num" data-tip="${esc(b)} · uno de cada cuatro rinde menos de: ${pct(s.cuartil)}">${num(s.cuartil, 1)}</td>` +
      `<td>${f.en_grupo ? (f.no_aguanta.map(a => `<span data-tip="${esc(a.texto)}" tabindex="0">${esc(a.corto)}</span>`).join("; ") || "ninguna") : "—"}</td><td>${avisos}</td></tr>`;
  });
  h += `</tbody><tfoot><tr class="total"><td>Total de la tabla</td><td></td><td class="num" id="t-total" data-valor="${suma}">${num(suma)}</td><td colspan="4"></td></tr></tfoot>`;
  $("tabla-barrios").innerHTML = h;
}

// ---- Filtros, pestañas y medidas ----
function pintarFiltros() {
  ponerOpciones($("f-distrito"), [[TODOS, "Todos"], ...Object.keys(D.distritos).map(d => [d, d])], estado.distrito);
  const lista = estado.distrito !== TODOS ? D.distritos[estado.distrito] : Object.keys(BARRIO_DISTRITO).sort((a, b) => a.localeCompare(b, "es"));
  ponerOpciones($("f-barrio"), [[TODOS, "Todos"], ...lista.map(b => [b, visible(b)])], estado.barrio);
  ponerOpciones($("f-dorm"), [[TODOS, "Todos"], ...D.tramos], estado.dorm);
  const hay = estado.distrito !== TODOS || estado.barrio !== TODOS || estado.dorm !== TODOS;
  if (hay) $("quitar").removeAttribute("disabled"); else $("quitar").setAttribute("disabled", "");
  $("viendo-texto").textContent = textoViendo();
  $("viendo").dataset.pisos = seleccion().pisos;
}
function pintarPestanas() {
  PESTANAS.forEach(p => {
    $("p-" + p).hidden = p !== estado.pestana;
    $("t-" + p).setAttribute("aria-selected", p === estado.pestana ? "true" : "false");
    $("t-" + p).tabIndex = p === estado.pestana ? 0 : -1;
  });
}
function palabrasDe(seccion) {
  const textos = [...seccion.querySelectorAll("h1, p.texto, .g-titulo, .g-subtitulo, .contexto")].map(e => e.textContent);
  return textos.join(" ").split(/\s+/).filter(p => /\p{L}/u.test(p)).length;
}
function medir() {
  const c = $("cuadro");
  c.dataset.ancho = document.documentElement.scrollWidth;
  c.dataset.alto = Math.ceil(document.body.getBoundingClientRect().height);
  c.dataset.palabras = palabrasDe($("p-" + estado.pestana));
  c.dataset.direccion = location.hash;
  c.dataset.estado = "listo";
}
function pintar() {
  pintarFiltros();
  pintarPestanas();
  dibujarRecomendacion();
  dibujarMapa();
  dibujarBarrios();
  escribirDireccion();
  medir();
}

// ---- Definición a un clic y etiquetas al pasar el ratón ----
document.addEventListener("click", ev => {
  const b = ev.target.closest("[data-def]");
  if (!b) return;
  const p = $("def-" + estado.pestana), texto = D.definiciones[b.dataset.def];
  const abierta = !p.hidden && p.textContent === texto;
  p.hidden = abierta;
  p.textContent = abierta ? "" : texto;
});
const tip = $("etiqueta");
function mostrar(el) {
  tip.textContent = el.dataset.tip;
  tip.hidden = false;
  const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
  const izq = Math.min(r.left, innerWidth - t.width - 8);
  const arriba = r.bottom + t.height + 8 > innerHeight ? r.top - t.height - 6 : r.bottom + 6;
  tip.style.left = Math.max(4, izq) + "px";
  tip.style.top = Math.max(4, arriba) + "px";
}
document.addEventListener("mouseover", ev => { const e = ev.target.closest("[data-tip]"); if (e) mostrar(e); else tip.hidden = true; });
document.addEventListener("focusin", ev => { const e = ev.target.closest("[data-tip]"); if (e) mostrar(e); });
document.addEventListener("focusout", () => { tip.hidden = true; });
document.addEventListener("keydown", ev => { if (ev.key === "Escape") tip.hidden = true; });

// ---- Controles ----
$("f-distrito").addEventListener("change", ev => {
  estado.distrito = ev.target.value;
  if (estado.barrio !== TODOS && BARRIO_DISTRITO[estado.barrio] !== estado.distrito) estado.barrio = TODOS;
  pintar();
});
$("f-barrio").addEventListener("change", ev => {
  estado.barrio = ev.target.value;
  if (estado.barrio !== TODOS) estado.distrito = BARRIO_DISTRITO[estado.barrio];
  pintar();
});
$("f-dorm").addEventListener("change", ev => { estado.dorm = ev.target.value; pintar(); });
$("quitar").addEventListener("click", () => { estado.distrito = TODOS; estado.barrio = TODOS; estado.dorm = TODOS; pintar(); });
document.querySelector(".pestanas").addEventListener("click", ev => {
  const b = ev.target.closest("[data-pestana]");
  if (b) { estado.pestana = b.dataset.pestana; pintar(); }
});
document.querySelector(".pestanas").addEventListener("keydown", ev => {
  const paso = {ArrowRight: 1, ArrowLeft: -1}[ev.key];
  if (!paso) return;
  const i = (PESTANAS.indexOf(estado.pestana) + paso + PESTANAS.length) % PESTANAS.length;
  estado.pestana = PESTANAS[i];
  pintar();
  $("t-" + estado.pestana).focus();
});
addEventListener("hashchange", () => { leerDireccion(); pintar(); });
leerDireccion();
pintar();
"""


def muestra(clase):
    """Dibuja la muestra de color de una clase para la leyenda."""
    return f'<svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" fill="{COLOR_CLASE[clase]}"></rect></svg>'


def datos_en_html(datos):
    """Escribe los datos como JSON sin que puedan cerrar su etiqueta <script>."""
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def montar_html(datos, texto, mapa, titulo_del_mapa):
    """Junta estilos, cuerpo, datos y JavaScript en un solo fichero que se abre sin internet."""
    fuente = (f"Fuente: Inside Airbnb, CC BY 4.0, descarga del {datos['fecha_texto']}, con sus límites de barrio. Origen de los datos: Ayuntamiento de Madrid, "
              "precio declarado de 2025, con datos del Colegio de Registradores de España.")
    nombres = {"5 de 5 veces": "5 de 5 veces", "4 de 5 veces": "4 de 5 veces", "menos de 4 veces": "Menos de 4 veces", "fuera de la lista": "Fuera de la lista", "menos de 30": "Menos de 30 pisos, no concluyente"}
    leyenda = "".join(f"<span>{muestra(c)}{nombres[c]}</span>" for c in ORDEN_CLASES)
    cuerpo = CUERPO
    sustituciones = {"__FECHA__": datos["fecha_texto"], "__TITULO_RECOMENDACION__": texto["titulo_recomendacion"], "__RECOMENDACION__": texto["recomendacion"], "__LIMITE__": texto["limite"],
                     "__TITULO_MAPA__": titulo_del_mapa, "__TITULO_BARRIOS__": texto["titulo_barrios"], "__FUENTE__": html.escape(fuente), "__LEYENDA__": leyenda, "__MAPA__": mapa,
                     "__TABLA_RECOMENDACION__": tabla_fija(texto["tabla_recomendacion"][0], texto["tabla_recomendacion"][1:]), "__NOTA_RECOMENDACION__": html.escape(texto["nota_recomendacion"]), "__TEXTO_MAPA__": texto["texto_mapa"],
                     "__TABLA_MAPA__": tabla_fija(texto["tabla_mapa"][0], texto["tabla_mapa"][1:]), "__NOTA_MAPA__": html.escape(texto["nota_mapa"]), "__TEXTO_BARRIOS__": texto["texto_barrios"]}
    for marca, valor in sustituciones.items():
        cuerpo = cuerpo.replace(marca, valor)
    exigir("__" not in cuerpo, "queda una marca sin sustituir en el HTML")
    estilo = ESTILO.read_text(encoding="utf-8") + CSS
    return (f'<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Mercado turístico de Madrid</title>\n<style>{estilo}</style>\n</head>\n<body>\n{cuerpo}\n'
            f'<script type="application/json" id="datos">{datos_en_html({**datos, "textos": texto})}</script>\n<script>{JS}</script>\n</body>\n</html>\n')


# ---------------------------------------------------------------------------
# 8. Principal
# ---------------------------------------------------------------------------

def principal():
    """Comprueba, calcula, compara y escribe; no escribe nada hasta que pasan todas las comprobaciones."""
    comprobar_orden()
    huella_antes = huella_de_datos()

    ind = leer_json(INDICADORES)
    comprobar_fecha(ind["fecha_datos"], FECHA_DEL_CASO)
    for tabla in (ANUNCIOS, BARRIOS):
        misma_entrada(ind["entradas"], str(tabla.relative_to(CASO)).replace("\\", "/"), sha256(tabla))
    anuncios = pd.read_parquet(ANUNCIOS)
    barrios = pd.read_parquet(BARRIOS)
    geo = leer_json(GEOJSON)

    datos = preparar_datos(ind, anuncios, barrios)
    sin_anuncios_sueltos(datos)
    comprobar_totales(datos)
    cifras_comparadas = comparar(datos, cifras_a_comparar(ind, datos["distritos"]))
    comprobar_grupos(datos, ind)
    comprobar_recomendacion(anuncios, ind)

    p2 = next(q for q in ind["preguntas"] if q["id"] == "P2")
    distrito_de = dict(zip(barrios["barrio"], barrios["distrito"]))
    clases = clases_del_mapa(barrios["barrio"], datos["barrios"])
    mapa = mapa_svg(geo, clases, distrito_de, p2["grupo"])
    texto = textos(ind)
    pagina = montar_html(datos, texto, mapa, titulo_mapa())
    buscar_datos_personales(pagina)

    huella_despues = huella_de_datos()
    exigir(huella_antes == huella_despues, "ha cambiado la huella de data/")

    SALIDA_HTML.write_text(pagina, encoding="utf-8")
    con_cifras = sum(1 for v in datos["selecciones"].values() if len(v) > 1)
    salida = {"script": SCRIPT, "fecha_datos": ind["fecha_datos"], "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"), "python": platform.python_version(), "pandas": pd.__version__,
              "entradas": [{"ruta": str(r.relative_to(CASO)).replace("\\", "/"), "sha256": sha256(r)} for r in (INDICADORES, ANUNCIOS, BARRIOS, GEOJSON)],
              "salida": {"ruta": "informes/cuadro_mando.html", "bytes": SALIDA_HTML.stat().st_size, "sha256": sha256(SALIDA_HTML)},
              "filtros": {"distritos": len(datos["distritos"]), "barrios": len(clases), "dormitorios": TRAMOS, "selecciones_guardadas": len(datos["selecciones"]), "con_cifras": con_cifras, "solo_recuento": len(datos["selecciones"]) - con_cifras},
              "cifras_sin_filtros": datos["selecciones"]["Todos|Todos"], "cifras_comparadas_con_indicadores": cifras_comparadas, "minimo": MINIMO,
              "clases": {c: sum(1 for v in clases.values() if v == c) for c in ORDEN_CLASES}, "textos": texto,
              "huella_data": {"antes": huella_antes, "despues": huella_despues, "iguales": huella_antes == huella_despues},
              "decisiones_propias": ["Las medianas no se suman: cada selección de los filtros se calcula en Python y el navegador la busca.",
                                       "Una selección de menos de 30 pisos guarda solo su recuento, porque su mediana puede ser la cifra de un anuncio.",
                                       "La tabla va por clase y por nombre, porque el grupo no tiene un orden cerrado.",
                                       "La recomendación sale del campo recomendacion de indicadores.json y se rehace aquí con los pisos de hasta 2 habitaciones de los recomendados.",
                                       "Las tablas fijas de la recomendación y del mapa no cambian con los filtros: repiten lo que dicen los informes."]}
    SALIDA_JSON.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Cuadro escrito: {SALIDA_HTML} ({SALIDA_HTML.stat().st_size / 1024:.0f} KB). {cifras_comparadas} cifras iguales a indicadores.json; {len(datos['selecciones'])} selecciones, {con_cifras} con cifras.")


if __name__ == "__main__":
    principal()
