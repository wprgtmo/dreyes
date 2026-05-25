\set ON_ERROR_STOP on

\if :{?apply}
\else
\set apply 0
\endif

\if :{?location_id}
\else
\set location_id 8
\endif

\if :{?owner_user_id}
\else
\set owner_user_id 1
\endif

\echo === Normalizando staging Wix -> Odoo ===

CREATE TEMP TABLE tmp_company_ids AS
SELECT id
FROM res_company
ORDER BY id;

CREATE TEMP TABLE tmp_wix_products AS
WITH src AS (
    SELECT DISTINCT ON (trim(COALESCE("sku", '')))
        trim(COALESCE("sku", '')) AS sku,
        NULLIF(trim(COALESCE("name", '')), '') AS name,
        CASE
            WHEN lower(trim(COALESCE("visible", ''))) IN ('1', 't', 'true', 'yes', 'y') THEN true
            ELSE false
        END AS is_published,
        NULLIF(trim(COALESCE("plainDescription", '')), '') AS plain_description,
        NULLIF(trim(COALESCE("categorySlugs", '')), '') AS category_slugs,
        NULLIF(trim(COALESCE("primaryCategorySlug", '')), '') AS primary_category_slug,
        NULLIF(trim(COALESCE("brand", '')), '') AS brand,
        NULLIF(trim(COALESCE("ribbon", '')), '') AS ribbon,
        NULLIF(trim(COALESCE("barcode", '')), '') AS barcode,
        CASE
            WHEN regexp_replace(COALESCE("price", ''), '[^0-9\\.-]+', '', 'g') <> '' THEN regexp_replace(COALESCE("price", ''), '[^0-9\\.-]+', '', 'g')::numeric
            ELSE NULL
        END AS price_num,
        CASE
            WHEN regexp_replace(COALESCE("cost", ''), '[^0-9\\.-]+', '', 'g') <> '' THEN regexp_replace(COALESCE("cost", ''), '[^0-9\\.-]+', '', 'g')::numeric
            ELSE NULL
        END AS cost_num,
        CASE
            WHEN regexp_replace(COALESCE("weight", ''), '[^0-9\\.-]+', '', 'g') <> '' THEN regexp_replace(COALESCE("weight", ''), '[^0-9\\.-]+', '', 'g')::numeric
            ELSE NULL
        END AS weight_num
    FROM stg_wix_catalog
    WHERE upper(COALESCE("fieldType", '')) = 'PRODUCT'
      AND NULLIF(trim(COALESCE("sku", '')), '') IS NOT NULL
    ORDER BY trim(COALESCE("sku", '')), trim(COALESCE("name", ''))
)
SELECT
    sku,
    name,
    is_published,
    plain_description,
    category_slugs,
    COALESCE(primary_category_slug, NULLIF(split_part(COALESCE(category_slugs, ''), ';', 1), '')) AS primary_slug,
    brand,
    ribbon,
    barcode,
    price_num,
    cost_num,
    weight_num
FROM src;

CREATE INDEX ON tmp_wix_products (sku);

CREATE TEMP TABLE tmp_wix_inventory AS
WITH raw_src AS (
    SELECT
        trim(COALESCE("SKU", '')) AS raw_sku,
        NULLIF(trim(COALESCE("Product image", '')), '') AS image_url,
        NULLIF(trim(COALESCE("Product category", '')), '') AS product_category,
        NULLIF(trim(COALESCE("Product name", '')), '') AS product_name,
        CASE
            WHEN regexp_replace(COALESCE("Inventory", ''), '[^0-9\\.-]+', '', 'g') <> '' THEN regexp_replace(COALESCE("Inventory", ''), '[^0-9\\.-]+', '', 'g')::numeric
            ELSE NULL
        END AS inventory_qty
    FROM stg_wix_inventory
    WHERE NULLIF(trim(COALESCE("SKU", '')), '') IS NOT NULL
),
resolved_src AS (
    SELECT
        COALESCE(
            sku_match.sku,
            name_match.sku,
            CASE
                WHEN raw_sku ~* '^[0-9]+(\\.0+)?$' THEN regexp_replace(raw_sku, '\\.0+$', '')
                WHEN raw_sku ~* '^[0-9]+\\.[0-9]+[eE][+-]?[0-9]+$' THEN trim(to_char((raw_sku::numeric), 'FM999999999999999999999999999999'))
                ELSE raw_sku
            END
        ) AS sku,
        image_url,
        product_category,
        product_name,
        inventory_qty
    FROM raw_src src
    LEFT JOIN tmp_wix_products sku_match
        ON lower(sku_match.sku) = lower(
            CASE
                WHEN src.raw_sku ~* '^[0-9]+(\\.0+)?$' THEN regexp_replace(src.raw_sku, '\\.0+$', '')
                WHEN src.raw_sku ~* '^[0-9]+\\.[0-9]+[eE][+-]?[0-9]+$' THEN trim(to_char((src.raw_sku::numeric), 'FM999999999999999999999999999999'))
                ELSE src.raw_sku
            END
        )
    LEFT JOIN tmp_wix_products name_match
        ON lower(COALESCE(name_match.name, '')) = lower(COALESCE(src.product_name, ''))
)
SELECT DISTINCT ON (sku)
    sku,
    image_url,
    product_category,
    product_name,
    inventory_qty
