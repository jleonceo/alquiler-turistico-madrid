"""Escáner del repositorio para el CI: mira lo que git publica y sale con 1 si encuentra algo que no debe estar.

Busca rutas absolutas de una máquina, ficheros de credenciales, correos, teléfonos y documentos de identidad, y columnas
identificativas en la tabla publicada. Sale con 0 si está limpio, con 1 si hay hallazgos y con 2 si no pudo mirar.

Ejecución:
  python scripts/escanear_repositorio.py [carpeta]
"""
import gzip
import re
import subprocess
import sys
from pathlib import Path

BINARIOS = {".png", ".pdf", ".xlsx", ".gz"}
# La ruta se monta por trozos para que este fichero no se denuncie a sí mismo.
PATRONES = {"ruta de una máquina": re.compile(r"[A-Za-z]:[\\/]" + "(?:Us" + r"ers|PROYECTOS_)|/ho" + r"me/[a-z]+/|/Us" + r"ers/[A-Za-z]"),
            "correo": re.compile(r"[\w.+-]+@(?!users\.noreply)[\w-]+\.[a-z]{2,}", re.I), "teléfono": re.compile(r"(?<![\w.,/-])[6789]\d{8}(?![\w.,])"),
            "documento": re.compile(r"(?<![\w.])\d{8}[A-HJ-NP-TV-Z](?!\w)"), "cuenta": re.compile(r"\bES\d{22}\b")}
PROHIBIDOS = {".env", "id_rsa"}
COLUMNAS_PROHIBIDAS = {"id", "listing_id", "host_id", "host_name", "latitud", "longitud", "latitude", "longitude", "anuncios_anfitrion", "calculated_host_listings_count", "precio_eur", "price"}
# Los HTML y JSON generados llevan datos de gráficos que no son texto de nadie: ahí solo se mira la ruta.
SOLO_RUTA = {".html", ".json", ".geojson"}
TABLA = "data/publicado/pisos_fuera_del_centro.csv.gz"
# Pruebas que plantan un correo inventado para comprobar que la cadena lo detecta. Se declaran una a una.
CORREO_PLANTADO = {"tests/probar_calidad_datos.py", "tests/probar_correccion_datos.py"}


def versionados(raiz):
    """Lista los ficheros que git publica."""
    r = subprocess.run(["git", "ls-files"], cwd=raiz, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(2)
    return [x for x in r.stdout.splitlines() if x]


def hallazgos_de(rel, texto):
    """Devuelve lo que un fichero de texto no debería llevar."""
    fuera = []
    patrones = {"ruta de una máquina": PATRONES["ruta de una máquina"]} if Path(rel).suffix in SOLO_RUTA else PATRONES
    for nombre, patron in patrones.items():
        if nombre == "correo" and rel in CORREO_PLANTADO:
            continue
        fuera += [f"{rel}: {nombre}" for _ in patron.findall(texto)[:1]]
    return fuera


def columnas_de(ruta):
    """Lee la cabecera de la tabla publicada."""
    with gzip.open(ruta, "rt", encoding="utf-8") as f:
        return set(f.readline().strip().split(","))


def escanear(raiz):
    """Recorre lo publicado y devuelve el número de ficheros mirados y los hallazgos."""
    fuera, mirados = [], 0
    for rel in versionados(raiz):
        ruta = Path(raiz) / rel
        mirados += 1
        if ruta.name in PROHIBIDOS:
            fuera.append(f"{rel}: fichero de credenciales")
        if ruta.suffix in BINARIOS:
            continue
        fuera += hallazgos_de(rel, ruta.read_text(encoding="utf-8"))
    tabla = Path(raiz) / TABLA
    if tabla.exists():
        fuera += [f"{TABLA}: columna {c}" for c in sorted(columnas_de(tabla) & COLUMNAS_PROHIBIDAS)]
    return mirados, fuera


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    n, lista = escanear(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
    for x in lista:
        print(f"HALLAZGO {x}")
    print(f"{n} ficheros mirados, {len(lista)} hallazgos.")
    sys.exit(1 if lista else 0)
