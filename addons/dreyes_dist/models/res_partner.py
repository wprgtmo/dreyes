# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    first_name = fields.Char(string="First name")
    last_name = fields.Char(string="Last name")
    join_community = fields.Boolean(string="Join the community")
    tax_permit_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Texas Sales and Use Tax Permit",
        copy=False,
    )
