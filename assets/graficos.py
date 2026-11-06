"""Gráficos en SVG que cumplen las reglas de salida (`reglas_de_salida.md`, G1 a G19 y E2 a E5).

Spec: `spec_v3_piezas.md`. Suite: `probar_piezas.py`. Banco: `banco/comprobar_informe.py`.

Una función por cada tipo del catálogo G14, más el intervalo y lo previsto:

- barras_ordenadas: ranking, de mayor a menor, cifra en cada barra, eje desde cero;
- barras_con_intervalo: grupos con su intervalo, que dice qué es, y una línea de referencia con su rótulo;
- barra_divergente: desviación sobre una referencia, con la desviación y su signo en cada barra;
- linea_tiempo: evolución, cuatro líneas como mucho, nombre y última cifra al final, lo previsto discontinuo;
- columnas_tiempo: evolución en pocos periodos, cifra en cada columna, lo previsto rayado;
- columna_apilada: parte del todo, cifra en cada tramo y el total encima; en importes o al 100 %;
- histograma: distribución, sin dibujar fuera del rango de los datos, con tramos enteros si los datos lo son;
- dispersion: relación entre dos medidas, un eje para cada una;
- curva_acumulada: concentración, qué parte del total reúne cada parte de los elementos.

Todas devuelven el SVG como texto, listo para meterlo en el HTML con `informe.py`. Llevan la letra Segoe UI con su
reserva (`system-ui, sans-serif`) como texto y no como dibujo, tamaños de 13 px, los colores de la paleta en su orden,
sin cuadrícula salvo cuando los valores no van rotulados y sin título dentro: el título y el subtítulo los pone
`informe.py`. El SVG mide justo el ancho y el alto pedidos, con el eje en el mismo sitio en todos los gráficos del
mismo tipo. Para comparar grupos en varios gráficos (G8), `maximo=` fija la escala y `bordes=` los tramos; `n=` pone
el número de cada grupo (G9). Paran con un ValueError que dice la regla cuando se les pide algo que la incumple.

Color con significado (04/10, auditoría de diseño): `destacar=` pone en naranja las barras de los grupos que nombra el
título, y el resto va en azul. Naranja quiere decir siempre lo peor o la alerta, nunca la mejor opción (G3, cambiada el 07/10).

Ningún texto pisa a otro (06/10, caso 04: 11 de 65 gráficos del exploratorio tenían textos montados). Si los nombres
del eje horizontal no caben, se deja uno de cada pocos, empezando por el primero; la cifra de un tramo apilado más
bajo que la letra va al lado de su columna; y si aun así dos textos se pisan, la pieza para y dice qué pedir.

Cada valor lleva su etiqueta al pasar el ratón : cada barra, tramo, punto o
marca va en un grupo `<g class="dato">` con su `<title>`, que dice el grupo, qué se mide (`medida=`) y la cifra exacta
con su unidad («Sur: 3.402 €»). `informe.py` la enseña con el ratón y con el tabulador.
"""

# Decimal y ROUND_HALF_UP redondean como Excel y Power BI
from decimal import Decimal, ROUND_HALF_UP
# hashlib da un prefijo único a los identificadores de cada SVG
import hashlib
# html escapa el texto de las etiquetas que van dentro del SVG
import html
# io guarda el SVG en memoria antes de devolverlo
import io
# math comprueba los valores que no son números
import math
# re arregla las unidades y quita los metadatos del SVG
import re

# matplotlib dibuja los gráficos
import matplotlib
# El modo Agg dibuja sin abrir ventanas
matplotlib.use("Agg")
# pyplot crea las figuras
import matplotlib.pyplot as plt
# ticker da formato a los números de los ejes
import matplotlib.ticker
# cycler fija el orden de los colores de las series
from cycler import cycler
# numpy calcula los intervalos del histograma y la curva acumulada
import numpy as np


# =====================================================================================================================
# COLORES Y TAMAÑOS (reglas E2, E3, E4 y E5)
# =====================================================================================================================

# Paleta en su orden (E2): la primera serie va siempre en el primer color
PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
# Texto principal (E3)
TINTA = "#0b0b0b"
# Texto secundario (E3): números de los ejes y rótulos de referencia
SECUNDARIO = "#52514e"
# Gris para líneas y para el relleno de lo que va en segundo plano, nunca para texto (E3)
LINEA = "#898781"
# Líneas finas de la cuadrícula (G17)
REJILLA = "#e1e0d9"
# Fondo blanco (E1)
BLANCO = "#ffffff"
# Letra con su reserva (E4): sin Segoe UI, el navegador pone la del sistema y nunca una con remate
FAMILIA = "'Segoe UI', system-ui, sans-serif"
# Tamaño de etiquetas y números dentro del gráfico (E5)
TAMANO = 13
# Ancho por defecto de un gráfico, en px
ANCHO = 640
# Ancho de cada gráfico cuando van dos lado a lado (S3)
ANCHO_FILA = 500
# Puntos por pulgada: con 72, una unidad del SVG es un píxel
PPP = 72
# Margen izquierdo mínimo de las barras horizontales: así las barras de todos los gráficos empiezan en el mismo sitio
IZQUIERDA_BARRAS = 120
# Margen izquierdo mínimo de los gráficos con números en el eje vertical
IZQUIERDA_EJE = 48
# Separación mínima entre los nombres del final de las líneas, en px (G16)
SEPARACION_NOMBRES = 18
# A partir de cuántos puntos la dispersión los dibuja huecos, para que no se tapen
PUNTOS_HUECOS = 100

# Ajustes de matplotlib que hay que cambiar porque los suyos por defecto incumplen las reglas
AJUSTES = {
    # La letra sale como texto y no convertida en dibujo, para que se pueda leer y medir (E4 y E5)
    "svg.fonttype": "none",
    # Identificadores internos del SVG fijos, para que el mismo gráfico dé siempre el mismo SVG
    "svg.hashsalt": "casos-de-uso-v3",
    # Con 72 puntos por pulgada, las medidas de la figura son píxeles
    "figure.dpi": PPP,
    # Letra del informe (E4); la reserva se añade al guardar, porque matplotlib solo escribe la primera
    "font.family": ["Segoe UI"],
    # Tamaño de toda la letra del gráfico (E5)
    "font.size": TAMANO,
    # Tamaño de los títulos de los ejes (E5)
    "axes.labelsize": TAMANO,
    # Tamaño de los números del eje horizontal (E5)
    "xtick.labelsize": TAMANO,
    # Tamaño de los números del eje vertical (E5)
    "ytick.labelsize": TAMANO,
    # Tamaño de la leyenda (E5)
    "legend.fontsize": TAMANO,
    # Color del texto (E3); por defecto matplotlib pone negro #000000
    "text.color": TINTA,
    # Color de los títulos de los ejes (E3)
    "axes.labelcolor": SECUNDARIO,
    # Color de las líneas de los ejes (E3: el gris de líneas)
    "axes.edgecolor": LINEA,
    # Grosor de las líneas de los ejes
    "axes.linewidth": 0.8,
    # Color de las marcas del eje horizontal
    "xtick.color": LINEA,
    # Color de las marcas del eje vertical
    "ytick.color": LINEA,
    # Color de los números del eje horizontal: es texto, va en secundario
    "xtick.labelcolor": SECUNDARIO,
    # Color de los números del eje vertical: es texto, va en secundario
    "ytick.labelcolor": SECUNDARIO,
    # Fondo del área del gráfico (E1)
    "axes.facecolor": BLANCO,
    # Fondo de la figura (E1)
    "figure.facecolor": BLANCO,
    # Fondo al guardar (E1)
    "savefig.facecolor": BLANCO,
    # Sin borde arriba (G17)
    "axes.spines.top": False,
    # Sin borde a la derecha (G17)
    "axes.spines.right": False,
    # Sin cuadrícula por defecto (G17)
    "axes.grid": False,
    # Cuadrícula fina cuando se pide (G17)
    "grid.color": REJILLA,
    # Grosor de la cuadrícula
    "grid.linewidth": 0.8,
    # Leyenda sin marco
    "legend.frameon": False,
    # Bordes de las barras en blanco, nunca en negro
    "patch.edgecolor": BLANCO,
    # El rayado toma el color del borde de la barra (G19)
    "hatch.color": "edge",
    # Series en el orden de la paleta (G3)
    "axes.prop_cycle": cycler(color=PALETA),
    # Grosor de las líneas de datos
    "lines.linewidth": 2,
}


