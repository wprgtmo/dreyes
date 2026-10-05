import hmac
from datetime import timedelta

from werkzeug.exceptions import BadRequest, Forbidden, NotFound
from werkzeug.utils import redirect

from odoo import fields, http
from odoo.http import request


class CloverController(http.Controller):

    @http.route("/clover/oauth/callback", type="http", auth="public", csrf=False, methods=["GET"])
    def oauth_callback(self, code=None, state=None, merchant_id=None, merchantId=None, **kwargs):
        if not code or not state:
            raise BadRequest("Missing OAuth code or state")
        connector = request.env["clover.connector"].sudo().search([
            ("oauth_state", "=", state),
            ("oauth_state_created_at", ">=", fields.Datetime.now() - timedelta(minutes=15)),
        ], limit=1)
        if not connector:
            raise NotFound("Unknown or expired OAuth state")
        connector.exchange_oauth_code(code, merchant_id or merchantId)
        return redirect(f"/web#id={connector.id}&model=clover.connector&view_type=form")

    @http.route("/clover/webhook", type="http", auth="public", csrf=False, methods=["POST"])
    def webhook(self, **kwargs):
        try:
            payload = request.httprequest.get_json(silent=False)
        except Exception as exc:
            raise BadRequest("Invalid JSON") from exc
        app_id = payload.get("appId")
        merchants = payload.get("merchants") or {}
        if not app_id or not isinstance(merchants, dict):
            raise BadRequest("Invalid Clover webhook payload")
        connectors = request.env["clover.connector"].sudo().search([
            ("app_id", "=", app_id), ("merchant_id", "in", list(merchants)), ("active", "=", True)
        ])
        if not connectors:
            raise NotFound("No connector for webhook")
        supplied = request.httprequest.headers.get("X-Clover-Auth", "")
        Event = request.env["clover.sync.event"].sudo()
        for connector in connectors:
            expected = connector._webhook_auth_code() or ""
            if not expected or not hmac.compare_digest(supplied, expected):
                raise Forbidden("Invalid Clover webhook authentication")
            for update in merchants.get(connector.merchant_id, []):
                self._enqueue_update(Event, connector, update)
        return request.make_response("OK", headers=[("Content-Type", "text/plain")], status=200)

    def _enqueue_update(self, Event, connector, update):
        object_id = str(update.get("objectId") or "")
        object_code = object_id.split(":", 1)[0] if ":" in object_id else str(update.get("objectType") or "")
        record_id = object_id.split(":", 1)[-1]
        action = str(update.get("type") or "UPDATE").upper()
        timestamp = str(update.get("ts") or "")
        handlers = {
            "I": ("item_changed", "item"),
            "IC": ("catalog_pull", "category"),
            "IG": ("catalog_pull", "modifier_group"),
            "TAX_RATE": ("catalog_pull", "tax"),
            "O": ("order_changed", "order"),
            "ORDER": ("order_changed", "order"),
        }
        event_type, object_type = handlers.get(object_code, ("orders_pull", "order"))
        if object_code == "I" and action == "DELETE":
            event_type = "item_deleted"
        Event.enqueue(
            connector, "in", event_type, object_type, record_id,
            payload=update,
            dedupe_key=f"webhook:{object_code}:{record_id}:{action}:{timestamp}",
            priority=1,
        )
