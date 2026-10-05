# DReyes Product Pricing

En la ficha del producto, **Listas de precios** consulta sus variantes activas
en las listas activas de la compañía actual y las listas compartidas.
En la ficha de cada lista, **Productos** abre todos los productos activos
vendibles de esa compañía, incluidos los compartidos.

Seleccione cantidad y fecha y pulse **Consultar**. La tabla muestra el precio
unitario calculado por Odoo, en la unidad del producto y la moneda de la lista.
La búsqueda incluye nombre, variante, referencia, código de barras y nombre de
la lista. Cada página calcula como máximo 80 combinaciones producto/lista.
La consulta no crea registros ni guarda una copia del catálogo de precios.

## Guardar precios

Los usuarios con permisos de escritura en la lista y de creación/escritura
en sus reglas pueden introducir un **Nuevo precio fijo** y pulsar **Guardar**.
Esto crea o actualiza una excepción específica de variante, desde 1 unidad,
sin fechas de inicio o vencimiento. Se acepta cero y se redondea según la moneda.
Las reglas generales, temporales y de volumen se conservan. Odoo mantiene su
prioridad nativa: si otra regla prevalece en la consulta, se muestra una advertencia.
Si existen varias excepciones equivalentes, se abren las reglas para resolver
la duplicidad, sin cambiar ningún precio.

Se respetan los permisos y reglas de acceso existentes, sin `sudo`. La consulta
está restringida a usuarios internos. El guardado usa el ORM y conserva los hooks
de sincronización con Clover. No se modifican tienda, portal ni pedidos.

## Instalación y pruebas

Agregar esta carpeta al `addons_path`, respaldar la base de datos e instalar
`dreyes_product_pricing`. Para ejecutar sus pruebas:

```sh
odoo -d <base> -i dreyes_product_pricing --stop-after-init --no-http \
  --test-enable --test-tags /dreyes_product_pricing
```

Si el catálogo fue importado directamente por SQL, sus categorías deben tener
el árbol `parent_path` completo para que funcione el cálculo nativo de Odoo.
Si falta, reconstruirlo con `env['product.category']._parent_store_compute()`
desde `odoo shell` después de respaldar la base. La consulta de precios no
modifica ni repara datos automáticamente.
