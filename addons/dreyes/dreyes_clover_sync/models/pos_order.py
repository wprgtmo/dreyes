from odoo import fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    clover_connector_id = fields.Many2one("clover.connector", copy=False, index=True)
    clover_order_id = fields.Char(copy=False, index=True)
    clover_sync_state = fields.Selection(
        [("pending", "Pendiente"), ("synced", "Sincronizado"), ("exception", "Excepción")], copy=False
    )
    clover_last_sync = fields.Datetime(copy=False)
    clover_error = fields.Text(copy=False)

    _sql_constraints = [
        ("clover_order_unique", "unique(clover_connector_id, clover_order_id)", "El pedido Clover ya fue importado."),
    ]
