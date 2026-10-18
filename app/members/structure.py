"""The branch and section editor, shared by the first-run wizard and staff.

The editor is a plain form over rows rendered by templates: the wizard's
structure step and the unit's ongoing sections tool are the same editor, so a
troop cannot get a different answer about its branches depending on which page
it opened. This module holds the rows, the parser and the writer; the two
callers supply the page around it.

The writer deletes what the editor no longer lists. The wizard runs before
anyone can have enrolled, so it trusts that; the staff tool passes
``enforce_empty_deletions``, which refuses to remove a branch or section that
members, activities or messages still reference.
"""

import uuid
from dataclasses import dataclass, field

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext as gettext
from django.utils.translation import gettext_lazy as _

from members.models import Branch, Enrollment, Section, SectionEvent
from members.presets import load_preset

#: The sex a section takes, in the editor's own words. ``Section.Sex``'s
#: labels are not translatable, and this is a page a person reads, so the
#: editor spells them out rather than inheriting "Both" and "Male".
SECTION_SEXES = (
    ("B", _("Both")),
    ("M", _("Boys")),
    ("F", _("Girls")),
)

#: The languages a branch or section name may be written in, in the order the
#: editor shows them.
NAME_LANGUAGES = ("fr", "nl", "en")

@dataclass
class SectionEntry:
    """One row of the structure editor's section list."""

    id: str
    names: dict
    sex: str = "B"
    branch: str = ""
    #: Where answers to this section's mail go. Empty means the unit's
    #: reply-to address, which is the ordinary case.
    email: str = ""
    #: The languages this row is being edited in. Carried on the row because a
    #: template cannot index a dict by a variable, and the alternative — one
    #: branch of markup per language — is worse.
    languages: tuple = ()

    @property
    def name_fields(self):
        """The name inputs to render, in the order they are edited in."""
        return [
            {"language": language, "value": self.names.get(language, "")}
            for language in self.languages
        ]


@dataclass
class BranchEntry:
    """One row of the structure editor's branch list."""

    id: str
    key: str = ""
    names: dict = field(default_factory=dict)
    min_age: int | None = None
    max_age: int | None = None
    sections: list = field(default_factory=list)
    languages: tuple = ()

    @property
    def name_fields(self):
        """The name inputs to render, in the order they are edited in."""
        return [
            {"language": language, "value": self.names.get(language, "")}
            for language in self.languages
        ]


@dataclass
class StructureChange:
    """What saving the structure editor did."""

    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    removed: list = field(default_factory=list)


def new_row_id():
    """A fresh identifier for a row the browser just added."""
    return uuid.uuid4().hex[:8]


def default_structure(languages=()):
    """The federation's own layout, as the editor's starting rows."""
    return [
        BranchEntry(
            id=rung.key,
            key=rung.key,
            names={
                language: rung.names.get(language, rung.names["fr"])
                for language in NAME_LANGUAGES
            },
            min_age=rung.min_age,
            max_age=rung.max_age,
            languages=tuple(languages),
            sections=[
                SectionEntry(
                    id=f"{rung.key}-{index}",
                    names={
                        language: section.names.get(language, section.names["fr"])
                        for language in NAME_LANGUAGES
                    },
                    sex=section.sex,
                    branch=rung.key,
                    languages=tuple(languages),
                )
                for index, section in enumerate(rung.sections)
            ],
        )
        for rung in load_preset().branches
    ]


def structure_from_database(languages=()):
    """The branches and sections this instance already has, as editor rows."""
    return [
        BranchEntry(
            id=branch.key or f"branch-{branch.pk}",
            key=branch.key,
            names={
                language: getattr(branch, f"name_{language}") or ""
                for language in NAME_LANGUAGES
            },
            min_age=branch.min_age_dec_31,
            max_age=branch.max_age_dec_31,
            languages=tuple(languages),
            sections=[
                SectionEntry(
                    id=f"section-{section.pk}",
                    names={
                        language: getattr(section, f"name_{language}") or ""
                        for language in NAME_LANGUAGES
                    },
                    sex=section.sex or Section.Sex.BOTH,
                    branch=branch.key or f"branch-{branch.pk}",
                    email=section.email,
                    languages=tuple(languages),
                )
                for section in branch.section_set.order_by("pk")
            ],
        )
        for branch in Branch.objects.order_by("min_age_dec_31", "name")
    ]