FROM resolved_src
WHERE NULLIF(trim(COALESCE(sku, '')), '') IS NOT NULL
ORDER BY
    sku,
    CASE WHEN image_url IS NULL THEN 1 ELSE 0 END,
    image_url;

CREATE INDEX ON tmp_wix_inventory (sku);

CREATE TEMP TABLE tmp_wix_category_names AS
SELECT DISTINCT ON (slug)
    slug,
    category_name
FROM stg_wix_category_map
WHERE slug IS NOT NULL
ORDER BY
    slug,
    CASE source
        WHEN 'explicit_slug_map' THEN 0
        WHEN 'derived_from_slug' THEN 1
        ELSE 2
    END,
    category_name;

CREATE INDEX ON tmp_wix_category_names (slug);

CREATE TEMP TABLE tmp_wix_category_links AS
SELECT DISTINCT
    p.sku,
    trim(slug_item) AS slug
FROM tmp_wix_products p
CROSS JOIN LATERAL unnest(string_to_array(COALESCE(p.category_slugs, ''), ';')) AS slug_item
WHERE NULLIF(trim(slug_item), '') IS NOT NULL;

CREATE INDEX ON tmp_wix_category_links (sku);
CREATE INDEX ON tmp_wix_category_links (slug);

CREATE TEMP TABLE tmp_existing_products AS
SELECT
    p.sku,
    pp.id AS product_id,
    pp.product_tmpl_id
FROM tmp_wix_products p
JOIN product_product pp
    ON lower(COALESCE(pp.default_code, '')) = lower(p.sku);

CREATE INDEX ON tmp_existing_products (sku);

CREATE TEMP TABLE tmp_new_products AS
SELECT p.*
FROM tmp_wix_products p
LEFT JOIN tmp_existing_products ep
    ON ep.sku = p.sku
WHERE ep.sku IS NULL;

CREATE INDEX ON tmp_new_products (sku);

\echo === Dry-run summary ===
SELECT COUNT(*) AS staged_products FROM tmp_wix_products;
SELECT COUNT(*) AS staged_inventory_rows FROM tmp_wix_inventory;
SELECT COUNT(*) AS sku_matches_catalog_inventory
FROM tmp_wix_products p
JOIN tmp_wix_inventory i ON i.sku = p.sku;
SELECT COUNT(*) AS staged_image_rows_ok
FROM stg_wix_images
WHERE lower(COALESCE(download_status, '')) = 'downloaded'
  AND db_datas_base64 IS NOT NULL;
SELECT COUNT(*) AS existing_products_by_sku FROM tmp_existing_products;
SELECT COUNT(*) AS new_products_by_sku FROM tmp_new_products;

SELECT
    COALESCE(l.slug, '(null)') AS unresolved_slug
FROM tmp_wix_category_links l
LEFT JOIN tmp_wix_category_names n
    ON n.slug = l.slug
WHERE n.slug IS NULL
GROUP BY l.slug
ORDER BY l.slug;

\if :apply
\echo === Aplicando upsert a Odoo ===

CREATE TEMP TABLE tmp_roots AS
SELECT
    (SELECT res_id FROM ir_model_data WHERE module = 'product' AND name = 'product_category_all') AS internal_root_id,
    (SELECT res_id FROM ir_model_data WHERE module = 'uom' AND name = 'product_uom_unit') AS unit_uom_id;

CREATE TEMP TABLE tmp_needed_internal_categories AS
SELECT DISTINCT
    p.primary_slug AS slug,
    COALESCE(n.category_name, initcap(replace(p.primary_slug, '-', ' '))) AS category_name
FROM tmp_wix_products p
LEFT JOIN tmp_wix_category_names n
    ON n.slug = p.primary_slug
WHERE p.primary_slug IS NOT NULL;

