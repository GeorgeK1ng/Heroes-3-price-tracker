from datetime import datetime, timezone

from prices import maybe_iso_datetime, parse_gog, parse_xbox_catalog


def test_gog_eest_sale_end_text_is_normalized_to_utc():
    assert maybe_iso_datetime("Offer ends on: 30/07/2026 09:59 EEST") == "2026-07-30T06:59:00+00:00"


def test_parse_gog_reads_visible_offer_end_text():
    offer = parse_gog(
        """
        <html><body>
          <script>{"finalAmount":"4.99","baseAmount":"9.99","discount":"50","currency":"USD"}</script>
          <p>Offer ends on: 30/07/2026 09:59 EEST</p>
        </body></html>
        """,
        "https://www.gog.com/game/example",
    )

    assert offer.sale_end == "2026-07-30T06:59:00+00:00"


def test_parse_xbox_catalog_reads_relative_sale_end_text():
    before = datetime.now(timezone.utc)
    payload = {
        "Products": [
            {
                "DisplaySkuAvailabilities": [
                    {
                        "Availabilities": [
                            {
                                "OrderManagementData": {
                                    "Price": {
                                        "ListPrice": 9.99,
                                        "DiscountedPrice": 2.49,
                                        "CurrencyCode": "USD",
                                    }
                                },
                                "Properties": {
                                    "PromotionDescription": "On sale: save $7.50, ends in 2 days"
                                },
                            }
                        ]
                    }
                ]
            }
        ]
    }

    offer = parse_xbox_catalog(payload, "https://www.xbox.com/example")

    assert offer.sale_end is not None
    parsed = datetime.fromisoformat(offer.sale_end)
    assert 1.99 <= (parsed - before).total_seconds() / 86400 <= 2.01


def test_parse_xbox_catalog_ignores_non_promotional_availability_end_date():
    before = datetime.now(timezone.utc)
    payload = {
        "Products": [
            {
                "DisplaySkuAvailabilities": [
                    {
                        "Availabilities": [
                            {
                                "Conditions": {"EndDate": "9998-12-30T23:59:59.0000000Z"},
                                "OrderManagementData": {
                                    "Price": {
                                        "ListPrice": 9.99,
                                        "DiscountedPrice": 2.49,
                                        "CurrencyCode": "USD",
                                    }
                                },
                                "Properties": {
                                    "PromotionDescription": "On sale: save $7.50, ends in 2 days"
                                },
                            }
                        ]
                    }
                ]
            }
        ]
    }

    offer = parse_xbox_catalog(payload, "https://www.xbox.com/example")

    assert offer.sale_end is not None
    parsed = datetime.fromisoformat(offer.sale_end)
    assert parsed.year != 9998
    assert 1.99 <= (parsed - before).total_seconds() / 86400 <= 2.01