def new_section_entry(branch_id, languages=()):
    """An empty section row, for the editor's "add a section" button."""
    return SectionEntry(
        id=f"new-{new_row_id()}", names={}, branch=branch_id, languages=tuple(languages)
    )


def new_branch_entry(languages=()):
    """An empty branch row, for the editor's "add a branch" button."""
    return BranchEntry(id=f"new-{new_row_id()}", key="", names={}, languages=tuple(languages))


def sex_label(value):
    """The editor's word for a section's sex, for a template."""
    return dict(SECTION_SEXES).get(value or Section.Sex.BOTH, "")


class StructureForm(forms.Form):
    """The branch and section editor, parsed from the rows that were posted.

    Rows are read back by *position* rather than by index — one list of values
    per field, in document order — which is what lets the editor add and
    remove rows with no bookkeeping in the browser at all: a row that is no
    longer on the page is simply no longer in the post, and a row that was
    added is at the end. Each section carries the id of the branch it sits
    under, so the two lists stay in step however the page was rearranged.
    """

    def __init__(
        self,
        data=None,
        languages=("fr",),
        request=None,
        enforce_empty_deletions=False,
    ):
        super().__init__(data)
        self.request = request
        # The wizard runs before anyone can have enrolled, so it may remove a
        # row without asking. The staff tool cannot: it asks clean() to refuse
        # any removal that would take members, activities or messages with it.
        self.enforce_empty_deletions = enforce_empty_deletions
        # Only the languages the site offers are edited; see
        # StructureStep.name_languages. Names are still read in every language
        # so a preset's other-language names are carried through untouched.
        self.languages = [language for language in languages if language in NAME_LANGUAGES]
        self.branch_entries = []

        if data is None:
            self.branch_entries = structure_from_database(self.languages) or (
                default_structure(self.languages)
            )
            return

        self.branch_entries = self._parse(data)
        self._attach_sections()

    # -- reading the posted rows -------------------------------------------

    @staticmethod
    def _many(data, name):
        """Every value posted under ``name``, in document order."""
        if hasattr(data, "getlist"):
            return data.getlist(name)
        return [value for key, value in data.items() if key == name]

    def _parse(self, data):
        ids = self._many(data, "branch-id")
        keys = self._many(data, "branch-key")
        minimums = self._many(data, "branch-min")
        maximums = self._many(data, "branch-max")
        names = {
            language: self._many(data, f"branch-name-{language}")
            for language in self.languages
        }

        entries = []
        for position, row_id in enumerate(ids):
            entries.append(
                BranchEntry(
                    id=row_id,
                    key=_at(keys, position).strip(),
                    languages=tuple(self.languages),
                    names={
                        language: _at(names[language], position).strip()
                        for language in self.languages
                    },
                    min_age=_age(_at(minimums, position)),
                    max_age=_age(_at(maximums, position)),
                )
            )

        self.section_entries = []
        section_ids = self._many(data, "section-id")
        parents = self._many(data, "section-branch")
        sexes = self._many(data, "section-sex")
        emails = self._many(data, "section-email")
        section_names = {
            language: self._many(data, f"section-name-{language}")
            for language in self.languages
        }
        for position, row_id in enumerate(section_ids):
            self.section_entries.append(
                SectionEntry(
                    id=row_id,
                    names={
                        language: _at(section_names[language], position).strip()
                        for language in self.languages
                    },
                    sex=_at(sexes, position) or Section.Sex.BOTH,
                    branch=_at(parents, position),
                    email=_at(emails, position).strip(),
                    languages=tuple(self.languages),
                )
            )
        return entries

    def _attach_sections(self):
        """Put each section under the branch row it names."""
        by_id = {entry.id: entry for entry in self.branch_entries}
        for entry in self.section_entries:
            parent = by_id.get(entry.branch)
            if parent is not None:
                parent.sections.append(entry)

    # -- validating --------------------------------------------------------

    def clean(self):
        cleaned = super().clean()
        if not self.branch_entries:
            raise ValidationError(_("A unit needs at least one branch."))
        if not self.languages:
            raise ValidationError(_("Enable at least one language first."))

        first_language = self.languages[0]
        for position, branch in enumerate(self.branch_entries, start=1):
            name = branch.names.get(first_language, "")
            label = name or gettext("Branch %(number)s") % {"number": position}
            if not name:
                raise ValidationError(
                    _("Branch %(number)s needs a name.") % {"number": position}
                )
            if (
                branch.min_age is not None
                and branch.max_age is not None
                and branch.min_age > branch.max_age
            ):
                raise ValidationError(
                    _("%(branch)s: the youngest age is above the oldest.") % {
                        "branch": label
                    }
                )
            if not branch.sections:
                raise ValidationError(
                    _("%(branch)s needs at least one section.") % {"branch": label}
                )
            for section in branch.sections:
                section_name = section.names.get(first_language, "")
                if not section_name:
                    raise ValidationError(
                        _("%(branch)s: every section needs a name.") % {
                            "branch": label
                        }
                    )
                if section.email:
                    try:
                        validate_email(section.email)
                    except ValidationError:
                        raise ValidationError(
                            _(
                                "%(branch)s: %(section)s has an invalid email address."
                            )
                            % {"branch": label, "section": section_name}
                        ) from None

        if self.enforce_empty_deletions:
            self._check_removals()
        return cleaned

    def _check_removals(self):
        """Refuse a removal that would take referenced rows with it.

        The writer deletes what the editor no longer lists, and a section FK
        cascades its activities and messages. Before anyone has enrolled that
        is harmless; afterwards it is data loss the editor did not ask about,
        so the row has to be emptied by hand or removed in the Django admin,
        which is the deliberate escape hatch.
        """
        kept_branches = {entry.id for entry in self.branch_entries}
        kept_sections = {
            section.id
            for branch in self.branch_entries
            for section in branch.sections
        }
        kept_section_pks = {
            int(row_id.removeprefix("section-"))
            for row_id in kept_sections
            if row_id.startswith("section-")
        }

        for section in Section.objects.all():
            if section.pk in kept_section_pks:
                continue
            if _is_referenced(section):
                raise ValidationError(
                    _(
                        "“%(name)s” is still used by members, activities or "
                        "messages, so it cannot be removed here. The Django "
                        "admin can delete it."
                    )
                    % {"name": section}
                )

        for branch in Branch.objects.all():
            if branch.key in kept_branches or f"branch-{branch.pk}" in kept_branches:
                continue
            # Only sections that are going away with the branch; one that is
            # being moved to another row keeps its references and its branch
            # can still be removed.
            sections = Section.objects.filter(branch=branch).exclude(
                pk__in=kept_section_pks
            )
            if any(_is_referenced(section) for section in sections):
                raise ValidationError(
                    _(
                        "“%(name)s” is still used by members, activities or "
                        "messages, so it cannot be removed here. The Django "
                        "admin can delete it."
                    )
                    % {"name": branch}
                )

    # -- writing -----------------------------------------------------------

    def save(self):
        """Write the structure, and report what changed.

        The editor *is* the troop's structure, so what it describes is what
        ends up in the database: branches and sections that are no longer in
        it are removed. Nothing can be lost by that — the wizard only runs
        before the instance has an administrator, which is to say before
        anybody could have enrolled in anything — but :func:`_delete_safely`
        holds back anything that somehow has an enrolment anyway.
        """
        change = StructureChange()
        branches = {}

        for entry in self.branch_entries:
            branch = self._branch_for(entry)
            is_new = branch.pk is None
            for language in NAME_LANGUAGES:
                if language in entry.names:
                    setattr(branch, f"name_{language}", entry.names[language])
            name = branch.name_fr or ""
            if not branch.key:
                branch.key = entry.key or entry.id
            branch.min_age_dec_31 = entry.min_age
            branch.max_age_dec_31 = entry.max_age
            branch.save()
            branches[entry.id] = branch
            (change.created if is_new else change.updated).append(name)

        # The ladder is the order of the list: each rung leads to the next, and
        # the last one is where members leave the unit for good.
        for position, entry in enumerate(self.branch_entries):
            branch = branches[entry.id]
            following = self.branch_entries[position + 1 : position + 2]
            branch.promotes_to = branches[following[0].id] if following else None
            branch.is_top = not following
            branch.save(update_fields=["promotes_to", "is_top"])

        kept = self._save_sections(branches)
        change.removed += _delete_safely(Section.objects.exclude(pk__in=kept))
        change.removed += _delete_safely(
            Branch.objects.exclude(pk__in=[b.pk for b in branches.values()])
        )
        return change

    def _branch_for(self, entry):
        """The branch this row is, whether or not it exists yet.

        Matched by the key a previous save gave it, then by its name in any
        language being edited: re-opening the wizard edits the branches it
        created rather than adding a second set beside them, and a branch the
        troop renamed is still recognised after a reload.
        """
        if entry.key:
            existing = Branch.objects.filter(key=entry.key).first()
            if existing is not None:
                return existing
        if entry.id:
            existing = Branch.objects.filter(key=entry.id).first()
            if existing is not None:
                return existing
        for language in NAME_LANGUAGES:
            name = entry.names.get(language)
            if name:
                existing = Branch.objects.filter(**{f"name_{language}": name}).first()
                if existing is not None:
                    return existing
        return Branch()

    def _save_sections(self, branches):
        """Write every section row, and return the pks that are still wanted."""
        kept = set()
        for entry in self.branch_entries:
            branch = branches[entry.id]
            for section in entry.sections:
                row = self._section_for(section, branch)
                for language in NAME_LANGUAGES:
                    if language in section.names:
                        setattr(row, f"name_{language}", section.names[language])
                row.sex = section.sex if section.sex in dict(SECTION_SEXES) else Section.Sex.BOTH
                row.branch = branch
                row.email = section.email
                row.save()
                kept.add(row.pk)
        return kept

    def _section_for(self, entry, branch):
        """The section this row is, whether or not it exists yet.

        The hidden row id is the section's own identity, so renaming it keeps
        the row — and with it the enrolments, activities and messages that
        name it. A section without an id in the database (a new row, or a
        name from a preset) is matched by name inside its branch, which is how
        a troop tells one of its sections from another.
        """
        if entry.id.startswith("section-"):
            try:
                existing = Section.objects.filter(pk=int(entry.id[8:])).first()
            except ValueError:
                existing = None
            if existing is not None:
                return existing
        for language in NAME_LANGUAGES:
            name = entry.names.get(language)
            if name:
                existing = (
                    Section.objects.filter(branch=branch)
                    .filter(**{f"name_{language}": name})
                    .first()
                )
                if existing is not None:
                    return existing
        return Section(branch=branch)


