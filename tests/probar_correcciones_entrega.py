"""Prueba las once correcciones hechas antes de entregar el caso, en sus tres capas.

  A. Las funciones nuevas de scripts/indicadores.py, con datos pequeños escritos aquí.
  B. informes/indicadores.json: las cifras esperadas salen del cálculo.
  C. Las salidas generadas: cada corrección está dicha en cada una y lo que había que quitar ya no está.

Las cifras esperadas están escritas aquí a propósito: se midieron antes de escribirlas. Sale con 0 si pasa y
con 1 si falla.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_correcciones_entrega.py
"""
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
INFORMES = CASO / "informes"
FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[:300]}"))
    if not bien:
        FALLOS.append(nombre)


def intento(nombre, funcion):
    """Lanza un bloque de casos; si le falta algo, ese es su rojo y los demás bloques siguen."""
    try:
        funcion()
    except (AttributeError, KeyError, TypeError, StopIteration, FileNotFoundError) as e:
        caso(nombre, False, f"{type(e).__name__}: {e}")


def visible_html(ruta):
    """Texto visible de un HTML generado, sin estilos, guiones ni dibujos."""
    h = ruta.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>|<script.*?</script>|<svg.*?</svg>", " ", h, flags=re.S)))


def salidas():
    """Lee el texto de cada salida. El cuadro lleva además sus definiciones, que se abren a un clic, y el título que escribe el navegador."""
    cuadro = visible_html(INFORMES / "cuadro_mando.html")
    m = re.search(r'<script type="application/json" id="datos">(.*?)</script>', (INFORMES / "cuadro_mando.html").read_text(encoding="utf-8"), re.S)
    datos = json.loads(m.group(1).replace("<\\/", "</"))
    interpretacion = (INFORMES / "interpretacion_resultados.md").read_text(encoding="utf-8").split("## Inventario de evidencias")[0]
    return {"ejecutivo": visible_html(INFORMES / "informe_ejecutivo.html"), "final": visible_html(INFORMES / "informe_final.html"), "interpretación": re.sub(r"\s+", " ", interpretacion),
            "cuadro": cuadro + " " + " ".join(datos["definiciones"].values()) + " " + datos["textos"]["titulo_dormitorios"]}


# ---------------------------------------------------------------------------
# A. Funciones con datos pequeños
# ---------------------------------------------------------------------------

def funciones():
    """Prueba las funciones nuevas con resultados conocidos de antemano."""
    import indicadores as ind
    plantas = pd.Series(["BAJA", "BAJA Y SOTANO", "1 BAJA, 2 PRIMERA", "PRIMERA", "SOTANO", None])
    caso("planta: cuenta cualquier licencia que nombra la baja", ind.incluye_planta_baja(plantas).tolist() == [True, True, True, False, False, False])

    # Dos barrios de 3 pisos con un año o más; el barrio C tiene 2 y no llega al mínimo de 3 de esta prueba.
    t = pd.DataFrame({"barrio": ["A", "A", "A", "B", "B", "B", "C", "C", "A"], "r": [10.0, 11.0, 12.0, 20.0, 21.0, 22.0, 90.0, 91.0, 99.0],
                      "first_review": ["2020-01-01", "2025-09-17", "2024-01-01", "2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01", "2025-09-18"]})
    u = ind.puestos_con_un_ano(t, "r", "2026-09-17", 3)
    caso("un año: el corte es la fecha de la foto menos un año", u["corte"] == "2025-09-17", u.get("corte"))
    caso("un año: entra el piso del mismo día y sale el del día siguiente", u["pisos"] == 8, u.get("pisos"))
    caso("un año: solo cuentan los barrios con el mínimo", u["barrios_comparados"] == 2, u.get("barrios_comparados"))
    por = {x["barrio"]: x for x in u["barrios"]}
    caso("un año: el piso nuevo no cuenta en la mediana", por["A"]["mediana_pct"] == 11.0, por["A"])
    caso("un año: el puesto va de mayor a menor", por["B"]["puesto"] == 1 and por["A"]["puesto"] == 2, por)

    r = ind.cifras_de_la_recomendacion(pd.DataFrame({"rent_valoraciones_pct": [6.0, 9.0], "compra_valoraciones_eur": [100.0, 200.0], "ingreso_anual_eur": [10.0, 30.0]}))
    caso("recomendación: medianas y recuento", (r["pisos"], r["rentabilidad_pct"], r["compra_eur"], r["ingreso_anual_eur"]) == (2, 7.5, 150.0, 20.0), r)

    o = ind.parte_de_operadores_grandes(pd.DataFrame({"barrio": ["A", "A", "A", "A", "B"], "anuncios_anfitrion": [10, 12, 1, 9, 50]}), ["A"], 10)
    caso("operadores grandes: desde 10 anuncios, sobre los pisos de esos barrios", o == 50.0, o)
    caso("el aviso del cuartil compara con el cuartil de la base", ind.avisos_del_barrio(41, 5.0, 4.0, True, 40)["cuartil_bajo"] is False and ind.avisos_del_barrio(41, 4.0, 4.0, True, 40)["cuartil_bajo"] is True)
    f = {"avisos_del_barrio": {"depende_del_tope": False, "pocos_anuncios": False, "cuartil_bajo": True}, "pisos": 50, "cuartil_bajo_pct": 3.0}
    caso("el texto del aviso nombra el cuartil bajo de la base", "corte de todos los pisos" in ind.texto_de_avisos(f, 4.0)[0], ind.texto_de_avisos(f, 4.0))


