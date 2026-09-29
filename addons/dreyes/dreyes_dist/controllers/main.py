# -*- coding: utf-8 -*-
import base64
import re

from werkzeug.utils import secure_filename

from odoo import _, fields, http
from odoo.addons.dreyes_portal.controllers.main import (
    DreyesPortalController, DreyesPortalHome, DreyesPortalRedirectMixin, DreyesPortalSignup,
)
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.exceptions import UserError, ValidationError
from odoo.http import content_disposition, request


MAX_TAX_PERMIT_SIZE = 15 * 1024 * 1024
ALLOWED_TAX_PERMIT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
PROFILE_URL = "/my/distributor-profile"


class DreyesDistRedirectMixin(DreyesPortalRedirectMixin):
    def _is_extended_signup_enabled(self):
        website = getattr(request, "website", False)
        return bool(website and website._dreyes_is_distribution_site())

    def _requires_profile_prompt(self, user):
        if not self._is_extended_signup_enabled() or user._is_public():
            return False
        profile = request.website._dreyes_profile_for_partner(user.partner_id, create=True)
        return profile.state == "no_profile"

    def _get_user_home_url(self, user):
        if self._requires_profile_prompt(user):
            return PROFILE_URL
        return super()._get_user_home_url(user)

    def _get_signup_redirect_url(self, user):
        if self._requires_profile_prompt(user):
            return PROFILE_URL
        return super()._get_signup_redirect_url(user)


class DreyesDistPortalController(DreyesDistRedirectMixin, DreyesPortalController):
    @http.route("/", type="http", auth="public", website=True)
    def index(self, **kwargs):
        return super().index(**kwargs)


class DreyesDistPortalHome(DreyesDistRedirectMixin, DreyesPortalHome):
    def _login_redirect(self, uid, redirect=None):
        user = request.env["res.users"].sudo().browse(uid)
        if self._requires_profile_prompt(user):
            redirect = PROFILE_URL
        return super()._login_redirect(uid, redirect=redirect)


class DreyesDistPortalSignup(DreyesDistRedirectMixin, DreyesPortalSignup):
    @http.route()
    def web_auth_signup(self, *args, **kw):
        return super().web_auth_signup(*args, **kw)


