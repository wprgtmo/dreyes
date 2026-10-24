# -*- coding: utf-8 -*-

import json

from odoo import http
from odoo.http import request
from odoo.tools import ustr

from odoo.addons.web_pwa_customize.controllers import webmanifest


class WebManifest(webmanifest.WebManifest):
    @http.route(
        "/web/manifest.webmanifest",
        type="http",
        auth="public",
        methods=["GET"],
        readonly=True,
    )
    def webmanifest(self):
        res = super().webmanifest()
        manifest = json.loads(res.response[0])
        manifest["id"] = request.env["ir.http"].sudo()._get_pwa_manifest_id()
        body = json.dumps(manifest, default=ustr)
        return request.make_response(
            body,
            [
                ("Content-Type", "application/manifest+json"),
            ],
        )
