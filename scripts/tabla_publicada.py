"""Deja en data/publicado/, solo en local, la tabla con la que se rehacen las cifras de portada sin descargar nada.

Lee data/processed/analisis_anuncios.parquet y escribe una fila por piso fuera del centro histórico que entra en
alguna de las variantes de las reglas §3. No lleva número de anuncio, coordenadas, recuento de anuncios por anfitrión, precio
ni ocupación: solo el barrio, las habitaciones, marcas de sí o no y cifras calculadas. Las filas van barajadas. Un barrio con
menos de 20 pisos en la tabla sale como «otros», porque ninguna variante puede ordenarlo. El criterio está en docs/datos.md.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/tabla_publicada.py
"""
import pandas as pd

import calidad_datos as cd
import indicadores as ind
import reglas_caso as rc

SALIDA = rc.CASO / "data" / "publicado" / "pisos_fuera_del_centro.csv.gz"
OTROS = "otros"
MINIMO_BARRIO = min(cd.MIN_VARIANTE)
ESTANCIA_MAXIMA = max(cd.ESTANCIAS)
FOTOS = {"sep": ("precio", "dias_cotizacion"), "mar": ("p_mar", "dias_cotizacion_mar"), "jun": ("p_jun", "dias_cotizacion_jun")}


def construir(a, dec):
    """Monta la tabla publicable a partir de la tabla de análisis por anuncio."""
    reglas = dec["pruebas_del_grupo"]
    quitados = a["excl_cero_banos"] | a["excl_no_vivienda"] | a["excl_tamano_incoherente"]
    L = ind.vista(a)
    filas = cd.mascara_fija(L, quitados, cero=True) & L["estancia"].le(ESTANCIA_MAXIMA)
    alguna_foto = pd.concat([L[c].between(20, 1000) for c, _ in FOTOS.values()], axis=1).any(axis=1)
    L, x = L.loc[filas & alguna_foto], a.loc[filas & alguna_foto]
    t = pd.DataFrame({"barrio": L["barrio"], "dormitorios": L["bedrooms"].astype("int64"), "estancia_hasta_3": L["estancia"].le(3).astype("int64"),
                      "temporada": L["temporada"].astype("int64"), "anfitrion_10_o_mas": L["anuncios_anfitrion"].ge(reglas["anfitrion_anuncios"]).astype("int64")})
    for foto, (precio, dias) in FOTOS.items():
        t[f"lejana_{foto}"] = L[dias].gt(reglas["cotizacion_dias"]).astype("int64")
        t[f"rent_{foto}_pct"] = cd.rentabilidad(L, precio).where(L[precio].between(20, 1000)).round(4)
    t["ingreso_sep_eur"] = x["ingreso_anual_eur"].where(L["precio"].between(20, 1000)).round(2)
    t["compra_eur"] = x["compra_valoraciones_eur"].round(2)
    pocos = t["barrio"].map(t["barrio"].value_counts()).lt(MINIMO_BARRIO)
    t.loc[pocos, "barrio"] = OTROS
    return t.sample(frac=1, random_state=cd.SEMILLA).reset_index(drop=True)


if __name__ == "__main__":
    tabla = construir(pd.read_parquet(rc.PROCESADO / "analisis_anuncios.parquet"), rc.leer_decisiones())
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(SALIDA, index=False, compression={"method": "gzip", "mtime": 0})
    print(f"Tabla escrita: {SALIDA.name}, {len(tabla)} filas, {tabla['barrio'].nunique()} barrios contando «{OTROS}».")
