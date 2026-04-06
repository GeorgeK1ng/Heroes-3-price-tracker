#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urlparse

import requests

URLS = {
    "GOG": "https://www.gog.com/en/game/heroes_of_might_and_magic_3_complete_edition",
    "Ubisoft": "https://store.ubisoft.com/ie/heroes-of-might-and-magic-iii--complete/575ffd9ba3be1633568b4d8c.html",
    "Epic": "https://store.epicgames.com/en-US/p/might-and-magic-heroes-3",
    "Xbox": "https://www.xbox.com/games/store/heroes-of-might-and-magic-3-complete-edition/9P96BJ164SL8",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

TIMEOUT = 30


class ParseError(RuntimeError):
    pass


@dataclass
class Offer:
    store: str
    url: str
    currency: Optional[str]
    current_price: Optional[float]
    original_price: Optional[float]
    discount_percent: Optional[int]
    sale_end: Optional[str]
    availability: str
    notes: str

    @property
    def savings(self) -> Optional[float]:
        if self.current_price is None or self.original_price is None:
            return None
        return round(self.original_price - self.current_price, 2)


CURRENCY_SIGNS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "Kč": "CZK",
}


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_decimal(value: str) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    value = value.replace("\u00a0", " ").replace(" ", "")
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        return float(Decimal(value))
    except (InvalidOperation, ValueError):
        return None


def parse_currency_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    for sign, code in CURRENCY_SIGNS.items():
        if sign in text:
            return code
    match = re.search(r'\b(USD|EUR|GBP|CZK)\b', text)
    return match.group(1) if match else None


def extract_money_values(text: str) -> list[tuple[str, float]]:
    pattern = re.compile(r'(?P<currency>[$€£]|Kč)\s*(?P<amount>\d{1,3}(?:[., ]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2})?)')
    values: list[tuple[str, float]] = []
    for match in pattern.finditer(text):
        amount = parse_decimal(match.group("amount"))
        if amount is not None:
            values.append((match.group("currency"), amount))
    return values


