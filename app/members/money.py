"""Rendering amounts in the troop's own currency.

The currency is troop content, not infrastructure — a unit that moved country
edits it on the settings page, it does not rebuild an image. So it lives in
``TroopSettings.currency`` and is read here, in one place, for every amount the
UI shows; nothing renders a ``€`` of its own.
"""

from django.utils.formats import number_format

from .models import TroopSettings

#: Symbols for the currencies a scout unit is likely to use. Anything else is
#: written as its ISO code, which is unambiguous and never wrong.
CURRENCY_SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
}

#: Between the amount and the currency. Non-breaking, so a line never wraps
#: between the number and what it is denominated in — "154,00" alone on a line
#: and "€" on the next reads as two different things.
SEPARATOR = "\u00a0"  # a no-break space


def currency_code():
    """The troop's ISO 4217 currency code."""
    return TroopSettings.get_settings().currency


def currency_symbol():
    """How the troop's currency is written next to an amount."""
    code = currency_code()
    return CURRENCY_SYMBOLS.get(code, code)


def format_money(amount):
    """``amount`` written with the troop's currency, or ``""`` for no amount.

    The digits follow the *reader's* language, not the troop's: a French parent
    sees ``154,00 €`` and an English one ``154.00 €``. Amounts are read by
    families deciding whether they can pay, so a decimal point that belongs to
    another language's convention is a misreading, not a style choice.

    The separator is non-breaking and applies to a symbol as well as a code —
    the currency belongs to the number and must not be wrapped away from it.
    """
    if amount is None:
        return ""
    digits = number_format(amount, decimal_pos=2)
    return f"{digits}{SEPARATOR}{currency_symbol()}"
