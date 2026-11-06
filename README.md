English version: [README.en.md](README.en.md)

# Dónde buscar pisos para alquiler turístico en Madrid

Una empresa ficticia quiere comprar pisos en Madrid para alquilarlos a turistas y necesita saber por dónde empezar. Este
análisis responde con datos públicos de Airbnb y del Ayuntamiento de Madrid.

**Resultado:** conviene mirar primero pisos de hasta 2 habitaciones en tres barrios de Madrid: Ventas (distrito de Ciudad
Lineal), Numancia y San Diego (los dos en el distrito de Puente de Vallecas). El 17/09/2026 había 256 anuncios con esas
condiciones, de los 2.940 pisos analizados. En mediana, cada piso costaría 161.973 € al precio oficial de 2025 e ingresaría
21.675 € al año. Calculada piso a piso, la mediana de la rentabilidad bruta es del 12,1 %, antes de gastos e impuestos.

Esta lista dice dónde buscar, pero no si un piso concreto se puede alquilar a turistas. Eso depende de la normativa
urbanística. Hay que comprobarlo piso a piso en el Ayuntamiento. Los días ocupados son además una estimación de Inside Airbnb,
con un máximo de 255 días al año.

Si se quitan los pisos que llegan a ese máximo, los tres barrios salen de la lista.

**El precio de compra es el oficial de 2025, y hoy el mercado pide más.** Con los precios que piden Fotocasa e Idealista,
la compra en mediana sube a 171.600 € y 182.000 €, y la rentabilidad bruta baja al 10,9 % y al 10,6 %. Son precios de anuncio,
así que la compra real quedaría algo por debajo.

