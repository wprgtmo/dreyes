# -*- coding: utf-8 -*-
import base64
import json
import io
from types import SimpleNamespace
from unittest.mock import patch

from lxml import html
from PIL import Image
from werkzeug.datastructures import FileStorage

from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..controllers.main import DreyesDistProfile
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
            "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
        })
        cls.reviewer = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Distribution Reviewer", "login": "reviewer-dist-test@example.com",
            "email": "reviewer@example.com", "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
            "group_ids": [(6, 0, [cls.env.ref("dreyes_dist.group_distribution_reviewer").id])],
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

    def _save_portal_address(self, logo=None, profile_state="no_profile", **post):
        controller = DreyesDistProfile()
        self.profile.state = profile_state
        mock_request = SimpleNamespace(
            env=self.env, httprequest=SimpleNamespace(files={"company_logo": logo} if logo else {}),
        )
        with (
            patch("odoo.http.request", mock_request),
            patch("odoo.addons.dreyes_dist.controllers.main.request", mock_request),
            patch.object(controller, "_read_upload", return_value=False),
        ):
            controller._save(self.profile, post)

    def test_portal_uploads_and_keeps_company_logo(self):
        image = io.BytesIO()
        Image.new("RGB", (16, 16), "red").save(image, format="PNG")
        image.seek(0)
        logo = FileStorage(stream=image, filename="company.png", content_type="image/png")
        self._save_portal_address(logo=logo, phone="5125550100")
        saved_logo = self.profile.company_logo
        self.assertTrue(saved_logo)
        with Image.open(io.BytesIO(base64.b64decode(saved_logo))) as saved:
            self.assertEqual(saved.size, (16, 16))
        self.assertEqual(self.partner.phone, "5125550100")
        self._save_portal_address()
        self.assertEqual(self.profile.company_logo, saved_logo)

    def test_portal_rejects_invalid_company_logo_before_saving(self):
        logo = FileStorage(stream=io.BytesIO(b"not an image"), filename="company.png")
        original_street = self.partner.street
        with self.assertRaisesRegex(UserError, "imagen válida"):
            self._save_portal_address(logo=logo, street="Must not be saved")
        self.assertEqual(self.partner.street, original_street)
        self.assertFalse(self.profile.company_logo)

    def test_saving_profile_under_review_queues_reviewer_notification(self):
        previous = self.env["mail.mail"].search([])
        self._save_portal_address(profile_state="under_review", street="Updated address")
        notification = self.env["mail.mail"].search([]) - previous
        self.assertTrue(notification)
        self.assertIn(self.reviewer.email, ",".join(notification.mapped("email_to")))
        self.assertEqual(self.partner.street, "Updated address")

    def test_reviewer_notifications_include_inherited_group_members(self):
        group = self.env["res.groups"].create({
            "name": "Inherited Distribution Reviewers",
            "implied_ids": [(4, self.env.ref("dreyes_dist.group_distribution_reviewer").id)],
        })
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Inherited reviewer", "login": "inherited-reviewer@example.com",
            "email": "inherited-reviewer@example.com", "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])], "group_ids": [(6, 0, group.ids)],
        })
        self.assertIn(user.email, self.profile._reviewer_emails())
        user.active = False
        self.assertNotIn(user.email, self.profile._reviewer_emails())

    def test_portal_country_is_always_usa(self):
        self._save_portal_address(
            country_id=str(self.env.ref("base.mx").id),
            state_id=str(self.env.ref("base.state_us_43").id),
        )
        self.assertEqual(self.partner.country_id, self.env.ref("base.us"))
        self.assertEqual(self.partner.state_id, self.env.ref("base.state_us_43"))

    def test_portal_rejects_non_usa_state_before_saving(self):
        state = self.env["res.country.state"].search([("country_id.code", "=", "MX")], limit=1)
        self.assertTrue(state)
        original_street = self.partner.street
        with self.assertRaisesRegex(UserError, "estado de USA"):
            self._save_portal_address(state_id=str(state.id), street="Must not be saved")
        self.assertEqual(self.partner.street, original_street)

    def test_portal_blank_state_still_saves_usa(self):
        self._save_portal_address(state_id="")
        self.assertEqual(self.partner.country_id, self.env.ref("base.us"))
        self.assertFalse(self.partner.state_id)

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
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        migrate_existing_profiles(self.env)
        migrate_existing_profiles(self.env)
        profiles = self.env["dreyes.distributor.profile"].search([
            ("partner_id", "=", second_partner.id), ("company_id", "=", self.company.id),
        ])
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles.state, "no_profile")

    def test_unapproved_cart_add_and_quantity_updates_are_blocked(self):
        order = self.env["sale.order"].with_company(self.company).create({
            "partner_id": self.partner.id, "company_id": self.company.id,
            "website_id": self.website.id, "pricelist_id": self.pricelist.id,
        })
        product = self.env["product.product"].create({"name": "Blocked cart product"})
        with self.assertRaises(UserError):
            order._cart_add(product.id)
        with self.assertRaises(UserError):
            order._cart_update_line_quantity(0, 2)
        self.assertFalse(order.order_line)

    def test_approval_reprices_existing_draft_cart(self):
        product = self.env["product.product"].create({"name": "Repriced product", "list_price": 100.0})
        self.env["product.pricelist.item"].create({
            "pricelist_id": self.pricelist.id, "product_id": product.id,
            "applied_on": "0_product_variant", "compute_price": "fixed", "fixed_price": 75.0,
        })
        order = self.env["sale.order"].with_company(self.company).create({
            "partner_id": self.partner.id, "company_id": self.company.id, "website_id": self.website.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1, "price_unit": 100.0})],
        })
        self.profile.with_user(self.reviewer).action_mark_reviewed()
        self.profile.with_user(self.reviewer).action_approve()
        self.assertEqual(order.pricelist_id, self.pricelist)
        self.assertEqual(order.order_line.price_unit, 75.0)