# =====================================================================================================================
# NÚMEROS A LA ESPAÑOLA
# =====================================================================================================================

def numero(x, decimales=0, unidad="", con_signo=False):
    """Escribe un número con punto de miles y coma decimal: 1234.5 -> «1.235»; con un decimal, «1.234,5».

    Redondea como Excel y Power BI: los empates se alejan del cero (2,5 -> 3 y −2,5 -> −3). El `round()` de Python
    los lleva al par (2,5 -> 2) y la cifra del informe no coincidiría con la de la hoja de cálculo (T3 y F2).
    """
    # Paso de redondeo: 1 para cero decimales, 0,01 para dos
    paso = Decimal(1).scaleb(-decimales)
    # Se redondea el número tal como se escribe (repr), para que 1,005 sea 1,005 y no 1,00499...
    redondeado = Decimal(repr(float(x))).quantize(paso, rounding=ROUND_HALF_UP)
    # Se formatea el valor absoluto con coma de miles y punto decimal, al estilo inglés
    texto = f"{abs(redondeado):,.{decimales}f}"
    # Se intercambian la coma y el punto para dejarlo en español
    texto = texto.replace(",", "§").replace(".", ",").replace("§", ".")
    # Signo menos tipográfico para los negativos; más solo si se pide; el cero, sin signo
    signo = "−" if redondeado < 0 else ("+" if con_signo and redondeado > 0 else "")
    # Número con su signo y su unidad
    return f"{signo}{texto}{unidad}"


def _formato_eje(decimales=0, unidad=""):
    """Formateador de matplotlib que escribe los números del eje a la española."""
    # Cada número del eje pasa por la función de arriba
    return matplotlib.ticker.FuncFormatter(lambda v, _: numero(v, decimales, unidad))


def _eje(eje, decimales=0, unidad="", log=False):
    """Números de un eje a la española y en marcas redondas que se puedan escribir con esos decimales."""
    # Números a la española
    eje.set_major_formatter(_formato_eje(decimales, unidad))
    # En escala logarítmica, las marcas de matplotlib (1, 10, 100) ya son redondas
    if log:
        # Sin números en las marcas menores
        eje.set_minor_formatter(matplotlib.ticker.NullFormatter())
        # Nada más que hacer
        return
    # Marcas en 1, 2 o 5 por una potencia de diez; sin decimales, solo enteras, para que no se repitan
    eje.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=6, steps=[1, 2, 5, 10], integer=decimales == 0))


def _con_n(etiquetas, n):
    """Añade el número de cada grupo a su nombre: «A (n = 1.200)» (G9)."""
    # Sin n, los nombres tal cual
    if n is None:
        # Se devuelven sin tocar
        return [str(e) for e in etiquetas]
    # Tiene que haber un n por grupo
    if len(n) != len(etiquetas):
        # Se para diciendo cuántos faltan
        raise ValueError(f"G9: hay {len(etiquetas)} grupos y {len(n)} valores de n")
    # Nombre con su n
    return [f"{e} (n = {numero(k)})" for e, k in zip(etiquetas, n)]


def _escala(mayor, maximo, funcion):
    """El tope del eje: el mayor dato, o `maximo` si se da para comparar gráficos con la misma escala (G8)."""
    # Sin maximo, manda el dato
    if maximo is None:
        # Tope del dato
        return mayor
    # Un maximo menor que los datos cortaría barras
    if maximo < mayor:
        # Se para diciendo la regla
        raise ValueError(f"G8: {funcion} con maximo={maximo} y un dato de {mayor}; el maximo tiene que cubrirlos")
    # Tope común
    return maximo


# =====================================================================================================================
# PIEZAS COMUNES
# =====================================================================================================================

def _series(series):
    """Convierte una lista o un diccionario de series en una lista de (nombre, valores); para con más de cuatro."""
    # Una lista suelta es una sola serie sin nombre
    if not isinstance(series, dict):
        # Se envuelve con nombre vacío
        series = {"": list(series)}
    # Más de cuatro series incumplen G3 y G18
    if len(series) > 4:
        # Se para diciendo la regla
        raise ValueError(f"G3 y G18: como mucho cuatro series en un gráfico; hay {len(series)}")
    # Cada serie, con sus valores pasados a número
    salida = [(str(nombre), [float(v) for v in valores]) for nombre, valores in series.items()]
    # Un valor que no es número no se puede dibujar sin mentir
    for nombre, valores in salida:
        # Se busca un vacío o un infinito
        if any(not math.isfinite(v) for v in valores):
            # Se para diciendo qué serie lo tiene
            raise ValueError(f"la serie «{nombre}» tiene valores que no son números")
    # Lista de series lista para dibujar
    return salida


def _figura(ancho, alto):
    """Crea una figura del tamaño pedido en píxeles."""
    # Con 72 puntos por pulgada, el tamaño en pulgadas es el de píxeles entre 72
    return plt.subplots(figsize=(ancho / PPP, alto / PPP))


def _encajar(fig, izquierda=0):
    """Mete todo el dibujo dentro del tamaño pedido sin cambiarlo; el eje empieza en `izquierda` px o más."""
    # El único eje de la figura
    ax = fig.axes[0]
    # Ancho y alto de la figura, en px
    ancho, alto = fig.bbox.width, fig.bbox.height
    # Aire alrededor del dibujo, en px
    aire = 4
    # Dos pasadas: al mover el eje, las etiquetas ya no cambian de tamaño
    for _ in range(2):
        # Se dibuja para saber lo que ocupa cada texto
        fig.canvas.draw()
        # Caja de todo lo que pinta el eje: números, nombres, rótulos y leyenda
        caja = ax.get_tightbbox(fig.canvas.get_renderer())
        # Posición del área del eje, en fracción de la figura
        pos = ax.get_position()
        # Lo que sobresale a la izquierda del área del eje
        sobra_izq = max(0, pos.x0 * ancho - caja.x0)
        # Lo que sobresale a la derecha
        sobra_der = max(0, caja.x1 - pos.x1 * ancho)
        # Lo que sobresale por abajo
        sobra_aba = max(0, pos.y0 * alto - caja.y0)
        # Lo que sobresale por arriba
        sobra_arr = max(0, caja.y1 - pos.y1 * alto)
        # Nuevos márgenes: lo que sobresale más el aire, y a la izquierda como poco el mínimo pedido
        fig.subplots_adjust(left=max(izquierda, sobra_izq + aire) / ancho, right=1 - (sobra_der + aire) / ancho,
                            bottom=(sobra_aba + aire) / alto, top=1 - (sobra_arr + aire) / alto)


def _sin_repetidos(fig):
    """Para si un eje numérico escribe el mismo número en dos marcas: faltan decimales (F2)."""
    # Se dibuja para que las marcas estén puestas
    fig.canvas.draw()
    # Cada eje de cada gráfico
    for ax in fig.axes:
        # Eje horizontal y vertical
        for nombre, eje in (("horizontal", ax.xaxis), ("vertical", ax.yaxis)):
            # Solo los ejes que se ven y escriben números con nuestro formato
            if not eje.get_visible() or not isinstance(eje.get_major_formatter(), matplotlib.ticker.FuncFormatter):
                # Se salta
                continue
            # Tramo que se ve del eje
            bajo, alto = sorted(eje.get_view_interval())
            # Margen para no perder la marca del borde
            holgura = (alto - bajo) * 1e-9
            # Números de las marcas que se ven
            textos = [eje.get_major_formatter()(v, i) for i, v in enumerate(eje.get_majorticklocs())
                      if bajo - holgura <= v <= alto + holgura]
            # Dos marcas con el mismo texto
            if len(textos) != len(set(textos)):
                # Se para diciendo qué pedir
                raise ValueError(f"F2: el eje {nombre} repite números ({', '.join(textos)}); pide más decimales")


def _cajas_marcas_x(fig, ax):
    """Caja en px de cada nombre que se ve en el eje horizontal, de izquierda a derecha."""
    # Se dibuja para que los nombres tengan su sitio
    fig.canvas.draw()
    # Herramienta que mide el texto
    r = fig.canvas.get_renderer()
    # Cajas de los nombres con texto, en orden
    return sorted((t.get_window_extent(r) for t in ax.get_xticklabels() if t.get_visible() and t.get_text().strip()),
                  key=lambda c: c.x0)


