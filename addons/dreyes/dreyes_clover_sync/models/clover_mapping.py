from odoo import _, api, Command, fields, models
from odoo.exceptions import ValidationError


class CloverObjectMap(models.Model):
    _name = "clover.object.map"
    _description = "Asociación de objeto Clover"
    _order = "object_type, clover_id"

    connector_id = fields.Many2one("clover.connector", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="connector_id.company_id", store=True, index=True)
    object_type = fields.Selection(
        [
            ("item", "Producto"),
            ("item_group", "Grupo de variantes"),
            ("attribute", "Atributo"),
            ("option", "Opción"),
            ("category", "Categoría"),
            ("tax", "Impuesto"),
            ("customer", "Cliente"),
            ("order", "Pedido"),
            ("payment", "Pago"),
            ("refund", "Devolución"),
            ("modifier_group", "Grupo de modificadores"),
            ("modifier", "Modificador"),
        ],
        required=True,
        index=True,
    )
    clover_id = fields.Char(required=True, index=True)
    odoo_model = fields.Char(required=True, index=True)
    odoo_res_id = fields.Integer(required=True, index=True)
    clover_modified_time = fields.Datetime()
    last_sync = fields.Datetime(default=fields.Datetime.now)
    checksum = fields.Char(index=True)

    _sql_constraints = [
        ("clover_object_unique", "unique(connector_id, object_type, clover_id)", "El objeto Clover ya está asociado."),
        ("odoo_object_unique", "unique(connector_id, object_type, odoo_model, odoo_res_id)", "El registro Odoo ya está asociado a otro objeto Clover."),
    ]

    def odoo_record(self):
        self.ensure_one()
        if self.odoo_model not in self.env:
            return self.env["ir.model"].browse()
        return self.env[self.odoo_model].browse(self.odoo_res_id).exists()

    @api.model
    def get_record(self, connector, object_type, clover_id):
        mapping = self.search([
            ("connector_id", "=", connector.id),
            ("object_type", "=", object_type),
            ("clover_id", "=", str(clover_id)),
        ], limit=1)
        return mapping.odoo_record() if mapping else self.env["ir.model"].browse()

    @api.model
    def bind(self, connector, object_type, clover_id, record, checksum=False):
        mapping = self.search([
            ("connector_id", "=", connector.id),
            ("object_type", "=", object_type),
            ("clover_id", "=", str(clover_id)),
        ], limit=1)
        values = {
            "odoo_model": record._name,
            "odoo_res_id": record.id,
            "last_sync": fields.Datetime.now(),
            "checksum": checksum or False,
        }
        if mapping:
            mapping.write(values)
        else:
            values.update({"connector_id": connector.id, "object_type": object_type, "clover_id": str(clover_id)})
            mapping = self.create(values)
        return mapping

    @api.model
    def find_odoo(self, connector, object_type, record):
        return self.search([
            ("connector_id", "=", connector.id),
            ("object_type", "=", object_type),
            ("odoo_model", "=", record._name),
            ("odoo_res_id", "=", record.id),
        ], limit=1)


class CloverProductBinding(models.Model):
    _name = "clover.product.binding"
    _description = "Configuración de producto por Clover"
    _order = "connector_id, product_id"

    connector_id = fields.Many2one("clover.connector", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="connector_id.company_id", store=True, index=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade", index=True)
    clover_item_id = fields.Char(index=True, copy=False)
    excluded = fields.Boolean(help="No publicar este producto en esta conexión Clover.")
    last_sync = fields.Datetime(copy=False)
    sync_state = fields.Selection(
        [("pending", "Pendiente"), ("synced", "Sincronizado"), ("conflict", "Conflicto"), ("error", "Error")],
        default="pending",
    )
    last_error = fields.Text(copy=False)

    _sql_constraints = [
        ("connector_product_unique", "unique(connector_id, product_id)", "El producto ya tiene configuración para esta conexión."),
        ("connector_item_unique", "unique(connector_id, clover_item_id)", "El Item ID ya está asociado en esta conexión."),
    ]


class CloverTenderMap(models.Model):
    _name = "clover.tender.map"
    _description = "Mapeo de método de pago Clover"
    _order = "connector_id, clover_label"

    connector_id = fields.Many2one("clover.connector", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="connector_id.company_id", store=True, index=True)
    clover_tender_id = fields.Char(required=True, index=True)
    clover_label = fields.Char(required=True)
    payment_method_id = fields.Many2one("pos.payment.method")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("connector_tender_unique", "unique(connector_id, clover_tender_id)", "El tender Clover ya está mapeado."),
    ]

    @api.constrains("payment_method_id", "connector_id")
    def _check_payment_method(self):
        for mapping in self:
            if mapping.payment_method_id and mapping.payment_method_id not in mapping.connector_id.pos_config_id.payment_method_ids:
                raise ValidationError(_("El método de pago debe estar habilitado en el POS de la conexión."))


