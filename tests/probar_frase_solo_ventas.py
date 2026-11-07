"""Comprueba por otro camino la frase del límite de la prueba de ocupación: contar además los pisos sin ocupación ni precio deja solo a Ventas como recomendado.

La frase viene de la lectura aprobada y no tiene clave en informes/indicadores.json. Esta prueba la rehace sobre
data/processed/analisis_anuncios.parquet con las funciones de tests/probar_indicadores_por_otro_camino.py: repite las 12
variantes de la prueba de los pisos sin ocupación, añadiendo con rentabilidad cero los que tampoco tienen precio en esa foto.
Sale con 0 si la frase se sostiene y con 1 si no. Esta prueba abre los datos reales: su trabajo es esa comprobación.
"""
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probar_indicadores_por_otro_camino as o  # noqa: E402


def variantes_con_vacios(t, contar_sin_precio):
    """Cuenta las 12 variantes con los pisos sin ocupación a cero y, si se pide, también los que no tienen precio en esa foto."""
    veces = Counter()
    base = [f for f in t if o.fija(f, cero=True)]
    for est in (3, 6):
        for col in ("precio_mar_eur", "precio_jun_eur", "precio_eur"):
            g = defaultdict(list)
            for f in base:
                if f["estancia_noches"] is None or f["estancia_noches"] > est:
                    continue
                if o.en_precio(f, col):
                    g[f["barrio"]].append(o.rent(f, col))
                elif contar_sin_precio and f["ocupacion_dias"] == 0 and f[col] is None:
                    g[f["barrio"]].append(0.0)
            for minimo in (30, 20):
                med = {b: statistics.median(v) for b, v in g.items() if len(v) >= minimo}
                corte = o.cuantil(list(med.values()), 0.75)
                veces.update(b for b, v in med.items() if v >= corte)
    return veces


def principal():
    """Rehace la prueba con y sin los pisos sin precio y mira qué recomendados siguen."""
    j = json.loads((o.CASO / "informes" / "indicadores.json").read_text(encoding="utf-8"))
    recomendados = j["preguntas"][1]["recomendados"]
    t = o.leer()
    # Caso que tiene que coincidir con el JSON: sin añadir nada, la prueba da sus variantes y todos los recomendados la aguantan.
    sin_anadir = variantes_con_vacios(t, False)
    o.caso("sin añadir pisos sale la prueba del JSON", dict(sorted(sin_anadir.items())), j["preguntas"][1]["pruebas"]["variantes_por_prueba"]["sin_ocupacion_como_cero"])
    con_vacios = variantes_con_vacios(t, True)
    print({b: con_vacios[b] for b in recomendados})
    o.caso("solo Ventas sigue en la lista", sorted(b for b in recomendados if con_vacios[b] >= 7), ["Ventas"])
    return 1 if o.FALLOS else 0


if __name__ == "__main__":
    sys.exit(principal())