WITH root AS (
    SELECT internal_root_id
    FROM tmp_roots
),
missing AS (
    SELECT nic.slug, nic.category_name, root.internal_root_id
    FROM tmp_needed_internal_categories nic
    CROSS JOIN root
    LEFT JOIN product_category pc
        ON pc.parent_id = root.internal_root_id
       AND lower(pc.name) = lower(nic.category_name)
    WHERE pc.id IS NULL
),
inserted AS (
    INSERT INTO product_category (
        parent_id,
        create_uid,
        write_uid,
        name,
        complete_name,
        parent_path,
        create_date,
        write_date
    )
    SELECT
        internal_root_id,
        :owner_user_id,
        :owner_user_id,
        category_name,
        NULL,
        NULL,
        now(),
        now()
    FROM missing
    RETURNING id, parent_id, name
)
UPDATE product_category pc
SET
    complete_name = parent.complete_name || ' / ' || pc.name,
    parent_path = parent.parent_path || pc.id || '/',
    write_uid = :owner_user_id,
    write_date = now()
FROM product_category parent
WHERE pc.parent_id = parent.id
  AND pc.id IN (SELECT id FROM inserted);

CREATE TEMP TABLE tmp_internal_category_ids AS
SELECT
    nic.slug,
    pc.id AS categ_id
FROM tmp_needed_internal_categories nic
JOIN tmp_roots root
    ON true
JOIN product_category pc
    ON pc.parent_id = root.internal_root_id
   AND lower(pc.name) = lower(nic.category_name);

CREATE INDEX ON tmp_internal_category_ids (slug);

CREATE TEMP TABLE tmp_needed_public_categories AS
SELECT DISTINCT
    l.slug,
    COALESCE(n.category_name, initcap(replace(l.slug, '-', ' '))) AS category_name
FROM tmp_wix_category_links l
LEFT JOIN tmp_wix_category_names n
    ON n.slug = l.slug;

WITH missing AS (
    SELECT npc.slug, npc.category_name
    FROM tmp_needed_public_categories npc
    LEFT JOIN product_public_category ppc
        ON ppc.parent_id IS NULL
       AND lower(COALESCE(ppc.name ->> 'en_US', ppc.name ->> 'es_419', '')) = lower(npc.category_name)
    WHERE ppc.id IS NULL
),
inserted AS (
    INSERT INTO product_public_category (
        parent_id,
        create_uid,
        write_uid,
        name,
        create_date,
        write_date
    )
    SELECT
        NULL,
        :owner_user_id,
        :owner_user_id,
        jsonb_build_object('en_US', category_name, 'es_419', category_name),
        now(),
        now()
    FROM missing
    RETURNING id, parent_id
)
UPDATE product_public_category ppc
SET
    parent_path = ppc.id || '/',
    write_uid = :owner_user_id,
    write_date = now()
WHERE ppc.id IN (SELECT id FROM inserted)
  AND ppc.parent_id IS NULL;

UPDATE product_public_category ppc
SET
    parent_path = ppc.id || '/',
    write_uid = :owner_user_id,
    write_date = now()
WHERE ppc.parent_id IS NULL
  AND (ppc.parent_path IS NULL OR ppc.parent_path = '');

CREATE TEMP TABLE tmp_public_category_ids AS
SELECT
    npc.slug,
    ppc.id AS public_category_id
FROM tmp_needed_public_categories npc
JOIN product_public_category ppc
    ON ppc.parent_id IS NULL
   AND lower(COALESCE(ppc.name ->> 'en_US', ppc.name ->> 'es_419', '')) = lower(npc.category_name);

CREATE INDEX ON tmp_public_category_ids (slug);

UPDATE product_template pt
SET
    name = COALESCE(pt.name, '{}'::jsonb) || jsonb_build_object('en_US', src.name, 'es_419', src.name),
    description_sale = CASE
        WHEN src.plain_description IS NOT NULL THEN COALESCE(pt.description_sale, '{}'::jsonb) || jsonb_build_object('en_US', src.plain_description, 'es_419', src.plain_description)
        ELSE pt.description_sale
    END,
    list_price = COALESCE(src.price_num, pt.list_price),
    weight = COALESCE(src.weight_num, pt.weight),
    categ_id = COALESCE(ic.categ_id, pt.categ_id),
    is_published = src.is_published,
    sale_ok = true,
    purchase_ok = true,
    active = true,
    default_code = src.sku,
    type = 'consu',
    is_storable = true,
    write_uid = :owner_user_id,
    write_date = now()
FROM tmp_wix_products src
JOIN tmp_existing_products ep
    ON ep.sku = src.sku
LEFT JOIN tmp_internal_category_ids ic
    ON ic.slug = src.primary_slug
WHERE pt.id = ep.product_tmpl_id;

