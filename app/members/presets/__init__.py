"""Branch presets: the shape of a unit's sections, shipped as data.

A preset describes how a unit's sections are laid out — each branch's name in
every language, the ages it takes, which branch leads to which — and the
sections to create with them. The layout a troop starts from is its
federation's, not this project's opinion: :file:`les-scouts.json` is Les
Scouts' four branches, and ``manage.py setup --preset <file>`` takes any other
file in the same shape, so a federation or a unit can contribute one.

The file is the contract, so it is validated against
:file:`preset.schema.json` on load rather than trusted, and every error names
the path into the file (``$.branches[2].promotes_to``) so somebody can fix it
without reading this module.

Only the subset of JSON Schema these files actually use is implemented here —
``type``, ``required``, ``properties``, ``additionalProperties``, ``items``,
``minItems``, ``minLength``, ``pattern``, ``enum``, ``minimum``, ``maximum``
and local ``$ref``. That keeps a schema library (and its compiled wheels, on
an Alpine image) out of the deployable for one schema; the schema file says
the same thing in its own descriptions. What a schema cannot express — that
``promotes_to`` names a branch that exists, that the ladder does not loop,
that a branch is not both ``is_top`` and promoted on — is checked by
:func:`_check_ladder`.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

#: The languages a preset may name a branch or section in. Modeltranslation
#: keeps a column per language and an empty one falls back to French, which is
#: why the schema requires ``fr``.
LANGUAGES = ("fr", "nl", "en")

PRESET_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = PRESET_DIR / "preset.schema.json"

#: The preset ``manage.py setup`` uses when none is named.
DEFAULT_PRESET = "les-scouts"


class PresetError(ValueError):
    """A preset file cannot be used — with *every* reason it cannot.

    Carries the whole list rather than only the first problem, so somebody
    writing a preset by hand sees everything that is wrong in one run instead
    of fixing one field at a time.
    """

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True)
class PresetSection:
    """A section to create inside a branch."""

    names: dict
    sex: str = "B"

    def name_for(self, language):
        """The name in ``language``, falling back to French as the model does."""
        return self.names.get(language) or self.names["fr"]


@dataclass(frozen=True)
class PresetBranch:
    """One rung of the ladder, and the sections that belong to it."""

    key: str
    names: dict
    min_age: int | None = None
    max_age: int | None = None
    promotes_to: str | None = None
    is_top: bool = False
    sections: tuple = ()

    def name_for(self, language):
        """The name in ``language``, falling back to French as the model does."""
        return self.names.get(language) or self.names["fr"]


@dataclass(frozen=True)
class Preset:
    """A validated preset file."""

    name: str
    title: str
    source: str
    note: str
    branches: tuple
    path: Path

    def __str__(self):
        return self.title or self.name


def preset_path(name_or_path=DEFAULT_PRESET):
    """Where a preset lives: a file path, or a name under this directory.

    A ``.json`` suffix or a path separator means "this is a path"; anything
    else is the name of a preset shipped here, written with or without its
    suffix. Nothing else is inferred from the filesystem, so a typo cannot
    quietly pick up a different file.
    """
    text = str(name_or_path)
    if text.endswith(".json") or "/" in text or "\\" in text:
        return Path(text)
    return PRESET_DIR / f"{text}.json"


def load_preset(name_or_path=DEFAULT_PRESET):
    """Read, validate and return the preset ``name_or_path`` names.

    Raises :class:`PresetError` — listing every problem — when the file is
    missing, is not JSON, does not match the schema, or describes a ladder
    that cannot be walked.
    """
    path = preset_path(name_or_path)

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PresetError([f"{path}: cannot be read ({exc.strerror})"]) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PresetError(
            [f"{path}:{exc.lineno}:{exc.colno}: invalid JSON ({exc.msg})"]
        ) from exc

    validate_preset(data)
    return _build(data, path)


def load_schema(path=SCHEMA_PATH):
    """The schema every preset is checked against."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def validate_preset(data, schema=None):
    """Raise :class:`PresetError` unless ``data`` is a usable preset.

    The schema covers the shape; :func:`_check_ladder` covers what a shape
    cannot — that the ladder's links resolve, do not loop, and end somewhere.
    """
    if schema is None:
        schema = load_schema()

    problems = []
    _check(data, schema, "$", problems, schema)
    if not problems:
        problems = _check_ladder(data)
    if problems:
        raise PresetError(problems)
    return data


# --- the schema, checked by hand ------------------------------------------

_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float))
    and not isinstance(value, bool),
    "null": lambda value: value is None,
}


