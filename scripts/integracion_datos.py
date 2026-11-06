"""Cruces del caso: une las tablas corregidas con el plan de informes/modelado-datos.json, de dos en dos y con sus controles.

Deja data/processed/barrios_integrado.parquet y data/processed/anuncios_integrado.parquet solo si todos los cruces pasan.
Escribe informes/integracion-datos.json y, generado de él, informes/integracion-datos.md, también cuando para.

Se lanza después de scripts/modelo_datos.py.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/integracion_datos.py
"""
import json

import pandas as pd

import calidad_datos as cd
import reglas_caso as rc

# ---------------------------------------------------------------------------
# 1. Configuración
# ---------------------------------------------------------------------------

SKILL = "integracion-datos"
VERSION = "06/10/2026 (SC-63)"
SCRIPT = "scripts/integracion_datos.py"
VALIDAR = {"1:1": "one_to_one", "N:1": "many_to_one"}


class Parada(Exception):
    """Un cruce no pasa sus controles: se para sin guardar."""


# ---------------------------------------------------------------------------
# 2. Un cruce con sus controles
# ---------------------------------------------------------------------------

def auditar(izq, der, a, b, plan):
    """Cuenta repetidas, nulas, formato y huérfanas sobre las tablas enteras, antes de cruzar."""
    claves_i, claves_d = set(izq[a].dropna()), set(der[b].dropna())
    repetidas_der = der.loc[der[b].duplicated(keep=False), b]
    repetidas_izq = izq.loc[izq[a].duplicated(keep=False), a] if plan["cardinalidad"] == "1:1" else izq.iloc[0:0][a]
    return {"repetidas_maestro": {"claves": int(repetidas_der.nunique()), "filas": len(repetidas_der)}, "repetidas_partida": {"claves": int(repetidas_izq.nunique()), "filas": len(repetidas_izq)},
            "claves_nulas": {"partida": int(izq[a].isna().sum()), "se_une": int(der[b].isna().sum())}, "formato_igual": str(izq[a].dtype) == str(der[b].dtype),
            "huerfanas_partida": {"claves": len(claves_i - claves_d), "filas": int((~izq[a].isin(claves_d)).sum())}, "huerfanas_maestro": {"claves": len(claves_d - claves_i)}}


def cruzar(izq, der, plan, nuevas):
    """Cruza por la izquierda con validate e indicator, y comprueba filas, huérfanas, nulos y sumas."""
    a, b = plan["clave_partida"][0], plan["clave_une"][0]
    fila = {"orden": plan["orden"], "partida": plan["partida"], "se_une": plan["se_une"], "clave": [a, b], "tipo_cruce": plan["tipo_cruce"], "cardinalidad_esperada": plan["cardinalidad"]}
    fila.update(auditar(izq, der, a, b, plan))
    fila.update(filas_antes=len(izq), filas_despues=None, sumas_control=[], hecho=False, motivo_parada=None)
    motivos = []
    if fila["repetidas_maestro"]["filas"]:
        motivos.append(f"el maestro repite {fila['repetidas_maestro']['claves']} claves")
    if fila["repetidas_partida"]["filas"]:
        motivos.append(f"la partida repite {fila['repetidas_partida']['claves']} claves en un cruce 1:1")
    if not fila["formato_igual"]:
        motivos.append("la clave tiene formato distinto a cada lado")
    if motivos:
        fila["motivo_parada"] = "; ".join(motivos)
        raise Parada(json.dumps(fila, ensure_ascii=False, default=str))
    # Las sumas de control se miden en el lado que trae la magnitud, antes de cruzar.
    antes = {m: float((izq[m] if m in izq else der[m]).sum()) for m in plan["magnitudes_control"]}
    df = izq.merge(der[[b, *nuevas]], how="left", left_on=a, right_on=b, validate=VALIDAR[plan["cardinalidad"]], indicator=True, suffixes=("", "_une"))
    conteo = df["_merge"].value_counts()
    con_pareja, solo_partida = int(conteo.get("both", 0)), int(conteo.get("left_only", 0))
    nulos = {c: {"huerfanas": int(df.loc[df["_merge"].eq("left_only"), c].isna().sum()), "del_maestro": int(df.loc[df["_merge"].eq("both"), c].isna().sum())} for c in nuevas}
    df = df.drop(columns=["_merge"] + ([f"{b}_une"] if f"{b}_une" in df else []))
    fila.update(filas_despues=len(df), con_pareja=con_pareja, solo_partida=solo_partida, nulos_nuevos=nulos, cardinalidad_observada=plan["cardinalidad"])
    for m, v in antes.items():
        d = float(df[m].sum())
        fila["sumas_control"].append({"magnitud": m, "antes": v, "despues": d, "coincide": abs(v - d) < 0.005})
    if len(df) != len(izq) or solo_partida != fila["huerfanas_partida"]["filas"] or not all(x["coincide"] for x in fila["sumas_control"]):
        fila["motivo_parada"] = "el cruce cambia filas o sumas, o las huérfanas no coinciden con las contadas antes"
        raise Parada(json.dumps(fila, ensure_ascii=False, default=str))
    fila["hecho"] = True
    return df, fila


