"""Prueba scripts/transformacion_datos.py en el caso pequeño: cada columna con un caso calculado a mano y las paradas."""
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cadena_de_prueba as cp  # noqa: E402

APARTADOS = ["## Fuente", "## Objetivo", "## Transformaciones aplicadas", "## Variables generadas", "## Transformaciones pendientes",
             "## Cambios estructurales", "## Validación", "## Dataset generado", "## Datos personales"]
PLANTADOS = (("cero", "excl_cero_banos"), ("no_vivienda", "excl_no_vivienda"), ("incoherente", "excl_tamano_incoherente"), ("vacio", "excl_precio_vacio"),
             ("privada", "excl_no_piso_completo"), ("centro", "excl_dentro_centro"), ("camas", "excl_camas_vacias"), ("miles", "excl_precio_fuera_rango"))


def principal():
    """Recorre los casos de la transformación."""
    p = cp.Prueba()
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            caso, r = cp.montar(tmp, "transformacion_datos.py")
            p.caso("la transformación acaba bien", r.returncode == 0, r.stderr[-800:])
            pro = caso / "data" / "processed"
            a = pd.read_parquet(pro / "analisis_anuncios.parquet").set_index("id")
            n = cp.gz_lineas(caso / "data" / "raw" / cp.SEP)
            p.caso("una fila por anuncio", len(a) == n and a.index.is_unique)
            p.caso("el anuncio dentro del centro lleva su lado", a.loc[cp.ID["centro"], "lado_centro"] == "dentro")
            p.caso("el resto está fuera", a.loc[cp.ID["cero"], "lado_centro"] == "fuera")
            p.caso("la distancia al borde es positiva", a["distancia_borde_m"].gt(0).all())
            p.caso("estancia de calendario con su origen", a.loc[cp.ID["estancia"], "estancia_noches"] == 2 and a.loc[cp.ID["estancia"], "estancia_origen"] == "calendario")
            # Ribera: el libro le da 2000 €/m² y 75 m² oficiales.
            fila = a.loc[1020]
            p.caso("estancia publicada con su origen", fila["estancia_origen"] == "publicada")
            sup = 65.0 if fila["dormitorios"] == 2 else 50.0
            p.caso("superficie de valoraciones", fila["superficie_valoraciones_m2"] == sup)
            compra = sup * 2000 * 0.75
            p.caso("precio de compra con descuento", abs(fila["compra_valoraciones_desc_eur"] - compra) < 1e-6)
            p.caso("precio de compra sin descuento", abs(fila["compra_valoraciones_sin_eur"] - compra / 0.75) < 1e-6)
            ingreso = fila["precio_eur"] * fila["ocupacion_dias"]
            p.caso("ingreso anual", abs(fila["ingreso_anual_eur"] - ingreso) < 1e-6)
            p.caso("rentabilidad con descuento", abs(fila["rent_valoraciones_desc_pct"] - 100 * ingreso / compra) < 1e-6)
            p.caso("rentabilidad con la superficie oficial", abs(fila["rent_oficial_sin_pct"] - 100 * ingreso / (75.0 * 2000)) < 1e-6)
            vacio = a.loc[cp.ID["vacio"]]
            p.caso("un precio vacío deja vacía la rentabilidad, no cero", pd.isna(vacio["ingreso_anual_eur"]) and pd.isna(vacio["rent_valoraciones_desc_pct"]))
            aero = a.loc[a["barrio"].eq("Aeropuerto")].iloc[0]
            p.caso("Aeropuerto toma el precio de su distrito", aero["precio_m2_eur"] == 5000 and aero["precio_m2_origen"] == "distrito", str(aero["precio_m2_eur"]))
            p.caso("un barrio con su precio dice su origen", fila["precio_m2_origen"] == "barrio")
            p.caso("competencia es el recuento del barrio", fila["competencia_anuncios"] == int(a["barrio"].eq("Ribera").sum()))
            p.caso("precio de junio", fila["precio_jun_eur"] > 0)
            p.caso("captura anterior", bool(a.loc[a["barrio"].eq("Bosque"), "captura_anterior"].any()) and not bool(fila["captura_anterior"]))
            # Columnas de las cinco pruebas: el anfitrión plantado tiene 12 anuncios y la cotización lejana, 120 días.
            p.caso("anuncios del anfitrión", "anuncios_anfitrion" in a and a.loc[cp.ID["anfitrion"], "anuncios_anfitrion"] == 12 and fila["anuncios_anfitrion"] == 1)
            p.caso("días hasta la cotización de septiembre", "dias_cotizacion" in a and fila["dias_cotizacion"] == 14 and a.loc[cp.ID["lejana"], "dias_cotizacion"] == 120)
            p.caso("días hasta la cotización de marzo y junio, cada una con su foto", "dias_cotizacion_mar" in a and fila["dias_cotizacion_mar"] == 14 and fila["dias_cotizacion_jun"] == 14)
            p.caso("puntos a menos de 500 m", a["puntos_interes_500m"].ge(0).all() and pd.api.types.is_integer_dtype(a["puntos_interes_500m"]))
            # Exclusiones: cada plantado cae en su marca y sale de la decisión.
            for clave, marca in PLANTADOS:
                p.caso(f"{clave} lleva {marca}", bool(a.loc[cp.ID[clave], marca]))
                p.caso(f"{clave} sale de la base de decisión", not bool(a.loc[cp.ID[clave], "base_decision"]))
            p.caso("un piso normal entra en la decisión", bool(fila["base_decision"]))
            # Base de comparación: lleva habitaciones, no hoteles, y exige 180 días.
            p.caso("la privada entra en la comparación", bool(a.loc[cp.ID["privada"], "base_comparacion"]))
            p.caso("la compartida entra en la comparación", bool(a.loc[cp.ID["compartida"], "base_comparacion"]))
            p.caso("la de hotel no entra", not bool(a.loc[cp.ID["hotel"], "base_comparacion"]))
            p.caso("un piso con 100 días no entra", not bool(fila["base_comparacion"]))
            p.caso("precio de vivienda de la privada", a.loc[cp.ID["privada"], "precio_vivienda_comparacion_eur"] == 50 * 2 * 0.5)
            p.caso("precio de vivienda de la compartida", a.loc[cp.ID["compartida"], "precio_vivienda_comparacion_eur"] == 50 * 3 * 0.5)

            b = pd.read_parquet(pro / "analisis_barrios.parquet").set_index("barrio")
            p.caso("una fila por barrio", len(b) == 11)
            p.caso("los recuentos suman la foto", b["anuncios"].sum() == n)
            p.caso("las licencias suman las de la fuente", b["licencias"].sum() == 6 and b.loc["Ribera", "licencias"] == 2)
            p.caso("un barrio sin licencias tiene cero", b.loc["Llano", "licencias"] == 0, str(b.loc["Llano", "licencias"]))
            p.caso("lo oficial viene con su origen", b.loc["San Andrés", "precio_m2_eur"] == 5000 and b.loc["San Andrés", "precio_m2_origen"] == "distrito")
            e = pd.read_parquet(pro / "evolucion_oferta.parquet")
            p.caso("cuatro fotos por barrio", len(e) == 44, str(len(e)))
            p.caso("cada foto suma sus anuncios", e.groupby("foto")["anuncios"].sum().nunique() == 1)
            s = pd.read_parquet(pro / "estacionalidad_resenas.parquet")
            p.caso("las reseñas suman", s["resenas"].sum() == cp.gz_lineas(caso / "data" / "raw" / "reviews_fechas_2026-09-17.csv.gz"))
            d = pd.read_parquet(pro / "disponibilidad_futura.parquet")
            cal = pd.read_parquet(pro / "calendario_corregido.parquet")
            p.caso("los días libres suman los del calendario", d["dias_libres"].sum() == int(cal["available"].sum()))
            p.caso("los días suman el calendario", d["dias_calendario"].sum() == len(cal))
            p.caso("una fila por anuncio y mes", not d.duplicated(["id", "mes"]).any())

            j = cp.leer(caso, "transformacion-datos.json")
            p.caso("el JSON no para sin controles", j["resultado"]["estado"] in ("OK", "AVISO"), j["resultado"]["resumen"])
            p.caso("cinco salidas", len(j["salidas"]) == 5)
            p.caso("todas las validaciones pasan", all(v["resultado"] == "pasa" for v in j["validaciones"]), str([v for v in j["validaciones"] if v["resultado"] != "pasa"]))
            p.caso("cada exclusión cruzada con los más alquilados", all("mas_alquilados_pct" in x and "quita_pct" in x for x in j["exclusiones"]))
            # Si una regla quita más de los más alquilados que del total, tiene que decirlo: se comprueba con la cuenta rehecha.
            fuera = a.loc[a["tipo_alquiler"].eq("Entire home/apt") & a["lado_centro"].eq("fuera") & a["ocupacion_dias"].gt(0)]
            fila180 = next(x for x in j["exclusiones"] if x["clase"] == "comp_excl_menos_de_180_dias")
            p.caso("el universo de la regla de los 180 días", abs(fila180["quita_pct"] - 100 * fuera["comp_excl_menos_de_180_dias"].mean()) < 0.01, str(fila180))
            p.caso("la marca sale de comparar las dos partes", fila180["deja_fuera_a_los_mas_alquilados"] == (fila180["mas_alquilados_pct"] > fila180["quita_pct"]))
            p.caso("el embudo acaba en la base", j["embudo"][-1]["quedan"] == int(a["base_decision"].sum()), str(j["embudo"][-1]))
            p.caso("el control trae las doce variantes", "variantes_por_barrio" in j["control_grupo"])
            g = j["control_grupo"]
            p.caso("el control trae las cinco pruebas de cada barrio", set(g.get("pruebas_por_barrio", {"x": 1})) == set(g["grupo"]), str(g.get("pruebas_por_barrio")))
            p.caso("cada barrio del grupo tiene su clase", set(g["firmes"]) | set(g.get("con_aviso", ["x"])) | set(g["segunda_linea"]) == set(g["grupo"]))
            registro = (caso / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
            p.caso("las columnas nuevas tienen ficha", "anuncios_anfitrion" in registro and "dias_cotizacion" in registro)
            riesgos = caso / "config" / "negocio" / "03_riesgos_de_calidad.md"
            antes = riesgos.read_bytes()
            riesgos.write_text("no tocar\n", encoding="utf-8")
            r_sin = cp.lanzar(caso, "transformacion_datos.py", "--sin-riesgos")
            p.caso("con --sin-riesgos acaba bien", r_sin.returncode == 0, r_sin.stderr[-500:])
            p.caso("con --sin-riesgos no reescribe los riesgos", riesgos.read_text(encoding="utf-8") == "no tocar\n")
            p.caso("con --sin-riesgos no los anuncia", not any("riesgos" in x for x in cp.leer(caso, "transformacion-datos.json")["resultado"]["artefactos"]))
            riesgos.write_bytes(antes)
            informe = (caso / "informes" / "transformacion-datos.md").read_text(encoding="utf-8")
            for apartado in APARTADOS:
                p.caso(f"el informe trae {apartado}", apartado in informe)
            p.caso("deja los riesgos", (caso / "config" / "negocio" / "03_riesgos_de_calidad.md").exists())

            # Rojo a propósito: un grupo esperado que no sale tiene que parar sin guardar y comparar con intervalo.
            for f in pro.glob("analisis_*.parquet"):
                f.unlink()
            ruta = caso / "scripts" / "decisiones_correccion.json"
            dec = json.loads(ruta.read_text(encoding="utf-8"))
            dec["controles"]["grupo_esperado"] = ["Barrio que no existe"]
            ruta.write_text(json.dumps(dec, ensure_ascii=False), encoding="utf-8")
            r2 = cp.lanzar(caso, "transformacion_datos.py")
            j2 = cp.leer(caso, "transformacion-datos.json")
            p.caso("si el grupo cambia, para", j2["resultado"]["estado"] == "PARADO", j2["resultado"]["estado"])
            p.caso("parado no guarda tablas", not (pro / "analisis_anuncios.parquet").exists())
            p.caso("parado compara con intervalo", "comparacion_con_intervalo" in j2["control_grupo"])
            p.caso("parar no es un fallo técnico", r2.returncode == 0, r2.stderr[-500:])
            dec["controles"]["grupo_esperado"] = None
            dec["controles"]["base_comparacion_esperada"] = 1
            ruta.write_text(json.dumps(dec, ensure_ascii=False), encoding="utf-8")
            cp.lanzar(caso, "transformacion_datos.py")
            j3 = cp.leer(caso, "transformacion-datos.json")
            p.caso("una base de comparación que no cuadra da rojo", j3["resultado"]["estado"] == "PARADO", j3["resultado"]["estado"])
    except FileNotFoundError as error:
        p.caso("los scripts existen", False, str(error))
    return p.fin()


if __name__ == "__main__":
    sys.exit(principal())