# ---------------------------------------------------------------------------
# B. El JSON
# ---------------------------------------------------------------------------

def cifras():
    """Comprueba que las cifras esperadas salen de indicadores.json."""
    j = json.loads((INFORMES / "indicadores.json").read_text(encoding="utf-8"))
    p1, p2, p3 = j["preguntas"]
    pl = j["licencias_y_registro"]["planta_baja"]
    caso("1. licencias con planta baja", (pl["licencias"], pl["de"], pl["recomendados"]["licencias"], pl["recomendados"]["de"]) == (930, 1031, 65, 72), pl)
    caso("2. cuartil bajo de la base", round(p2["cuartil_bajo_de_toda_la_base"], 2) == 3.04, p2.get("cuartil_bajo_de_toda_la_base"))
    caso("2. contra la mediana avisa a 35 de 36", (p2["aviso_del_cuartil"]["no_superan_la_mediana"], p2["aviso_del_cuartil"]["barrios_comparados"]) == (35, 36), p2.get("aviso_del_cuartil"))
    fichas = {f["barrio"]: f for f in p2["fichas_del_grupo"]}
    caso("2. ningún barrio recomendado lleva el aviso del cuartil", not any(fichas[b]["avisos_del_barrio"]["cuartil_bajo"] for b in p2["recomendados"]))
    u = p2["con_un_ano_o_mas"]
    puesto = {x["barrio"]: x["puesto"] for x in u["barrios"]}
    caso("3. puestos con un año o más", (puesto["Numancia"], puesto["Ventas"], puesto["San Diego"], u["barrios_comparados"]) == (2, 3, 8, 26), (puesto, u["barrios_comparados"]))
    caso("3. cada barrio con su rentabilidad", all(x["mediana_pct"] > 0 and x["pisos"] >= 30 for x in u["barrios"]))
    so = {f["barrio"]: round(f["pisos_fuera_sin_ocupacion_pct"], 1) for f in p3["fichas_del_grupo"]}
    caso("4. sin ocupación, misma población que la media", (so["Numancia"], so["San Diego"], so["Ventas"], round(p3["pisos_fuera_sin_ocupacion"]["pct"], 1)) == (32.4, 20.9, 18.9, 24.7), so)
    r = j["recomendacion"]
    caso("5. cifra de la recomendación", (r["pisos"], round(r["rentabilidad_pct"], 1)) == (256, 12.1), r)
    caso("6. San Diego por debajo de los dos que siguen en la lista 4 veces", all(any({x["a"], x["b"]} == {b, "San Diego"} and x["se_distinguen"] for x in p3["pares_dentro_del_grupo"]) for b in p2["cuatro_de_cinco"]))
    caso("6. operadores grandes en los dos que siguen en la lista 4 veces", round(p2["operadores_grandes"]["cuatro_de_cinco_pct"]) == 65, p2.get("operadores_grandes"))
    caso("8. compra e ingreso por piso", (round(r["compra_eur"]), round(r["ingreso_anual_eur"])) == (161973, 21675), r)
    q = p2["que_ordena_la_lista"]
    caso("9. correlaciones entre los 36 barrios", (q["barrios"], round(q["rentabilidad_con_ocupacion"], 2), round(q["rentabilidad_con_m2"], 2)) == (36, 0.78, -0.60), q)
    caso("9. baratos, recomendados y grupo", tuple(round(q[k]["mediana_pct"] / 0.1) for k in ("m2_baratos", "recomendados", "grupo")) == (109, 114, 118), q)
    caso("los pares de la lista traen su intervalo", all("se_distinguen" in x for x in q["pares"]) and len(q["pares"]) == 2, q.get("pares"))


