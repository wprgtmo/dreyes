# -*- coding: utf-8 -*-

from odoo import api, models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def _get_pwa_manifest_id(self):
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        return f"{base_url}/web?db={self.env.cr.dbname}"

    @api.model
    def _get_pwa_badge_head_data(self):
        icp = self.env["ir.config_parameter"].sudo()
        short_name = icp.get_param("pwa.manifest.short_name", "Odoo")
        theme_color = icp.get_param("pwa.manifest.theme_color", "#714B67")
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .search([("url", "=", "/pwa_badge/apple-touch-icon.png")], limit=1)
        )
        return {
            "apple_touch_icon_url": attachment.url if attachment else False,
            "manifest_id": self._get_pwa_manifest_id(),
            "short_name": short_name,
            "theme_color": theme_color,
        }
