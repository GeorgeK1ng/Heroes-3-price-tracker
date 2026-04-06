#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import requests

GAME_NAME = "Heroes of Might and Magic III Complete"

URLS = {
    "GOG": "https://www.gog.com/en/game/heroes_of_might_and_magic_3_complete_edition",
    "Ubisoft": "https://store.ubisoft.com/ie/heroes-of-might-and-magic-iii--complete/575ffd9ba3be1633568b4d8c.html",
    "Epic": "https://store.epicgames.com/en-US/p/might-and-magic-heroes-3",
    "Xbox": "https://www.xbox.com/en-US/games/store/heroes-of-might-and-magic-3-complete-edition/9P96BJ164SL8",
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

CURRENCY_SIGNS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "Kč": "CZK",
}


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


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_tags(html: str) -> str:
    return normalize_spaces(re.sub(r"<[^>]+>", " ", html))


def parse_decimal(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    text = text.replace("\u00a0", " ").replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def parse_currency_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    for sign, code in CURRENCY_SIGNS.items():
        if sign in text:
            return code
    match = re.search(r"\b(USD|EUR|GBP|CZK)\b", text)
    return match.group(1) if match else None


def extract_money_values(text: str) -> list[tuple[str, float]]:
    pattern = re.compile(
        r"(?P<currency>[$€£]|Kč|USD|EUR|GBP|CZK)\s*"
        r"(?P<amount>\d{1,3}(?:[., ]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2})?)"
    )
    values: list[tuple[str, float]] = []
    for match in pattern.finditer(text):
        amount = parse_decimal(match.group("amount"))
        if amount is not None:
            currency = match.group("currency")
            values.append((currency, amount))
    return values


def maybe_iso_datetime(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = value.strip()
    if not raw or raw == "<DATE>":
        return raw if raw else None

    candidates = [
        "%m/%d/%Y at %I:%M %p",
        "%m/%d/%Y, %I:%M %p",
        "%d/%m/%Y at %H:%M",
        "%B %d, %Y %I:%M %p",
        "%b %d, %Y %I:%M %p",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in candidates:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return raw


def fetch(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def find_json_ld_blocks(html: str) -> list[Any]:
    blocks: list[Any] = []
    for match in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blocks


def walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from walk_json(nested)
    elif isinstance(value, list):
        for item in value:
            yield from walk_json(item)


def parse_gog(html: str, url: str) -> Offer:
    text = strip_tags(html)
    current = original = None
    discount = None
    currency = None
    sale_end = None

    final_matches = re.findall(r'"finalAmount"\s*:\s*"?([0-9.,]+)"?', html)
    base_matches = re.findall(r'"baseAmount"\s*:\s*"?([0-9.,]+)"?', html)
    discount_matches = re.findall(r'"discount"\s*:\s*"?([0-9]+)"?', html)
    currency_matches = re.findall(r'"currency"\s*:\s*"([A-Z]{3})"', html)
    end_matches = re.findall(
        r'"(?:validTo|discountEndDate|priceTill|promotionEndDate)"\s*:\s*"([^"]+)"',
        html,
    )

    if final_matches:
        current = parse_decimal(final_matches[0])
    if base_matches:
        original = parse_decimal(base_matches[0])
    if discount_matches:
        discount = int(discount_matches[0])
    if currency_matches:
        currency = currency_matches[0]
    if end_matches:
        sale_end = maybe_iso_datetime(end_matches[0])

    if current is None:
        paid_values = extract_money_values(text)
        if paid_values:
            currency = currency or CURRENCY_SIGNS.get(paid_values[0][0], paid_values[0][0])
            current = paid_values[0][1]
            if len(paid_values) > 1:
                original = paid_values[1][1]

    if discount is None and current is not None and original and original > 0:
        discount = int(round((1 - (current / original)) * 100))

    return Offer(
        store="GOG",
        url=url,
        currency=currency,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        sale_end=sale_end,
        availability="ok" if current is not None else "parser_warning",
        notes="Parsed from public product page data.",
    )


def parse_ubisoft(html: str, url: str) -> Offer:
    text = strip_tags(html)
    anchor = "Heroes of Might and Magic III Complete Edition"
    idx = text.find(anchor)
    window = text[idx : idx + 800] if idx != -1 else text

    money = extract_money_values(window)
    current = money[0][1] if len(money) >= 1 else None
    original = money[1][1] if len(money) >= 2 else None
    currency = None
    if money:
        first_currency = money[0][0]
        currency = CURRENCY_SIGNS.get(first_currency, first_currency)
    else:
        currency = parse_currency_from_text(window)

    discount_match = re.search(r"-(\d{1,3})%", window)
    discount = int(discount_match.group(1)) if discount_match else None

    end_match = re.search(r"Ending on\s+(.+?)(?:\s+-\d{1,3}%|\s+(?:[$€£]|USD|EUR|GBP|CZK))", window)
    sale_end = maybe_iso_datetime(end_match.group(1)) if end_match else None

    if discount is None and current is not None and original and original > 0:
        discount = int(round((1 - (current / original)) * 100))

    return Offer(
        store="Ubisoft",
        url=url,
        currency=currency,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        sale_end=sale_end,
        availability="ok" if current is not None else "parser_warning",
        notes="Parsed from the visible product pricing block.",
    )


def parse_epic(html: str, url: str) -> Offer:
    text = strip_tags(html)

    current = original = None
    discount = None
    currency = None
    sale_end = None

    visible_match = re.search(
        r"Base Game\s+-(?P<discount>\d{1,3})%\s+"
        r"(?P<original>(?:[$€£]|USD|EUR|GBP|CZK)\s*\d+(?:[.,]\d{2})?)\*?\s+"
        r"(?P<current>(?:[$€£]|USD|EUR|GBP|CZK)\s*\d+(?:[.,]\d{2})?)\s+"
        r"Sale ends\s+(?P<ends>.+?)\s+Buy Now",
        text,
        flags=re.IGNORECASE,
    )

    if visible_match:
        original_money = extract_money_values(visible_match.group("original"))
        current_money = extract_money_values(visible_match.group("current"))
        if original_money:
            original = original_money[0][1]
        if current_money:
            current = current_money[0][1]
            currency = CURRENCY_SIGNS.get(current_money[0][0], current_money[0][0])
        discount = int(visible_match.group("discount"))
        sale_end = maybe_iso_datetime(visible_match.group("ends"))

    if current is None:
        json_match = re.search(
            r'"fmtPrice"\s*:\s*\{[^{}]*?"originalPrice"\s*:\s*"([^"]+)"[^{}]*?'
            r'"discountPrice"\s*:\s*"([^"]+)"',
            html,
            flags=re.DOTALL,
        )
        if json_match:
            original_values = extract_money_values(json_match.group(1))
            current_values = extract_money_values(json_match.group(2))
            if original_values:
                original = original_values[0][1]
            if current_values:
                current = current_values[0][1]
                currency = CURRENCY_SIGNS.get(current_values[0][0], current_values[0][0])

        discount_match = re.search(r'"discount"\s*:\s*(\d+)', html)
        if discount_match:
            discount = int(discount_match.group(1))

    if current is None:
        raise ParseError("Epic pricing data not found")

    if discount is None and current is not None and original and original > 0:
        discount = int(round((1 - (current / original)) * 100))

    return Offer(
        store="Epic",
        url=url,
        currency=currency,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        sale_end=sale_end,
        availability="ok",
        notes="Parsed from visible Epic source data.",
    )


def parse_xbox(html: str, url: str) -> Offer:
    current = original = None
    discount = None
    currency = None
    sale_end = None

    # Prefer schema.org JSON-LD because it is stable in saved page source.
    for block in find_json_ld_blocks(html):
        for node in walk_json(block):
            if not isinstance(node, dict):
                continue
            offers = node.get("offers")
            if not isinstance(offers, list):
                continue
            paid_offers: list[dict[str, Any]] = []
            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                price = parse_decimal(offer.get("price"))
                if price is None or price <= 0:
                    continue
                paid_offers.append(offer)
            if paid_offers:
                primary = paid_offers[0]
                current = parse_decimal(primary.get("price"))
                currency = primary.get("priceCurrency")
                break
        if current is not None:
            break

    if current is None:
        preloaded_state_match = re.search(
            r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;</script>",
            html,
            flags=re.DOTALL,
        )
        if preloaded_state_match:
            raw = preloaded_state_match.group(1)
            try:
                state = json.loads(raw)
            except json.JSONDecodeError:
                state = None
            if state is not None:
                for node in walk_json(state):
                    if not isinstance(node, dict):
                        continue
                    price = node.get("price")
                    if isinstance(price, dict):
                        current = parse_decimal(
                            price.get("listPrice")
                            or price.get("price")
                            or price.get("discountedPrice")
                        )
                        original = parse_decimal(price.get("msrp") or price.get("basePrice"))
                        currency = price.get("currencyCode") or currency
                        if current is not None:
                            discount_value = price.get("discountPercentage")
                            if discount_value is not None:
                                discount = int(discount_value)
                            break

    if discount is None and current is not None and original and original > 0:
        discount = int(round((1 - (current / original)) * 100))

    notes = (
        "Parsed from JSON-LD and preloaded state when available."
        if current is not None
        else "Xbox pricing was not found in the fetched HTML snapshot."
    )

    return Offer(
        store="Xbox",
        url=url,
        currency=currency,
        current_price=current,
        original_price=original,
        discount_percent=discount,
        sale_end=sale_end,
        availability="ok" if current is not None else "parser_warning",
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


def sort_key_price(offer: Offer) -> tuple[Any, ...]:
    current = offer.current_price if offer.current_price is not None else math.inf
    discount = -(offer.discount_percent if offer.discount_percent is not None else -1)
    original = offer.original_price if offer.original_price is not None else math.inf
    return (current, discount, original, offer.store.lower())


def sort_key_discount(offer: Offer) -> tuple[Any, ...]:
    discount = -(offer.discount_percent if offer.discount_percent is not None else -1)
    current = offer.current_price if offer.current_price is not None else math.inf
    return (discount, current, offer.store.lower())


def format_money(value: Optional[float], currency: Optional[str]) -> str:
    if value is None:
        return "—"
    return f"{value:.2f} {currency or ''}".strip()


def format_discount(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return f"-{value}%" if value > 0 else "0%"


def format_sale_end(value: Optional[str]) -> str:
    return value or "—"


def render_table(offers: list[Offer]) -> list[str]:
    lines = [
        "| Store | Current price | Regular price | Discount | Savings | Sale ends | Status | Link |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
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
    return lines


def build_readme(offers: list[Offer], checked_at: str, errors: list[str]) -> str:
    by_price = sorted(offers, key=sort_key_price)
    by_discount = sorted(offers, key=sort_key_discount)
    best_price = next((offer for offer in by_price if offer.current_price is not None), None)
    best_discount = next((offer for offer in by_discount if offer.discount_percent is not None), None)

    lines: list[str] = []
    lines.append(f"# {GAME_NAME} price tracker")
    lines.append("")
    lines.append("Automatically generated by GitHub Actions from public product pages.")
    lines.append("")
    lines.append(f"**Last checked:** `{checked_at}`")
    lines.append("")

    if best_price is not None:
        lines.append(
            f"**Best current price:** {best_price.store} — {format_money(best_price.current_price, best_price.currency)}"
        )
    if best_discount is not None:
        lines.append(
            f"**Best discount:** {best_discount.store} — {format_discount(best_discount.discount_percent)}"
        )
    lines.append("")

    lines.append("## Sorted by current price")
    lines.append("")
    lines.extend(render_table(by_price))
    lines.append("")

    lines.append("## Sorted by discount")
    lines.append("")
    lines.extend(render_table(by_discount))
    lines.append("")

    lines.append("## Parser notes")
    lines.append("")
    for offer in offers:
        lines.append(f"- **{offer.store}:** {offer.notes}")
    if errors:
        lines.append("")
        lines.append("## Runtime errors")
        lines.append("")
        for error in errors:
            lines.append(f"- `{error}`")
    lines.append("")

    payload = {
        "checked_at": checked_at,
        "game": GAME_NAME,
        "offers": [{**asdict(offer), "savings": offer.savings} for offer in offers],
        "errors": errors,
    }
    lines.append("## Raw JSON")
    lines.append("")
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
            errors.append(f"{store}: {type(exc).__name__}: {exc}")
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

    offers.sort(key=sort_key_price)

    os.makedirs("data", exist_ok=True)
    payload = {
        "checked_at": checked_at,
        "game": GAME_NAME,
        "offers": [{**asdict(offer), "savings": offer.savings} for offer in offers],
        "errors": errors,
    }

    with open("data/prices.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    with open("README.md", "w", encoding="utf-8") as handle:
        handle.write(build_readme(offers, checked_at, errors))

    if not any(offer.current_price is not None for offer in offers):
        raise SystemExit("No store returned a price; failing workflow.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