UPDATE product_product pp
SET
    default_code = src.sku,
    barcode = COALESCE(src.barcode, pp.barcode),
    weight = COALESCE(src.weight_num, pp.weight),
    active = true,
    standard_price = CASE
        WHEN src.cost_num IS NULL THEN pp.standard_price
        ELSE COALESCE(pp.standard_price, '{}'::jsonb) || (
            SELECT jsonb_object_agg(c.id::text, to_jsonb(src.cost_num))
            FROM tmp_company_ids c
        )
    END,
    write_uid = :owner_user_id,
    write_date = now()
FROM tmp_wix_products src
JOIN tmp_existing_products ep
    ON ep.sku = src.sku
WHERE pp.id = ep.product_id;

WITH root AS (
    SELECT internal_root_id, unit_uom_id
    FROM tmp_roots
),
inserted AS (
    INSERT INTO product_template (
        categ_id,
        uom_id,
        uom_po_id,
        company_id,
        create_uid,
        write_uid,
        type,
        service_tracking,
        default_code,
        name,
        description_sale,
        list_price,
        weight,
        sale_ok,
        purchase_ok,
        active,
        create_date,
        write_date,
        tracking,
        is_storable,
        sale_line_warn,
        purchase_line_warn,
        invoice_policy,
        purchase_method,
        base_unit_count,
        is_published
    )
    SELECT
        COALESCE(ic.categ_id, root.internal_root_id),
        root.unit_uom_id,
        root.unit_uom_id,
        NULL,
        :owner_user_id,
        :owner_user_id,
        'consu',
        'no',
        src.sku,
        jsonb_build_object('en_US', src.name, 'es_419', src.name),
        CASE
            WHEN src.plain_description IS NOT NULL THEN jsonb_build_object('en_US', src.plain_description, 'es_419', src.plain_description)
            ELSE NULL
        END,
        COALESCE(src.price_num, 0),
        src.weight_num,
        true,
        true,
        true,
        now(),
        now(),
        'none',
        true,
        'no-message',
        'no-message',
        'delivery',
        'receive',
        1,
        src.is_published
    FROM tmp_new_products src
    CROSS JOIN root
    LEFT JOIN tmp_internal_category_ids ic
        ON ic.slug = src.primary_slug
    RETURNING id, default_code
)
INSERT INTO product_product (
    product_tmpl_id,
    create_uid,
    write_uid,
    default_code,
    barcode,
    standard_price,
    weight,
    active,
    create_date,
    write_date,
    base_unit_count
)
SELECT
    inserted.id,
    :owner_user_id,
    :owner_user_id,
    src.sku,
    src.barcode,
    CASE
        WHEN src.cost_num IS NULL THEN NULL
        ELSE (
            SELECT jsonb_object_agg(c.id::text, to_jsonb(src.cost_num))
            FROM tmp_company_ids c
        )
    END,
    src.weight_num,
    true,
    now(),
    now(),
    1
FROM inserted
JOIN tmp_new_products src
    ON src.sku = inserted.default_code;

CREATE TEMP TABLE tmp_product_targets AS
SELECT
    src.sku,
    pp.id AS product_id,
    pp.product_tmpl_id
FROM tmp_wix_products src
JOIN product_product pp
    ON lower(COALESCE(pp.default_code, '')) = lower(src.sku);

CREATE INDEX ON tmp_product_targets (sku);
CREATE INDEX ON tmp_product_targets (product_tmpl_id);

DELETE FROM product_public_category_product_template_rel rel
USING tmp_product_targets t
WHERE rel.product_template_id = t.product_tmpl_id;

INSERT INTO product_public_category_product_template_rel (
    product_public_category_id,
    product_template_id
)
SELECT DISTINCT
    pc.public_category_id,
    t.product_tmpl_id
FROM tmp_product_targets t
JOIN tmp_wix_category_links l
    ON l.sku = t.sku
JOIN tmp_public_category_ids pc
    ON pc.slug = l.slug;

CREATE TEMP TABLE tmp_stock_input AS
SELECT
    t.product_id,
    i.inventory_qty
FROM tmp_product_targets t
JOIN tmp_wix_inventory i
    ON i.sku = t.sku
WHERE i.inventory_qty IS NOT NULL;

UPDATE stock_quant sq
SET
    quantity = src.inventory_qty,
    company_id = COALESCE(sq.company_id, loc.company_id),
    reserved_quantity = COALESCE(sq.reserved_quantity, 0),
    write_uid = :owner_user_id,
    write_date = now()
FROM tmp_stock_input src
JOIN stock_location loc
    ON loc.id = :location_id
