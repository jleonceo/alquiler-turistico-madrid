"""Interpretación de los resultados del caso para la Dirección de Inversiones.

Lee informes/indicadores.json y deja informes/interpretacion_resultados.md. No calcula cifras: las lee por su clave y deja
al final el inventario con la ruta de cada una. Va en un script para que ninguna cifra se escriba a mano.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/interpretacion_resultados.py
Opciones: --indicadores <json>, --salida <carpeta>. Las usa tests/probar_interpretacion_resultados.py.
"""
import argparse
import datetime
import sys
from pathlib import Path

import cifras_informes as ci
from cifras_informes import ORDENA, PLANTA, Q2, Q3, REC, UN_ANO, ficha

Q1 = "preguntas[0]"
SUP = f"{Q1}.sensibilidad_superficie"
DORM = f"{Q1}.dormitorios"


# =====================================================================================================================
# 1. El documento
# =====================================================================================================================

def documento(c, hoy):
    """Escribe el cuerpo del documento en Markdown, con cada cifra leída del JSON."""
    rango = f"{Q3}.rango_de_rentabilidad_del_grupo_firme"
    rango2 = f"{Q3}.rango_de_rentabilidad_de_firmes_y_con_aviso"
    baratos = f"{Q2}.referencia_baratos.comparados"
    cuartil_base = c.pct(f"{Q2}.cuartil_bajo_de_toda_la_base", 2)
    acciones = ci.acciones(c)
    filas_acciones = "\n".join(f"| {a['nombre']} | {a['quien']} | {a['cuando'][0].upper() + a['cuando'][1:]} | {r} |" for a, r in zip(acciones, (
        "Cada barrio de la lista queda con una respuesta del Ayuntamiento sobre planta, acceso y norma.",
        "La rentabilidad bruta de cada oportunidad se rehace con su superficie real.",
        "Se comprueba si cada barrio conserva su clase con la foto nueva.")))
    return f"""# Buscar primero pisos de hasta 2 habitaciones en los tres barrios firmes

Emitido el {hoy}. Datos de la foto del {ci.fecha_es(c.dato('fecha_datos'))}. Cada cifra lleva su ruta en el inventario del final.

## Pregunta y objetivo

La Dirección de Inversiones decide dónde concentra la búsqueda de pisos para alquiler turístico en Madrid, y el equipo de valoraciones decide qué oportunidades estudia. La pregunta tiene tres partes: qué tipo de piso rinde más, en qué barrios conviene buscarlo fuera del centro histórico y con qué riesgo.

## Grandes números

- Recomendación: los firmes de hasta 2 habitaciones son {c.num(REC + '.pisos')} anuncios en Airbnb, con una rentabilidad bruta de {c.pct(REC + '.rentabilidad_sin_descuento_pct')} sin descuento y de {c.pct(REC + '.rentabilidad_con_descuento_pct')} con él.
- Rango: todos los pisos firmes van de {c.pct(rango + '.minimo')} a {c.pct(rango + '.maximo')}, según la foto de precio y el descuento, sin gastos. No es beneficio.
- Por piso, en mediana y sin gastos: {c.eur(REC + '.compra_sin_descuento_eur')} de compra sin descuento, {c.eur(REC + '.compra_con_descuento_eur')} con él y {c.eur(REC + '.ingreso_anual_eur')} de ingreso anual.
- Lista de barrios: {c.cuantos(Q2 + '.firmes')} firmes y {c.cuantos(Q2 + '.con_aviso')} con aviso, dentro de un grupo de {c.cuantos(Q2 + '.grupo')} barrios y {c.num(Q2 + '.pisos_del_grupo')} anuncios en Airbnb.
- Planta: {c.num(PLANTA + '.licencias')} de las {c.num(PLANTA + '.de')} licencias municipales incluyen planta baja, y {c.num(PLANTA + '.firmes.licencias')} de las {c.num(PLANTA + '.firmes.de')} de los barrios firmes.
- Riesgo: en uno de cada cuatro anuncios la rentabilidad no llega a {cuartil_base}, el cuartil bajo de toda la base. Los firmes quedan por encima, de {c.pct(ficha('Numancia', 'cuartil_bajo_pct'))} a {c.pct(ficha('Ventas', 'cuartil_bajo_pct'))}.
- Precio: los {c.num(baratos + '.de')} barrios de m² más barato dan {c.pct(ORDENA + '.m2_baratos.mediana_pct')} con descuento, los firmes {c.pct(ORDENA + '.firmes.mediana_pct')} y el grupo {c.pct(ORDENA + '.grupo.mediana_pct')}, sin distinguirse. La mediana conjunta de los firmes no es la media de sus barrios.

## La historia

Es una lista de dónde buscar, que no dice si un piso se puede comprar para este uso. Se partía de un mercado visible en Airbnb del que buena parte queda dentro del centro histórico, donde el Plan RESIDE no admite pisos turísticos en edificios residenciales. La base de decisión deja {c.num(Q1 + '.poblacion.filas')} pisos fuera de ese centro.

Dónde buscar primero: Ventas, Numancia y San Diego. Una variante repite el cálculo con otra estancia, otro mínimo de anuncios u otra foto de precio, y una prueba repite esas variantes quitando algo. Estos tres aguantan las cinco pruebas. Son estables, no mejores: Numancia supera la mediana de la base de decisión, y Ventas y San Diego no se distinguen de ella. No se distingue significa que la diferencia puede ser cero con un intervalo de confianza del 95 %.

Quién va detrás: San Diego queda por debajo de Casco Histórico de Vallecas y de Opañel, que aun así van después porque dependen de operadores grandes, los anfitriones de 10 anuncios o más. Son el {c.pct(Q2 + '.operadores_grandes.con_aviso_pct', 0)} de sus anuncios. El resto del grupo es segunda línea, y Puerta del Ángel está en él sin aguantar ninguna prueba. La lista es un grupo y no un ranking.

Qué buscar: pisos de hasta 2 habitaciones. No hay ganador entre estudio, una y dos habitaciones, porque su orden depende del supuesto de m². En {c.num(SUP + '.combinaciones_que_cambian')} de las {c.cuantos(SUP + '.combinaciones')} combinaciones cambian los tipos que se dan.

Por dónde empezar: valoraciones empieza por bajos y primeras plantas con acceso independiente. Las normas dicen que, fuera del centro histórico, en el nivel B de la zona 1, el hospedaje cabe en planta baja, inferior a la baja y primera, y siempre con acceso independiente. El ingreso de un bajo no se conoce, porque el de los anuncios mezcla todas las plantas. Qué norma rige en cada barrio no se puede saber con estos datos: hay que preguntarlo en el Ayuntamiento antes de comprar. Esto no es asesoramiento jurídico.

Qué aporta la lista: elegir solo por m² barato no se distingue de ella en rentabilidad. Entre los {c.num(ORDENA + '.barrios')} barrios, la rentabilidad se asocia más con la ocupación ({c.num(ORDENA + '.rentabilidad_con_ocupacion', 2)}) que con el m² ({c.num(ORDENA + '.rentabilidad_con_m2', 2)}), y la ocupación es la cifra más débil del caso. La lista aporta saber qué barrios aguantan las pruebas.

Qué riesgo queda: un barrio depende del tope si sale del grupo al quitar los pisos que llegan a 255 días, y los tres firmes dependen. Opañel, con el {c.pct(ficha('Opañel', 'parte_en_el_tope_pct'), 0)} de sus pisos en el tope, no depende. La ocupación cuenta reseñas de 12 meses y un anuncio nuevo sale bajo: con los {c.num(UN_ANO + '.pisos')} anuncios de un año o más, Numancia queda {c.num(ci.puesto('Numancia'))}.ª, Ventas {c.num(ci.puesto('Ventas'))}.ª y San Diego {c.num(ci.puesto('San Diego'))}.ª de {c.num(UN_ANO + '.barrios_comparados')}. San Diego se sostiene menos con este corte.

## Nivel de confianza

**Confianza media** en dónde buscar y qué tipo de piso buscar. **Baja** en el nivel de la rentabilidad bruta. **No se puede saber** si un piso concreto se puede comprar para este uso.

- Muestra: Numancia, Ventas y San Diego tienen {c.num(ficha('Numancia', 'pisos'))}, {c.num(ficha('Ventas', 'pisos'))} y {c.num(ficha('San Diego', 'pisos'))} anuncios, por encima del mínimo de 30.
- Cobertura temporal: una foto de septiembre, con el precio de marzo y junio como contraste. La temporada completa no se ve.
- Calidad: la ocupación es una estimación con tope de 255 días, y en la parte alta no ordena. Los tres firmes dependen del tope.
- Supuestos: la superficie y el descuento del 25 % no salen de los datos, y el precio de compra es el declarado en 2025.
- Segmentos: no hay ganador, y la ventaja de 1 habitación sobre 2 se repite en {c.num(Q1 + '.por_segmentos.distritos_donde_1_supera_a_2')} de {c.num(Q1 + '.por_segmentos.distritos_comparables_1_y_2')} distritos.
- Diseño: datos observados, sin experimento.
- Sin comprobar: noches vendidas reales, norma de cada barrio e ingreso por planta.

Prueba de refutación de cada afirmación principal:

| Afirmación | Qué la haría falsa | Resultado |
|---|---|---|
| Los tres firmes aguantan las cinco pruebas | que alguno cayera en una prueba | se mantiene; contar además los pisos sin ocupación ni precio dejaría solo a Ventas como firme |
| Hasta 2 habitaciones rinden más que 3 | una combinación de superficie con 3 habitaciones por encima | se mantiene en todas |
| Los firmes rinden más que la base de decisión | que su intervalo tocara la mediana | se corrige: solo Numancia la supera, y San Diego y Ventas no se distinguen |
| La lista rinde más que elegir por precio | que las cifras no se distinguieran | se corrige: no se distinguen, y coinciden {c.num(baratos + '.cuantos')} de {c.num(baratos + '.de')} barrios |

## Lo que no se puede afirmar

- Causalidad: todo son asociaciones sobre datos observados. Una hipótesis sigue siéndolo: la concentración en el tope de Casco Histórico de Vallecas admite dos lecturas, muchos alquileres o una fórmula inflada, y haría falta conocer las noches vendidas.
- Segmentos: cada barrio se da con su recuento, y los totales de habitaciones se miraron por distrito.
- Terceras variables: el m² y el alquiler van juntos por distrito, y la localización puede mover los dos.
- Generalización: vale para los pisos fuera del centro histórico en esta foto. Un anuncio no es un inmueble.
- Cambio con el tiempo: marzo y junio solo cubren los anuncios que siguen en septiembre, con la ocupación de septiembre. El rango entre fotos no predice otras fechas.
- Valores extremos: se usan medianas, porque el ingreso tiene cola larga. Un barrio con 40 pisos o menos lleva aviso.
- Ocupación: es una estimación con tope de 255 días, y en la parte alta no ordena. Quedan fuera de la lista {c.num(Q3 + '.pisos_fuera_sin_ocupacion.pisos')} pisos sin ocupación, el {c.pct(Q3 + '.pisos_fuera_sin_ocupacion.pct')} de los pisos fuera del centro. Con esa misma población, Numancia llega al {c.pct(ficha('Numancia', 'pisos_fuera_sin_ocupacion_pct', 3))}, San Diego al {c.pct(ficha('San Diego', 'pisos_fuera_sin_ocupacion_pct', 3))} y Ventas al {c.pct(ficha('Ventas', 'pisos_fuera_sin_ocupacion_pct', 3))}. Contar además los pisos sin ocupación ni precio dejaría solo a Ventas como firme.
- Calendario y competencia: el calendario no distingue reservado de bloqueado, y la competencia cuenta solo anuncios de Airbnb.
- Territorio: cerca del borde del centro histórico el lado de un anuncio no se puede asegurar, y Casco Histórico de Vallecas junta en Airbnb lo que el Ayuntamiento separa.
- Licencias: una licencia no se puede unir a un anuncio.

## Decisión que permite

La Dirección de Inversiones puede concentrar la búsqueda en la lista. No permite decidir una compra.

| Acción | Quién | Plazo | Resultado esperado y cómo se mide |
|---|---|---|---|
{filas_acciones}

## Cifras pendientes

- Inversión total en euros: no consta, y la fijaría la Dirección de Inversiones.
- Rentabilidad neta: no hay fuente para cada gasto.
- Noches vendidas reales: no están en los datos.
- Fecha de cada acción: no consta.

## Fuentes

- Inside Airbnb, Madrid, foto del 17/09/2026, con licencia CC BY 4.0.
- Origen de los datos: Ayuntamiento de Madrid, datos de 2025.
- Colegio de Registradores de España, fuente del precio declarado y de la superficie de 2025 que publica el Ayuntamiento.
- `informes/indicadores.json`, `informes/indicadores.md` y `scripts/indicadores.py`.
- `informes/analisis-exploratorio__analisis_anuncios.json` y `informes/analisis-exploratorio__analisis_barrios.json`, para las hipótesis y alertas.
- `config/metodo/06_borrador_de_hallazgos.md`.

## Datos personales

Son datos públicos, protegidos antes de llegar al caso con una supresión de columnas, sin códigos con clave. Salieron las columnas que identifican al anfitrión, los enlaces, las fotos, los textos, el nombre de quien reseña y el número de licencia, del que queda su tipo. Quedan el número del anuncio, las coordenadas, desplazadas hasta 150 m, y el recuento de anuncios por anfitrión. Los resultados se dan por barrio y tipo de piso, y ninguno decide sobre una persona.

## Límite de este documento

Solo interpreta lo que contienen los informes previos y hereda sus limitaciones. No calcula cifras, no valora un piso concreto y no sustituye a la consulta en el Ayuntamiento. La rentabilidad con los dos barrios con aviso va de {c.pct(rango2 + '.minimo')} a {c.pct(rango2 + '.maximo')}.
"""


