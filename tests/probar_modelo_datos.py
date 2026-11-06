"""Prueba scripts/modelo_datos.py en el caso pequeño: comprueba el diseño y no da nunca la aprobación por hecha."""
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cadena_de_prueba as cp  # noqa: E402


def principal():
    """Recorre los casos del modelo."""
    p = cp.Prueba()
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            caso, r = cp.montar(tmp, "modelo_datos.py")
            p.caso("el modelo acaba bien", r.returncode == 0, r.stderr[-800:])
            j = cp.leer(caso, "modelado-datos.json")
            p.caso("sin la línea de aprobación queda sin aprobar", j["aprobado"]["aprobado"] is False)
            p.caso("la orden de seguir queda escrita", bool(j["seguir_sin_aprobacion"]))
            p.caso("no para: la cadena sigue y lo avisa", j["resultado"]["estado"] == "AVISO", j["resultado"]["estado"])
            p.caso("hay plan de cruces", len(j["plan_cruces"]) >= 6)
            repetidas = [t["tabla"] for t in j["tablas"] if t["clave_grano"] and not t["clave_unica"]]
            p.caso("cada clave de grano es única", not repetidas, str(repetidas))
            exclusiones = {e["clase"]: e for e in j["registro_exclusiones"]}
            p.caso("el registro cuenta los cero baños", exclusiones["excl_cero_banos"]["filas"] == 1, str(exclusiones.get("excl_cero_banos")))
            p.caso("cada exclusión dice si se recupera", all(e["recuperable"] for e in j["registro_exclusiones"]))
            md = caso / "config" / "modelo" / "modelo-datos.md"
            md.write_text(md.read_text(encoding="utf-8") + "\nAprobado: sí · Persona · 2026-11-06\n", encoding="utf-8")
            r2 = cp.lanzar(caso, "modelo_datos.py")
            j2 = cp.leer(caso, "modelado-datos.json")
            p.caso("con la línea de aprobación queda aprobado", r2.returncode == 0 and j2["aprobado"]["aprobado"] is True and j2["aprobado"]["fecha"] == "2026-11-06")
            # Una clave repetida en una tabla tiene que dar rojo.
            ruta = caso / "data" / "processed" / "barrios_corregido.parquet"
            t = pd.read_parquet(ruta)
            pd.concat([t, t.head(1)]).to_parquet(ruta)
            cp.lanzar(caso, "modelo_datos.py")
            j3 = cp.leer(caso, "modelado-datos.json")
            fila = next(x for x in j3["tablas"] if x["tabla"] == "dim_barrio")
            p.caso("una clave repetida se detecta", fila["clave_unica"] is False and fila["filas_repetidas"] == 1, json.dumps(fila)[:200])
    except FileNotFoundError as error:
        p.caso("los scripts existen", False, str(error))
    return p.fin()


if __name__ == "__main__":
    sys.exit(principal())