# ---------------------------------------------------------------------------
# C. Las salidas
# ---------------------------------------------------------------------------

def textos():
    """Mira cada corrección en cada salida."""
    s = salidas()
    for nombre, t in s.items():
        bajo = t.lower()
        # 1. Planta
        caso(f"1. {nombre}: bajos y primeras plantas con acceso independiente", "bajos y primeras plantas con acceso independiente" in bajo)
        caso(f"1. {nombre}: dice lo que no se conoce de un bajo", "ingresa un bajo" in bajo and "no se conoce" in bajo)
        caso(f"1. {nombre}: Ayuntamiento", "en el ayuntamiento" in bajo)
        caso(f"1. {nombre}: ya no dice que las normas no se han estudiado", "no se han estudiado" not in bajo)
        # 13. Comunidad de propietarios: Ley 49/1960, arts. 7.3 y 17.12
        caso(f"13. {nombre}: la comunidad de propietarios tiene que aprobarlo", "comunidad de propietarios" in bajo and "tres quintos" in bajo)
        # 14. Vivienda con protección pública: Decreto 79/2014, art. 17 ter.3
        caso(f"14. {nombre}: dice que no puede tener protección pública", "protección pública" in bajo)
        # 2 y 3. Corte del peor 25 % y anuncios nuevos, dichos con palabras
        caso(f"2. {nombre}: explica el corte con palabras", "uno de cada cuatro" in bajo)
        caso(f"3. {nombre}: mira los anuncios de un año o más", "anuncios de un año o más" in bajo)
        # 5 y 6. Recomendación
        caso(f"5. {nombre}: sin ganador", "ganador" in bajo)
        caso(f"6. {nombre}: se recomiendan sin decir que rindan más", "que rindan más" in bajo or "no significa que rindan" in bajo)
        caso(f"6. {nombre}: explica los dos que siguen en la lista 4 veces", "65 %" in t and "anfitriones con 10 anuncios o más" in bajo)
        # 7. Tope
        caso(f"7. {nombre}: quita la frase del tope", "cuantos más pisos llegan al tope" not in bajo)
        # 8. Anuncios
        caso(f"8. {nombre}: «280 pisos» no se lee como disponibles", "280 pisos" not in bajo and "anuncios en airbnb" in bajo)
        # 9. Lista
        caso(f"9. {nombre}: los días ocupados son la cifra menos fiable", "cifra menos fiable" in bajo)
        caso(f"9. {nombre}: quita el 0 de 9", "toda la ciudad coinciden" not in bajo and "coincidencias con los de m²" not in bajo)
        # 11. Texto
        caso(f"11. {nombre}: quita «con cualquier superficie»", "con cualquier superficie" not in bajo)
        # 12. Palabras que no se entienden fuera del proyecto
        for palabra in ("operadores grandes", "base de decisión", "firme", "con aviso", "cuartil bajo", "mejor cuarto", "no se distingue", "descuento del 25", "sin descuento", "con descuento", "semilla"):
            caso(f"12. {nombre}: no dice «{palabra}»", palabra not in bajo)
    for nombre in ("ejecutivo", "final", "interpretación"):
        t = s[nombre]
        caso(f"10. {nombre}: explica las 12 repeticiones", "12 veces" in t or "12 repeticiones" in t)
        caso(f"10. {nombre}: dice qué diferencia no se puede asegurar", "95 % de confianza" in t)
        caso(f"11. {nombre}: la tercera acción se liga a los datos siguientes", "cuando inside airbnb publique sus datos siguientes" in t.lower())
    for nombre in ("final", "cuadro", "interpretación"):
        caso(f"10. {nombre}: Puerta del Ángel sale en las cinco", "Puerta del Ángel" in s[nombre])
    for nombre in ("final", "interpretación"):
        caso(f"1. {nombre}: la norma, con su nivel y su zona", "nivel b de la zona 1" in s[nombre].lower() and "inferior a la baja" in s[nombre].lower())
    for nombre in ("final", "interpretación"):
        caso(f"13. {nombre}: cita la ley y lo que puede hacer la misma mayoría", "Ley 49/1960, arts. 7.3 y 17.12" in s[nombre] and "subir la cuota hasta un 20 %" in s[nombre])
    caso("13. la primera acción nombra a la comunidad", "Comprobar planta, norma y comunidad de propietarios" in s["ejecutivo"] and "Comprobar planta, norma y comunidad de propietarios" in s["cuadro"])
    for nombre in ("final", "interpretación"):
        caso(f"14. {nombre}: cita el artículo de la vivienda con protección pública", "art. 17 ter.3 del Decreto 79/2014" in s[nombre] and "Decreto 27/2026" in s[nombre])
        caso(f"14. {nombre}: nombra los dos certificados con su artículo", "dos certificados" in s[nombre] and "estatutos" in s[nombre] and "letras f y g" in s[nombre])
    caso("14. el final tiene la fila de la vivienda protegida", "Vivienda protegida" in s["final"])
    caso("14. el final tiene la fila de los certificados", "Certificados" in s["final"])
    caso("11. el anexo del final no lleva la frase del protocolo", "se siguiera uno" not in s["final"])
    caso("11. el anexo del ejecutivo no lleva la frase de las demás consultas", "Las demás consultas generales no se hacen" not in s["ejecutivo"])
    h1 = re.findall(r"<h1>(.*?)</h1>", (INFORMES / "cuadro_mando.html").read_text(encoding="utf-8"))
    caso("5. el título del cuadro dice hasta 2 habitaciones", "hasta 2 habitaciones" in h1[0], h1)
    caso("10. el título del mapa nombra los barrios", all(b in h1[1] for b in ("Ventas", "Numancia", "San Diego")) and "Vallecas" not in h1[1], h1)