class DreyesDistProfile(http.Controller):
    def _profile(self):
        return request.website._dreyes_profile_for_partner(request.env.user.partner_id, create=True)

    def _split_phone(self, phone):
        match = re.match(r"^\+(\d+)\s+(.+)$", phone or "")
        return (match.group(1), match.group(2)) if match else ("1", phone or "")

    def _values(self, profile, error=None):
        partner = profile.partner_id
        phone_code, phone = self._split_phone(partner.phone)
        state_label = dict(profile._fields["state"].selection).get(profile.state)
        return {
            "profile": profile,
            "profile_state": profile.state,
            "profile_state_label": state_label,
            "legal_business_name": profile.legal_business_name or "",
            "ein_masked": "***-**-%s" % profile.ein[-4:] if profile.ein else "",
            "tax_permit_number": profile.tax_permit_number or "",
            "first_name": partner.first_name or "", "last_name": partner.last_name or "",
            "email": partner.email or request.env.user.login or "",
            "street": partner.street or "", "street2": partner.street2 or "",
            "city": partner.city or "", "state_id": str(partner.state_id.id) if partner.state_id else "",
            "zip": partner.zip or "", "country_id": str(partner.country_id.id) if partner.country_id else "",
            "phone_code": phone_code, "phone": phone, "join_community": partner.join_community,
            "countries": request.env["res.country"].sudo().search([]),
            "states": request.env["res.country.state"].sudo().search([]),
            "phone_countries": request.env["res.country"].sudo().search([("phone_code", "!=", False)]),
            "error": error,
        }

    def _normalized_digits(self, value, length, label, required=False):
        value = (value or "").strip()
        if not value:
            if required:
                raise UserError(_("%s es obligatorio.") % label)
            return False
        digits = re.sub(r"[\s-]", "", value)
        if not digits.isdigit() or len(digits) != length:
            raise UserError(_("%s debe contener exactamente %s dígitos.") % (label, length))
        return digits

    def _read_upload(self):
        upload = request.httprequest.files.get("tax_permit")
        if not upload or not upload.filename:
            return False
        filename = secure_filename(upload.filename)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_TAX_PERMIT_EXTENSIONS:
            raise UserError(_("El tax permit debe ser un archivo PDF, JPG, JPEG o PNG."))
        data = upload.read(MAX_TAX_PERMIT_SIZE + 1)
        if not data:
            raise UserError(_("El archivo del tax permit está vacío."))
        if len(data) > MAX_TAX_PERMIT_SIZE:
            raise UserError(_("El tax permit debe pesar 15 MB o menos."))
        return {"filename": filename, "data": data, "mimetype": upload.mimetype}

    def _save(self, profile, post, submit=False):
        upload = self._read_upload()
        ein_value = post.get("ein")
        ein = profile.ein if not (ein_value or "").strip() and profile.ein else self._normalized_digits(
            ein_value, 9, _("EIN"), required=submit,
        )
        permit_number = self._normalized_digits(
            post.get("tax_permit_number"), 11, _("Número de permiso de Texas"), required=submit,
        )
        country_id = int(post["country_id"]) if post.get("country_id") else False
        state_id = int(post["state_id"]) if post.get("state_id") else False
        phone_code = re.sub(r"\D", "", post.get("phone_code") or "")
        phone_number = (post.get("phone") or "").strip()
        partner_values = {
            "first_name": (post.get("first_name") or "").strip(),
            "last_name": (post.get("last_name") or "").strip(),
            "email": (post.get("email") or "").strip(),
            "street": (post.get("street") or "").strip(), "street2": (post.get("street2") or "").strip(),
            "city": (post.get("city") or "").strip(), "state_id": state_id,
            "zip": (post.get("zip") or "").strip(), "country_id": country_id,
            "phone": (f"+{phone_code} {phone_number}" if phone_code else phone_number).strip(),
            "join_community": bool(post.get("join_community")),
        }
        old_state = profile.state
        profile.partner_id.sudo().write(partner_values)
        profile.sudo().write({
            "legal_business_name": (post.get("legal_business_name") or "").strip(),
            "ein": ein, "tax_permit_number": permit_number,
        })
        if upload:
            attachment = request.env["ir.attachment"].sudo().create({
                "name": upload["filename"], "datas": base64.b64encode(upload["data"]),
                "mimetype": upload["mimetype"], "res_model": "dreyes.distributor.profile", "res_id": profile.id,
                "public": False,
            })
            permit = request.env["dreyes.distributor.permit"].sudo().create({
                "profile_id": profile.id, "attachment_id": attachment.id, "filename": upload["filename"],
                "mimetype": upload["mimetype"], "uploaded_by_id": request.env.user.id,
            })
            profile.sudo().current_permit_id = permit

        if submit:
            missing = profile._required_missing_labels()
            if missing:
                raise UserError(_("Faltan datos obligatorios: %s") % ", ".join(missing))
            profile.sudo().write({
                "state": "under_review", "submitted_at": fields.Datetime.now(),
                "submitted_by_id": request.env.user.id, "correction_reason": False,
                "reviewed_at": False, "reviewed_by_id": False, "approved_at": False, "approved_by_id": False,
            })
            profile.notify_reviewers(
                _("Perfil de distribuidor enviado a revisión"),
                _("El cliente %s envió su perfil de distribuidor a revisión.") % (profile.legal_business_name or profile.partner_id.name),
            )
        elif old_state == "pending_approval":
            profile.sudo().write({"state": "under_review", "reviewed_at": False, "reviewed_by_id": False})
            profile.notify_reviewers(_("Perfil modificado"), _("Un perfil pendiente de aprobación fue modificado y debe revisarse nuevamente."))
        elif old_state == "under_review":
            profile.notify_reviewers(_("Perfil modificado durante la revisión"), _("El cliente actualizó su expediente en revisión."))
        elif old_state == "approved" and upload:
            profile.sudo().write({"state": "under_review", "approved_at": False, "approved_by_id": False})
            profile.notify_reviewers(_("Nuevo tax permit"), _("Un cliente aprobado reemplazó su tax permit y requiere nueva revisión."))

    @http.route([PROFILE_URL, "/profile/complete"], type="http", auth="user", website=True, methods=["GET", "POST"])
    def distributor_profile(self, **post):
        if not request.website._dreyes_is_distribution_site():
            return request.redirect("/my/account")
        profile = self._profile()
        error = None
        if request.httprequest.method == "POST":
            try:
                action = post.get("action", "save")
                if action == "later":
                    return request.redirect("/my/home")
                self._save(profile, post, submit=action == "submit")
                return request.redirect(PROFILE_URL + "?saved=1")
            except (UserError, ValidationError, ValueError) as exc:
                error = exc.args[0] if exc.args else str(exc)
        values = self._values(profile, error=error)
        values["saved"] = request.params.get("saved")
        return request.render("dreyes_dist.portal_distributor_profile", values)

    @http.route("/my/distributor-profile/permit/<int:permit_id>", type="http", auth="user", website=True)
    def download_permit(self, permit_id, **kw):
        permit = request.env["dreyes.distributor.permit"].sudo().browse(permit_id).exists()
        profile = self._profile()
        if not permit or permit.profile_id != profile:
            return request.not_found()
        data = base64.b64decode(permit.attachment_id.datas or b"")
        return request.make_response(data, headers=[
            ("Content-Type", permit.mimetype or "application/octet-stream"),
            ("Content-Disposition", content_disposition(permit.filename)),
            ("X-Content-Type-Options", "nosniff"),
        ])


