"""Monta el HTML de un informe que cumple las reglas de salida (`reglas_de_salida.md`, S1 a S4, C1 a C2, TB1 a TB4, F1, D7).

Spec: `spec_v3_piezas.md`. Suite: `probar_piezas.py`. Banco: `banco/comprobar_informe.py`.

Un solo fichero HTML con la hoja de estilos `estilo.css` dentro, un panel fijo a la izquierda con las páginas y
cambio de página sin recargar; al recargar, se queda en la página que estaba. Cada página se compone solo de cuatro
bloques (S4): cifras clave, texto, gráfico y tabla.

Uso:

    informe = Informe("Valor de los clientes", "datos a 31/12/2025")
    resumen = informe.pagina("Resumen", "resumen")
    resumen.cifra_clave("1.234 €", "margen medio por cliente", "de 2023 a 2025")
    resumen.cifra_clave(1.08, "margen por euro", "de 2023 a 2025", decimales=2, unidad=" €")
    resumen.texto("Primera frase con la respuesta.", "Segundo párrafo.")
    resumen.grafico(svg, "El título dice la conclusión", "Medida, unidad, periodo. Fuente: ventas, datos a 31/12/2025")
    resumen.fila(svg_a, "Título A", "Medida. Fuente: ventas", svg_b, "Título B", "Medida. Fuente: ventas")
    resumen.tabla(["Grupo", "Clientes", "Margen por euro (€)"], [["A", 120, 1.08], ["B", 80, 0.95]],
                  fuente="ventas, datos a 31/12/2025", totales=["", "suma", ""], decimales=[0, 0, 2])
    canales = informe.pagina("Canales", "pregunta", pregunta="¿Qué canales dejan más margen?")
    anexo = informe.pagina("Anexo con el método y las fuentes", "anexo", panel="Método y fuentes")
    informe.guardar("informes/informe_final.html")

Las páginas van en el orden de S2 (resumen, una por pregunta, límites, decisiones propuestas y anexo); una pregunta,
los límites, las decisiones o el anexo que no caben se parten en páginas seguidas, y la pregunta partida lleva el mismo
número; su pregunta entera va solo en la primera página y las siguientes dicen «Pregunta N, sigue» (S3 y D7). Sin
contar el anexo, como mucho 15 páginas (D7). Si se crean en otro orden, para; una página de pregunta sin la pregunta,
también. Con más de cuatro cifras clave en una página, para
(C2). Un gráfico sin «Fuente:» en el subtítulo, para (G2): la fuente sale del subtítulo y va en su propia línea,
debajo del dibujo, como en la ficha de gráficos de la ONS; una tabla sin fuente, también para (F1). Una cifra con decimales
sin decir cuántos, para (F2 y TB2). Al montar, una página más alta de lo que cabe en la pantalla, para (S3): la
cuenta, con las medidas de `estilo.css`, es la misma que `alto_por_pagina()` del banco, y la suite comprueba que dan
lo mismo. Así las tres piezas funcionan solas, copiadas a `scripts/` de un caso sin el banco.
"""

# html escapa el texto que entra en el informe
import html
# math redondea hacia arriba las líneas de un párrafo
import math
# re lee el ancho y el alto de un SVG
import re
# Path encuentra la hoja de estilos junto a este fichero
from pathlib import Path

# numero escribe las cifras a la española, igual que en los gráficos; ANCHO_FILA es el ancho de dos lado a lado
from graficos import numero, ANCHO_FILA


# Orden de las páginas (S2) y cuántas puede haber de cada clase; preguntas, límites y decisiones se pueden partir (S3;
# las decisiones desde el 07/10, caso 04). El anexo, al final, desde el 07/10 (D6)
ORDEN = {"resumen": 1, "pregunta": None, "limites": None, "decision": None, "anexo": None}
# Como mucho 15 páginas sin contar el anexo 
MAX_PAGINAS = 15
# Como mucho cuatro cifras clave por página (C2)
MAX_CIFRAS = 4
# Hoja de estilos, junto a este fichero
ESTILO = Path(__file__).with_name("estilo.css")
# S3: alto que se ve de una página en una pantalla de 1366 × 768 con el navegador abierto, en px
ALTO_UTIL = 650
# Lo que ocupa cada bloque con estilo.css, en px: las mismas medidas que ALTO en banco/comprobar_informe.py. Cada
# bloque cuenta su margen de arriba, su contenido y su margen de abajo; entre dos bloques seguidos queda el mayor de los
# dos márgenes, como hace el navegador, y el de abajo del último no se ve. Plantilla copiada el 04/10 (ONS, GOV.UK y
# Observable): título del gráfico a 20 px (26 de línea, 4 debajo), subtítulo a 16 (24 de línea, 16 debajo), fuente a
# 13 en su propia línea debajo del dibujo (8 encima), 30 px entre bloques. Caracteres: el texto, unos 7,6 px cada uno;
# el título del gráfico, 10,5; el subtítulo, 9,2; la fuente y las celdas de tabla, 7,3 y 6,6 (7,6 en las tablas de
# texto); una celda se parte a unos 6,6 px por carácter (7,4 en las de texto), y una etiqueta de cifra clave, a 6,8
# (medido en Edge el 04/10: con 6,2 y 6,4 la cuenta se quedaba 9 px corta en el resumen).
ALTO = {"arriba": 24, "h1": 35, "h1_abajo": 12, "cifras": 73, "cifras_arriba": 15, "cifras_abajo": 30,
        "linea_cifra": 19.5, "letra_cifra": 6.8, "ancho_cifras": 1024, "hueco_cifras": 32, "linea_texto": 22.5,
        "parrafo": 12, "caracteres_linea": 85, "caracteres_pregunta": 80, "linea_g_titulo": 26, "letra_g_titulo": 10.5,
        "g_titulo_abajo": 4, "linea_g_sub": 24, "letra_g_sub": 9.2, "g_sub_abajo": 16, "fuente_arriba": 8,
        "linea_fuente": 19.5, "letra_fuente": 7.3, "bloque": 30, "ancho_columna_fila": 500, "fila_tabla": 32,
        "fila_tabla_texto": 34.5, "linea_celda": 19.5, "linea_celda_texto": 22.5, "letra_celda": 6.6,
        "letra_celda_texto": 7.4, "letra_tabla": 6.6, "letra_tabla_texto": 7.6, "relleno_celda": 16,
        "ancho_pagina": 1024, "hueco_lado": 32, "ancho_otro": 640, "letra_texto": 7.6}
