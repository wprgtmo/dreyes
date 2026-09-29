# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..hooks import migrate_existing_profiles


@tagged("post_install", "-at_install")
class TestDistributionProfile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Distribution Test"})
        cls.website = cls.env["website"].create({
            "name": "Distribution Test", "domain": "distribution-test.example.com",
            "company_id": cls.company.id, "signup_form_type": "extended",
        })
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Wholesale Test", "company_id": cls.company.id,
        })
        cls.segment = cls.env["dreyes.market.segment"].create({
            "name": "Independent", "company_id": cls.company.id, "pricelist_id": cls.pricelist.id,
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Buyer Test", "first_name": "Ana", "last_name": "Buyer",
            "email": "buyer@example.com", "street": "1 Main St", "city": "Austin",
            "state_id": cls.env.ref("base.state_us_43").id, "zip": "78701",
            "country_id": cls.env.ref("base.us").id, "phone": "+1 5125550100",
        })
        cls.portal_user = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Buyer Test", "login": "buyer-dist-test@example.com", "partner_id": cls.partner.id,
            "company_id": cls.company.id, "company_ids": [(6, 0, [cls.company.id])],
            "groups_id": [(6, 0, [cls.env.ref("base.group_portal").id])],
        })
        cls.reviewer = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Distribution Reviewer", "login": "reviewer-dist-test@example.com",
            "email": "reviewer@example.com", "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
            "groups_id": [(6, 0, [cls.env.ref("dreyes_dist.group_distribution_reviewer").id])],
        })
        cls.profile = cls.env["dreyes.distributor.profile"].create({
            "partner_id": cls.partner.id, "company_id": cls.company.id, "website_id": cls.website.id,
            "legal_business_name": "Buyer LLC", "ein": "123456789", "tax_permit_number": "12345678901",
            "segment_id": cls.segment.id, "state": "under_review",
        })
        attachment = cls.env["ir.attachment"].create({
            "name": "permit.pdf", "datas": base64.b64encode(b"test permit"),
            "mimetype": "application/pdf", "res_model": cls.profile._name, "res_id": cls.profile.id,
        })
        permit = cls.env["dreyes.distributor.permit"].create({
            "profile_id": cls.profile.id, "attachment_id": attachment.id, "filename": attachment.name,
            "mimetype": attachment.mimetype,
        })
        cls.profile.current_permit_id = permit

    def test_review_and_approval_activate_segment_pricelist(self):
        profile = self.profile.with_user(self.reviewer)
        profile.action_mark_reviewed()
        self.assertEqual(profile.state, "pending_approval")
        profile.action_approve()
        self.assertEqual(profile.state, "approved")
        self.assertTrue(profile.can_purchase)
        self.assertEqual(self.partner.with_company(self.company).property_product_pricelist, self.pricelist)

    def test_segment_change_requires_new_approval(self):
        self.profile.with_user(self.reviewer).action_mark_reviewed()
        self.profile.with_user(self.reviewer).action_approve()
        other_pricelist = self.env["product.pricelist"].create({"name": "Wholesale 2", "company_id": self.company.id})
        other_segment = self.env["dreyes.market.segment"].create({
            "name": "Chain", "company_id": self.company.id, "pricelist_id": other_pricelist.id,
        })
        self.profile.segment_id = other_segment
        self.assertEqual(self.profile.state, "pending_approval")
        self.assertFalse(self.profile.can_purchase)

    def test_corrections_require_reason_and_suspend_purchase(self):
        self.profile.with_user(self.reviewer).action_mark_reviewed()
        self.profile.with_user(self.reviewer).action_approve()
        with self.assertRaises(UserError):
            self.profile.with_user(self.reviewer).action_request_corrections()
        self.profile.correction_reason = "Upload a readable permit."
        self.profile.with_user(self.reviewer).action_request_corrections()
        self.assertEqual(self.profile.state, "no_profile")
        self.assertFalse(self.profile.can_purchase)

    def test_tax_number_formats(self):
        with self.assertRaises(ValidationError):
            self.profile.ein = "123"
        with self.assertRaises(ValidationError):
            self.profile.tax_permit_number = "TX-123"

    def test_segment_company_and_archive_guards(self):
        other_company = self.env["res.company"].create({"name": "Other Test"})
        other_pricelist = self.env["product.pricelist"].create({"name": "Other", "company_id": other_company.id})
        with self.assertRaises(ValidationError):
            self.env["dreyes.market.segment"].create({
                "name": "Invalid", "company_id": self.company.id, "pricelist_id": other_pricelist.id,
            })
        self.profile.with_user(self.reviewer).action_mark_reviewed()
        self.profile.with_user(self.reviewer).action_approve()
        with self.assertRaises(UserError):
            self.segment.active = False

    def test_distribution_site_purchase_gate(self):
        website = self.website.with_user(self.portal_user)
        self.assertFalse(website._dreyes_can_purchase())
        product = self.env["product.template"].create({"name": "Protected product", "list_price": 99.0})
        self.assertEqual(product.with_user(self.portal_user)._get_sales_prices(website)[product.id]["price_reduce"], 0)
        self.profile.with_user(self.reviewer).action_mark_reviewed()
        self.profile.with_user(self.reviewer).action_approve()
        self.assertTrue(website._dreyes_can_purchase())

    def test_existing_user_migration_is_idempotent(self):
        second_partner = self.env["res.partner"].create({"name": "Legacy incomplete"})
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": second_partner.name, "login": "legacy-incomplete@example.com", "partner_id": second_partner.id,
            "company_id": self.company.id, "company_ids": [(6, 0, [self.company.id])],
            "groups_id": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        migrate_existing_profiles(self.env)
        migrate_existing_profiles(self.env)
        profiles = self.env["dreyes.distributor.profile"].search([
            ("partner_id", "=", second_partner.id), ("company_id", "=", self.company.id),
        ])
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles.state, "no_profile")


@tagged("post_install", "-at_install")
class TestDistributionPortal(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([("signup_form_type", "=", "extended")], limit=1)
        cls.website.domain = "http://distribution-test.invalid"
        cls.http_headers = {"Host": "distribution-test.invalid"}
        cls.login = "portal-http-dist-test@example.com"
        cls.password = "portal-http-dist-test"
        partner = cls.env["res.partner"].create({"name": "Portal HTTP Test", "email": cls.login})
        cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name, "login": cls.login, "password": cls.password, "partner_id": partner.id,
            "company_id": cls.website.company_id.id,
            "company_ids": [(6, 0, [cls.website.company_id.id])],
            "groups_id": [(6, 0, [cls.env.ref("base.group_portal").id])],
        })

    def test_profile_and_catalog_are_available_without_approval(self):
        self.authenticate(self.login, self.password)
        profile_response = self.url_open("/my/distributor-profile", headers=self.http_headers)
        self.assertEqual(profile_response.status_code, 200)
        self.assertIn("Guardar borrador", profile_response.text)
        self.assertIn("Sin perfil", profile_response.text)
        shop_response = self.url_open("/shop", headers=self.http_headers)
        self.assertEqual(shop_response.status_code, 200)
        self.assertIn("Precio disponible al aprobar la cuenta", shop_response.text)
        cart_response = self.url_open("/shop/cart", headers=self.http_headers, allow_redirects=False)
        self.assertEqual(cart_response.status_code, 303)
        self.assertEqual(cart_response.headers["Location"], "/my/distributor-profile")
