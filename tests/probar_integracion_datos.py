"""Prueba scripts/integracion_datos.py en el caso pequeño: filas y sumas iguales, y parada si el maestro repite clave."""
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cadena_de_prueba as cp  # noqa: E402


def principal():
    """Recorre los casos de los cruces."""
    p = cp.Prueba()
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            caso, r = cp.montar(tmp, "integracion_datos.py")
            p.caso("los cruces acaban bien", r.returncode == 0, r.stderr[-800:])
            pro = caso / "data" / "processed"
            a = pd.read_parquet(pro / "anuncios_integrado.parquet")
            sep = pd.read_parquet(pro / "listings_2026-09-17_corregido.parquet")
            p.caso("los anuncios no ganan ni pierden filas", len(a) == len(sep) and a["id"].is_unique)
            p.caso("la suma del precio no cambia", abs(a["price"].sum() - sep["price"].sum()) < 0.005)
            p.caso("trae la estancia del calendario", a.loc[a["id"].eq(cp.ID["estancia"]), "estancia_calendario"].iloc[0] == 2)
            p.caso("trae el precio de junio", a["precio_jun"].notna().any())
            b = pd.read_parquet(pro / "barrios_integrado.parquet").set_index("barrio")
            p.caso("los barrios no ganan filas", len(b) == 11, str(len(b)))
            p.caso("Concepción casa por su equivalencia", b.loc["Concepción", "m2_barrio"] == 4400, str(b.loc["Concepción", "m2_barrio"]))
            p.caso("San Andrés no tiene pareja propia", pd.isna(b.loc["San Andrés", "m2_barrio"]))
            p.caso("San Andrés tiene su distrito", b.loc["San Andrés", "m2_distrito"] == 5000)
            p.caso("las licencias se agregan sin perder ninguna", b["licencias"].sum() == 6, str(b["licencias"].sum()))
            j = cp.leer(caso, "integracion-datos.json")
            p.caso("todos los cruces hechos", all(c["hecho"] for c in j["cruces"]) and len(j["cruces"]) >= 6)
            p.caso("filas iguales en cada cruce", all(c["filas_antes"] == c["filas_despues"] for c in j["cruces"]))
            p.caso("las sumas de control coinciden", all(s["coincide"] for c in j["cruces"] for s in c["sumas_control"]))
            informe = (caso / "informes" / "integracion-datos.md").read_text(encoding="utf-8")
            for apartado in ["## Fuente", "## Resumen", "## Auditoría previa", "## Control posterior", "## Huérfanas y repetidas", "## Datos personales", "## Límites"]:
                p.caso(f"el informe trae {apartado}", apartado in informe)
            # Rojo a propósito: un barrio repetido en el maestro multiplicaría los anuncios.
            ruta = pro / "barrios_corregido.parquet"
            t = pd.read_parquet(ruta)
            pd.concat([t, t.head(1)]).to_parquet(ruta)
            (pro / "anuncios_integrado.parquet").unlink()
            (pro / "barrios_integrado.parquet").unlink()
            r2 = cp.lanzar(caso, "integracion_datos.py")
            j2 = cp.leer(caso, "integracion-datos.json")
            p.caso("un maestro repetido para los cruces", j2["resultado"]["estado"] == "PARADO", j2["resultado"]["estado"])
            p.caso("parado no deja dataset", not (pro / "anuncios_integrado.parquet").exists())
            p.caso("parar no es un fallo técnico", r2.returncode == 0, r2.stderr[-500:])
    except FileNotFoundError as error:
        p.caso("los scripts existen", False, str(error))
    return p.fin()


if __name__ == "__main__":
    sys.exit(principal())