def maybe_iso_datetime(value: str) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    known_formats = [
        "%m/%d/%Y at %I:%M %p",
        "%m/%d/%Y, %I:%M %p",
        "%d/%m/%Y at %H:%M",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in known_formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return value


def fetch(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def parse_gog(html: str, url: str) -> Offer:
    text = normalize_spaces(re.sub(r"<[^>]+>", " ", html))

    # Try JSON-ish data first.
    current = original = None
    discount = None
    currency = None
    sale_end = None

    base_matches = re.findall(r'"baseAmount"\s*:\s*"?(\d+(?:\.\d+)?)"?', html)
    final_matches = re.findall(r'"finalAmount"\s*:\s*"?(\d+(?:\.\d+)?)"?', html)
    discount_matches = re.findall(r'"discount"\s*:\s*"?(\d+)"?', html)
    currency_matches = re.findall(r'"currency"\s*:\s*"([A-Z]{3})"', html)
    end_matches = re.findall(r'"(?:validTo|discountEndDate|priceTill|promotionEndDate)"\s*:\s*"([^"]+)"', html)

    if base_matches and final_matches:
        original = parse_decimal(base_matches[0])
        current = parse_decimal(final_matches[0])
    if discount_matches:
        discount = int(discount_matches[0])
    if currency_matches:
        currency = currency_matches[0]
    if end_matches:
        sale_end = maybe_iso_datetime(end_matches[0])

    # Fallback to visible text patterns.
    if current is None:
        money = extract_money_values(text)
        if money:
            currency = currency or CURRENCY_SIGNS.get(money[0][0])
            current = money[0][1]
            if len(money) > 1:
                original = money[1][1]

    availability = "ok" if current is not None else "parser_warning"
    notes = "Parsed from public product page"

    if discount is None and current is not None and original:
        if original > 0:
            discount = int(round((1 - (current / original)) * 100))

    return Offer(
        store="GOG",
        url=url,
        currency=currency,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        sale_end=sale_end,
        availability=availability,
        notes=notes,
    )


def parse_ubisoft(html: str, url: str) -> Offer:
    text = normalize_spaces(re.sub(r"<[^>]+>", " ", html))

    title_anchor = "Heroes of Might and Magic III"
    idx = text.find(title_anchor)
    window = text[idx: idx + 500] if idx != -1 else text

    money = extract_money_values(window)
    current = money[0][1] if len(money) >= 1 else None
    original = money[1][1] if len(money) >= 2 else None
    currency = CURRENCY_SIGNS.get(money[0][0]) if money else parse_currency_from_text(window)

    discount_match = re.search(r'-(\d{1,3})%', window)
    discount = int(discount_match.group(1)) if discount_match else None

    end_match = re.search(r'Ending on\s+([^\-€$£]+?)(?:\s+-\d{1,3}%|\s+[€$£])', window)
    sale_end = maybe_iso_datetime(end_match.group(1).strip()) if end_match else None

    if discount is None and current is not None and original:
        discount = int(round((1 - (current / original)) * 100))

    availability = "ok" if current is not None else "parser_warning"
    notes = "Parsed from visible product pricing block"

    return Offer(
        store="Ubisoft",
        url=url,
        currency=currency,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        sale_end=sale_end,
        availability=availability,
        notes=notes,
    )


def parse_epic(html: str, url: str) -> Offer:
    text = normalize_spaces(re.sub(r"<[^>]+>", " ", html))

    # Epic page exposes a compact visible pricing block in the HTML.
    match = re.search(
        r'Base Game\s+-(?P<discount>\d{1,3})%\s+(?P<original>[£€$]\s*\d+(?:[.,]\d{2})?)\*?\s+(?P<current>[£€$]\s*\d+(?:[.,]\d{2})?)\s+Sale ends\s+(?P<ends>.+?)\s+Buy Now',
        text,
    )

    if not match:
        raise ParseError("Epic pricing block not found")

    original_text = match.group("original")
    current_text = match.group("current")
    original = extract_money_values(original_text)[0][1]
    current = extract_money_values(current_text)[0][1]
    currency = CURRENCY_SIGNS.get(extract_money_values(current_text)[0][0])
    discount = int(match.group("discount"))
    sale_end = maybe_iso_datetime(match.group("ends"))

    return Offer(
        store="Epic",
        url=url,
        currency=currency,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        sale_end=sale_end,
        availability="ok",
        notes="Parsed from visible Epic pricing block",
    )


def parse_xbox(html: str, url: str) -> Offer:
    text = normalize_spaces(re.sub(r"<[^>]+>", " ", html))

    # Xbox often keeps the visible text sparse in non-browser requests.
    # Try JSON-like fragments first.
    currency = None
    current = original = None
    discount = None
    sale_end = None

    price_match = re.search(r'"price"\s*:\s*\{[^}]*"listPrice"\s*:\s*([0-9.]+)[^}]*"msrp"\s*:\s*([0-9.]+)[^}]*"currencyCode"\s*:\s*"([A-Z]{3})"', html)
    if price_match:
        current = parse_decimal(price_match.group(1))
        original = parse_decimal(price_match.group(2))
        currency = price_match.group(3)

    discount_match = re.search(r'"discountPercentage"\s*:\s*(\d+)', html)
    if discount_match:
        discount = int(discount_match.group(1))

    end_match = re.search(r'"(?:endDate|saleEndDate|promotionEndDate)"\s*:\s*"([^"]+)"', html)
    if end_match:
        sale_end = maybe_iso_datetime(end_match.group(1))

    # Last-resort text parsing if Xbox exposes visible text in the response.
    if current is None:
        title_anchor = "Heroes of Might and Magic 3 - Complete Edition"
        idx = text.find(title_anchor)
        window = text[idx: idx + 400] if idx != -1 else text
        money = extract_money_values(window)
        if money:
            current = money[0][1]
            currency = CURRENCY_SIGNS.get(money[0][0])
            if len(money) > 1:
                original = money[1][1]
        discount_text_match = re.search(r'-(\d{1,3})%', window)
        if discount_text_match:
            discount = int(discount_text_match.group(1))
        end_text_match = re.search(r'(?:Sale ends|Ends in)\s+(.+?)(?:\s+[£€$]|\s+Buy|$)', window)
        if end_text_match:
            sale_end = maybe_iso_datetime(end_text_match.group(1))

    availability = "ok" if current is not None else "parser_warning"
    notes = (
        "Xbox page may require selector updates because some pricing data is rendered dynamically"
        if availability != "ok"
        else "Parsed from product page data"
    )

    if discount is None and current is not None and original:
        discount = int(round((1 - (current / original)) * 100))

    return Offer(
        store="Xbox",
        url=url,
        currency=currency,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        sale_end=sale_end,
        availability=availability,
        notes=notes,
    )


def fetch_offer(store: str, url: str) -> Offer:
    html = fetch(url)
    if store == "GOG":
        return parse_gog(html, url)
    if store == "Ubisoft":
        return parse_ubisoft(html, url)
    if store == "Epic":
        return parse_epic(html, url)
    if store == "Xbox":
        return parse_xbox(html, url)
    raise ValueError(f"Unsupported store: {store}")


def sort_key(offer: Offer) -> tuple:
    current = offer.current_price if offer.current_price is not None else math.inf
    discount = -(offer.discount_percent if offer.discount_percent is not None else -1)
    original = offer.original_price if offer.original_price is not None else math.inf
    return (current, discount, original, offer.store.lower())


def format_money(value: Optional[float], currency: Optional[str]) -> str:
    if value is None:
        return "—"
    code = currency or ""
    return f"{value:.2f} {code}".strip()


def format_discount(value: Optional[int]) -> str:
    return f"-{value}%" if value is not None and value > 0 else ("0%" if value == 0 else "—")


def format_sale_end(value: Optional[str]) -> str:
    return value or "—"


def build_readme(offers: list[Offer], checked_at: str) -> str:
    lines: list[str] = []
    lines.append("# Heroes III Complete price tracker")
    lines.append("")
    lines.append(
        "Automaticky generováno v GitHub Actions z veřejných produktových stránek pro "
        "Heroes of Might and Magic III Complete."
    )
    lines.append("")
    lines.append(f"**Poslední kontrola:** `{checked_at}`")
    lines.append("")
    lines.append("## Přehled")
    lines.append("")
    lines.append("| Store | Cena | Běžná cena | Sleva | Ušetříš | Konec slevy | Stav | Odkaz |")
    lines.append("|---|---:|---:|---:|---:|---|---|---|")
    for offer in offers:
        lines.append(
            "| {store} | {current} | {original} | {discount} | {savings} | {sale_end} | {status} | [Open]({url}) |".format(
                store=offer.store,
                current=format_money(offer.current_price, offer.currency),
                original=format_money(offer.original_price, offer.currency),
                discount=format_discount(offer.discount_percent),
                savings=format_money(offer.savings, offer.currency),
                sale_end=format_sale_end(offer.sale_end),
                status=offer.availability,
                url=offer.url,
            )
        )

    lines.append("")
    lines.append("## Pořadí")
    lines.append("")
    lines.append("- Primárně podle nejnižší aktuální ceny.")
    lines.append("- Při shodě podle nejvyšší slevy.")
    lines.append("- Pokud store nevrátí cenu, přesune se na konec tabulky a označí se jako `parser_warning`.")
    lines.append("")
    lines.append("## Poznámky parseru")
    lines.append("")
    for offer in offers:
        lines.append(f"- **{offer.store}:** {offer.notes}")
    lines.append("")
    lines.append("## Raw JSON")
    lines.append("")
    payload = {
        "checked_at": checked_at,
        "game": "Heroes of Might and Magic III Complete",
        "offers": [
            {
                **asdict(offer),
                "savings": offer.savings,
            }
            for offer in offers
        ],
    }
    lines.append("```json")
    lines.append(json.dumps(payload, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    offers: list[Offer] = []
    errors: list[str] = []

    for store, url in URLS.items():
        try:
            offers.append(fetch_offer(store, url))
        except Exception as exc:
            errors.append(f"{store}: {exc}")
            offers.append(
                Offer(
                    store=store,
                    url=url,
                    currency=None,
                    current_price=None,
                    original_price=None,
                    discount_percent=None,
                    sale_end=None,
                    availability="error",
                    notes=f"{type(exc).__name__}: {exc}",
                )
            )

    offers.sort(key=sort_key)

    os.makedirs("data", exist_ok=True)
    payload = {
        "checked_at": checked_at,
        "game": "Heroes of Might and Magic III Complete",
        "offers": [
            {
                **asdict(offer),
                "savings": offer.savings,
            }
            for offer in offers
        ],
        "errors": errors,
    }
    with open("data/prices.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    readme = build_readme(offers, checked_at)
    with open("README.md", "w", encoding="utf-8") as fh:
        fh.write(readme)

    # Fail only if every store failed.
    successful = any(offer.current_price is not None for offer in offers)
    if not successful:
        raise SystemExit("No store returned a price; failing workflow.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
