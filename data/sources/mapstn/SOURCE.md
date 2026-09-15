# Tribal tables from MapsTN

Four tables copied verbatim from the sibling repository
[MedDhia/MapsTN](https://github.com/MedDhia/MapsTN) at commit
`df459286a2c8740c70dcd2bf940c9758fb15b242` (14 September 2026). They are the
input to `tools/make_tribal_mobility.py`, and nothing here is edited: to
refresh them, copy the same four files from a newer MapsTN checkout.

| file | rows | what |
|---|---|---|
| `tribal_territories.csv` | 121 | every tribe name read off the two Gallica sheets, the 1853 Pellissier and the 1881 Lasailly, placed on the ground by an affine fitted to towns |
| `martel_1965_tribes.csv` | 27 | the same for the sketch map in André Martel, *Les Confins saharo-tripolitains de la Tunisie* (1965), which depicts 1881 |
| `tribal_spread.csv` | 92 | one row per tribe: the largest ellipse that holds all of its own labels on every sheet and no other tribe's label |
| `tribal_spread_by_sheet.csv` | 143 | the same ellipse built from one sheet at a time |

How the labels were read, placed and bounded is documented in MapsTN's
`docs/TRIBES.md` and `docs/CODEBOOK-TRIBES.md`. Three points from there govern
how these tables may be used:

* **No sheet draws a tribal boundary.** A tribe is a name letterspaced across
  the ground it holds. The ellipse is the largest reading the sheets will
  carry, bounded by neighbouring names rather than by a line anyone drew.
* **A point is where the engraver centred the name**, good to about 6 to 8 km,
  and the name itself covers a median 16 km of ground.
* **Where the sheets disagree the ellipse joins their placements.** Ouled
  Khiar (287 km apart), Ouled Sdira (211), Souassi (126) and Riah (119) are
  suspected name collisions, and `encloses_other_tribes` flags them.
