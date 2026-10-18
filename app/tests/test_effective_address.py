"""A child without an address of their own is read at the parent's.

The address is what bills a family together, so an empty child address must
not fall through to the unnamed "no address" group. The primary contact's
address wins when several parents are linked, and the forms show it in the
address field instead of leaving it blank.
"""

from datetime import date

from django.urls import reverse

from members.forms import ChildForm
from members.models import Account, ParentChild, Person, Role

from .base import TroopSettingsTestCase


class EffectiveAddressTest(TroopSettingsTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_child = Role.objects.get(short=Person.CHILD_ROLE_SHORT)
        cls.role_parent = Role.objects.get(short="p")
        cls.child = Person.objects.create(
            first_name="Enfant",
            last_name="Test",
            primary_role=cls.role_child,
            status="a",
            sex="M",
            birthday=date(2016, 6, 15),
        )
        cls.parent = Person.objects.create(
            first_name="Parent",
            last_name="Test",
            primary_role=cls.role_parent,
            status="a",
            address="Rue du Test 1, 1300 Wavre",
        )
        ParentChild.objects.create(
            parent=cls.parent, child=cls.child, primary_contact=True
        )

    def test_their_own_address_wins(self):
        self.child.address = "Rue Haute 3, 1300 Wavre"
        self.child.save(update_fields=["address"])

        self.assertEqual(
            self.child.effective_address(), "Rue Haute 3, 1300 Wavre"
        )

    def test_an_empty_address_reads_the_parents(self):
        self.assertEqual(
            self.child.effective_address(), "Rue du Test 1, 1300 Wavre"
        )

    def test_the_primary_contact_wins_over_another_parent(self):
        other = Person.objects.create(
            first_name="Autre",
            last_name="Parent",
            primary_role=self.role_parent,
            status="a",
            address="Avenue du Parc 34, 1340 Ottignies",
        )
        # The newer link is the primary one, and its address is the one to
        # read even though the older link has the lower pk.
        ParentChild.objects.filter(
            parent=self.parent, child=self.child
        ).update(primary_contact=False)
        ParentChild.objects.create(
            parent=other, child=self.child, primary_contact=True
        )

        self.assertEqual(
            self.child.effective_address(), "Avenue du Parc 34, 1340 Ottignies"
        )

    def test_no_address_anywhere_is_empty(self):
        self.parent.address = ""
        self.parent.save(update_fields=["address"])
        self.child.refresh_from_db()

        self.assertEqual(self.child.effective_address(), "")

    def test_the_member_page_shows_the_parents_address(self):
        account = Account.objects.create_user(
            email="staff@test.be",
            password="pass",
            is_staff=True,
            person=Person.objects.create(
                first_name="Admin",
                last_name="Test",
                primary_role=self.role_parent,
                status="a",
            ),
        )
        self.client.force_login(account)

        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": self.child.pk})
        )

        self.assertEqual(
            response.context["form"].fields["address"].initial,
            "Rue du Test 1, 1300 Wavre",
        )

    def test_the_child_form_shows_the_parents_address(self):
        form = ChildForm(instance=self.child)

        self.assertEqual(
            form.fields["address"].initial, "Rue du Test 1, 1300 Wavre"
        )
