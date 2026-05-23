# -*- coding: utf-8 -*-
from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    dreyes_auth_logo = fields.Image(string="Logo del login/registro", max_width=1024, max_height=512)
    dreyes_auth_panel_start = fields.Char(string="Rojo inicial", default="#f31922")
    dreyes_auth_panel_end = fields.Char(string="Rojo final", default="#d0111d")
    dreyes_auth_accent = fields.Char(string="Color secundario", default="#302678")
    dreyes_auth_background = fields.Char(string="Fondo exterior", default="#d8d5d2")
    dreyes_auth_welcome = fields.Char(string="Texto de bienvenida", default="Bienvenido a")
    dreyes_auth_tagline = fields.Char(string="Frase lateral", default="En el lugar de tu corazon.")
    dreyes_auth_footer_left = fields.Char(string="Texto inferior izquierdo", default="Latin Market")
    dreyes_auth_footer_right = fields.Char(string="Texto inferior derecho", default="Productos y sabores")
    dreyes_auth_login_title = fields.Char(string="Titulo de login", default="Bienvenido a su tienda")
    dreyes_auth_login_subtitle = fields.Char(string="Subtitulo de login", default="Inicia sesion para continuar comprando.")
    dreyes_auth_signup_title = fields.Char(string="Titulo de registro", default="Crea tu cuenta")
    dreyes_auth_signup_subtitle = fields.Char(string="Subtitulo de registro", default="Unete a DReyes.")
