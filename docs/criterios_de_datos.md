# Criterios de datos

Cada fila es un criterio que las reglas de negocio no recogían. Se fijó con los datos delante: se midió si cambiaba alguna
respuesta y se dejó escrito. Los códigos CP son los que aparecen en el código y en los informes técnicos.

| Código | Asunto | Decidido | Por qué |
|---|---|---|---|
| CP-001 | precio vacío | sigue vacío | un vacío no se rellena, y el precio de otra descarga es el de otras fechas |
| CP-002 | anuncios que Airbnb no ha actualizado en la última descarga | se quedan | son pisos válidos y de los más alquilados; quitarlos sesgaría la lista |
| CP-003 | Aeropuerto sin precio propio | toma el de su distrito | igual que San Andrés y Ambroz; no cambia ninguna respuesta |
| CP-004 | siete barrios escritos de otra forma | se unen por su nombre | son los mismos barrios; sin unirlos, 67 pisos quedarían sin precio |
| CP-005 | barrio de Casco Histórico de Vallecas | precio del barrio | es la regla general y no cambia el grupo; va como riesgo, porque Airbnb junta en él lo que el Ayuntamiento separa |
| CP-006 | camas vacías | no cuentan para el máximo de camas | no cambia ninguna respuesta |
| CP-007 | cero baños | salen | dudosos en un piso; no cambian ninguna respuesta |
| CP-008 | tipo que no es un piso | salen | no son pisos; no cambian ninguna respuesta |
| CP-009 | tamaños incoherentes | salen | más camas o habitaciones que huéspedes; no cambian ninguna respuesta |
| CP-010 | estancias de más de 365 noches | salen por el filtro de estancia | no hace falta otra regla |
| CP-011 | puntos de interés fuera de Madrid | salen | 2 puntos sin relación con el análisis |
| CP-012 | escritura de las licencias | se normaliza | solo mejora el recuento por barrio |
| CP-013 | columnas enteras vacías | salen de las tablas de trabajo | no traen nada |
| CP-014 | polígono inválido de Campamento | se repara | hace falta para el mapa |
