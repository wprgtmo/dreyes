# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class PwaBadgeController(http.Controller):
    @http.route(
        "/pwa_badge/count",
        type="http",
        auth="user",
        methods=["GET", "POST"],
        csrf=False,
        readonly=True,
    )
    def pwa_badge_count(self, **kwargs):
        data = request.env.user.sudo()._get_pwa_badge_counts()
        return request.make_json_response(data)
