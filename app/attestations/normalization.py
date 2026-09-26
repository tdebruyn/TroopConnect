"""Name normalisation shared by the matcher and the remembered correspondences.

Lives outside ``services`` because the ``NameAlias`` model needs ``name_key``
when it saves, and ``services`` already imports the models.

The functions return ASCII, lowercase strings so that a name read from a PDF
(scanned, all-caps, accented or not, in either order) and a name held in the
database compare equal when they are the same name.
"""

import re

from unidecode import unidecode


def normalize(text):
    """Lowercase, strip accents, collapse whitespace."""
    return re.sub(r"\s+", " ", unidecode(text or "").lower()).strip()


def name_tokens(text):
    """Split a name into its significant word tokens (accent- and case-free)."""
    return [t for t in re.findall(r"[a-z]+", normalize(text)) if len(t) > 1]


def token_key(tokens):
    """The key for an already-tokenised name."""
    return " ".join(sorted(tokens))


def name_key(name):
    """A stable key for a name: its significant tokens, sorted.

    Order-insensitive, so "Dupont Charlie" and "Charlie Dupont" share a key —
    a document that reverses the two is the same person either way.
    """
    return token_key(name_tokens(name))
