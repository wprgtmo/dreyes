from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    clover_binding_ids = fields.One2many("clover.product.binding", "product_id", string="Conexiones Clover")

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        products._clover_enqueue_changes()
        return products

    def write(self, vals):
        result = super().write(vals)
        watched = {"name", "default_code", "barcode", "standard_price", "available_in_pos", "sale_ok", "active", "categ_id", "taxes_id", "image_1920"}
        if watched.intersection(vals):
            self._clover_enqueue_changes()
        return result

    def _clover_enqueue_changes(self):
        if self.env.context.get("clover_inbound") or not self.env.registry.ready:
            return
        connectors = self.env["clover.connector"].sudo().search([
            ("active", "=", True), ("state", "=", "connected"), ("initial_import_done", "=", True)
        ])
        Event = self.env["clover.sync.event"].sudo()
        Binding = self.env["clover.product.binding"].sudo()
        for product in self:
            for connector in connectors.filtered(lambda c: not product.company_id or c.company_id == product.company_id):
                binding = Binding.search([("connector_id", "=", connector.id), ("product_id", "=", product.id)], limit=1)
                if binding and binding.excluded:
                    continue
                Event.enqueue(
                    connector, "out", "item_push", "item", binding.clover_item_id if binding else str(product.id),
                    payload={"odoo_model": product._name, "odoo_res_id": product.id},
                    dedupe_key=f"product:{product.id}:{product.write_date}",
                )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def write(self, vals):
        result = super().write(vals)
        watched = {"name", "standard_price", "available_in_pos", "sale_ok", "active", "categ_id", "taxes_id", "image_1920"}
        if watched.intersection(vals):
            self.product_variant_ids._clover_enqueue_changes()
        return result


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._clover_enqueue_price_changes()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if {"fixed_price", "percent_price", "price_discount", "pricelist_id", "product_id", "product_tmpl_id"}.intersection(vals):
            self._clover_enqueue_price_changes()
        return result

    def _clover_enqueue_price_changes(self):
        if self.env.context.get("clover_inbound") or not self.env.registry.ready:
            return
        connectors = self.env["clover.connector"].sudo().search([
            ("pricelist_id", "in", self.mapped("pricelist_id").ids), ("state", "=", "connected"), ("active", "=", True)
        ])
        for connector in connectors:
            matching = self.filtered(lambda line: line.pricelist_id == connector.pricelist_id)
            products = matching.mapped("product_id") | matching.mapped("product_tmpl_id.product_variant_ids")
            for product in products:
                self.env["clover.sync.event"].sudo().enqueue(
                    connector, "out", "item_push", "item", str(product.id),
                    payload={"odoo_model": product._name, "odoo_res_id": product.id},
                    dedupe_key=f"price:{product.id}:{fields.Datetime.now()}",
                )