# ---------------------------------------------------------------------------
# 3. Informe
# ---------------------------------------------------------------------------

def informe(s):
    """Genera el Markdown a partir del diccionario que se guarda en el JSON."""
    r = ["# Integración de datos · caso", "", "## Fuente", ""]
    r += [f"- Ejecución: {s['fecha_ejecucion']}.", f"- Con diseño: {s.get('con_diseno')}; {s.get('seguir_sin_aprobacion') or 'aprobado'}."]
    r += [f"- Entrada `{e['ruta']}`: huella {e['sha256']}." for e in s["entradas"]]
    r += ["", "## Resumen", "", s["resultado"].get("resumen", ""), "", "## Tablas y granularidad", "", "- `anuncios_integrado`: un anuncio de la foto de septiembre.", "- `barrios_integrado`: un barrio de Inside Airbnb.", "",
          "## Claves y cardinalidad esperada", ""]
    r += [f"- Cruce {c['orden']}: {c['partida']} con {c['se_une']}, {c['cardinalidad_esperada']}, por {c['clave']}." for c in s.get("cruces", [])]
    r += ["", "## Auditoría previa", ""]
    r += [f"- Cruce {c['orden']}: repetidas en el maestro {c['repetidas_maestro']['filas']}; nulas {c['claves_nulas']}; formato igual {c['formato_igual']}; huérfanas de la partida {c['huerfanas_partida']['filas']} filas; del maestro {c['huerfanas_maestro']['claves']} claves." for c in s.get("cruces", [])]
    r += ["", "## Cruce", ""] + [f"- Cruce {c['orden']}: {c.get('con_pareja')} con pareja y {c.get('solo_partida')} solo en la partida; hecho {c['hecho']}." for c in s.get("cruces", [])]
    r += ["", "## Control posterior", ""] + [f"- Cruce {c['orden']}: {c['filas_antes']} filas antes y {c['filas_despues']} después; sumas {[(x['magnitud'], x['antes'], x['despues'], x['coincide']) for x in c['sumas_control']]}." for c in s.get("cruces", [])]
    r += ["", "## Huérfanas y repetidas", ""] + [f"- Cruce {c['orden']}: nulos nuevos {c.get('nulos_nuevos')}." for c in s.get("cruces", [])]
    r += ["", "Los anuncios sin pareja en junio o en marzo se quedan con el precio vacío. Los anuncios de esas fotos que no están en septiembre no entran, porque el grano es la foto de septiembre (diseño, «Plan de cruces»).",
          "", "## Decisiones del usuario", "", "No hay ninguna sobre huérfanas.", "", "## Decisiones pendientes", "", "No hay." if not s["pendientes"] else str(s["pendientes"]), "",
          "## Dataset generado", ""]
    r += [f"- `{x['ruta']}`: {x['filas']} filas y {x['columnas']} columnas, huella {x['sha256']}." for x in s.get("salidas", [])] or ["No se generó: el cruce paró."]
    r += ["", "", "## Datos personales", "", rc.texto_personales("Los cruces arrastran las columnas de licencia tal como llegan: ningún valor sale al informe."), "", "## Límites", "",
          "- El cruce compara claves exactas; una clave que existe pero apunta a otra entidad no se detecta.", "- El mismo ente con dos claves en el maestro no se ve como repetido.",
          "- Si el maestro cambia con el tiempo, el cruce usa la versión que hay y no la vigente en la fecha de cada hecho.", "- Las sumas de control solo cubren las magnitudes declaradas en la configuración.", ""]
    return "\n".join(r)


# ---------------------------------------------------------------------------
# 4. Ejecución
# ---------------------------------------------------------------------------

