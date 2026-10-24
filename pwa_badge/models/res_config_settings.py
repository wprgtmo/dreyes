# -*- coding: utf-8 -*-

import base64
import io

from PIL import Image

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

APPLE_TOUCH_ICON_URL = "/pwa_badge/apple-touch-icon.png"
PWA_ICON_URL_PREFIX = "/web_pwa_customize/icon."


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pwa_badge_count_mode = fields.Selection(
        selection=[
            ("activities", "Solo actividades"),
            ("mail", "Solo notificaciones mail"),
            ("both", "Ambas"),
        ],
        string="Fuente del badge",
        config_parameter="pwa_badge.count_mode",
        default="both",
    )
    pwa_badge_android_mode = fields.Selection(
        selection=[
            ("best_effort", "Best effort"),
            ("system_notifications", "Notificaciones del sistema"),
        ],
        string="Modo Android",
        config_parameter="pwa_badge.android_mode",
        default="best_effort",
    )
    pwa_badge_enable_title_fallback = fields.Boolean(
        string="Fallback en el titulo",
        config_parameter="pwa_badge.title_fallback",
        default=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        values.setdefault("pwa_badge_count_mode", "both")
        values.setdefault("pwa_badge_android_mode", "best_effort")
        values.setdefault("pwa_badge_enable_title_fallback", True)
        return values

    def _get_pwa_icon_attachment(self):
        return (
            self.env["ir.attachment"]
            .sudo()
            .search(
                ["|", ("url", "=", "/web_pwa_customize/icon.png"), ("url", "=", "/web_pwa_customize/icon.svg")],
                limit=1,
            )
        )

    def _get_apple_touch_attachment(self):
        return (
            self.env["ir.attachment"]
            .sudo()
            .search([("url", "=", APPLE_TOUCH_ICON_URL)], limit=1)
        )

    def _validate_apple_icon_source(self, attachment):
        if not attachment:
            return
        raw = base64.b64decode(attachment.datas or b"")
        mimetype = guess_mimetype(raw)
        if not mimetype.startswith("image/png"):
            raise UserError(
                _(
                    "El icono PWA debe ser PNG de al menos 512x512 para generar el apple-touch-icon."
                )
            )
        image = Image.open(io.BytesIO(raw))
        if image.size[0] < 512 or image.size[1] < 512:
            raise UserError(
                _(
                    "El icono PWA debe ser PNG de al menos 512x512 para generar el apple-touch-icon."
                )
            )
        return image

    def _write_apple_touch_icon(self, image):
        output = io.BytesIO()
        image.resize((180, 180)).save(output, format="PNG")
        values = {
            "name": APPLE_TOUCH_ICON_URL,
            "url": APPLE_TOUCH_ICON_URL,
            "type": "binary",
            "mimetype": "image/png",
            "datas": base64.b64encode(output.getvalue()),
            "db_datas": base64.b64encode(output.getvalue()),
        }
        attachment = self._get_apple_touch_attachment()
        if attachment:
            attachment.write(values)
        else:
            self.env["ir.attachment"].sudo().create(values)

    def set_values(self):
        res = super().set_values()
        attachment = self._get_pwa_icon_attachment()
        if not attachment:
            apple_touch_attachment = self._get_apple_touch_attachment()
            if apple_touch_attachment:
                apple_touch_attachment.unlink()
            return res
        image = self._validate_apple_icon_source(attachment)
        self._write_apple_touch_icon(image)
        return res
