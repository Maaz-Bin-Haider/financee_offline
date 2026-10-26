"""Idempotent public currency-catalogue seeding."""

from .currency_data import CURRENCY_SEED_ROWS


def seed_currency_catalogue(currency_model):
    """Upsert the frozen catalogue and return `(created, updated)` counts."""
    created_count = 0
    updated_count = 0
    for code, name, symbol, minor_units, is_active in CURRENCY_SEED_ROWS:
        _, created = currency_model.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "symbol": symbol,
                "minor_units": minor_units,
                "is_active": is_active,
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1
    return created_count, updated_count
