"""Prueba scripts/diccionario_datos.py de punta a punta, con datos pequeños escritos en datos_de_prueba.py.

Copia el script a una carpeta de caso temporal y lo lanza como proceso aparte, así que no lo importa.
Sale con 0 si todo pasa y con 1 si falla algo, e imprime qué caso falla.
Para probar un mutante, pon en SCRIPT_A_PROBAR la ruta de una copia cambiada.
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

SCRIPT = Path(os.environ.get("SCRIPT_A_PROBAR", CARPETA.parent / "scripts" / "diccionario_datos.py"))
FALLOS = []


def caso(nombre, condicion, detalle=""):
    """Apunta un caso de la prueba y dice si pasa."""
    print(f"{'ok   ' if condicion else 'FALLA'} {nombre} {detalle if not condicion else ''}")
    if not condicion:
        FALLOS.append(nombre)


def lanzar(raiz, nombre, entorno=None):
    """Ejecuta la copia del script dentro del caso temporal, con -W error."""
    env = {**os.environ, "PYTHONUTF8": "1", **(entorno or {})}
    return subprocess.run([sys.executable, "-W", "error", str(raiz / "scripts" / nombre)], capture_output=True,
                          text=True, encoding="utf-8", env=env)


def tabla_de(datos, nombre):
    """Busca una tabla del diccionario por su nombre."""
    return next((t for t in datos["tablas"] if t["tabla"] == nombre), None)


def campo_de(tabla, columna):
    """Busca la ficha de una columna."""
    return next((c for c in tabla["campos"] if c["columna"] == columna), None)


def principal():
    """Recorre los casos de la prueba."""
    if not SCRIPT.exists():
        print(f"FALLA el script no existe todavía: {SCRIPT}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        raiz = dp.crear_caso(Path(tmp) / "caso", [SCRIPT])
        nombre = SCRIPT.name
        r = lanzar(raiz, nombre, {"TROZO_FILAS": "50"})  # trozos pequeños: lo que cruce un trozo tiene que sumar bien
        caso("el script acaba sin error con -W error", r.returncode == 0, r.stderr[-1500:])
        ruta = raiz / "config" / "fuentes" / "diccionario-datos-origen.json"
        if not ruta.exists():
            print("FALLA no hay JSON")
            return 1
        texto_json = ruta.read_text(encoding="utf-8")
        d = json.loads(texto_json)
        md = (raiz / "config" / "fuentes" / "diccionario-datos-origen.md").read_text(encoding="utf-8")

        sep = tabla_de(d, "listings_2026-09-17")
        caso("la foto tiene sus filas", sep is not None and sep["filas"] == 322, str(sep and sep["filas"]))
        caso("cada columna de la foto tiene ficha", sep["columnas"] == len(sep["campos"]))
        caso("el calendario suma todos los trozos", tabla_de(d, "calendar_2026-09-17")["filas"] == 322 * 3)
        cal_id = campo_de(tabla_de(d, "calendar_2026-09-17"), "listing_id")
        caso("los distintos no se cuentan dos veces entre trozos", cal_id["distintos"] == 322, str(cal_id["distintos"]))
        caso("las reseñas suman todos los trozos", tabla_de(d, "reviews_fechas_2026-09-17")["filas"] == 317 * 2)

        caso("nulos exactos de una columna", campo_de(sep, "minimum_nights")["nulos"] == 1)
        caso("una columna entera vacía no es resuelta", campo_de(sep, "bathrooms")["clase"] == "no_se_puede_saber")
        lic = campo_de(sep, "licencia_nacional")
        caso("la licencia generalizada es dato personal", lic["rol"] == "dato_personal")
        caso("la licencia no enseña valores", lic["valores"] is None)
        caso("la licencia lleva su protección", (lic["proteccion"] or {}).get("tecnica") == "generalizacion")
        caso("ni el JSON ni el Markdown dicen valores de la licencia", '"NT"' not in texto_json and "| NT" not in md)
        caso("un cero documentado lo dice", campo_de(sep, "estimated_occupancy_l365d")["significado_cero"] is not None)
        caso("un dominio desbordado va a decisión de negocio", campo_de(sep, "bedrooms")["clase"] == "decision_de_negocio")
        caso("la columna decidida va a pendientes", any(p["columna"] == "bedrooms" for p in d["pendientes"]))
        caso("cada significado tiene procedencia", all(c["procedencia"] for t in d["tablas"] for c in t["campos"]))

        pl = campo_de(tabla_de(d, "licencias_vut_por_barrio"), "planta")
        caso("las variantes de escritura van a decisión", pl["clase"] == "decision_de_negocio")
        caso("un texto con 15 valores o menos da su lista", pl["valores"] is not None and len(pl["valores"]) <= 15)

        e = tabla_de(d, "E3210626_precio_declarado_2025")
        caso("el libro lee distritos y barrios", e is not None and e["filas"] == 13, str(e and e["filas"]))
        caso("el libro declara hoja y cabecera", e["lectura"]["hoja"] == "E32" and e["lectura"]["fila_cabecera"] is not None)
        caso("la cabecera de dos filas se conserva", campo_de(e, "Total ") is not None,
             str([c["columna"] for c in e["campos"]]))
        caso("un precio en texto da mínimo y máximo numéricos", campo_de(sep, "price")["maximo"] == 409.0, str(campo_de(sep, "price")["maximo"]))
        caso("el cero de la nota (2) del libro está documentado", (campo_de(e, "Nueva")["significado_cero"] or {}).get("procedencia") == "declarado")
        caso("deja las posiciones para calidad", len(e["lectura"]["posiciones"]) == e["columnas"])
        caso("el total de la ciudad no entra", "Ciudad de Madrid" not in json.dumps(campo_de(e, "Distrito"), ensure_ascii=False))

        geo = {g["fichero"].split("/")[-1]: g for g in d["geometrias"]}
        caso("cuenta los elementos del GeoJSON", geo["neighbourhoods.geojson"]["elementos"] == 11)
        caso("caza el polígono inválido", geo["neighbourhoods.geojson"]["invalidos"] == 1)
        caso("cuenta los puntos fuera de Madrid", geo["parques_jardines.geojson"]["fuera_de_madrid"] == 1)
        caso("el límite es válido", geo["ape_00_01.json"]["invalidos"] == 0)

        caso("el diccionario de la organización está leído", d["diccionario_organizacion"] is not None)
        caso("lista lo documentado que no llega", any(c["columna"] == "EXPEDIENTE" for c in d["contradicciones"]))
        caso("lista lo que la protección quitó", any(c["columna"] == "host_name" for c in d["columnas_que_no_llegan"]))
        caso("el filtro de precio tiene su recuento",
             any(f["regla"].startswith("Precio") and f["filas_afectadas"] is not None for f in d["filtros_de_negocio"]))
        caso("lo que pide cruzar tablas va como null", any(f["filas_afectadas"] is None for f in d["filtros_de_negocio"]))
        caso("el JSON y el Markdown dicen las mismas filas", f"| {sep['tabla']} | {sep['filas']} |" in md)
        caso("el Markdown lleva Datos personales", "## Datos personales" in md)
        caso("el JSON lleva fecha_datos", d.get("fecha_datos") == "2026-09-17")
        caso("el JSON no lleva NaN", "NaN" not in texto_json and "Infinity" not in texto_json)

        # La huella distinta se dice, y un dato sin proteger para el trabajo.
        g = raiz / "data" / "raw" / "externos" / "neighbourhoods.csv"
        g.write_text(g.read_text(encoding="utf-8") + "Este,Nuevo\n", encoding="utf-8")
        lanzar(raiz, nombre)
        d2 = json.loads(ruta.read_text(encoding="utf-8"))
        caso("una huella distinta se dice",
             any("neighbourhoods.csv" in a for a in d2["avisos"]) and d2["resultado"]["estado"] == "AVISO")
        pj = raiz / "config" / "fuentes" / "proteccion-datos.json"
        protegido = json.loads(pj.read_text(encoding="utf-8"))
        protegido["estado"] = "PARADO"
        pj.write_text(json.dumps(protegido), encoding="utf-8")
        lanzar(raiz, nombre)
        d3 = json.loads(ruta.read_text(encoding="utf-8"))
        caso("sin protección no empieza", d3["resultado"]["estado"] == "PARADO" and not d3["tablas"])

    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodos los casos pasan")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