def inventario(c):
    """Escribe el inventario: cada cifra citada, de qué fichero y clave sale."""
    filas = "\n".join(f"| {x['cifra']} | `informes/indicadores.json` | `{'`, `'.join(x['claves'])}` |" for x in c.rastro())
    return f"\n## Inventario de evidencias\n\n| Cifra | Fichero | Clave |\n|---|---|---|\n{filas}\n"


# =====================================================================================================================
# 2. Principal
# =====================================================================================================================

def principal():
    """Comprueba la lectura, pasa la guardia y escribe."""
    a = argparse.ArgumentParser()
    a.add_argument("--indicadores", default=str(ci.INDICADORES))
    a.add_argument("--salida", default=str(ci.CASO / "informes"))
    o = a.parse_args()
    c = ci.Cifras(o.indicadores)
    ci.comprobar_lectura(c)
    hoy = datetime.date.today().strftime("%d/%m/%Y")
    cuerpo = documento(c, hoy)
    ci.sin_jerga(cuerpo.split("## Fuentes")[0])
    sueltas = ci.cifras_sin_rastro(cuerpo.split("## Fuentes")[0].replace("\u00a0", " "), list(c.apuntadas))
    if sueltas:
        raise SystemExit(f"Cifras sin clave en el texto: {sueltas}")
    ruta = Path(o.salida) / "interpretacion_resultados.md"
    ruta.write_text(cuerpo + inventario(c), encoding="utf-8", newline="\n")
    print(f"Interpretación en {ruta}")


if __name__ == "__main__":
    principal()
