# Los datos

El repositorio publica lo mínimo para que cualquiera compruebe la respuesta. Son datos públicos y reales, con anfitriones que
pueden ser personas físicas, así que lo que entra se decidió fuente por fuente.

## Qué hay en el repositorio

| Carpeta | Contenido | Peso | Por qué |
|---|---|---|---|
| `data/raw/externos/` | 10 ficheros del Ayuntamiento de Madrid | 302 KB | se pueden reutilizar citando la fuente, y hacen falta para repetir el análisis |
| `informes/` | las tres salidas y los JSON de los que salen sus cifras | 1,2 MB | se leen sin ejecutar nada |

Las descargas de Inside Airbnb no están, ni una tabla derivada con una fila por piso. Sus [condiciones](https://insideairbnb.com/data-policies/) piden no volver a publicar
los datos, descargarlos una vez y citar la fuente. Pesan unos 40 MB ya sin las columnas personales. `scripts/descargar_datos.py`
guarda la dirección y la huella SHA-256 de cada fichero, y para si la huella no coincide.

## La tabla local

`python ejecutar.py --completo` deja en `data/publicado/pisos_fuera_del_centro.csv.gz`, sin versionar, la tabla con la que un segundo script rehace las cifras de portada. Tiene una fila por piso fuera del centro histórico que entra en alguna
repetición del análisis, barajadas y sin clave.

| Columna | Qué es |
|---|---|
| `barrio` | barrio, u `otros` si tiene menos de 20 pisos en la tabla |
| `dormitorios` | número de habitaciones |
| `estancia_hasta_3` | 1 si la estancia mínima es de hasta 3 noches; si no, es de 4 a 6 |
| `temporada` | 1 si el anuncio declara alquiler de temporada |
| `anfitrion_10_o_mas` | 1 si el anfitrión tiene 10 anuncios o más |
| `lejana_sep`, `lejana_mar`, `lejana_jun` | 1 si el precio de esa descarga es para fechas a más de 60 días |
| `rent_sep_pct`, `rent_mar_pct`, `rent_jun_pct` | rentabilidad bruta con el precio de esa descarga; vacía si el precio falta o está fuera del rango de 20 a 1.000 €, y cero si no hay ocupación |
| `ingreso_sep_eur` | ingreso anual estimado con el precio de septiembre |
| `compra_eur` | superficie supuesta × precio oficial del m² |

## Qué se quitó y por qué

- Número de anuncio: fuera. Con él se llega a la página pública del anuncio y, desde ella, al anfitrión. La tabla no lleva
  ninguna clave con la que unirla a otra.
- Coordenadas: fuera. El barrio basta para las tres preguntas.
- Recuento de anuncios por anfitrión: fuera. Queda un sí o no, que es lo único que usa la regla.
- Precio y ocupación: fuera. Son datos de la fuente, y la portada solo necesita lo calculado con ellos.
- Barrios con pocos pisos: se agrupan como `otros`, para que ninguna fila quede sola en su barrio. No cambian la lista,
  porque ninguna repetición ordena un barrio con menos de 20 pisos.

Antes del análisis salieron además 16 columnas de cada descarga: las del anfitrión que lo identifican, los enlaces, las fotos, el
nombre del anuncio y su descripción. El número de licencia quedó reducido a su tipo. De las reseñas solo quedan el anuncio y la
fecha, y las licencias municipales llegan sin dirección, punto ni expediente. Eso se hace en local y no se publica. Es una
supresión sin códigos con clave, de modo que no hay seudonimización que deshacer.

## Riesgo que queda

Cada fila sigue siendo un anuncio. Quien tuviera las descargas de Inside Airbnb podría intentar localizar una fila cruzando barrio,
habitaciones e ingreso, y solo llegaría a un anuncio que ya es público en Airbnb. La tabla no añade ningún dato sobre una
persona, y ningún resultado decide sobre nadie. Es un criterio técnico y no sustituye a un delegado de protección de datos.

## Fuentes y atribución

- El documento municipal sobre licencias que cita `scripts/diccionario_datos.py` (`normas/vut_doc.pdf`) no está en el repositorio.
- Fotocasa e Idealista: precio del m² en venta de los barrios de Ventas, Numancia y San Diego, consultado el 06/11/2026, en
  `config/fuentes/precios_de_mercado.json`.
- Inside Airbnb: datos de Madrid, descargas del 14/12/2025, 24/03/2026, 20/06/2026 y 17/09/2026, con licencia
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). [Descarga](https://insideairbnb.com/get-the-data/).
- Ayuntamiento de Madrid: «Origen de los datos: Ayuntamiento de Madrid». Portal de [datos abiertos](https://datos.madrid.es/),
  con sus [condiciones de uso](https://datos.madrid.es/pages/condiciones-de-uso), y Geoportal para los puntos de interés y el límite del centro histórico. Las licencias de vivienda turística son de 2026.
- Colegio de Registradores de España: origen del precio declarado y de la superficie de 2025 que publica el Ayuntamiento.

El recuento de junio de 2025, 26.004 anuncios, se anotó cuando esa descarga se podía consultar. Ya no se puede descargar, va como
contexto y no entra en ninguna cifra de la respuesta.

El código va con licencia MIT. La licencia no cubre los datos, que conservan la de su fuente.
