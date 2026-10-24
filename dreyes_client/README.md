# `dreyes_client`

Modernizacion del portal cliente nativo de Odoo en `/my/home`.

## Incluye

- portada moderna para `/my/home`;
- tarjetas del portal con look Tabler;
- resumen visual de cliente, ordenes recientes y facturas recientes;
- iconos locales de Tabler y estilos propios sobre Bootstrap de Odoo.

## Assets locales

El modulo sirve los iconos de Tabler de forma local desde `static/lib/`.
No carga el CSS ni el JavaScript completo de Tabler para evitar conflictos
con el encabezado y los componentes Bootstrap de Odoo.
Las tarjetas conservan un unico contador nativo por documento.

Versiones vendorizadas:

- `@tabler/core` `1.4.0`
- `@tabler/icons-webfont` `3.43.0`

No crea rutas nuevas. Reutiliza el portal estandar bajo `/my/*`.
