import math
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    dreyes_pricing_product_count = fields.Integer(
        string="Productos", compute="_compute_dreyes_pricing_product_count"
    )

    def _dreyes_product_domain(self, sale_only=False):
        domain = [
            ("active", "=", True),
            ("company_id", "in", [False, self.env.company.id]),
        ]
        if sale_only:
            domain.append(("sale_ok", "=", True))
        return domain

    @api.depends_context("company", "uid")
    def _compute_dreyes_pricing_product_count(self):
        Product = self.env["product.product"]
        count = (
            Product.search_count(self._dreyes_product_domain(sale_only=True))
            if Product.has_access("read")
            else 0
        )
        for pricelist in self:
            pricelist.dreyes_pricing_product_count = count

    def action_dreyes_pricing_products(self):
        self.ensure_one()
        self._dreyes_check_internal_user()
        self.check_access("read")
        self._dreyes_validate_pricelist()
        return {
            "type": "ir.actions.client",
            "tag": "dreyes_product_pricing.catalog",
            "name": _("Productos: %s", self.display_name),
            "params": {"source_model": self._name, "source_id": self.id},
        }

    def _dreyes_validate_pricelist(self):
        self.ensure_one()
        if not self.active or (self.company_id and self.company_id != self.env.company):
            raise UserError(_("Seleccione una lista activa de la compañía actual o una lista compartida."))

    @api.model
    def _dreyes_check_internal_user(self):
        if not self.env.user.has_group("base.group_user"):
            raise AccessError(_("La consulta de precios está disponible solo para usuarios internos."))

    @api.model
    def _dreyes_query_context(self, quantity, date):
        try:
            if isinstance(quantity, bool):
                raise ValueError
            quantity = float(quantity)
            if not math.isfinite(quantity) or quantity <= 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ValidationError(_("La cantidad debe ser un número mayor que cero."))
        try:
            date = fields.Date.to_date(date) if date else fields.Date.context_today(self)
            if not date:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ValidationError(_("Seleccione una fecha válida."))
        return quantity, date

    @api.model
    def _dreyes_scope(self, source_model, source_id):
        if source_model not in ("product.template", "product.product", "product.pricelist"):
            raise ValidationError(_("Origen de consulta no válido."))
        if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id <= 0:
            raise ValidationError(_("Guarde el registro antes de consultar sus precios."))
        source = self.env[source_model].browse(source_id).exists()
        if not source:
            raise UserError(_("El registro ya no existe."))
        source.check_access("read")
        product_domain = self._dreyes_product_domain(sale_only=source_model == self._name)
        if source_model == self._name:
            source._dreyes_validate_pricelist()
            pricelists = source
        else:
            if source.company_id and source.company_id != self.env.company:
                raise UserError(_("Cambie a la compañía del producto para consultar sus precios."))
            product_domain.append(
                ("product_tmpl_id", "=", source.id)
                if source_model == "product.template"
                else ("id", "=", source.id)
            )
            pricelists = self.search([
                ("active", "=", True),
                ("company_id", "in", [False, self.env.company.id]),
            ], order="name, id")
        return pricelists, product_domain

    @api.model
    def _dreyes_fixed_rule_domain(self, pricelist_ids, product_ids):
        return [
            ("pricelist_id", "in", pricelist_ids),
            ("product_id", "in", product_ids),
            ("applied_on", "=", "0_product_variant"),
            ("compute_price", "=", "fixed"),
            ("min_quantity", "=", 1.0),
            ("date_start", "=", False),
            ("date_end", "=", False),
        ]

    @api.model
    def _dreyes_price_rows(self, pricelist, products, quantity, date):
        Item = self.env["product.pricelist.item"]
        Item.check_access("read")
        if any(not category.parent_path for category in products.mapped("categ_id")):
            raise UserError(_("Hay categorías importadas con una jerarquía incompleta. Actualice el módulo DReyes Product Pricing para repararlas antes de consultar los precios."))
        prices = pricelist._compute_price_rule(products, quantity, date=date)
        rule_ids = [rule_id for _price, rule_id in prices.values() if rule_id]
        rules = Item.browse(rule_ids)
        rules.check_access("read")
        fixed_rules = defaultdict(lambda: Item.browse())
        for rule in Item.search(self._dreyes_fixed_rule_domain(pricelist.ids, products.ids)):
            fixed_rules[rule.product_id.id] |= rule
        can_edit = (
            pricelist.has_access("write")
            and Item.has_access("create")
            and Item.has_access("write")
        )
        rows = []
        for product in products:
            price, rule_id = prices[product.id]
            rule = Item.browse(rule_id) if rule_id else Item.browse()
            candidates = fixed_rules[product.id]
            rows.append({
                "key": "%s-%s" % (pricelist.id, product.id),
                "product_id": product.id,
                "product_name": product.display_name,
                "default_code": product.default_code or "",
                "pricelist_id": pricelist.id,
                "pricelist_name": pricelist.display_name,
                "currency_id": pricelist.currency_id.id,
                "currency_name": pricelist.currency_id.name,
                "currency_digits": pricelist.currency_id.decimal_places,
                "uom_name": product.uom_id.display_name,
                "price": pricelist.currency_id.round(price),
                "rule_id": rule_id or False,
                "rule_name": (
                    _("%s — %s", rule.name, rule.price)
                    if rule else _("Precio de venta base del producto")
                ),
                "can_edit": bool(can_edit and candidates.has_access("write")),
                "duplicate_fixed_rules": len(candidates) > 1,
            })
        return rows

    @api.model
    def dreyes_get_price_page(
        self, source_model, source_id, quantity=1.0, date=False, search="", offset=0, limit=80
    ):
        """Read one page of live variant/list pairs; never materialize a price catalog."""
        self._dreyes_check_internal_user()
        self.check_access("read")
        Product = self.env["product.product"]
        Product.check_access("read")
        quantity, date = self._dreyes_query_context(quantity, date)
        if (
            not isinstance(offset, int) or isinstance(offset, bool) or offset < 0
            or not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0
        ):
            raise ValidationError(_("Paginación no válida."))
        limit = min(limit, 80)
        search = str(search or "").strip()[:200]
        pricelists, domain = self._dreyes_scope(source_model, source_id)
        search_domain = expression.OR([
            [("name", "ilike", search)],
            [("default_code", "ilike", search)],
            [("barcode", "ilike", search)],
            [("product_template_attribute_value_ids.name", "ilike", search)],
        ]) if search else []
        matching_lists = self.search([
            ("id", "in", pricelists.ids), ("name", "ilike", search),
        ]) if search else pricelists
        domains = {
            pricelist.id: domain if pricelist in matching_lists else expression.AND([domain, search_domain])
            for pricelist in pricelists
        }
        counts = {
            pricelist.id: Product.search_count(domains[pricelist.id])
            for pricelist in pricelists
        }
        total = sum(counts.values())
        offset = min(offset, ((total - 1) // limit) * limit) if total else 0
        skip = offset
        rows = []
        for pricelist in pricelists:
            count = counts[pricelist.id]
            if skip >= count:
                skip -= count
                continue
            products = Product.search(
                domains[pricelist.id], offset=skip, limit=limit - len(rows),
                order="name, default_code, id",
            )
            rows.extend(self._dreyes_price_rows(pricelist, products, quantity, date))
            skip = 0
            if len(rows) == limit:
                break
        return {
            "rows": rows, "total": total, "offset": offset, "limit": limit,
            "quantity": quantity, "date": fields.Date.to_string(date),
        }

    @api.model
    def dreyes_save_fixed_price(self, pricelist_id, product_id, price, quantity=1.0, date=False):
        self._dreyes_check_internal_user()
        quantity, date = self._dreyes_query_context(quantity, date)
        try:
            if isinstance(price, bool):
                raise ValueError
            price = float(price)
            if not math.isfinite(price) or price < 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ValidationError(_("El precio fijo debe ser un número mayor o igual que cero."))
        pricelists, _domain = self._dreyes_scope(self._name, pricelist_id)
        pricelist = pricelists.ensure_one()
        pricelist.check_access("write")
        if not isinstance(product_id, int) or isinstance(product_id, bool):
            raise ValidationError(_("Producto no válido."))
        # Product tabs also allow active non-sale variants; saving must use the same scope.
        product = self.env["product.product"].browse(product_id).exists()
        if not product:
            raise UserError(_("El producto ya no existe."))
        product.check_access("read")
        if not product.active or (product.company_id and product.company_id != self.env.company):
            raise UserError(_("El producto debe estar activo y pertenecer a la compañía actual o ser compartido."))
        Item = self.env["product.pricelist.item"]
        Item.check_access("read")
        Item.check_access("create")
        Item.check_access("write")
        # Serialize writers for this list so simultaneous saves cannot create duplicate exceptions.
        self.env.cr.execute("SELECT id FROM product_pricelist WHERE id = %s FOR UPDATE", (pricelist.id,))
        rule_domain = self._dreyes_fixed_rule_domain(pricelist.ids, product.ids)
        rules = Item.search(rule_domain)
        rules.check_access("write")
        if len(rules) > 1:
            return {
                "status": "duplicates",
                "action": {
                    "type": "ir.actions.act_window", "name": _("Reglas de precio fijo duplicadas"),
                    "res_model": "product.pricelist.item", "view_mode": "list,form",
                    "domain": rule_domain,
                    "context": {"default_pricelist_id": pricelist.id, "default_product_id": product.id},
                },
            }
        price = pricelist.currency_id.round(price)
        # Odoo uses REPEATABLE READ. Updating the locked parent makes a concurrent
        # request with an older snapshot retry instead of inserting a second rule.
        pricelist.write({"write_date": fields.Datetime.now()})
        if rules:
            rules.write({"fixed_price": price})
        else:
            rules = Item.create({
                "pricelist_id": pricelist.id, "product_id": product.id,
                "applied_on": "0_product_variant", "compute_price": "fixed",
                "fixed_price": price, "min_quantity": 1.0,
                "date_start": False, "date_end": False,
            })
        row = self._dreyes_price_rows(pricelist, product, quantity, date)[0]
        return {
            "status": "saved", "row": row, "fixed_rule_id": rules.id,
            "overridden": row["rule_id"] != rules.id,
        }


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def dreyes_get_price_page(self, **kwargs):
        self.ensure_one()
        self.check_access("read")
        return self.env["product.pricelist"].dreyes_get_price_page(self._name, self.id, **kwargs)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def dreyes_get_price_page(self, **kwargs):
        self.ensure_one()
        self.check_access("read")
        return self.env["product.pricelist"].dreyes_get_price_page(self._name, self.id, **kwargs)
