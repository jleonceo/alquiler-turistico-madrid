Versión en español: [README.md](README.md)

# Where to look for tourist rental flats in Madrid

A fictional company wants to buy flats in Madrid to let to tourists and needs to know where to start. This analysis answers
that question with public data from Airbnb and Madrid City Council.

**Result:** the best place to start is flats of up to 2 bedrooms in three Madrid neighbourhoods: Ventas (Ciudad Lineal
district), Numancia and San Diego (both in Puente de Vallecas). On 17/09/2026 there were 256 such listings among the 2,940
homes analysed. At the median, each flat would cost €161,973 at the official 2025 price and earn €21,675 a year. That is a
gross yield of 12.1%, before costs and taxes.

This list says where to look, but not whether a specific flat can be used as a tourist rental. That depends on planning rules
and has to be checked flat by flat with the City Council. Occupied days are also an Inside
Airbnb estimate, capped at 255 a year. If the flats at that cap are removed, the three neighbourhoods drop off the list.

[![CI](https://github.com/jleonceo/alquiler-turistico-madrid/actions/workflows/ci.yml/badge.svg)](https://github.com/jleonceo/alquiler-turistico-madrid/actions/workflows/ci.yml)

```bash
git clone https://github.com/jleonceo/alquiler-turistico-madrid.git && cd alquiler-turistico-madrid
pip install -r requirements.txt
python ejecutar.py --completo
```

It needs Python 3.13. The last command downloads the original 240 MB from Inside Airbnb, repeats the whole analysis in about five
minutes, recalculates the figures on this page and runs the tests.

## The three deliverables

The deliverables are in Spanish.

- [Executive report](https://jleonceo.github.io/alquiler-turistico-madrid/informes/informe_ejecutivo.html): three pages for
  management, also [as a PDF](informes/informe_ejecutivo.pdf).
- [Final report](https://jleonceo.github.io/alquiler-turistico-madrid/informes/informe_final.html): the full analysis, with its
  charts.
- [Dashboard](https://jleonceo.github.io/alquiler-turistico-madrid/informes/cuadro_mando.html): for the team that values the flats
  to compare neighbourhoods.

![First screen of the dashboard, with the recommendation and its figures](docs/img/cuadro_de_mando.png)

## Why not all of Madrid

Of the 23,109 Airbnb listings in the city, 14,150 are in the historic centre, where the City Council's RESIDE Plan does not
allow tourist flats in residential buildings. So the analysis uses flats outside the centre.

The analysis uses listings from €20 to €1,000 a night. Those limits are a choice: there are almost no listings below €20 and
only 164 above €1,000. That leaves 18,573 of the 18,785 listings with a price, enough for the analysis.

## How the neighbourhoods were chosen

A flat's gross yield is its annual income divided by what it would cost to buy. Income comes from the nightly price and the
occupied days estimated by Inside Airbnb. The purchase price comes from an assumed floor area and the official price per m² in
the neighbourhood. If the flat were bought 25% below that price, the yield would rise to 16.2%.

The neighbourhoods were ranked by yield to see which ones fell in the top 25%. That ranking changes with the conditions of
the calculation, such as the minimum stay or the month of the price, so it was repeated with 12 combinations. The 9 neighbourhoods that made the top
25% in more than half of them stayed.

The next check was whether those 9 depended on one particular group of listings. The calculation was run five more times,
for example without hosts who have 10 listings or more. Ventas, Numancia and San Diego stayed on the list all five times. They are recommended for that stability: none of them clearly yields more than the others on the list. Numancia beats the median
of all flats analysed, while Ventas and San Diego may not differ from it.

Casco Histórico de Vallecas and Opañel yield more than San Diego, but they drop off the list without hosts with 10 listings or
more.

![Map of Madrid with the selected neighbourhoods](docs/img/mapa_de_barrios.png)

`python ejecutar.py --completo` prints this summary, in Spanish:

```text
Pisos analizados, datos del 17/09/2026: 2.940
Barrios que rinden más: 9
De ellos, siguen en la lista en las 5 repeticiones: Numancia, San Diego y Ventas
Siguen en 4 de 5: Casco Histórico de Vallecas y Opañel

Pisos de hasta 2 habitaciones en los barrios de Numancia, San Diego y Ventas: 256 anuncios
  Precio de compra, en mediana: 161.973 €
  Ingreso al año, en mediana: 21.675 €
  Rentabilidad bruta: 12,1 %
  Rentabilidad bruta si la compra baja un 25 %: 16,2 %
  Rentabilidad de todos los pisos de esos barrios, según el mes del precio y el descuento: de 10,8 % a 15,4 %

Estas cifras coinciden con las del análisis y con las de los dos README.
```

## How it is built

Thirteen Python scripts do the work, from download to the three deliverables: quality, correction, joins, exploration, metrics
and reports. The three deliverables take their figures from a single file, [indicadores.json](informes/indicadores.json).
[A second script](scripts/rehacer_portada.py), which shares no code with the analysis, recalculates the figures on this page.

The detail, in Spanish, is in [the method](docs/metodo.md), [the business rules](docs/reglas_de_negocio.md),
[the data criteria](docs/criterios_de_datos.md) and [the data](docs/datos.md).

## The data

| Source | What it provides | Licence | Where it is |
|---|---|---|---|
| [Inside Airbnb](https://insideairbnb.com/get-the-data/), Madrid | listings, calendar, reviews and neighbourhood boundaries | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | downloaded separately |
| [Madrid City Council](https://datos.madrid.es/) | 2025 price and floor area, sales, licences, historic centre and points of interest | reuse with attribution | `data/raw/externos/` |
| Colegio de Registradores de España | origin of the price and floor area published by the City Council | cited with the City Council | `data/raw/externos/` |

Inside Airbnb's data is not included because  asks people not to republish
it. It is downloaded from their website when the analysis is repeated.

## Limits

- The floor and access of each flat are unknown.
- With listings a year old or more, San Diego falls to 8th place out of 26 by yield.
- The real floor area is unknown, so it cannot be said which yields more: a studio, one bedroom or two.
- It has not been measured whether another price range would change the neighbourhoods.
- The yield excludes costs, taxes, community fees and commissions.
- The purchase price is the one declared in 2025.
- A rental listing does not mean the flat is for sale.
- Repeating the full analysis depends on Inside Airbnb still offering these downloads.

## Related repositories

- [accident-intelligent-agent](https://github.com/jleonceo/accident-intelligent-agent): another analysis of Madrid open data,
  the 2020 traffic accidents.
- [de-datos-en-bruto-a-decisiones](https://github.com/jleonceo/de-datos-en-bruto-a-decisiones): from a raw sales file to a
  dashboard.
- [lead-scoring-ml](https://github.com/jleonceo/lead-scoring-ml): a complete machine learning case for scoring sales leads.