def _is_referenced(section):
    """True when deleting this section would take something else with it.

    ``SectionEvent`` and ``SectionMessage`` cascade from their section, and an
    enrolment names one; anything but an empty section is a row whose removal
    belongs in the Django admin, where the cascade is a deliberate choice.
    """
    from messaging.models import SectionMessage

    return (
        Enrollment.objects.filter(section=section).exists()
        or SectionEvent.objects.filter(section=section).exists()
        or SectionMessage.objects.filter(section=section).exists()
    )


def _delete_safely(queryset):
    """Delete what the editor no longer describes, holding back what it must.

    A branch or section that is still referenced is left where it is: the
    wizard runs before anybody can have enrolled, so this should never find
    one, and the staff tool's clean() has already refused the save when it
    would. If one slips through, leaving the data alone is the right answer.
    """
    removed = []
    for row in queryset:
        if isinstance(row, Section):
            in_use = _is_referenced(row)
        else:
            in_use = any(
                _is_referenced(section)
                for section in Section.objects.filter(branch=row)
            )
        if in_use:
            continue
        removed.append(str(row))
        row.delete()
    return removed


def _at(values, position):
    """``values[position]``, or ``""`` when the lists are uneven."""
    if position < len(values):
        return values[position] or ""
    return ""


def _age(text):
    """An age from a number input, or None when it was left empty."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return max(0, min(99, value))