class CloverModifierGroup(models.Model):
    _name = "clover.modifier.group"
    _description = "Grupo de modificadores Clover"

    connector_id = fields.Many2one("clover.connector", required=True, ondelete="cascade", index=True)
    clover_id = fields.Char(index=True)
    name = fields.Char(required=True)
    product_ids = fields.Many2many("product.template", string="Productos")
    modifier_ids = fields.One2many("clover.modifier", "group_id")
    min_required = fields.Integer()
    max_allowed = fields.Integer()

    _sql_constraints = [("connector_group_unique", "unique(connector_id, clover_id)", "El grupo ya existe.")]

    @api.model_create_multi
    def create(self, vals_list):
        groups = super().create(vals_list)
        groups._enqueue_clover_change()
        return groups

    def write(self, vals):
        result = super().write(vals)
        if {"name", "min_required", "max_allowed", "product_ids"}.intersection(vals):
            self._enqueue_clover_change()
        return result

    def _enqueue_clover_change(self):
        if self.env.context.get("clover_inbound") or not self.env.registry.ready:
            return
        for group in self.filtered(lambda g: g.connector_id.state == "connected" and g.connector_id.active):
            self.env["clover.sync.event"].sudo().enqueue(
                group.connector_id, "out", "modifiers_push", "modifier_group", group.clover_id or str(group.id),
                payload={"group_id": group.id}, dedupe_key=f"modifier-group:{group.id}:{fields.Datetime.now()}"
            )


class CloverModifier(models.Model):
    _name = "clover.modifier"
    _description = "Modificador Clover"

    group_id = fields.Many2one("clover.modifier.group", required=True, ondelete="cascade", index=True)
    connector_id = fields.Many2one(related="group_id.connector_id", store=True, index=True)
    clover_id = fields.Char(index=True)
    name = fields.Char(required=True)
    price = fields.Monetary()
    currency_id = fields.Many2one(related="connector_id.pricelist_id.currency_id")
    available = fields.Boolean(default=True)

    _sql_constraints = [("group_modifier_unique", "unique(group_id, clover_id)", "El modificador ya existe.")]

    @api.model_create_multi
    def create(self, vals_list):
        modifiers = super().create(vals_list)
        modifiers.mapped("group_id")._enqueue_clover_change()
        return modifiers

    def write(self, vals):
        result = super().write(vals)
        if {"name", "price", "available", "group_id"}.intersection(vals):
            self.mapped("group_id")._enqueue_clover_change()
        return result


class CloverSyncConflict(models.Model):
    _name = "clover.sync.conflict"
    _description = "Conflicto de sincronización Clover"
    _order = "create_date desc"

    connector_id = fields.Many2one("clover.connector", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="connector_id.company_id", store=True, index=True)
    object_type = fields.Char(required=True, index=True)
    clover_id = fields.Char(required=True, index=True)
    odoo_model = fields.Char(required=True)
    odoo_res_id = fields.Integer(required=True)
    field_name = fields.Char(required=True)
    odoo_value = fields.Text()
    clover_value = fields.Text()
    payload = fields.Json()
    state = fields.Selection(
        [("open", "Abierto"), ("accepted", "Aceptado en Odoo"), ("restored", "Restaurado en Clover")],
        default="open",
        required=True,
        index=True,
    )
    resolved_by = fields.Many2one("res.users", readonly=True)
    resolved_at = fields.Datetime(readonly=True)

    def action_accept_clover(self):
        for conflict in self.filtered(lambda c: c.state == "open"):
            record = self.env[conflict.odoo_model].browse(conflict.odoo_res_id).exists()
            if record:
                value = conflict.payload.get("value")
                if conflict.field_name == "__clover_price__":
                    event = self.env["clover.sync.event"].new({"connector_id": conflict.connector_id.id})
                    event._set_pricelist_price(record, float(value))
                elif conflict.field_name == "taxes_id":
                    record.with_context(clover_inbound=True).write({"taxes_id": [Command.set(value)]})
                else:
                    record.with_context(clover_inbound=True).write({conflict.field_name: value})
            conflict.write({"state": "accepted", "resolved_by": self.env.user.id, "resolved_at": fields.Datetime.now()})

    def action_restore_clover(self):
        for conflict in self.filtered(lambda c: c.state == "open"):
            self.env["clover.sync.event"].enqueue(
                conflict.connector_id, "out", "item_push", conflict.object_type, conflict.clover_id,
                payload={"odoo_model": conflict.odoo_model, "odoo_res_id": conflict.odoo_res_id},
                dedupe_key=f"restore:{conflict.id}",
            )
            conflict.write({"state": "restored", "resolved_by": self.env.user.id, "resolved_at": fields.Datetime.now()})