class DreyesDistributionWebsiteSale(WebsiteSale):
    def _dreyes_blocked(self):
        return request.website._dreyes_is_distribution_site() and not request.website._dreyes_can_purchase()

    def _dreyes_blocked_redirect(self):
        if request.env.user._is_public():
            return request.redirect("/web/login?redirect=/shop")
        return request.redirect(PROFILE_URL)

    @http.route()
    def is_add_to_cart_allowed(self, product_id, **kwargs):
        if self._dreyes_blocked():
            return False
        return super().is_add_to_cart_allowed(product_id, **kwargs)

    @http.route()
    def cart_update(self, product_id, add_qty=1, set_qty=0, **kwargs):
        if self._dreyes_blocked():
            return self._dreyes_blocked_redirect()
        return super().cart_update(product_id, add_qty=add_qty, set_qty=set_qty, **kwargs)

    @http.route()
    def cart_update_json(self, product_id, **kwargs):
        if self._dreyes_blocked():
            message = _("Su cuenta debe estar aprobada antes de comprar.")
            return {"quantity": 0, "cart_quantity": 0, "warning": message, "notification_info": {"warning": message}}
        return super().cart_update_json(product_id, **kwargs)

    @http.route()
    def cart(self, access_token=None, revive="", **post):
        if self._dreyes_blocked():
            return self._dreyes_blocked_redirect()
        return super().cart(access_token=access_token, revive=revive, **post)

    @http.route()
    def shop_checkout(self, try_skip_step=None, **query_params):
        if self._dreyes_blocked():
            return self._dreyes_blocked_redirect()
        return super().shop_checkout(try_skip_step=try_skip_step, **query_params)

    @http.route()
    def shop_payment(self, **post):
        if self._dreyes_blocked():
            return self._dreyes_blocked_redirect()
        return super().shop_payment(**post)

    @http.route()
    def shop_payment_validate(self, sale_order_id=None, **post):
        if self._dreyes_blocked():
            return self._dreyes_blocked_redirect()
        return super().shop_payment_validate(sale_order_id=sale_order_id, **post)
