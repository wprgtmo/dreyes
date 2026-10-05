from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCloverSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Clover Test", "currency_id": cls.company.currency_id.id, "company_id": cls.company.id
        })
        cls.pos_config = cls.env["pos.config"].create({
            "name": "Clover Test POS",
            "company_id": cls.company.id,
            "warehouse_id": cls.warehouse.id,
            "picking_type_id": cls.warehouse.pos_type_id.id,
            "pricelist_id": cls.pricelist.id,
        })
        with patch.dict("os.environ", {"CLOVER_TOKEN_ENCRYPTION_KEY": "unit-test-secret"}):
            cls.connector = cls.env["clover.connector"].create({
                "name": "Clover Sandbox",
                "company_id": cls.company.id,
                "app_id": "APP-TEST",
                "app_secret": "secret-value",
                "webhook_auth_code": "webhook-value",
                "merchant_id": "MERCHANT-TEST",
                "public_base_url": "https://odoo.example.test",
                "warehouse_id": cls.warehouse.id,
                "location_id": cls.warehouse.lot_stock_id.id,
                "pricelist_id": cls.pricelist.id,
                "pos_config_id": cls.pos_config.id,
            })

    def test_credentials_are_encrypted(self):
        self.assertFalse(self.connector.app_secret)
        self.assertNotIn("secret-value", self.connector.app_secret_encrypted)
        with patch.dict("os.environ", {"CLOVER_TOKEN_ENCRYPTION_KEY": "unit-test-secret"}):
            self.assertEqual(self.connector._app_secret(), "secret-value")
            self.assertEqual(self.connector._webhook_auth_code(), "webhook-value")

    def test_only_one_active_connector_per_company(self):
        with self.assertRaises(ValidationError), patch.dict("os.environ", {"CLOVER_TOKEN_ENCRYPTION_KEY": "unit-test-secret"}):
            self.env["clover.connector"].create({
                "name": "Duplicate",
                "company_id": self.company.id,
                "app_id": "APP-OTHER",
                "app_secret": "another-secret",
                "public_base_url": "https://other.example.test",
                "warehouse_id": self.warehouse.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "pricelist_id": self.pricelist.id,
                "pos_config_id": self.pos_config.id,
            })

    def test_event_is_idempotent_and_retries(self):
        Event = self.env["clover.sync.event"]
        first = Event.enqueue(
            self.connector, "in", "unsupported_test", "item", "ITEM-1", {"x": 1}, dedupe_key="same-event"
        )
        second = Event.enqueue(
            self.connector, "in", "unsupported_test", "item", "ITEM-1", {"x": 1}, dedupe_key="same-event"
        )
        self.assertEqual(first, second)
        first._process_safely()
        self.assertEqual(first.state, "retry")
        self.assertEqual(first.attempts, 1)
        self.assertTrue(first.next_retry)

    def test_product_match_uses_sku_not_name(self):
        first = self.env["product.product"].with_context(clover_inbound=True).create({
            "name": "Same name", "default_code": "SKU-A", "company_id": self.company.id
        })
        second = self.env["product.product"].with_context(clover_inbound=True).create({
            "name": "Same name", "default_code": "SKU-B", "company_id": self.company.id
        })
        event = self.env["clover.sync.event"].create({
            "connector_id": self.connector.id,
            "direction": "in",
            "event_type": "item_changed",
            "object_type": "item",
            "object_id": "CLOVER-ITEM",
            "dedupe_key": "product-match",
        })
        self.assertEqual(event._find_product_for_item({"id": "CLOVER-ITEM", "name": "Same name", "sku": "SKU-B"}), second)
        self.assertFalse(event._find_product_for_item({"id": "OTHER", "name": "Same name"}))
        self.assertNotEqual(first, second)

    def test_stock_change_creates_auditable_move(self):
        product = self.env["product.product"].with_context(clover_inbound=True).create({
            "name": "Stock item", "default_code": "STOCK-1", "is_storable": True, "company_id": self.company.id
        })
        event = self.env["clover.sync.event"].create({
            "connector_id": self.connector.id,
            "direction": "in",
            "event_type": "stock_changed",
            "object_type": "stock",
            "object_id": "CLOVER-STOCK",
            "dedupe_key": "stock-adjustment",
        })
        event._apply_stock_difference(product, 4.0)
        moves = self.env["stock.move"].search([("origin", "=", "Clover:CLOVER-STOCK"), ("product_id", "=", product.id)])
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves.state, "done")
        locations = self.env["stock.location"].search([("id", "child_of", self.connector.location_id.id)])
        quantity = sum(self.env["stock.quant"].search([
            ("product_id", "=", product.id), ("location_id", "in", locations.ids)
        ]).mapped("quantity"))
        self.assertEqual(quantity, 4.0)

    def test_clover_options_select_the_correct_variant(self):
        attribute = self.env["product.attribute"].create({"name": "Size", "create_variant": "always"})
        small = self.env["product.attribute.value"].create({"name": "Small", "attribute_id": attribute.id})
        large = self.env["product.attribute.value"].create({"name": "Large", "attribute_id": attribute.id})
        template = self.env["product.template"].with_context(clover_inbound=True).create({
            "name": "Variant product",
            "company_id": self.company.id,
            "attribute_line_ids": [(0, 0, {"attribute_id": attribute.id, "value_ids": [(6, 0, [small.id, large.id])]})],
        })
        self.env["clover.object.map"].bind(self.connector, "option", "OPT-S", small)
        self.env["clover.object.map"].bind(self.connector, "option", "OPT-L", large)
        event = self.env["clover.sync.event"].create({
            "connector_id": self.connector.id, "direction": "in", "event_type": "item_changed",
            "object_type": "item", "object_id": "VARIANT-L", "dedupe_key": "variant-test",
        })
        variant = event._variant_for_item(template, {"options": {"elements": [{"id": "OPT-L"}]}})
        self.assertEqual(variant.product_template_attribute_value_ids.product_attribute_value_id, large)

    def test_clover_price_becomes_conflict_after_cutover(self):
        product = self.env["product.product"].with_context(clover_inbound=True).create({
            "name": "Authoritative Odoo product", "default_code": "AUTH-1", "company_id": self.company.id,
        })
        self.env["product.pricelist.item"].with_context(clover_inbound=True).create({
            "pricelist_id": self.pricelist.id, "product_id": product.id,
            "applied_on": "0_product_variant", "compute_price": "fixed", "fixed_price": 10.0,
        })
        event = self.env["clover.sync.event"].create({
            "connector_id": self.connector.id, "direction": "in", "event_type": "item_changed",
            "object_type": "item", "object_id": "AUTH-CLOVER", "dedupe_key": "authority-test",
        })
        item = {"id": "AUTH-CLOVER", "name": product.name, "sku": "AUTH-1", "price": 500, "cost": 0, "available": True}
        with patch.object(type(event), "_pull_item_stock", return_value=None):
            event._import_item(item, initial=False)
        self.assertEqual(event._product_price(product), 10.0)
        conflict = self.env["clover.sync.conflict"].search([
            ("connector_id", "=", self.connector.id), ("clover_id", "=", "AUTH-CLOVER"),
            ("field_name", "=", "__clover_price__"), ("state", "=", "open"),
        ])
        self.assertEqual(len(conflict), 1)
        conflict.action_accept_clover()
        self.assertEqual(event._product_price(product), 5.0)
