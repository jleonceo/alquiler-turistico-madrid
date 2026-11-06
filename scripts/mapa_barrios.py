"""Mapa de los barrios de Madrid por clase, en SVG, para el informe final del caso.

Este módulo no hace nada al importarse. assets/graficos.py no trae mapas y no se cambia, así que el mapa vive aquí: recibe los
polígonos, la clase de cada barrio del grupo y el límite del centro histórico, y devuelve el SVG listo para `Pagina.grafico`.
Cumple las reglas de salida: colores de la paleta en su orden, con el naranja en los barrios con aviso, que son la alerta (G3), cada barrio con su nombre
escrito junto al dibujo (G16), una etiqueta al pasar el ratón con grupo y clase (G20) y la letra del informe (E4).
"""
import html

import shapely

# Color de cada clase, en el orden de la paleta: azul, naranja para la alerta y verde agua (E2 y G3).
COLOR = {"firme": "#2a78d6", "con aviso": "#eb6834", "segunda línea": "#1baf7a"}
RESTO, BORDE, TINTA, SECUNDARIO, LINEA = "#e1e0d9", "#ffffff", "#0b0b0b", "#52514e", "#898781"
FAMILIA = "'Segoe UI', system-ui, sans-serif"
ANCHO, ALTO = 640, 400
MARGEN_LADO = 190  # px a cada lado del dibujo para escribir los nombres, el más largo incluido
ARRIBA, ABAJO = 8, 34  # px; abajo va la leyenda
LINEA_NOMBRE = 20  # px entre dos nombres de la misma columna


def anillos(geometria):
    """Da los anillos de un polígono o multipolígono, exteriores e interiores."""
    salida = []
    for g in shapely.get_parts(geometria):
        if isinstance(g, shapely.Polygon):
            salida.append(list(g.exterior.coords))
            salida.extend(list(i.coords) for i in g.interiors)
    return salida


def proyeccion(limites):
    """Devuelve la función que pasa lon y lat a px, con la misma escala en los dos ejes a esta latitud."""
    x0, y0, x1, y1 = limites
    # A la latitud de Madrid un grado de longitud mide menos que uno de latitud.
    aspecto = 0.76
    escala = min((ANCHO - 2 * MARGEN_LADO) / ((x1 - x0) * aspecto), (ALTO - ARRIBA - ABAJO) / (y1 - y0))
    ancho_mapa = (x1 - x0) * aspecto * escala
    izquierda = (ANCHO - ancho_mapa) / 2

    def px(lon, lat):
        """Pasa un punto a coordenadas del SVG."""
        return izquierda + (lon - x0) * aspecto * escala, ARRIBA + (y1 - lat) * escala
    return px


