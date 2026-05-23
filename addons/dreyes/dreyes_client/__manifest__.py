# -*- coding: utf-8 -*-
{
    "name": "Dreyes Client",
    "summary": "Modernizacion Tabler del portal cliente nativo en /my/home.",
    "version": "18.0.1.0.0",
    "author": "Wilfredo",
    "website": "https://dreyeslatinmarket,com",
    "category": "DReyes/Portal",
    "application": True,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
    "depends": ["website", "portal", "sale_management", "account", "contacts", "dreyes_portal"],
    "data": [
        "templates/dreyes_client_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "dreyes_client/static/src/scss/dreyes_client.scss",
        ],
    },
}
