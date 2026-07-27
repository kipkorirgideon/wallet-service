"""Static per-country configuration."""

from dataclasses import dataclass

from .models import Country


@dataclass(frozen=True)
class CountryInfo:
    timezone: str  # IANA timezone name
    currency: str  # ISO 4217 currency code
    daily_send_limit: int  # minor units


COUNTRY_INFO = {
    Country.SN: CountryInfo(timezone="Africa/Dakar", currency="XOF", daily_send_limit=500_000),
    Country.CI: CountryInfo(timezone="Africa/Abidjan", currency="XOF", daily_send_limit=500_000),
    Country.CM: CountryInfo(timezone="Africa/Douala", currency="XAF", daily_send_limit=750_000),
    Country.NE: CountryInfo(timezone="Africa/Niamey", currency="XOF", daily_send_limit=400_000),
    Country.UG: CountryInfo(timezone="Africa/Kampala", currency="UGX", daily_send_limit=2_000_000),
}
