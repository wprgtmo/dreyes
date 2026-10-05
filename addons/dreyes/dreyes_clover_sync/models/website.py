from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    clover_connector_id = fields.Many2one("clover.connector", compute="_compute_clover_connector", string="Conexión Clover")

    def _compute_clover_connector(self):
        Connector = self.env["clover.connector"]
        for website in self:
            website.clover_connector_id = Connector.search([
                ("company_id", "=", website.company_id.id), ("active", "=", True), ("state", "!=", "paused")
            ], limit=1)
