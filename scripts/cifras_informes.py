"""Piezas comunes de los dos informes y de la interpretación del caso: leer cifras con su rastro, guardias y acciones.

Este módulo no hace nada al importarse. Lo usan scripts/informe_ejecutivo.py, scripts/informe_final.py y
scripts/interpretacion_resultados.py. No calcula cifras de negocio: cada cifra se lee de informes/indicadores.json por su
clave y queda apuntada, para que después se pueda seguir cada número del texto hasta su origen.
"""
import json
import re
import sys
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
# Las piezas comunes se usan desde assets/.
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402

INDICADORES = CASO / "informes" / "indicadores.json"


# =====================================================================================================================
# 1. Cifras con rastro
# =====================================================================================================================

class Cifras:
    """Lee cifras de un JSON por su clave y apunta cada una con el texto con que se escribe."""

    def __init__(self, ruta=INDICADORES):
        """Abre el JSON y comprueba que trae la fecha de los datos."""
        self.ruta = Path(ruta)
        self.j = json.loads(self.ruta.read_text(encoding="utf-8"))
        if not self.j.get("fecha_datos"):
            raise SystemExit(f"{self.ruta.name} no trae fecha_datos: el informe no sabe de qué fecha son sus cifras")
        self.apuntadas = {}

    def dato(self, clave):
        """Devuelve el valor de una clave como `preguntas[1].fichas_del_grupo[barrio=Ventas].pisos`, sin apuntarlo."""
        valor = self.j
        # Cada trozo es un nombre, un índice entre corchetes o un elemento de lista elegido por un campo.
        for nombre, indice, campo, igual in re.findall(r"([^.\[\]]+)|\[(\d+)\]|\[([^=\]]+)=([^\]]+)\]", clave):
            if nombre:
                valor = valor[nombre]
            elif indice:
                valor = valor[int(indice)]
            else:
                valor = next(x for x in valor if str(x[campo]) == igual)
        return valor

    def _apuntar(self, clave, texto):
        """Guarda el texto de una cifra con la clave de la que sale."""
        self.apuntadas.setdefault(texto, set()).add(clave)
        return texto

    def num(self, clave, decimales=0):
        """Escribe un número a la española, con punto de miles."""
        return self._apuntar(clave, numero(self.dato(clave), decimales))

    def pct(self, clave, decimales=1):
        """Escribe un porcentaje con un decimal, como pide F2."""
        return self._apuntar(clave, numero(self.dato(clave), decimales)) + " %"

    def eur(self, clave):
        """Escribe euros sin decimales, como pide F2 en importes grandes."""
        return self._apuntar(clave, numero(self.dato(clave), 0)) + " €"

    def cuantos(self, clave):
        """Escribe cuántos elementos tiene una lista del JSON."""
        return self._apuntar(clave, numero(len(self.dato(clave)), 0))

    def rastro(self):
        """Da cada texto escrito con las claves de las que sale, para dejarlo en el JSON del informe."""
        return [{"cifra": t, "claves": sorted(c)} for t, c in sorted(self.apuntadas.items())]


# =====================================================================================================================
# 2. Guardias
# =====================================================================================================================

# Constantes de las reglas y datos de la fuente que no están en indicadores.json como cifra: cada una con su origen.
CONSTANTES = {"255": "reglas §2, máximo de la ocupación", "25": "reglas §3, el 25 % más rentable", "30": "reglas §3, mínimo por grupo",
              "20": "reglas §3, mínimo de las variantes", "12": "reglas §3, variantes", "6": "reglas §3, más de 6 de 12",
              "95": "planteamientos, intervalo", "2.000": "planteamientos, remuestreos", "63": "scripts, semilla",
              "10": "reglas §3, anfitriones", "60": "reglas §3, cotización", "40": "reglas §3, pocos anuncios",
              "150": "reglas §1, coordenadas", "1": "habitaciones", "2": "habitaciones", "3": "habitaciones y estancia",
              "5": "las cinco pruebas", "4": "pruebas aguantadas", "9": "barrios del grupo", "2025": "año del precio oficial",
              "2026": "año de las descargas", "35": "planteamientos, estudio", "45": "planteamientos, una habitación",
              "50": "reglas §2, superficie", "65": "reglas §2, superficie", "75": "planteamientos, dos habitaciones",
              "15": "páginas del informe", "90": "reglas §2, superficie", "110": "reglas §2, superficie",
              "140": "reglas §2, superficie", "1.000": "reglas §3, precio", "8": "reglas §3, huéspedes"}
