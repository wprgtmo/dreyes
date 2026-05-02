# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _authenticate(cls, endpoint):
        res = super()._authenticate(endpoint)

        user = request.env.user
        # active_profile = user.get_active_profile() if hasattr(user, "get_active_profile") else False
        # request.active_profile = active_profile or False

        return res
