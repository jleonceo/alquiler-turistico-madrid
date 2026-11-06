"""Prueba scripts/correccion_datos.py de punta a punta en el caso pequeño, con datos escritos en las pruebas."""
import sys
import tempfile
from pathlib import Path

import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cadena_de_prueba as cp  # noqa: E402

APARTADOS = ["## Fuente", "## Correcciones aplicadas", "## Decisiones del usuario", "## Elementos mantenidos sin cambios",
             "## Decisiones pendientes", "## Validación", "## Datos personales", "## Límites"]


def tablas_buenas():
    """Monta unas tablas pequeñas que pasan las comprobaciones; cada caso en rojo estropea una."""
    sep = pd.DataFrame({"id": [1, 2], "price": [50.0, None], "banos": [1.0, 2.0], "bedrooms": [1.0, 2.0], "beds": [1.0, 2.0], "accommodates": [2, 4], "room_type": ["Entire home/apt", "Private room"], "property_type": ["Entire rental unit", "Private room"],
                        "neighbourhood_cleansed": ["Ribera", "Bosque"], "neighbourhood_group_cleansed": ["Norte", "Norte"], "latitude": [40.3, 40.4], "longitude": [-3.6, -3.7], "minimum_nights": [2.0, 3.0], "availability_365": [10, 20],
                        "estimated_occupancy_l365d": [10, 0], "number_of_reviews_ltm": [1, 0], "calculated_host_listings_count": [1, 2], "price_quote_checkin_date": ["2026-10-01", None], "licencia_exencion": ["temporada", None]})
    cal = pd.DataFrame({"listing_id": [1], "date": pd.to_datetime(["2026-09-20"]), "available": pd.array([True], dtype="boolean")})
    res = pd.DataFrame({"listing_id": [1], "date": pd.to_datetime(["2026-01-01"])})
    barrios = pd.DataFrame({"barrio": ["Ribera"], "clave_oficial": ["ribera"]})
    return sep, cal, res, barrios


def pruebas_de_comprobaciones(p, cor):
    """Las comprobaciones de la corrección miden: cada una tiene su caso en rojo a propósito."""
    sep, cal, res, barrios = tablas_buenas()
    bien = cor.medir_consistencia({"sep": sep}, cal, res, barrios, 0)
    p.caso("consistencia buena pasa", bien["pasa"], str(bien))
    # ROJO a propósito: cada uno de estos fallos tiene que dar que no pasa.
    malo = sep.assign(price=["50", "60"])
    p.caso("un precio en texto no pasa la consistencia", not cor.medir_consistencia({"sep": malo}, cal, res, barrios, 0)["pasa"])
    p.caso("una fecha en texto no pasa la consistencia", not cor.medir_consistencia({"sep": sep}, cal.assign(date=["2026-09-20"]), res, barrios, 0)["pasa"])
    p.caso("una reseña sin fecha no pasa la consistencia", not cor.medir_consistencia({"sep": sep}, cal, res.assign(date=pd.to_datetime([None])), barrios, 0)["pasa"])
    p.caso("un día fuera del mapeo no pasa la consistencia", not cor.medir_consistencia({"sep": sep}, cal.assign(available=pd.array([pd.NA], dtype="boolean")), res, barrios, 0)["pasa"])
    p.caso("un distrito sin maestro no pasa la consistencia", not cor.medir_consistencia({"sep": sep}, cal, res, barrios, 1)["pasa"])
    p.caso("un barrio sin clave no pasa la consistencia", not cor.medir_consistencia({"sep": sep}, cal, res, barrios.assign(clave_oficial=[None]), 0)["pasa"])

    u = cor.medir_utilidad(sep)
    p.caso("utilidad buena pasa", u["pasa"], str(u))
    p.caso("sin una columna de las preguntas no pasa la utilidad", not cor.medir_utilidad(sep.drop(columns="bedrooms"))["pasa"])
    p.caso("con una columna entera vacía no pasa la utilidad", not cor.medir_utilidad(sep.assign(price=float("nan")))["pasa"])
    p.caso("la utilidad dice qué falta", "bedrooms" in cor.medir_utilidad(sep.drop(columns="bedrooms"))["texto"])

    roles = {"room_type": "categorica", "nota": "texto_libre"}
    d = cor.medir_datos_personales([("sep", sep, roles, ["host_name"])])
    p.caso("sin datos personales pasa", d["pasa"], str(d))
    p.caso("un correo en una columna de texto no pasa", not cor.medir_datos_personales([("sep", sep.assign(nota=["a@b.es", "x"]), roles, ["host_name"])])["pasa"])
    p.caso("una columna suprimida que vuelve no pasa", not cor.medir_datos_personales([("sep", sep.assign(host_name=["x", "y"]), roles, ["host_name"])])["pasa"])
    p.caso("el texto no copia el valor", "a@b.es" not in cor.medir_datos_personales([("sep", sep.assign(nota=["a@b.es", "x"]), roles, ["host_name"])])["texto"])

    p.caso("completitud buena pasa", cor.medir_completitud(10, 10, 2)["pasa"])
    p.caso("una fila de menos no pasa la completitud", not cor.medir_completitud(10, 9, 2)["pasa"])
    p.caso("el recuento de cuestiones se lee del fichero", cor.contar_cuestiones("| CP-001 (C-01) | a | b | c |\n| CP-002 (C-02) | a | b | c |\n") == ["CP-001", "CP-002"])


