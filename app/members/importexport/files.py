"""A CSV or an XLSX turned into rows, and rows turned back into one.

The reader is forgiving about everything that does not change what a cell
means, because these files are made in a spreadsheet by people who are not
thinking about this application: the delimiter is worked out from the header,
the encoding falls back to the one Excel on a French Windows writes, and the
header is matched through the folding in ``columns``.

The writer produces what that reader reads: UTF-8 with a byte-order mark and a
semicolon delimiter, which is the pair Excel opens into columns on a
French-locale machine instead of piling into one.
"""

import csv
import io

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from . import columns as cols

#: Which column of the file a row came from, for "line 4" in an error message.
LINE_KEY = "_line"

#: What the reader treats as a workbook rather than a text table.
XLSX_SUFFIXES = (".xlsx", ".xlsm")

#: Wide enough for a header and a little more; the sheet is for reading.
_COLUMN_WIDTH = 18


class FileError(Exception):
    """The upload is not a table this format can read.

    Carries a message meant for the person who uploaded it, not a traceback.
    """


def _is_xlsx(filename):
    return str(filename or "").casefold().endswith(XLSX_SUFFIXES)


def _decode(data):
    """Text from an upload, in whichever of the two encodings Excel picked.

    ``utf-8-sig`` first so the byte-order mark the export writes — and that
    Excel writes too — comes off rather than becoming part of the first
    header. ``cp1252`` second because that is what Excel on a Windows machine
    with a Western European locale saves a CSV as, and ``Prénom`` in it is not
    valid UTF-8.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _delimiter(header_line):
    """The delimiter the header line uses; the export's own when unsure."""
    counts = {candidate: header_line.count(candidate) for candidate in ";,\t|"}
    best = max(counts, key=counts.get)
    return best if counts[best] else ";"


def _csv_rows(data):
    text = _decode(data)
    if not text.strip():
        raise FileError("empty")
    reader = csv.reader(io.StringIO(text), delimiter=_delimiter(text.splitlines()[0]))
    return [row for row in reader]


def _xlsx_rows(data):
    try:
        workbook = load_workbook(
            io.BytesIO(data), read_only=True, data_only=True
        )
    except Exception as error:  # openpyxl raises a family of these
        raise FileError("unreadable") from error
    sheet = workbook.worksheets[0] if workbook.worksheets else None
    if sheet is None:
        raise FileError("empty")
    return [list(row) for row in sheet.iter_rows(values_only=True)]


class Table:
    """The uploaded file, as rows keyed by internal column key.

    ``unknown_headers`` and ``missing_headers`` are kept rather than raised:
    a column the format does not know is worth a warning ("this file has a
    column nothing will read"), and so is one it expected and did not get,
    because whether that is fatal depends on what the rows say.
    """

    def __init__(self, rows, unknown_headers, missing_headers):
        self.rows = rows
        self.unknown_headers = unknown_headers
        self.missing_headers = missing_headers


def read_table(filename, data, column_set=None):
    """Parse an uploaded member or payments file into rows.

    Each row is a ``{internal key: cell}`` dict carrying :data:`LINE_KEY`, the
    1-based line in the file the row came from — the header being line 1 — so
    a complaint about a row can say where to find it.
    """
    columns = cols.MEMBER_COLUMNS if column_set is None else column_set
    raw_rows = _xlsx_rows(data) if _is_xlsx(filename) else _csv_rows(data)
    if not raw_rows:
        raise FileError("empty")

    header = ["" if cell is None else str(cell) for cell in raw_rows[0]]
    index = cols.header_index(columns)
    mapping = {}
    unknown = []
    for position, label in enumerate(header):
        if not label.strip():
            continue
        key = index.get(cols.fold_header(label))
        if key is None:
            unknown.append(label.strip())
        else:
            mapping[position] = key

    if not mapping:
        raise FileError("no-headers")

    known = {column.key for column in columns}
    missing = sorted(known - set(mapping.values()))

    rows = []
    for offset, raw in enumerate(raw_rows[1:], start=2):
        if all(cell is None or str(cell).strip() == "" for cell in raw):
            continue  # a blank line is not a row
        row = {LINE_KEY: offset}
        for position, key in mapping.items():
            row[key] = raw[position] if position < len(raw) else None
        rows.append(row)

    return Table(rows, unknown, missing)


# --- Writing ----------------------------------------------------------------


def _cell(value, column):
    if column.kind == "date" and value:
        return value
    return cols.to_cell(value, column)


def write_csv(column_set, records):
    """A CSV with the export's own conventions: UTF-8 BOM, semicolons, CRLF."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([column.heading() for column in column_set])
    for record in records:
        writer.writerow(
            [cols.to_cell(record.get(column.key), column) for column in column_set]
        )
    return buffer.getvalue().encode("utf-8-sig")


def write_xlsx(column_set, records, title="Sheet"):
    """The same table as a sheet, with a frozen, bold header and real dates."""
    workbook = Workbook()
    sheet = workbook.active
    # Excel refuses a sheet name over 31 characters or holding []:*?/\\.
    sheet.title = (title or "Sheet")[:31]

    for position, column in enumerate(column_set, start=1):
        cell = sheet.cell(row=1, column=position, value=column.heading())
        cell.font = Font(bold=True)
        sheet.column_dimensions[get_column_letter(position)].width = _COLUMN_WIDTH

    for row_number, record in enumerate(records, start=2):
        for position, column in enumerate(column_set, start=1):
            value = _cell(record.get(column.key), column)
            cell = sheet.cell(row=row_number, column=position, value=value)
            if column.kind == "date" and value is not None:
                cell.number_format = "YYYY-MM-DD"

    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def write_table(column_set, records, extension, title="Sheet"):
    """The table in the format the extension names."""
    if extension == "xlsx":
        return write_xlsx(column_set, records, title=title)
    return write_csv(column_set, records)
