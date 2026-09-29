# -*- coding: utf-8 -*-
import base64

from werkzeug.utils import secure_filename

from odoo import _, http
from odoo.addons.dreyes_portal.controllers.main import (
    DreyesPortalController,
    DreyesPortalHome,
    DreyesPortalRedirectMixin,
    DreyesPortalSignup,
)
from odoo.exceptions import UserError
from odoo.http import request

EXTENDED_PROFILE_FIELDS = {
    "first_name",
    "last_name",
    "street",
    "street2",
    "city",
    "state_id",
    "zip",
    "country_id",
    "phone_code",
    "phone",
    "join_community",
}
MAX_TAX_PERMIT_SIZE = 15 * 1024 * 1024
ALLOWED_TAX_PERMIT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
PROFILE_COMPLETION_URL = "/profile/complete"


class DreyesDistRedirectMixin(DreyesPortalRedirectMixin):
    def _get_profile_completion_url(self):
        return PROFILE_COMPLETION_URL

    def _is_extended_signup_enabled(self):
        website = getattr(request, "website", False)
        if website:
            return (website.signup_form_type or website.company_id.signup_form_type or "basic") == "extended"
        return request.env.company.signup_form_type == "extended"

    def _requires_profile_completion(self, user):
        if not self._is_extended_signup_enabled() or user._is_public():
            return False

        partner = user.sudo().partner_id
        required_values = [
            partner.first_name,
            partner.last_name,
            partner.street,
            partner.city,
            partner.state_id,
            partner.zip,
            partner.country_id,
            partner.phone,
            partner.tax_permit_attachment_id,
        ]
        return not all(required_values)

    def _get_user_home_url(self, user):
        if self._requires_profile_completion(user):
            return self._get_profile_completion_url()
        return super()._get_user_home_url(user)

    def _get_signup_redirect_url(self, user):
        if self._requires_profile_completion(user):
            return self._get_profile_completion_url()
        return super()._get_signup_redirect_url(user)


class DreyesDistPortalController(DreyesDistRedirectMixin, DreyesPortalController):
    @http.route("/", type="http", auth="public", website=True)
    def index(self, **kwargs):
        user = request.env.user
        if self._requires_profile_completion(user):
            return request.redirect(self._get_profile_completion_url())
        return super().index(**kwargs)


class DreyesDistPortalHome(DreyesDistRedirectMixin, DreyesPortalHome):
    pass


class DreyesDistPortalSignup(DreyesDistRedirectMixin, DreyesPortalSignup):
    @http.route()
    def web_auth_signup(self, *args, **kw):
        return super().web_auth_signup(*args, **kw)


class DreyesDistProfileCompletion(DreyesDistRedirectMixin, http.Controller):
    def _get_profile_completion_values(self, partner):
        return {
            "first_name": partner.first_name or "",
            "last_name": partner.last_name or "",
            "street": partner.street or "",
            "street2": partner.street2 or "",
            "city": partner.city or "",
            "state_id": str(partner.state_id.id) if partner.state_id else "",
            "zip": partner.zip or "",
            "country_id": str(partner.country_id.id) if partner.country_id else "",
            "phone_code": "1",
            "phone": partner.phone or "",
            "join_community": partner.join_community,
        }

    def _get_profile_completion_qcontext(self, error=None, values=None):
        partner = request.env.user.sudo().partner_id
        qcontext = self._get_profile_completion_values(partner)
        qcontext.update({key: request.params.get(key, qcontext.get(key)) for key in EXTENDED_PROFILE_FIELDS})
        if values:
            qcontext.update(values)
        qcontext.update({
            "error": error,
            "countries": request.env["res.country"].sudo().search([]),
            "states": request.env["res.country.state"].sudo().search([]),
            "phone_countries": request.env["res.country"].sudo().search([("phone_code", "!=", False)]),
        })
        qcontext.setdefault("phone_code", "1")
        return qcontext

    def _validate_profile_completion(self, qcontext):
        required_fields = {
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "street": _("Street Address"),
            "city": _("City"),
            "state_id": _("Region/State/Province"),
            "zip": _("Postal / Zip code"),
            "country_id": _("Country"),
            "phone": _("Phone"),
        }
        missing = [label for field, label in required_fields.items() if not (qcontext.get(field) or "").strip()]
        if missing:
            raise UserError(_("Please complete the required fields: %s") % ", ".join(missing))

        partner = request.env.user.sudo().partner_id
        upload = request.httprequest.files.get("tax_permit")
        if (not upload or not upload.filename) and not partner.tax_permit_attachment_id:
            raise UserError(_("Texas Sales and Use Tax Permit is required."))
        if not upload or not upload.filename:
            return

        filename = secure_filename(upload.filename)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_TAX_PERMIT_EXTENSIONS:
            raise UserError(_("The tax permit file must be a PDF, JPG, JPEG, or PNG."))

        file_data = upload.read()
        if len(file_data) > MAX_TAX_PERMIT_SIZE:
            raise UserError(_("The tax permit file must be 15MB or smaller."))

        qcontext["tax_permit_file"] = {
            "filename": filename,
            "content": file_data,
            "mimetype": upload.mimetype,
        }

    def _update_profile_completion_partner(self, qcontext):
        partner = request.env.user.sudo().partner_id
        phone_code = (qcontext.get("phone_code") or "").strip()
        phone = (qcontext.get("phone") or "").strip()
        if phone_code and not phone_code.startswith("+"):
            phone_code = f"+{phone_code}"

        partner_values = {
            "first_name": (qcontext.get("first_name") or "").strip(),
            "last_name": (qcontext.get("last_name") or "").strip(),
            "join_community": bool(qcontext.get("join_community")),
            "street": (qcontext.get("street") or "").strip(),
            "street2": (qcontext.get("street2") or "").strip(),
            "city": (qcontext.get("city") or "").strip(),
            "state_id": int(qcontext.get("state_id")),
            "zip": (qcontext.get("zip") or "").strip(),
            "country_id": int(qcontext.get("country_id")),
            "phone": f"{phone_code} {phone}".strip(),
        }
        partner.write(partner_values)

        tax_permit = qcontext.get("tax_permit_file")
        if tax_permit:
            attachment = request.env["ir.attachment"].sudo().create({
                "name": tax_permit["filename"],
                "datas": base64.b64encode(tax_permit["content"]).decode("ascii"),
                "mimetype": tax_permit["mimetype"],
                "res_model": "res.partner",
                "res_id": partner.id,
            })
            partner.tax_permit_attachment_id = attachment.id

    @http.route(PROFILE_COMPLETION_URL, type="http", auth="user", website=True, sitemap=False)
    def profile_complete(self, **kw):
        user = request.env.user
        if not self._requires_profile_completion(user):
            return request.redirect(self._get_user_home_url(user))

        qcontext = self._get_profile_completion_qcontext()
        if request.httprequest.method == "POST":
            try:
                self._validate_profile_completion(qcontext)
                self._update_profile_completion_partner(qcontext)
                return request.redirect(self._get_user_home_url(user))
            except UserError as e:
                qcontext["error"] = e.args[0]

        return request.render("dreyes_dist.portal_profile_complete", qcontext)
