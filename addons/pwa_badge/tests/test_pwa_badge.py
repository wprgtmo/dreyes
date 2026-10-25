# -*- coding: utf-8 -*-

import base64
import io

from PIL import Image

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.base.tests.common import HttpCaseWithUserDemo


@tagged("post_install", "-at_install")
class TestPwaBadgeCounts(TransactionCase):
    def setUp(self):
        super().setUp()
        self.user = new_test_user(self.env, login="pwa_badge_counts_test", groups="base.group_user")
        self.env["mail.activity"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.user.partner_id.id,
                "user_id": self.user.id,
                "summary": "Pending activity",
            }
        )

    def test_counts_both_mode(self):
        self.env["ir.config_parameter"].sudo().set_param("pwa_badge.count_mode", "both")
        counts = self.user._get_pwa_badge_counts()
        self.assertEqual(counts["activities_count"], 1)
        self.assertGreaterEqual(counts["mail_count"], 0)
        self.assertEqual(
            counts["total_count"], counts["activities_count"] + counts["mail_count"]
        )

    def test_counts_activities_mode(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "pwa_badge.count_mode", "activities"
        )
        counts = self.user._get_pwa_badge_counts()
        self.assertEqual(counts["total_count"], counts["activities_count"])

    def test_counts_mail_mode(self):
        self.env["ir.config_parameter"].sudo().set_param("pwa_badge.count_mode", "mail")
        counts = self.user._get_pwa_badge_counts()
        self.assertEqual(counts["total_count"], counts["mail_count"])


@tagged("-at_install", "post_install")
class TestPwaBadgeHttp(HttpCaseWithUserDemo):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        image = Image.new("RGBA", (512, 512), color=(10, 20, 30, 255))
        output = io.BytesIO()
        image.save(output, format="PNG")
        cls.env["ir.attachment"].sudo().create(
            {
                "name": "/web_pwa_customize/icon.png",
                "url": "/web_pwa_customize/icon.png",
                "type": "binary",
                "mimetype": "image/png",
                "datas": base64.b64encode(output.getvalue()),
                "db_datas": base64.b64encode(output.getvalue()),
            }
        )
        cls.env["res.config.settings"].create({}).set_values()

    def test_webmanifest_contains_manifest_id(self):
        response = self.url_open("/web/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("/web?db=", data["id"])

    def test_web_layout_contains_apple_touch_icon(self):
        response = self.url_open("/web/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn("apple-touch-icon", response.text)
        self.assertIn("apple-mobile-web-app-title", response.text)

    def test_count_endpoint_requires_login(self):
        response = self.url_open("/pwa_badge/count", allow_redirects=False)
        self.assertIn(response.status_code, {302, 303})

    def test_count_endpoint_returns_json_for_authenticated_user(self):
        self.authenticate("demo", "demo")
        response = self.url_open("/pwa_badge/count")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("activities_count", data)
        self.assertIn("mail_count", data)
        self.assertIn("total_count", data)


@tagged("post_install", "-at_install")
class TestPwaBadgeAppleIconValidation(TransactionCase):
    def test_svg_icon_is_rejected_for_apple_touch_icon(self):
        svg_data = base64.b64encode(
            b'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"></svg>'
        )
        self.env["ir.attachment"].sudo().create(
            {
                "name": "/web_pwa_customize/icon.svg",
                "url": "/web_pwa_customize/icon.svg",
                "type": "binary",
                "mimetype": "image/svg+xml",
                "datas": svg_data,
                "db_datas": svg_data,
            }
        )
        with self.assertRaisesRegex(Exception, "apple-touch-icon"):
            self.env["res.config.settings"].create({}).set_values()