def _caben(cajas):
    """Cierto si entre cada nombre y el siguiente quedan 6 px o más."""
    # Hueco entre cada caja y la siguiente
    return all(b.x0 - a.x1 >= 6 for a, b in zip(cajas, cajas[1:]))


def _aclarar_marcas(fig):
    """Si los nombres del eje horizontal se pisan, deja uno de cada pocos, empezando por el primero (06/10).

    Con 48 meses, por ejemplo, queda uno por trimestre o por año: los pasos 3, 6 y 12 caen en el mismo mes de cada
    año. Si los nombres ya caben, el eje no se toca.
    """
    # Cada eje de la figura
    for ax in fig.axes:
        # Un eje oculto no enseña nombres; si ya caben, no se toca
        if not ax.xaxis.get_visible() or _caben(_cajas_marcas_x(fig, ax)):
            # Siguiente eje
            continue
        # Posiciones de las marcas
        posiciones = list(ax.get_xticks())
        # Nombre de cada marca, tal como se escribe
        nombres = [t.get_text() for t in ax.get_xticklabels()]
        # Pasos de menos a más: uno de cada 2, 3, 4, 6, 12...
        for paso in (2, 3, 4, 6, 12, 24, 36, 48, 60, 120):
            # Se dejan solo las marcas de ese paso, con su nombre
            ax.set_xticks(posiciones[::paso], nombres[::paso])
            # Si ya caben, se queda este paso
            if _caben(_cajas_marcas_x(fig, ax)):
                # Fin de la búsqueda
                break


def _sin_montados(fig):
    """Para si dos textos del gráfico se pisan: un nombre, una cifra, un rótulo o el título del eje (06/10).

    Lo que la pieza puede arreglar sola ya lo ha hecho (`_aclarar_marcas`); lo que queda lo tiene que cambiar quien
    llama: menos grupos o periodos, más ancho, o `linea_tiempo` en vez de columnas cuando hay muchos periodos.
    """
    # Se dibuja para saber dónde cae cada texto
    fig.canvas.draw()
    # Herramienta que mide el texto
    r = fig.canvas.get_renderer()
    # Textos que se ven, con su caja
    piezas = []
    # Cada eje de la figura
    for ax in fig.axes:
        # Nombres de los ejes que se ven, cifras y rótulos dentro del gráfico, y el título del eje horizontal
        candidatos = (list(ax.get_xticklabels()) if ax.xaxis.get_visible() else []) \
            + (list(ax.get_yticklabels()) if ax.yaxis.get_visible() else []) + list(ax.texts) + [ax.xaxis.label]
        # Solo los que se ven y dicen algo
        piezas += [(t.get_text(), t.get_window_extent(r)) for t in candidatos
                   if t.get_visible() and t.get_text().strip()]
    # Cada pareja de textos
    for i, (texto_a, a) in enumerate(piezas):
        # Con los que vienen detrás
        for texto_b, b in piezas[i + 1:]:
            # Se pisan si se cruzan más de 1 px a lo ancho y a lo alto
            if min(a.x1, b.x1) - max(a.x0, b.x0) > 1 and min(a.y1, b.y1) - max(a.y0, b.y0) > 1:
                # Se para diciendo cuáles y qué pedir
                raise ValueError(f"los textos «{texto_a}» y «{texto_b}» se pisan: pide menos grupos o periodos, más "
                                 f"ancho o, con muchos periodos, linea_tiempo")


def _etiqueta(grupo, cifra, medida="", serie=""):
    """Texto de la etiqueta de un valor: «grupo · serie · medida: cifra», sin las partes vacías (G20)."""
    # Lo que dice de qué es la cifra
    de_que = " · ".join(str(p) for p in (grupo, serie, medida) if str(p).strip())
    # Con algo delante, dos puntos; si no, la cifra sola
    return f"{de_que}: {cifra}" if de_que else str(cifra)


def _dato(fig, artista, texto):
    """Marca una barra, un tramo o un punto como valor con su etiqueta; `_a_svg` le pone el `<title>` (G20)."""
    # Etiquetas ya apuntadas en esta figura
    apuntadas = fig.__dict__.setdefault("_etiquetas", [])
    # Identificador propio de este valor
    gid = f"dato{len(apuntadas)}"
    # matplotlib escribe el valor dentro de <g id="gid">
    artista.set_gid(gid)
    # Se apunta con su texto
    apuntadas.append((gid, texto))


def _punto(fig, ax, x, y, texto):
    """Un punto invisible sobre una línea o un elemento, que lleva la etiqueta al pasar el ratón (G20)."""
    # Marca redonda de 10 px sin color que se vea: solo sirve para que el ratón tenga dónde caer
    marca, = ax.plot([x], [y], marker="o", markersize=10, linestyle="none", color=PALETA[0], alpha=0.0)
    # Se marca como valor con su etiqueta
    _dato(fig, marca, texto)


def _poner_etiquetas(fig, svg):
    """Pone a cada valor marcado su clase, el tabulador y su `<title>`; para si alguno no está en el SVG (G20)."""
    # Cada valor apuntado
    for gid, texto in fig.__dict__.get("_etiquetas", []):
        # Apertura del grupo que escribe matplotlib
        apertura = f'<g id="{gid}">'
        # Un valor apuntado que no aparece se perdería sin avisar
        if apertura not in svg:
            # Se para diciendo cuál
            raise ValueError(f"G20: la etiqueta «{texto}» no encuentra su valor en el SVG")
        # Clase, foco con el tabulador y título con el texto escapado
        svg = svg.replace(apertura, f'<g id="{gid}" class="dato" tabindex="0"><title>'
                                    f'{html.escape(texto, quote=False)}</title>', 1)
    # SVG con las etiquetas
    return svg


def _a_svg(fig, izquierda=0):
    """Guarda la figura en SVG listo para el HTML: mide justo lo pedido, en px, con letra de reserva e ids únicos."""
    # Todo el dibujo dentro del tamaño pedido
    _encajar(fig, izquierda)
    # Ningún eje con números repetidos
    _sin_repetidos(fig)
    # Si los nombres del eje horizontal se pisan, se deja uno de cada pocos (06/10)
    _aclarar_marcas(fig)
    # Se vuelve a encajar, porque los nombres han podido cambiar
    _encajar(fig, izquierda)
    # Ningún texto encima de otro (06/10)
    _sin_montados(fig)
    # Memoria para el SVG
    buf = io.StringIO()
    # Se guarda sin recortar, para que mida el ancho y el alto pedidos, y sin la fecha, para que salga igual cada vez
    fig.savefig(buf, format="svg", metadata={"Date": None})
    # Se cierra la figura para liberar memoria
    plt.close(fig)
    # Texto del SVG
    svg = buf.getvalue()
    # Se quita lo que va antes de <svg>: la cabecera XML y el DOCTYPE no van dentro de un HTML
    svg = svg[svg.index("<svg"):]
    # Se quitan los metadatos, que no aportan nada al lector
    svg = re.sub(r"<metadata>.*?</metadata>\s*", "", svg, flags=re.S)
    # Cada valor con su etiqueta al pasar el ratón (G20)
    svg = _poner_etiquetas(fig, svg)
    # La letra con su reserva (E4): matplotlib solo escribe la primera familia
    svg = svg.replace("font-family: 'Segoe UI'", "font-family: " + FAMILIA)
    # Prefijo propio de este gráfico, sacado de su contenido, para que sus ids no choquen con los de otro
    prefijo = "g" + hashlib.md5(svg.encode("utf-8")).hexdigest()[:6] + "_"
    # Cada id lleva el prefijo
    svg = re.sub(r'\bid="', 'id="' + prefijo, svg)
    # Y cada referencia a un id, también
    svg = svg.replace("url(#", "url(#" + prefijo).replace('href="#', 'href="#' + prefijo)
    # Etiqueta de apertura del SVG
    raiz = re.match(r"<svg[^>]*>", svg)
    # Ancho y alto pasan de pt a unidades sin medida, que son píxeles: así 13px se ven a 13 px (E5)
    nueva = re.sub(r'(width|height)="([\d.]+)pt"', r'\1="\2"', raiz.group(0))
    # SVG con la etiqueta de apertura arreglada
    return nueva + svg[raiz.end():]