# Lo que parece cifra y no lo es: fechas, la licencia y los nombres de las normas.
NO_CIFRAS = [r"\d{2}/\d{2}/\d{4}", r"CC BY 4\.0", r"BOCM \d+", r"APE \d+\.\d+"]

# Palabras que las salidas no pueden llevar: método interno y nombres de código.
PROHIBIDAS = [r"\bbase de comparaci[oó]n\b",
              r"\bsuceso\b", r"\bentidad(es)?\b", r"\bcosecha\b", r"\br[eé]gimen\b", r"\bvalidaci[oó]n\b", r"\bCP-\d+",
              r"\bn =", r"_pct\b", r"_eur\b", r"\.parquet\b"]
# Sinónimos de los términos fijados: cada concepto lleva un solo nombre (D4).
SINONIMOS = [r"\bgrupo fuerte\b", r"\bbarrios? seguros?\b", r"\bbarrios? s[oó]lidos?\b", r"\brentabilidad neta estimada\b", r"\bocupaci[oó]n real\b",
             r"\bbeneficio bruto\b", r"\bretorno\b", r"\bROI\b", r"\bpercentil 25\b"]
# Verbos causales: sin diseño que los sostenga, el caso solo describe asociaciones.
CAUSALES = [r"\bprovoca", r"\bcausa\b", r"\bhace que\b", r"\bgracias a\b", r"\bdebido a\b"]
# Estilo que no se admite en los textos.
ESTILO = [r"[—–]", r"\bcrucial\b", r"\brobust[oa]s?\b", r"\bintegral(es)?\b", r"\bexhaustiv[oa]s?\b", r"\bpotente\b", r"\bvital\b", r"\bfundamental(es)?\b", r"\bdefinitiv[oa]\b"]


def exigir(condicion, frase):
    """Para el script si las cifras dejan de decir lo que dice una frase del informe."""
    if not condicion:
        raise SystemExit(f"Las cifras ya no sostienen esta frase: {frase}")


def sin_jerga(texto):
    """Para el script si el texto visible lleva una palabra prohibida, un sinónimo, un verbo causal o un rasgo de estilo."""
    fallos = []
    for lista, que in ((PROHIBIDAS, "prohibida"), (SINONIMOS, "sinónimo"), (CAUSALES, "causal"), (ESTILO, "estilo")):
        for patron in lista:
            for m in re.finditer(patron, texto, flags=re.IGNORECASE):
                fallos.append(f"{que}: «{texto[max(0, m.start() - 30):m.end() + 30]}»")
    if fallos:
        raise SystemExit("El texto no pasa la guardia:\n" + "\n".join(fallos))


def cifras_sin_rastro(texto, rastro):
    """Da los números del texto que no están apuntados con su clave ni entre las constantes con origen."""
    for patron in NO_CIFRAS:
        texto = re.sub(patron, " ", texto)
    # El signo menos tipográfico queda fuera del número que se busca en el texto.
    escritas = {x.lstrip("−") for x in rastro} | set(CONSTANTES)
    numeros = re.findall(r"(?<![\w.,])\d[\d.]*(?:,\d+)?(?![\w])", texto)
    return sorted({n.rstrip(".") for n in numeros if n.rstrip(".") not in escritas})


def palabras(texto):
    """Cuenta las palabras de un texto, con las cifras como una palabra."""
    return len(re.findall(r"\S+", texto))


# =====================================================================================================================
# 3. La lectura aprobada: lo que tiene que seguir cierto para escribirla
# =====================================================================================================================

FIRMES = ["Ventas", "Numancia", "San Diego"]
CON_AVISO = ["Casco Histórico de Vallecas", "Opañel"]
Q2 = "preguntas[1]"
Q3 = "preguntas[2]"
REC = "recomendacion"
ORDENA = f"{Q2}.que_ordena_la_lista"
UN_ANO = f"{Q2}.con_un_ano_o_mas"
PLANTA = "licencias_y_registro.planta_baja"
# La fuente escribe sin tilde este barrio: el lector lo lee con ella en todas las salidas.
NOMBRE_VISIBLE = {"Puerta del Angel": "Puerta del Ángel"}


def barrio(b):
    """Da el nombre de un barrio como lo lee quien recibe el informe."""
    return NOMBRE_VISIBLE.get(b, b)


def ficha(nombre, campo, pregunta=2):
    """Clave de un campo en la ficha de un barrio del grupo."""
    return f"preguntas[{pregunta - 1}].fichas_del_grupo[barrio={nombre}].{campo}"


