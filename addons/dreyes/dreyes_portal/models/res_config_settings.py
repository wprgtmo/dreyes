# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    signup_form_type = fields.Selection(related="website_id.signup_form_type", readonly=False)
    dreyes_auth_logo = fields.Image(related="website_id.dreyes_auth_logo", readonly=False)
    dreyes_auth_panel_start = fields.Char(related="website_id.dreyes_auth_panel_start", readonly=False)
    dreyes_auth_panel_end = fields.Char(related="website_id.dreyes_auth_panel_end", readonly=False)
    dreyes_auth_accent = fields.Char(related="website_id.dreyes_auth_accent", readonly=False)
    dreyes_auth_background = fields.Char(related="website_id.dreyes_auth_background", readonly=False)
    dreyes_auth_welcome = fields.Char(related="website_id.dreyes_auth_welcome", readonly=False)
    dreyes_auth_tagline = fields.Char(related="website_id.dreyes_auth_tagline", readonly=False)
    dreyes_auth_footer_left = fields.Char(related="website_id.dreyes_auth_footer_left", readonly=False)
    dreyes_auth_footer_right = fields.Char(related="website_id.dreyes_auth_footer_right", readonly=False)
    dreyes_auth_login_title = fields.Char(related="website_id.dreyes_auth_login_title", readonly=False)
    dreyes_auth_login_subtitle = fields.Char(related="website_id.dreyes_auth_login_subtitle", readonly=False)
    dreyes_auth_signup_title = fields.Char(related="website_id.dreyes_auth_signup_title", readonly=False)
    dreyes_auth_signup_subtitle = fields.Char(related="website_id.dreyes_auth_signup_subtitle", readonly=False)
