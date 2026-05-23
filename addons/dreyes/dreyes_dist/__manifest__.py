# -*- coding: utf-8 -*-
{
    "name": "Dreyes Dist",
    "summary": "Formulario extendido posterior al registro y login de distribuidores.",
    "version": "18.0.1.0.0",
    "author": "Wilfredo",
    "website": "https://dreyeslatinmarket,com",
    "category": "DReyes/Portal",
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
    "depends": ["dreyes_portal"],
    "data": [
        "views/res_config_settings_views.xml",
        "templates/dreyes_profile_complete.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "dreyes_dist/static/src/scss/profile.scss",
        ],
    },
}
