# -*- coding: utf-8 -*-
{
    "name": "Dreyes Portal",

    "summary": "Entrada del portal con login, registro y branding del acceso.",
    
    "version": "18.0.1.0.0",
    "author": "Wilfredo",
    "website": "https://dreyeslatinmarket,com",
    "category": "DReyes/Portal",
    
    "application": True,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
    
    "depends": ["base", "web", "website", "auth_signup"],
    
    "data": [
        "views/res_config_settings_views.xml",
        "templates/dreyes_portal_layout.xml",
        "templates/dreyes_login.xml",
        "templates/dreyes_register.xml",
    ],
    
    "assets": {
        "web.assets_frontend": [
            "dreyes_portal/static/src/**/*",
        ],
    },
}