# Las cifras clave van en cuatro casillas iguales, haya las que haya (estilo.css)
CASILLAS_CIFRAS = 4

# Cambio de página sin recargar: muestra la página pulsada, la apunta en la dirección, oculta las demás y deja su botón
# a la vista en el panel
SCRIPT = """
function mostrar(id) {
  var boton = document.querySelector('nav button[data-pagina="' + id + '"]');
  if (!boton) { return; }
  document.querySelectorAll('section.pagina').forEach(function (pagina) { pagina.hidden = pagina.id !== id; });
  document.querySelectorAll('nav button').forEach(function (otro) { otro.removeAttribute('aria-current'); });
  boton.setAttribute('aria-current', 'page');
  boton.scrollIntoView({block: 'nearest'});
}
document.querySelectorAll('nav button').forEach(function (boton) {
  boton.addEventListener('click', function () {
    mostrar(boton.dataset.pagina);
    history.replaceState(null, '', '#' + boton.dataset.pagina);
    window.scrollTo(0, 0);
  });
});
if (location.hash) { mostrar(location.hash.slice(1)); }

// G20: cada valor de un gráfico enseña su etiqueta con el ratón y con el tabulador. El texto pasa del <title> a
// aria-label, para que el navegador no saque además su propia etiqueta y el lector de pantalla lo siga leyendo.
var caja = document.querySelector('.etiqueta-dato');
document.querySelectorAll('svg g.dato').forEach(function (dato) {
  var titulo = dato.querySelector('title');
  if (!titulo) { return; }
  dato.dataset.etiqueta = titulo.textContent;
  dato.setAttribute('aria-label', titulo.textContent);
  titulo.remove();
});
function enseñar(dato, x, y) {
  caja.textContent = dato.dataset.etiqueta;
  caja.hidden = false;
  var ancho = caja.offsetWidth, alto = caja.offsetHeight;
  // Al lado del ratón; si no cabe a la derecha o abajo, al otro lado
  var izquierda = x + 12 + ancho > window.innerWidth ? x - 12 - ancho : x + 12;
  var arriba = y + 12 + alto > window.innerHeight ? y - 12 - alto : y + 12;
  caja.style.left = Math.max(0, izquierda) + 'px';
  caja.style.top = Math.max(0, arriba) + 'px';
}
function esconder() { caja.hidden = true; }
document.addEventListener('mouseover', function (e) {
  var dato = e.target.closest ? e.target.closest('g.dato') : null;
  if (dato && dato.dataset.etiqueta) { enseñar(dato, e.clientX, e.clientY); } else { esconder(); }
});
document.addEventListener('mousemove', function (e) {
  var dato = e.target.closest ? e.target.closest('g.dato') : null;
  if (dato && dato.dataset.etiqueta) { enseñar(dato, e.clientX, e.clientY); }
});
document.addEventListener('focusin', function (e) {
  var dato = e.target.closest ? e.target.closest('g.dato') : null;
  if (!dato || !dato.dataset.etiqueta) { esconder(); return; }
  var r = dato.getBoundingClientRect();
  enseñar(dato, r.right, r.top);
});
document.addEventListener('focusout', esconder);
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { esconder(); } });
"""


def _e(texto):
    """Escapa un texto para el HTML."""
    # Escapa <, >, & y comillas
    return html.escape(str(texto))


def _es_numero(valor):
    """Dice si un valor es un número (y no un sí o no)."""
    # Enteros y decimales cuentan; los booleanos no
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _con_aria(svg, titulo):
    """Marca el SVG como imagen con su título, para quien lee con lector de pantalla."""
    # Se añaden role e aria-label a la etiqueta de apertura
    return svg.replace("<svg", f'<svg role="img" aria-label="{_e(titulo)}"', 1)


def _ancho(svg):
    """Ancho del SVG en px, leído de su atributo."""
    # Atributo width de la etiqueta de apertura
    m = re.search(r'<svg[^>]*\bwidth="([\d.]+)', svg)
    # Ancho, o cero si no lo dice
    return float(m.group(1)) if m else 0.0


def _alto(svg):
    """Alto del SVG en px, leído de su atributo."""
    # Atributo height de la etiqueta de apertura
    m = re.search(r'<svg[^>]*\bheight="([\d.]+)', svg)
    # Alto, o cero si no lo dice
    return float(m.group(1)) if m else 0.0


def _caracteres(texto):
    """Caracteres de un texto tal como se ve, con los espacios juntados."""
    # Espacios y saltos seguidos cuentan como uno
    return len(" ".join(str(texto).split()))


