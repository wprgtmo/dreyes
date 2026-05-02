# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.home import Home
from odoo.http import request


class DomPortalRedirectMixin:
    """Centraliza las decisiones de entrada y redireccion del portal."""

    def _get_login_url(self):
        return "/web/login"

    def _get_profile_creation_url(self):
        return "/profile/new"

    def _get_dashboard_url(self):
        return "/inicio"

    def _get_profile_url(self, profile):
        return f"/profile/view/{profile.id}"

    def _get_active_profile(self, user):
        if hasattr(user, "get_active_profile"):
            return user.get_active_profile()
        return False

    def _get_public_home_url(self):
        return self._get_login_url()

    def _get_user_home_url(self, user):
        if user._is_public():
            return self._get_public_home_url()

        active_profile = self._get_active_profile(user)
        if not active_profile:
            return self._get_profile_creation_url()

        return self._get_dashboard_url()

    def _get_signup_redirect_url(self, user):
        profile = getattr(user, "last_active_profile_id", False) or self._get_active_profile(user)
        if profile:
            return self._get_profile_url(profile)
        return self._get_profile_creation_url()


class DomPortalController(DomPortalRedirectMixin, http.Controller):
    @http.route("/", type="http", auth="public", website=True)
    def index(self, **kwargs):
        return request.redirect(self._get_user_home_url(request.env.user))


class DomPortalHome(DomPortalRedirectMixin, Home):
    def _login_redirect(self, uid, redirect=None):
        """Resuelve el destino posterior al login del portal."""
        if not redirect:
            user = request.env["res.users"].sudo().browse(uid)
            redirect = self._get_user_home_url(user)
        return super()._login_redirect(uid, redirect=redirect)


class DomPortalSignup(DomPortalRedirectMixin, AuthSignupHome):
    @http.route()
    def web_auth_signup(self, *args, **kw):
        response = super().web_auth_signup(*args, **kw)
        if (
            request.httprequest.method == "POST"
            and request.session.uid
            and request.params.get("login_success")
        ):
            user = request.env["res.users"].sudo().browse(request.session.uid)
            return request.redirect(self._get_signup_redirect_url(user))
        return response
