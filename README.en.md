Versión en español: [README.md](README.md)

# Where to look for tourist rental flats in Madrid

A fictional company wants to buy flats in Madrid to let to tourists and needs to know where to start. This analysis answers
that question with public data from Airbnb and Madrid City Council.

**Result:** the first place to look is flats with up to 2 bedrooms in three Madrid neighbourhoods: Ventas (in Ciudad Lineal
district), Numancia and San Diego (both in Puente de Vallecas district). On 17/09/2026 there were 256 such listings among the
2,940 flats analysed. At the median, each flat would cost €161,973 at the official 2025 price and bring in €21,675 a year in
revenue. Calculated flat by flat, the median gross yield is 12.1%, before costs and taxes.

This list says where to look, not whether a specific flat can be let to tourists. That depends on planning rules and has to
be checked flat by flat with the City Council. The occupied days are also an estimate by Inside Airbnb, capped at 255 days a year.

If flats at that cap are excluded, the list becomes the neighbourhoods of Comillas, Cuatro Caminos, Opañel, Pinar del Rey, Puerta del Ángel, Quintana and
San Andrés, and none of the three neighbourhoods stays on it. That is why this recommendation is only a first screening.

**The purchase price used is the official 2025 one, and the market is asking more today.** At the prices on Fotocasa and Idealista,
the median purchase price rises to €171,600 and €182,000 respectively, and the gross yield falls to 10.9% and 10.6%. These are asking prices, not sale prices,
so the price actually paid could be somewhat lower.