def _limpiar_ejes(ax, izquierda=True, abajo=True):
    """Deja solo los bordes que hacen de línea base, sin marcas."""
    # Borde izquierdo: se deja o se quita
    ax.spines["left"].set_visible(izquierda)
    # Borde inferior: se deja o se quita
    ax.spines["bottom"].set_visible(abajo)
    # Sin las rayitas de las marcas
    ax.tick_params(length=0)


def _colores(etiquetas, destacar):
    """Color de cada barra: naranja las que se destacan, azul las demás; para si se destaca un grupo que no existe."""
    # Grupos que se destacan
    destacar = [str(d) for d in (destacar or [])]
    # Un nombre que no está entre los grupos es un error de quien llama
    faltan = [d for d in destacar if d not in [str(e) for e in etiquetas]]
    # Si falta alguno, se para
    if faltan:
        # Se para diciendo cuáles
        raise ValueError(f"destacar: {faltan} no están entre los grupos del gráfico")
    # Naranja para los destacados, azul para el resto
    return [PALETA[1] if str(e) in destacar else PALETA[0] for e in etiquetas]


def _no_negativos(valores, funcion):
    """Para si hay negativos en un gráfico de barras que tienen que empezar en cero y sumar su total (G4)."""
    # Se busca algún negativo
    if any(v < 0 for v in valores):
        # Se para diciendo la regla y la función que sí los admite
        raise ValueError(f"G4: {funcion} no admite valores negativos; para una desviación, barra_divergente")


# =====================================================================================================================
# LOS NUEVE GRÁFICOS
# =====================================================================================================================

def barras_ordenadas(etiquetas, series, decimales=0, unidad="", ancho=ANCHO, maximo=None, ordenar=True, n=None,
                     destacar=None, medida=""):
    """Ranking: barras horizontales de mayor a menor (por la primera serie), cifra en cada barra, eje desde cero.

    `ordenar=False` deja el orden recibido, para repetirlo en otro gráfico (G8); `maximo=` fija la escala.
    `destacar=` (con una sola serie) pone en naranja los grupos que son lo peor o la alerta (G3). `medida=` dice en la etiqueta
    de cada barra qué se mide (G20).
    """
    # Series en orden de la paleta; para con más de cuatro
    s = _series(series)
    # Todas las barras empiezan en cero: sin negativos
    _no_negativos([v for _, valores in s for v in valores], "barras_ordenadas")
    # Nombres con su n, si se da (G9)
    nombres = _con_n(etiquetas, n)
    # Número de grupos
    k_grupos = len(nombres)
    # Número de series
    k = len(s)
    # Destacar solo tiene sentido con una serie: con varias, el color ya distingue las series
    if destacar and k > 1:
        # Se para diciendo por qué
        raise ValueError("destacar: solo con una serie; con varias, cada serie ya lleva su color")
    # Color de cada barra de la primera serie
    colores = _colores(etiquetas, destacar)
    # Orden de mayor a menor según la primera serie, o el recibido
    orden = sorted(range(k_grupos), key=lambda i: s[0][1][i], reverse=True) if ordenar else list(range(k_grupos))
    # Alto de cada barra dentro de su grupo
    alto_barra = 0.8 / k
    # Alto de la figura según el número de barras
    alto = 30 + k_grupos * (14 + 24 * k) + (30 if k > 1 else 0)
    # Tope del eje: el mayor dato o el maximo común
    tope = _escala(max([v for _, valores in s for v in valores] + [0]), maximo, "barras_ordenadas")
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Cada serie, en su color
        for j, (nombre, valores) in enumerate(s):
            # Posición de cada grupo: el primero arriba
            y = [k_grupos - 1 - orden.index(i) + (k - 1) / 2 * alto_barra - j * alto_barra for i in range(k_grupos)]
            # Barras desde cero; con una serie, cada barra en su color (destacada o no)
            barras = ax.barh(y, valores, height=alto_barra * 0.9, color=colores if k == 1 else PALETA[j], linewidth=0,
                             label=nombre)
            # Cifra al final de cada barra
            for yi, v in zip(y, valores):
                # Texto de la cifra
                ax.text(v + tope * 0.01, yi, numero(v, decimales, unidad), va="center", ha="left")
            # Cada barra con su etiqueta al pasar el ratón (G20)
            for barra, grupo, v in zip(barras.patches, etiquetas, valores):
                # Grupo, serie, medida y cifra exacta
                _dato(fig, barra, _etiqueta(grupo, numero(v, decimales, unidad), medida, nombre))
        # Nombre de cada grupo en su posición
        ax.set_yticks([k_grupos - 1 - orden.index(i) for i in range(k_grupos)], nombres)
        # Eje desde cero, con sitio para las cifras
        ax.set_xlim(0, tope * 1.2 if tope else 1)
        # Sin eje horizontal: cada barra lleva su cifra
        ax.xaxis.set_visible(False)
        # Solo la línea base a la izquierda
        _limpiar_ejes(ax, izquierda=True, abajo=False)
        # Con varias series, la leyenda pegada encima (G16)
        if k > 1:
            # Leyenda en una fila sobre el gráfico
            ax.legend(loc="lower left", bbox_to_anchor=(0, 1), ncol=k, handlelength=1, borderaxespad=0.2)
        # SVG listo, con las barras empezando en el mismo sitio que las de los demás gráficos
        return _a_svg(fig, IZQUIERDA_BARRAS)


def barras_con_intervalo(etiquetas, valores, bajos, altos, referencia=None, rotulo_referencia="", decimales=2,
                         unidad="", ancho=ANCHO, intervalo="", maximo=None, n=None, destacar=None, medida=""):
    """Grupos con su intervalo: cifra e intervalo en cada barra, y dentro del gráfico qué intervalo es (G5).

    `intervalo` es obligatorio y dice qué es, por ejemplo «intervalo del 95 %»; va debajo del dibujo, y el paréntesis
    de cada barra, en gris, para que la cifra destaque. El extremo bajo puede ser negativo: entonces se marca la línea
    del cero. `destacar=` pone en naranja los grupos que son lo peor o la alerta (G3).
    """
    # Un intervalo sin decir qué es incumple G5
    if not str(intervalo).strip():
        # Se para diciendo la regla
        raise ValueError("G5: barras_con_intervalo necesita intervalo=, que diga qué es (p. ej. «intervalo del 95 %»)")
    # Una sola serie, comprobada
    (_, v), = _series(list(valores))
    # Extremos de los intervalos, como números
    b, a = [float(x) for x in bajos], [float(x) for x in altos]
    # Cada valor tiene que tener su intervalo, y el intervalo tiene que contener al valor
    if not (len(v) == len(b) == len(a) == len(etiquetas)) or any(not bi <= vi <= ai for vi, bi, ai in zip(v, b, a)):
        # Se para: un intervalo que no contiene su valor está mal calculado
        raise ValueError("barras_con_intervalo: cada valor necesita su intervalo, y el intervalo tiene que contenerlo")
    # Las barras empiezan en cero: los valores, sin negativos; el extremo bajo del intervalo sí puede serlo
    _no_negativos(v, "barras_con_intervalo")
    # Nombres con su n, si se da (G9)
    nombres = _con_n(etiquetas, n)
    # Número de grupos
    k = len(nombres)
    # Alto de la figura según el número de barras, con sitio debajo para la nota del intervalo
    alto = 70 + k * 34
    # Color de cada barra
    colores = _colores(etiquetas, destacar)
    # Tope del eje: el mayor extremo o el maximo común
    tope = _escala(max(a + v), maximo, "barras_con_intervalo")
    # Extremo más bajo, que puede quedar por debajo de cero
    suelo = min(b + [0])
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Posiciones: el primer grupo arriba, en el orden recibido
        y = [k - 1 - i for i in range(k)]
        # Barras desde cero
        barras = ax.barh(y, v, height=0.6, color=colores, linewidth=0)
        # Cada barra con su etiqueta al pasar el ratón: la cifra y su intervalo (G20)
        for barra, grupo, vi, bi, ai in zip(barras.patches, etiquetas, v, b, a):
            # Grupo, medida, cifra exacta y el intervalo dicho
            _dato(fig, barra, _etiqueta(grupo, f"{numero(vi, decimales, unidad)} ({intervalo}: "
                                               f"{numero(bi, decimales)} a {numero(ai, decimales, unidad)})", medida))
        # Intervalo de cada barra, en tinta
        ax.errorbar(v, y, xerr=[[vi - bi for vi, bi in zip(v, b)], [ai - vi for vi, ai in zip(v, a)]], fmt="none",
                    ecolor=TINTA, elinewidth=1.2, capsize=4)
        # Cifra al lado de cada barra, en tinta
        cifras = [ax.text(max(ai, vi) + tope * 0.04, yi, numero(vi, decimales, unidad), va="center", ha="left")
                  for yi, vi, ai in zip(y, v, a)]
        # Se dibuja para saber cuánto ocupa cada cifra
        fig.canvas.draw()
        # El intervalo entre paréntesis, en gris, justo detrás de su cifra
        for cifra, yi, vi, bi, ai in zip(cifras, y, v, b, a):
            # Ancho de la cifra en px
            ancho_cifra = cifra.get_window_extent().width
            # Paréntesis desplazado ese ancho más un espacio, anclado al mismo punto que la cifra
            ax.annotate(f"({numero(bi, decimales)} a {numero(ai, decimales, unidad)})", xy=cifra.get_position(),
                        xytext=(ancho_cifra + 4, 0), textcoords="offset pixels", color=SECUNDARIO, va="center",
                        ha="left")
        # Qué es el paréntesis, debajo del dibujo (G5)
        ax.text(0, 0, f"Entre paréntesis, el {intervalo}", transform=ax.transAxes, color=SECUNDARIO, va="top",
                ha="left")
        # Línea de referencia con su rótulo (G5)
        if referencia is not None:
            # Línea discontinua en el gris de líneas
            ax.axvline(referencia, color=LINEA, linewidth=1, linestyle=(0, (4, 3)))
            # Rótulo encima de la línea, dentro del gráfico
            ax.text(referencia, k - 0.35, " " + (rotulo_referencia or numero(referencia, decimales, unidad)),
                    color=SECUNDARIO, va="bottom", ha="left")
        # Si algún intervalo baja de cero, la línea del cero hace de base
        if suelo < 0:
            # Línea del cero, en tinta
            ax.axvline(0, color=TINTA, linewidth=1)
        # Nombre de cada grupo
        ax.set_yticks(y, nombres)
        # Eje desde cero (o desde el extremo más bajo), con sitio para las cifras
        ax.set_xlim(suelo * 1.15, tope * 1.55)
        # Sitio arriba para el rótulo de la referencia y abajo para la nota del intervalo
        ax.set_ylim(-0.6, k + 0.1)
        # Sin eje horizontal: cada barra lleva su cifra
        ax.xaxis.set_visible(False)
        # La línea base a la izquierda solo si no hay negativos; si los hay, la base es la línea del cero
        _limpiar_ejes(ax, izquierda=suelo >= 0, abajo=False)
        # SVG listo, con las barras empezando en el mismo sitio que las de los demás gráficos
        return _a_svg(fig, IZQUIERDA_BARRAS)


