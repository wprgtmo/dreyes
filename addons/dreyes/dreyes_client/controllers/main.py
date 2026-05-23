# -*- coding: utf-8 -*-
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request


class DreyesClientPortal(CustomerPortal):
    def _format_currency(self, currency, amount):
        amount_text = f"{amount:,.2f}"
        if currency.position == "after":
            return f"{amount_text} {currency.symbol}"
        return f"{currency.symbol}{amount_text}"

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.sudo().partner_id.commercial_partner_id
        sale_order_model = request.env["sale.order"].sudo()
        invoice_model = request.env["account.move"].sudo()

        sale_domain = [
            ("partner_id", "child_of", partner.id),
            ("state", "!=", "cancel"),
        ]
        invoice_domain = [
            ("partner_id", "child_of", partner.id),
            ("move_type", "in", ["out_invoice", "out_refund"]),
            ("state", "!=", "cancel"),
        ]

        recent_orders = sale_order_model.search(sale_domain, limit=3, order="date_order desc, id desc")
        recent_invoices = invoice_model.search(invoice_domain, limit=3, order="invoice_date desc, id desc")
        company_currency = request.website.company_id.currency_id

        values.update({
            "dreyes_client_partner": partner,
            "dreyes_client_recent_orders": recent_orders,
            "dreyes_client_recent_invoices": recent_invoices,
            "dreyes_client_total_sales_text": self._format_currency(company_currency, sum(recent_orders.mapped("amount_total"))),
            "dreyes_client_total_due_text": self._format_currency(company_currency, sum(recent_invoices.mapped("amount_residual"))),
        })
        return values
