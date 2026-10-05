import base64
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class CloverConnector(models.Model):
    _name = "clover.connector"
    _description = "Conexión Clover"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("connected", "Conectado"), ("paused", "Pausado"), ("error", "Error")],
        default="draft",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    environment = fields.Selection(
        [("sandbox", "Sandbox"), ("production", "Producción")], default="sandbox", required=True
    )
    region = fields.Selection(
        [("na", "Norteamérica"), ("eu", "Europa"), ("la", "Latinoamérica")], default="na", required=True
    )
    app_id = fields.Char(required=True, copy=False)
    app_secret = fields.Char(string="Nuevo App Secret", copy=False, groups="dreyes_clover_sync.group_clover_manager")
    app_secret_encrypted = fields.Text(copy=False, groups="base.group_system")
    webhook_auth_code = fields.Char(string="Nuevo código de webhook", copy=False, groups="dreyes_clover_sync.group_clover_manager")
    webhook_auth_code_encrypted = fields.Text(copy=False, groups="base.group_system")
    merchant_id = fields.Char(copy=False, tracking=True, index=True)
    access_token_encrypted = fields.Text(copy=False, groups="base.group_system")
    refresh_token_encrypted = fields.Text(copy=False, groups="base.group_system")
    access_token_expiration = fields.Datetime(copy=False)
    refresh_token_expiration = fields.Datetime(copy=False)
    oauth_state = fields.Char(copy=False, groups="base.group_system")
    oauth_state_created_at = fields.Datetime(copy=False, groups="base.group_system")
    public_base_url = fields.Char(required=True, help="URL HTTPS pública de esta instancia de Odoo.")
    backfill_from = fields.Datetime(string="Importar ventas desde")
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True)
    location_id = fields.Many2one(
        "stock.location", required=True, check_company=True, domain="[('usage', '=', 'internal')]"
    )
    pricelist_id = fields.Many2one("product.pricelist", required=True, check_company=True)
    pos_config_id = fields.Many2one("pos.config", required=True, check_company=True)
    anonymous_partner_id = fields.Many2one("res.partner", check_company=True)
    tip_product_id = fields.Many2one("product.product", check_company=True, domain="[('type', '=', 'service')]")
    service_charge_product_id = fields.Many2one("product.product", check_company=True, domain="[('type', '=', 'service')]")
    refund_product_id = fields.Many2one("product.product", check_company=True, domain="[('type', '=', 'service')]")
    discount_product_id = fields.Many2one("product.product", check_company=True, domain="[('type', '=', 'service')]")
    initial_import_done = fields.Boolean(copy=False, tracking=True)
    last_catalog_sync = fields.Datetime(copy=False)
    last_stock_sync = fields.Datetime(copy=False)
    last_order_sync = fields.Datetime(copy=False)
    last_error = fields.Text(copy=False)
    website_ids = fields.Many2many("website", compute="_compute_websites", string="Sitios web")
    event_count = fields.Integer(compute="_compute_counts")
    conflict_count = fields.Integer(compute="_compute_counts")

    _sql_constraints = [
        ("merchant_environment_unique", "unique(environment, merchant_id)", "Ese comercio Clover ya está conectado."),
    ]

    @api.depends("company_id")
    def _compute_counts(self):
        Event = self.env["clover.sync.event"]
        Conflict = self.env["clover.sync.conflict"]
        for connector in self:
            connector.event_count = Event.search_count([("connector_id", "=", connector.id)])
            connector.conflict_count = Conflict.search_count(
                [("connector_id", "=", connector.id), ("state", "=", "open")]
            )

    @api.depends("company_id")
    def _compute_websites(self):
        Website = self.env["website"]
        for connector in self:
            connector.website_ids = Website.search([("company_id", "=", connector.company_id.id)])

    @api.constrains("active", "company_id", "state")
    def _check_one_active_per_company(self):
        for connector in self.filtered(lambda c: c.active and c.state != "paused"):
            duplicate = self.search_count([
                ("id", "!=", connector.id),
                ("company_id", "=", connector.company_id.id),
                ("active", "=", True),
                ("state", "!=", "paused"),
            ])
            if duplicate:
                raise ValidationError(_("Solo puede existir una conexión Clover activa por empresa."))

    @api.constrains("public_base_url")
    def _check_public_url(self):
        for connector in self:
            if connector.public_base_url and not connector.public_base_url.lower().startswith("https://"):
                raise ValidationError(_("La URL pública de Clover debe usar HTTPS."))

    @api.constrains("warehouse_id", "location_id", "pricelist_id", "pos_config_id", "company_id")
    def _check_company_configuration(self):
        for connector in self:
            records = (connector.warehouse_id, connector.location_id, connector.pos_config_id)
            if any(record.company_id != connector.company_id for record in records if record):
                raise ValidationError(_("Almacén, ubicación y POS deben pertenecer a la empresa de la conexión."))
            if connector.pricelist_id.company_id and connector.pricelist_id.company_id != connector.company_id:
                raise ValidationError(_("La lista de precios debe pertenecer a la empresa de la conexión."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._consume_secret_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        self._consume_secret_values(vals)
        return super().write(vals)

    @api.model
    def _consume_secret_values(self, vals):
        for public_name, encrypted_name in (
            ("app_secret", "app_secret_encrypted"),
            ("webhook_auth_code", "webhook_auth_code_encrypted"),
        ):
            secret = vals.pop(public_name, False)
            if secret:
                vals[encrypted_name] = self._encrypt(secret)
        vals["app_secret"] = False
        vals["webhook_auth_code"] = False

    @api.model
    def _fernet(self):
        secret = os.environ.get("CLOVER_TOKEN_ENCRYPTION_KEY")
        if not secret:
            raise UserError(_("Falta la variable CLOVER_TOKEN_ENCRYPTION_KEY en el servidor Odoo."))
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)

    @api.model
    def _encrypt(self, value):
        return self._fernet().encrypt(value.encode()).decode() if value else False

    def _decrypt(self, encrypted):
        if not encrypted:
            return False
        try:
            return self._fernet().decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise UserError(_("No se pudo descifrar una credencial Clover. Verifique la clave del servidor.")) from exc

    def _app_secret(self):
        self.ensure_one()
        return self._decrypt(self.app_secret_encrypted)

    def _webhook_auth_code(self):
        self.ensure_one()
        return self._decrypt(self.webhook_auth_code_encrypted)

    @property
    def api_base_url(self):
        self.ensure_one()
        if self.environment == "sandbox":
            return "https://apisandbox.dev.clover.com"
        return {"na": "https://api.clover.com", "eu": "https://api.eu.clover.com", "la": "https://api.la.clover.com"}[self.region]

    @property
    def authorize_base_url(self):
        self.ensure_one()
        if self.environment == "sandbox":
            return "https://sandbox.dev.clover.com"
        return {"na": "https://www.clover.com", "eu": "https://www.eu.clover.com", "la": "https://www.la.clover.com"}[self.region]

    def _callback_url(self):
        self.ensure_one()
        return f"{self.public_base_url.rstrip('/')}/clover/oauth/callback"

    def action_connect_oauth(self):
        self.ensure_one()
        self._assert_manager()
        if not self._app_secret():
            raise UserError(_("Capture el App Secret antes de conectar."))
        state = secrets.token_urlsafe(32)
        self.write({"oauth_state": state, "oauth_state_created_at": fields.Datetime.now()})
        query = urlencode({
            "client_id": self.app_id,
            "redirect_uri": self._callback_url(),
            "response_type": "code",
            "state": state,
        })
        return {"type": "ir.actions.act_url", "url": f"{self.authorize_base_url}/oauth/v2/authorize?{query}", "target": "self"}

    def exchange_oauth_code(self, code, merchant_id=False):
        self.ensure_one()
        payload = {"client_id": self.app_id, "client_secret": self._app_secret(), "code": code}
        response = requests.post(f"{self.api_base_url}/oauth/v2/token", json=payload, timeout=20)
        response.raise_for_status()
        token_data = response.json()
        self._store_tokens(token_data)
        values = {"state": "connected", "oauth_state": False, "oauth_state_created_at": False, "last_error": False}
        if merchant_id:
            values["merchant_id"] = merchant_id
        self.write(values)

    def _store_tokens(self, token_data):
        values = {"access_token_encrypted": self._encrypt(token_data["access_token"])}
        if token_data.get("refresh_token"):
            values["refresh_token_encrypted"] = self._encrypt(token_data["refresh_token"])
        for source, target in (
            ("access_token_expiration", "access_token_expiration"),
            ("refresh_token_expiration", "refresh_token_expiration"),
        ):
            if token_data.get(source):
                values[target] = datetime.fromtimestamp(int(token_data[source]), tz=timezone.utc).replace(tzinfo=None)
        self.write(values)

    def _access_token(self):
        self.ensure_one()
        if self.access_token_expiration and self.access_token_expiration <= fields.Datetime.now():
            self._refresh_access_token()
        token = self._decrypt(self.access_token_encrypted)
        if not token:
            raise UserError(_("La conexión Clover no tiene token de acceso."))
        return token

    def _refresh_access_token(self):
        self.ensure_one()
        refresh_token = self._decrypt(self.refresh_token_encrypted)
        if not refresh_token:
            raise UserError(_("El token Clover expiró y no existe refresh token. Reconecte la cuenta."))
        response = requests.post(
            f"{self.api_base_url}/oauth/v2/refresh",
            json={"client_id": self.app_id, "client_secret": self._app_secret(), "refresh_token": refresh_token},
            timeout=20,
        )
        response.raise_for_status()
        self._store_tokens(response.json())

    def api_request(self, method, path, params=None, payload=None, retry_auth=True):
        self.ensure_one()
        url = path if path.startswith("https://") else f"{self.api_base_url}{path}"
        response = requests.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Accept": "application/json",
                "User-Agent": "DReyes-Odoo-Clover/18.0",
            },
            params=params,
            json=payload,
            timeout=25,
        )
        if response.status_code == 401 and retry_auth and self.refresh_token_encrypted:
            self._refresh_access_token()
            return self.api_request(method, path, params=params, payload=payload, retry_auth=False)
        if response.status_code == 429:
            raise UserError(_("Clover limitó temporalmente las solicitudes; el evento será reintentado."))
        response.raise_for_status()
        return response.json() if response.content else {}

    def merchant_path(self, suffix):
        self.ensure_one()
        if not self.merchant_id:
            raise UserError(_("Falta el Merchant ID de Clover."))
        return f"/v3/merchants/{self.merchant_id}/{suffix.lstrip('/')}"

    def action_test_connection(self):
        self.ensure_one()
        self.api_request("GET", f"/v3/merchants/{self.merchant_id}")
        self.write({"state": "connected", "last_error": False})
        return self._notification(_("Conexión Clover verificada correctamente."))

    def action_initial_import(self):
        self.ensure_one()
        self._validate_ready()
        self.env["clover.sync.event"].enqueue(self, "in", "catalog_pull", "catalog", self.merchant_id)
        return self._notification(_("La importación inicial fue enviada a la cola."))

    def action_publish_catalog(self):
        self.ensure_one()
        self._validate_ready()
        self.env["clover.sync.event"].enqueue(self, "out", "catalog_push", "catalog", str(self.id))
        return self._notification(_("La publicación del catálogo fue enviada a la cola."))

    def action_reconcile(self):
        self.ensure_one()
        self._validate_ready()
        Event = self.env["clover.sync.event"]
        Event.enqueue(self, "in", "catalog_pull", "catalog", self.merchant_id)
        Event.enqueue(self, "out", "stock_push", "stock", str(self.id))
        Event.enqueue(self, "in", "orders_pull", "order", self.merchant_id)
        return self._notification(_("La conciliación fue enviada a la cola."))

    def action_pause(self):
        self.write({"state": "paused"})

    def action_resume(self):
        self._validate_ready()
        self.write({"state": "connected"})

    def _validate_ready(self):
        self.ensure_one()
        missing = []
        for field_name in ("app_id", "merchant_id", "public_base_url", "warehouse_id", "location_id", "pricelist_id", "pos_config_id"):
            if not self[field_name]:
                missing.append(self._fields[field_name].string)
        if not self.access_token_encrypted:
            missing.append(_("Token de acceso"))
        if missing:
            raise UserError(_("Complete la configuración: %s", ", ".join(missing)))

    def _assert_manager(self):
        if not self.env.user.has_group("dreyes_clover_sync.group_clover_manager"):
            raise AccessError(_("Solo un administrador Clover puede realizar esta acción."))

    def _notification(self, message):
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"message": message, "type": "success", "sticky": False}}

    def get_adjustment_product(self, kind):
        self.ensure_one()
        field_name, label, code = {
            "tip": ("tip_product_id", _("Propina Clover"), "CLOVER-TIP"),
            "service": ("service_charge_product_id", _("Cargo de servicio Clover"), "CLOVER-SERVICE"),
            "refund": ("refund_product_id", _("Ajuste de devolución Clover"), "CLOVER-REFUND"),
            "discount": ("discount_product_id", _("Descuento Clover"), "CLOVER-DISCOUNT"),
        }[kind]
        product = self[field_name]
        if not product:
            product = self.env["product.product"].with_company(self.company_id).with_context(clover_inbound=True).create({
                "name": label,
                "default_code": f"{code}-{self.company_id.id}",
                "type": "service",
                "available_in_pos": True,
                "sale_ok": True,
                "company_id": self.company_id.id,
            })
            self[field_name] = product
        return product

    @api.model
    def _cron_nightly_reconcile(self):
        for connector in self.search([("active", "=", True), ("state", "=", "connected")]):
            connector.action_reconcile()