[![CI](https://github.com/jleonceo/alquiler-turistico-madrid/actions/workflows/ci.yml/badge.svg)](https://github.com/jleonceo/alquiler-turistico-madrid/actions/workflows/ci.yml)

```bash
git clone https://github.com/jleonceo/alquiler-turistico-madrid.git && cd alquiler-turistico-madrid
pip install -r requirements.txt
python ejecutar.py --completo
```

It requires Python 3.13.

The last command downloads the original 240 MB of data from Inside Airbnb, repeats the whole analysis,
recalculates the figures on this page and runs the tests. The PDF of the executive report needs Microsoft Edge. Without it, the
PDF already in the repository is kept.

## The three deliverables

All three deliverables are in Spanish.

- [Executive report](https://alquiler-turistico-madrid.vercel.app/informes/informe_ejecutivo.html): three pages for
  management, also available [as a PDF](informes/informe_ejecutivo.pdf).
- [Final report](https://alquiler-turistico-madrid.vercel.app/informes/informe_final.html): the full analysis, with its
  charts.
- [Dashboard](https://alquiler-turistico-madrid.vercel.app/informes/cuadro_mando.html): for the team that appraises the
  flats, to compare neighbourhoods.

![First screen of the dashboard, with the recommendation and its figures](docs/img/cuadro_de_mando.png)

The four large figures in the image cover all the flats analysed. Those for the three neighbourhoods are in the table on the right.

## Why not all of Madrid

Of the 23,109 Airbnb listings in the city, 14,150 are in the historic centre, where the City Council's RESIDE Plan does not
allow tourist lets in residential buildings. The analysis therefore uses flats outside the centre.
It uses listings from €20 to €1,000 a night. These limits are a judgement call: there are almost no listings below €20 and only
164 above €1,000. Across the whole city, 18,785 listings have a price and 18,573 fall between €20 and €1,000. The other filters, such as size, minimum stay and occupancy,
then leave the 2,940 flats.

## How the neighbourhoods were chosen

A flat's gross yield is its annual rental income divided by its purchase price. The income is the nightly price multiplied by the
occupied days estimated by Inside Airbnb. The purchase price is based on an assumed floor area and the neighbourhood's official price per m².

The neighbourhoods were ranked by yield to see which fell in the top 25%. That ranking changes with the minimum stay and the month
of the price, so the calculation was repeated 12 times with different values. The 9 neighbourhoods that were in the top 25% in more
than half of the repetitions were kept.

The next check was whether those 9 depended on one particular group of listings. The calculation was repeated in five more ways,
for example excluding hosts who have 10 or more listings. The neighbourhoods of Ventas, Numancia and San Diego stayed on the list
all five times.

They are recommended because they stayed on the list all five times, which does not mean they yield more: none of them clearly outperforms the others on the list. The Numancia neighbourhood's yield is
above the median for all the flats analysed, but the same cannot be stated with confidence for the Ventas and San Diego neighbourhoods. The neighbourhoods of Casco Histórico de Vallecas and Opañel yield more than the San Diego neighbourhood, but they drop off the list when hosts with
10 or more listings are excluded.

![Map of Madrid with the selected neighbourhoods](docs/img/mapa_de_barrios.png)

`python ejecutar.py --completo` prints this summary, in Spanish:

```text
Pisos analizados, datos del 17/09/2026: 2.940
Barrios en la lista: 9
Barrios que siguen en la lista en las 5 repeticiones: Numancia, San Diego y Ventas
Barrios que siguen en 4 de 5: Casco Histórico de Vallecas y Opañel

Pisos de hasta 2 habitaciones en los barrios de Numancia, San Diego y Ventas: 256 anuncios
  Precio de compra, en mediana: 161.973 €
  Ingreso al año, en mediana: 21.675 €
  Rentabilidad bruta: 12,1 %
  Con los precios que pide hoy Fotocasa: compra de 171.600 € y rentabilidad bruta de 10,9 %
  Con los precios que pide hoy Idealista: compra de 182.000 € y rentabilidad bruta de 10,6 %
  Rentabilidad de los pisos de esos barrios con estancia de hasta 3 noches, de cualquier tamaño, según la fecha del precio: de 10,8 % a 11,5 %

Estas cifras coinciden con las del análisis y con las de esta página, en español y en inglés.
```

## Today's purchase price

| Neighbourhood | Official, 2025 deeds | Fotocasa | Idealista |
|---|---|---|---|
| Ventas | €4,133/m² | €4,825/m² | €4,816/m² |
| Numancia | €3,239/m² | €3,432/m² | €3,640/m² |
| San Diego | €3,078/m² | €3,388/m² | €3,489/m² |

The portal prices were checked on 06/11/2026 and are compared only for these three neighbourhoods.

## How it is built

Fourteen Python scripts do the work, from download to the three deliverables, covering data quality checks, cleaning, joins,
exploration, metrics and reports. The three deliverables take their figures from a single file,
[indicadores.json](informes/indicadores.json).
[A second script](scripts/rehacer_portada.py) redoes the choice of neighbourhoods and the medians on this page from a local table,
sharing no code with the analysis. The tests also recalculate the metrics independently.

The detail, in Spanish, is in [the method](docs/metodo.md), [the business rules](docs/reglas_de_negocio.md),
[the data criteria](docs/criterios_de_datos.md) and [the data](docs/datos.md).

## The data

| Source | What it provides | Licence | Where it is |
|---|---|---|---|
| [Inside Airbnb](https://insideairbnb.com/get-the-data/), Madrid | listings, calendar, reviews and neighbourhood boundaries | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | downloaded separately |
| [Madrid City Council](https://datos.madrid.es/) | 2025 price and floor area, sales, licences, historic centre and points of interest | reuse with attribution | `data/raw/externos/` |
| Colegio de Registradores de España | origin of the price and floor area published by the City Council | cited with the City Council | `data/raw/externos/` |
| [Fotocasa](https://www.fotocasa.es/fotocasa-life/sector/evolucion-del-precio-de-la-vivienda-en-madrid/) and [Idealista](https://www.idealista.com/maps/madrid/) | today's asking price per m² in the three neighbourhoods, for comparison only | source cited | `config/fuentes/precios_de_mercado.json` |

Inside Airbnb's data is not included because [its policy](https://insideairbnb.com/data-policies/) asks people not to republish
it. It is downloaded from their website when the analysis is repeated.

## Limits

- The storey and access of each flat are unknown.
- Since 03/04/2025 the homeowners' association must also approve it expressly, by three fifths of owners and of shares. The same majority can ban it or raise the service charge by up to 20% (Spanish Law 49/1960, arts. 7.3 and 17.12).
- A home under public protection cannot be a tourist home (art. 17 ter.3 of Decree 79/2014, added by Decree 27/2026). The responsible declaration must state that two certificates are held: one that the title deed or the association's bylaws do not ban the activity, and one that the association has approved the request (art. 17 bis, letters f and g, of the same decree).
- If only listings that are a year old or more are used, the San Diego neighbourhood falls to 8th out of 26 by yield.
- Each flat's floor area is an assumption: 50 m² for up to 1 bedroom, 65 m² for 2 bedrooms, and 90 to 140 m² for 3. So we cannot say which
  yields more: a studio, a one-bedroom flat or a two-bedroom flat. The floor area of 3-bedroom flats was not varied in the checks.
- Only flats with estimated occupancy count, meaning those with reviews in the last year. Flats that are not being let are left out,
  which may push the yield up.
- If flats with no estimated occupancy or price are also counted as zero, only the Ventas neighbourhood stays on the list.
- We have not tested whether a different price range would change the neighbourhoods.
- The yield excludes costs, taxes, service charges and commissions.
- The neighbourhoods were chosen using the price declared in 2025. We have not tested whether today's prices would change them.
- A rental listing does not mean the flat is for sale.
- Repeating the full analysis depends on Inside Airbnb still offering these downloads.

## Related repositories

- [accident-intelligent-agent](https://github.com/jleonceo/accident-intelligent-agent): another analysis of Madrid open data,
  the 2020 traffic accidents.
- [de-datos-en-bruto-a-decisiones](https://github.com/jleonceo/de-datos-en-bruto-a-decisiones): from a raw sales file to a
  dashboard.
- [lead-scoring-ml](https://github.com/jleonceo/lead-scoring-ml): a complete machine learning case for scoring sales leads.