def barra_divergente(etiquetas, valores, referencia=0, rotulo_referencia="", decimales=1, unidad="", ancho=ANCHO,
                     n=None, destacar=None, medida=""):
    """Desviación sobre una referencia: barras a los dos lados, en un solo color, con la desviación y su signo.

    Con una referencia distinta de cero, `rotulo_referencia` es obligatorio: la línea se explica en el gráfico (G5).
    `destacar=` pone en naranja los grupos que son lo peor o la alerta (G3).
    """
    # Una referencia que no es cero tiene que decir qué es (G5)
    if referencia != 0 and not str(rotulo_referencia).strip():
        # Se para diciendo la regla
        raise ValueError(f"G5: barra_divergente con referencia {referencia} necesita rotulo_referencia=")
    # Una sola serie, comprobada
    (_, v), = _series(list(valores))
    # Desviación de cada valor sobre la referencia
    d = [x - referencia for x in v]
    # Nombres con su n, si se da (G9)
    nombres = _con_n(etiquetas, n)
    # Número de barras
    k = len(nombres)
    # Alto de la figura según el número de barras
    alto = 40 + k * 36
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Posiciones: la primera arriba
        y = [k - 1 - i for i in range(k)]
        # Barras desde la referencia; el signo lo dice la cifra, y el naranja, lo peor o la alerta (G3)
        barras = ax.barh(y, d, left=referencia, height=0.6, color=_colores(etiquetas, destacar), linewidth=0)
        # Cada barra con su etiqueta: el valor y su desviación sobre la referencia (G20)
        for barra, grupo, x, di in zip(barras.patches, etiquetas, v, d):
            # Con referencia cero el valor es la desviación; si no, se dicen los dos
            cifra = (numero(di, decimales, unidad, con_signo=True) if referencia == 0 else
                     f"{numero(x, decimales, unidad)} ({numero(di, decimales, unidad, con_signo=True)} sobre "
                     f"{rotulo_referencia})")
            # Grupo, medida y cifra
            _dato(fig, barra, _etiqueta(grupo, cifra, medida))
        # Línea de la referencia, en tinta
        ax.axvline(referencia, color=TINTA, linewidth=1)
        # Mayor desviación, para el margen
        mayor = max([abs(x) for x in d] + [1e-9])
        # Desviación con signo al final de cada barra (G4: la cifra es lo que mide la barra)
        for yi, x, di in zip(y, v, d):
            # A la derecha si sube, a la izquierda si baja
            ax.text(x + (1 if di >= 0 else -1) * mayor * 0.03, yi, numero(di, decimales, unidad, con_signo=True),
                    va="center", ha="left" if di >= 0 else "right")
        # Rótulo de la referencia si se da (G5)
        if rotulo_referencia:
            # Encima de la línea
            ax.text(referencia, k - 0.4, " " + rotulo_referencia, color=SECUNDARIO, va="bottom", ha="left")
        # Nombre de cada barra
        ax.set_yticks(y, nombres)
        # Margen igual a los dos lados de la referencia
        ax.set_xlim(referencia - mayor * 1.4, referencia + mayor * 1.4)
        # Sitio arriba para el rótulo
        ax.set_ylim(-0.6, k - 0.1 + (0.5 if rotulo_referencia else 0))
        # Sin eje horizontal: cada barra lleva su cifra
        ax.xaxis.set_visible(False)
        # Sin bordes: la línea de referencia hace de base
        _limpiar_ejes(ax, izquierda=False, abajo=False)
        # SVG listo, con los nombres en el mismo sitio que en las barras
        return _a_svg(fig, IZQUIERDA_BARRAS)


def linea_tiempo(periodos, series, previsto_desde=None, decimales=0, unidad="", ancho=ANCHO, alto=320, medida=""):
    """Evolución: cuatro líneas como mucho, cada una con su nombre y su última cifra al final (G16).

    Lo previsto va discontinuo y lleva «previsto» encima de su tramo (G19). Los nombres del final se separan para que
    no se monten aunque las líneas acaben cerca.
    """
    # Series en orden de la paleta; para con más de cuatro (G3 y G18)
    s = _series(series)
    # Número de periodos
    k = len(periodos)
    # El primer periodo previsto tiene que dejar al menos uno real
    if previsto_desde is not None and not 1 <= previsto_desde < k:
        # Se para diciendo qué valores valen
        raise ValueError(f"previsto_desde tiene que ir de 1 a {k - 1}")
    # Hasta dónde llega lo real
    corte = k if previsto_desde is None else previsto_desde
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Posición de cada periodo
        x = list(range(k))
        # Cada serie, en su color
        for j, (nombre, valores) in enumerate(s):
            # Tramo real, continuo
            ax.plot(x[:corte], valores[:corte], color=PALETA[j])
            # Tramo previsto, discontinuo y en el mismo color, desde el último real
            if corte < k:
                # Línea discontinua
                ax.plot(x[corte - 1:], valores[corte - 1:], color=PALETA[j], linestyle=(0, (5, 3)))
            # Cada punto con su etiqueta al pasar el ratón; los previstos lo dicen (G20)
            for xi, periodo, valor in zip(x, periodos, valores):
                # Periodo, serie, medida y cifra exacta
                _punto(fig, ax, xi, valor, _etiqueta(periodo, numero(valor, decimales, unidad)
                                                     + (" (previsto)" if xi >= corte else ""), medida, nombre))
        # Escala vertical fijada ya, para colocar los nombres
        bajo, alto_eje = ax.get_ylim()
        # Unidades del eje que ocupan la separación mínima, contando con que el eje mide al menos el 70 % del alto
        hueco = SEPARACION_NOMBRES * (alto_eje - bajo) / (alto * 0.7)
        # Final de cada línea, de abajo arriba
        finales = sorted(((valores[-1], nombre) for nombre, valores in s), key=lambda f: f[0])
        # Altura de cada nombre: la del final de su línea, subida si pisa al de debajo
        alturas = []
        # Cada final
        for valor, _ in finales:
            # Como poco, la separación sobre el anterior
            alturas.append(max(valor, alturas[-1] + hueco) if alturas else valor)
        # Cada nombre con su última cifra, pegado al final de su línea
        for (valor, nombre), altura in zip(finales, alturas):
            # Texto: nombre y cifra, o solo la cifra si la serie no tiene nombre
            rotulo = " ".join(p for p in [nombre, numero(valor, decimales, unidad)] if p)
            # Texto a la derecha del último punto
            ax.text(k - 1 + 0.08, altura, rotulo, va="center", ha="left")
        # Lo previsto dice «previsto» encima de su tramo (G19)
        if corte < k:
            # Texto centrado sobre el tramo discontinuo, arriba del gráfico
            ax.text((corte - 1 + k - 1) / 2, 1, "previsto", transform=ax.get_xaxis_transform(), color=SECUNDARIO,
                    ha="center", va="bottom")
        # Nombre de cada periodo
        ax.set_xticks(x, periodos)
        # Sitio a la derecha para los nombres
        ax.set_xlim(-0.2, k - 1 + 1.4)
        # Se mantiene la escala vertical
        ax.set_ylim(bajo, alto_eje)
        # Números del eje vertical a la española, en marcas redondas
        _eje(ax.yaxis, decimales, unidad)
        # Los puntos no llevan cifra: cuadrícula fina horizontal (G17)
        ax.grid(True, axis="y")
        # Cuadrícula detrás de las líneas
        ax.set_axisbelow(True)
        # Solo la línea base abajo
        _limpiar_ejes(ax, izquierda=False, abajo=True)
        # SVG listo
        return _a_svg(fig, IZQUIERDA_EJE)


