# -*- coding: utf-8 -*-
{
    "name": "PWA Badge",
    "summary": "PWA badge counters and iPhone install icon support.",
    "version": "19.0.1.0.0",
    "author": "OpenAI",
    "website": "https://example.com",
    "category": "Website",
    "license": "LGPL-3",
    "application": True,
    "auto_install": False,
    "depends": ["web", "mail", "bus", "web_pwa_customize"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/web_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pwa_badge/static/src/js/pwa_badge_service.esm.js",
        ],
        "web.assets_unit_tests": [
            "pwa_badge/static/tests/**/*.js",
        ],
    },
    "installable": True,
}
