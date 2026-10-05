# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError
from odoo.http import request


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _dreyes_purchase_is_blocked(self):
        self.ensure_one()
        website = self.website_id
        if not website or not website._dreyes_is_distribution_site():
            return False
        profile = website._dreyes_profile_for_partner(self.partner_id, create=False)
        return not profile or not profile.can_purchase

    def _cart_update(self, *args, **kwargs):
        if request and self._dreyes_purchase_is_blocked():
            raise UserError(_("Su cuenta de distribución debe estar aprobada antes de agregar productos al carrito."))
        return super()._cart_update(*args, **kwargs)

    def _is_cart_ready(self):
        if self._dreyes_purchase_is_blocked():
            return False
        return super()._is_cart_ready()

    def _check_cart_is_ready_to_be_paid(self):
        if self._dreyes_purchase_is_blocked():
            raise UserError(_("Su cuenta de distribución no está habilitada para comprar."))
        return super()._check_cart_is_ready_to_be_paid()
