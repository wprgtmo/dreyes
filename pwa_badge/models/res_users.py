# -*- coding: utf-8 -*-

from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _get_pwa_badge_count_mode(self):
        return (
            self.env["ir.config_parameter"].sudo().get_param("pwa_badge.count_mode")
            or "both"
        )

    @api.model
    def _get_pwa_badge_android_mode(self):
        return (
            self.env["ir.config_parameter"].sudo().get_param("pwa_badge.android_mode")
            or "best_effort"
        )

    @api.model
    def _get_pwa_badge_title_fallback(self):
        raw_value = self.env["ir.config_parameter"].sudo().get_param(
            "pwa_badge.title_fallback"
        )
        if raw_value is None:
            return True
        return str(raw_value).lower() in {"1", "true", "yes"}

    def _get_pwa_badge_mail_count(self):
        self.ensure_one()
        partner = self.partner_id.sudo()
        for field_name in ("message_needaction_counter", "message_unread_counter"):
            if field_name in partner._fields:
                return int(partner[field_name] or 0)
        return 0

    def _get_pwa_badge_activities_count(self):
        self.ensure_one()
        return self.env["mail.activity"].sudo().search_count(
            [("user_id", "=", self.id)]
        )

    def _get_pwa_badge_total_count(self, activities_count, mail_count, count_mode):
        if count_mode == "activities":
            return activities_count
        if count_mode == "mail":
            return mail_count
        return activities_count + mail_count

    def _get_pwa_badge_counts(self):
        self.ensure_one()
        count_mode = self._get_pwa_badge_count_mode()
        android_mode = self._get_pwa_badge_android_mode()
        activities_count = self._get_pwa_badge_activities_count()
        mail_count = self._get_pwa_badge_mail_count()
        return {
            "activities_count": activities_count,
            "mail_count": mail_count,
            "total_count": self._get_pwa_badge_total_count(
                activities_count, mail_count, count_mode
            ),
            "android_mode": android_mode,
            "count_mode": count_mode,
            "title_fallback": self._get_pwa_badge_title_fallback(),
        }
