# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDistributionClientsApplication(TransactionCase):
    def test_root_menu_uses_application_icon(self):
        menu = self.env.ref(
            "dreyes_dist_clients.menu_distribution_clients_root"
        )
        self.assertEqual(
            menu.web_icon,
            "dreyes_dist_clients,static/description/icon.png",
        )

    def test_main_action_contains_all_requested_views(self):
        action = self.env.ref("dreyes_dist_clients.action_distribution_clients_all")
        self.assertEqual(action.view_mode, "kanban,list,form,graph,pivot")
        self.assertEqual(
            set(action.view_ids.mapped("view_mode")),
            {"kanban", "list", "form", "graph", "pivot"},
        )

    def test_pending_action_uses_workflow_domain_and_views(self):
        action = self.env.ref("dreyes_dist_clients.action_distribution_clients_pending")
        self.assertIn("under_review", action.domain)
        self.assertIn("pending_approval", action.domain)
        self.assertEqual(
            set(action.view_ids.mapped("view_mode")),
            {"kanban", "list", "form", "graph", "pivot"},
        )

    def test_analysis_measure_and_admin_access(self):
        profile = self.env["dreyes.distributor.profile"].new({})
        self.assertEqual(profile.request_count, 1)
        self.assertTrue(self.env.ref("base.user_admin").has_group("dreyes_dist.group_distribution_reviewer"))


