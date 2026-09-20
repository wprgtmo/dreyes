import hashlib
import json
import logging
from datetime import timedelta
from datetime import datetime

from odoo import _, api, Command, fields, models, registry, SUPERUSER_ID
from odoo.exceptions import UserError
from psycopg2 import IntegrityError
from requests import HTTPError

_logger = logging.getLogger(__name__)


class CloverSyncEvent(models.Model):
    _name = "clover.sync.event"
    _description = "Evento de sincronización Clover"
    _order = "priority, create_date, id"

    connector_id = fields.Many2one("clover.connector", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="connector_id.company_id", store=True, index=True)
    direction = fields.Selection([("in", "Clover → Odoo"), ("out", "Odoo → Clover")], required=True, index=True)
    event_type = fields.Char(required=True, index=True)
    object_type = fields.Char(required=True, index=True)
    object_id = fields.Char(index=True)
    dedupe_key = fields.Char(required=True, index=True)
    payload = fields.Json(default=dict)
    state = fields.Selection(
        [("pending", "Pendiente"), ("processing", "Procesando"), ("retry", "Reintento"), ("done", "Completado"), ("error", "Error")],
        default="pending",
        required=True,
        index=True,
    )
    priority = fields.Integer(default=10, index=True)
    attempts = fields.Integer(default=0)
    next_retry = fields.Datetime(default=fields.Datetime.now, index=True)
    processed_at = fields.Datetime()
    last_error = fields.Text()

    _sql_constraints = [
        ("event_dedupe_unique", "unique(connector_id, dedupe_key)", "El evento Clover ya fue recibido."),
    ]

    @api.model
    def enqueue(self, connector, direction, event_type, object_type, object_id=False, payload=None, dedupe_key=False, priority=10):
        payload = payload or {}
        if not dedupe_key:
            serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
            raw = f"{direction}|{event_type}|{object_type}|{object_id or ''}|{serialized}"
            dedupe_key = hashlib.sha256(raw.encode()).hexdigest()
        existing = self.search([("connector_id", "=", connector.id), ("dedupe_key", "=", dedupe_key)], limit=1)
        if existing:
            return existing
        try:
            with self.env.cr.savepoint():
                event = self.create({
                    "connector_id": connector.id,
                    "direction": direction,
                    "event_type": event_type,
                    "object_type": object_type,
                    "object_id": str(object_id) if object_id else False,
                    "payload": payload,
                    "dedupe_key": dedupe_key,
                    "priority": priority,
                })
        except IntegrityError:
            return self.search([("connector_id", "=", connector.id), ("dedupe_key", "=", dedupe_key)], limit=1)
        self._wake_worker_after_commit()
        return event

    @api.model
    def _wake_worker_after_commit(self):
        if getattr(self.env.cr, "_clover_worker_scheduled", False):
            return
        self.env.cr._clover_worker_scheduled = True
        dbname = self.env.cr.dbname

        def wake():
            try:
                with registry(dbname).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    cron = env.ref("dreyes_clover_sync.ir_cron_clover_process_events", raise_if_not_found=False)
                    if cron:
                        cron._trigger()
                    cr.commit()
            except Exception:
                _logger.exception("No se pudo despertar el worker Clover")

        self.env.cr.postcommit.add(wake)

    @api.model
    def _cron_process_events(self, limit=50):
        self.env.cr.execute("""
            SELECT event.id
              FROM clover_sync_event AS event
              JOIN clover_connector AS connector ON connector.id = event.connector_id
             WHERE event.state IN ('pending', 'retry')
               AND event.next_retry <= NOW()
               AND connector.state = 'connected'
               AND connector.active IS TRUE
             ORDER BY event.priority, event.create_date, event.id
             FOR UPDATE OF event SKIP LOCKED
             LIMIT %s
        """, [limit])
        for event in self.browse([row[0] for row in self.env.cr.fetchall()]):
            event._process_safely()

    def _process_safely(self):
        self.ensure_one()
        self.write({"state": "processing", "attempts": self.attempts + 1, "last_error": False})
        try:
            with self.env.cr.savepoint():
                self._dispatch()
        except Exception as exc:
            _logger.exception("Error procesando evento Clover %s", self.id)
            self._schedule_retry(exc)
        else:
            self.write({"state": "done", "processed_at": fields.Datetime.now(), "last_error": False})

    def _schedule_retry(self, exc):
        delays = [1, 5, 15, 60]
        if self.attempts >= 10:
            self.write({"state": "error", "last_error": str(exc)[:4000]})
            self.connector_id.write({"last_error": str(exc)[:4000]})
            return
        minutes = delays[self.attempts - 1] if self.attempts <= len(delays) else 360
        self.write({
            "state": "retry",
            "next_retry": fields.Datetime.now() + timedelta(minutes=minutes),
            "last_error": str(exc)[:4000],
        })

    def action_retry(self):
        self.filtered(lambda e: e.state in ("retry", "error")).write({
            "state": "pending", "attempts": 0, "next_retry": fields.Datetime.now(), "last_error": False
        })
        self._wake_worker_after_commit()

    def _dispatch(self):
        self.ensure_one()
        handler = getattr(self, f"_handle_{self.event_type}", None)
        if not handler:
            raise UserError(_("Tipo de evento Clover no soportado: %s", self.event_type))
        return handler()

    def _clover_elements(self, suffix, params=None):
        connector = self.connector_id
        params = dict(params or {})
        params.setdefault("limit", 100)
        offset = 0
        while True:
            params["offset"] = offset
            data = connector.api_request("GET", connector.merchant_path(suffix), params=params)
            elements = data.get("elements", []) if isinstance(data, dict) else []
            yield from elements
            if len(elements) < params["limit"]:
                break
            offset += params["limit"]

    def _handle_catalog_pull(self):
        connector = self.connector_id
        initial = not connector.initial_import_done
        self._import_categories()
        self._import_tax_rates()
        self._import_modifier_groups()
        self._import_tenders()
        imported_products = self.env["product.product"]
        grouped_item_ids = set()
        for group in self._clover_elements("item_groups", {"expand": "items,attributes"}):
            template, item_ids = self._import_item_group(group)
            grouped_item_ids.update(item_ids)
            for item_id in item_ids:
                item = connector.api_request(
                    "GET", connector.merchant_path(f"items/{item_id}"),
                    params={"expand": "categories,taxRates,modifierGroups,options"},
                )
                variant = self._variant_for_item(template, item)
                if variant:
                    self.env["clover.object.map"].bind(connector, "item", item_id, variant)
                imported_products |= self._import_item(item, initial=initial)
        for item in self._clover_elements("items", {"expand": "categories,taxRates,modifierGroups"}):
            if item["id"] in grouped_item_ids:
                continue
            imported_products |= self._import_item(item, initial=initial)
        if initial:
            all_products = self.env["product.product"].with_company(connector.company_id).search([
                ("sale_ok", "=", True), ("company_id", "in", [False, connector.company_id.id]), ("id", "not in", imported_products.ids)
            ])
            Binding = self.env["clover.product.binding"]
            for product in all_products:
                if not Binding.search_count([("connector_id", "=", connector.id), ("product_id", "=", product.id)]):
                    Binding.create({"connector_id": connector.id, "product_id": product.id, "excluded": True})
        connector.write({"initial_import_done": True, "last_catalog_sync": fields.Datetime.now()})

    def _import_item_group(self, data):
        connector = self.connector_id
        Map = self.env["clover.object.map"]
        template = Map.get_record(connector, "item_group", data["id"])
        if not template:
            template = self.env["product.template"].with_company(connector.company_id).with_context(clover_inbound=True).create({
                "name": data.get("name") or data["id"],
                "is_storable": True,
                "available_in_pos": True,
                "company_id": connector.company_id.id,
            })
        else:
            template.with_context(clover_inbound=True).write({"name": data.get("name") or template.name})
        Map.bind(connector, "item_group", data["id"], template)
        line_commands = [Command.clear()]
        attributes = (data.get("attributes") or {}).get("elements", [])
        for attribute_data in attributes:
            attribute = Map.get_record(connector, "attribute", attribute_data["id"])
            if not attribute:
                attribute = self.env["product.attribute"].with_context(clover_inbound=True).create({
                    "name": attribute_data.get("name") or attribute_data["id"], "create_variant": "always"
                })
            Map.bind(connector, "attribute", attribute_data["id"], attribute)
            options = list(self._clover_elements(f"attributes/{attribute_data['id']}/options"))
            values = self.env["product.attribute.value"]
            for option_data in options:
                value = Map.get_record(connector, "option", option_data["id"])
                if not value:
                    value = self.env["product.attribute.value"].with_context(clover_inbound=True).create({
                        "name": option_data.get("name") or option_data["id"], "attribute_id": attribute.id
                    })
                Map.bind(connector, "option", option_data["id"], value)
                values |= value
            if values:
                line_commands.append(Command.create({"attribute_id": attribute.id, "value_ids": [Command.set(values.ids)]}))
        if len(line_commands) > 1:
            template.with_context(clover_inbound=True).write({"attribute_line_ids": line_commands})
        item_ids = [item["id"] for item in (data.get("items") or {}).get("elements", [])]
        return template, item_ids

    def _variant_for_item(self, template, item):
        option_ids = [option["id"] for option in (item.get("options") or {}).get("elements", [])]
        if not option_ids:
            return template.product_variant_id
        values = self.env["product.attribute.value"]
        for option_id in option_ids:
            value = self.env["clover.object.map"].get_record(self.connector_id, "option", option_id)
            if value:
                values |= value
        for variant in template.product_variant_ids:
            variant_values = variant.product_template_attribute_value_ids.product_attribute_value_id
            if values and set(values.ids) == set(variant_values.ids):
                return variant
        return self.env["product.product"]

    def _handle_item_changed(self):
        connector = self.connector_id
        item = connector.api_request("GET", connector.merchant_path(f"items/{self.object_id}"), params={"expand": "categories,taxRates,modifierGroups"})
        self._import_item(item, initial=not connector.initial_import_done)

    def _handle_item_deleted(self):
        binding = self.env["clover.product.binding"].search([
            ("connector_id", "=", self.connector_id.id), ("clover_item_id", "=", self.object_id)
        ], limit=1)
        if not binding:
            return
        binding.write({"excluded": True, "sync_state": "pending", "last_sync": fields.Datetime.now()})
        other_active = self.env["clover.product.binding"].search_count([
            ("product_id", "=", binding.product_id.id), ("excluded", "=", False), ("id", "!=", binding.id)
        ])
        if not other_active:
            binding.product_id.with_context(clover_inbound=True).write({"active": False})

    def _find_product_for_item(self, item):
        connector = self.connector_id
        Map = self.env["clover.object.map"]
        product = Map.get_record(connector, "item", item["id"])
        if product:
            return product
        sku = (item.get("sku") or "").strip()
        barcode = (item.get("code") or "").strip()
        domain = [("company_id", "in", [False, connector.company_id.id])]
        if sku:
            matches = self.env["product.product"].search(domain + [("default_code", "=", sku)], limit=2)
            if len(matches) == 1:
                return matches
        if barcode:
            matches = self.env["product.product"].search(domain + [("barcode", "=", barcode)], limit=2)
            if len(matches) == 1:
                return matches
        return self.env["product.product"]

    def _import_item(self, item, initial=False):
        connector = self.connector_id
        Product = self.env["product.product"].with_company(connector.company_id)
        product = self._find_product_for_item(item)
        existing_product = bool(product)
        incoming = {
            "name": item.get("name") or _("Producto Clover %s", item["id"]),
            "default_code": item.get("sku") or False,
            "barcode": item.get("code") or False,
            "standard_price": (item.get("cost") or 0) / 100.0,
            "available_in_pos": bool(item.get("available", True)),
            "sale_ok": bool(item.get("available", True)),
        }
        if not product:
            product = Product.with_context(clover_inbound=True).create({
                **incoming,
                "is_storable": True,
                "company_id": connector.company_id.id,
            })
        elif initial:
            product.with_context(clover_inbound=True).write(incoming)
        else:
            self._create_item_conflicts(product, item, incoming)
        self.env["clover.object.map"].bind(connector, "item", item["id"], product)
        binding = self.env["clover.product.binding"].search([
            ("connector_id", "=", connector.id), ("product_id", "=", product.id)
        ], limit=1)
        values = {"clover_item_id": item["id"], "last_sync": fields.Datetime.now(), "sync_state": "synced", "last_error": False}
        binding.write(values) if binding else self.env["clover.product.binding"].create({**values, "connector_id": connector.id, "product_id": product.id})
        incoming_price = (item.get("price") or 0) / 100.0
        if initial or not existing_product:
            self._set_pricelist_price(product, incoming_price)
        elif abs(self._product_price(product) - incoming_price) > 0.00001:
            self._create_conflict(product, item["id"], "__clover_price__", self._product_price(product), incoming_price, incoming_price)
        self._pull_item_stock(product, item["id"])
        self._link_item_categories(product, item, apply=initial or not existing_product)
        self._link_item_taxes(product, item, apply=initial or not existing_product)
        self._link_item_modifiers(product, item, apply=initial or not existing_product)
        return product

    def _create_item_conflicts(self, product, item, incoming):
        connector = self.connector_id
        Conflict = self.env["clover.sync.conflict"]
        for field_name, clover_value in incoming.items():
            current = product[field_name]
            if isinstance(current, models.BaseModel):
                current = current.id
            if current != clover_value and not (isinstance(current, float) and abs(current - clover_value) < 0.00001):
                self._create_conflict(product, item["id"], field_name, current, clover_value, clover_value)

    def _create_conflict(self, product, clover_id, field_name, odoo_value, clover_value, payload_value):
        Conflict = self.env["clover.sync.conflict"]
        existing = Conflict.search_count([
            ("connector_id", "=", self.connector_id.id), ("object_type", "=", "item"),
            ("clover_id", "=", clover_id), ("field_name", "=", field_name), ("state", "=", "open")
        ])
        if not existing:
            Conflict.create({
                "connector_id": self.connector_id.id,
                "object_type": "item",
                "clover_id": clover_id,
                "odoo_model": product._name,
                "odoo_res_id": product.id,
                "field_name": field_name,
                "odoo_value": str(odoo_value),
                "clover_value": str(clover_value),
                "payload": {"value": payload_value},
            })

    def _set_pricelist_price(self, product, price):
        connector = self.connector_id
        Item = self.env["product.pricelist.item"]
        line = Item.search([("pricelist_id", "=", connector.pricelist_id.id), ("product_id", "=", product.id)], limit=1)
        values = {"fixed_price": price, "compute_price": "fixed"}
        line.with_context(clover_inbound=True).write(values) if line else Item.with_context(clover_inbound=True).create({
            **values, "pricelist_id": connector.pricelist_id.id, "product_id": product.id, "applied_on": "0_product_variant"
        })

    def _pull_item_stock(self, product, item_id):
        connector = self.connector_id
        stock = connector.api_request("GET", connector.merchant_path(f"item_stocks/{item_id}"))
        if "quantity" not in stock:
            return
        target = float(stock["quantity"] or 0)
        self._apply_stock_difference(product, target)

    def _apply_stock_difference(self, product, target):
        connector = self.connector_id
        locations = self.env["stock.location"].search([("id", "child_of", connector.location_id.id), ("usage", "=", "internal")])
        quants = self.env["stock.quant"].search([("product_id", "=", product.id), ("location_id", "in", locations.ids)])
        current = sum(quants.mapped("quantity"))
        difference = target - current
        if abs(difference) < product.uom_id.rounding:
            return
        inventory_location = self.env["stock.location"].search([
            ("usage", "=", "inventory"), ("company_id", "in", [False, connector.company_id.id])
        ], limit=1)
        if not inventory_location:
            raise UserError(_("No existe una ubicación de ajuste de inventario."))
        source, destination = (inventory_location, connector.location_id) if difference > 0 else (connector.location_id, inventory_location)
        move = self.env["stock.move"].with_context(clover_inbound=True).create({
            "name": _("Ajuste Clover %s", self.object_id or product.display_name),
            "origin": f"Clover:{self.object_id or product.id}",
            "product_id": product.id,
            "product_uom_qty": abs(difference),
            "product_uom": product.uom_id.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "company_id": connector.company_id.id,
            "is_inventory": True,
        })
        move._action_confirm()
        move.quantity = abs(difference)
        move.picked = True
        move._action_done()

    def _link_item_categories(self, product, item, apply=True):
        elements = (item.get("categories") or {}).get("elements", [])
        if not elements:
            return
        category = self.env["clover.object.map"].get_record(self.connector_id, "category", elements[0].get("id"))
        if category:
            if apply:
                product.with_context(clover_inbound=True).write({"categ_id": category.id})
            elif product.categ_id != category:
                self._create_conflict(product, item["id"], "categ_id", product.categ_id.display_name, category.display_name, category.id)

    def _link_item_taxes(self, product, item, apply=True):
        taxes = self.env["account.tax"]
        for tax_data in (item.get("taxRates") or {}).get("elements", []):
            tax = self.env["clover.object.map"].get_record(self.connector_id, "tax", tax_data.get("id"))
            if tax:
                taxes |= tax
        if taxes:
            if apply:
                product.with_context(clover_inbound=True).write({"taxes_id": [Command.set(taxes.ids)]})
            elif set(product.taxes_id.ids) != set(taxes.ids):
                self._create_conflict(product, item["id"], "taxes_id", product.taxes_id.mapped("name"), taxes.mapped("name"), taxes.ids)

    def _link_item_modifiers(self, product, item, apply=True):
        if not apply:
            return
        group_ids = [group.get("id") for group in (item.get("modifierGroups") or {}).get("elements", [])]
        groups = self.env["clover.modifier.group"].search([
            ("connector_id", "=", self.connector_id.id), ("clover_id", "in", group_ids)
        ])
        for group in groups:
            if product.product_tmpl_id not in group.product_ids:
                group.with_context(clover_inbound=True).write({"product_ids": [Command.link(product.product_tmpl_id.id)]})

    def _import_categories(self):
        connector = self.connector_id
        for data in self._clover_elements("categories"):
            category = self.env["clover.object.map"].get_record(connector, "category", data["id"])
            if category:
                category.with_context(clover_inbound=True).write({"name": data.get("name") or category.name})
            else:
                category = self.env["product.category"].with_context(clover_inbound=True).create({"name": data.get("name") or data["id"]})
            self.env["clover.object.map"].bind(connector, "category", data["id"], category)

    def _import_tax_rates(self):
        connector = self.connector_id
        for data in self._clover_elements("tax_rates"):
            tax = self.env["clover.object.map"].get_record(connector, "tax", data["id"])
            rate = float(data.get("rate") or 0) / 100000.0
            values = {"name": data.get("name") or data["id"], "amount": rate, "amount_type": "percent", "type_tax_use": "sale", "company_id": connector.company_id.id}
            tax.with_context(clover_inbound=True).write(values) if tax else None
            if not tax:
                tax = self.env["account.tax"].with_context(clover_inbound=True).create(values)
            self.env["clover.object.map"].bind(connector, "tax", data["id"], tax)

    def _import_modifier_groups(self):
        connector = self.connector_id
        Group = self.env["clover.modifier.group"]
        for data in self._clover_elements("modifier_groups", {"expand": "modifiers,items"}):
            group = Group.search([("connector_id", "=", connector.id), ("clover_id", "=", data["id"])], limit=1)
            values = {"name": data.get("name") or data["id"], "min_required": data.get("minRequired") or 0, "max_allowed": data.get("maxAllowed") or 0}
            group.with_context(clover_inbound=True).write(values) if group else None
            if not group:
                group = Group.with_context(clover_inbound=True).create({**values, "connector_id": connector.id, "clover_id": data["id"]})
            for modifier in (data.get("modifiers") or {}).get("elements", []):
                existing = self.env["clover.modifier"].search([("group_id", "=", group.id), ("clover_id", "=", modifier["id"])], limit=1)
                mod_values = {"name": modifier.get("name") or modifier["id"], "price": (modifier.get("price") or 0) / 100.0, "available": bool(modifier.get("available", True))}
                existing.with_context(clover_inbound=True).write(mod_values) if existing else self.env["clover.modifier"].with_context(clover_inbound=True).create({**mod_values, "group_id": group.id, "clover_id": modifier["id"]})

    def _import_tenders(self):
        connector = self.connector_id
        Tender = self.env["clover.tender.map"]
        for data in self._clover_elements("tenders"):
            mapping = Tender.search([("connector_id", "=", connector.id), ("clover_tender_id", "=", data["id"])], limit=1)
            values = {"clover_label": data.get("label") or data.get("name") or data["id"], "active": bool(data.get("enabled", True))}
            mapping.write(values) if mapping else Tender.create({
                **values, "connector_id": connector.id, "clover_tender_id": data["id"]
            })

    def _handle_catalog_push(self):
        self._push_modifier_groups()
        products = self.env["product.product"].with_company(self.connector_id.company_id).search([
            ("sale_ok", "=", True), ("company_id", "in", [False, self.connector_id.company_id.id])
        ])
        for product in products:
            self._push_product(product)
        self.connector_id.last_catalog_sync = fields.Datetime.now()

    def _handle_item_push(self):
        product = False
        if self.payload.get("odoo_model") and self.payload.get("odoo_res_id"):
            product = self.env[self.payload["odoo_model"]].browse(self.payload["odoo_res_id"]).exists()
        if not product:
            product = self.env["clover.object.map"].get_record(self.connector_id, "item", self.object_id)
        if product._name == "product.template":
            product = product.product_variant_id
        if product:
            self._push_product(product)

    def _product_price(self, product):
        return self.connector_id.pricelist_id._get_product_price(product, 1.0)

    def _push_product(self, product):
        connector = self.connector_id
        binding = self.env["clover.product.binding"].search([
            ("connector_id", "=", connector.id), ("product_id", "=", product.id)
        ], limit=1)
        if binding and binding.excluded:
            return
        payload = {
            "name": product.name,
            "sku": product.default_code or "",
            "code": product.barcode or "",
            "price": round(self._product_price(product) * 100),
            "cost": round(product.standard_price * 100),
            "available": bool(product.active and product.sale_ok and product.available_in_pos),
            "unitName": product.uom_id.name,
        }
        payload.update(self._variant_payload(product))
        payload.update(self._category_tax_payload(product))
        modifier_groups = self.env["clover.modifier.group"].search([
            ("connector_id", "=", connector.id), ("product_ids", "in", product.product_tmpl_id.id), ("clover_id", "!=", False)
        ])
        if modifier_groups:
            payload["modifierGroups"] = [{"id": group.clover_id} for group in modifier_groups]
        if binding and binding.clover_item_id:
            data = connector.api_request("POST", connector.merchant_path(f"items/{binding.clover_item_id}"), payload=payload)
            clover_id = binding.clover_item_id
        else:
            data = connector.api_request("POST", connector.merchant_path("items"), payload=payload)
            clover_id = data.get("id")
            if not clover_id:
                raise UserError(_("Clover no devolvió el ID del producto %s", product.display_name))
            binding = self.env["clover.product.binding"].create({"connector_id": connector.id, "product_id": product.id, "clover_item_id": clover_id})
        binding.write({"sync_state": "synced", "last_sync": fields.Datetime.now(), "last_error": False})
        self.env["clover.object.map"].bind(connector, "item", clover_id, product)
        self._push_product_stock(product, clover_id)

    def _variant_payload(self, product):
        template = product.product_tmpl_id
        if len(template.product_variant_ids) <= 1 or not template.attribute_line_ids:
            return {}
        connector = self.connector_id
        Map = self.env["clover.object.map"]
        group_map = Map.find_odoo(connector, "item_group", template)
        if not group_map:
            group_data = connector.api_request("POST", connector.merchant_path("item_groups"), payload={"name": template.name})
            group_map = Map.bind(connector, "item_group", group_data["id"], template)
        option_refs = []
        for ptav in product.product_template_attribute_value_ids:
            attribute = ptav.attribute_id
            value = ptav.product_attribute_value_id
            attribute_map = Map.find_odoo(connector, "attribute", attribute)
            if not attribute_map:
                result = connector.api_request("POST", connector.merchant_path("attributes"), payload={
                    "name": attribute.name, "itemGroup": {"id": group_map.clover_id}
                })
                attribute_map = Map.bind(connector, "attribute", result["id"], attribute)
            option_map = Map.find_odoo(connector, "option", value)
            if not option_map:
                result = connector.api_request(
                    "POST", connector.merchant_path(f"attributes/{attribute_map.clover_id}/options"), payload={"name": value.name}
                )
                option_map = Map.bind(connector, "option", result["id"], value)
            option_refs.append({"id": option_map.clover_id})
        return {"itemGroup": {"id": group_map.clover_id}, "options": option_refs}

    def _category_tax_payload(self, product):
        connector = self.connector_id
        Map = self.env["clover.object.map"]
        category_map = Map.find_odoo(connector, "category", product.categ_id)
        if not category_map:
            result = connector.api_request("POST", connector.merchant_path("categories"), payload={"name": product.categ_id.complete_name})
            category_map = Map.bind(connector, "category", result["id"], product.categ_id)
        tax_refs = []
        for tax in product.taxes_id.filtered(lambda t: not t.company_id or t.company_id == connector.company_id):
            tax_map = Map.find_odoo(connector, "tax", tax)
            if not tax_map:
                result = connector.api_request("POST", connector.merchant_path("tax_rates"), payload={
                    "name": tax.name, "rate": round(tax.amount * 100000), "isDefault": False
                })
                tax_map = Map.bind(connector, "tax", result["id"], tax)
            tax_refs.append({"id": tax_map.clover_id})
        return {"categories": [{"id": category_map.clover_id}], "taxRates": tax_refs, "defaultTaxRates": not bool(tax_refs)}

    def _stock_quantity(self, product):
        locations = self.env["stock.location"].search([("id", "child_of", self.connector_id.location_id.id), ("usage", "=", "internal")])
        return sum(self.env["stock.quant"].search([
            ("product_id", "=", product.id), ("location_id", "in", locations.ids)
        ]).mapped("quantity"))

    def _push_product_stock(self, product, clover_id):
        path = self.connector_id.merchant_path(f"item_stocks/{clover_id}")
        payload = {"quantity": self._stock_quantity(product)}
        try:
            self.connector_id.api_request("PUT", path, payload=payload)
        except HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
            self.connector_id.api_request("POST", path, payload=payload)

    def _push_modifier_groups(self):
        connector = self.connector_id
        groups = self.env["clover.modifier.group"].search([("connector_id", "=", connector.id)])
        for group in groups:
            payload = {"name": group.name, "minRequired": group.min_required, "maxAllowed": group.max_allowed}
            if group.clover_id:
                connector.api_request("POST", connector.merchant_path(f"modifier_groups/{group.clover_id}"), payload=payload)
            else:
                result = connector.api_request("POST", connector.merchant_path("modifier_groups"), payload=payload)
                group.with_context(clover_inbound=True).clover_id = result["id"]
            for modifier in group.modifier_ids:
                modifier_payload = {
                    "name": modifier.name, "price": round(modifier.price * 100), "available": modifier.available,
                    "modifierGroup": {"id": group.clover_id},
                }
                if modifier.clover_id:
                    path = f"modifier_groups/{group.clover_id}/modifiers/{modifier.clover_id}"
                else:
                    path = f"modifier_groups/{group.clover_id}/modifiers"
                result = connector.api_request("POST", connector.merchant_path(path), payload=modifier_payload)
                if not modifier.clover_id:
                    modifier.with_context(clover_inbound=True).clover_id = result["id"]

    def _handle_modifiers_push(self):
        self._push_modifier_groups()

    def _handle_stock_push(self):
        domain = [
            ("connector_id", "=", self.connector_id.id), ("excluded", "=", False), ("clover_item_id", "!=", False)
        ]
        if self.payload.get("product_ids"):
            domain.append(("product_id", "in", self.payload["product_ids"]))
        bindings = self.env["clover.product.binding"].search(domain)
        for binding in bindings:
            self._push_product_stock(binding.product_id, binding.clover_item_id)
        self.connector_id.last_stock_sync = fields.Datetime.now()

    def _handle_stock_changed(self):
        product = self.env["clover.object.map"].get_record(self.connector_id, "item", self.object_id)
        if product:
            self._pull_item_stock(product, self.object_id)

    def _handle_orders_pull(self):
        params = {"expand": "lineItems,payments,refunds,discounts"}
        if self.connector_id.backfill_from:
            params["filter"] = f"createdTime>={int(self.connector_id.backfill_from.timestamp() * 1000)}"
        for order in self._clover_elements("orders", params):
            self._import_order(order)
        self.connector_id.last_order_sync = fields.Datetime.now()

    def _handle_order_changed(self):
        order = self.connector_id.api_request(
            "GET", self.connector_id.merchant_path(f"orders/{self.object_id}"),
            params={"expand": "lineItems,payments,refunds,discounts,customers"},
        )
        self._import_order(order)

    def _get_open_session(self):
        config = self.connector_id.pos_config_id
        session = self.env["pos.session"].search([("config_id", "=", config.id), ("state", "in", ["opening_control", "opened"])], limit=1)
        if not session:
            session = self.env["pos.session"].create({"config_id": config.id, "user_id": self.env.user.id})
            session.set_opening_control(0, "Apertura automática para importación Clover")
        return session

    def _import_order(self, data):
        connector = self.connector_id
        Map = self.env["clover.object.map"]
        existing = Map.get_record(connector, "order", data["id"])
        if existing:
            for payment in (data.get("payments") or {}).get("elements", []):
                self._import_payment(existing, payment)
            for refund in (data.get("refunds") or {}).get("elements", []):
                self._import_refund(existing, refund)
            return existing
        session = self._get_open_session()
        partner = self._order_partner(data)
        order = self.env["pos.order"].with_context(clover_inbound=True).create({
            "name": f"Clover {data.get('orderNumber') or data['id']}",
            "pos_reference": f"CLOVER-{data['id']}",
            "session_id": session.id,
            "config_id": connector.pos_config_id.id,
            "partner_id": partner.id if partner else False,
            "date_order": self._from_milliseconds(data.get("createdTime")),
            "to_invoice": bool(data.get("invoiceRequested")) and bool(partner),
            "clover_connector_id": connector.id,
            "clover_order_id": data["id"],
            "clover_sync_state": "pending",
        })
        for line in (data.get("lineItems") or {}).get("elements", []):
            self._import_order_line(order, line)
        order_discount = sum(abs(float(d.get("amount") or 0)) for d in (data.get("discounts") or {}).get("elements", [])) / 100.0
        if order_discount:
            self._create_adjustment_line(order, "discount", -order_discount)
        service_charge = data.get("serviceCharge") or {}
        if service_charge.get("amount"):
            self._create_adjustment_line(order, "service", float(service_charge["amount"]) / 100.0)
        total_tip = sum(float(p.get("tipAmount") or 0) for p in (data.get("payments") or {}).get("elements", [])) / 100.0
        if total_tip:
            self._create_adjustment_line(order, "tip", total_tip)
        for payment in (data.get("payments") or {}).get("elements", []):
            self._import_payment(order, payment)
        Map.bind(connector, "order", data["id"], order)
        expected = float(data.get("total") or 0) / 100.0 + total_tip
        if abs(order.amount_total - expected) > 0.01:
            order.write({"clover_sync_state": "exception", "clover_error": _("Diferencia superior a un centavo")})
            raise UserError(_("El pedido Clover %s difiere de Odoo en más de un centavo.", data["id"]))
        if order.payment_ids and abs(sum(order.payment_ids.mapped("amount")) - order.amount_total) <= 0.01:
            order.action_pos_order_paid()
            if order.to_invoice:
                order._generate_pos_order_invoice()
        order.write({"clover_sync_state": "synced", "clover_last_sync": fields.Datetime.now(), "clover_error": False})
        for refund in (data.get("refunds") or {}).get("elements", []):
            self._import_refund(order, refund)
        return order

    def _from_milliseconds(self, value):
        return datetime.utcfromtimestamp(float(value) / 1000.0) if value else fields.Datetime.now()

    def _create_adjustment_line(self, order, kind, amount):
        product = self.connector_id.get_adjustment_product(kind)
        return self.env["pos.order.line"].with_context(clover_inbound=True).create({
            "order_id": order.id, "product_id": product.id, "qty": 1, "price_unit": amount,
        })

    def _import_order_line(self, order, data):
        item_id = (data.get("item") or {}).get("id")
        product = self.env["clover.object.map"].get_record(self.connector_id, "item", item_id)
        if not product:
            raise UserError(_("El producto Clover %s no está mapeado.", item_id))
        price = float(data.get("price") or 0) / 100.0
        quantity = float(data.get("unitQty") or 1000) / 1000.0
        discount_total = sum(float(d.get("amount") or 0) for d in (data.get("discounts") or {}).get("elements", [])) / 100.0
        discount = (discount_total / (price * quantity) * 100.0) if price and quantity else 0
        self.env["pos.order.line"].with_context(clover_inbound=True).create({
            "order_id": order.id, "product_id": product.id, "qty": quantity, "price_unit": price, "discount": discount,
        })

    def _import_payment(self, order, data):
        if self.env["clover.object.map"].get_record(self.connector_id, "payment", data["id"]):
            return
        tender = data.get("tender") or {}
        mapping = self.env["clover.tender.map"].search([
            ("connector_id", "=", self.connector_id.id), ("clover_tender_id", "=", tender.get("id")), ("active", "=", True)
        ], limit=1)
        if not mapping or not mapping.payment_method_id:
            raise UserError(_("Falta mapear el tender Clover %s.", tender.get("label") or tender.get("id")))
        amount = (float(data.get("amount") or 0) + float(data.get("tipAmount") or 0)) / 100.0
        payment = self.env["pos.payment"].with_context(clover_inbound=True).create({
            "pos_order_id": order.id,
            "payment_method_id": mapping.payment_method_id.id,
            "amount": amount,
            "payment_date": self._from_milliseconds(data.get("createdTime")),
        })
        self.env["clover.object.map"].bind(self.connector_id, "payment", data["id"], payment)

    def _import_refund(self, original_order, data):
        Map = self.env["clover.object.map"]
        if Map.get_record(self.connector_id, "refund", data["id"]):
            return
        amount = float(data.get("amount") or 0) / 100.0
        if not amount:
            return
        refund_order = self.env["pos.order"].with_context(clover_inbound=True).create({
            "name": f"Clover Refund {data['id']}",
            "pos_reference": f"CLOVER-REFUND-{data['id']}",
            "session_id": original_order.session_id.id,
            "config_id": original_order.config_id.id,
            "partner_id": original_order.partner_id.id,
            "date_order": self._from_milliseconds(data.get("createdTime")),
            "clover_connector_id": self.connector_id.id,
            "clover_order_id": f"refund:{data['id']}",
            "clover_sync_state": "pending",
        })
        product = self.connector_id.get_adjustment_product("refund")
        self.env["pos.order.line"].with_context(clover_inbound=True).create({
            "order_id": refund_order.id, "product_id": product.id, "qty": -1, "price_unit": amount,
        })
        payment = original_order.payment_ids[:1]
        if payment:
            self.env["pos.payment"].with_context(clover_inbound=True).create({
                "pos_order_id": refund_order.id, "payment_method_id": payment.payment_method_id.id,
                "amount": -amount, "payment_date": self._from_milliseconds(data.get("createdTime")),
            })
            refund_order.action_pos_order_paid()
        refund_order.write({"clover_sync_state": "synced", "clover_last_sync": fields.Datetime.now()})
        Map.bind(self.connector_id, "refund", data["id"], refund_order)

    def _order_partner(self, data):
        customers = (data.get("customers") or {}).get("elements", [])
        if not customers:
            return self.connector_id.anonymous_partner_id
        customer = customers[0]
        partner = self.env["clover.object.map"].get_record(self.connector_id, "customer", customer["id"])
        if partner:
            return partner
        email = customer.get("emailAddress") or False
        phone = customer.get("phoneNumber") or False
        partner = self.env["res.partner"].with_context(clover_inbound=True).create({
            "name": customer.get("firstName") or customer.get("lastName") or _("Cliente Clover"),
            "email": email,
            "phone": phone,
            "company_id": self.connector_id.company_id.id,
        })
        self.env["clover.object.map"].bind(self.connector_id, "customer", customer["id"], partner)
        return partner