def columnas_tiempo(periodos, valores, previsto_desde=None, decimales=0, unidad="", ancho=ANCHO, alto=320,
                    maximo=None, medida=""):
    """Evolución en pocos periodos: columnas desde cero con su cifra; lo previsto, rayado y sin relleno (G19)."""
    # Una sola serie, comprobada
    (_, v), = _series(list(valores))
    # Número de periodos
    k = len(periodos)
    # El primer periodo previsto tiene que dejar al menos uno real
    if previsto_desde is not None and not 1 <= previsto_desde < k:
        # Se para diciendo qué valores valen
        raise ValueError(f"previsto_desde tiene que ir de 1 a {k - 1}")
    # Hasta dónde llega lo real
    corte = k if previsto_desde is None else previsto_desde
    # Tope del eje: el mayor dato o el maximo común
    tope = _escala(max(v + [0]), maximo, "columnas_tiempo")
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Columnas reales, rellenas
        columnas = list(ax.bar(range(corte), v[:corte], width=0.6, color=PALETA[0], linewidth=0).patches)
        # Columnas previstas, en blanco con rayado del mismo color
        if corte < k:
            # Mismo color en el borde y en el rayado
            columnas += list(ax.bar(range(corte, k), v[corte:], width=0.6, facecolor=BLANCO, edgecolor=PALETA[0],
                                    hatch="///", linewidth=1.2).patches)
        # Cada columna con su etiqueta al pasar el ratón; las previstas lo dicen (G20)
        for i, (columna, periodo, x) in enumerate(zip(columnas, periodos, v)):
            # Periodo, medida y cifra exacta
            _dato(fig, columna, _etiqueta(periodo, numero(x, decimales, unidad) + (" (previsto)" if i >= corte else ""),
                                          medida))
        # Mayor valor absoluto, para los márgenes
        mayor = max([abs(x) for x in v] + [tope, 1e-9])
        # Cifra en cada columna, encima si sube y debajo si baja
        for i, x in enumerate(v):
            # Posición vertical de la cifra
            ax.text(i, x + (1 if x >= 0 else -1) * mayor * 0.03, numero(x, decimales, unidad), ha="center",
                    va="bottom" if x >= 0 else "top")
            # Las previstas dicen «previsto» encima de su cifra
            if i >= corte:
                # Texto en secundario
                ax.text(i, x + (1 if x >= 0 else -1) * mayor * 0.13, "previsto", ha="center", color=SECUNDARIO,
                        va="bottom" if x >= 0 else "top")
        # Nombre de cada periodo
        ax.set_xticks(range(k), periodos)
        # Eje desde cero, con sitio para las cifras
        ax.set_ylim(min(0, min(v) * 1.3), max(0, tope) * 1.3 or 1)
        # Sin eje vertical: cada columna lleva su cifra
        ax.yaxis.set_visible(False)
        # Línea base en cero
        ax.axhline(0, color=LINEA, linewidth=0.8)
        # Sin bordes: la línea del cero hace de base
        _limpiar_ejes(ax, izquierda=False, abajo=False)
        # SVG listo
        return _a_svg(fig)


def columna_apilada(categorias, partes, decimales=0, unidad="", ancho=ANCHO, alto=360, porcentaje=False,
                    maximo=None, medida=""):
    """Parte del todo: tramos que suman su total, cifra en cada tramo, total encima y nombre de cada tramo al lado.

    Con `porcentaje=True` cada columna va al 100 %: los tramos dicen su peso con un decimal y encima va el total en
    su unidad. Es la forma de hablar de peso (G1); en importes, el título habla de importes.
    """
    # Partes en orden de la paleta; para con más de cuatro
    s = _series(partes)
    # Las partes suman su total: sin negativos (G4)
    _no_negativos([x for _, valores in s for x in valores], "columna_apilada")
    # Número de columnas
    k = len(categorias)
    # Total de cada columna: la suma de sus tramos
    totales = [sum(valores[i] for _, valores in s) for i in range(k)]
    # Al 100 %, una columna sin total no tiene peso que repartir
    if porcentaje and any(t == 0 for t in totales):
        # Se para diciendo cuál
        raise ValueError("columna_apilada al 100 %: hay columnas con total cero")
    # Lo que se dibuja: el peso de cada tramo o su importe
    dibujo = [(nombre, [x / t * 100 for x, t in zip(valores, totales)] if porcentaje else valores)
              for nombre, valores in s]
    # Tope del eje: 100 al porcentaje; si no, el mayor total o el maximo común
    tope = 100 if porcentaje else _escala(max(totales + [0]), maximo, "columna_apilada")
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Altura acumulada de cada columna
        base = [0.0] * k
        # Cada tramo, en su color
        for j, (nombre, valores) in enumerate(dibujo):
            # Tramo encima del anterior
            tramos = ax.bar(range(k), valores, bottom=base, width=0.6, color=PALETA[j], linewidth=0)
            # Cada tramo con su etiqueta: al 100 %, el peso y el importe (G20)
            for i, tramo in enumerate(tramos.patches):
                # Importe del tramo, tal como llega
                importe = numero(s[j][1][i], decimales, unidad)
                # Al 100 %, el peso con un decimal y el importe entre paréntesis
                cifra = f"{numero(valores[i], 1, ' %')} ({importe})" if porcentaje else importe
                # Columna, tramo, medida y cifra
                _dato(fig, tramo, _etiqueta(categorias[i], cifra, medida, nombre))
            # Cifra en el centro de cada tramo
            for i, x in enumerate(valores):
                # Texto en tinta: el peso con un decimal o el importe
                cifra = numero(x, 1, " %") if porcentaje else numero(x, decimales, unidad)
                # Alto aproximado del tramo en px: el eje ocupa unas tres cuartas partes del alto (06/10)
                alto_tramo = x / (tope * 1.15 or 1) * alto * 0.75
                # Un tramo más bajo que la letra lleva la cifra al lado de la columna, para no pisar el nombre de abajo
                if alto_tramo < TAMANO * 1.4:
                    # En la última columna va a la izquierda, porque a la derecha van los nombres de los tramos
                    lado = -1 if i == k - 1 else 1
                    # Cifra pegada al borde de la columna, a la altura del tramo
                    ax.text(i + lado * 0.33, base[i] + x / 2, cifra, ha="left" if lado > 0 else "right", va="center")
                # Un tramo con sitio lleva la cifra dentro
                else:
                    # Cifra en el centro del tramo
                    ax.text(i, base[i] + x / 2, cifra, ha="center", va="center")
            # Nombre del tramo a la derecha de la última columna (G16)
            ax.text(k - 1 + 0.36, base[-1] + valores[-1] / 2, nombre, ha="left", va="center")
            # Se sube la base para el tramo siguiente
            base = [b + x for b, x in zip(base, valores)]
        # Total encima de cada columna, en su unidad
        for i, t in enumerate(totales):
            # Total en negrita
            ax.text(i, base[i] + tope * 0.02, numero(t, decimales, unidad), ha="center", va="bottom",
                    fontweight="bold")
        # Nombre de cada columna
        ax.set_xticks(range(k), categorias)
        # Sitio a la derecha para los nombres de los tramos
        ax.set_xlim(-0.5, k - 1 + 1.3)
        # Eje desde cero, con sitio para el total
        ax.set_ylim(0, tope * 1.15 or 1)
        # Sin eje vertical: cada tramo lleva su cifra
        ax.yaxis.set_visible(False)
        # Solo la línea base abajo
        _limpiar_ejes(ax, izquierda=False, abajo=True)
        # SVG listo
        return _a_svg(fig)


