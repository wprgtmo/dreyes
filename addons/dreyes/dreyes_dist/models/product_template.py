# -*- coding: utf-8 -*-
from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _get_sales_prices(self, website):
        if website._dreyes_is_distribution_site() and not website._dreyes_can_purchase():
            return {template.id: {"price_reduce": 0, "base_price": 0} for template in self}
        return super()._get_sales_prices(website)

    def _get_combination_info(self, *args, **kwargs):
        values = super()._get_combination_info(*args, **kwargs)
        website = self.env["website"].get_current_website()
        if website._dreyes_is_distribution_site() and not website._dreyes_can_purchase():
            for key in ("price", "list_price", "compare_list_price", "price_extra", "base_unit_price"):
                if key in values:
                    values[key] = 0
            values["has_discounted_price"] = False
            values["prevent_zero_price_sale"] = True
            values.pop("product_tracking_info", None)
        return values

    def _is_add_to_cart_allowed(self):
        website = self.env["website"].get_current_website()
        if website._dreyes_is_distribution_site() and not website._dreyes_can_purchase():
            return False
        return super()._is_add_to_cart_allowed()


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _is_add_to_cart_allowed(self):
        website = self.env["website"].get_current_website()
        if website._dreyes_is_distribution_site() and not website._dreyes_can_purchase():
            return False
        return super()._is_add_to_cart_allowed()
