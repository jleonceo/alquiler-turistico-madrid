"""Interpretación de los resultados del caso para la Dirección de Inversiones.

Lee informes/indicadores.json y deja informes/interpretacion_resultados.md. No calcula cifras: las lee por su clave y deja
su ruta en informes/interpretacion_rastro.json. Va en un script para que ninguna cifra se escriba a mano.

Ejecución:
  PYTHONUTF8=1 python -W error scripts/interpretacion_resultados.py
Opciones: --indicadores <json>, --salida <carpeta>. Las usa tests/probar_interpretacion_resultados.py.
"""
import argparse
import datetime
import json
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
    rango = f"{Q3}.rango_de_rentabilidad_de_recomendados"
    rango2 = f"{Q3}.rango_de_rentabilidad_de_recomendados_y_cuatro_de_cinco"
    baratos = f"{Q2}.referencia_baratos.comparados"
    cuartil_base = c.pct(f"{Q2}.cuartil_bajo_de_toda_la_base", 2)
    acciones = ci.acciones(c)
    filas_acciones = "\n".join(f"| {a['nombre']} | {a['quien']} | {a['cuando'][0].upper() + a['cuando'][1:]} | {r} |" for a, r in zip(acciones, (
        "Cada barrio de la lista queda con una respuesta del Ayuntamiento sobre planta, acceso y norma, y cada piso con la de su comunidad.",
        "La rentabilidad bruta de cada oportunidad se rehace con su superficie real.",
        "Se comprueba si cada barrio sigue en la lista con la descarga nueva.")))
    return f"""# Buscar primero pisos de hasta 2 habitaciones en los tres barrios recomendados

Emitido el {hoy}. Datos de la descarga del {ci.fecha_es(c.dato('fecha_datos'))}. El origen de cada cifra está en `informes/interpretacion_rastro.json`.

## Pregunta y objetivo

La Dirección de Inversiones decide dónde concentra la búsqueda de pisos para alquiler turístico en Madrid, y el equipo de valoraciones decide qué oportunidades estudia. La pregunta tiene tres partes: qué tipo de piso rinde más, en qué barrios conviene buscarlo fuera del centro histórico y con qué riesgo.

## Grandes números

- Recomendación: los recomendados de hasta 2 habitaciones son {c.num(REC + '.pisos')} anuncios en Airbnb, con una rentabilidad bruta de {c.pct(REC + '.rentabilidad_pct')}, calculada piso a piso, frente al {c.pct(Q2 + '.mediana_de_toda_la_base')} de todos los pisos.
- Rango: con pisos de cualquier tamaño, los tres barrios van de {c.pct(rango + '.minimo')} a {c.pct(rango + '.maximo')}, según la fecha del precio, antes de gastos e impuestos. Con los dos barrios que siguen en la lista 4 veces, de {c.pct(rango2 + '.minimo')} a {c.pct(rango2 + '.maximo')}.
- Por piso, en mediana y sin gastos: {c.eur(REC + '.compra_eur')} de compra, lo que cuesta un piso de 50 m² en el barrio de Numancia, y {c.eur(REC + '.ingreso_anual_eur')} de ingreso anual. Dividir esas dos cifras no da la rentabilidad, que se calcula piso a piso y después se resume con su mediana. Según barrio y tamaño, la compra va de {c.eur(REC + '.compra_minima_eur')} a {c.eur(REC + '.compra_maxima_eur')}.
- Lista de barrios: {c.cuantos(Q2 + '.recomendados')} recomendados y {c.cuantos(Q2 + '.cuatro_de_cinco')} que siguen en la lista 4 veces, dentro de un grupo de {c.cuantos(Q2 + '.grupo')} barrios y {c.num(Q2 + '.pisos_del_grupo')} anuncios en Airbnb.
- Planta: {c.num(PLANTA + '.licencias')} de las {c.num(PLANTA + '.de')} licencias municipales incluyen planta baja, y {c.num(PLANTA + '.recomendados.licencias')} de las {c.num(PLANTA + '.recomendados.de')} de los barrios recomendados.
- Riesgo: en uno de cada cuatro anuncios la rentabilidad no llega a {cuartil_base}, el corte de todos los pisos. Los recomendados quedan por encima, de {c.pct(ficha('Numancia', 'cuartil_bajo_pct'))} a {c.pct(ficha('Ventas', 'cuartil_bajo_pct'))}.
- Precio: los {c.num(baratos + '.de')} barrios de m² más barato dan {c.pct(ORDENA + '.m2_baratos.mediana_pct')}, los recomendados {c.pct(ORDENA + '.recomendados.mediana_pct')} y el grupo {c.pct(ORDENA + '.grupo.mediana_pct')}, sin que se pueda asegurar la diferencia. La mediana de los pisos de los tres barrios juntos no es la media de las medianas de cada barrio.

## La historia

Esta recomendación es una primera criba para saber dónde empezar a buscar. Sin los pisos que llegan al máximo de 255 días ocupados, la lista pasa a ser los barrios de {ci.lista_sin_maximo(c)}, y ninguno de los tres recomendados sigue en ella. Si un piso concreto se puede comprar para alquilarlo a turistas depende de la normativa. Buena parte de los anuncios de Airbnb está dentro del centro histórico, donde el Plan RESIDE no admite pisos turísticos en edificios residenciales. El análisis usa {c.num(Q1 + '.poblacion.filas')} pisos fuera de ese centro.

Dónde buscar primero: en los barrios de Ventas, Numancia y San Diego. El cálculo se repitió 12 veces cambiando la estancia mínima, el mínimo de anuncios por barrio o la fecha del precio. Después se repitió todo de 5 formas, quitando cada vez un grupo de anuncios, y estos tres barrios siguieron en la lista las 5 veces. Eso no significa que rindan más: el barrio de Numancia rinde más que la mediana de todos los pisos, y en los barrios de Ventas y San Diego esa diferencia no se puede asegurar con un 95 % de confianza.

Quién va detrás: los barrios de Casco Histórico de Vallecas y Opañel rinden más que el de San Diego, pero el {c.pct(Q2 + '.operadores_grandes.cuatro_de_cinco_pct', 0)} de sus anuncios es de anfitriones con 10 anuncios o más, y sin ellos salen de la lista. El barrio de Puerta del Ángel está en la lista, pero sale en las 5 formas de repetir el cálculo. La lista no ordena a los barrios.

Qué buscar: pisos de hasta 2 habitaciones. Los de 3 se calculan con 90 m² o más y no se probó otra superficie: para igualar a los de 2 habitaciones tendrían que medir unos {c.num(SUP + '.tres_habitaciones.superficie_para_igualar_a_2_m2')} m². No hay ganador entre estudio, una y dos habitaciones, porque su orden depende de la superficie supuesta. El tipo más rentable cambia en {c.num(SUP + '.combinaciones_que_cambian')} de las {c.cuantos(SUP + '.combinaciones')} superficies probadas.

Por dónde empezar: por bajos y primeras plantas con acceso independiente. Las normas dicen que, fuera del centro histórico, en el nivel B de la zona 1, la de protección del patrimonio histórico, el hospedaje cabe en planta baja, inferior a la baja y primera, y siempre con acceso independiente. No se ha comprobado si los tres barrios están en esa zona. Lo que ingresa un bajo no se conoce, porque los datos mezclan todas las plantas. Qué norma rige en cada barrio se pregunta en el Ayuntamiento antes de comprar. La comunidad de propietarios tiene que aprobarlo de forma expresa, por tres quintos de propietarios y de cuotas, y la misma mayoría puede prohibirlo o subir la cuota hasta un 20 % (Ley 49/1960, arts. 7.3 y 17.12). Una vivienda con protección pública no puede ser vivienda turística (art. 17 ter.3 del Decreto 79/2014, añadido por el Decreto 27/2026). La declaración responsable manifiesta contar con dos certificados: uno de que el título constitutivo o los estatutos no prohíben la actividad y otro de que la comunidad ha aprobado la solicitud (art. 17 bis, letras f y g, del mismo decreto). Esto no es asesoramiento jurídico.

Qué aporta la lista: elegir solo por m² barato podría rendir lo mismo. Entre los {c.num(ORDENA + '.barrios')} barrios, la rentabilidad va más ligada a los días ocupados que al precio del m²: la correlación es de {c.num(ORDENA + '.rentabilidad_con_ocupacion', 2)} frente a {c.num(ORDENA + '.rentabilidad_con_m2', 2)}, en una escala de −1 a 1. Los días ocupados son la cifra menos fiable. La lista aporta saber qué barrios siguen en ella al repetir el cálculo.

Qué riesgo queda: un barrio depende del máximo si sale de la lista al quitar los pisos que llegan a 255 días, y los tres recomendados dependen. El barrio de Opañel, con el {c.pct(ficha('Opañel', 'parte_en_el_tope_pct'), 0)} de sus pisos en el máximo, no depende. Los días ocupados salen de las reseñas del último año, y un anuncio con menos de un año ha tenido menos tiempo para recibirlas. Con los {c.num(UN_ANO + '.pisos')} anuncios de un año o más, los barrios de Numancia y Ventas quedan en los puestos {c.num(ci.puesto('Numancia'))} y {c.num(ci.puesto('Ventas'))} de {c.num(UN_ANO + '.barrios_comparados')}, y el de San Diego en el {c.num(ci.puesto('San Diego'))}.

## Nivel de confianza

**Confianza baja** en los barrios, porque la lista cambia entera sin los pisos en el máximo, y en el nivel de la rentabilidad bruta. **Media** en dejar fuera los pisos de 3 habitaciones. **No se puede saber** si un piso concreto se puede comprar para este uso.

- Muestra: Numancia, Ventas y San Diego tienen {c.num(ficha('Numancia', 'pisos'))}, {c.num(ficha('Ventas', 'pisos'))} y {c.num(ficha('San Diego', 'pisos'))} anuncios, por encima del mínimo de 30.
- Cobertura temporal: una descarga de septiembre, con el precio de marzo y junio como contraste. La temporada completa no se ve.
- Calidad: los días ocupados son una estimación con máximo de 255, y entre los pisos más ocupados no sirven para ordenar. Los tres recomendados dependen del máximo.
- Supuestos: la superficie no sale de los datos, y el precio de compra es el declarado en 2025.
- Segmentos: no hay ganador, y la ventaja de 1 habitación sobre 2 se repite en {c.num(Q1 + '.por_segmentos.distritos_donde_1_supera_a_2')} de {c.num(Q1 + '.por_segmentos.distritos_comparables_1_y_2')} distritos.
- Diseño: datos observados, sin experimento.
- Sin comprobar: noches vendidas reales, norma de cada barrio e ingreso por planta.

Prueba de refutación de cada afirmación principal:

| Afirmación | Qué la haría falsa | Resultado |
|---|---|---|
| Los tres recomendados siguen en la lista las 5 veces | que alguno saliera una vez | es cierto en esas 5; si también se cuentan como cero los pisos sin precio, solo sigue el barrio de Ventas, y sin los pisos en el máximo no sigue ninguno |
| Hasta 2 habitaciones rinden más que 3 | que un piso de 3 igualara a uno de 2 con una superficie razonable | es cierto con 90 m² o más; solo igualaría con unos {c.num(SUP + '.tres_habitaciones.superficie_para_igualar_a_2_m2')} m² |
| Los recomendados rinden más que la mediana de todos los pisos | que no se pudiera asegurar la diferencia con la mediana | se corrige: solo el barrio de Numancia la supera; en los de San Diego y Ventas no se puede asegurar |
| La lista rinde más que elegir por precio | que no se pudiera asegurar la diferencia | se corrige: no se puede asegurar, y coinciden {c.num(baratos + '.cuantos')} de {c.num(baratos + '.de')} barrios |

## Lo que no se puede afirmar

- Causalidad: todo son asociaciones sobre datos observados. Una hipótesis sigue siéndolo: la concentración en el máximo de Casco Histórico de Vallecas admite dos lecturas, muchos alquileres o una fórmula inflada, y haría falta conocer las noches vendidas.
- Segmentos: cada barrio se da con su recuento, y los totales de habitaciones se miraron por distrito.
- Terceras variables: el m² y el alquiler van juntos por distrito, y la localización puede mover los dos.
- Generalización: vale para los pisos fuera del centro histórico en esta descarga. Un anuncio no es un inmueble.
- Cambio con el tiempo: marzo y junio solo cubren los anuncios que siguen en septiembre, con la ocupación de septiembre. El rango entre fechas de precio no predice otras fechas.
- Valores extremos: se usan medianas, porque el ingreso tiene cola larga. Un barrio con 40 pisos o menos se señala aparte.
- Días ocupados: son una estimación con máximo de 255, y entre los pisos más ocupados no sirven para ordenar. Quedan fuera de la lista {c.num(Q3 + '.pisos_fuera_sin_ocupacion.pisos')} pisos sin ocupación, el {c.pct(Q3 + '.pisos_fuera_sin_ocupacion.pct')} de los pisos fuera del centro. Con esa misma población, Numancia llega al {c.pct(ficha('Numancia', 'pisos_fuera_sin_ocupacion_pct', 3))}, San Diego al {c.pct(ficha('San Diego', 'pisos_fuera_sin_ocupacion_pct', 3))} y Ventas al {c.pct(ficha('Ventas', 'pisos_fuera_sin_ocupacion_pct', 3))}. Si se cuentan como cero los pisos sin días ocupados, los tres barrios siguen en la lista. Si también se cuentan así los pisos sin precio, solo sigue el barrio de Ventas.
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
- Fecha de cada acción: por fijar.

## Fuentes

- Inside Airbnb, Madrid, descarga del 17/09/2026, con licencia CC BY 4.0.
- Origen de los datos: Ayuntamiento de Madrid, datos de 2025.
- Colegio de Registradores de España, fuente del precio declarado y de la superficie de 2025 que publica el Ayuntamiento.
- `informes/indicadores.json`, `informes/indicadores.md` y `scripts/indicadores.py`.
- `informes/analisis-exploratorio__analisis_anuncios.json` y `informes/analisis-exploratorio__analisis_barrios.json`, para las hipótesis y alertas.
- `config/metodo/06_borrador_de_hallazgos.md`.

`indicadores.md`, los dos JSON del análisis exploratorio y el borrador de hallazgos no están en el repositorio: se generan al ejecutar `python ejecutar.py --completo`.

## Datos personales

Son datos públicos, protegidos antes de llegar al caso con una supresión de columnas, sin códigos con clave. Salieron las columnas que identifican al anfitrión, los enlaces, las fotos, los textos, el nombre de quien reseña y el número de licencia, del que queda su tipo. Quedan el número del anuncio, las coordenadas, desplazadas hasta 150 m, y el recuento de anuncios por anfitrión. Los resultados se dan por barrio y tipo de piso, y ninguno decide sobre una persona.

## Límite de este documento

Solo interpreta lo que contienen los informes previos y hereda sus limitaciones. No calcula cifras, no valora un piso concreto y no sustituye a la consulta en el Ayuntamiento.
"""


def rastro(c):
    """Da cada cifra citada con su clave en indicadores.json, para el fichero que acompaña al documento."""
    return {"script": "scripts/interpretacion_resultados.py", "indicadores": "informes/indicadores.json", "rastro": c.rastro()}


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
    ruta.write_text(cuerpo, encoding="utf-8", newline="\n")
    (Path(o.salida) / "interpretacion_rastro.json").write_text(json.dumps(rastro(c), ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"Interpretación en {ruta}")


if __name__ == "__main__":
    principal()