def _lineas(caracteres, por_linea):
    """Líneas que ocupa un texto, como poco una."""
    # Hacia arriba: una línea a medias es una línea
    return max(1, math.ceil(caracteres / por_linea))


def _partir_fuente(subtitulo, titulo):
    """Separa el subtítulo en la medida y la línea de fuente, que va debajo del dibujo (G2)."""
    # El subtítulo tiene que decir de dónde salen las cifras (G2 y F1)
    if "Fuente:" not in subtitulo:
        # Se para diciendo la regla
        raise ValueError(f"G2: el subtítulo del gráfico «{titulo}» tiene que decir «Fuente:» y el fichero")
    # Lo de antes de «Fuente:» es la medida; desde ahí, la fuente
    corte = subtitulo.index("Fuente:")
    # Las dos partes, sin espacios sobrantes
    return subtitulo[:corte].strip(), subtitulo[corte:].strip()


def alto_cifras(cifras):
    """Contenido de la fila de cifras clave: [(caracteres de la etiqueta, del contexto)]. Es la cuenta del banco."""
    # Sin cifras no hay fila
    if not cifras:
        # No ocupa nada
        return 0
    # Cada cifra ocupa una de las cuatro casillas: caracteres que caben en una línea de cada una
    por_linea = ((ALTO["ancho_cifras"] - ALTO["hueco_cifras"] * (CASILLAS_CIFRAS - 1)) / CASILLAS_CIFRAS
                 / ALTO["letra_cifra"])
    # La cifra con más líneas de etiqueta y contexto marca el alto de la fila
    lineas = max(_lineas(et, por_linea) + _lineas(ctx, por_linea) for et, ctx in cifras)
    # Alto con una línea de cada, más lo que añade cada línea de más
    return ALTO["cifras"] + (lineas - 2) * ALTO["linea_cifra"]


def alto_grafico(alto_svg, titulo, subtitulo, fuente, ancho):
    """Contenido de un bloque de gráfico de `ancho` px: título, subtítulo, dibujo y fuente. Es la cuenta del banco.

    `titulo`, `subtitulo` y `fuente` son caracteres; un subtítulo o una fuente de 0 caracteres no se escriben.
    """
    # Título, por sus líneas, y su margen
    alto = _lineas(titulo, ancho / ALTO["letra_g_titulo"]) * ALTO["linea_g_titulo"] + ALTO["g_titulo_abajo"]
    # Subtítulo, si lo hay
    if subtitulo:
        # Sus líneas y su margen
        alto += _lineas(subtitulo, ancho / ALTO["letra_g_sub"]) * ALTO["linea_g_sub"] + ALTO["g_sub_abajo"]
    # Dibujo
    alto += alto_svg
    # Fuente, si la hay, debajo del dibujo
    if fuente:
        # Su margen y sus líneas
        alto += ALTO["fuente_arriba"] + _lineas(fuente, ancho / ALTO["letra_fuente"]) * ALTO["linea_fuente"]
    # Alto del bloque
    return alto


def alto_fila(graficos, subtitulo, fuente):
    """Contenido de una fila de dos gráficos: [(alto del SVG, título, subtítulo, fuente)] de cada uno, y el subtítulo
    y la fuente comunes, que van una vez a todo el ancho. Es la cuenta del banco."""
    # Subtítulo común, a todo el ancho
    alto = (_lineas(subtitulo, ALTO["ancho_pagina"] / ALTO["letra_g_sub"]) * ALTO["linea_g_sub"] + ALTO["g_sub_abajo"]
            if subtitulo else 0)
    # Los dos gráficos: el más alto
    alto += max(alto_grafico(a, t, st, f, ALTO["ancho_columna_fila"]) for a, t, st, f in graficos)
    # Fuente común, a todo el ancho
    if fuente:
        # Su margen y sus líneas
        alto += ALTO["fuente_arriba"] + _lineas(fuente, ALTO["ancho_pagina"] / ALTO["letra_fuente"]) * ALTO["linea_fuente"]
    # Alto de la fila
    return alto


def ancho_tabla(filas, texto=False):
    """Ancho de una tabla sin partir ninguna celda, en px: [caracteres de cada celda], fila a fila. Es la cuenta del banco."""
    # Letra de la tabla
    letra = ALTO["letra_tabla_texto" if texto else "letra_tabla"]
    # Por columna, su celda más larga más el relleno
    return sum(max(f[c] for f in filas) * letra + ALTO["relleno_celda"] for c in range(len(filas[0])))


def alto_tabla(filas, fuente, disponible, texto=False):
    """Contenido de una tabla con su fuente debajo, en un sitio de `disponible` px. Es la cuenta del banco.

    `filas` son los caracteres de cada celda, fila a fila y con el encabezado primero; `fuente`, los de la línea de
    fuente. Si la tabla no cabe sin partir, cada columna se queda una parte del sitio en proporción a su celda más larga
    y sus celdas se parten en líneas. Una tabla de texto va a 15 px.
    """
    # Medidas de la clase de tabla
    fila, linea, letra = ((ALTO["fila_tabla_texto"], ALTO["linea_celda_texto"], ALTO["letra_celda_texto"]) if texto
                          else (ALTO["fila_tabla"], ALTO["linea_celda"], ALTO["letra_celda"]))
    # Letra para el ancho sin partir
    letra_ancho = ALTO["letra_tabla_texto" if texto else "letra_tabla"]
    # Ancho de cada columna sin partir
    naturales = [max(f[c] for f in filas) * letra_ancho + ALTO["relleno_celda"] for c in range(len(filas[0]))]
    # Si no caben, se reparten el sitio
    anchos = naturales if sum(naturales) <= disponible else [disponible * n / sum(naturales) for n in naturales]
    # Filas
    alto = 0
    # Cada fila mide lo que su celda con más líneas
    for f in filas:
        # Líneas de la celda más partida
        lineas = max(_lineas(n * letra, a - ALTO["relleno_celda"]) for n, a in zip(f, anchos))
        # Una línea, más lo que suma cada línea de más
        alto += fila + (lineas - 1) * linea
    # La fuente, por sus líneas, con su margen de arriba
    return alto + ALTO["fuente_arriba"] + _lineas(fuente, disponible / ALTO["letra_fuente"]) * ALTO["linea_fuente"]


