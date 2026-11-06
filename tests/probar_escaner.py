"""Prueba scripts/escanear_repositorio.py sobre un repositorio pequeño, con un caso limpio y uno roto por cada defecto."""
import gzip
import subprocess
import sys
import tempfile
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
import escanear_repositorio as er  # noqa: E402

FALLOS = []


def caso(nombre, bien, detalle=""):
    """Apunta un caso e imprime si pasa."""
    print(f"{'ok   ' if bien else 'FALLA'} {nombre}" + ("" if bien else f": {str(detalle)[:300]}"))
    if not bien:
        FALLOS.append(nombre)


def repositorio(raiz, ficheros):
    """Crea un repositorio de prueba y versiona los ficheros."""
    for rel, texto in ficheros.items():
        ruta = Path(raiz, rel)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".gz"):
            ruta.write_bytes(gzip.compress(texto.encode("utf-8")))
        else:
            ruta.write_text(texto, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
    subprocess.run(["git", "add", *ficheros], cwd=raiz, check=True)


ROTOS = {"ruta de una máquina": {"a.md": "C:" + "/Us" + "ers/ana/datos.csv\n"}, "correo": {"a.md": "escribe a ana" + "@ejemplo.es\n"},
         "teléfono": {"a.md": "llama al 6" + "12345678\n"}, "documento": {"a.md": "DNI 1234" + "5678Z\n"},
         "credenciales": {".env": "CLAVE=1\n"}, "columna": {er.TABLA: "barrio,id\nUsera,1\n"}}

with tempfile.TemporaryDirectory() as t:
    repositorio(t, {"a.md": "texto limpio\n", er.TABLA: "barrio,rent_sep_pct\nUsera,10.1\n"})
    n, fuera = er.escanear(t)
    caso("limpio sin hallazgos", not fuera, fuera)
    caso("mira los dos ficheros", n == 2, n)
with tempfile.TemporaryDirectory() as t:
    repositorio(t, {"a.py": 'HUELLA = "a67236bae3044d7f1' + '612345678cf"\n'})
    caso("una huella no es un teléfono", not er.escanear(t)[1], er.escanear(t)[1])
for nombre, ficheros in ROTOS.items():
    with tempfile.TemporaryDirectory() as t:
        repositorio(t, ficheros)
        caso(f"rojo: {nombre}", er.escanear(t)[1])

print("VERDE" if not FALLOS else f"ROJO: {FALLOS}")
sys.exit(1 if FALLOS else 0)
