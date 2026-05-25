\set ON_ERROR_STOP on

\if :{?catalog_csv}
\else
\set catalog_csv '/mnt/extra-addons/dreyes/productos/catalog_products.csv'
\endif

\if :{?inventory_csv}
\else
\set inventory_csv '/mnt/extra-addons/dreyes/productos/product-inventory-v3_2026-05-04-2026-05-05.csv'
\endif

\if :{?categories_csv}
\else
\set categories_csv '/mnt/extra-addons/dreyes/productos/categ_products.csv'
\endif

\if :{?images_csv}
\else
\set images_csv '/mnt/extra-addons/dreyes/productos/import_sql/output/stg_wix_images.csv'
\endif

\if :{?load_images}
\else
\set load_images 0
\endif

\echo === Preparando staging Wix -> Odoo ===

CREATE TABLE IF NOT EXISTS stg_wix_catalog (
    "handle" text,
    "fieldType" text,
    "name" text,
    "visible" text,
    "plainDescription" text,
    "categorySlugs" text,
    "primaryCategorySlug" text,
    "media" text,
    "mediaAltText" text,
    "ribbon" text,
    "brand" text,
    "price" text,
    "strikethroughPrice" text,
    "cost" text,
    "inventory" text,
    "preOrderEnabled" text,
    "preOrderMessage" text,
    "preOrderLimit" text,
    "sku" text,
    "barcode" text,
    "weight" text,
    "baseUnit" text,
    "baseUnitMeasurement" text,
    "totalUnits" text,
    "totalUnitsMeasurement" text,
    "productOptionName1" text,
    "productOptionType1" text,
    "productOptionChoices1" text,
    "productOptionName2" text,
    "productOptionType2" text,
    "productOptionChoices2" text,
    "productOptionName3" text,
    "productOptionType3" text,
    "productOptionChoices3" text,
    "productOptionName4" text,
    "productOptionType4" text,
    "productOptionChoices4" text,
    "productOptionName5" text,
    "productOptionType5" text,
    "productOptionChoices5" text,
    "productOptionName6" text,
    "productOptionType6" text,
    "productOptionChoices6" text,
    "modifierName1" text,
    "modifierType1" text,
    "modifierCharLimit1" text,
    "modifierMandatory1" text,
    "modifierDescription1" text,
    "modifierName2" text,
    "modifierType2" text,
    "modifierCharLimit2" text,
    "modifierMandatory2" text,
    "modifierDescription2" text,
    "modifierName3" text,
    "modifierType3" text,
    "modifierCharLimit3" text,
    "modifierMandatory3" text,
    "modifierDescription3" text,
    "modifierName4" text,
    "modifierType4" text,
    "modifierCharLimit4" text,
    "modifierMandatory4" text,
    "modifierDescription4" text,
    "modifierName5" text,
    "modifierType5" text,
    "modifierCharLimit5" text,
    "modifierMandatory5" text,
    "modifierDescription5" text,
    "modifierName6" text,
    "modifierType6" text,
    "modifierCharLimit6" text,
    "modifierMandatory6" text,
    "modifierDescription6" text,
    "modifierName7" text,
    "modifierType7" text,
    "modifierCharLimit7" text,
    "modifierMandatory7" text,
    "modifierDescription7" text,
    "modifierName8" text,
    "modifierType8" text,
    "modifierCharLimit8" text,
    "modifierMandatory8" text,
    "modifierDescription8" text,
    "modifierName9" text,
    "modifierType9" text,
    "modifierCharLimit9" text,
    "modifierMandatory9" text,
    "modifierDescription9" text,
    "modifierName10" text,
    "modifierType10" text,
    "modifierCharLimit10" text,
    "modifierMandatory10" text,
    "modifierDescription10" text
);

CREATE TABLE IF NOT EXISTS stg_wix_inventory (
    "Product image" text,
    "Imagen" text,
    "Variant" text,
    "SKU" text,
    "Product category" text,
    "Product name" text,
    "Total value" text,
    "Inventory" text
);