def sin_decir_barrio(texto):
    """Da las frases que nombran un barrio sin decir antes que es un barrio: «Ventas» a secas no se entiende fuera de Madrid."""
    texto = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>|<table.*?</table>|```.*?```", " ", texto, flags=re.S)
    texto = re.sub(r"(?<=\S)\n(?=\S)", " ", texto)
    texto = html.unescape(re.sub(r"<[^>]+>", "\n", texto))
    malas = []
    for frase in re.split(r"(?<=[.:;])\s+|\n+", re.sub(r"[ \t]+", " ", texto)):
        m = re.search(r"Ventas|Numancia|San Diego|Opañel|Casco Histórico de Vallecas|Puerta del Ángel", frase)
        if m and "|" not in frase and "barrio" not in frase[:m.start()].lower():
            malas.append(frase.strip())
    return malas


def barrios_dichos_como_barrios():
    """Mira párrafos y listas de las salidas y de la portada; las tablas ya llevan «Barrio» en la cabecera."""
    caso("una frase con el barrio a secas se detecta", sin_decir_barrio("<p>Ventas rinde más.</p>") == ["Ventas rinde más."])
    caso("una frase que dice barrio pasa", not sin_decir_barrio("<p>El barrio de Ventas rinde más.</p>"))
    caso("una tabla no cuenta", not sin_decir_barrio("<table><tr><td>Ventas</td></tr></table>"))
    for ruta in (INFORMES / "informe_ejecutivo.html", INFORMES / "informe_final.html", INFORMES / "cuadro_mando.html", INFORMES.parent / "index.html", INFORMES.parent / "README.md"):
        malas = sin_decir_barrio(ruta.read_text(encoding="utf-8"))
        caso(f"{ruta.name}: cada barrio se dice como barrio", not malas, malas[:5])


if __name__ == "__main__":
    intento("A. funciones", funciones)
    intento("B. cifras", cifras)
    intento("C. textos", textos)
    intento("D. barrios", barrios_dichos_como_barrios)
    print(f"{len(FALLOS)} fallos")
    sys.exit(1 if FALLOS else 0)
