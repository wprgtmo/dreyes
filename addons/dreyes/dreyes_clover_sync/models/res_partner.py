from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    clover_last_sync = fields.Datetime(compute="_compute_clover_last_sync")

    def _compute_clover_last_sync(self):
        Mapping = self.env["clover.object.map"]
        for partner in self:
            mapping = Mapping.search([
                ("object_type", "=", "customer"), ("odoo_model", "=", "res.partner"), ("odoo_res_id", "=", partner.id)
            ], order="last_sync desc", limit=1)
            partner.clover_last_sync = mapping.last_sync