def trazo(geometria, px):
    """Escribe la geometría como el atributo d de un <path>."""
    partes = []
    for anillo in anillos(geometria):
        puntos = [px(x, y) for x, y in anillo]
        # La coma separa x de y: con un espacio, un par de coordenadas se lee como un número de identidad.
        partes.append("M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in puntos) + " Z")
    return " ".join(partes)


def nombres(barrios, px, poligonos):
    """Reparte los nombres en dos columnas, a cada lado del mapa, ordenados de arriba abajo para que no se crucen."""
    puntos = {b: px(*list(poligonos[b].representative_point().coords)[0]) for b in barrios}
    izquierda = sorted((b for b in barrios if puntos[b][0] < ANCHO / 2), key=lambda b: puntos[b][1])
    derecha = sorted((b for b in barrios if puntos[b][0] >= ANCHO / 2), key=lambda b: puntos[b][1])
    salida = []
    for lado, columna in (("izquierda", izquierda), ("derecha", derecha)):
        # Cada nombre cae a la altura de su barrio, empujado hacia abajo si pisa al anterior.
        y_anterior = ARRIBA - LINEA_NOMBRE
        for b in columna:
            y = max(puntos[b][1], y_anterior + LINEA_NOMBRE)
            y_anterior = y
            salida.append((b, lado, puntos[b], y))
    return salida


def mapa(poligonos, clases, limite, nombre=str):
    """Dibuja todos los barrios: los del grupo con el color de su clase, su nombre y su etiqueta; el centro histórico, con su rótulo.

    `nombre` da cómo se escribe cada barrio al lado del dibujo, porque la fuente escribe alguno sin tilde.
    """
    faltan = [b for b in clases if b not in poligonos]
    if faltan:
        raise ValueError(f"barrios del grupo sin polígono: {faltan}")
    raras = sorted(set(clases.values()) - set(COLOR))
    if raras:
        raise ValueError(f"clases sin color: {raras}")
    px = proyeccion(shapely.union_all(list(poligonos.values()) + [limite]).bounds)
    # Primero el resto de la ciudad, en gris claro; encima, los barrios del grupo.
    fondo = "".join(f'<path d="{trazo(g, px)}" fill="{RESTO}" stroke="{BORDE}" stroke-width="0.5"/>' for b, g in sorted(poligonos.items()) if b not in clases)
    grupo = ""
    for b in sorted(clases):
        titulo = html.escape(f"{nombre(b)}: {clases[b]}")
        grupo += f'<g class="dato" tabindex="0"><title>{titulo}</title><path d="{trazo(poligonos[b], px)}" fill="{COLOR[clases[b]]}" stroke="{BORDE}" stroke-width="0.5"/></g>'
    # El centro histórico va como línea, porque es una referencia y no un grupo (G3).
    centro = f'<path d="{trazo(limite, px)}" fill="none" stroke="{TINTA}" stroke-width="1.5"/>'
    letra = f'font-family="{FAMILIA}" font-size="13"'
    # Nombres a los lados, cada uno con una línea fina hasta su barrio (G5 y G16).
    rotulos = ""
    for b, lado, (x, y), yt in nombres(sorted(clases), px, poligonos):
        xt, ancla = (MARGEN_LADO - 6, "end") if lado == "izquierda" else (ANCHO - MARGEN_LADO + 6, "start")
        rotulos += f'<line x1="{xt + (3 if lado == "izquierda" else -3):.1f}" y1="{yt:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{LINEA}" stroke-width="0.8"/>'
        rotulos += f'<text x="{xt:.1f}" y="{yt + 4:.1f}" text-anchor="{ancla}" fill="{TINTA}" {letra}>{html.escape(nombre(b))}</text>'
    cx, cy = px(*list(limite.representative_point().coords)[0])
    rotulos += f'<line x1="{MARGEN_LADO - 3:.1f}" y1="{ALTO - ABAJO - 10:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" stroke="{LINEA}" stroke-width="0.8"/>'
    rotulos += f'<text x="{MARGEN_LADO - 6:.1f}" y="{ALTO - ABAJO - 6:.1f}" text-anchor="end" fill="{SECUNDARIO}" {letra}>Centro histórico</text>'
    # Leyenda pegada al mapa: cada clase con su color y su nombre; el resto de barrios, en gris.
    leyenda, x = "", 170
    for texto, color in (("Firme", COLOR["firme"]), ("Con aviso", COLOR["con aviso"]), ("Segunda línea", COLOR["segunda línea"]), ("Otros barrios", RESTO)):
        leyenda += f'<rect x="{x}" y="{ALTO - 18}" width="13" height="13" fill="{color}"/><text x="{x + 18}" y="{ALTO - 7}" fill="{TINTA}" {letra}>{texto}</text>'
        x += 34 + 7 * len(texto)
    return f'<svg width="{ANCHO}" height="{ALTO}" viewBox="0 0 {ANCHO} {ALTO}" xmlns="http://www.w3.org/2000/svg">{fondo}{grupo}{centro}{rotulos}{leyenda}</svg>'
