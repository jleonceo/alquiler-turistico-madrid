# Método

El análisis contesta tres preguntas: qué tipo de piso rinde más, en qué barrios conviene buscarlo fuera del centro histórico y
con qué riesgo. No hay modelo predictivo: son técnicas descriptivas que se pueden explicar. Una asociación no se presenta como
causa. Lo que se calcula para cada pregunta quedó escrito en
[los planteamientos](../config/metodo/04_planteamientos.md) antes de calcular.

## La cadena

Cada script deja un informe técnico y un JSON con sus cifras, y el siguiente comprueba la huella de lo que recibe. Si algo no
cuadra, la cadena para sin escribir.

| Paso | Script | Qué hace |
|---|---|---|
| 1 | `descargar_datos.py` | trae las fotos una vez, comprueba su huella y quita lo personal |
| 2 | `diccionario_datos.py` | describe las 344 columnas de las 12 tablas de origen |
| 3 | `calidad_datos.py` | mide vacíos, duplicados, atípicos y coherencia, y qué asuntos cambian la respuesta |
| 4 | `correccion_datos.py` | aplica los [criterios de datos](criterios_de_datos.md) sin quitar anuncios |
| 5 | `modelo_datos.py` | comprueba claves y cardinalidades de las 11 tablas |
| 6 | `integracion_datos.py` | hace los 7 cruces y comprueba que ninguno gana ni pierde filas |
| 7 | `transformacion_datos.py` | calcula la rentabilidad y deja las exclusiones como marcas |
| 8 | `analisis_exploratorio.py` | describe las dos tablas de análisis |
| 9 | `indicadores.py` | contesta las tres preguntas y 16 de comprobación, cada cifra por dos caminos |
| 10 | `interpretacion_resultados.py` | escribe la lectura para la dirección |
| 11 | `informe_ejecutivo.py` | monta el informe de dos páginas y su PDF |
| 12 | `informe_final.py` | monta el informe completo con sus gráficos |
| 13 | `cuadro_mando.py` | monta el cuadro de mando, un HTML que no pide nada de fuera |
| 14 | `tabla_publicada.py` | deja en local, en `data/publicado/`, la tabla sin datos identificativos |

`reglas_caso.py` y `cifras_informes.py` son piezas comunes, y `assets/` guarda las piezas de gráficos e informes.

## Decisiones que importan

- Ningún anuncio sale de la tabla. Las exclusiones son marcas, y cada una se cuenta. Así se ve qué pesa cada filtro.
- Quitar pisos con menos de 180 días libres cambia los barrios. Ese filtro habitual deja fuera a los más alquilados, y por
  eso solo se usa en la base de comparación.
- La estancia vacía se toma del calendario. En septiembre 1.729 anuncios no la publican. La menor estancia del calendario
  coincide con la publicada en el 91,1 % de los 3.175 pisos que traen las dos, y el lado de las 3 noches, en el 96,6 %.
- Los vacíos no se rellenan. Un precio vacío sigue vacío, porque el de otra foto es otra cotización.
- Se compara con intervalo y no con el orden. Con 36 barrios comparables el azar da diferencias aparentes, y por eso cada
  comparación lleva su intervalo del 95 %, con 2.000 remuestreos y semilla fija.

## Cómo se comprueba

- Dos caminos por cifra. `tests/probar_indicadores_por_otro_camino.py` rehace los indicadores sin pandas ni los scripts de
  la cadena.
- Una portada que se rehace sola. `scripts/rehacer_portada.py` usa solo la biblioteca estándar y la tabla local, y falla
  si una cifra de los README se separa de la cadena.
- Casos que tienen que fallar. Las pruebas de `tests/` montan un caso pequeño inventado con defectos plantados, y varias
  llevan controles que tienen que salir en rojo. Las que abren datos reales se saltan en un clon limpio y lo dicen.
- Las salidas no se escriben si dejan de ser ciertas. Cada frase del informe comprueba la cifra que la sostiene, y cada número
  queda apuntado con la clave de la que sale.
