"""Prueba del cuadro de mando del caso, con caso que tiene que fallar en cada guardia.

Tres partes:
  A. Las piezas de scripts/cuadro_mando.py con datos pequeños escritos aquí.
  B. El HTML ya generado contra informes/indicadores.json: las cifras coinciden y no lleva ningún anuncio suelto.
  C. El HTML abierto en Edge sin ventana, selección a selección: un filtro cambia las cifras y su total casa con la suma.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla.

Ejecución:
  PYTHONUTF8=1 python -W error tests/probar_cuadro_mando.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))

HTML = CASO / "informes" / "cuadro_mando.html"
JSON_CUADRO = CASO / "informes" / "cuadro_mando.json"
INDICADORES = CASO / "informes" / "indicadores.json"
ANUNCIOS = CASO / "data" / "processed" / "analisis_anuncios.parquet"
EDGE = next((Path(p) for p in (shutil.which("msedge"), os.environ.get("ProgramFiles(x86)", "") + "/Microsoft/Edge/Application/msedge.exe") if p and Path(p).exists()), None)

fallos = []


def caso(nombre, cumple, detalle=""):
    """Apunta un caso de prueba e imprime si pasa."""
    print(("  ok   " if cumple else "  FALLA ") + nombre + (f" · {detalle}" if detalle and not cumple else ""))
    if not cumple:
        fallos.append(nombre)


def para(nombre, funcion, *args):
    """Comprueba que una guardia para con ValueError: una guardia que no puede dar rojo no prueba nada."""
    try:
        funcion(*args)
    except ValueError:
        caso(nombre, True)
        return
    caso(nombre, False, "no paró")


# ---------------------------------------------------------------------------
# Datos pequeños
# ---------------------------------------------------------------------------

def pisos_pequenos():
    """Distrito A con el barrio X (31 de 1 habitación y 5 de 2) y distrito B con el barrio Y (4 de 3 habitaciones)."""
    filas = []
    for i in range(31):
        filas.append(("A", "X", 1.0, 10.0 + i, 100.0 + i, 100 + i, 150000.0))
    for i in range(5):
        filas.append(("A", "X", 2.0, 50.0 + i, 300.0, 200, 195000.0))
    for i in range(4):
        filas.append(("B", "Y", 3.0, 3.0 + i, 90.0, 60, 300000.0))
    return pd.DataFrame(filas, columns=["distrito", "barrio", "dormitorios", "rent_valoraciones_pct",
                                        "precio_eur", "ocupacion_dias", "compra_valoraciones_eur"])


GEO_PEQUENO = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"neighbourhood": "X", "neighbourhood_group": "A"},
     "geometry": {"type": "MultiPolygon", "coordinates": [[[[-3.7, 40.4], [-3.6, 40.4], [-3.6, 40.5], [-3.7, 40.5], [-3.7, 40.4]]]]}},
    {"type": "Feature", "properties": {"neighbourhood": "Y", "neighbourhood_group": "B"},
     "geometry": {"type": "MultiPolygon", "coordinates": [[[[-3.6, 40.4], [-3.5, 40.4], [-3.5, 40.5], [-3.6, 40.5], [-3.6, 40.4]]]]}}]}


# ---------------------------------------------------------------------------
# A. Piezas con datos pequeños
# ---------------------------------------------------------------------------

def parte_a():
    """Prueba las piezas del script; si el script no existe, ese es el rojo."""
    print("A. Piezas con datos pequeños")
    try:
        import cuadro_mando as cm
    except ModuleNotFoundError as e:
        caso("el script existe", False, str(e))
        return
    d = pisos_pequenos()
    distritos = {"A": ["X"], "B": ["Y"], "C": ["Z"]}
    sel, celdas = cm.agregar(d, distritos)

    caso("tramos de habitaciones", [cm.tramo_dormitorios(x) for x in (0.0, 1.0, 3.0, 4.0, 5.0)] == ["0", "1", "3", "4 o más", "4 o más"])
    t = sel[cm.clave("Todos", "Todos", "Todos")]
    caso("el total cuenta todos los pisos", t["pisos"] == 40, str(t))
    # Mediana de 40 valores calculada a mano: con 3 a 6 delante de 10 a 40, las posiciones 20 y 21 son 25 y 26
    caso("la mediana del total es la de los 40 pisos", abs(t["rent"] - 25.5) < 1e-9, str(t.get("rent")))
    celda = sel[cm.clave("A", "X", "1")]
    caso("una celda de 31 pisos da cifras", celda["pisos"] == 31 and celda["rent"] == 25.0 and celda["precio"] == 115.0, str(celda))
    caso("el cuartil bajo sale de esos 31 pisos", celda["cuartil"] == 17.5, str(celda))
    pequena = sel[cm.clave("A", "X", "2")]
    caso("una celda de 5 pisos solo da el recuento", set(pequena) == {"pisos"} and pequena["pisos"] == 5, str(pequena))
    caso("un distrito con pocos pisos solo da el recuento", set(sel[cm.clave("B", "Todos", "Todos")]) == {"pisos"})
    caso("un barrio sin pisos no se guarda", cm.clave("C", "Z", "Todos") not in sel)
    datos = {"selecciones": sel, "celdas": celdas, "distritos": distritos}
    caso("una selección vacía se resuelve a cero", cm.resumen(datos, "C", "Z", "Todos") == {"pisos": 0})
    caso("las celdas suman el total", sum(c[2] for c in celdas) == 40)
    caso("el total de un filtro casa con sus celdas", cm.suma_celdas(datos, "A", "Todos", "Todos") == cm.resumen(datos, "A", "Todos", "Todos")["pisos"] == 36)
    caso("el filtro cambia las cifras", cm.resumen(datos, "A", "X", "1")["rent"] != cm.resumen(datos, "A", "Todos", "Todos")["rent"])
    cm.comprobar_totales(datos)
    roto = json.loads(json.dumps(datos))
    roto["selecciones"][cm.clave("A", "Todos", "Todos")]["pisos"] = 35
    para("para si el total de un filtro no casa con la suma", cm.comprobar_totales, roto)

    esperadas = [("Todos|Todos", "rent", 25.5, "mediana")]
    caso("cifra igual a su fuente: pasa", cm.comparar(datos, esperadas) == 1)
    para("para si una cifra no coincide con su fuente", cm.comparar, datos, [("Todos|Todos", "rent", 25.6, "mediana")])
    para("para si la cifra de la fuente no está en el cuadro", cm.comparar, datos, [("A|1", "rent", 1.0, "falta")])

    cm.sin_anuncios_sueltos({"selecciones": sel, "celdas": celdas})
    para("para si una selección de menos de 30 lleva cifras", cm.sin_anuncios_sueltos,
         {"selecciones": {"B:Y|3": {"pisos": 4, "rent": 3.0}}, "celdas": []})
    para("para si los datos llevan una columna de anuncio", cm.sin_anuncios_sueltos,
         {"selecciones": {"Todos|Todos": {"pisos": 40, "latitud": 40.4}}, "celdas": []})
    para("para si una celda trae algo más que barrio, habitaciones y recuento", cm.sin_anuncios_sueltos,
         {"selecciones": {}, "celdas": [["X", "1", 31, 40.41]]})

    caso("una entrada más nueva que su script pasa", cm.entrada_vieja(200.0, 100.0) is False)
    caso("una entrada más vieja que su script se detecta", cm.entrada_vieja(100.0, 200.0) is True)
    para("para si la fecha de los datos no es la del caso", cm.comprobar_fecha, "2026-09-16", "2026-09-17")
    entradas = [{"ruta": "data/processed/analisis_anuncios.parquet", "sha256": "abc"}]
    cm.misma_entrada(entradas, "data/processed/analisis_anuncios.parquet", "abc")
    para("para si la tabla no es la que usaron los indicadores", cm.misma_entrada, entradas, "data/processed/analisis_anuncios.parquet", "otra")
    para("para si los indicadores no dicen qué tabla usaron", cm.misma_entrada, entradas, "data/processed/analisis_barrios.parquet", "abc")

    clases = {"X": "5 de 5 veces", "Y": "menos de 30"}
    svg = cm.mapa_svg(GEO_PEQUENO, clases, {"X": "A", "Y": "B"}, ["X"])
    caso("el mapa lleva un trazado por barrio", svg.count("<path") == 2 and 'data-barrio="X"' in svg and 'data-barrio="Y"' in svg)
    caso("cada barrio sale con el color de su clase", cm.COLOR_CLASE["5 de 5 veces"] in svg)
    caso("el mapa no pide nada de fuera", "http" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', ""))
    caso("los barrios del grupo llevan su nombre en el mapa", ">X</text>" in svg and ">Y</text>" not in svg)
    para("para si falta un barrio en los límites", cm.mapa_svg, GEO_PEQUENO, {"X": "5 de 5 veces", "Y": "5 de 5 veces", "Z": "5 de 5 veces"}, {}, [])

    texto = cm.datos_en_html({"a": "</script><b>"})
    caso("los datos no pueden cerrar su etiqueta", "</script>" not in texto, texto)


# ---------------------------------------------------------------------------
# B. El HTML generado contra el JSON de indicadores
# ---------------------------------------------------------------------------

def datos_del_html(texto):
    """Saca del HTML los datos que usa el navegador."""
    m = re.search(r'<script type="application/json" id="datos">(.*?)</script>', texto, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def parte_b():
    """Compara las cifras del HTML con indicadores.json por un camino propio y busca anuncios sueltos."""
    print("B. El HTML generado")
    if not HTML.exists() or not JSON_CUADRO.exists():
        caso("el HTML y su JSON existen", False, "falta la salida")
        return None
    texto = HTML.read_text(encoding="utf-8")
    datos = datos_del_html(texto)
    ind = json.loads(INDICADORES.read_text(encoding="utf-8"))
    p = {q["id"]: q for q in ind["preguntas"]}
    s = {x["id"]: x for x in ind["las_16"]}
    sel = datos["selecciones"]

    def igual(nombre, a, b, tolerancia=2e-6):
        """Compara dos cifras con la precisión del JSON, que guarda seis decimales."""
        caso(nombre, a is not None and b is not None and abs(a - b) <= tolerancia, f"{a} frente a {b}")

    todos = sel["Todos|Todos"]
    caso("fecha de los datos", datos["fecha_datos"] == ind["fecha_datos"])
    caso("pisos de la base", todos["pisos"] == p["P1"]["poblacion"]["filas"])
    cifras_p1 = {c["nombre"]: c["valor"] for c in p["P1"]["cifras"]}
    igual("rentabilidad mediana de la base", todos["rent"], cifras_p1["rentabilidad de toda la base: mediana"])
    igual("cuartil bajo de la base", todos["cuartil"], cifras_p1["rentabilidad de toda la base: q25"])
    igual("precio de la base", todos["precio"], s["S01"]["base_decision"]["datos"]["global"]["mediana"])
    igual("ocupación de la base", todos["ocupacion"], s["S07"]["base_decision"]["datos"]["global"]["mediana"])

    malas = []
    for f in p["P1"]["dormitorios"]["tabla"]:
        c = sel[f"Todos|{f['grupo']}"]
        if (c["pisos"], round(c["rent"], 5), round(c["cuartil"], 5)) != (f["pisos"], round(f["rentabilidad_mediana_pct"], 5), round(f["cuartil_bajo_pct"], 5)):
            malas.append(f["grupo"])
    caso("las cuatro filas de habitaciones", not malas, str(malas))
    caso("los 4 o más habitaciones no se ordenan", set(sel["Todos|4 o más"]) == {"pisos"} and sel["Todos|4 o más"]["pisos"] == p["P1"]["dormitorios"]["sin_conclusion"][0]["casos"])

    malas = []
    for f in p["P2"]["tabla_barrios"]:
        c = sel[f"B:{f['barrio']}|Todos"]
        if (c["pisos"], round(c["rent"], 5), round(c["cuartil"], 5)) != (f["pisos"], round(f["rentabilidad_mediana_pct"], 5), round(f["cuartil_bajo_pct"], 5)):
            malas.append(f["barrio"])
        if datos["barrios"][f["barrio"]]["clase"] != f["clase"]:
            malas.append(f["barrio"] + " (clase)")
    caso("las 36 filas de barrios, con su clase", not malas and len(p["P2"]["tabla_barrios"]) == 36, str(malas))
    caso("solo 36 barrios llevan ficha", set(datos["barrios"]) == {f["barrio"] for f in p["P2"]["tabla_barrios"]})

    malas = []
    for f in p["P2"]["fichas_del_grupo"]:
        b = datos["barrios"][f["barrio"]]
        if b["aguanta"] != len(f["pruebas_que_aguanta"]) or len(b["no_aguanta"]) != len(f["pruebas_que_no_aguanta"]) or b["aguanta"] + len(b["no_aguanta"]) != 5 or [a["texto"] for a in b["avisos"]] != f["avisos_en_texto"]:
            malas.append(f["barrio"])
    caso("pruebas y avisos de los 9 barrios del grupo", not malas, str(malas))

    for pregunta, medida, nombre in (("S01", "precio", "precio"), ("S07", "ocupacion", "ocupación")):
        d = s[pregunta]["base_decision"]["datos"]
        malas = [f["grupo"] for f in d["por_distrito"] if abs(sel[f"D:{f['grupo']}|Todos"][medida] - f["mediana"]) > 2e-6 or sel[f"D:{f['grupo']}|Todos"]["pisos"] != f["casos"]]
        malas += [f["grupo"] for f in d["por_barrio"] if abs(sel[f"B:{f['grupo']}|Todos"][medida] - f["mediana"]) > 2e-6]
        caso(f"{nombre} de cada distrito y barrio", not malas, str(malas))
    filas_s14 = s["S14"]["base_decision"]["datos"]["distritos"]
    # Tres distritos se escriben distinto en las dos fuentes: se casan sin los espacios
    nombre = {d.replace(" ", ""): d for d in datos["distritos"]}
    malas = [f["distrito"] for f in filas_s14 if f["anuncios_de_la_base"] >= 30 and abs(sel[f"D:{nombre[f['distrito'].replace(' ', '')]}|Todos"]["compra"] - f["compra_mediana_valoraciones_eur"]) > 2e-4]
    caso("precio de compra de cada distrito", not malas, str(malas))

    trazados = re.findall(r'<path d="[^"]*" fill="([^"]*)" data-barrio="([^"]*)"', texto)
    caso("el mapa tiene los 128 barrios", len({b for _, b in trazados}) == 128, str(len(trazados)))
    color = {b: f for f, b in trazados}
    caso("el color de cada barrio del grupo es el de su clase", all(color[b] == c for b, c in (("Ventas", "#2a78d6"), ("Opañel", "#eb6834"), ("Quintana", "#1baf7a"), ("Atocha", "#898781"), ("Sol", "url(#rayado)"))))
    pisos_de = lambda b: sel[f"B:{b}|Todos"]["pisos"]
    caso("pisos del grupo", sum(pisos_de(b) for b in p["P2"]["grupo"]) == p["P2"]["pisos_del_grupo"])
    caso("pisos del grupo recomendado", sum(pisos_de(b) for b in p["P2"]["firmes"]) == p["P2"]["pisos_del_grupo_firme"])
    caso("pisos en barrios comparados", sum(pisos_de(f["barrio"]) for f in p["P2"]["tabla_barrios"]) == p["P2"]["referencia"]["filas"])
    caso("barrios con pisos", len({c[0] for c in datos["celdas"]}) == p["P2"]["cobertura"]["barrios_con_pisos"])

    caso("los textos de la recomendación salen del JSON", all(b in texto for b in p["P2"]["firmes"]))
    caso("el límite está en la primera pantalla", "no si un piso se puede alquilar a turistas" in texto.split('id="p-mapa"')[0].lower())
    firmes = [f for f in p["P2"]["fichas_del_grupo"] if f["clase"] == "5 de 5 veces"]
    dicho = "salen de la lista al quitar los pisos" in texto
    caso("el aviso del tope sale solo si vale para todos los recomendados", dicho == all(f["avisos_del_barrio"]["depende_del_tope"] for f in firmes))
    caso("la atribución está entera", all(x in texto for x in ("Inside Airbnb", "CC BY 4.0", "17/09/2026", "Origen de los datos: Ayuntamiento de Madrid", "Colegio de Registradores de España")))

    # Ningún anuncio suelto: ni columnas de anuncio, ni cifras con menos de 30, ni identificadores ni coordenadas
    menores = [k for k, v in sel.items() if v["pisos"] < 30 and set(v) != {"pisos"}]
    caso("ninguna selección de menos de 30 lleva cifras", not menores, str(menores[:5]))
    caso("hay selecciones de menos de 30 que comprobar", any(v["pisos"] < 30 for v in sel.values()))
    caso("cada celda es barrio, habitaciones y recuento", all(len(c) == 3 for c in datos["celdas"]))
    a = pd.read_parquet(ANUNCIOS, columns=["id", "latitud", "longitud", "base_decision"])
    numeros = set(re.findall(r"\d{6,}", texto))
    caso("ningún número de anuncio", not numeros & {str(x) for x in a["id"]})
    caso("ninguna coordenada", not re.search(r"\b40\.[3-6]\d{2}|-3\.[5-9]\d{2}", texto))
    caso("ninguna columna de anuncio", not any(w in texto for w in ("latitud", "longitud", "ocupacion_dias", '"id"')))
    caso("no pide nada de fuera", not re.search(r'(src|href)\s*=\s*"http|https?://|@import|url\(http|fetch\(|XMLHttpRequest', texto), "hay una llamada externa")
    return datos


# ---------------------------------------------------------------------------
# C. El navegador
# ---------------------------------------------------------------------------

# Edge no devuelve el DOM por la salida estándar en este Windows. Por eso la prueba sirve una copia del HTML desde esta
# máquina con este recorrido añadido: pasa por cada selección de los filtros en cada pestaña y envía lo que ve en pantalla.
RECORRIDO = r"""
<script>
window.__errores = [];
addEventListener("error", e => window.__errores.push(String(e.message)));
(async () => {
  const combinaciones = await (await fetch("/combinaciones")).json();
  const inicial = {direccion: location.hash, pisos: Number(document.getElementById("viendo").dataset.pisos)};
  estado.pestana = "mapa"; estado.dorm = "2"; pintar();
  const escrita = location.hash;
  // Definición a un clic y etiqueta al pasar el ratón, en la primera pestaña sin filtros
  estado.pestana = "recomendacion"; estado.distrito = "Todos"; estado.dorm = "Todos"; pintar();
  const c1 = document.querySelector("#cifras-recomendacion [data-def=rent]");
  c1.click();
  const definicion = document.getElementById("def-recomendacion").textContent;
  c1.dispatchEvent(new MouseEvent("mouseover", {bubbles: true}));
  const etiqueta = document.getElementById("etiqueta").textContent;
  document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape"}));
  const etiqueta_oculta = document.getElementById("etiqueta").hidden;
  c1.click();
  const sin_tip = [...document.querySelectorAll("button.cifra-clave, svg g.dato, #mapa path")].filter(e => !e.dataset.tip).length;
  const vistas = [];
  for (const [pestana, distrito, barrio, dorm] of combinaciones) {
    estado.pestana = pestana; estado.distrito = distrito; estado.barrio = barrio; estado.dorm = dorm;
    pintar();
    const valores = {};
    document.querySelectorAll("[id][data-valor]").forEach(e => { valores[e.id] = e.dataset.valor; });
    const c = document.getElementById("cuadro");
    vistas.push({pestana, distrito, barrio, dorm, valores, filas: [...document.querySelectorAll("#tabla-barrios tr[data-barrio]")].map(f => [f.dataset.barrio, Number(f.dataset.pisos)]),
      pisos: Number(document.getElementById("viendo").dataset.pisos), viendo: document.getElementById("viendo-texto").textContent, quitar_activo: !document.getElementById("quitar").disabled,
      contexto: document.getElementById("c-rent-contexto").dataset.texto, estado: c.dataset.estado, ancho: Number(c.dataset.ancho), alto: Number(c.dataset.alto), palabras: Number(c.dataset.palabras), direccion: c.dataset.direccion});
  }
  const salida = {vistas, inicial, escrita, definicion, etiqueta, etiqueta_oculta, sin_tip, errores: window.__errores, ventana: [innerWidth, innerHeight]};
  await fetch("/resultado", {method: "POST", body: JSON.stringify(salida)});
  window.close();
})().catch(e => fetch("/resultado", {method: "POST", body: JSON.stringify({vistas: [], errores: [String(e)], ventana: []})}));
</script>
"""


class Pagina(BaseHTTPRequestHandler):
    """Sirve el HTML con el recorrido y recoge lo que el navegador envía."""
    pagina, combinaciones, resultado, llego = b"", b"", {}, threading.Event()

    def log_message(self, *args):
        """Calla el registro de peticiones."""

    def do_GET(self):
        """Da la página o la lista de selecciones."""
        cuerpo = Pagina.combinaciones if self.path == "/combinaciones" else Pagina.pagina
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if self.path == "/combinaciones" else "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        """Guarda lo que vio el navegador."""
        Pagina.resultado = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        self.send_response(200)
        self.end_headers()
        Pagina.llego.set()


def cerrar_edge(perfil):
    """Cierra los procesos de Edge de esta prueba, y solo esos, y devuelve cuántos quedan: los reconoce por su carpeta de perfil."""
    lista = f"Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object {{ $_.CommandLine -like '*{Path(perfil).name}*' }}"
    orden = f"{lista} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}; Start-Sleep -Milliseconds 500; @({lista}).Count"
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", orden], capture_output=True, text=True, timeout=60)
    return int(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else -1


def recorrer(datos):
    """Abre la copia en Edge sin ventana y devuelve lo que vio en cada selección; 1390 × 742 de ventana deja 1366 × 650 de página."""
    combinaciones = []
    for pestana in ("recomendacion", "mapa", "barrios"):
        for dorm in ["Todos"] + [t[0] for t in datos["tramos"]]:
            combinaciones.append([pestana, "Todos", "Todos", dorm])
            for distrito, barrios in datos["distritos"].items():
                combinaciones.append([pestana, distrito, "Todos", dorm])
                combinaciones += [[pestana, distrito, b, dorm] for b in barrios]
    Pagina.combinaciones = json.dumps(combinaciones, ensure_ascii=False).encode("utf-8")
    Pagina.pagina = HTML.read_text(encoding="utf-8").replace("</body>", RECORRIDO + "</body>").encode("utf-8")
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Pagina)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    # Edge a veces arranca sin cargar la página: el recorrido tarda segundos, de modo que se dan tres intentos de 45
    url = f"http://127.0.0.1:{servidor.server_port}/#pestana=barrios&distrito=Puente%20de%20Vallecas"
    quedan = 0
    try:
        for intento in range(3):
            perfil = tempfile.mkdtemp(prefix="cuadro63_")
            proceso = subprocess.Popen([str(EDGE), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={perfil}", "--window-size=1390,742", url])
            llego = Pagina.llego.wait(timeout=45)
            proceso.kill()
            proceso.wait(timeout=20)
            quedan += cerrar_edge(perfil)
            shutil.rmtree(perfil, ignore_errors=True)
            # Un intento que no llega a recorrer nada, por un fallo de red del propio navegador, tampoco vale.
            if llego and Pagina.resultado.get("vistas"):
                break
            Pagina.llego.clear()
            print(f"  intento {intento + 1}: Edge no cargó la página")
    finally:
        servidor.shutdown()
        servidor.server_close()
    Pagina.resultado["edge_abiertos"] = quedan
    return Pagina.resultado


def parte_c(datos):
    """Comprueba en un navegador real, selección a selección, que los filtros cambian las cifras y que los totales casan."""
    print("C. El navegador")
    if datos is None:
        caso("hay HTML que abrir", False)
        return
    if EDGE is None:
        print("  NO SE PUDO COMPROBAR: este equipo no tiene Edge y el recorrido en navegador se salta")
        return
    r = recorrer(datos)
    vistas = r.get("vistas", [])
    caso("no queda ningún Edge de la prueba abierto", r.get("edge_abiertos") == 0, str(r.get("edge_abiertos")))
    caso("el recorrido llega al final", len(vistas) > 0, str(r)[:300])
    if not vistas:
        return
    print(f"  {len(vistas)} vistas recorridas, ventana {r['ventana']}")
    caso("ningún error de JavaScript", not r["errores"], str(r["errores"][:3]))
    caso("todas se montan", all(v["estado"] == "listo" for v in vistas))
    sel = datos["selecciones"]

    def clave(v):
        """Construye la clave de la vista igual que el script."""
        ambito = f"B:{v['barrio']}" if v["barrio"] != "Todos" else (f"D:{v['distrito']}" if v["distrito"] != "Todos" else "Todos")
        return f"{ambito}|{v['dorm']}"

    def de_barrios(v):
        """Da los barrios de la vista."""
        if v["barrio"] != "Todos":
            return [v["barrio"]]
        return datos["distritos"][v["distrito"]] if v["distrito"] != "Todos" else [b for l in datos["distritos"].values() for b in l]

    mal = {"cifras": [], "recuento": [], "suma": [], "tabla": [], "menos_de_30": [], "fila_baja": [], "total": []}
    for v in vistas:
        s = sel.get(clave(v), {"pisos": 0})
        for campo, ident in (("rent", "c-rent"), ("precio", "c-precio"), ("ocupacion", "c-ocupacion"), ("compra", "c-compra")):
            propio = v["valores"].get(ident)
            if (campo in s and (propio in ("", None) or float(propio) != s[campo])) or (campo not in s and propio != ""):
                mal["cifras"].append((clave(v), campo))
        if v["pisos"] != s["pisos"]:
            mal["recuento"].append(clave(v))
        # La suma se rehace aquí desde las celdas: es el camino distinto del total guardado
        barrios = set(de_barrios(v))
        suma = sum(c[2] for c in datos["celdas"] if c[0] in barrios and v["dorm"] in ("Todos", c[1]))
        if suma != s["pisos"]:
            mal["suma"].append(clave(v))
        tabla = sum(f[1] for f in v["filas"])
        if tabla + int(v["valores"]["c-pisos-menos"]) != s["pisos"]:
            mal["tabla"].append(clave(v))
        if int(v["valores"]["t-total"]) != tabla:
            mal["total"].append(clave(v))
        if any(f[1] < 30 for f in v["filas"]):
            mal["fila_baja"].append(clave(v))
        if 0 < s["pisos"] < 30 and "no concluyente" not in v["contexto"]:
            mal["menos_de_30"].append(clave(v))
    caso("las cuatro cifras de cada selección son las guardadas", not mal["cifras"], str(mal["cifras"][:5]))
    caso("el recuento de cada selección es el guardado", not mal["recuento"], str(mal["recuento"][:5]))
    caso("el total de cada filtro casa con la suma de sus celdas", not mal["suma"], str(mal["suma"][:5]))
    caso("la tabla más lo contado aparte da el total de cada filtro", not mal["tabla"], str(mal["tabla"][:5]))
    caso("la fila de total es la suma de la tabla", not mal["total"], str(mal["total"][:5]))
    caso("ninguna fila de la tabla baja de 30", not mal["fila_baja"], str(mal["fila_baja"][:5]))
    caso("menos de 30 dice no concluyente", not mal["menos_de_30"], str(mal["menos_de_30"][:5]))

    def vista(pestana, distrito="Todos", barrio="Todos", dorm="Todos"):
        """Busca una vista concreta del recorrido."""
        return next(v for v in vistas if (v["pestana"], v["distrito"], v["barrio"], v["dorm"]) == (pestana, distrito, barrio, dorm))

    base = vista("barrios")
    distrito = vista("barrios", "Puente de Vallecas")
    dormitorio = vista("barrios", dorm="2")
    caso("sin filtros, la tabla tiene 36 barrios", len(base["filas"]) == 36, str(len(base["filas"])))
    caso("sin filtros, el botón de quitar está desactivado", not base["quitar_activo"])
    caso("con filtro, el botón de quitar está activo", distrito["quitar_activo"])
    caso("el filtro de distrito cambia las cifras", distrito["valores"]["c-rent"] != base["valores"]["c-rent"] and distrito["pisos"] < base["pisos"])
    caso("el filtro de habitaciones cambia las cifras", dormitorio["valores"]["c-rent"] != base["valores"]["c-rent"] and dormitorio["pisos"] < base["pisos"])
    caso("el filtro cambia las filas de la tabla", len(distrito["filas"]) < len(base["filas"]) and len(dormitorio["filas"]) < len(base["filas"]))
    caso("la página mide 1366 × 650 en la prueba", r["ventana"] == [1366, 650], str(r["ventana"]))
    caso("el filtro se lee de la dirección", r["inicial"]["pisos"] == distrito["pisos"], str(r["inicial"]))
    caso("el filtro se escribe en la dirección", r["escrita"] == "#pestana=mapa&distrito=Puente%20de%20Vallecas&dorm=2", r["escrita"])
    caso("la definición sale a un clic", r["definicion"].startswith("Rentabilidad bruta:"), r["definicion"])
    caso("la etiqueta da la selección, la medida y la cifra", "Rentabilidad bruta" in r["etiqueta"] and "8,3 %" in r["etiqueta"], r["etiqueta"])
    caso("la etiqueta se esconde con Escape", r["etiqueta_oculta"])
    caso("cada cifra, barra y barrio lleva etiqueta", r["sin_tip"] == 0, str(r["sin_tip"]))
    pequena = next(v for v in vistas if 0 < v["pisos"] < 30)
    caso("menos de 30 dice que no se ordena", "no se ordena" in pequena["viendo"], pequena["viendo"])
    caso("una selección sin pisos no rompe el cuadro", vista("mapa", "Centro", "Sol", "4 o más")["pisos"] == 0)

    for pestana in ("recomendacion", "mapa", "barrios"):
        propias = [v for v in vistas if v["pestana"] == pestana]
        ancho, alto, palabras = max(v["ancho"] for v in propias), max(v["alto"] for v in propias), max(v["palabras"] for v in propias)
        print(f"  {pestana}: ancho {ancho}, alto {alto}, palabras {palabras}")
        caso(f"{pestana}: sin barra a lo ancho a 1366", ancho <= 1366, str(ancho))
        caso(f"{pestana}: cabe en 650 de alto", alto <= 650, str(alto))
        caso(f"{pestana}: unas 60 palabras, con el tope de 80 que fija esta prueba", palabras <= 80, str(palabras))


if __name__ == "__main__":
    parte_a()
    resultado = parte_b()
    parte_c(resultado)
    print()
    if fallos:
        print(f"ROJO: {len(fallos)} casos fallan")
        for f in fallos:
            print(" -", f)
        sys.exit(1)
    print("VERDE: todos los casos pasan")
    sys.exit(0)
