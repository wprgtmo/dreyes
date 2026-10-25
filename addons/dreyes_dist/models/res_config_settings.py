# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    signup_form_type = fields.Selection(related="website_id.signup_form_type", readonly=False)