def histograma(valores, intervalos=12, log=False, decimales=0, unidad="", etiqueta_x="", ancho=ANCHO, alto=320,
               bordes=None, medida=""):
    """Distribución: cuántos valores caen en cada tramo, sin dibujar fuera del rango de los datos (G10).

    Con datos enteros, los tramos son enteros y se nombran «1-3», «4-6»; si no, las marcas van en los bordes de los
    tramos. Cada tramo lleva su cuenta, también el «0» de los vacíos (G4). `bordes=` fija los tramos para repetirlos
    en otro gráfico (G8).
    """
    # Valores válidos
    v = [float(x) for x in valores if x is not None and math.isfinite(float(x))]
    # Sin valores no hay distribución
    if not v:
        # Se para
        raise ValueError("histograma sin valores")
    # Escala logarítmica solo con valores positivos (G11)
    if log and min(v) <= 0:
        # Se para diciendo la regla y cuántos sobran
        raise ValueError(f"G11: escala logarítmica solo con valores positivos; hay {sum(x <= 0 for x in v)} "
                         f"valores iguales o menores que cero")
    # Menor y mayor valor
    menor, mayor = min(v), max(v)
    # Unos bordes dados tienen que cubrir todos los datos
    if bordes is not None and (menor < bordes[0] or mayor > bordes[-1]):
        # Se para diciendo la regla
        raise ValueError(f"G10: los bordes van de {bordes[0]} a {bordes[-1]} y los datos de {menor} a {mayor}")
    # Datos enteros en escala normal y sin bordes dados: tramos enteros
    enteros = not log and bordes is None and all(x == int(x) for x in v)
    # Tramos enteros: cada uno junta `paso` valores seguidos
    if enteros:
        # Valores enteros que hay que cubrir, del menor al mayor
        cubrir = int(mayor) - int(menor) + 1
        # Valores por tramo
        paso = max(1, math.ceil(cubrir / intervalos))
        # Primer valor de cada tramo
        inicios = list(range(int(menor), int(mayor) + 1, paso))
        # Cuántos valores caen en cada tramo
        cuentas = [sum(i <= x < i + paso for x in v) for i in inicios]
        # Punto de miles solo desde 10.000: los años y los números de cuatro cifras van sin punto (06/10)
        escribir = lambda n: numero(n) if abs(n) >= 10000 else str(n)
        # Nombre de cada tramo, sin pasar del mayor valor (G10)
        nombres = [escribir(i) if min(i + paso - 1, int(mayor)) == i else
                   f"{escribir(i)}-{escribir(min(i + paso - 1, int(mayor)))}" for i in inicios]
    # Tramos con decimales
    else:
        # Bordes dados, o iguales en el logaritmo, o iguales
        if bordes is not None:
            # Los dados
            limites = np.array([float(b) for b in bordes])
        # Un solo valor distinto: un tramo alrededor
        elif menor == mayor:
            # Límites del único tramo
            limites = np.array([menor - 0.5, mayor + 0.5])
        # En escala logarítmica, tramos iguales en el logaritmo
        elif log:
            # Bordes repartidos en escala logarítmica
            limites = np.logspace(math.log10(menor), math.log10(mayor), intervalos + 1)
        # En escala normal, tramos iguales
        else:
            # Bordes repartidos de forma lineal
            limites = np.linspace(menor, mayor, intervalos + 1)
        # Cuántos valores caen en cada tramo
        cuentas, limites = np.histogram(v, bins=limites)
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Mayor cuenta, para los márgenes
        tope = max(max(cuentas), 1)
        # Tramos enteros: una barra por tramo, pegadas, con su nombre debajo
        if enteros:
            # Barras pegadas, separadas por una línea blanca
            barras = ax.bar(range(len(cuentas)), cuentas, width=1, color=PALETA[0], edgecolor=BLANCO, linewidth=1)
            # Centro de cada barra
            centros = list(range(len(cuentas)))
            # Nombre de cada tramo para su etiqueta, con su unidad
            tramos = [f"{t}{unidad}" for t in nombres]
            # Nombre de cada tramo
            ax.set_xticks(centros, nombres)
            # Solo los tramos con datos (G10)
            ax.set_xlim(-0.5, len(cuentas) - 0.5)
        # Tramos con decimales: barras sobre sus bordes, con las marcas en los bordes
        else:
            # Barras pegadas, separadas por una línea blanca
            barras = ax.bar(limites[:-1], cuentas, width=np.diff(limites), align="edge", color=PALETA[0],
                            edgecolor=BLANCO, linewidth=1)
            # Cada tramo dicho por sus bordes, para su etiqueta
            tramos = [f"de {numero(i, decimales)} a {numero(d, decimales, unidad)}"
                      for i, d in zip(limites[:-1], limites[1:])]
            # Centro de cada barra (en escala logarítmica, el centro geométrico)
            centros = [math.sqrt(i * d) if log else (i + d) / 2 for i, d in zip(limites[:-1], limites[1:])]
            # Escala logarítmica dicha en el eje (G11)
            if log:
                # Eje horizontal logarítmico
                ax.set_xscale("log")
            # Marcas en los bordes de los tramos
            ax.set_xticks(limites)
            # Números a la española
            ax.xaxis.set_major_formatter(_formato_eje(decimales, unidad))
            # Sin números en las marcas menores
            ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
            # Solo el rango de los tramos (G10)
            ax.set_xlim(limites[0], limites[-1])
        # Cuenta encima de cada barra, también el cero de los vacíos (G4)
        for centro, c in zip(centros, cuentas):
            # Texto de la cuenta
            ax.text(centro, c + tope * 0.02, numero(c), ha="center", va="bottom")
        # Cada tramo con su etiqueta al pasar el ratón: el tramo y cuántos valores caen en él (G20)
        for barra, tramo, c in zip(barras.patches, tramos, cuentas):
            # Tramo, con lo que se mide delante si se dice, y la cuenta
            _dato(fig, barra, _etiqueta(" ".join(p for p in (etiqueta_x, tramo) if p), numero(c), medida))
        # Eje desde cero, con sitio para las cifras
        ax.set_ylim(0, tope * 1.15)
        # Título del eje horizontal, con la escala si es logarítmica
        ax.set_xlabel(" ".join(p for p in [etiqueta_x, "(escala logarítmica)" if log else ""] if p))
        # Sin eje vertical: cada barra lleva su cifra
        ax.yaxis.set_visible(False)
        # Solo la línea base abajo
        _limpiar_ejes(ax, izquierda=False, abajo=True)
        # SVG listo
        return _a_svg(fig)


