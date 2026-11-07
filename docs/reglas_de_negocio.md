# Reglas de negocio

Estas son las definiciones que hay que tener delante para leer las cifras. La empresa, Casa Mayor Inversiones, es ficticia, y
los datos son públicos y reales. Lo que no sale de los datos ni de las normas va marcado como supuesto.

## 1. Qué se analiza

Un **anuncio** es la oferta publicada en Airbnb de una vivienda o de parte de ella. No es un inmueble: un mismo piso puede
tener varios anuncios y no se puede saber cuántos. Un **piso** es el anuncio de una vivienda, sin habitaciones sueltas, y se
analiza aparte de las habitaciones.

Una **descarga** es la copia de todos los anuncios de Madrid en una fecha. La fecha de referencia es el 17/09/2026. El precio
de una descarga no se compara con el de otra sin decirlo, porque el precio cambia con la temporada.

El **centro histórico** es el ámbito APE 00.01 del plan urbanístico. Un anuncio está dentro si su punto cae dentro del
límite oficial. Las coordenadas vienen desplazadas hasta 150 m, así que cerca del borde su lado no se puede asegurar.

## 2. Cómo se calcula la rentabilidad

- **Precio por noche:** el que publica el anuncio. Desde 2026 es un precio para unas fechas concretas, ya con las
  rebajas del anfitrión, de modo que no se compara con 2025 y no es el precio medio del año.
- **Ocupación:** días al año que estima la fuente: reseñas del último año × 2 × el mayor entre 3 y la estancia mínima, con
  máximo de 255 días. Es una estimación y no incluye noches reales vendidas. Un cero significa que no hay reseñas en el último
  año, no que el piso esté vacío.
- **Ingreso anual:** precio por noche × ocupación.
- **Superficie (supuesto):** hasta 1 habitación, 50 m²; 2 habitaciones, 65 m²; 3 habitaciones, 90 m² con menos de 2 baños y
  110 m² con 2 o más; más de 3 habitaciones o 3 baños o más, 140 m².
- **Precio oficial del m²:** el precio declarado de 2025 que publica el Ayuntamiento, con datos del Colegio de Registradores.
  San Andrés, Ambroz y Aeropuerto toman el de su distrito.
- **Precio de compra:** superficie × precio oficial del m².
- **Precio de mercado:** el m² que piden hoy Fotocasa e Idealista en los tres barrios recomendados, consultado el 06/11/2026.
  Solo sirve para comparar: repite la compra y la rentabilidad de esos pisos. No entra en la selección de barrios.
- **Rentabilidad bruta:** ingreso anual / precio de compra, en porcentaje. No incluye gastos, impuestos, comunidad, limpieza
  ni comisiones, y no implica beneficio. La rentabilidad neta no se calcula, porque no hay fuente para cada gasto.

## 3. Qué pisos cuentan

Los **pisos analizados** son los que están fuera del centro histórico con precio entre 20 y 1.000 €, hasta 8 huéspedes,
5 baños, 5 habitaciones y 6 camas, con ocupación mayor que cero y estancia mínima de hasta 3 noches. Quedan fuera además los
de cero baños, los de un tipo que no es un piso y los de más camas o habitaciones que huéspedes.

- El precio va de 20 a 1.000 € por noche. Los dos límites son una decisión de este análisis. De los 18.785 anuncios con
  precio quedan dentro 18.573. Por debajo de 20 € hay 48, cuando solo el tramo de 20 a 25 € ya tiene 194. Por encima de
  1.000 € hay 164, y entre 500 y 1.000 € quedan 652, de modo que ese límite deja pisos de sobra. No se midió si otro
  rango cambiaría los barrios.
- Los límites de tamaño (8 huéspedes, 5 baños, 5 habitaciones y 6 camas) también son una decisión: a partir de ahí la frecuencia
  cae y ya no parece un piso para esta empresa. De los 13.412 pisos con precio en rango de toda la ciudad, esos límites quitan 323.
  Por separado son 277 por huéspedes, 21 por baños, 50 por habitaciones y 177 por camas. Los baños con medio, como 1,5, se dan
  por válidos: hay 556.
- La estancia se limita a 3 noches porque, por encima, la fórmula de la ocupación se infla, y un piso con estancia larga no
  es turístico.
- Los pisos sin ocupación salen del cálculo, porque no hay ingreso que medir, y su peso se da como riesgo.
- Los anuncios sin días libres se quedan: son los más alquilados. Por eso no hay filtro de disponibilidad.

La **base de comparación** repite los filtros de un análisis habitual de este mercado, con al menos 180 días disponibles y
todos los tipos de alquiler. Solo sirve para ver qué cambia con ese filtro.

## 4. Cómo se forma la lista de barrios

La **lista** son los barrios que quedan en el 25 % más rentable en más de 6 de 12 repeticiones del cálculo: estancia de hasta 3 o
hasta 6 noches, mínimo de 30 o de 20 anuncios, y precio de marzo, junio o septiembre.

Después se repiten esas 12 de cinco maneras: sin los pisos que declaran temporada, sin los de anfitriones con 10
anuncios o más, sin los precios para fechas a más de 60 días, solo con 1 y 2 habitaciones, y contando los pisos sin ocupación como
cero. Esos pisos siguen en el análisis: estas repeticiones solo miden si los barrios siguen en la lista.

- Se recomiendan los barrios que siguen en la lista las cinco veces. Eso no significa que rindan más.
- Los que siguen cuatro veces se dicen aparte, con la repetición en la que salen.

Cada barrio lleva además tres avisos: depende del máximo de días, si sale de la lista sin sus pisos en 255 días; pocos anuncios, si tiene
40 o menos; y uno de cada cuatro rinde poco, si el corte de su peor 25 % no supera el de todos los pisos.

Por debajo de 30 anuncios un barrio no se ordena. Entre barrios se mira si la diferencia se puede asegurar, con su intervalo del 95 %,
y no su orden.

## 5. Cómo se lee

Conviene no confundir estas parejas:

- anuncio e inmueble;
- estar fuera del centro histórico y poder obtener licencia: estar fuera solo significa que no aplica ese artículo. Desde el 03/04/2025 hace falta además que la comunidad de propietarios lo apruebe de forma expresa, por tres quintos de propietarios y de cuotas. La misma mayoría puede prohibirlo o subir la cuota hasta un 20 % (Ley 49/1960, arts. 7.3 y 17.12). Una vivienda sometida a algún régimen de protección pública no puede ser vivienda turística (art. 17 ter.3 del Decreto 79/2014, añadido por el Decreto 27/2026), y la declaración responsable manifiesta que no lo está (art. 17 bis, letra h). Esa declaración manifiesta también que se cuenta con dos certificados: uno de que el título constitutivo o los estatutos de la comunidad no prohíben la actividad, y otro de que la comunidad ha aprobado la solicitud (art. 17 bis, letras f y g);
- ocupación estimada y noches vendidas;
- rentabilidad bruta y beneficio;
- precio declarado y precio de oferta.

Ninguna diferencia entre barrios se presenta como causa. Ningún resultado decide sobre una persona: se dan por barrio y tipo
de piso, con su mínimo de casos.

Las normas que enmarcan el análisis son el Plan RESIDE (BOCM 226, de 22/09/2025), el Decreto 27/2026 de la Comunidad de Madrid
(BOCM 80, de 06/04/2026) y el Real Decreto 1312/2024 (BOE de 24/12/2024). Este repositorio no es asesoramiento jurídico.