def alto_texto(parrafos, por_linea):
    """Contenido de una columna de párrafos, cada uno con su margen de abajo. Es la cuenta del banco."""
    # Cada párrafo por sus líneas, más su margen
    return sum(_lineas(c, por_linea) * ALTO["linea_texto"] + ALTO["parrafo"] for c in parrafos)


def apilar(bloques):
    """Alto de una página: [(margen de arriba, contenido, margen de abajo)] de cada bloque, en su orden.

    Entre dos bloques seguidos queda el mayor de los dos márgenes; el de abajo del último no se ve. Es la cuenta del
    banco.
    """
    # Margen de arriba de la página
    alto = ALTO["arriba"]
    # Cada bloque
    for i, (arriba, contenido, _) in enumerate(bloques):
        # Su contenido, y el hueco con el anterior: el mayor de los dos márgenes
        alto += contenido + (max(bloques[i - 1][2], arriba) if i else arriba)
    # Alto redondeado a píxeles
    return round(alto)


class Pagina:
    """Una página del informe: solo cifras clave, texto, gráficos y tablas (S4)."""

    def __init__(self, titulo, tipo, numero_pagina, pregunta="", columnas=True, panel=None):
        # Título de la página (T1)
        self.titulo = titulo
        # Clase de página según S2
        self.tipo = tipo
        # Pregunta que contesta, en las páginas de pregunta
        self.pregunta = pregunta
        # Número de la pregunta, que pone el informe
        self.numero_pregunta = None
        # Si es la segunda página o una posterior de la misma pregunta: dice «Pregunta N, sigue» (D7)
        self.sigue = False
        # Identificador para el panel
        self.id = f"p{numero_pagina}"
        # Título corto para el panel, que quepa en una línea
        self.panel = panel or titulo
        # Cifras clave, que van juntas en una fila arriba
        self.cifras = []
        # Resto de bloques, en el orden en que se añaden: cada uno con su clase, su HTML y lo que pide la cuenta de alto
        self.bloques = []
        # Si el texto y un solo gráfico o una sola tabla pueden ir lado a lado
        self.columnas = columnas

    def _linea_pregunta(self):
        """La línea de la pregunta bajo el título: entera en su primera página, «Pregunta N, sigue» en las demás (D7)."""
        # En una página que sigue, la línea corta
        if self.sigue:
            # Sin repetir la pregunta
            return f"Pregunta {self.numero_pregunta}, sigue"
        # En la primera, la pregunta entera
        return f"Pregunta {self.numero_pregunta}. {self.pregunta}"

    def _lado(self):
        """Los párrafos y el bloque que van lado a lado, o None si la página va de arriba abajo.

        Van lado a lado cuando, además del texto, la página tiene un solo gráfico o una sola tabla de 640 px o menos.
        """
        # Bloques de texto
        textos = [b for b in self.bloques if b["clase"] == "parrafo"]
        # Los que no son texto
        otros = [b for b in self.bloques if b["clase"] != "parrafo"]
        # Texto y un solo gráfico o tabla, que quepa a la derecha
        if (self.columnas and textos and len(otros) == 1 and otros[0]["clase"] in ("grafico", "tabla")
                and otros[0]["ancho"] <= ALTO["ancho_otro"]):
            # Van lado a lado
            return textos, otros[0]
        # De arriba abajo
        return None

    def alto(self):
        """Alto estimado de la página en px, con las medidas de estilo.css (S3). Es la cuenta del banco."""
        # Bloques en su orden: (margen de arriba, contenido, margen de abajo)
        bloques = [(0, ALTO["h1"], ALTO["h1_abajo"])]
        # La pregunta, en un párrafo propio debajo del título
        if self.numero_pregunta:
            # Sus líneas, como se escriben
            bloques.append((0, _lineas(_caracteres(self._linea_pregunta()),
                                       ALTO["caracteres_pregunta"]) * ALTO["linea_texto"], ALTO["parrafo"]))
        # Fila de cifras clave, si hay alguna, según lo largas que sean sus etiquetas
        if self.cifras:
            # Contenido y márgenes
            bloques.append((ALTO["cifras_arriba"], alto_cifras([(_caracteres(et), _caracteres(ctx))
                                                                for _, et, ctx in self.cifras]), ALTO["cifras_abajo"]))
        # Lado a lado: un bloque que mide lo que la columna más alta
        lado = self._lado()
        # Si van lado a lado, el texto y lo otro se cuentan juntos
        if lado:
            # Párrafos a la izquierda y lo otro a la derecha
            textos, otro = lado
            # Alto de la columna de la derecha
            derecha = (alto_tabla(otro["filas"], otro["fuente"], otro["ancho"], otro["texto"])
                       if otro["clase"] == "tabla"
                       else alto_grafico(otro["svg"], otro["titulo"], otro["subtitulo"], otro["fuente"], otro["ancho"]))
            # Columna del texto, con lo que deja la otra
            izquierda = alto_texto([c for b in textos for c in b["parrafos"]],
                                   (ALTO["ancho_pagina"] - ALTO["hueco_lado"] - otro["ancho"]) / ALTO["letra_texto"])
            # El bloque entero
            bloques.append((ALTO["bloque"], max(izquierda, derecha), ALTO["bloque"]))
        # De arriba abajo, cada bloque con sus márgenes
        for bloque in ([] if lado else self.bloques):
            # Cada párrafo, por sus líneas
            if bloque["clase"] == "parrafo":
                # Un bloque por párrafo
                bloques += [(0, _lineas(c, ALTO["caracteres_linea"]) * ALTO["linea_texto"], ALTO["parrafo"])
                            for c in bloque["parrafos"]]
            # Un gráfico a lo ancho: el título y el subtítulo se parten al ancho de la página
            elif bloque["clase"] == "grafico":
                # Contenido y márgenes
                bloques.append((ALTO["bloque"], alto_grafico(bloque["svg"], bloque["titulo"], bloque["subtitulo"],
                                                             bloque["fuente"], ALTO["ancho_pagina"]), ALTO["bloque"]))
            # Una fila de dos gráficos
            elif bloque["clase"] == "fila":
                # Contenido y márgenes
                bloques.append((ALTO["bloque"], alto_fila(bloque["graficos"], bloque["subtitulo"], bloque["fuente"]),
                                ALTO["bloque"]))
            # Una tabla con su fuente, a lo ancho de la página
            else:
                # Contenido y márgenes
                bloques.append((ALTO["bloque"], alto_tabla(bloque["filas"], bloque["fuente"], ALTO["ancho_pagina"],
                                                           bloque["texto"]), ALTO["bloque"]))
        # Alto de la página
        return apilar(bloques)

    def cifra_clave(self, valor, etiqueta, contexto="", decimales=None, unidad=""):
        """Número grande, etiqueta debajo y una línea de contexto (C1). Como mucho cuatro por página (C2).

        Un texto ya viene redondeado y con su unidad. Un número necesita `decimales=` (F2): sin él, 1,08 saldría «1».
        """
        # La quinta cifra incumple C2
        if len(self.cifras) >= MAX_CIFRAS:
            # Se para diciendo la regla
            raise ValueError(f"C2: como mucho {MAX_CIFRAS} cifras clave por página; «{self.titulo}» ya tiene "
                             f"{len(self.cifras)}")
        # Un número sin decimales dichos se redondearía sin avisar
        if _es_numero(valor) and decimales is None:
            # Se para diciendo la regla
            raise ValueError(f"F2: la cifra clave «{etiqueta}» es un número; di con cuántos decimales (decimales=)")
        # Un número se escribe a la española; un texto ya viene redondeado y con su unidad
        texto_valor = numero(valor, decimales, unidad) if _es_numero(valor) else str(valor)
        # Etiqueta y contexto van debajo del número como líneas sueltas: empiezan por mayúscula
        etiqueta, contexto = (t[:1].upper() + t[1:] for t in (str(etiqueta), str(contexto)))
        # Se guarda la cifra
        self.cifras.append((texto_valor, etiqueta, contexto))

    def texto(self, *parrafos):
        """Uno o varios párrafos cortos (T2)."""
        # Cada párrafo, escapado, con sus caracteres para la cuenta de alto
        self.bloques.append({"clase": "parrafo", "html": "".join(f"<p>{_e(p)}</p>" for p in parrafos),
                             "parrafos": [_caracteres(p) for p in parrafos]})

    def _bloque_grafico(self, svg, titulo, subtitulo, fuente):
        """Un gráfico con su título, su subtítulo (si lo lleva), el dibujo y su fuente debajo (si la lleva) (G7)."""
        # Tiene que ser un SVG en texto, no una imagen (G7)
        if not isinstance(svg, str) or not svg.lstrip().startswith("<svg") or "data:image" in svg:
            # Se para diciendo la regla
            raise ValueError("G7: el gráfico tiene que ser un <svg> en texto, como lo devuelve graficos.py")
        # Subtítulo, si lo hay
        sub = f'<div class="g-subtitulo">{_e(subtitulo)}</div>' if subtitulo else ""
        # Fuente debajo del dibujo, si la hay
        pie = f'<div class="g-fuente">{_e(fuente)}</div>' if fuente else ""
        # Bloque del gráfico
        return f'<div class="grafico"><div class="g-titulo">{_e(titulo)}</div>{sub}{_con_aria(svg, titulo)}{pie}</div>'

    def grafico(self, svg, titulo, subtitulo):
        """Un gráfico en SVG con su título (G1) y su subtítulo con medida, unidad, periodo y fuente (G2).

        Lo que va desde «Fuente:» sale del subtítulo y se escribe en su propia línea, debajo del dibujo.
        """
        # Medida y fuente, por separado
        medida, fuente = _partir_fuente(subtitulo, titulo)
        # Bloque del gráfico, con lo que pide la cuenta de alto
        self.bloques.append({"clase": "grafico", "html": self._bloque_grafico(svg, titulo, medida, fuente),
                             "svg": _alto(svg), "titulo": _caracteres(titulo), "subtitulo": _caracteres(medida),
                             "fuente": _caracteres(fuente), "ancho": _ancho(svg)})

    def fila(self, svg1, titulo1, subtitulo1, svg2, titulo2, subtitulo2):
        """Dos gráficos lado a lado, de 500 px como mucho cada uno (`ancho=graficos.ANCHO_FILA`), para que quepan (S3).

        Si los dos llevan el mismo subtítulo, la medida va una vez encima de la fila y la fuente, una vez debajo.
        """
        # Cada gráfico tiene que caber en su mitad
        for svg, titulo in ((svg1, titulo1), (svg2, titulo2)):
            # Más ancho que la mitad se saldría de la página
            if _ancho(svg) > ANCHO_FILA:
                # Se para diciendo cómo hacerlo
                raise ValueError(f"S3: «{titulo}» mide {_ancho(svg):.0f} px; en una fila, como mucho {ANCHO_FILA} "
                                 f"(ancho=graficos.ANCHO_FILA)")
        # Medida y fuente de cada uno
        (m1, f1), (m2, f2) = _partir_fuente(subtitulo1, titulo1), _partir_fuente(subtitulo2, titulo2)
        # Con el mismo subtítulo, una sola vez a todo el ancho
        comun = (m1, f1) == (m2, f2)
        # Lo que va en cada gráfico y lo que va común
        medida, fuente = (m1, f1) if comun else ("", "")
        # Cada gráfico, con lo suyo
        propios = [(svg1, titulo1, "" if comun else m1, "" if comun else f1),
                   (svg2, titulo2, "" if comun else m2, "" if comun else f2)]
        # Fila con su subtítulo y su fuente comunes, si los hay
        fila = ('<div class="fila-bloque">' + (f'<div class="g-subtitulo">{_e(medida)}</div>' if medida else "")
                + '<div class="fila">' + "".join(self._bloque_grafico(*g) for g in propios) + "</div>"
                + (f'<div class="g-fuente">{_e(fuente)}</div>' if fuente else "") + "</div>")
        # Bloque de la fila, con lo que pide la cuenta de alto
        self.bloques.append({"clase": "fila", "html": fila,
                             "graficos": [(_alto(sv), _caracteres(t), _caracteres(m), _caracteres(f))
                                          for sv, t, m, f in propios],
                             "subtitulo": _caracteres(medida), "fuente": _caracteres(fuente)})

    def tabla(self, columnas, filas, fuente, totales=None, decimales=None, texto=None):
        """Tabla con los números a la derecha (TB2), fila de total si se pide (TB4) y la fuente debajo (F1).

        `totales` dice qué columnas se suman: ["", "suma", ""]. Solo se suman las que tienen sentido; un ratio o una
        mediana no se suman, y su celda del total queda vacía. `decimales` es obligatorio si alguna columna los lleva.
        Una tabla sin cifras es de texto (15 px, a todo el ancho); `texto=False` la deja a 13 px si no cabe.
        """
        # Sin fuente, la cifra no se puede seguir hasta su origen (F1)
        if not str(fuente).strip():
            # Se para diciendo la regla
            raise ValueError("F1: toda tabla lleva su fuente debajo")
        # Columnas en las que todos los valores son números
        numericas = [all(_es_numero(f[c]) for f in filas if f[c] is not None) and any(f[c] is not None for f in filas)
                     for c in range(len(columnas))]
        # Sin decimales dichos, una columna con decimales se redondearía a entero sin avisar
        if decimales is None:
            # Columnas con algún valor que no es entero
            con_decimales = [columnas[c] for c in range(len(columnas)) if numericas[c] and
                             any(f[c] is not None and float(f[c]) != int(f[c]) for f in filas)]
            # Si hay alguna, se para
            if con_decimales:
                # Se para diciendo cuáles
                raise ValueError(f"TB2: las columnas {con_decimales} llevan decimales; di cuántos (decimales=)")
        # Decimales de cada columna: los mismos en toda la columna (TB2)
        decimales = list(decimales) if decimales is not None else [0] * len(columnas)
        # Qué columnas se suman
        totales = list(totales) if totales is not None else []
        # Si se piden totales, uno por columna
        if totales and len(totales) != len(columnas):
            # Se para diciendo cuántos faltan
            raise ValueError(f"TB4: hay {len(columnas)} columnas y {len(totales)} valores en totales")
        # Solo se suman columnas de números
        for c, que in enumerate(totales):
            # Una suma pedida sobre una columna que no es de números
            if que == "suma" and not numericas[c]:
                # Se para diciendo cuál
                raise ValueError(f"TB4: la columna «{columnas[c]}» no es de números y no se puede sumar")
        # Filas de la tabla, ya escritas
        cuerpo = []
        # Cada fila
        for fila in filas:
            # Celdas de la fila
            celdas = []
            # Cada celda
            for c, valor in enumerate(fila):
                # Un número se escribe a la española con los decimales de su columna
                texto_celda = numero(valor, decimales[c]) if _es_numero(valor) else ("" if valor is None else valor)
                # Las columnas numéricas van a la derecha
                clase = ' class="num"' if numericas[c] else ""
                # Celda escrita
                celdas.append(f"<td{clase}>{_e(texto_celda)}</td>")
            # Fila escrita
            cuerpo.append("<tr>" + "".join(celdas) + "</tr>")
        # Fila de total si se pide alguna suma (TB4)
        if "suma" in totales:
            # Celdas del total
            celdas = []
            # Cada columna
            for c in range(len(columnas)):
                # Las que se suman llevan la suma de sus filas
                if totales[c] == "suma":
                    # Suma de la columna
                    suma = sum(f[c] for f in filas if f[c] is not None)
                    # Celda del total
                    celdas.append(f'<td class="num">{_e(numero(suma, decimales[c]))}</td>')
                # La primera dice «Total»
                elif c == 0:
                    # Etiqueta del total
                    celdas.append("<td>Total</td>")
                # Las demás quedan vacías
                else:
                    # Celda vacía, alineada como su columna
                    celdas.append(f'<td{" class=\"num\"" if numericas[c] else ""}></td>')
            # Fila del total
            cuerpo.append('<tr class="total">' + "".join(celdas) + "</tr>")
        # Una tabla sin ninguna columna de números es de texto: va a 15 px y a todo el ancho
        texto = not any(numericas) if texto is None else bool(texto)
        # Encabezados, alineados como su columna
        cabecera = "".join(f'<th{" class=\"num\"" if numericas[c] else ""}>{_e(nombre)}</th>'
                           for c, nombre in enumerate(columnas))
        # Caracteres de cada celda como se ve, fila a fila, con el encabezado primero
        caracteres = [[_caracteres(nombre) for nombre in columnas]] + [
            [_caracteres(html.unescape(celda)) for celda in re.findall(r"<td[^>]*>([^<]*)</td>", fila_html)]
            for fila_html in cuerpo]
        # Tabla con su fuente debajo, con lo que pide la cuenta de alto: las celdas, la fuente y el ancho sin partir,
        # hacia arriba para que en su columna no se parta ninguna
        self.bloques.append({"clase": "tabla",
                             "html": f"<table{' class=\"texto\"' if texto else ''}><thead><tr>{cabecera}</tr></thead>"
                                     f"<tbody>{''.join(cuerpo)}</tbody></table>"
                                     f'<div class="fuente">Fuente: {_e(fuente)}</div>',
                             "filas": caracteres, "fuente": _caracteres(f"Fuente: {fuente}"), "texto": texto,
                             "ancho": ALTO["ancho_pagina"] if texto else math.ceil(ancho_tabla(caracteres))})

    def html(self, visible):
        """La página como <section>, visible o escondida."""
        # Cifras clave en una fila
        cifras = "".join(f'<div class="cifra-clave"><p class="numero">{_e(v)}</p><p class="etiqueta">{_e(et)}</p>'
                         f'<p class="contexto">{_e(ctx)}</p></div>' for v, et, ctx in self.cifras)
        # Fila de cifras solo si hay alguna
        fila_cifras = f'<div class="cifras">{cifras}</div>' if cifras else ""
        # La pregunta que contesta, debajo del título
        pregunta = (f'<p class="pregunta">{_e(self._linea_pregunta())}</p>' if self.numero_pregunta else "")
        # Atributo para esconder las páginas que no son la primera
        oculta = "" if visible else " hidden"
        # Lado a lado: el texto a la izquierda y lo otro a la derecha, con su ancho en una variable de CSS
        lado = self._lado()
        # Si van lado a lado, un solo bloque con las dos columnas
        if lado:
            # Párrafos a la izquierda y el gráfico o la tabla a la derecha
            textos, otro = lado
            # Bloque de dos columnas
            cuerpo = (f'<div class="lado" style="--ancho-otro: {otro["ancho"]:.0f}px">'
                      f'<div class="lado-texto">{"".join(b["html"] for b in textos)}</div>'
                      f'<div class="lado-otro">{otro["html"]}</div></div>')
        # Si no, uno debajo de otro
        else:
            # Bloques en su orden
            cuerpo = "".join(b["html"] for b in self.bloques)
        # Página entera
        return (f'<section id="{self.id}" class="pagina"{oculta}><h1>{_e(self.titulo)}</h1>{pregunta}{fila_cifras}'
                f'{cuerpo}</section>')


