"""Prueba scripts/indicadores.py: cada función con datos pequeños escritos aquí, las paradas y el caso pequeño entero.

Los casos en rojo a propósito están marcados: una comprobación que da verde tiene que poder dar rojo (error 24).
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))
sys.path.insert(0, str(CARPETA.parent / "scripts"))
import cadena_de_prueba as cp  # noqa: E402

PLANTEAMIENTO = """# Planteamientos

La población de las tres preguntas es la base de decisión.

## Pregunta 1 · Qué tipo de piso rinde más

- Decisión: a.
- Medida: b.
- Referencia: c.
- Mínimo: 30 anuncios por grupo.
- Qué cambia la decisión: d.

## Pregunta 2 · En qué barrios

- Decisión: a.
- Medida: b.
- Referencia: c.
- Mínimo: 30 anuncios.
- Qué cambia la decisión: d.

## Pregunta 3 · Con qué riesgo

- Decisión: a.
- Medida: b.
- Referencia: c.
- Mínimo: 30 anuncios.
- Qué cambia la decisión: d.
"""


def tabla_grupos():
    """Ocho barrios de 30 pisos: Alto rinde más que todos; Medio solo por sus pisos de temporada; Tercero queda justo detrás."""
    filas = []
    niveles = {"Alto": 300, "Medio": 200, "Tercero": 150, "D": 100, "E": 90, "F": 80, "G": 70, "H": 60}
    for b, precio in niveles.items():
        for i in range(30):
            filas.append({"id": len(filas) + 1, "barrio": b, "piso": True, "dentro": False, "ocupacion": 100, "accommodates": 2, "banos": 1.0, "bedrooms": 1.0, "beds": 1.0,
                          "estancia": 2.0, "precio": float(precio), "p_mar": float(precio), "p_jun": float(precio), "sup_regla": 50.0, "m2": 4000.0, "temporada": False, "property_type": "Entire rental unit",
                          "anuncios_anfitrion": 1, "dias_cotizacion": 5.0, "dias_cotizacion_mar": 5.0, "dias_cotizacion_jun": 5.0})
    t = pd.DataFrame(filas)
    # Todos los pisos de Medio declaran temporada y sin ellos Medio no tiene dato: el barrio no sigue en el grupo.
    t.loc[t["barrio"].eq("Medio"), "temporada"] = True
    return t


def pruebas_de_funciones(p, ind):
    """Comprueba las funciones sueltas contra cuentas hechas a mano."""
    # Wilson: 5 de 10 al 95 % son 0,2366 y 0,7634, calculado aparte con la fórmula.
    bajo, alto = ind.intervalo_wilson(5, 10)
    p.caso("Wilson de 5 de 10", abs(bajo - 0.2366) < 1e-3 and abs(alto - 0.7634) < 1e-3, str((bajo, alto)))
    d = pd.DataFrame({"g": ["a"] * 40 + ["b"] * 40 + ["c"] * 5, "si": [True] * 38 + [False] * 2 + [True] * 2 + [False] * 38 + [True] * 5})
    t, azar = ind.comparar_con_total(d, "g", "si")
    p.caso("el grupo pequeño no se compara", "c" not in t.index)
    p.caso("azar en dos grupos al 95 %", azar == 0.1, str(azar))
    p.caso("el grupo alto queda por encima", t.loc["a", "frente_al_total"] == "por encima")
    p.caso("el grupo bajo queda por debajo", t.loc["b", "frente_al_total"] == "por debajo")

    s = ind.dormitorios_de(pd.Series([0.0, 1.0, 3.0, 4.0, 5.0]))
    p.caso("habitaciones en grupos", list(s) == ["0", "1", "3", "4 o más", "4 o más"], str(list(s)))
    n = ind.nivel_ocupacion(pd.Series([1, 85, 86, 170, 171, 254, 255]))
    p.caso("niveles con el tope aparte", list(n) == ["1-85", "1-85", "86-170", "86-170", "171-254", "171-254", "255"], str(list(n)))
    p.caso("un cero no cae en ningún nivel", pd.isna(ind.nivel_ocupacion(pd.Series([0])).iloc[0]))

    # Cuantil lineal hecho a mano: en 1, 2, 3, 4 el cuartil bajo es 1,75.
    p.caso("cuantil a mano", ind.cuantil([4.0, 1.0, 3.0, 2.0], 0.25) == 1.75)
    p.caso("mediana a mano", ind.mediana([4.0, 1.0, 3.0, 2.0]) == 2.5)

    rng = np.random.default_rng(1)
    alto_v, bajo_v = rng.normal(20, 1, 60), rng.normal(10, 1, 60)
    igual_a, igual_b = rng.normal(10, 3, 60), rng.normal(10, 3, 60)
    r = ind.diferencia_de_medianas(alto_v, bajo_v, "a", "b")
    p.caso("dos grupos lejanos se distinguen", r["se_distinguen"] and r["bajo"] > 0, str(r))
    r2 = ind.diferencia_de_medianas(igual_a, igual_b, "a", "b")
    # ROJO a propósito: dos grupos de la misma población no pueden salir distintos.
    p.caso("dos grupos iguales no se distinguen", not r2["se_distinguen"], str(r2))
    p.caso("el intervalo se repite con la misma semilla", ind.diferencia_de_medianas(igual_a, igual_b, "a", "b") == r2)

    d = pd.DataFrame({"g": ["a"] * 30 + ["b"] * 29, "x": list(range(30)) + [1.0] * 29, "id": range(59)})
    filas, fuera = ind.por_grupo(d, "g", "x")
    p.caso("el mínimo de 30 deja al grupo", [f["grupo"] for f in filas] == ["a"])
    p.caso("el de 29 sale sin conclusión", fuera == [{"grupo": "b", "casos": 29}], str(fuera))
    p.caso("cuartil bajo por grupo", abs(filas[0]["q25"] - 7.25) < 1e-9, str(filas[0]))
    v = ind.comprobar_por_grupo("prueba", filas, d, "g", "x")
    p.caso("la segunda vía coincide", v["coinciden"], str(v))
    mal = [dict(filas[0], mediana=filas[0]["mediana"] + 1)]
    # ROJO a propósito: una cifra cambiada tiene que dar que no coincide.
    p.caso("una cifra cambiada no coincide", not ind.comprobar_por_grupo("prueba", mal, d, "g", "x")["coinciden"])

    m = ind.mejor_cuarto(pd.Series({"a": 5.0, "b": 5.0, "c": 1.0, "d": 1.0, "e": 1.0}))
    p.caso("empates: el mismo valor, la misma marca", bool(m["a"]) == bool(m["b"]) and bool(m["c"]) == bool(m["d"]))

    L = tabla_grupos()
    nadie = pd.Series(False, index=L.index)
    reglas = {"anfitrion_anuncios": 10, "cotizacion_dias": 60, "dormitorios": [1, 2], "pocos_anuncios": 40}
    grupo, recomendados, _ = ind.grupo_y_recomendados(L, nadie, reglas)
    p.caso("grupo de ocho barrios", grupo == ["Alto", "Medio"], str(grupo))
    p.caso("el barrio que depende de temporada no sale recomendado", recomendados == ["Alto"], str(recomendados))
    pruebas_de_las_cinco(p, ind, reglas)

    # 2 pisos de 50 m² a 4.000 €/m² y 100 días: junio a 50 € da 2,5 %; marzo a 200 € da 10 %.
    t = pd.DataFrame({"precio": [100.0, 100.0], "p_mar": [200.0, 200.0], "p_jun": [50.0, 50.0], "ocupacion": [100, 100], "sup_regla": [50.0, 50.0], "m2": [4000.0, 4000.0], "estancia": [2.0, 2.0]})
    r = ind.rango_de_rentabilidad(t)
    p.caso("la fecha más baja es junio", abs(r["minimo"] - 2.5) < 1e-9 and r["peor"] == "junio", str(r))
    p.caso("la fecha más alta es marzo", abs(r["maximo"] - 10.0) < 1e-9 and r["mejor"] == "marzo", str(r))
    p.caso("tres fechas", len(r["combinaciones"]) == 3)

    # «No supere»: un cuartil bajo igual a la mediana de la base también lleva aviso.
    p.caso("aviso con el cuartil por debajo", ind.lleva_aviso(5.0, 6.0))
    p.caso("aviso con el cuartil igual", ind.lleva_aviso(6.0, 6.0))
    p.caso("sin aviso con el cuartil por encima", not ind.lleva_aviso(6.1, 6.0))

    p.caso("hay 16 preguntas", len(ind.LAS_16) == 16)
    bloques = [x["bloque"] for x in ind.LAS_16]
    p.caso("seis, seis y cuatro", (bloques.count("precio"), bloques.count("ocupacion"), bloques.count("compra")) == (6, 6, 4), str(bloques))
    p.caso("cada una con su texto", all(x["texto"].strip() for x in ind.LAS_16))
    p.caso("identificadores únicos", len({x["id"] for x in ind.LAS_16}) == 16)

    p.caso("unidad buena", ind.unidad_correcta(pd.DataFrame({"id": [1, 2, 3]})))
    # ROJO a propósito: una clave repetida es contar filas de más.
    p.caso("unidad mala con un id repetido", not ind.unidad_correcta(pd.DataFrame({"id": [1, 1, 3]})))

    # ROJO a propósito: la validación 8 busca en un código con un sí escrito a mano.
    p.caso("detecta una comprobación con un sí a mano", ind.escritos_a_mano('c = {"unidad": True}\n', []) != [])
    p.caso("detecta una validación con un sí a mano", ind.escritos_a_mano('c = {"raw_intacto": True}\n', []) != [])
    p.caso("detecta un resultado escrito", ind.escritos_a_mano('x = "Barrio Plantado"\n', ["Barrio Plantado"]) != [])
    p.caso("un código limpio no da nada", ind.escritos_a_mano('x = calcular()\n', ["Barrio Plantado"]) == [])

    p.caso("planteamiento completo", ind.falta_en_planteamiento(PLANTEAMIENTO) == [])
    # ROJO a propósito: sin una referencia hay que parar.
    falta = ind.falta_en_planteamiento(PLANTEAMIENTO.replace("- Referencia: c.\n- Mínimo: 30 anuncios por grupo.", "- Mínimo: 30 anuncios por grupo."))
    p.caso("sin referencia se para", falta != [], str(falta))


def pruebas_de_las_cinco(p, ind, reglas):
    """Cada prueba, con su caso en rojo: el barrio que tiene que caer, cae en esa prueba y solo en esa."""
    rc = ind.rc
    L = tabla_grupos()
    nadie = pd.Series(False, index=L.index)
    r = rc.pruebas_del_grupo(L, nadie, reglas)
    p.caso("son cinco pruebas", len(rc.PRUEBAS) == 5 and set(r["barrios"]["Alto"]["aguanta"]) == set(rc.PRUEBAS), str(r["barrios"].get("Alto")))
    p.caso("el que aguanta las cinco sale recomendado", r["barrios"]["Alto"]["clase"] == "5 de 5 veces" and r["recomendados"] == ["Alto"], str(r["barrios"]))
    p.caso("el que aguanta cuatro lleva aviso", r["barrios"]["Medio"]["clase"] == "4 de 5 veces" and r["cuatro_de_cinco"] == ["Medio"], str(r["barrios"]))
    p.caso("Medio cae solo en la temporada", r["barrios"]["Medio"]["no_aguanta"] == ["sin_temporada"], str(r["barrios"]["Medio"]))

    # ROJO a propósito: con los anuncios de un anfitrión grande, Medio cae en dos pruebas y baja a resto del grupo.
    x = tabla_grupos()
    x.loc[x["barrio"].eq("Medio"), "anuncios_anfitrion"] = 10
    r2 = rc.pruebas_del_grupo(x, nadie, reglas)
    p.caso("10 anuncios ya es anfitrión grande", "sin_anfitriones_grandes" in r2["barrios"]["Medio"]["no_aguanta"], str(r2["barrios"]["Medio"]))
    p.caso("el que aguanta tres va en resto del grupo", r2["barrios"]["Medio"]["clase"] == "menos de 4 veces" and r2["segunda_linea"] == ["Medio"], str(r2["barrios"]))
    x.loc[x["barrio"].eq("Medio"), "anuncios_anfitrion"] = 9
    p.caso("9 anuncios no lo es", "sin_anfitriones_grandes" in rc.pruebas_del_grupo(x, nadie, reglas)["barrios"]["Medio"]["aguanta"])

    # La cotización mira la foto de cada variante: si cae solo marzo quedan ocho variantes y aguanta; si caen marzo y junio, cuatro.
    x = tabla_grupos()
    x.loc[x["barrio"].eq("Alto"), "dias_cotizacion_mar"] = 61.0
    p.caso("sin marzo aguanta la cotización", "sin_cotizaciones_lejanas" in rc.pruebas_del_grupo(x, nadie, reglas)["barrios"]["Alto"]["aguanta"])
    x.loc[x["barrio"].eq("Alto"), "dias_cotizacion_jun"] = 61.0
    p.caso("sin marzo ni junio no aguanta la cotización", "sin_cotizaciones_lejanas" in rc.pruebas_del_grupo(x, nadie, reglas)["barrios"]["Alto"]["no_aguanta"])
    x.loc[x["barrio"].eq("Alto"), ["dias_cotizacion_mar", "dias_cotizacion_jun"]] = 60.0
    p.caso("a 60 días exactos sigue", "sin_cotizaciones_lejanas" in rc.pruebas_del_grupo(x, nadie, reglas)["barrios"]["Alto"]["aguanta"])

    # Con los pisos de tres dormitorios fuera, Alto se queda sin datos.
    x = tabla_grupos()
    x.loc[x["barrio"].eq("Alto"), "bedrooms"] = 3.0
    p.caso("los de 3 habitaciones no cuentan en esa prueba", "solo_1_y_2_dormitorios" in rc.pruebas_del_grupo(x, nadie, reglas)["barrios"]["Alto"]["no_aguanta"])

    # Pisos sin ocupación: 60 más en Alto hunden su mediana a cero solo en esa prueba.
    extra = tabla_grupos().query("barrio == 'Alto'").assign(ocupacion=0)
    y = pd.concat([tabla_grupos(), extra, extra.assign(id=lambda t: t["id"] + 2000)], ignore_index=True)
    y["id"] = range(len(y))
    r3 = rc.pruebas_del_grupo(y, pd.Series(False, index=y.index), reglas)
    p.caso("contar los sin ocupación como cero tumba al barrio", r3["barrios"]["Alto"]["no_aguanta"] == ["sin_ocupacion_como_cero"], str(r3["barrios"]["Alto"]))

    # Los tres avisos, en su frontera.
    p.caso("40 pisos son pocos", ind.avisos_del_barrio(40, 7.0, 6.0, True, 40)["pocos_anuncios"])
    p.caso("41 pisos no son pocos", not ind.avisos_del_barrio(41, 7.0, 6.0, True, 40)["pocos_anuncios"])
    p.caso("sale sin el tope", ind.avisos_del_barrio(41, 7.0, 6.0, False, 40)["depende_del_tope"])
    p.caso("sigue sin el tope", not ind.avisos_del_barrio(41, 7.0, 6.0, True, 40)["depende_del_tope"])
    p.caso("cuartil igual a la base avisa", ind.avisos_del_barrio(41, 6.0, 6.0, True, 40)["cuartil_bajo"])
    p.caso("cuartil por encima no avisa", not ind.avisos_del_barrio(41, 6.1, 6.0, True, 40)["cuartil_bajo"])

    # Referencia: el grupo frente a los de m² más barato, con el empate deshecho por el nombre.
    precios = pd.Series({"A": 1000.0, "B": 2000.0, "C": 2000.0, "D": 3000.0})
    b = ind.comparar_con_baratos(["A", "C"], precios)
    p.caso("toma tantos baratos como barrios tiene el grupo", b["baratos"] == ["A", "B"], str(b))
    p.caso("cuenta las coincidencias", b["coinciden"] == ["A"] and b["cuantos"] == 1, str(b))

    # Sensibilidad: con el estudio a 35 m² gana el estudio; con 1 dormitorio a 45 m², gana 1 dormitorio. Doble ingreso = doble rentabilidad.
    rng = np.random.default_rng(3)
    d = pd.DataFrame({"grupo_dormitorios": ["0"] * 40 + ["1"] * 40 + ["2"] * 40, "superficie_valoraciones_m2": [50.0] * 80 + [65.0] * 40, "ingreso_anual_eur": np.r_[rng.normal(1000, 5, 40), rng.normal(1200, 5, 40), rng.normal(1200, 5, 40) * 1.3],
                      "precio_m2_eur": 4000.0, "dormitorios": [0.0] * 40 + [1.0] * 40 + [2.0] * 40})
    s = ind.sensibilidad_superficie(d, {"0": [35, 50], "1": [45, 60], "2": [60, 75]})
    p.caso("ocho combinaciones", len(s["combinaciones"]) == 8, str(len(s["combinaciones"])))
    tipos = {tuple(sorted(c["se_dan"])) for c in s["combinaciones"]}
    p.caso("se ve qué tipos se dan en cada una", len(tipos) >= 2, str(tipos))
    p.caso("dice si cambia", s["cambia"] == (len(tipos) > 1 or tipos != {tuple(sorted(s["se_dan_con_la_regla"]))}), str(s["cambia"]))
    c = next(x for x in s["combinaciones"] if x["superficies"] == {"0": 35, "1": 60, "2": 75})
    p.caso("con el estudio a 35 m² el estudio sube", c["medianas"]["0"] > c["medianas"]["1"] or c["se_dan"][0] == "0", str(c))
    # Un piso de 1 dormitorio y 140 m² por sus baños no cambia de superficie.
    p.caso("la superficie que viene de los baños no se mueve", list(ind.superficie_movida(pd.Series(["1", "1"]), pd.Series([50.0, 140.0]), {"1": 60}, {"1": 50.0})) == [60.0, 140.0])


def caso_entero(p):
    """Monta el caso pequeño, lanza el exploratorio y los indicadores y mira el JSON."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        caso, r = cp.montar(tmp, "transformacion_datos.py")
        p.caso("el caso pequeño se monta", r.returncode == 0, r.stderr[-500:])
        origen = CARPETA.parent
        (caso / "assets").mkdir(exist_ok=True)
        for nombre in ("graficos.py", "estilo.css"):
            shutil.copy(origen / "assets" / nombre, caso / "assets" / nombre)
        for nombre in ("analisis_exploratorio.py", "indicadores.py"):
            shutil.copy(origen / "scripts" / nombre, caso / "scripts" / nombre)
        metodo = caso / "config" / "metodo"
        metodo.mkdir(parents=True, exist_ok=True)
        (metodo / "04_planteamientos.md").write_text(PLANTEAMIENTO, encoding="utf-8")
        fuentes = caso / "config" / "fuentes"
        fuentes.mkdir(parents=True, exist_ok=True)
        (fuentes / "02_datos_necesarios.md").write_text("El recuento de junio de 2025, 111 anuncios, recuento anotado.\n", encoding="utf-8")
        huellas = cp.huellas(caso)
        r0 = cp.lanzar(caso, "analisis_exploratorio.py")
        p.caso("el exploratorio acaba bien", r0.returncode == 0, r0.stderr[-1500:])
        r1 = cp.lanzar(caso, "indicadores.py")
        p.caso("los indicadores acaban bien", r1.returncode == 0, r1.stderr[-1500:])
        j = cp.leer(caso, "indicadores.json")
        p.caso("sin errores", j["resultado"]["estado"] in ("OK", "AVISO"), j["resultado"]["resumen"])
        p.caso("trae fecha_datos", j["fecha_datos"] == "2026-09-17")
        p.caso("tres preguntas", [x["id"] for x in j["preguntas"]] == ["P1", "P2", "P3"])
        p.caso("16 preguntas en el JSON", len(j["las_16"]) == 16)
        p.caso("cada una en las dos bases", all(x["base_decision"] and x["base_comparacion"] for x in j["las_16"]))
        p.caso("cada una con texto y respuesta", all(x["texto"] and x["base_decision"]["respuesta"] and x["base_comparacion"]["respuesta"] for x in j["las_16"]))
        p.caso("todas las validaciones pasan", all(v is True for v in j["validaciones"].values()), str(j["validaciones"]))
        q1, q2, q3 = j["preguntas"]
        p.caso("cada barrio del grupo lleva sus pruebas, su clase y sus avisos", all({"clase", "pruebas_que_aguanta", "pruebas_que_no_aguanta", "avisos_del_barrio"} <= set(f) for f in q2["fichas_del_grupo"]), str(q2["fichas_del_grupo"][:1]))
        p.caso("trae la tabla de las cinco pruebas", set(q2["pruebas"]) == {"barrios", "recomendados", "cuatro_de_cinco", "segunda_linea", "por_prueba", "variantes_por_prueba"}, str(list(q2.get("pruebas", {}))))
        p.caso("trae la sensibilidad de superficie", len(q1["sensibilidad_superficie"]["combinaciones"]) == 8)
        p.caso("trae la referencia de los baratos", {"comparados", "toda_la_ciudad"} <= set(q2["referencia_baratos"]))
        p.caso("trae el rango de recomendados y los que siguen en la lista 4 veces", "rango_de_rentabilidad_de_recomendados_y_cuatro_de_cinco" in q3)
        p.caso("trae la parte sin ocupación en la misma base", all("sin_ocupacion_misma_base_pct" in f for f in q3["fichas_del_grupo"]))
        p.caso("P-01 queda resuelto", not any("no fijan cuándo" in x["pregunta"] for x in j["pendientes"]) and j["pendientes_resueltos"][0]["id"] == "P-01", str(j["pendientes"]))
        p.caso("el corte de pocos anuncios no se decide en el script", "corte_de_pocos_anuncios" not in q3)
        p.caso("la segunda vía repasa las cinco pruebas", any(v["tabla"].startswith("prueba ") for v in j["segunda_via"]))
        p.caso("las nueve validaciones", len(j["validaciones"]) == 9)
        for q in j["preguntas"]:
            p.caso(f"{q['id']} con población y filas", q["poblacion"]["filas"] >= 0 and q["poblacion"]["regla"] != "")
            p.caso(f"{q['id']} con referencia", q["referencia"]["que_es"] != "")
            p.caso(f"{q['id']} con las nueve comprobaciones", len(q["comprobaciones"]) == 9)
            p.caso(f"{q['id']} con cada null explicado", all(v is not None or any(k in x for x in q["limites"]) for k, v in q["comprobaciones"].items()), str(q["comprobaciones"]))
        p.caso("JSON sin NaN", "NaN" not in (caso / "informes" / "indicadores.json").read_text(encoding="utf-8"))
        md = (caso / "informes" / "indicadores.md").read_text(encoding="utf-8")
        for apartado in ["## Las preguntas y su planteamiento", "## Lo que no saca conclusión", "## Validaciones", "## Parámetros usados", "## Datos personales", "## Límites"]:
            p.caso(f"el informe trae {apartado}", apartado in md)
        for clave in ("evolucion_oferta", "estacionalidad", "disponibilidad", "atractivo_y_competencia", "licencias_y_registro"):
            p.caso(f"el JSON trae {clave}", clave in j)
        p.caso("el recuento de 2025 se lee del documento", j["evolucion_oferta"]["junio_2025"]["anuncios"] == 111, str(j["evolucion_oferta"].get("junio_2025")))
        borrador = metodo / "06_borrador_de_hallazgos.md"
        p.caso("deja el borrador de hallazgos", borrador.exists())
        texto = borrador.read_text(encoding="utf-8") if borrador.exists() else ""
        for parte in ("## Hallazgos", "## Alertas", "## Hipótesis"):
            p.caso(f"el borrador separa {parte}", parte in texto)
        p.caso("los datos de entrada no cambian", cp.huellas(caso) == huellas)

        # ROJO a propósito: un grupo esperado que no sale no se ajusta; se dice y queda en AVISO.
        ruta = caso / "scripts" / "decisiones_correccion.json"
        dec = json.loads(ruta.read_text(encoding="utf-8"))
        dec["controles"]["grupo_esperado"] = ["Barrio que no existe"]
        ruta.write_text(json.dumps(dec, ensure_ascii=False), encoding="utf-8")
        cp.lanzar(caso, "indicadores.py")
        j2 = cp.leer(caso, "indicadores.json")
        p.caso("un control que no sale se dice", j2["controles"]["grupo"]["coincide"] is False, str(j2.get("controles")))
        p.caso("no se ajusta: el estado avisa", j2["resultado"]["estado"] == "AVISO", j2["resultado"]["estado"])
        dec["controles"]["grupo_esperado"] = None
        ruta.write_text(json.dumps(dec, ensure_ascii=False), encoding="utf-8")

        # ROJO a propósito: un exploratorio parado detiene los indicadores.
        ruta = caso / "informes" / "analisis-exploratorio__analisis_anuncios.json"
        e = json.loads(ruta.read_text(encoding="utf-8"))
        e["resultado"]["estado"] = "ERROR"
        ruta.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
        cp.lanzar(caso, "indicadores.py")
        p.caso("con el exploratorio en ERROR no empieza", cp.leer(caso, "indicadores.json")["resultado"]["estado"] == "PARADO")
        e["resultado"]["estado"] = "OK"
        ruta.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")

        # ROJO a propósito: sin planteamiento completo el estado es PARADO.
        (metodo / "04_planteamientos.md").write_text("# Nada\n", encoding="utf-8")
        cp.lanzar(caso, "indicadores.py")
        p.caso("sin planteamiento para", cp.leer(caso, "indicadores.json")["resultado"]["estado"] == "PARADO")


def principal():
    """Recorre las funciones y el caso pequeño."""
    p = cp.Prueba()
    try:
        import indicadores as ind
    except ModuleNotFoundError as error:
        p.caso("el script existe", False, str(error))
        return p.fin()
    pruebas_de_funciones(p, ind)
    caso_entero(p)
    return p.fin()


if __name__ == "__main__":
    sys.exit(principal())
