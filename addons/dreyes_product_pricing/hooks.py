import logging

from odoo import _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


def repair_category_paths(env):
    """Repair SQL-imported category paths during installation/upgrade, never on reads."""
    Category = env["product.category"]
    missing = Category.search(["|", ("parent_path", "=", False), ("parent_path", "=", "")])
    if not missing:
        return 0
    if any(category._has_cycle() for category in Category.search([])):
        raise ValidationError(_("El árbol de categorías contiene un ciclo. Corríjalo antes de actualizar el módulo de precios."))
    count = len(missing)
    Category._parent_store_compute()
    Category.invalidate_model(["parent_path"])
    _logger.info("Rebuilt product category hierarchy: %s categories had missing paths", count)
    return count


def post_init_hook(env):
    repair_category_paths(env)
