from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        if self.env.context.get("clover_inbound") or not self.env.registry.ready:
            return moves
        connectors = self.env["clover.connector"].sudo().search([
            ("active", "=", True), ("state", "=", "connected"), ("initial_import_done", "=", True)
        ])
        for connector in connectors:
            relevant = moves.filtered(
                lambda move: (move.location_id.parent_path or "").startswith(connector.location_id.parent_path or "/")
                or (move.location_dest_id.parent_path or "").startswith(connector.location_id.parent_path or "/")
            ).mapped("product_id")
            if relevant:
                self.env["clover.sync.event"].sudo().enqueue(
                    connector, "out", "stock_push", "stock", str(connector.id),
                    payload={"product_ids": relevant.ids},
                    dedupe_key=f"stock:{connector.id}:{max(moves.ids)}",
                    priority=5,
                )
        return moves
