# -*- coding: utf-8 -*-
{
    "name": "DReyes Distribution Clients",
    "summary": "Gestión visual de solicitudes y perfiles de clientes distribuidores.",
    "version": "19.0.1.2.0",
    "author": "Wilfredo",
    "website": "https://dreyeslatinmarket.com",
    "category": "DReyes/Distribution",
    "application": True,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
    "depends": ["dreyes_dist"],
    "data": [
        "security/ir.model.access.csv",
        "views/distribution_client_form.xml",
        "views/distribution_client_views.xml",
        "views/distribution_client_menus.xml",
    ],
}