WHERE sq.product_id = src.product_id
  AND sq.location_id = :location_id
  AND sq.lot_id IS NULL
  AND sq.package_id IS NULL
  AND sq.owner_id IS NULL;

INSERT INTO stock_quant (
    product_id,
    location_id,
    company_id,
    create_uid,
    write_uid,
    quantity,
    reserved_quantity,
    in_date,
    create_date,
    write_date
)
SELECT
    src.product_id,
    :location_id,
    loc.company_id,
    :owner_user_id,
    :owner_user_id,
    src.inventory_qty,
    0,
    now(),
    now(),
    now()
FROM tmp_stock_input src
JOIN stock_location loc
    ON loc.id = :location_id
WHERE NOT EXISTS (
    SELECT 1
    FROM stock_quant sq
    WHERE sq.product_id = src.product_id
      AND sq.location_id = :location_id
      AND sq.lot_id IS NULL
      AND sq.package_id IS NULL
      AND sq.owner_id IS NULL
);

CREATE TEMP TABLE tmp_image_input AS
SELECT
    wi.sku,
    t.product_tmpl_id,
    wi.image_url,
    wi.image_path,
    COALESCE(NULLIF(trim(wi.mimetype), ''), 'application/octet-stream') AS mimetype,
    wi.file_size,
    wi.checksum,
    wi.db_datas_base64
FROM stg_wix_images wi
JOIN tmp_product_targets t
    ON t.sku = wi.sku
WHERE lower(COALESCE(wi.download_status, '')) = 'downloaded'
  AND wi.db_datas_base64 IS NOT NULL;

WITH existing AS (
    SELECT MIN(id) AS attachment_id, res_id
    FROM ir_attachment
    WHERE res_model = 'product.template'
      AND res_field = 'image_1920'
    GROUP BY res_id
)
UPDATE ir_attachment ia
SET
    name = 'image_1920',
    type = 'binary',
    url = NULL,
    store_fname = NULL,
    checksum = img.checksum,
    mimetype = img.mimetype,
    file_size = img.file_size,
    db_datas = decode(img.db_datas_base64, 'base64'),
    public = false,
    write_uid = :owner_user_id,
    write_date = now()
FROM tmp_image_input img
JOIN existing e
    ON e.res_id = img.product_tmpl_id
WHERE ia.id = e.attachment_id;

INSERT INTO ir_attachment (
    res_id,
    company_id,
    file_size,
    create_uid,
    write_uid,
    name,
    res_model,
    res_field,
    type,
    url,
    checksum,
    mimetype,
    public,
    create_date,
    write_date,
    db_datas
)
SELECT
    img.product_tmpl_id,
    NULL,
    img.file_size,
    :owner_user_id,
    :owner_user_id,
    'image_1920',
    'product.template',
    'image_1920',
    'binary',
    NULL,
    img.checksum,
    img.mimetype,
    false,
    now(),
    now(),
    decode(img.db_datas_base64, 'base64')
FROM tmp_image_input img
WHERE NOT EXISTS (
    SELECT 1
    FROM ir_attachment ia
    WHERE ia.res_model = 'product.template'
      AND ia.res_field = 'image_1920'
      AND ia.res_id = img.product_tmpl_id
);

\echo === Resultado apply ===
SELECT COUNT(*) AS internal_categories_resolved FROM tmp_internal_category_ids;
SELECT COUNT(*) AS public_categories_resolved FROM tmp_public_category_ids;
SELECT COUNT(*) AS affected_product_templates FROM tmp_product_targets;
SELECT COUNT(*) AS stock_rows_source FROM tmp_stock_input;
SELECT COUNT(*) AS image_rows_source FROM tmp_image_input;
\echo Ejecuta post_import_odoo.py via odoo shell para regenerar image_1024/image_512 y validar el lote.

\else
\echo No se aplicaron cambios. Ejecuta con -v apply=1 para escribir en la base.
\endif

\echo === Validacion final ===
SELECT
    COUNT(*) AS products_in_db_for_staged_skus
FROM tmp_wix_products src
JOIN product_product pp
    ON lower(COALESCE(pp.default_code, '')) = lower(src.sku);

SELECT
    src.sku,
    pt.name ->> 'en_US' AS product_name,
    pp.default_code,
    pt.list_price,
    pp.standard_price,
    pt.is_published,
    pt.categ_id
FROM tmp_wix_products src
JOIN product_product pp
    ON lower(COALESCE(pp.default_code, '')) = lower(src.sku)
JOIN product_template pt
    ON pt.id = pp.product_tmpl_id
ORDER BY src.sku
LIMIT 10;
