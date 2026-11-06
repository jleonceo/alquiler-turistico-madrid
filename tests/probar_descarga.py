"""Prueba que scripts/descargar_datos.py quita lo personal y para ante una huella que no es la esperada. No descarga nada."""
import sys
import tempfile
from pathlib import Path

import pandas as pd

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
import descargar_datos as dd  # noqa: E402

FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[:300]}"))
    if not bien:
        FALLOS.append(nombre)


foto = pd.DataFrame({"id": ["1", "2"], "listing_url": ["https://www.airbnb.es/rooms/1", "https://www.airbnb.es/rooms/2"], "host_name": ["Ana", "Luis"],
                     "license": ["ESFCTU0000280000000000000000000000000VT-1", "Exempt - seasonal"], "price": ["$50.00", "$70.00"]})
limpia = dd.limpiar_foto(foto)
caso("sale el enlace y el nombre", not ({"listing_url", "host_name", "license"} & set(limpia.columns)), list(limpia.columns))
caso("la licencia queda como tipo", limpia["licencia_nacional"].tolist()[0] == "TU" and limpia["licencia_exencion"].tolist()[1] == "temporada", limpia.to_dict())
caso("la tabla limpia pasa", not dd.fallos_de_foto(limpia), dd.fallos_de_foto(limpia))
# Rojos: la tabla original y un enlace colado en otra columna tienen que caer.
caso("rojo con la tabla original", dd.fallos_de_foto(foto))
colada = limpia.assign(price=["https://www.airbnb.es/rooms/1", "$70.00"])
caso("rojo con un enlace colado", any("enlace" in x for x in dd.fallos_de_foto(colada)))
colada = limpia.assign(price=["ESFCTU000028", "$70.00"])
caso("rojo con un número de licencia colado", any("licencia" in x for x in dd.fallos_de_foto(colada)))

with tempfile.TemporaryDirectory() as t:
    Path(t, "a.csv").write_text("x\n", encoding="utf-8")
    dd.ORIGINAL = Path(t, "original")
    try:
        dd.traer("a.csv", "http://sin-usar", "0" * 64, t)
        paro = False
    except SystemExit:
        paro = True
    caso("rojo si la huella no es la del fichero analizado", paro)
    dd.traer("a.csv", "http://sin-usar", dd.huella(Path(t, "a.csv")), t)
    caso("sigue si la huella coincide", Path(t, "original", "a.csv").exists())

print("VERDE" if not FALLOS else f"ROJO: {FALLOS}")
sys.exit(1 if FALLOS else 0)
