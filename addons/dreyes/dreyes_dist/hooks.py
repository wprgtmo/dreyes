# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api, fields


def migrate_existing_profiles(env):
    if not isinstance(env, api.Environment):
        env = api.Environment(env, SUPERUSER_ID, {})
    websites = env["website"].sudo().search([("signup_form_type", "=", "extended")])
    Profile = env["dreyes.distributor.profile"].sudo()
    for website in websites:
        users = env["res.users"].sudo().search([
            ("share", "=", True), ("company_id", "=", website.company_id.id),
            ("login", "not in", ["public", "portaltemplate"]),
        ])
        for partner in users.mapped("partner_id.commercial_partner_id"):
            if Profile.search_count([("partner_id", "=", partner.id), ("company_id", "=", website.company_id.id)]):
                continue
            complete_legacy = all([
                partner.first_name, partner.last_name, partner.street, partner.city,
                partner.state_id, partner.zip, partner.country_id, partner.phone,
                partner.tax_permit_attachment_id,
            ])
            profile = Profile.create({
                "partner_id": partner.id, "company_id": website.company_id.id, "website_id": website.id,
                "legal_business_name": partner.name, "state": "under_review" if complete_legacy else "no_profile",
                "submitted_at": fields.Datetime.now() if complete_legacy else False,
            })
            if partner.tax_permit_attachment_id:
                attachment = partner.tax_permit_attachment_id
                permit = env["dreyes.distributor.permit"].sudo().create({
                    "profile_id": profile.id, "attachment_id": attachment.id,
                    "filename": attachment.name, "mimetype": attachment.mimetype,
                    "uploaded_by_id": SUPERUSER_ID,
                })
                profile.current_permit_id = permit


def post_init_hook(env):
    if not isinstance(env, api.Environment):
        env = api.Environment(env, SUPERUSER_ID, {})
    migrate_existing_profiles(env)
