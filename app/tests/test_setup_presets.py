"""Branch presets: the files, and the schema that decides what they may say.

A preset is data a contributor can write, so the two things worth proving are
that the file this project ships describes the federation it claims to, and
that a file which does *not* describe a walkable ladder is refused with a
message naming the line to fix.
"""

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from members.presets import (
    DEFAULT_PRESET,
    PRESET_DIR,
    PresetError,
    load_preset,
    load_schema,
    preset_path,
    validate_preset,
)


def a_preset(**overrides):
    """The smallest valid preset, with ``overrides`` applied to it."""
    data = {
        "name": "test",
        "branches": [
            {
                "key": "small",
                "name": {"fr": "Petits"},
                "min_age_dec_31": 6,
                "max_age_dec_31": 8,
                "promotes_to": "big",
                "is_top": False,
                "sections": [{"name": {"fr": "Petits"}, "sex": "B"}],
            },
            {
                "key": "big",
                "name": {"fr": "Grands"},
                "min_age_dec_31": 8,
                "max_age_dec_31": 12,
                "promotes_to": None,
                "is_top": True,
                "sections": [{"name": {"fr": "Grands"}}],
            },
        ],
    }
    data.update(overrides)
    return data


class ShippedPresetTest(SimpleTestCase):
    """The preset a fresh instance starts from."""

    def setUp(self):
        self.preset = load_preset(DEFAULT_PRESET)

    def test_it_is_the_ladder_les_scouts_publishes(self):
        """Four branches, youngest first, each promoting into the next."""
        keys = [branch.key for branch in self.preset.branches]
        self.assertEqual(keys, ["baladins", "louveteaux", "eclaireurs", "pionniers"])
        self.assertEqual(
            [(branch.min_age, branch.max_age) for branch in self.preset.branches],
            [(6, 8), (8, 12), (12, 16), (16, 18)],
        )

    def test_only_the_last_branch_ends_the_ladder(self):
        for branch, last in zip(
            self.preset.branches, [False, False, False, True], strict=True
        ):
            self.assertEqual(branch.is_top, last, branch.key)
            self.assertEqual(branch.promotes_to is None, last, branch.key)

    def test_every_branch_is_named_in_french_and_dutch(self):
        """A unit that switches language reads its own branches, not blanks."""
        for branch in self.preset.branches:
            self.assertTrue(branch.names.get("fr"), branch.key)
            self.assertTrue(branch.names.get("nl"), branch.key)

    def test_the_dutch_names_are_the_federation_s_own(self):
        self.assertEqual(
            [branch.name_for("nl") for branch in self.preset.branches],
            ["Baladins", "Welpen", "Verkenners", "Pioniers"],
        )

    def test_each_branch_comes_with_one_section(self):
        """Enough to enrol a member in; a troop replaces them with its own."""
        for branch in self.preset.branches:
            self.assertEqual(len(branch.sections), 1, branch.key)
            self.assertEqual(branch.sections[0].sex, "B", branch.key)
            self.assertEqual(
                branch.sections[0].name_for("fr"), branch.name_for("fr"), branch.key
            )

    def test_the_ladder_can_be_walked_from_the_first_branch_to_the_end(self):
        """The whole point of `promotes_to`: a member always has somewhere to go."""
        by_key = {branch.key: branch for branch in self.preset.branches}
        branch = self.preset.branches[0]
        walked = []
        while branch is not None:
            walked.append(branch.key)
            branch = by_key.get(branch.promotes_to)
        self.assertEqual(walked, list(by_key))

    def test_it_refuses_to_name_a_unit(self):
        """The federation's layout is not one troop's section names.

        The sections a unit actually has (Limal's "Meute Waigunga", …) belong
        in the database the troop edits, not in a file every instance ships.
        """
        text = (PRESET_DIR / f"{DEFAULT_PRESET}.json").read_text(encoding="utf-8")
        for unit_specific in ("Limal", "Waigunga", "Brocéliande", "Seeonee"):
            self.assertNotIn(unit_specific, text)