def puesto(nombre):
    """Clave de un barrio en el orden con los pisos de un año o más."""
    return f"{UN_ANO}.barrios[barrio={nombre}].puesto"


def comprobar_lectura(c):
    """Comprueba con las cifras cada frase de la lectura aprobada antes de escribir nada."""
    p1, p2, p3 = c.dato("preguntas")
    exigir(sorted(p2["firmes"]) == sorted(FIRMES), "los recomendados son Ventas, Numancia y San Diego")
    exigir(sorted(p2["con_aviso"]) == sorted(CON_AVISO), "que siguen en la lista 4 veces van Casco Histórico de Vallecas y Opañel")
    exigir(len(p2["segunda_linea"]) == 4, "cuatro barrios en resto del grupo")
    fichas = {f["barrio"]: f for f in p2["fichas_del_grupo"]}
    # Los recomendados aguantan las cinco pruebas, dependen del máximo y su cuartil bajo supera el de la base.
    for b in FIRMES:
        exigir(len(fichas[b]["pruebas_que_aguanta"]) == 5, f"{b} aguanta las cinco pruebas")
        exigir(fichas[b]["avisos_del_barrio"]["depende_del_tope"], f"{b} depende del máximo de días")
        exigir(fichas[b]["cuartil_bajo_pct"] > p2["cuartil_bajo_de_toda_la_base"], f"el cuartil bajo de {b} supera el de la base")
        exigir(not fichas[b]["avisos_del_barrio"]["cuartil_bajo"], f"{b} no lleva el aviso del cuartil bajo")
    # Contra la mediana el aviso no distinguía: le pasaba a casi todos los barrios.
    a = p2["aviso_del_cuartil"]
    exigir(a["no_superan_la_mediana"] >= a["barrios_comparados"] - 1, "contra la mediana el aviso le pasa a casi todos los barrios")
    # Opañel llega a la mitad de sus pisos en el máximo y no depende de él; Puerta del Ángel no aguanta ninguna prueba.
    exigir(fichas["Opañel"]["parte_en_el_tope_pct"] >= 50 and not fichas["Opañel"]["avisos_del_barrio"]["depende_del_tope"], "Opañel no depende del máximo aunque la mitad de sus pisos llega a él")
    exigir(not fichas["Puerta del Angel"]["pruebas_que_aguanta"], "Puerta del Ángel no aguanta ninguna prueba")
    # Los que siguen en la lista 4 veces caen justo en la prueba de los operadores grandes.
    for b in CON_AVISO:
        exigir(fichas[b]["pruebas_que_no_aguanta"] == ["sin_anfitriones_grandes"], f"{b} depende de operadores grandes")
    # Hasta 2 dormitorios rinden más que 3 en cada combinación, y el orden entre ellos cambia con los m².
    s = p1["sensibilidad_superficie"]
    exigir(len(s["combinaciones"]) == 8, "ocho combinaciones de superficie")
    for x in s["combinaciones"]:
        exigir(min(x["medianas"][g] for g in ("0", "1", "2")) > x["medianas"]["3"], "hasta 2 habitaciones rinden más que 3 en cada combinación")
        exigir("3" not in x["se_dan"], "los de 3 habitaciones no se dan en ninguna combinación")
    exigir(len(s["tipos_que_aparecen"]) > 1 and s["cambia"], "no hay ganador entre estudio, una y dos habitaciones")
    exigir(all(k in ("0", "1", "2") for t in s["tipos_que_aparecen"] for k in t), "los tipos que se dan son estudio, una y dos habitaciones")
    # Con el m² barato: seis de nueve entre los comparados.
    r = p2["referencia_baratos"]["comparados"]
    exigir(r["cuantos"] == 6 and r["de"] == 9 and r["barrios_entre_los_que_se_elige"] == 36, "6 de los 9 están entre los de m² más barato de los 36 comparados")
    # Numancia supera la mediana de la base con intervalo; San Diego y Ventas no se distinguen de ella.
    exigir(fichas["Numancia"]["frente_a_la_base"] == "por encima", "Numancia queda por encima de la mediana de la base")
    for b in ("San Diego", "Ventas"):
        exigir(fichas[b]["frente_a_la_base"] == "no se distingue", f"{b} no se distingue de la mediana de la base")
    # Dentro del grupo el orden no se cierra: de los 36 pares, se distinguen 4.
    exigir(sum(1 for x in p3["pares_dentro_del_grupo"] if x["se_distinguen"]) == 4, "cuatro pares del grupo se distinguen")
    # San Diego queda por debajo de los dos que siguen en la lista 4 veces, que rinden más.
    for b in CON_AVISO:
        exigir(any({x["a"], x["b"]} == {b, "San Diego"} and x["se_distinguen"] for x in p3["pares_dentro_del_grupo"]), f"San Diego queda por debajo de {b}")
        exigir(fichas[b]["rentabilidad_mediana_pct"] > fichas["San Diego"]["rentabilidad_mediana_pct"], f"{b} rinde más que San Diego")
    # Con los pisos de un año o más, Numancia y Ventas siguen en el mejor cuarto y San Diego sale de él.
    u = {x["barrio"]: x for x in p2["con_un_ano_o_mas"]["barrios"]}
    exigir(u["Numancia"]["en_el_mejor_cuarto"] and u["Ventas"]["en_el_mejor_cuarto"], "Numancia y Ventas siguen en el mejor cuarto con pisos de un año o más")
    exigir(not u["San Diego"]["en_el_mejor_cuarto"], "San Diego se sostiene menos con pisos de un año o más")
    # La lista frente a elegir por precio: ninguno de los dos pares se distingue, y la rentabilidad va más con la ocupación que con el m².
    o = p2["que_ordena_la_lista"]
    exigir(not any(x["se_distinguen"] for x in o["pares"]) and len(o["pares"]) == 2, "los recomendados y el grupo no se distinguen de los barrios de m² más barato")
    exigir(abs(o["rentabilidad_con_ocupacion"]) > abs(o["rentabilidad_con_m2"]), "la rentabilidad se asocia más con la ocupación que con el m²")