CREATE TABLE IF NOT EXISTS stg_wix_category_map (
    slug text,
    category_name text NOT NULL,
    source text NOT NULL,
    loaded_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stg_wix_images (
    sku text NOT NULL,
    image_url text,
    image_path text,
    mimetype text,
    file_size integer,
    checksum text,
    db_datas_base64 text,
    download_status text,
    error_message text,
    loaded_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS stg_wix_catalog_sku_idx ON stg_wix_catalog ("sku");
CREATE INDEX IF NOT EXISTS stg_wix_catalog_fieldtype_idx ON stg_wix_catalog ("fieldType");
CREATE INDEX IF NOT EXISTS stg_wix_inventory_sku_idx ON stg_wix_inventory ("SKU");
CREATE INDEX IF NOT EXISTS stg_wix_category_map_slug_idx ON stg_wix_category_map (slug);
CREATE UNIQUE INDEX IF NOT EXISTS stg_wix_images_sku_uidx ON stg_wix_images (sku);

TRUNCATE TABLE stg_wix_catalog;
TRUNCATE TABLE stg_wix_inventory;
TRUNCATE TABLE stg_wix_category_map;

\echo Cargando catalogo desde /mnt/extra-addons/dreyes/productos/catalog_products.csv
\copy stg_wix_catalog FROM '/mnt/extra-addons/dreyes/productos/catalog_products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

\echo Cargando inventario desde /mnt/extra-addons/dreyes/productos/product-inventory-v3_2026-05-04-2026-05-05.csv
\copy stg_wix_inventory FROM '/mnt/extra-addons/dreyes/productos/product-inventory-v3_2026-05-04-2026-05-05.csv' WITH (FORMAT csv, HEADER true, ENCODING 'LATIN1')

CREATE TEMP TABLE tmp_wix_category_names_raw (
    category_name text
);

\echo Cargando nombres de categorias desde /mnt/extra-addons/dreyes/productos/categ_products.csv
\copy tmp_wix_category_names_raw (category_name) FROM '/mnt/extra-addons/dreyes/productos/categ_products.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

INSERT INTO stg_wix_category_map (slug, category_name, source)
VALUES
    ('appliances', 'Appliances', 'explicit_slug_map'),
    ('bakery-snacks', 'Bakery / Baked Goods', 'explicit_slug_map'),
    ('beauty-personal-care', 'Beauty & Personal Care', 'explicit_slug_map'),
    ('beverages', 'Beverages', 'explicit_slug_map'),
    ('board-games-cards', 'Board Games & Cards', 'explicit_slug_map'),
    ('candels', 'Candels', 'explicit_slug_map'),
    ('candy', 'Candy', 'explicit_slug_map'),
    ('canned-preserves', 'Canned & Preserves', 'explicit_slug_map'),
    ('cofee', 'Cofee', 'explicit_slug_map'),
    ('dairy', 'Dairy', 'explicit_slug_map'),
    ('deli-meats', 'Deli Meats', 'explicit_slug_map'),
    ('frozen-foods', 'Frozen Foods', 'explicit_slug_map'),
    ('latin-flavors', 'Latin Flavors', 'explicit_slug_map'),
    ('mexico', 'Mexico', 'explicit_slug_map'),
    ('pantry-essentials', 'Pantry Essentials', 'explicit_slug_map'),
    ('snacks', 'Snacks', 'explicit_slug_map'),
    ('spices-sauces', 'Spices & Sauces', 'explicit_slug_map'),
    ('turron', 'Turron', 'explicit_slug_map');

INSERT INTO stg_wix_category_map (slug, category_name, source)
SELECT
    NULL,
    trim(category_name),
    'wix_export_only'
FROM tmp_wix_category_names_raw
WHERE NULLIF(trim(category_name), '') IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM stg_wix_category_map m
      WHERE lower(m.category_name) = lower(trim(tmp_wix_category_names_raw.category_name))
  );

WITH used_slugs AS (
    SELECT DISTINCT trim(slug_item) AS slug
    FROM stg_wix_catalog c
    CROSS JOIN LATERAL unnest(string_to_array(COALESCE(c."categorySlugs", ''), ';')) AS slug_item
    WHERE upper(COALESCE(c."fieldType", '')) = 'PRODUCT'
      AND NULLIF(trim(slug_item), '') IS NOT NULL
)
INSERT INTO stg_wix_category_map (slug, category_name, source)
SELECT
    used_slugs.slug,
    initcap(replace(used_slugs.slug, '-', ' ')),
    'derived_from_slug'
FROM used_slugs
WHERE NOT EXISTS (
    SELECT 1
    FROM stg_wix_category_map m
    WHERE m.slug = used_slugs.slug
);

TRUNCATE TABLE stg_wix_images;

\if :load_images
\echo Cargando metadatos de imagenes desde /mnt/extra-addons/dreyes/productos/import_sql/output/stg_wix_images.csv
\copy stg_wix_images (sku, image_url, image_path, mimetype, file_size, checksum, db_datas_base64, download_status, error_message) FROM '/mnt/extra-addons/dreyes/productos/import_sql/output/stg_wix_images.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\else
\echo Saltando carga de imagenes. Ejecuta con -v load_images=1 cuando exista stg_wix_images.csv
\endif

\echo === Resumen staging ===
SELECT
    COUNT(*) FILTER (WHERE upper(COALESCE("fieldType", '')) = 'PRODUCT') AS product_rows,
    COUNT(*) FILTER (WHERE upper(COALESCE("fieldType", '')) = 'MEDIA') AS media_rows
FROM stg_wix_catalog;

SELECT COUNT(*) AS inventory_rows FROM stg_wix_inventory;
SELECT COUNT(*) AS category_map_rows FROM stg_wix_category_map;
SELECT COUNT(*) AS image_rows FROM stg_wix_images;
