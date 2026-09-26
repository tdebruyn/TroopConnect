"""Rendering amounts in the troop's own currency.

The currency is troop content, not infrastructure — a unit that moved country
edits it on the settings page, it does not rebuild an image. So it lives in
``TroopSettings.currency`` and is read here, in one place, for every amount the
UI shows; nothing renders a ``€`` of its own.
"""

from .models import TroopSettings

#: Symbols for the currencies a scout unit is likely to use. Anything else is
#: written as its ISO code, which is unambiguous and never wrong.
CURRENCY_SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
}

#: Codes written as words, so they need a space before them: "12.50 CHF".
_ALPHABETIC = " "


def currency_code():
    """The troop's ISO 4217 currency code."""
    return TroopSettings.get_settings().currency


def currency_symbol():
    """How the troop's currency is written next to an amount."""
    code = currency_code()
    symbol = CURRENCY_SYMBOLS.get(code, code)
    return f"{_ALPHABETIC}{symbol}" if symbol.isalpha() else symbol


def format_money(amount):
    """``amount`` written with the troop's currency, or ``""`` for no amount.

    The digits are left as ``str()`` renders them, which is how these amounts
    have always been displayed; only the currency beside them moves to the
    settings.
    """
    if amount is None:
        return ""
    return f"{amount}{currency_symbol()}"