def principal():
    """Recorre los casos de la corrección."""
    p = cp.Prueba()
    try:
        import correccion_datos as cor
        if not hasattr(cor, "medir_consistencia"):
            p.caso("las comprobaciones de la corrección miden", False, "falta medir_consistencia")
        else:
            pruebas_de_comprobaciones(p, cor)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            caso, r = cp.montar(tmp, "correccion_datos.py")
            p.caso("la corrección acaba bien", r.returncode == 0, r.stderr[-800:])
            pro = caso / "data" / "processed"
            sep = pd.read_parquet(pro / "listings_2026-09-17_corregido.parquet").set_index("id")
            filas = cp.gz_lineas(caso / "data" / "raw" / cp.SEP)
            p.caso("ninguna fila desaparece de la foto", len(sep) == filas, f"{len(sep)} frente a {filas}")
            p.caso("el precio es número", pd.api.types.is_float_dtype(sep["price"]))
            p.caso("el precio con coma de miles vale 1250", sep.loc[cp.ID["miles"], "price"] == 1250)
            p.caso("el precio vacío sigue vacío (CP-001)", pd.isna(sep.loc[cp.ID["vacio"], "price"]))
            p.caso("medio baño vale 0,5", sep.loc[cp.ID["medio"], "banos"] == 0.5)
            p.caso("cero baños se marca (CP-007)", bool(sep.loc[cp.ID["cero"], "marca_cero_banos"]))
            p.caso("un piso sin vivienda entera se marca (CP-008)", bool(sep.loc[cp.ID["no_vivienda"], "marca_no_vivienda"]))
            p.caso("una habitación no se marca como no vivienda", not bool(sep.loc[cp.ID["privada"], "marca_no_vivienda"]))
            p.caso("el tamaño incoherente se marca (CP-009)", bool(sep.loc[cp.ID["incoherente"], "marca_tamano_incoherente"]))
            p.caso("la columna vacía sale (CP-013)", "neighbourhood" not in sep.columns)
            dic = pd.read_parquet(pro / "listings_2025-12-14_corregido.parquet")
            p.caso("la foto sin precio pierde esa columna", "price" not in dic.columns)
            puntos = pd.read_parquet(pro / "puntos_interes_corregido.parquet")
            p.caso("el punto fuera de Madrid sale (CP-011)", len(puntos) == 4, str(len(puntos)))
            lic = pd.read_parquet(pro / "licencias_corregido.parquet")
            p.caso("las licencias conservan sus filas", len(lic) == 6)
            p.caso("el distrito de las licencias queda como en el maestro (CP-012)", set(lic["distrito"]) == {"Norte", "Sur"}, str(set(lic["distrito"])))
            p.caso("la planta se unifica (CP-012)", int(lic["planta"].eq("BAJA").sum()) == 4, str(lic["planta"].tolist()))
            bar = pd.read_parquet(pro / "barrios_corregido.parquet").set_index("barrio")
            p.caso("la equivalencia de nombre se aplica (CP-004)", bar.loc["Concepción", "clave_oficial"] == "la concepcion")
            of = pd.read_parquet(pro / "oficial_2025_corregido.parquet")
            aero = of.loc[of["clave"].eq("san andres"), "m2_total"]
            p.caso("San Andrés no está en el libro", aero.empty)
            cero = of.loc[of["clave"].eq("aeropuerto"), "m2_total"].iloc[0]
            p.caso("el cero del libro pasa a vacío", pd.isna(cero), str(cero))
            geo = pd.read_parquet(pro / "barrios_poligonos_corregido.parquet")
            formas = shapely.from_wkb(geo["geometria_wkb"].to_numpy())
            p.caso("el polígono inválido se repara (CP-014)", bool(shapely.is_valid(formas).all()))
            cal = pd.read_parquet(pro / "calendario_corregido.parquet")
            p.caso("el calendario conserva sus filas", len(cal) == cp.gz_lineas(caso / "data" / "raw" / "calendar_2026-09-17.csv.gz"))
            p.caso("la fecha del calendario es fecha", pd.api.types.is_datetime64_any_dtype(cal["date"]))
            res = pd.read_parquet(pro / "resenas_corregido.parquet")
            p.caso("las reseñas conservan sus filas", len(res) == cp.gz_lineas(caso / "data" / "raw" / "reviews_fechas_2026-09-17.csv.gz"))

            j = cp.leer(caso, "correccion-datos.json")
            p.caso("el JSON no está parado", j["resultado"]["estado"] in ("OK", "AVISO"), j["resultado"]["resumen"])
            p.caso("el JSON lleva fecha_datos", j.get("fecha_datos") == "2026-09-17")
            p.caso("hay una salida por tabla", len(j["salidas"]) >= 10, str(len(j["salidas"])))
            p.caso("cada corrección lleva su ficha", all(c["ficha"] for c in j["correcciones"]))
            p.caso("las sumas de control cuadran", j["sumas_control"] and all(x["coincide"] for x in j["sumas_control"]))
            p.caso("las comprobaciones son las cuatro y pasan", all(v.startswith("pasa:") for v in j["comprobaciones"].values()) and set(j["comprobaciones"]) == {"completitud", "consistencia", "utilidad", "datos_personales"}, str(j["comprobaciones"]))
            p.caso("las columnas suprimidas se encuentran de verdad", " 0 columnas suprimidas" not in j["comprobaciones"]["datos_personales"], j["comprobaciones"]["datos_personales"])
            codigo = (Path(__file__).resolve().parents[1] / "scripts" / "correccion_datos.py").read_text(encoding="utf-8")
            p.caso("ninguna comprobación lleva un pasa escrito a mano", '"pasa: ' not in codigo.split("# 4. Fichas del registro")[1])
            p.caso("el número de columnas no lleva un fijo", "shape[1] - 6" not in codigo)
            p.caso("el número de cuestiones no va escrito", "catorce" not in codigo)
            informe = (caso / "informes" / "correccion-datos.md").read_text(encoding="utf-8")
            for apartado in APARTADOS:
                p.caso(f"el informe trae {apartado}", apartado in informe)

            registro = caso / "config" / "modelo" / "registro-transformaciones.md"
            texto = registro.read_text(encoding="utf-8")
            p.caso("la ficha R-001 sigue", "## R-001" in texto)
            p.caso("hay una ficha por cada cuestión", all(f"CP-{i:03d}" in texto for i in range(1, 15)))
            p.caso("el registro conserva sus saltos de línea", b"\r\n" not in registro.read_bytes())
            cuantas = texto.count("\n## R-")
            antes = cp.huellas(caso)
            r2 = cp.lanzar(caso, "correccion_datos.py")
            p.caso("repetir no añade fichas", r2.returncode == 0 and registro.read_text(encoding="utf-8").count("\n## R-") == cuantas)
            p.caso("data/raw no cambia", antes == cp.huellas(caso))
    except FileNotFoundError as error:
        p.caso("los scripts existen", False, str(error))
    return p.fin()


if __name__ == "__main__":
    sys.exit(principal())
