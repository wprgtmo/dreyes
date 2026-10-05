from datetime import timedelta
from unittest.mock import patch

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestProductPricing(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Pricelist = cls.env["product.pricelist"]
        cls.Item = cls.env["product.pricelist.item"]
        cls.today = fields.Date.context_today(cls.Pricelist)
        cls.category = cls.env["product.category"].create({"name": "Pricing test category"})
        cls.template = cls.env["product.template"].create({
            "name": "Pricing test product", "default_code": "PRICING-TEST",
            "list_price": 100.0, "sale_ok": True, "categ_id": cls.category.id,
            "company_id": cls.env.company.id,
        })
        cls.product = cls.template.product_variant_id
        cls.pricelist = cls.Pricelist.create({
            "name": "Pricing test list", "currency_id": cls.env.company.currency_id.id,
            "company_id": cls.env.company.id,
        })
        user_env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.reader = new_test_user(
            user_env, login="dreyes_pricing_reader", groups="base.group_user",
            company_id=cls.env.company.id,
        )
        cls.manager = new_test_user(
            user_env, login="dreyes_pricing_manager",
            groups="base.group_user,product.group_product_manager",
            company_id=cls.env.company.id,
        )

    def page(self, **kwargs):
        return self.Pricelist.dreyes_get_price_page(
            "product.pricelist", self.pricelist.id, search="PRICING-TEST", **kwargs
        )

    def rule(self, **kwargs):
        values = {
            "pricelist_id": self.pricelist.id, "product_id": self.product.id,
            "applied_on": "0_product_variant", "compute_price": "fixed",
            "fixed_price": 80.0, "min_quantity": 1.0,
        }
        values.update(kwargs)
        return self.Item.create(values)

    def test_fallback_read_only_and_consistency(self):
        before = self.Item.search_count([])
        result = self.page()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["date"], fields.Date.to_string(self.today))
        row = result["rows"][0]
        self.assertEqual(row["price"], 100.0)
        self.assertFalse(row["rule_id"])
        self.assertIn("base", row["rule_name"])
        template_rows = self.template.dreyes_get_price_page()["rows"]
        template_row = next(r for r in template_rows if r["pricelist_id"] == self.pricelist.id)
        self.assertEqual(template_row, row)
        variant_rows = self.product.dreyes_get_price_page()["rows"]
        self.assertEqual(next(r for r in variant_rows if r["pricelist_id"] == self.pricelist.id), row)
        self.assertEqual(self.Item.search_count([]), before)

    def test_standard_price_engine_category_percentage_formula_and_derived(self):
        rule = self.rule(
            applied_on="2_product_category", product_id=False, categ_id=self.category.id,
            compute_price="percentage", percent_price=10.0,
        )
        self.assertEqual(self.page()["rows"][0]["price"], 90.0)
        rule.write({"compute_price": "formula", "price_discount": 20.0, "price_surcharge": 3.0})
        self.assertEqual(self.page()["rows"][0]["price"], 83.0)
        derived = self.Pricelist.create({
            "name": "Pricing derived list", "currency_id": self.pricelist.currency_id.id,
            "company_id": self.env.company.id,
        })
        self.Item.create({
            "pricelist_id": derived.id, "applied_on": "3_global", "compute_price": "formula",
            "base": "pricelist", "base_pricelist_id": self.pricelist.id, "price_discount": 10.0,
        })
        row = self.Pricelist.dreyes_get_price_page(
            "product.pricelist", derived.id, search="PRICING-TEST"
        )["rows"][0]
        self.assertEqual(row["price"], derived.currency_id.round(74.7))
        self.assertTrue(row["rule_id"])

    def test_quantity_and_validity(self):
        ordinary = self.rule(fixed_price=80.0)
        volume = self.rule(fixed_price=65.0, min_quantity=10.0)
        start = self.today + timedelta(days=5)
        end = self.today + timedelta(days=10)
        temporary = self.rule(fixed_price=50.0, date_start=start, date_end=end)
        self.assertEqual(self.page()["rows"][0]["rule_id"], ordinary.id)
        self.assertEqual(self.page(quantity=10)["rows"][0]["rule_id"], volume.id)
        self.assertEqual(self.page(date=fields.Date.to_string(start))["rows"][0]["rule_id"], temporary.id)
        self.assertEqual(self.page(date=fields.Date.to_string(end + timedelta(days=1)))["rows"][0]["rule_id"], ordinary.id)

    def test_create_update_zero_and_rounding(self):
        service = self.Pricelist.with_user(self.manager)
        first = service.dreyes_save_fixed_price(self.pricelist.id, self.product.id, 12.345)
        rule = self.Item.browse(first["fixed_rule_id"])
        self.assertEqual(rule.fixed_price, self.pricelist.currency_id.round(12.345))
        self.assertEqual(rule.applied_on, "0_product_variant")
        self.assertEqual(rule.min_quantity, 1.0)
        self.assertFalse(rule.date_start)
        self.assertFalse(rule.date_end)
        second = service.dreyes_save_fixed_price(self.pricelist.id, self.product.id, 0)
        self.assertEqual(first["fixed_rule_id"], second["fixed_rule_id"])
        self.assertEqual(second["row"]["price"], 0)
        self.assertFalse(second["overridden"])

    def test_preserve_general_volume_and_temporary_rules(self):
        general = self.rule(applied_on="3_global", product_id=False, fixed_price=90.0)
        volume = self.rule(min_quantity=10.0, fixed_price=50.0)
        temporary = self.rule(
            date_start=self.today - timedelta(days=1), date_end=self.today + timedelta(days=1),
            fixed_price=60.0,
        )
        before = (general.fixed_price, volume.fixed_price, temporary.fixed_price)
        result = self.Pricelist.dreyes_save_fixed_price(
            self.pricelist.id, self.product.id, 70.0, quantity=10, date=self.today
        )
        self.assertTrue(result["overridden"])
        self.assertEqual(result["row"]["rule_id"], volume.id)
        self.assertEqual((general.fixed_price, volume.fixed_price, temporary.fixed_price), before)
        self.assertNotIn(result["fixed_rule_id"], (general | volume | temporary).ids)

    def test_duplicates_open_rules_without_writing(self):
        rules = self.rule(fixed_price=80) | self.rule(fixed_price=85)
        before = self.Item.search_count([])
        result = self.Pricelist.dreyes_save_fixed_price(self.pricelist.id, self.product.id, 30)
        self.assertEqual(result["status"], "duplicates")
        self.assertEqual(result["action"]["res_model"], "product.pricelist.item")
        self.assertEqual(self.Item.search(result["action"]["domain"]), rules.sorted(key=lambda r: -r.id))
        self.assertEqual(self.Item.search_count([]), before)
        self.assertEqual(rules.mapped("fixed_price"), [80, 85])

    def test_read_permissions_and_write_denial(self):
        service = self.Pricelist.with_user(self.reader)
        page = service.dreyes_get_price_page("product.pricelist", self.pricelist.id, search="PRICING-TEST")
        self.assertFalse(page["rows"][0]["can_edit"])
        with self.assertRaises(AccessError):
            service.dreyes_save_fixed_price(self.pricelist.id, self.product.id, 1)
        with self.assertRaises(AccessError):
            self.Pricelist.with_user(self.env.ref("base.public_user")).dreyes_get_price_page(
                "product.pricelist", self.pricelist.id
            )

    def test_record_rules_checked_for_reads_and_writes(self):
        security_rule = self.env["ir.rule"].create({
            "name": "Pricing test denied list", "model_id": self.env["ir.model"]._get_id("product.pricelist"),
            "domain_force": "[('id', '!=', %s)]" % self.pricelist.id,
            "perm_read": True, "perm_write": True, "perm_create": False, "perm_unlink": False,
        })
        with self.assertRaises(AccessError):
            self.Pricelist.with_user(self.manager).dreyes_get_price_page("product.pricelist", self.pricelist.id)
        with self.assertRaises(AccessError):
            self.Pricelist.with_user(self.manager).dreyes_save_fixed_price(self.pricelist.id, self.product.id, 1)
        security_rule.unlink()

    def test_company_isolation_active_lists_and_products(self):
        other_company = self.env["res.company"].create({"name": "Pricing test other company"})
        other_list = self.Pricelist.create({
            "name": "Pricing other list", "company_id": other_company.id,
            "currency_id": self.pricelist.currency_id.id,
        })
        shared_list = self.Pricelist.create({
            "name": "Pricing shared list", "company_id": False,
            "currency_id": self.pricelist.currency_id.id,
        })
        archived_list = self.Pricelist.create({
            "name": "Pricing archived list", "active": False,
            "currency_id": self.pricelist.currency_id.id,
        })
        rows = self.template.dreyes_get_price_page()["rows"]
        ids = {row["pricelist_id"] for row in rows}
        self.assertIn(shared_list.id, ids)
        self.assertNotIn(other_list.id, ids)
        self.assertNotIn(archived_list.id, ids)
        with self.assertRaises(UserError):
            self.Pricelist.dreyes_get_price_page("product.pricelist", other_list.id)
        with self.assertRaises(UserError):
            self.Pricelist.dreyes_save_fixed_price(archived_list.id, self.product.id, 1)
        other_product = self.env["product.product"].create({
            "name": "Other pricing product", "company_id": other_company.id, "default_code": "PRICING-TEST-OTHER",
        })
        with self.assertRaises(UserError):
            self.Pricelist.dreyes_save_fixed_price(self.pricelist.id, other_product.id, 1)
        self.assertEqual(self.page()["total"], 1)
        self.product.active = False
        self.assertEqual(self.page()["total"], 0)

    def test_pagination_only_calculates_current_page(self):
        self.env["product.product"].create([
            {"name": "Pricing bulk %03d" % n, "default_code": "PRICING-TEST-%03d" % n, "sale_ok": True}
            for n in range(85)
        ])
        cls = type(self.pricelist)
        original = cls._compute_price_rule
        batches = []

        def compute(record, products, *args, **kwargs):
            batches.append(len(products))
            return original(record, products, *args, **kwargs)

        with patch.object(cls, "_compute_price_rule", compute):
            first = self.page(limit=10000)
            second = self.page(offset=80)
        self.assertEqual(first["total"], 86)
        self.assertEqual(len(first["rows"]), 80)
        self.assertEqual(len(second["rows"]), 6)
        self.assertEqual(batches, [80, 6])
        self.assertFalse({r["key"] for r in first["rows"]} & {r["key"] for r in second["rows"]})
        self.assertEqual(self.page(offset=10000)["offset"], 80)

    def test_variant_rows_extra_prices_and_search(self):
        attribute = self.env["product.attribute"].create({"name": "Pricing size"})
        values = self.env["product.attribute.value"].create([
            {"name": "Small", "attribute_id": attribute.id},
            {"name": "Large", "attribute_id": attribute.id},
        ])
        template = self.env["product.template"].create({
            "name": "Pricing variants", "list_price": 100.0,
            "attribute_line_ids": [Command.create({"attribute_id": attribute.id, "value_ids": [Command.set(values.ids)]})],
        })
        large_value = template.attribute_line_ids.product_template_value_ids.filtered(
            lambda value: value.product_attribute_value_id == values[1]
        )
        large_value.price_extra = 15.0
        rows = template.dreyes_get_price_page(search=self.pricelist.name)["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(row["price"] for row in rows), [100.0, 115.0])
        large = template.product_variant_ids.filtered(
            lambda variant: large_value in variant.product_template_attribute_value_ids
        )
        self.Pricelist.dreyes_save_fixed_price(self.pricelist.id, large.id, 75.0)
        rows = template.dreyes_get_price_page(search=self.pricelist.name)["rows"]
        self.assertEqual(sorted(row["price"] for row in rows), [75.0, 100.0])
        variant_rows = large.dreyes_get_price_page(search=self.pricelist.name)["rows"]
        self.assertEqual(len(variant_rows), 1)
        self.assertEqual(variant_rows[0]["price"], 75.0)
        matching = template.dreyes_get_price_page(search="Large")["rows"]
        self.assertTrue(matching)
        self.assertTrue(all(row["product_id"] == large.id for row in matching))

    def test_currency_conversion(self):
        currency = self.env["res.currency"].create({
            "name": "XDP", "symbol": "XDP", "rounding": 0.01,
            "rate_ids": [Command.create({"name": self.today, "rate": 2.0, "company_id": self.env.company.id})],
        })
        self.pricelist.currency_id = currency
        expected = self.product.currency_id._convert(100.0, currency, self.env.company, self.today)
        self.assertEqual(self.page()["rows"][0]["price"], expected)

    def test_invalid_inputs(self):
        for quantity in (0, -1, float("nan"), float("inf"), "", True):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.page(quantity=quantity)
        for price in (-1, float("nan"), float("inf"), "", True):
            with self.subTest(price=price), self.assertRaises(ValidationError):
                self.Pricelist.dreyes_save_fixed_price(self.pricelist.id, self.product.id, price)
        with self.assertRaises(ValidationError):
            self.page(date="not-a-date")
        with self.assertRaises(ValidationError):
            self.page(offset=-1)
        with self.assertRaises(ValidationError):
            self.Pricelist.dreyes_get_price_page("res.partner", self.env.user.partner_id.id)

    def test_clover_price_hooks_preserved_when_available(self):
        cls = type(self.Item)
        if not hasattr(cls, "_clover_enqueue_price_changes"):
            self.skipTest("Clover Sync is not installed")
        with patch.object(cls, "_clover_enqueue_price_changes", autospec=True) as enqueue:
            self.page()
            enqueue.assert_not_called()
            self.Pricelist.dreyes_save_fixed_price(self.pricelist.id, self.product.id, 55)
            self.assertEqual(enqueue.call_count, 1)
            self.Pricelist.dreyes_save_fixed_price(self.pricelist.id, self.product.id, 60)
            self.assertEqual(enqueue.call_count, 2)

    def test_views_and_catalog_action(self):
        for model in ("product.template", "product.product"):
            arch = etree.fromstring(self.env[model].get_view(view_type="form")["arch"])
            self.assertEqual(len(arch.xpath("//page[@name='dreyes_product_pricing']")), 1)
            self.assertEqual(len(arch.xpath("//widget[@name='dreyes_product_pricing_table']")), 1)
        arch = etree.fromstring(self.pricelist.get_view(view_type="form")["arch"])
        self.assertTrue(arch.xpath("//button[@name='action_dreyes_pricing_products']"))
        action = self.pricelist.action_dreyes_pricing_products()
        self.assertEqual(action["tag"], "dreyes_product_pricing.catalog")
        self.assertEqual(action["params"]["source_id"], self.pricelist.id)
