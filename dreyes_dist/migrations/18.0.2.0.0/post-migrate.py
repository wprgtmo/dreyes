# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

from odoo.addons.dreyes_dist.hooks import migrate_existing_profiles


def migrate(cr, version):
    migrate_existing_profiles(api.Environment(cr, SUPERUSER_ID, {}))