@tagged("post_install", "-at_install")
class TestDistributionPortal(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].create({
            "name": "Distribution HTTP Test", "domain": cls.base_url(),
            "company_id": cls.env.company.id, "signup_form_type": "extended",
        })
        cls.product = cls.env["product.template"].create({
            "name": "Distribution HTTP Product", "list_price": 99.0, "is_published": True,
            "website_id": cls.website.id,
        })
        cls.http_headers = {}
        cls.login = "portal-http-dist-test@example.com"
        cls.password = "portal-http-dist-test"
        partner = cls.env["res.partner"].create({"name": "Portal HTTP Test", "email": cls.login, "zip": "78701"})
        cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name, "login": cls.login, "password": cls.password, "partner_id": partner.id,
            "company_id": cls.website.company_id.id,
            "company_ids": [(6, 0, [cls.website.company_id.id])],
            "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
        })

    def test_cart_json_routes_reject_unapproved_account(self):
        self.authenticate(self.login, self.password)
        requests = [
            ("/shop/cart/add", {"product_template_id": self.product.id,
                                "product_id": self.product.product_variant_id.id, "quantity": 1}),
            ("/shop/cart/update", {"line_id": 0, "quantity": 2}),
        ]
        for route, params in requests:
            response = self.url_open(route, data=json.dumps({
                "jsonrpc": "2.0", "method": "call", "params": params, "id": 1,
            }), headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("Su cuenta debe estar aprobada", response.json()["error"]["data"]["message"])
        self.assertFalse(self.env["sale.order"].search_count([("website_id", "=", self.website.id)]))

    def test_profile_and_catalog_are_available_without_approval(self):
        self.authenticate(self.login, self.password)
        profile_response = self.url_open("/my/distributor-profile", headers=self.http_headers)
        self.assertEqual(profile_response.status_code, 200)
        self.assertIn("Guardar borrador", profile_response.text)
        document = html.fromstring(profile_response.content)
        self.assertEqual(document.xpath("//input[@name='zip']/@value"), ["78701"])
        self.assertFalse(document.xpath("//select[@name='phone_code']"))
        self.assertIn("Sin perfil", profile_response.text)
        shop_response = self.url_open("/shop", headers=self.http_headers)
        self.assertEqual(shop_response.status_code, 200)
        self.assertIn("Precio disponible al aprobar la cuenta", shop_response.text)
        cart_response = self.url_open("/shop/cart", headers=self.http_headers, allow_redirects=False)
        self.assertEqual(cart_response.status_code, 303)
        self.assertEqual(cart_response.headers["Location"], "/my/distributor-profile")
