# -*- coding: utf-8 -*-
from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    signup_form_type = fields.Selection(
        selection=[
            ("basic", "Basico"),
            ("extended", "Extendido"),
        ],
        string="Formulario de registro",
        default="basic",
    )

    def _dreyes_is_distribution_site(self):
        self.ensure_one()
        return (self.signup_form_type or self.company_id.signup_form_type or "basic") == "extended"

    def _dreyes_profile_for_partner(self, partner, create=False):
        self.ensure_one()
        if not self._dreyes_is_distribution_site() or not partner:
            return self.env["dreyes.distributor.profile"]
        commercial_partner = partner.commercial_partner_id
        profile = self.env["dreyes.distributor.profile"].sudo().search([
            ("partner_id", "=", commercial_partner.id),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not profile and create:
            profile = self.env["dreyes.distributor.profile"].sudo().create({
                "partner_id": commercial_partner.id,
                "company_id": self.company_id.id,
                "website_id": self.id,
            })
        return profile

    def _dreyes_current_profile(self, create=False):
        self.ensure_one()
        if self.env.user._is_public():
            return self.env["dreyes.distributor.profile"]
        return self._dreyes_profile_for_partner(self.env.user.partner_id, create=create)

    def _dreyes_can_purchase(self):
        self.ensure_one()
        if not self._dreyes_is_distribution_site():
            return True
        profile = self._dreyes_current_profile(create=False)
        return bool(profile and profile.can_purchase)

    def _get_current_pricelist(self):
        self.ensure_one()
        profile = self._dreyes_current_profile(create=False) if self._dreyes_is_distribution_site() else False
        if profile and profile.can_purchase:
            return profile.segment_id.pricelist_id
        return super()._get_current_pricelist()

    def get_pricelist_available(self, show_visible=False):
        self.ensure_one()
        profile = self._dreyes_current_profile(create=False) if self._dreyes_is_distribution_site() else False
        if profile and profile.can_purchase:
            return profile.segment_id.pricelist_id
        return super().get_pricelist_available(show_visible=show_visible)