def principal(s):
    """Hace los cruces del plan en orden y guarda solo si pasan todos."""
    modelado = json.loads((rc.INFORMES / "modelado-datos.json").read_text(encoding="utf-8"))
    correccion = json.loads((rc.INFORMES / "correccion-datos.json").read_text(encoding="utf-8"))
    s["con_diseno"] = True
    s["seguir_sin_aprobacion"] = modelado.get("seguir_sin_aprobacion")
    if modelado["resultado"]["estado"] in ("PARADO", "ERROR") or not (modelado["aprobado"]["aprobado"] or modelado.get("seguir_sin_aprobacion")):
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": "El diseño está parado o sin aprobar.", "artefactos": [], "siguiente": "modelado-datos"}
        return s
    plan = {c["orden"]: c for c in modelado["plan_cruces"]}
    tablas = {k: rc.PROCESADO / rc.CORREGIDA[k] for k in ("sep", "jun", "mar", "barrios", "oficial", "licencias", "calendario")}
    huellas = {x["tabla"]: x["sha256"] for x in correccion["salidas"]}
    s["entradas"] = [rc.entrada(r) for r in tablas.values()]
    distintas = [k for k, r in tablas.items() if cd.huella(r) != huellas.get(k)]
    s["huellas_distintas_a_la_correccion"] = distintas

    # 4.1 Lo que se une, en su grano: el calendario y las licencias se agregan antes de cruzar.
    b = pd.read_parquet(tablas["barrios"])
    of = pd.read_parquet(tablas["oficial"])
    of_b = of.loc[of["nivel"].eq("barrio"), ["clave", "cod", "m2_total", "sup_total", "ventas"]].rename(columns={"cod": "cod_oficial", "m2_total": "m2_barrio", "sup_total": "sup_barrio", "ventas": "ventas_barrio"})
    of_d = of.loc[of["nivel"].eq("distrito"), ["clave_distrito", "m2_total", "sup_total"]].rename(columns={"m2_total": "m2_distrito", "sup_total": "sup_distrito"})
    lic = pd.read_parquet(tablas["licencias"]).groupby("barrio", as_index=False).agg(licencias=("viviendas", "size"), viviendas_licencia=("viviendas", "sum"))
    cal = pd.read_parquet(tablas["calendario"], columns=["listing_id", "minimum_nights", "available"])
    cal_a = cal.groupby("listing_id", as_index=False).agg(estancia_calendario=("minimum_nights", "min"), dias_calendario=("minimum_nights", "size"))
    sep = pd.read_parquet(tablas["sep"])
    precios = {k: pd.read_parquet(tablas[k], columns=["id", "price"]).rename(columns={"price": f"precio_{k}"}) for k in ("jun", "mar")}
    s["cruces"] = []

    # 4.2 Los cruces, de dos en dos: el primero que falla para los siguientes.
    try:
        for orden, derecha, nuevas in ((1, of_b, ["cod_oficial", "m2_barrio", "sup_barrio", "ventas_barrio"]), (2, of_d, ["m2_distrito", "sup_distrito"]), (3, lic, ["licencias", "viviendas_licencia"])):
            b, fila = cruzar(b, derecha, plan[orden], nuevas)
            s["cruces"].append(fila)
        columnas_barrio = ["cod_oficial", "m2_barrio", "sup_barrio", "ventas_barrio", "m2_distrito", "sup_distrito", "toma_precio_de_distrito"]
        for orden, derecha, nuevas in ((4, b, columnas_barrio), (5, cal_a, ["estancia_calendario", "dias_calendario"]), (6, precios["jun"], ["precio_jun"]), (7, precios["mar"], ["precio_mar"])):
            sep, fila = cruzar(sep, derecha, plan[orden], nuevas)
            s["cruces"].append(fila)
    except Parada as parada:
        fila = json.loads(str(parada))
        s["cruces"].append(fila)
        s["salidas"] = []
        s["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": f"El cruce {fila['orden']} paró: {fila['motivo_parada']}.", "artefactos": ["informes/integracion-datos.json", "informes/integracion-datos.md"], "siguiente": "revisar la clave con correccion-datos"}
        return s

    # 4.3 Guardar solo cuando han pasado todos.
    s["salidas"] = []
    for nombre, df in (("barrios_integrado", b), ("anuncios_integrado", sep)):
        ruta = rc.PROCESADO / f"{nombre}.parquet"
        df.to_parquet(ruta, index=False)
        s["salidas"].append({"ruta": ruta.relative_to(rc.CASO).as_posix(), "sha256": cd.huella(ruta), "filas": len(df), "columnas": df.shape[1]})
    s["salida"] = s["salidas"][-1]
    estado = "AVISO" if distintas else "OK"
    s["resultado"] = {"estado": estado, "riesgo": "bajo", "resumen": f"Los {len(s['cruces'])} cruces pasaron: ninguno gana ni pierde filas y sus sumas coinciden." + (f" Huellas distintas: {distintas}." if distintas else ""),
                      "artefactos": [x["ruta"] for x in s["salidas"]] + ["informes/integracion-datos.json", "informes/integracion-datos.md"], "siguiente": "transformacion-datos"}
    return s


def ejecutar():
    """Lanza los cruces y, si algo falla, deja el JSON con estado ERROR antes de avisar."""
    s = rc.bloque_comun(SKILL, VERSION, SCRIPT)
    try:
        s = principal(s)
    except Exception as error:
        rc.parar_con_error(s, "integracion-datos", error, informe)
        raise
    rc.guardar(s, "integracion-datos", informe)
    print(s["resultado"]["estado"], s["resultado"]["resumen"])
    return 0


if __name__ == "__main__":
    raise SystemExit(ejecutar())
