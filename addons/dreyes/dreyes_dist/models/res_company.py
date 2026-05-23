# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    signup_form_type = fields.Selection(
        selection=[
            ("basic", "Basico"),
            ("extended", "Extendido"),
        ],
        string="Formulario de registro",
        default="basic",
        required=True,
    )
