# -*- coding: utf-8 -*-
{
    "name": "Dreyes Dist",
    "summary": "Formulario extendido posterior al registro y login de distribuidores.",
    "version": "18.0.2.0.0",
    "author": "Wilfredo",
    "website": "https://dreyeslatinmarket,com",
    "category": "DReyes/Portal",
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
    "depends": ["dreyes_portal", "portal", "website_sale", "mail", "contacts"],
    "post_init_hook": "post_init_hook",
    "data": [
        "security/dreyes_dist_security.xml",
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/distributor_profile_views.xml",
        "templates/dreyes_profile_complete.xml",
        "templates/dreyes_distribution_shop.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "dreyes_dist/static/src/scss/profile.scss",
        ],
    },
}