@tagged("post_install", "-at_install")
class TestDistributionClientsBackend(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].create({
            "name": "Backend clients test", "company_id": cls.env.company.id,
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Backend Buyer", "first_name": "Ana", "last_name": "Buyer",
            "email": "backend-buyer@example.com", "phone": "5125550100",
            "street": "1 Main St", "city": "Austin", "zip": "78701",
            "country_id": cls.env.ref("base.us").id,
            "state_id": cls.env.ref("base.state_us_43").id,
        })
        cls.pricelist = cls.env["product.pricelist"].create({"name": "Backend prices"})
        cls.segment = cls.env["dreyes.market.segment"].create({
            "name": "Backend clients", "pricelist_id": cls.pricelist.id,
        })
        cls.profile = cls.env["dreyes.distributor.profile"].create({
            "partner_id": cls.partner.id, "company_id": cls.env.company.id,
            "website_id": cls.website.id, "legal_business_name": "Backend Buyer LLC",
            "ein": "123456789", "tax_permit_number": "12345678901",
            "segment_id": cls.segment.id,
        })
        attachment = cls.env["ir.attachment"].create({
            "name": "permit.pdf", "datas": base64.b64encode(b"test permit"),
            "res_model": cls.profile._name, "res_id": cls.profile.id,
        })
        cls.profile.current_permit_id = cls.env["dreyes.distributor.permit"].create({
            "profile_id": cls.profile.id, "attachment_id": attachment.id,
            "filename": "permit.pdf",
        })

    def _approve(self):
        self.profile.action_send_to_review()
        self.profile.action_mark_reviewed()
        self.profile.action_approve()
        self.assertTrue(self.profile.can_purchase)

    def test_edit_contact_from_profile(self):
        self.profile.write({
            "contact_email": "updated@example.com", "contact_phone": "5125550199",
            "contact_first_name": "Maria", "street": "2 Main St", "zip": "78702",
        })
        self.assertEqual(self.partner.email, "updated@example.com")
        self.assertEqual(self.partner.phone, "5125550199")
        self.assertEqual(self.partner.first_name, "Maria")
        self.assertEqual(self.partner.street, "2 Main St")
        self.assertEqual(self.partner.zip, "78702")

    def test_upload_permit_preserves_history_and_requires_new_review(self):
        self._approve()
        previous = self.profile.current_permit_id
        wizard = self.env["dreyes.distributor.permit.upload"].create({
            "profile_id": self.profile.id, "filename": "new-permit.pdf",
            "file": base64.b64encode(b"%PDF-1.4 new permit"),
        })
        wizard.action_upload()
        current = self.profile.current_permit_id
        self.assertNotEqual(current, previous)
        self.assertIn(previous, self.profile.permit_ids)
        self.assertEqual(current.uploaded_by_id, self.env.user)
        self.assertEqual(self.profile.tax_permit_filename, "new-permit.pdf")
        self.assertEqual(base64.b64decode(self.profile.tax_permit_file), b"%PDF-1.4 new permit")
        self.assertFalse(current.attachment_id.public)
        self.assertEqual(self.profile.state, "under_review")
        self.assertFalse(self.profile.can_purchase)
        self.assertFalse(self.profile.approved_at)

    def test_upload_permit_rejects_invalid_files_without_replacing_current(self):
        previous = self.profile.current_permit_id
        for filename, payload in [
            ("bad.exe", base64.b64encode(b"invalid")),
            ("empty.pdf", base64.b64encode(b"")),
            ("invalid.pdf", b"not base64"),
            ("large.pdf", base64.b64encode(b"x" * (15 * 1024 * 1024 + 1))),
        ]:
            wizard = self.env["dreyes.distributor.permit.upload"].new({
                "profile_id": self.profile.id, "filename": filename, "file": payload,
            })
            with self.assertRaises(UserError):
                wizard.action_upload()
            self.assertEqual(self.profile.current_permit_id, previous)

    def test_public_user_cannot_open_upload(self):
        with self.assertRaises(UserError):
            self.profile.with_user(self.env.ref("base.public_user")).action_upload_tax_permit()

    def test_reviewer_can_upload_without_direct_permit_create_access(self):
        reviewer = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Permit reviewer", "login": "permit-reviewer@example.com",
            "company_id": self.env.company.id, "company_ids": [(6, 0, self.env.company.ids)],
            "group_ids": [(6, 0, self.env.ref("dreyes_dist.group_distribution_reviewer").ids)],
        })
        wizard = self.env["dreyes.distributor.permit.upload"].with_user(reviewer).create({
            "profile_id": self.profile.id, "filename": "reviewer.pdf",
            "file": base64.b64encode(b"%PDF-1.4 reviewer"),
        })
        wizard.action_upload()
        self.assertEqual(self.profile.current_permit_id.uploaded_by_id, reviewer)

    def test_return_approved_customer_to_review_and_reapprove(self):
        self._approve()
        self.profile.action_send_to_review()
        self.assertEqual(self.profile.state, "under_review")
        self.assertFalse(self.profile.can_purchase)
        self.assertFalse(self.profile.approved_at)
        self.assertFalse(self.profile.approved_by_id)
        self.assertFalse(self.profile.reviewed_at)
        self.assertEqual(self.profile.submitted_by_id, self.env.user)
        self.profile.action_mark_reviewed()
        self.profile.action_approve()
        self.assertTrue(self.profile.can_purchase)

    def test_reset_preserves_customer_data_and_revokes_purchase(self):
        self._approve()
        self.profile.action_reset_profile()
        self.assertEqual(self.profile.state, "no_profile")
        self.assertFalse(self.profile.can_purchase)
        self.assertFalse(self.profile.submitted_at)
        self.assertFalse(self.profile.reviewed_at)
        self.assertFalse(self.profile.approved_at)
        self.assertEqual(self.profile.legal_business_name, "Backend Buyer LLC")
        self.assertTrue(self.profile.current_permit_id)

    def test_approval_rechecks_data_after_review(self):
        self.profile.action_send_to_review()
        self.profile.action_mark_reviewed()
        self.profile.contact_phone = False
        with self.assertRaises(UserError):
            self.profile.action_approve()
        self.assertEqual(self.profile.state, "pending_approval")

    def test_approval_requires_active_pricelist(self):
        self.profile.action_send_to_review()
        self.profile.action_mark_reviewed()
        self.pricelist.active = False
        with self.assertRaises(UserError):
            self.profile.action_approve()
        self.assertFalse(self.profile.can_purchase)

    def test_public_user_cannot_change_state(self):
        profile = self.profile.with_user(self.env.ref("base.public_user"))
        for action in (profile.action_send_to_review, profile.action_reset_profile):
            with self.assertRaises(UserError):
                action()
        self.assertEqual(self.profile.state, "no_profile")
