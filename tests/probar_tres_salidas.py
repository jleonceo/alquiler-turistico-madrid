"""Comprueba que el informe ejecutivo, el informe final, la interpretación y el cuadro de mando dan la misma recomendación y las mismas cifras.

Las cifras se leen de informes/indicadores.json y se escriben con la misma función que las salidas: esta prueba no lleva ninguna
escrita a mano. Lee las salidas reales de informes/. Sale con 0 si pasa y con 1 si falla.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_tres_salidas.py
"""
import json
import re
import sys
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
from cifras_informes import numero  # noqa: E402

INFORMES = CASO / "informes"
FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[:300]}"))
    if not bien:
        FALLOS.append(nombre)


def visible(ruta):
    """Texto visible de un HTML generado, sin estilos, guiones ni dibujos."""
    h = ruta.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>|<script.*?</script>|<svg.*?</svg>", " ", h, flags=re.S)))


def faltan(texto, cifras):
    """Da las cifras que un texto no lleva, cada una como número suelto."""
    return [c for c in cifras if not re.search(rf"(?<![\d.,]){re.escape(c)}(?![\d])", texto)]


def lista_comun(j):
    """Reúne, con el formato de las salidas, las cifras que las tres salidas tienen que dar iguales."""
    p2, p3 = j["preguntas"][1], j["preguntas"][2]
    r, rango, pl = j["recomendacion"], p3["rango_de_rentabilidad_del_grupo_firme"], j["licencias_y_registro"]["planta_baja"]
    so = {f["barrio"]: f["pisos_fuera_sin_ocupacion_pct"] for f in p3["fichas_del_grupo"]}
    puesto = {x["barrio"]: x["puesto"] for x in p2["con_un_ano_o_mas"]["barrios"]}
    q = p2["que_ordena_la_lista"]
    return [numero(r["pisos"]), numero(r["rentabilidad_sin_descuento_pct"], 1) + " %", numero(r["rentabilidad_con_descuento_pct"], 1) + " %", numero(rango["minimo"], 1) + " %", numero(rango["maximo"], 1) + " %",
            numero(r["compra_sin_descuento_eur"]) + " €", numero(r["compra_con_descuento_eur"]) + " €", numero(r["ingreso_anual_eur"]) + " €", numero(pl["licencias"]), numero(pl["de"]), numero(pl["firmes"]["licencias"]), numero(pl["firmes"]["de"]),
            numero(p2["cuartil_bajo_de_toda_la_base"], 2) + " %", numero(so["Numancia"], 1), numero(so["San Diego"], 1), numero(so["Ventas"], 1), numero(p3["pisos_fuera_sin_ocupacion"]["pct"], 1),
            f"{numero(puesto['San Diego'])}.ª", numero(p2["con_un_ano_o_mas"]["barrios_comparados"]), numero(q["rentabilidad_con_ocupacion"], 2), numero(q["m2_baratos"]["mediana_pct"], 1) + " %"]


def principal():
    """Compara las salidas entre sí y contra el JSON."""
    j = json.loads((INFORMES / "indicadores.json").read_text(encoding="utf-8"))
    s = {"ejecutivo": visible(INFORMES / "informe_ejecutivo.html"), "final": visible(INFORMES / "informe_final.html"),
         "interpretación": re.sub(r"\s+", " ", (INFORMES / "interpretacion_resultados.md").read_text(encoding="utf-8").split("## Inventario de evidencias")[0]), "cuadro": visible(INFORMES / "cuadro_mando.html")}
    cifras = lista_comun(j)
    # Caso que tiene que fallar: un texto sin una cifra se detecta, y una cifra dentro de otra mayor no cuenta.
    caso("una cifra que falta se detecta", faltan("nada", cifras[:1]) == cifras[:1])
    caso("una cifra dentro de otra no cuenta", faltan("1.256 pisos", ["256"]) == ["256"])
    for nombre, t in s.items():
        caso(f"{nombre}: da todas las cifras comunes", not faltan(t, cifras), faltan(t, cifras))
        caso(f"{nombre}: recomienda hasta 2 habitaciones", "hasta 2 habitaciones" in t)
        caso(f"{nombre}: nombra los tres firmes en el mismo orden", "Ventas, Numancia y San Diego" in t)
        caso(f"{nombre}: la cifra sin descuento va antes que la de con descuento", "12,1 %" in t and "16,2 %" in t and t.index("12,1 %") < t.index("16,2 %"))
        caso(f"{nombre}: no recomienda solo 1 y 2 habitaciones", "pisos de 1 y 2 habitaciones en" not in t)
    a = json.loads((INFORMES / "informe_ejecutivo.json").read_text(encoding="utf-8"))["se_pide"]
    b = [x["nombre"] for x in json.loads((INFORMES / "informe_final_rastro.json").read_text(encoding="utf-8"))["acciones"]]
    caso("las acciones son las mismas", a == b, (a, b))
    caso("la primera acción es la de planta", "planta" in a[0].lower(), a)
    for nombre in ("interpretación", "cuadro"):
        caso(f"{nombre}: nombra la primera acción", a[0] in s[nombre], a[0])
    print(f"{len(FALLOS)} fallos")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
