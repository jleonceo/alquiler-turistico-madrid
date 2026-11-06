# Los datos

El repositorio publica lo mínimo para que cualquiera compruebe la respuesta. Son datos públicos y reales, con anfitriones que
pueden ser personas físicas, así que lo que entra se decidió fuente por fuente.

## Qué hay en el repositorio

| Carpeta | Contenido | Peso | Por qué |
|---|---|---|---|
| `data/raw/externos/` | 10 ficheros del Ayuntamiento de Madrid | 324 KB | se pueden reutilizar citando la fuente, y hacen falta para repetir la cadena |
| `informes/` | las tres salidas y los JSON de los que salen sus cifras | 1,2 MB | se leen sin ejecutar nada |

Las fotos de Inside Airbnb no están, ni una tabla derivada con una fila por piso. Sus [condiciones](https://insideairbnb.com/data-policies/) piden no volver a publicar
los datos, descargarlos una vez y citar la fuente. Pesan unos 40 MB ya sin las columnas personales. `scripts/descargar_datos.py`
guarda la dirección y la huella SHA-256 de cada fichero, y para si la huella no coincide.

## La tabla local

`python ejecutar.py --completo` deja en `data/publicado/pisos_fuera_del_centro.csv.gz`, sin versionar, la tabla con la que un segundo script rehace las cifras de portada. Tiene una fila por piso fuera del centro histórico que entra en alguna
variante del análisis, barajadas y sin clave.

| Columna | Qué es |
|---|---|
| `barrio` | barrio, u `otros` si tiene menos de 20 pisos en la tabla |
| `dormitorios` | número de habitaciones |
| `estancia_hasta_3` | 1 si la estancia mínima es de hasta 3 noches; si no, es de 4 a 6 |
| `temporada` | 1 si el anuncio declara alquiler de temporada |
| `anfitrion_10_o_mas` | 1 si el anfitrión tiene 10 anuncios o más |
| `lejana_sep`, `lejana_mar`, `lejana_jun` | 1 si la cotización de esa foto es a más de 60 días |
| `rent_sep_pct`, `rent_mar_pct`, `rent_jun_pct` | rentabilidad bruta con descuento con el precio de esa foto; vacía si el precio falta o sale de 20 a 1.000 €, y cero si no hay ocupación |
| `ingreso_sep_eur` | ingreso anual estimado con el precio de septiembre |
| `compra_sin_descuento_eur` | superficie supuesta × precio oficial del m² |

## Qué se quitó y por qué

- Número de anuncio: fuera. Con él se llega a la página pública del anuncio y, desde ella, al anfitrión. La tabla no lleva
  ninguna clave con la que unirla a otra.
- Coordenadas: fuera. El barrio basta para las tres preguntas.
- Recuento de anuncios por anfitrión: fuera. Queda una marca de sí o no, que es lo único que usa la regla.
- Precio y ocupación: fuera. Son datos de la fuente, y la portada solo necesita lo calculado con ellos.
- Barrios con pocos pisos: se agrupan como `otros`, para que ninguna fila quede sola en su barrio. No cambian la lista,
  porque ninguna variante ordena un barrio con menos de 20 pisos.

Antes del análisis salieron además 16 columnas de cada foto: las del anfitrión que lo identifican, los enlaces, las fotos, el
nombre del anuncio y su descripción. El número de licencia quedó reducido a su tipo. De las reseñas solo quedan el anuncio y la
fecha, y las licencias municipales llegan sin dirección, punto ni expediente. Eso se hace en local y no se publica. Es una
supresión sin códigos con clave, de modo que no hay seudonimización que deshacer.

## Riesgo que queda

Cada fila sigue siendo un anuncio. Quien tuviera las fotos de Inside Airbnb podría intentar localizar una fila cruzando barrio,
habitaciones e ingreso, y solo llegaría a un anuncio que ya es público en Airbnb. La tabla no añade ningún dato sobre una
persona, y ningún resultado decide sobre nadie. Es un criterio técnico y no sustituye a un delegado de protección de datos.

## Fuentes y atribución

- Inside Airbnb: datos de Madrid, fotos del 14/12/2025, 24/03/2026, 20/06/2026 y 17/09/2026, con licencia
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). [Descarga](https://insideairbnb.com/get-the-data/).
- Ayuntamiento de Madrid: «Origen de los datos: Ayuntamiento de Madrid». Portal de [datos abiertos](https://datos.madrid.es/),
  con sus [condiciones de uso](https://datos.madrid.es/pages/condiciones-de-uso), y Geoportal para los puntos de interés y el límite del centro histórico. Las licencias de vivienda turística son de 2026.
- Colegio de Registradores de España: origen del precio declarado y de la superficie de 2025 que publica el Ayuntamiento.

El recuento de junio de 2025, 26.004 anuncios, se anotó cuando esa foto se podía consultar. Ya no se puede descargar, va como
contexto y no entra en ninguna cifra de la respuesta.

El código va con licencia MIT. La licencia no cubre los datos, que conservan la de su fuente.
