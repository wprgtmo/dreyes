# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.website.controllers.main import Website
from odoo.addons.web.controllers.home import Home
from odoo.http import request


class DreyesPortalRedirectMixin:
    """Centraliza las decisiones de entrada y redireccion del portal."""

    def _get_login_url(self):
        return "/web/login"

    def _get_site_home_url(self):
        return "/"

    def _get_public_home_url(self):
        return self._get_login_url()

    def _get_user_home_url(self, user):
        if user._is_public():
            return self._get_public_home_url()
        return self._get_site_home_url()

    def _get_signup_redirect_url(self, user):
        return self._get_user_home_url(user)


class DreyesPortalController(DreyesPortalRedirectMixin, Website):
    @http.route("/", type="http", auth="public", website=True)
    def index(self, **kwargs):
        user = request.env.user
        if not user._is_public():
            return super().index(**kwargs)

        return request.redirect(self._get_user_home_url(user))


class DreyesPortalHome(DreyesPortalRedirectMixin, Home):
    def _login_redirect(self, uid, redirect=None):
        """Resuelve el destino posterior al login del portal."""
        if not redirect:
            user = request.env["res.users"].sudo().browse(uid)
            redirect = self._get_user_home_url(user)
        return super()._login_redirect(uid, redirect=redirect)


class DreyesPortalSignup(DreyesPortalRedirectMixin, AuthSignupHome):
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
