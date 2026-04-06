# Heroes III Complete price tracker

Automaticky generováno v GitHub Actions z veřejných produktových stránek pro Heroes of Might and Magic III Complete.

**Poslední kontrola:** `2026-04-06T20:06:05+00:00`

## Přehled

| Store | Cena | Běžná cena | Sleva | Ušetříš | Konec slevy | Stav | Odkaz |
|---|---:|---:|---:|---:|---|---|---|
| GOG | 9.99 | 9.99 | 0% | 0.00 | — | ok | [Open](https://www.gog.com/en/game/heroes_of_might_and_magic_3_complete_edition) |
| Xbox | — | — | 0% | — | — | parser_warning | [Open](https://www.xbox.com/games/store/heroes-of-might-and-magic-3-complete-edition/9P96BJ164SL8) |
| Epic | — | — | — | — | — | error | [Open](https://store.epicgames.com/en-US/p/might-and-magic-heroes-3) |
| Ubisoft | — | — | — | — | — | parser_warning | [Open](https://store.ubisoft.com/ie/heroes-of-might-and-magic-iii--complete/575ffd9ba3be1633568b4d8c.html) |

## Pořadí

- Primárně podle nejnižší aktuální ceny.
- Při shodě podle nejvyšší slevy.
- Pokud store nevrátí cenu, přesune se na konec tabulky a označí se jako `parser_warning`.

## Poznámky parseru

- **GOG:** Parsed from public product page
- **Xbox:** Xbox page may require selector updates because some pricing data is rendered dynamically
- **Epic:** HTTPError: 403 Client Error: Forbidden for url: https://store.epicgames.com/en-US/p/might-and-magic-heroes-3
- **Ubisoft:** Parsed from visible product pricing block

## Raw JSON

```json
{
  "checked_at": "2026-04-06T20:06:05+00:00",
  "game": "Heroes of Might and Magic III Complete",
  "offers": [
    {
      "store": "GOG",
      "url": "https://www.gog.com/en/game/heroes_of_might_and_magic_3_complete_edition",
      "currency": null,
      "current_price": 9.99,
      "original_price": 9.99,
      "discount_percent": 0,
      "sale_end": null,
      "availability": "ok",
      "notes": "Parsed from public product page",
      "savings": 0.0
    },
    {
      "store": "Xbox",
      "url": "https://www.xbox.com/games/store/heroes-of-might-and-magic-3-complete-edition/9P96BJ164SL8",
      "currency": null,
      "current_price": null,
      "original_price": null,
      "discount_percent": 0,
      "sale_end": null,
      "availability": "parser_warning",
      "notes": "Xbox page may require selector updates because some pricing data is rendered dynamically",
      "savings": null
    },
    {
      "store": "Epic",
      "url": "https://store.epicgames.com/en-US/p/might-and-magic-heroes-3",
      "currency": null,
      "current_price": null,
      "original_price": null,
      "discount_percent": null,
      "sale_end": null,
      "availability": "error",
      "notes": "HTTPError: 403 Client Error: Forbidden for url: https://store.epicgames.com/en-US/p/might-and-magic-heroes-3",
      "savings": null
    },
    {
      "store": "Ubisoft",
      "url": "https://store.ubisoft.com/ie/heroes-of-might-and-magic-iii--complete/575ffd9ba3be1633568b4d8c.html",
      "currency": null,
      "current_price": null,
      "original_price": null,
      "discount_percent": null,
      "sale_end": null,
      "availability": "parser_warning",
      "notes": "Parsed from visible product pricing block",
      "savings": null
    }
  ]
}
```