# =====================================================================================================================
# 4. Las acciones: las mismas palabras en los dos informes
# =====================================================================================================================

def acciones(c):
    """Devuelve las tres acciones: nombre, qué se hace, quién, para cuándo y de qué hallazgo sale con su cifra."""
    pendiente = "fecha por fijar"
    return [
        {"nombre": "Comprobar planta y norma en el Ayuntamiento",
         "que": "Empezar por bajos y primeras plantas con acceso independiente y preguntar en el Ayuntamiento qué norma rige en cada barrio de la lista antes de comprar.",
         "quien": "Dirección de Inversiones", "cuando": pendiente,
         "por_que": f"{c.num(PLANTA + '.licencias')} de las {c.num(PLANTA + '.de')} licencias municipales incluyen planta baja.",
         "pagina": "Lo que puede cambiar estas conclusiones"},
        {"nombre": "Pedir a valoraciones la superficie real",
         "que": "Sustituir el supuesto de m² por la superficie real de cada oportunidad que se estudie.",
         "quien": "Equipo de valoraciones, a petición de la Dirección de Inversiones", "cuando": pendiente,
         "por_que": f"El tipo de piso más rentable cambia en {c.num('preguntas[0].sensibilidad_superficie.combinaciones_que_cambian')} de las {c.cuantos('preguntas[0].sensibilidad_superficie.combinaciones')} superficies probadas.",
         "pagina": "Pregunta 1, sigue"},
        {"nombre": "Repetir el análisis con los datos siguientes",
         "que": "Volver a calcular la lista con las mismas reglas.",
         "quien": "Dirección de Inversiones y equipo de valoraciones", "cuando": "cuando Inside Airbnb publique sus datos siguientes",
         "por_que": f"Entre las tres fechas de precio, la rentabilidad mediana del barrio de Ventas varía {c.num(ficha('Ventas', 'rango_entre_fotos_puntos', 3), 1)} puntos; la de todos los pisos, {c.num(Q3 + '.referencia.rango_entre_fotos_puntos', 1)}.",
         "pagina": "Pregunta 3"},
    ]


# =====================================================================================================================
# 5. Atribución de las fuentes, igual en cada salida
# =====================================================================================================================

ATRIBUCION = ["Inside Airbnb, Madrid, descarga del 17/09/2026, con licencia CC BY 4.0.",
              "Origen de los datos: Ayuntamiento de Madrid, datos de 2025.",
              "Colegio de Registradores de España, fuente del precio declarado y de la superficie de 2025 que publica el Ayuntamiento."]


def fecha_es(iso):
    """Pasa una fecha de AAAA-MM-DD a DD/MM/AAAA."""
    a, m, d = str(iso)[:10].split("-")
    return f"{d}/{m}/{a}"
