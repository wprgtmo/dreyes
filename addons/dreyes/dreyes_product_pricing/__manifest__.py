{
    "name": "DReyes Product Pricing",
    "summary": "Consulta y edición de precios por producto y lista de precios",
    "version": "18.0.1.0.1",
    "author": "DReyes",
    "license": "LGPL-3",
    "category": "Sales",
    "depends": ["product", "web"],
    "post_init_hook": "post_init_hook",
    "data": ["views/product_pricing_views.xml"],
    "assets": {
        "web.assets_backend": [
            "dreyes_product_pricing/static/src/pricing_table.js",
            "dreyes_product_pricing/static/src/pricing_table.xml",
            "dreyes_product_pricing/static/src/pricing_table.scss",
        ],
    },
    "installable": True,
    "application": False,
}
