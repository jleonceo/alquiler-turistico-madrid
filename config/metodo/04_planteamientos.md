# Planteamientos

Lo que se calcula para cada pregunta quedó escrito aquí antes de calcular. `scripts/indicadores.py` lo lee y para si falta
la decisión, la referencia, el mínimo o la población. La población de las tres preguntas es la base de decisión, una fila por
anuncio, con la foto del 17/09/2026. La unidad es el anuncio, que no es un inmueble.

## Pregunta 1 · Qué tipo de piso rinde más

- Decisión: qué habitaciones y qué tipo de inmueble busca valoraciones.
- Medida: rentabilidad bruta mediana por habitaciones, con la superficie de valoraciones. Al lado, los euros al año.
- Referencia: la mediana de toda la base.
- Mínimo: 30 anuncios por grupo.
- Comparación: intervalo del 95 % de la diferencia de medianas, con 2.000 remuestreos y semilla fija.
- Qué cambia la decisión: si dos tipos no se distinguen, se dan los dos.

## Pregunta 2 · En qué barrios

- Decisión: dónde concentra la búsqueda el equipo de valoraciones.
- Medida: rentabilidad bruta mediana por barrio y las doce variantes de las reglas §3.
- Referencia: la mediana de los barrios con 30 anuncios o más.
- Mínimo: 30 anuncios en la base; 20 solo en las variantes que lo fijan.
- Salida: barrios con 5, 4 o menos pruebas superadas, cada barrio con recuento, cuartil bajo, parte de pisos en el tope de
  ocupación, las cinco pruebas que aguanta y sus tres avisos.
- Qué cambia la decisión: la clase de cada barrio sale de las cinco pruebas, y sus tres avisos se escriben al lado.

## Pregunta 3 · Con qué riesgo

- Decisión: qué barrios se miran con más cuidado.
- Medida: recuento, cuartil bajo, rango de la mediana entre las tres fotos de precio, y barrios que se distinguen del
  primero con el mismo intervalo.
- Referencia: el mismo cálculo para toda la base.
- Rango de rentabilidad bruta: el del grupo recomendado y, aparte, el de recomendados más los que siguen en la lista 4 veces, de la fecha del
  precio más baja a la más alta.
- Pisos sin ocupación: su parte en cada barrio del grupo, como riesgo.
- Mínimo: 30 anuncios.
- Qué cambia la decisión: un barrio del grupo que dependa del tope de 255 días o de pocos anuncios se dice así.

## Añadido tras revisar la preparación de los datos

Este apartado se escribió después de auditar la preparación y antes de rehacer los scripts. Sus medidas no se eligieron a
ciegas, y por eso se separa de lo escrito antes de calcular.

### Las cinco pruebas del grupo

Cada una repite las 12 variantes y cambia una sola cosa; quien sigue en más de 6 aguanta la prueba. Esos pisos se quedan en
la base: las pruebas solo miden si la lista aguanta.

1. Sin los pisos que declaran temporada.
2. Sin los pisos de anfitriones con 10 anuncios o más.
3. Sin las cotizaciones a más de 60 días. Cada variante usa los días de la foto de la que toma el precio.
4. Solo con los pisos de 1 y 2 habitaciones.
5. Contando los pisos sin ocupación como cero. Se les aplican los demás filtros de cada variante, también el del precio.

### Sensibilidad de superficie

- Decisión: si el supuesto de superficie cambia los tipos que se dan en la pregunta 1.
- Medida: la misma comparación de la pregunta 1, con el estudio entre 35 y 50 m², 1 habitación entre 45 y 60 y
  2 habitaciones entre 60 y 75, en las ocho combinaciones de esos extremos.
- Referencia: los tipos que se dan con la superficie de valoraciones.
- Mínimo: 30 anuncios por grupo.
- Qué cambia la decisión: si en alguna combinación se dan otros tipos, se dice cuál y el tipo deja de darse como recomendado.

### Referencia del grupo: los barrios de m² más barato

- Decisión: si la regla del grupo aporta algo frente a elegir por precio de compra.
- Medida: cuántos barrios del grupo están entre los de m² oficial más barato, tomando tantos como barrios tiene el grupo.
- Referencia: esa lista, entre los barrios comparados con 30 pisos o más y, aparte, en toda la ciudad.
- Mínimo: 30 anuncios en la lista de los comparados.
- Qué cambia la decisión: si coinciden casi todos, el grupo apenas añade nada al precio del m², y se dice.

## Las 16 preguntas de comprobación

Sostienen las tres de arriba y se comprueban una a una en las dos bases. Los factores son asociaciones y la competencia
cuenta solo anuncios de Airbnb. Los niveles de ocupación son 1-85, 86-170, 171-254 y 255 días.
