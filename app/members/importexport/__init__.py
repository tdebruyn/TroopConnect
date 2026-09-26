"""Member import and export in one column format.

The two directions are two halves of one contract: a file this module exports
has to be a file it can read back, so the column definitions, the value
conventions and the readers and writers all live here together. See
``docs/dev/CONTRACT.md`` §3c for the human-readable specification.

The pieces, in the order a file passes through them:

``columns``
    What a column is called and how its value is written and read.
``files``
    A CSV or an XLSX on the wire turned into rows, and rows turned back.
``exporter``
    The database read out into those rows, balances included.
``importer``
    Those rows turned into a plan — what would be created, updated, or
    complained about — and then, on confirmation, into records.
"""
