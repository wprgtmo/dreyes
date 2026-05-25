# Importacion Wix -> Odoo por SQL

Este directorio deja el flujo tecnico sin modulo Odoo:

1. `01_stage.sql`
   Crea y rellena tablas staging desde los CSV exportados de Wix.
2. `predescarga_imagenes.py`
   Descarga imagenes desde Wix y genera `output/stg_wix_images.csv` con binario en base64.
3. `02_upsert.sql`
   Normaliza staging y hace el upsert en Odoo. Por defecto corre en modo `dry-run`.
4. `post_import_odoo.py`
   Ejecuta el postproceso por ORM para regenerar tamaños derivados de imagen y validar el lote cargado.

## Requisitos

- Contenedor Odoo con `psql` disponible: `odoo_dreyes_18`
- Base de datos `dreyes`
- Archivos fuente montados en `/mnt/extra-addons/dreyes/productos`

## 1. Cargar staging sin imagenes

```bash
docker exec -w /mnt/extra-addons/dreyes/productos/import_sql odoo_dreyes_18 \
  bash -lc 'export PGPASSWORD="$PASSWORD"; psql -h db -U odoo -d dreyes -f 01_stage.sql'
```

## 2. Descargar imagenes y generar CSV auxiliar

```bash
docker exec -w /mnt/extra-addons/dreyes/productos/import_sql odoo_dreyes_18 \
  python3 predescarga_imagenes.py --skip-existing --image-mode original
```

El script genera:

- `output/images/*`
- `output/stg_wix_images.csv`

`--image-mode original` es el modo recomendado para produccion. El export de Wix trae thumbnails
`w_50,h_50`; este modo reconstruye la URL del asset original en `static.wixstatic.com/media/...`
y evita importar miniaturas borrosas.

Si ya descargaste thumbnails antiguas, no uses `--skip-existing` o limpia `output/images/` antes de
repetir la descarga para que se reemplacen por la version de mejor calidad.

## 3. Recargar staging incluyendo imagenes

```bash
docker exec -w /mnt/extra-addons/dreyes/productos/import_sql odoo_dreyes_18 \
  bash -lc 'export PGPASSWORD="$PASSWORD"; psql -h db -U odoo -d dreyes -v load_images=1 -f 01_stage.sql'
```

## 4. Dry-run de validacion

```bash
docker exec -w /mnt/extra-addons/dreyes/productos/import_sql odoo_dreyes_18 \
  bash -lc 'export PGPASSWORD="$PASSWORD"; psql -h db -U odoo -d dreyes -f 02_upsert.sql'
```

`02_upsert.sql` no escribe en la base mientras `apply=0`.

## 5. Aplicar importacion real

```bash
docker exec -w /mnt/extra-addons/dreyes/productos/import_sql odoo_dreyes_18 \
  bash -lc 'export PGPASSWORD="$PASSWORD"; psql -h db -U odoo -d dreyes -v apply=1 -f 02_upsert.sql'
```

## 6. Regenerar imagenes derivadas en Odoo

Este paso es obligatorio si quieres que las imagenes se vean correctamente en vistas que usan
`image_1024`, `image_512`, `image_256` o `image_128`.

```bash
docker exec -w /mnt/extra-addons/dreyes/productos/import_sql odoo_dreyes_18 \
  bash -lc 'odoo shell -d dreyes --db_host=db --db_user=odoo --db_password="$PASSWORD" < post_import_odoo.py'
```

El script:

- regenera derivados desde `image_1920`
- hace commits por lotes
- imprime resumen de templates, quants e imagenes del lote staged

## Variables utiles

- `load_images=1`
- `apply=1`
- `location_id=8`
- `owner_user_id=1`

Ejemplo:

```bash
docker exec -w /mnt/extra-addons/dreyes/productos/import_sql odoo_dreyes_18 \
  bash -lc 'export PGPASSWORD="$PASSWORD"; psql -h db -U odoo -d dreyes -v apply=1 -v location_id=8 -v owner_user_id=1 -f 02_upsert.sql'
```

Y luego:

```bash
docker exec -w /mnt/extra-addons/dreyes/productos/import_sql odoo_dreyes_18 \
  bash -lc 'odoo shell -d dreyes --db_host=db --db_user=odoo --db_password="$PASSWORD" < post_import_odoo.py'
```

No mezcles `load_images` con `02_upsert.sql`; esa variable solo afecta `01_stage.sql`.
`post_import_odoo.py` debe ejecutarse despues de `02_upsert.sql` cuando `apply=1`.
