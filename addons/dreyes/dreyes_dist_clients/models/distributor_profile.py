# -*- coding: utf-8 -*-
from odoo import fields, models


class DreyesDistributorProfile(models.Model):
    _inherit = "dreyes.distributor.profile"

    request_count = fields.Integer(string="Solicitudes", default=1, readonly=True)
    contact_email = fields.Char(string="Correo", related="partner_id.email", store=True, readonly=True)
    contact_phone = fields.Char(string="Teléfono", related="partner_id.phone", store=True, readonly=True)
    city = fields.Char(string="Ciudad", related="partner_id.city", store=True, readonly=True)
    state_id = fields.Many2one("res.country.state", string="Estado/Provincia", related="partner_id.state_id", store=True, readonly=True)
    country_id = fields.Many2one("res.country", string="País", related="partner_id.country_id", store=True, readonly=True)