def dispersion(x, y, etiqueta_x="", etiqueta_y="", decimales_x=0, decimales_y=0, ancho=ANCHO, alto=360,
               log_x=False, log_y=False, nombres=None):
    """Relación entre dos medidas: un punto por elemento y un solo eje para cada medida (G15).

    Con más de 100 puntos, los puntos van huecos para que se vean los que se tapan. `log_x` y `log_y` ponen la escala
    logarítmica, solo con valores positivos y dicho en el eje (G11). El título del eje vertical va en horizontal,
    arriba a la izquierda. Cada punto lleva su etiqueta con las dos cifras; `nombres=` le pone delante el nombre de
    cada elemento (G20).
    """
    # Las dos medidas tienen que tener el mismo número de elementos
    if len(x) != len(y):
        # Se para diciendo cuántos tiene cada una
        raise ValueError(f"dispersion: {len(x)} valores en x y {len(y)} en y")
    # Medidas como números, comprobadas
    (_, vx), (_, vy) = _series({"x": x, "y": y})
    # Escala logarítmica solo con valores positivos (G11)
    for log, valores, eje in ((log_x, vx, "horizontal"), (log_y, vy, "vertical")):
        # Se mira cada eje que la pide
        if log and min(valores) <= 0:
            # Se para diciendo la regla
            raise ValueError(f"G11: escala logarítmica en el eje {eje} solo con valores positivos; hay "
                             f"{sum(v <= 0 for v in valores)} iguales o menores que cero")
    # Muchos puntos: huecos para que no se tapen
    huecos = len(vx) > PUNTOS_HUECOS
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Un punto por elemento, en el primer color: hueco si son muchos, relleno si son pocos
        if huecos:
            # Círculo de 6 px con borde y sin relleno
            ax.scatter(vx, vy, s=36, facecolors="none", edgecolors=PALETA[0], linewidths=1)
        # Pocos puntos
        else:
            # Círculo de 8 px relleno
            ax.scatter(vx, vy, s=64, color=PALETA[0], linewidths=0)
        # Un nombre por punto, si se dan
        if nombres is not None and len(nombres) != len(vx):
            # Se para diciendo cuántos faltan
            raise ValueError(f"dispersion: {len(vx)} puntos y {len(nombres)} nombres")
        # Cada punto con su etiqueta al pasar el ratón: las dos cifras con lo que mide cada una (G20)
        for i, (xi, yi) in enumerate(zip(vx, vy)):
            # Las dos cifras, cada una con su medida
            cifras = " · ".join(f"{e}: {c}" if e else c for e, c in
                                ((etiqueta_x, numero(xi, decimales_x)), (etiqueta_y, numero(yi, decimales_y))))
            # Con el nombre del elemento delante, si se da
            _punto(fig, ax, xi, yi, f"{nombres[i]} · {cifras}" if nombres is not None else cifras)
        # Escala logarítmica del eje horizontal, si se pide
        if log_x:
            # Eje horizontal logarítmico
            ax.set_xscale("log")
        # Escala logarítmica del eje vertical, si se pide
        if log_y:
            # Eje vertical logarítmico
            ax.set_yscale("log")
        # Números de los dos ejes a la española, en marcas que no se repiten
        _eje(ax.xaxis, decimales_x, log=log_x)
        # Eje vertical
        _eje(ax.yaxis, decimales_y, log=log_y)
        # Título del eje horizontal, con la escala si es logarítmica
        ax.set_xlabel(" ".join(p for p in [etiqueta_x, "(escala logarítmica)" if log_x else ""] if p))
        # Título del eje vertical en horizontal, arriba a la izquierda, que se lee sin girar la cabeza
        ax.text(0, 1.02, " ".join(p for p in [etiqueta_y, "(escala logarítmica)" if log_y else ""] if p),
                transform=ax.transAxes, color=SECUNDARIO, ha="left", va="bottom")
        # Los puntos no llevan cifra: cuadrícula fina (G17)
        ax.grid(True)
        # Cuadrícula detrás de los puntos
        ax.set_axisbelow(True)
        # Las dos líneas base
        _limpiar_ejes(ax, izquierda=True, abajo=True)
        # SVG listo
        return _a_svg(fig, IZQUIERDA_EJE)


def curva_acumulada(valores, marcas=(10, 20, 50), etiqueta_x="% de los elementos, de mayor a menor",
                    etiqueta_y="% del total", ancho=ANCHO, alto=360, rotulo_igual="reparto igual"):
    """Concentración: qué parte del total reúne cada parte de los elementos, ordenados de mayor a menor (G12 y G14).

    La diagonal es el reparto igual y lleva su rótulo (G5). Cada marca pedida (por ejemplo, el 20 % de los
    elementos) lleva su punto y su cifra. El número de elementos de una marca se redondea hacia arriba (el 20 % de
    1.467 son 294), como se cuenta en el texto que la cita: así el gráfico y el texto dan la misma cifra (T3). Sin
    negativos: un total con negativos no se reparte en partes (G4). `rotulo_igual` es el rótulo de la diagonal. Si la
    curva llega al total antes del 95 % de los elementos, el tramo plano dice qué parte no suma nada.
    """
    # Valores como números, comprobados
    (_, v), = _series(list(valores))
    # Sin valores no hay curva
    if not v:
        # Se para
        raise ValueError("curva_acumulada sin valores")
    # Con negativos, la curva pasaría del 100 %
    _no_negativos(v, "curva_acumulada")
    # Total que se reparte
    total = sum(v)
    # Sin total no hay nada que concentrar
    if total == 0:
        # Se para
        raise ValueError("curva_acumulada: el total es cero")
    # Parte de los elementos, de 0 a 100
    xs = [0.0] + [(i + 1) / len(v) * 100 for i in range(len(v))]
    # Parte del total que reúnen, de mayor a menor
    ys = [0.0] + list(np.cumsum(sorted(v, reverse=True)) / total * 100)
    # Figura con los ajustes de las reglas
    with plt.rc_context(AJUSTES):
        # Figura y ejes
        fig, ax = _figura(ancho, alto)
        # Reparto igual, en el gris de líneas y discontinuo
        ax.plot([0, 100], [0, 100], color=LINEA, linewidth=1, linestyle=(0, (4, 3)))
        # Su rótulo, pegado debajo de la diagonal (G5)
        ax.text(70, 68, rotulo_igual, color=SECUNDARIO, ha="left", va="top")
        # Curva acumulada, en el primer color
        ax.plot(xs, ys, color=PALETA[0])
        # Cada marca pedida, con su punto y su cifra
        for m in marcas:
            # Elementos de la marca, hacia arriba, y la parte del total que reúnen
            cuantos = math.ceil(m / 100 * len(v) - 1e-9)
            # Parte del total que reúnen
            reune = float(ys[cuantos])
            # Punto sobre la curva, donde acaban esos elementos
            punto = ax.scatter([xs[cuantos]], [reune], s=36, color=PALETA[0], linewidths=0, zorder=3)
            # Con su etiqueta al pasar el ratón: cuántos elementos son y qué parte reúnen (G20)
            _dato(fig, punto, f"el {numero(m)} % de los elementos ({numero(cuantos)} de {numero(len(v))}) reúne el "
                              f"{numero(reune, 1)} % del total")
            # Cifra al lado del punto
            ax.text(xs[cuantos] + 1.5, reune, f"el {numero(m)} % reúne el {numero(reune, 1)} %", va="top", ha="left")
        # Primer elemento con el que la curva llega al total
        lleno = next(i for i, y in enumerate(ys) if y >= 100 - 1e-6)
        # Si llega antes del 95 %, el tramo plano dice cuántos no suman nada
        if xs[lleno] < 95:
            # Rótulo sobre el tramo plano
            ax.text((xs[lleno] + 100) / 2, 100, f"el {numero(100 - xs[lleno])} % restante no suma nada",
                    color=SECUNDARIO, ha="center", va="bottom")
        # Los dos ejes de 0 a 100
        ax.set_xlim(0, 100)
        # Con un poco de aire arriba
        ax.set_ylim(0, 105)
        # Números a la española con su %
        _eje(ax.xaxis, 0, " %")
        # Eje vertical
        _eje(ax.yaxis, 0, " %")
        # Sin el 0 % vertical, que se montaría con el 0 % horizontal en la esquina
        ax.set_yticks(range(20, 101, 20))
        # Título del eje horizontal
        ax.set_xlabel(etiqueta_x)
        # Título del eje vertical en horizontal, arriba a la izquierda
        ax.text(0, 1.02, etiqueta_y, transform=ax.transAxes, color=SECUNDARIO, ha="left", va="bottom")
        # La curva no lleva cifra en cada punto: cuadrícula fina (G17)
        ax.grid(True)
        # Cuadrícula detrás de la curva
        ax.set_axisbelow(True)
        # Las dos líneas base
        _limpiar_ejes(ax, izquierda=True, abajo=True)
        # SVG listo
        return _a_svg(fig, IZQUIERDA_EJE)
