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
