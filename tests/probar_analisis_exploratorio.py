"""Prueba scripts/analisis_exploratorio.py: la tipificación, las señales, Pareto y el caso pequeño entero."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))
sys.path.insert(0, str(CARPETA.parent / "scripts"))
import cadena_de_prueba as cp  # noqa: E402

APARTADOS = ["Resumen ejecutivo", "Contexto", "Visión general", "Variables numéricas", "Variables categóricas", "Análisis temporal", "Hallazgos principales", "Alertas y limitaciones",
             "Hipótesis y preguntas abiertas", "Observaciones de la persona", "Comprobaciones aplicadas", "Parámetros usados", "Datos personales", "Siguiente paso"]


def pruebas_de_funciones(p, eda):
    """Comprueba las funciones sueltas contra cuentas hechas a mano."""
    d = pd.DataFrame({"id": range(1, 101), "latitud": [40.0 + i / 1000 for i in range(100)], "precio_eur": [10.5 + i for i in range(100)], "huespedes": [1 + i % 3 for i in range(100)],
                      "barrio": [f"b{i}" for i in range(100)], "tipo_alquiler": ["a", "b"] * 50, "base_decision": [True, False] * 50})
    t = {x["columna"]: x["tipo"] for x in eda.tipificar(d)}
    p.caso("el id es identificador", t["id"] == "identificador")
    p.caso("la coordenada no es magnitud", t["latitud"] == "identificador")
    p.caso("continua", t["precio_eur"] == "continua")
    p.caso("discreta", t["huespedes"] == "discreta", t["huespedes"])
    p.caso("alta cardinalidad", t["barrio"] == "alta_cardinalidad")
    p.caso("categórica", t["tipo_alquiler"] == "categorica")
    p.caso("booleana", t["base_decision"] == "booleana")

    e = eda.estadisticos(pd.Series([1.0, 2.0, 3.0, 4.0, None]))
    p.caso("conteo y nulos", e["conteo"] == 4 and e["nulos"] == 1)
    p.caso("mediana y cuartil", e["mediana"] == 2.5 and e["p25"] == 1.75, str(e))
    s = eda.estadisticos(pd.Series([1.0] * 90 + [1000.0] * 10))
    p.caso("señal media lejos de la mediana", "media_lejos_de_la_mediana" in s["senales"], str(s["senales"]))
    p.caso("señal cuartiles iguales", "cuartiles_iguales" in s["senales"])
    p.caso("señal binaria", "dos_valores" in s["senales"])
    # ROJO a propósito: una variable corriente no da ninguna señal.
    corriente = eda.estadisticos(pd.Series(range(50, 101), dtype="float64"))
    p.caso("una variable corriente no da señal", corriente["senales"] == [], str(corriente["senales"]))

    d = pd.DataFrame({"e": ["a", "b", "c", "d", "e"], "m": [80.0, 10.0, 5.0, 3.0, 2.0]})
    r = eda.pareto(d, "e", "m")
    p.caso("elementos que suman el 80 %", r["pct_elementos_80"] == 20.0, str(r))
    p.caso("clases ABC", r["clases"]["A"]["elementos"] == 1 and r["clases"]["B"]["elementos"] == 2 and r["clases"]["C"]["elementos"] == 2, str(r["clases"]))
    p.caso("conserva quién", r["primeros"][0]["elemento"] == "a")

    # ROJO a propósito: una comprobación sin estado no se da por hecha.
    p.caso("detecta una comprobación sin estado", eda.comprobaciones_sin_estado([{"comprobacion": "1", "estado": "aplicada"}], 2) != [])
    p.caso("acepta los tres estados", eda.comprobaciones_sin_estado([{"comprobacion": "1", "estado": "no_aplica"}, {"comprobacion": "2", "estado": "aplicada_con_resultado"}], 2) == [])


def caso_entero(p):
    """Monta el caso pequeño y lanza el exploratorio."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        caso, r = cp.montar(tmp, "transformacion_datos.py")
        p.caso("el caso pequeño se monta", r.returncode == 0, r.stderr[-500:])
        origen = CARPETA.parent
        (caso / "assets").mkdir(exist_ok=True)
        for nombre in ("graficos.py", "estilo.css"):
            shutil.copy(origen / "assets" / nombre, caso / "assets" / nombre)
        shutil.copy(origen / "scripts" / "analisis_exploratorio.py", caso / "scripts" / "analisis_exploratorio.py")
        huellas = cp.huellas(caso)
        r0 = cp.lanzar(caso, "analisis_exploratorio.py")
        p.caso("acaba bien", r0.returncode == 0, r0.stderr[-1500:])
        for tabla in ("analisis_anuncios", "analisis_barrios"):
            j = cp.leer(caso, f"analisis-exploratorio__{tabla}.json")
            p.caso(f"{tabla}: estado", j["resultado"]["estado"] in ("OK", "AVISO"), j["resultado"]["resumen"])
            p.caso(f"{tabla}: fecha_datos", j["fecha_datos"] == "2026-09-17")
            p.caso(f"{tabla}: diecisiete comprobaciones", len(j["comprobaciones"]) == 17, str(len(j["comprobaciones"])))
            p.caso(f"{tabla}: siguiente paso", j["siguiente_paso"] in ("con_esto_basta", "hace_falta_modelar", "volver_a_limpiar", "falta_un_dato"))
            p.caso(f"{tabla}: tipifica todas", len(j["tipificacion"]) == j["vision_general"]["columnas"])
            p.caso(f"{tabla}: separa hallazgos", all(x["id"].startswith("H-") for x in j["hallazgos"]) and all(x["id"].startswith("A-") for x in j["alertas"]) and all(x["id"].startswith("Hi-") for x in j["hipotesis"]))
            html = (caso / "informes" / f"analisis-exploratorio__{tabla}.html").read_text(encoding="utf-8")
            posiciones = [html.find(f">{a}<") for a in APARTADOS]
            p.caso(f"{tabla}: apartados en orden", -1 not in posiciones and posiciones == sorted(posiciones), str(posiciones))
            p.caso(f"{tabla}: lleva gráficos", "<svg" in html)
        j = cp.leer(caso, "analisis-exploratorio__analisis_anuncios.json")
        p.caso("las dos bases", set(j["bases"]) == {"decision", "comparacion"})
        p.caso("lo que espera el paso siguiente", set(j["para_el_paso_siguiente"]) == {"rentabilidad_por_dormitorios_y_barrio", "ocupacion_con_su_tope", "compra_y_alquiler_por_distrito"})
        p.caso("cifras de control por base", j["bases"]["decision"]["filas"] >= 0 and "ingreso_total_eur" in j["bases"]["decision"])
        p.caso("los datos no cambian", cp.huellas(caso) == huellas)

        # ROJO a propósito: con la transformación parada no se analiza.
        ruta = caso / "informes" / "transformacion-datos.json"
        t = json.loads(ruta.read_text(encoding="utf-8"))
        t["resultado"]["estado"] = "PARADO"
        ruta.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
        cp.lanzar(caso, "analisis_exploratorio.py")
        p.caso("con la transformación parada, para", cp.leer(caso, "analisis-exploratorio__analisis_anuncios.json")["resultado"]["estado"] == "PARADO")


def principal():
    """Recorre las funciones y el caso pequeño."""
    p = cp.Prueba()
    try:
        import analisis_exploratorio as eda
    except ModuleNotFoundError as error:
        p.caso("el script existe", False, str(error))
        return p.fin()
    pruebas_de_funciones(p, eda)
    caso_entero(p)
    return p.fin()


if __name__ == "__main__":
    sys.exit(principal())