def _json_type(value):
    """How the value is named in an error message."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value, spec):
    """Whether ``value`` satisfies a ``type`` keyword (a name, or a list)."""
    names = spec if isinstance(spec, list) else [spec]
    return any(_TYPE_CHECKS.get(name, lambda _value: True)(value) for name in names)


def _resolve(schema, root, path, problems):
    """Follow a local ``$ref``, reporting any other kind and any dead one."""
    reference = schema.get("$ref") if isinstance(schema, dict) else None
    if reference is None:
        return schema

    if not reference.startswith("#/"):
        problems.append(
            f"{path}: unsupported $ref {reference!r} — only references within "
            f"this document are resolved"
        )
        return None

    node = root
    for step in reference[2:].split("/"):
        if not isinstance(node, dict) or step not in node:
            problems.append(f"{path}: $ref {reference!r} does not resolve")
            return None
        node = node[step]
    return node


def _check(value, schema, path, problems, root):
    """Add every way ``value`` fails ``schema`` to ``problems``."""
    schema = _resolve(schema, root, path, problems)
    if schema is None:
        return

    spec = schema.get("type")
    if spec is not None and not _matches_type(value, spec):
        expected = spec if isinstance(spec, str) else " or ".join(spec)
        problems.append(f"{path}: expected {expected}, got {_json_type(value)}")
        # Every other keyword would only restate the same mistake.
        return

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        allowed = ", ".join(json.dumps(item) for item in enum)
        problems.append(f"{path}: {json.dumps(value)} is not one of {allowed}")

    if isinstance(value, str):
        _check_string(value, schema, path, problems)
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float)):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(
                f"{path}: {value} is below the minimum {schema['minimum']}"
            )
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(
                f"{path}: {value} is above the maximum {schema['maximum']}"
            )
    elif isinstance(value, list):
        _check_list(value, schema, path, problems, root)
    elif isinstance(value, dict):
        _check_object(value, schema, path, problems, root)


def _check_string(value, schema, path, problems):
    if len(value) < schema.get("minLength", 0):
        problems.append(f"{path}: must not be empty")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        problems.append(f"{path}: at most {schema['maxLength']} characters")
    pattern = schema.get("pattern")
    if pattern and not re.search(pattern, value):
        problems.append(f"{path}: {json.dumps(value)} does not match {pattern}")


def _check_list(value, schema, path, problems, root):
    if len(value) < schema.get("minItems", 0):
        problems.append(
            f"{path}: needs at least {schema['minItems']} entries, has {len(value)}"
        )
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        problems.append(f"{path}: at most {schema['maxItems']} entries")
    if "items" in schema:
        for index, item in enumerate(value):
            _check(item, schema["items"], f"{path}[{index}]", problems, root)


def _check_object(value, schema, path, problems, root):
    properties = schema.get("properties", {})

    for name in schema.get("required", []):
        if name not in value:
            problems.append(f"{path}.{name}: required, but missing")

    for name, item in value.items():
        child = f"{path}.{name}"
        if name in properties:
            _check(item, properties[name], child, problems, root)
        elif schema.get("additionalProperties") is False:
            known = ", ".join(sorted(properties)) or "none"
            problems.append(f"{child}: unknown here — this level takes {known}")
        elif isinstance(schema.get("additionalProperties"), dict):
            _check(item, schema["additionalProperties"], child, problems, root)


# --- and the parts a schema cannot state ----------------------------------


def _check_ladder(data):
    """Whether the branches form a ladder anything can walk."""
    branches = data["branches"]

    index_by_key = {}
    problems = []
    for position, branch in enumerate(branches):
        key = branch["key"]
        if key in index_by_key:
            problems.append(
                f"$.branches[{position}].key: {key!r} is already used by "
                f"$.branches[{index_by_key[key]}]"
            )
        else:
            index_by_key[key] = position

    # A duplicate key makes every walk below ambiguous, and each message it
    # would produce is a restatement of this one.
    if problems:
        return problems

    for position, branch in enumerate(branches):
        target = branch.get("promotes_to")
        if target is None:
            continue
        if target not in index_by_key:
            problems.append(
                f"$.branches[{position}].promotes_to: {target!r} is not the key "
                f"of any branch in this file"
            )
        elif target == branch["key"]:
            problems.append(
                f"$.branches[{position}].promotes_to: {target!r} points at itself"
            )
        if branch.get("is_top"):
            problems.append(
                f"$.branches[{position}]: is_top is set, so this branch ends the "
                f"ladder, but promotes_to is {target!r}"
            )

    for position, branch in enumerate(branches):
        low = branch.get("min_age_dec_31")
        high = branch.get("max_age_dec_31")
        if low is not None and high is not None and low > high:
            problems.append(
                f"$.branches[{position}]: min_age_dec_31 {low} is above "
                f"max_age_dec_31 {high}"
            )

    if not any(branch.get("is_top") for branch in branches):
        problems.append(
            "$.branches: no branch is marked is_top, so members who outgrow the "
            "last one have nowhere to leave from"
        )

    problems.extend(_check_no_loop(branches, index_by_key))
    return problems


def _check_no_loop(branches, index_by_key):
    """Report each loop in the ``promotes_to`` links once."""
    problems = []
    reported = set()

    for branch in branches:
        walked = []
        key = branch["key"]
        while key is not None and key in index_by_key:
            if key in walked:
                loop = walked[walked.index(key) :] + [key]
                if frozenset(loop) not in reported:
                    reported.add(frozenset(loop))
                    problems.append(
                        "$.branches: promotes_to loops through " + " → ".join(loop)
                    )
                break
            walked.append(key)
            key = branches[index_by_key[key]].get("promotes_to")

    return problems


def _build(data, path):
    """Turn validated data into the objects the rest of the app reads."""
    return Preset(
        name=data["name"],
        title=data.get("title", ""),
        source=data.get("source", ""),
        note=data.get("note", ""),
        branches=tuple(
            PresetBranch(
                key=branch["key"],
                names=dict(branch["name"]),
                min_age=branch.get("min_age_dec_31"),
                max_age=branch.get("max_age_dec_31"),
                promotes_to=branch.get("promotes_to"),
                is_top=bool(branch.get("is_top", False)),
                sections=tuple(
                    PresetSection(
                        names=dict(section["name"]), sex=section.get("sex", "B")
                    )
                    for section in branch.get("sections", [])
                ),
            )
            for branch in data["branches"]
        ),
        path=path,
    )