class SchemaTest(SimpleTestCase):
    """What a preset file may say, and what it may not."""

    def setUp(self):
        self.schema = load_schema()

    def assertRejected(self, data, expected):
        """The preset is refused, with ``expected`` somewhere in the reasons."""
        with self.assertRaises(PresetError) as caught:
            validate_preset(data, self.schema)
        joined = "\n".join(caught.exception.problems)
        self.assertIn(expected, joined, f"expected {expected!r} in:\n{joined}")

    def test_the_schema_itself_is_json_schema_shaped(self):
        self.assertIn("$schema", self.schema)
        self.assertEqual(self.schema["type"], "object")

    def test_a_well_formed_preset_passes(self):
        validate_preset(a_preset(), self.schema)

    def test_the_optional_top_level_fields_are_optional(self):
        minimal = {"name": "test", "branches": a_preset()["branches"]}
        validate_preset(minimal, self.schema)

    def test_a_missing_required_section_is_named(self):
        data = a_preset()
        data["branches"][0]["name"] = {}
        self.assertRejected(data, "$.branches[0].name.fr: required, but missing")

    def test_an_unknown_key_is_named_with_what_is_allowed(self):
        data = a_preset()
        data["branches"][0]["colour"] = "blue"
        self.assertRejected(data, "$.branches[0].colour: unknown here")

    def test_an_unknown_sex_is_refused(self):
        data = a_preset()
        data["branches"][0]["sections"][0]["sex"] = "X"
        self.assertRejected(data, "is not one of \"M\", \"F\", \"B\"")

    def test_an_age_that_is_not_a_number_is_refused(self):
        data = a_preset()
        data["branches"][0]["min_age_dec_31"] = "six"
        self.assertRejected(data, "$.branches[0].min_age_dec_31: expected")

    def test_an_empty_ladder_is_refused(self):
        self.assertRejected(a_preset(branches=[]), "needs at least 1 entries")

    def test_a_branch_key_that_is_not_a_slug_is_refused(self):
        data = a_preset()
        data["branches"][0]["key"] = "Les Petits"
        self.assertRejected(data, "does not match")

    def test_every_problem_is_reported_at_once(self):
        """Fixing a preset one error per run would be a poor way to spend an evening."""
        data = a_preset()
        data["branches"][0]["key"] = "Nope"
        data["branches"][0]["sections"][0]["sex"] = "X"
        with self.assertRaises(PresetError) as caught:
            validate_preset(data, self.schema)
        self.assertEqual(len(caught.exception.problems), 2)


class LadderTest(SimpleTestCase):
    """What the schema cannot state: that the links describe a real ladder."""

    def setUp(self):
        self.schema = load_schema()

    def assertRejected(self, data, expected):
        with self.assertRaises(PresetError) as caught:
            validate_preset(data, self.schema)
        joined = "\n".join(caught.exception.problems)
        self.assertIn(expected, joined, f"expected {expected!r} in:\n{joined}")

    def test_a_link_to_a_branch_that_is_not_there_is_refused(self):
        data = a_preset()
        data["branches"][0]["promotes_to"] = "grands"
        self.assertRejected(data, "'grands' is not the key of any branch")

    def test_a_branch_that_promotes_into_itself_is_refused(self):
        data = a_preset()
        data["branches"][0]["promotes_to"] = "small"
        self.assertRejected(data, "'small' points at itself")

    def test_a_duplicate_key_is_refused(self):
        data = a_preset()
        data["branches"][1]["key"] = "small"
        self.assertRejected(data, "already used by $.branches[0]")

    def test_an_endless_ladder_is_refused(self):
        """Every rung pointing at the next one, with no end to leave from."""
        data = a_preset()
        data["branches"][1]["promotes_to"] = "small"
        data["branches"][1]["is_top"] = False
        self.assertRejected(data, "promotes_to loops through")

    def test_a_branch_that_both_ends_the_ladder_and_promotes_is_refused(self):
        data = a_preset()
        data["branches"][1]["promotes_to"] = "small"
        self.assertRejected(data, "is_top is set")

    def test_a_ladder_with_no_top_is_refused(self):
        data = a_preset()
        data["branches"][1]["is_top"] = False
        self.assertRejected(data, "no branch is marked is_top")

    def test_an_age_range_the_wrong_way_round_is_refused(self):
        data = a_preset()
        data["branches"][0]["min_age_dec_31"] = 10
        data["branches"][0]["max_age_dec_31"] = 8
        self.assertRejected(data, "is above max_age_dec_31")

    def test_one_branch_on_its_own_is_a_ladder(self):
        """A small unit starting with only its youngest branch is not an error."""
        validate_preset(
            a_preset(
                branches=[
                    {
                        "key": "baladins",
                        "name": {"fr": "Baladins"},
                        "min_age_dec_31": 6,
                        "max_age_dec_31": 8,
                        "is_top": True,
                    }
                ]
            ),
            self.schema,
        )


class PathTest(SimpleTestCase):
    """`--preset` takes a shipped name or a path to a file."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def write(self, name, text):
        path = Path(self.directory.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_bare_name_is_a_shipped_preset(self):
        self.assertEqual(preset_path("les-scouts"), PRESET_DIR / "les-scouts.json")

    def test_a_json_suffix_is_a_path(self):
        self.assertEqual(preset_path("mine.json"), Path("mine.json"))

    def test_a_separator_is_a_path(self):
        self.assertEqual(
            preset_path("contrib/mine.json"), Path("contrib/mine.json")
        )

    def test_a_name_that_is_not_there_is_reported_not_substituted(self):
        """A typo must not quietly fall back to the shipped preset."""
        with self.assertRaises(PresetError) as caught:
            load_preset("no-such-preset")
        self.assertIn("cannot be read", str(caught.exception))

    def test_a_file_that_is_not_json_is_reported_with_its_line(self):
        path = self.write("broken.json", "{ not json")
        with self.assertRaises(PresetError) as caught:
            load_preset(str(path))
        self.assertIn("invalid JSON", str(caught.exception))
        self.assertIn("broken.json:1:3", str(caught.exception))

    def test_a_custom_file_is_validated_the_same_way(self):
        """A contributed preset meets the same schema the shipped one does."""
        path = self.write("custom.json", json.dumps(a_preset(branches=[])))
        with self.assertRaises(PresetError) as caught:
            load_preset(str(path))
        self.assertIn("needs at least 1 entries", str(caught.exception))