[![CI](https://github.com/jleonceo/alquiler-turistico-madrid/actions/workflows/ci.yml/badge.svg)](https://github.com/jleonceo/alquiler-turistico-madrid/actions/workflows/ci.yml)

```bash
git clone https://github.com/jleonceo/alquiler-turistico-madrid.git && cd alquiler-turistico-madrid
pip install -r requirements.txt
python ejecutar.py --completo
```

Hace falta Python 3.13.

El último comando descarga los 240 MB originales de Inside Airbnb, repite todo el análisis, recalcula
las cifras de esta página y ejecuta las pruebas. El PDF del informe ejecutivo necesita Microsoft Edge. Sin él, se conserva el
que ya está en el repositorio.

## Las tres entregas

- [Informe ejecutivo](https://jleonceo.github.io/alquiler-turistico-madrid/informes/informe_ejecutivo.html): tres páginas para
  la dirección, también [en PDF](informes/informe_ejecutivo.pdf).
- [Informe final](https://jleonceo.github.io/alquiler-turistico-madrid/informes/informe_final.html): el análisis completo, con
  sus gráficos.
- [Cuadro de mando](https://jleonceo.github.io/alquiler-turistico-madrid/informes/cuadro_mando.html): para que el equipo que
  valora los pisos compare los barrios.

![Primera pantalla del cuadro de mando, con la recomendación y sus cifras](docs/img/cuadro_de_mando.png)

Las cuatro cifras grandes de la imagen son de todos los pisos analizados. Las de los tres barrios están en la tabla de la derecha.

## Por qué no se mira todo Madrid

De los 23.109 anuncios de Airbnb en la ciudad, 14.150 están en el centro histórico, donde el Ayuntamiento, con el Plan RESIDE,
no admite pisos turísticos en edificios residenciales. Por eso el análisis usa los pisos de fuera del centro.
Se usan los anuncios de 20 a 1.000 € por noche. Esos límites los fija este análisis: por debajo de 20 € casi no hay anuncios
y por encima de 1.000 € solo hay 164. Dentro quedan 18.573 de los 18.785 anuncios con precio. Después se aplican los demás
filtros, como el tamaño, la estancia mínima y la ocupación, y quedan los 2.940 pisos.

## Cómo se eligieron los barrios

La rentabilidad bruta de un piso es su ingreso anual dividido entre lo que costaría comprarlo. El ingreso es el precio por
noche multiplicado por los días ocupados que estima Inside Airbnb. El precio de compra sale de una superficie supuesta y del
precio oficial del m² del barrio.

Si se comprara un 25 % por debajo de ese precio, la rentabilidad subiría al 16,2 %. Ese descuento es un supuesto sin datos detrás:
frente a los precios que se piden hoy, sería una rebaja de entre el 29 % y el 33 %.

Los barrios se ordenaron por rentabilidad y se miró cuáles quedaban en el 25 % más rentable. Ese orden cambia según la
estancia mínima o el mes del precio. Por eso el cálculo se repitió 12 veces, con distintos valores. Se quedaron los 9 barrios
que salieron en ese 25 % en más de la mitad de las repeticiones.

Después se comprobó si esos 9 barrios dependían de un grupo concreto de anuncios. El cálculo se repitió de cinco maneras más,
por ejemplo sin los anfitriones que tienen 10 anuncios o más. Los barrios de Ventas, Numancia y San Diego siguieron en la lista
las cinco veces.

Se recomiendan por eso: ninguno rinde claramente más que los otros barrios de la lista. Numancia rinde más que
la mediana de todos los pisos analizados, pero en Ventas y San Diego no se puede asegurar. Los barrios de Casco Histórico de Vallecas y Opañel rinden más que San Diego, pero salen de la lista si se quitan los anfitriones
con 10 anuncios o más.

![Mapa de Madrid con los barrios seleccionados](docs/img/mapa_de_barrios.png)

`python ejecutar.py --completo` imprime este resumen:

```text
Pisos analizados, datos del 17/09/2026: 2.940
Barrios que rinden más: 9
De ellos, siguen en la lista en las 5 repeticiones: Numancia, San Diego y Ventas
Siguen en 4 de 5: Casco Histórico de Vallecas y Opañel

Pisos de hasta 2 habitaciones en los barrios de Numancia, San Diego y Ventas: 256 anuncios
  Precio de compra, en mediana: 161.973 €
  Ingreso al año, en mediana: 21.675 €
  Rentabilidad bruta: 12,1 %
  Rentabilidad bruta si la compra baja un 25 %, un supuesto: 16,2 %
  Con los precios que pide hoy Fotocasa: compra de 171.600 € y rentabilidad bruta de 10,9 %
  Con los precios que pide hoy Idealista: compra de 182.000 € y rentabilidad bruta de 10,6 %
  Rentabilidad de todos los pisos de esos barrios, según el mes del precio y el descuento: de 10,8 % a 15,4 %

Estas cifras coinciden con las del análisis y con las de esta página, en español y en inglés.
```

## El precio de compra de hoy

| Barrio | Oficial, escrituras de 2025 | Fotocasa | Idealista |
|---|---|---|---|
| Ventas | 4.133 €/m² | 4.825 €/m² | 4.816 €/m² |
| Numancia | 3.239 €/m² | 3.432 €/m² | 3.640 €/m² |
| San Diego | 3.078 €/m² | 3.388 €/m² | 3.489 €/m² |

Los precios de los portales se consultaron el 06/11/2026 y solo se comparan en estos tres barrios.

## Cómo está hecho

Catorce scripts de Python hacen el trabajo, desde la descarga hasta las tres entregas: calidad, corrección, cruces,
exploración, indicadores e informes. Las tres entregas toman sus cifras de un único fichero,
[indicadores.json](informes/indicadores.json).
[Un segundo script](scripts/rehacer_portada.py) rehace la selección de barrios y las medianas de esta página desde una tabla
local, sin compartir código con el análisis. Las pruebas además recalculan los indicadores por otro camino.

El detalle está en [el método](docs/metodo.md), [las reglas de negocio](docs/reglas_de_negocio.md),
[los criterios de datos](docs/criterios_de_datos.md) y [los datos](docs/datos.md).

## Los datos

| Fuente | Qué aporta | Licencia | Dónde está |
|---|---|---|---|
| [Inside Airbnb](https://insideairbnb.com/get-the-data/), Madrid | anuncios, calendario, reseñas y límites de barrio | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | se descarga aparte |
| [Ayuntamiento de Madrid](https://datos.madrid.es/) | precio y superficie de 2025, ventas, licencias, centro histórico y puntos de interés | reutilización con cita | `data/raw/externos/` |
| Colegio de Registradores de España | origen del precio y la superficie que publica el Ayuntamiento | se cita junto al Ayuntamiento | `data/raw/externos/` |
| [Fotocasa](https://www.fotocasa.es/fotocasa-life/sector/evolucion-del-precio-de-la-vivienda-en-madrid/) e [Idealista](https://www.idealista.com/maps/madrid/) | precio del m² que se pide hoy en los tres barrios, solo para comparar | se cita la fuente | `config/fuentes/precios_de_mercado.json` |

Los datos de Inside Airbnb no están aquí porque [su política](https://insideairbnb.com/data-policies/) pide no volver a
publicarlos. Se descargan de su web al repetir el análisis.

## Límites

- No se conoce la planta ni el acceso de cada piso.
- Con los anuncios de un año o más, San Diego baja al puesto 8 de 26 barrios en rentabilidad.
- La superficie de cada piso es un supuesto: 50 m² hasta 1 habitación, 65 m² con 2 y más con 3 o más. Por eso no se puede decir
  qué rinde más: un estudio, una habitación o dos.
- Solo cuentan los pisos con ocupación estimada, o sea con reseñas en el último año. Quedan fuera los que no funcionan, lo que
  puede subir la rentabilidad.
- No se ha medido si otro rango de precio cambiaría los barrios.
- La rentabilidad no incluye gastos, impuestos, comunidad ni comisiones.
- Los barrios se eligieron con el precio declarado en 2025. No se ha medido si cambiarían con los precios de hoy.
- Un anuncio de alquiler no significa que ese piso esté en venta.
- Repetir el análisis completo depende de que Inside Airbnb siga ofreciendo estas descargas.

## Repositorios relacionados

- [accident-intelligent-agent](https://github.com/jleonceo/accident-intelligent-agent): otro análisis con datos abiertos de
  Madrid, los accidentes de tráfico de 2020.
- [de-datos-en-bruto-a-decisiones](https://github.com/jleonceo/de-datos-en-bruto-a-decisiones): de un fichero de ventas sin tratar
  a un cuadro de mando.
- [lead-scoring-ml](https://github.com/jleonceo/lead-scoring-ml): un caso completo de machine learning para puntuar contactos
  comerciales.
