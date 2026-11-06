"""Prueba scripts/calidad_datos.py de punta a punta, con datos pequeños escritos en datos_de_prueba.py.

Copia los dos scripts a una carpeta de caso temporal y los lanza como procesos aparte, así que no los importa.
Sale con 0 si todo pasa y con 1 si falla algo, e imprime qué caso falla.
Para probar un mutante, pon en SCRIPT_A_PROBAR la ruta de una copia cambiada de calidad_datos.py.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))
import datos_de_prueba as dp  # noqa: E402

SCRIPTS = CARPETA.parent / "scripts"
CALIDAD = Path(os.environ.get("SCRIPT_A_PROBAR", SCRIPTS / "calidad_datos.py"))
DICCIONARIO = SCRIPTS / "diccionario_datos.py"
APARTADOS = ["Fuente analizada", "Resumen", "Inspección general", "Estructura", "Tipos y formatos", "Valores ausentes", "Duplicados",
             "Claves y granularidad", "Categóricas y texto", "Numéricas y outliers", "Fechas", "Reglas lógicas e integridad",
             "Cruces entre tablas", "Reglas candidatas para aprobar", "Resumen de problemas detectados", "Posibles acciones",
             "Parámetros usados", "Datos personales", "Límites de esta revisión", "Tabla de decisiones"]
FALLOS = []


def caso(nombre, condicion, detalle=""):
    """Apunta un caso de la prueba y dice si pasa."""
    print(f"{'ok   ' if condicion else 'FALLA'} {nombre} {detalle if not condicion else ''}")
    if not condicion:
        FALLOS.append(nombre)


def lanzar(raiz, nombre):
    """Ejecuta un script dentro del caso temporal, con -W error."""
    return subprocess.run([sys.executable, "-W", "error", str(raiz / "scripts" / nombre)], capture_output=True, text=True,
                          encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1", "TROZO_FILAS": "50"})


def fila_de(lista, **filtros):
    """Busca la primera fila que cumple todos los filtros."""
    return next((f for f in lista if all(f.get(k) == v for k, v in filtros.items())), None)


def asunto(datos, clave):
    """Busca una fila de la tabla de decisiones por su clave."""
    return fila_de(datos["tabla_de_decisiones"], clave=clave)


def principal():
    """Recorre los casos de la prueba."""
    if not CALIDAD.exists():
        print(f"FALLA el script no existe todavía: {CALIDAD}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        raiz = dp.crear_caso(Path(tmp) / "caso", [DICCIONARIO, CALIDAD])
        antes = {p: dp.huella(p) for p in (raiz / "data" / "raw").rglob("*") if p.is_file()}
        r0 = lanzar(raiz, DICCIONARIO.name)
        caso("el diccionario acaba bien", r0.returncode == 0, r0.stderr[-800:])
        r = lanzar(raiz, CALIDAD.name)
        caso("el script acaba sin error con -W error", r.returncode == 0, r.stderr[-1800:] + r.stdout[-400:])
        ruta = raiz / "informes" / "calidad-datos.json"
        if not ruta.exists():
            print("FALLA no hay JSON")
            return 1
        texto = ruta.read_text(encoding="utf-8")
        d = json.loads(texto)
        md = (raiz / "informes" / "calidad-datos.md").read_text(encoding="utf-8")
        caso("el estado no es ERROR", d["resultado"]["estado"] != "ERROR", d["resultado"]["resumen"])

        caso("parte del diccionario", d["con_diccionario"] is True)
        caso("lleva fecha_datos", d.get("fecha_datos") == "2026-09-17")
        posiciones = [md.find(f"## {a}") for a in APARTADOS]
        caso("el informe tiene los apartados en su orden", -1 not in posiciones and posiciones == sorted(posiciones), str(posiciones))
        caso("el informe sale de la ejecución", d["fecha_ejecucion"][:10] in md)
        caso("el JSON no lleva NaN", "NaN" not in texto and "Infinity" not in texto)
        caso("el JSON no da valores de licencia", '"NT"' not in texto)
        caso("el plan queda sin aprobar y por eso AVISO", d["plan_aprobado"]["por"] == "" and d["resultado"]["estado"] == "AVISO")

        n = fila_de(d["nulos_por_segmento"], tabla="listings_2026-09-17", columna="review_scores_rating")
        caso("nulos concentrados en su segmento", n is not None and n["veredicto"] == "concentrados", str(n))
        n = fila_de(d["nulos_por_segmento"], tabla="licencias_vut_por_barrio", columna="planta")
        caso("sin segmento de 30 filas no se puede saber", n is None or n["veredicto"] in ("no_se_puede_saber", "sin_nulos"), str(n))
        magnitudes = {(t["tabla"], c["columna"]) for t in d["roles_de_magnitud"] for c in t["columnas"]}
        caso("cada magnitud tiene escala", magnitudes <= {(e["tabla"], e["columna"]) for e in d["escala"]})
        caso("cada magnitud tiene colas", magnitudes <= {(e["tabla"], e["columna"]) for e in d["colas"]})
        cola = fila_de(d["colas"], tabla="listings_2026-09-17", columna="bedrooms")
        caso("las colas enseñan el valor raro", cola["altos"][-1]["valor"] == 50)
        caso("el mayor salto llega al valor raro", cola["mayor_salto"]["hasta"] == 50)
        e = fila_de(d["escala"], tabla="listings_2026-09-17", columna="review_scores_value")
        caso("marca la escala perdida con su factor", e["salto"] and e["factor"] == 1000 and e["factor_uniforme"] is True, str(e))
        e = fila_de(d["escala"], tabla="listings_2026-09-17", columna="price")
        caso("una magnitud normal no lleva factor", e["factor"] is None, str(e))
        o = fila_de(d["outliers"], tabla="listings_2026-09-17", columna="accommodates")
        caso("sin dispersión no se marcan atípicos", o["iqr"] is None and o["sin_dispersion"] is True, str(o))
        c = fila_de(d["codigos_de_ausencia"], tabla="licencias_vut_por_barrio", columna="planta", codigo="N/A")
        caso("caza el código de ausencia en texto", c is not None and c["documentado"] is False, str(c))
        c = fila_de(d["codigos_de_ausencia"], tabla="E3210626_precio_declarado_2025", codigo=0)
        caso("el cero del libro es código documentado", c is not None and c["documentado"] is True, str(c))
        caso("licencias: filas iguales", fila_de(d["duplicados"], tabla="licencias_vut_por_barrio")["exactos"] == 1)
        caso("reseñas: clave repetida", fila_de(d["duplicados"], tabla="reviews_fechas_2026-09-17")["por_clave"] == 317)
        caso("registra la instrucción en un texto sin obedecerla",
             any(i["columna"] == "property_type" for i in d["instrucciones_en_texto"]))
        caso("categoría rara tomada del diccionario", fila_de(d["categorias_raras"], tabla="listings_2026-09-17", columna="property_type") is not None)
        caso("marca una regla candidata con su recuento", any(rc["filas_que_incumplen"] is not None for rc in d["reglas_candidatas"]))
        caso("las reglas candidatas van a pendientes", any(p["id"].startswith("RC-") for p in d["pendientes"]))

        cr = fila_de(d["cruces"], izquierda="listings_2026-09-17.id", derecha="reviews_fechas_2026-09-17.listing_id")
        caso("cruce con reseñas, los dos lados", cr is not None and cr["sin_pareja_izquierda"] == 5 and cr["sin_pareja_derecha"] == 0, str(cr))
        cr = fila_de(d["cruces"], izquierda="neighbourhoods.neighbourhood", derecha="E3210626_precio_declarado_2025.barrio")
        caso("el cruce de barrios cuenta antes y después de igualar",
             cr is not None and cr["sin_pareja_izquierda_antes"] == 3 and cr["sin_pareja_izquierda"] == 2, str(cr))

        m = d["medicion"]
        caso("la base de decisión sale del embudo", m["base"]["pisos"] == 321, str(m["base"]["pisos"]))
        caso("el barrio plantado está en el grupo", "Bosque" in m["base"]["grupo"], str(m["base"]["grupo"]))
        caso("el barrio bajo no está en el grupo", "Llano" not in m["base"]["grupo"])
        caso("el tipo de piso ganador sale", m["base"]["tipo"]["dormitorios"]["ganador"] == "1", str(m["base"]["tipo"]))
        caso("Ribera y Llano se distinguen", ["Llano", "Ribera"] in m["base"]["pares_que_se_distinguen"])
        caso("dos barrios iguales no se distinguen", ["Concepción", "Prado"] not in m["base"]["pares_que_se_distinguen"], str(m["base"]["pares_que_se_distinguen"]))
        a = asunto(d, "captura_anterior")
        caso("sin decisión: lleva opciones y medición", a["decision"] is None and a["opciones"] and a["medicion"] is not None)
        caso("quitar la captura anterior saca el barrio plantado", "Bosque" in a["medicion"]["grupo_salen"], str(a["medicion"]))
        caso("el veredicto dice que cambia", a["medicion"]["cambia_grupo"] is True)
        caso("compara con intervalo el que sale y el que entra",
             any(x["sale"] == "Bosque" and "se_distinguen_en_la_base" in x for x in a["medicion"]["pares_entran_salen"]), str(a["medicion"].get("pares_entran_salen")))
        caso("cuenta los pares que tocan al grupo", "pares_del_grupo_que_cambian" in a["medicion"])
        caso("un primero que cambia sin distinguirse no cambia el tipo",
             all(v["cambia_de_verdad"] == (v["cambia_ganador"] and v["nuevo_se_distingue_del_anterior"]) for v in a["medicion"]["tipo"].values()), str(a["medicion"]["tipo"]))
        a = asunto(d, "aeropuerto")
        caso("si el primero no cambia, no se cuenta cambio", not any(v["cambia_ganador"] for v in a["medicion"]["tipo"].values()), str(a["medicion"]["tipo"]))
        caso("Aeropuerto, pocos pisos: no cambia el grupo", a["medicion"]["cambia_grupo"] is False and a["medicion"]["pares_que_cambian"] == 0, str(a["medicion"]))
        a = asunto(d, "estancia_vacia")
        caso("con decisión: la cita y no mide", a["decision"] and "§5" in a["decision"] and a["medicion"] is None, str(a))
        caso("cada fila lleva identificador C-nn", all(f["id"].startswith("C-") for f in d["tabla_de_decisiones"]))
        caso("toda fila sin decisión tiene medición o motivo",
             all(f["decision"] or f["medicion"] or f["no_medible"] for f in d["tabla_de_decisiones"]))
        caso("una fila con cero afectados no es un asunto", all(f["filas_afectadas"] for f in d["tabla_de_decisiones"]),
             str([f["clave"] for f in d["tabla_de_decisiones"] if not f["filas_afectadas"]]))
        caso("la tabla está en el informe", asunto(d, "captura_anterior")["id"] in md.split("## Tabla de decisiones")[1])

        caso("data/raw no cambia", antes == {p: dp.huella(p) for p in (raiz / "data" / "raw").rglob("*") if p.is_file()})

        # Un diccionario que no corresponde a los datos no se usa.
        dicc = raiz / "config" / "fuentes" / "diccionario-datos-origen.json"
        original = dicc.read_text(encoding="utf-8")
        cambiado = json.loads(original)
        cambiado["entradas"][0]["sha256"] = "0" * 64
        dicc.write_text(json.dumps(cambiado), encoding="utf-8")
        lanzar(raiz, CALIDAD.name)
        caso("con otra huella no toma el diccionario", json.loads(ruta.read_text(encoding="utf-8"))["con_diccionario"] is False)

        # Si el diccionario paró, calidad no empieza.
        cambiado = json.loads(original)
        cambiado["resultado"] = {"estado": "PARADO", "resumen": "paró"}
        dicc.write_text(json.dumps(cambiado), encoding="utf-8")
        lanzar(raiz, CALIDAD.name)
        caso("si el diccionario paró, no empieza", json.loads(ruta.read_text(encoding="utf-8"))["resultado"]["estado"] == "PARADO")
        dicc.write_text(original, encoding="utf-8")

        # Un dato personal en claro para el trabajo (reglas §9).
        lic = raiz / "data" / "raw" / "externos" / "licencias_vut_por_barrio.csv"
        lic.write_text(lic.read_text(encoding="utf-8") + "Distrito de Sur,Valle,ana.perez@correo.es,1.0\n", encoding="utf-8")
        lanzar(raiz, CALIDAD.name)
        d4 = json.loads(ruta.read_text(encoding="utf-8"))
        caso("un correo en claro para el trabajo", d4["resultado"]["estado"] == "PARADO", d4["resultado"]["resumen"])
        caso("el valor personal no se copia", "ana.perez" not in ruta.read_text(encoding="utf-8"))

    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodos los casos pasan")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
