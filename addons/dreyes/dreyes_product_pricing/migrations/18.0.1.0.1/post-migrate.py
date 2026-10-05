from odoo import SUPERUSER_ID, api
from odoo.addons.dreyes_product_pricing.hooks import repair_category_paths


def migrate(cr, version):
    repair_category_paths(api.Environment(cr, SUPERUSER_ID, {}))