class Informe:
    """Un informe HTML de un solo fichero, con panel a la izquierda y páginas en el orden de S2."""

    def __init__(self, titulo, fecha_datos):
        # Título del informe, en el panel
        self.titulo = titulo
        # Fecha o periodo de los datos, en el panel, con mayúscula como el resto de rótulos
        self.fecha_datos = str(fecha_datos)[:1].upper() + str(fecha_datos)[1:]
        # Páginas en orden
        self.paginas = []

    def pagina(self, titulo, tipo, pregunta="", columnas=True, panel=None):
        """Añade una página: tipo 'resumen', 'pregunta', 'limites', 'decision' o 'anexo', en ese orden (S2).

        Una página de pregunta dice cuál contesta (`pregunta=`), y el panel la numera. Si una pregunta no cabe en una
        página (S3), se parte: la página siguiente lleva la misma `pregunta=` y el mismo número. Los límites y las
        decisiones también se pueden partir en varias páginas seguidas. Con `columnas=False`, el texto y un gráfico o una tabla van uno debajo
        de otro aunque quepan lado a lado. `panel=` es un título corto para el panel, que quepa en una línea.
        """
        # Solo las cuatro clases de S2
        if tipo not in ORDEN:
            # Se para diciendo cuáles valen
            raise ValueError(f"S2: tipo de página «{tipo}»; los tipos son {', '.join(ORDEN)}")
        # Una página de pregunta sin la pregunta no dice qué contesta
        if tipo == "pregunta" and not str(pregunta).strip():
            # Se para diciendo la regla
            raise ValueError(f"S2: la página «{titulo}» es de pregunta; di cuál contesta (pregunta=)")
        # Posición de cada clase en el orden de S2
        posicion = list(ORDEN).index
        # Una página no puede ir antes que la anterior en el orden de S2
        if self.paginas and posicion(tipo) < posicion(self.paginas[-1].tipo):
            # Se para diciendo el orden
            raise ValueError(f"S2: la página «{titulo}» ({tipo}) va antes que «{self.paginas[-1].titulo}» "
                             f"({self.paginas[-1].tipo}); el orden es resumen, preguntas, límites, decisión y anexo")
        # El resumen, una sola vez
        if ORDEN[tipo] == 1 and any(p.tipo == tipo for p in self.paginas):
            # Se para diciendo cuál se repite
            raise ValueError(f"S2: solo puede haber una página de tipo «{tipo}»")
        # Página nueva
        nueva = Pagina(titulo, tipo, len(self.paginas) + 1, pregunta, columnas, panel)
        # Las preguntas se numeran en orden
        if tipo == "pregunta":
            # Preguntas ya puestas, cada una una vez y en su orden
            anteriores = [p.pregunta for p in self.paginas if p.tipo == "pregunta"]
            # La misma pregunta que la página anterior: es la misma pregunta partida en dos páginas (S3)
            if anteriores and pregunta == anteriores[-1]:
                # Lleva el mismo número y no repite la pregunta entera (D7)
                nueva.numero_pregunta = self.paginas[-1].numero_pregunta
                nueva.sigue = True
            # Una pregunta que ya salió antes de otra rompe el orden de S2
            elif pregunta in anteriores:
                # Se para diciendo la regla
                raise ValueError(f"S2: la página «{titulo}» vuelve a una pregunta que ya tuvo su página; una pregunta "
                                 f"partida va en páginas seguidas")
            # Una pregunta nueva
            else:
                # Una más que las preguntas distintas que ya hay
                nueva.numero_pregunta = len(dict.fromkeys(anteriores)) + 1
        # Se añade al informe
        self.paginas.append(nueva)
        # Se devuelve para llenarla
        return nueva

    def html(self):
        """El informe entero como texto HTML. Para si alguna página no cabe en la pantalla (S3)."""
        # Sin páginas no hay informe (S1)
        if not self.paginas:
            # Se para
            raise ValueError("S1: el informe necesita al menos una página")
        # Panel: las páginas de cada pregunta, juntas bajo un rótulo con su número (la pregunta entera, al pasar el
        # ratón); los límites y la decisión, bajo el suyo
        partes = []
        # Rótulo del grupo anterior
        grupo = None
        # Cada página, la primera marcada
        for i, p in enumerate(self.paginas):
            # Rótulo del grupo de esta página: la pregunta, los límites, la decisión o ninguno
            rotulo = (f"Pregunta {p.numero_pregunta}" if p.numero_pregunta else
                      {"limites": "Límites", "decision": "Decisión", "anexo": "Anexo"}.get(p.tipo))
            # Un grupo nuevo abre su rótulo, que no se pulsa
            if rotulo and rotulo != grupo:
                # Con la pregunta entera al pasar el ratón, si es de pregunta
                ayuda = f' title="{_e(p.pregunta)}"' if p.numero_pregunta else ""
                # Rótulo
                partes.append(f'<p class="grupo"{ayuda}>{_e(rotulo)}</p>')
            # Se apunta el grupo de esta página
            grupo = rotulo
            # Clase del botón: el de una página con grupo va metido bajo su rótulo
            clase = ' class="sub"' if rotulo else ""
            # La primera página va marcada
            marca = ' aria-current="page"' if i == 0 else ""
            # Botón de la página, con su título corto
            partes.append(f'<button data-pagina="{p.id}"{clase}{marca}>{_e(p.panel)}</button>')
        # Panel entero
        botones = "".join(partes)
        # Páginas, solo la primera visible
        paginas = "".join(p.html(i == 0) for i, p in enumerate(self.paginas))
        # Hoja de estilos, dentro del HTML
        estilo = ESTILO.read_text(encoding="utf-8")
        # Documento entero
        documento = (f'<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
                     f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                     f"<title>{_e(self.titulo)}</title>\n<style>\n{estilo}</style>\n</head>\n<body>\n"
                     f'<nav><p class="informe-titulo">{_e(self.titulo)}</p>'
                     f'<p class="informe-fecha">{_e(self.fecha_datos)}</p>{botones}</nav>\n'
                     f"<main>\n{paginas}\n</main>\n"
                     f'<div class="etiqueta-dato" role="tooltip" hidden></div>\n'
                     f"<script>{SCRIPT}</script>\n</body>\n</html>\n")
        # Más páginas de las que se leen: sin contar el anexo, como mucho MAX_PAGINAS (D7)
        sin_anexo = sum(1 for p in self.paginas if p.tipo != "anexo")
        # Si pasa, se para diciendo cuántas sobran
        if sin_anexo > MAX_PAGINAS:
            # Se para diciendo la regla
            raise ValueError(f"D7: el informe tiene {sin_anexo} páginas sin el anexo y caben {MAX_PAGINAS}. Quita lo "
                             f"que sobra, junta las páginas que dicen casi lo mismo o lleva el método al anexo")
        # Páginas más altas de lo que cabe, con la misma cuenta que el banco
        altas = [(p.titulo, p.alto()) for p in self.paginas if p.alto() > ALTO_UTIL]
        # Si hay alguna, se para diciendo cuál y cuánto mide
        if altas:
            # Se para diciendo la regla
            raise ValueError("S3: no caben en la pantalla (%d px): %s. Parte la página en dos o pon los gráficos en "
                             "una fila" % (ALTO_UTIL, "; ".join(f"«{t}», unos {a} px" for t, a in altas)))
        # Documento listo
        return documento

    def guardar(self, ruta):
        """Escribe el informe en `ruta`, en UTF-8."""
        # Carpeta de destino, si no existe
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        # Fichero HTML
        Path(ruta).write_text(self.html(), encoding="utf-8")
