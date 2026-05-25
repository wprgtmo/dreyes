"""Postproceso Odoo para completar derivados tras un import SQL.

Se ejecuta dentro de `odoo shell` y usa el entorno `env` ya disponible.
Objetivos:
- regenerar `image_1024`, `image_512`, etc. a partir de `image_1920`
- verificar cobertura basica de productos, stock e imagenes del lote staged
"""

BATCH_SIZE = 25


def _staged_skus():
    env.cr.execute(
        """
        SELECT DISTINCT ON (trim(COALESCE("sku", '')))
               trim(COALESCE("sku", '')) AS sku
        FROM stg_wix_catalog
        WHERE upper(COALESCE("fieldType", '')) = 'PRODUCT'
          AND NULLIF(trim(COALESCE("sku", '')), '') IS NOT NULL
        ORDER BY trim(COALESCE("sku", '')), trim(COALESCE("name", ''))
        """
    )
    return [row[0] for row in env.cr.fetchall()]


def _product_domain(staged_skus):
    return [("default_code", "in", staged_skus)]


DERIVED_IMAGE_FIELDS = ["image_1024", "image_512", "image_256", "image_128"]


def regenerate_image_variants(products):
    derived_attachments = env["ir.attachment"].search(
        [
            ("res_model", "=", "product.template"),
            ("res_id", "in", products.ids),
            ("res_field", "in", DERIVED_IMAGE_FIELDS),
        ]
    )
    if derived_attachments:
        print(f"deleting_stale_derived_attachments={len(derived_attachments)}")
        derived_attachments.unlink()
        env.cr.commit()

    updated = 0
    failed = []
    for product in products:
        if product.image_1920:
            try:
                # Force ORM recomputation of resized image fields.
                product.write({"image_1920": product.image_1920})
                updated += 1
                if updated % BATCH_SIZE == 0:
                    env.cr.commit()
                    print(f"image_variants_regenerated={updated}")
            except Exception as exc:
                env.cr.rollback()
                failed.append((product.default_code, str(exc)))
    env.cr.commit()
    print(f"image_variants_regenerated_total={updated}")
    print(f"image_variants_failed_total={len(failed)}")
    for sku, error in failed[:20]:
        print(f"image_variants_failed sku={sku} error={error}")


def print_summary(products):
    product_variants = products.product_variant_ids
    quant_count = env["stock.quant"].search_count(
        [
            ("product_id", "in", product_variants.ids),
            ("location_id", "=", 8),
            ("lot_id", "=", False),
            ("package_id", "=", False),
            ("owner_id", "=", False),
        ]
    )
    attachment_count = env["ir.attachment"].search_count(
        [
            ("res_model", "=", "product.template"),
            ("res_field", "=", "image_1920"),
            ("res_id", "in", products.ids),
        ]
    )
    missing_derived = products.filtered(
        lambda p: p.image_1920 and (not p.image_1024 or not p.image_512)
    )
    print(f"staged_products={len(products)}")
    print(f"staged_variants={len(product_variants)}")
    print(f"stock_quants_at_wh_stock={quant_count}")
    print(f"image_attachments={attachment_count}")
    print(f"products_missing_derived_images={len(missing_derived)}")
    if missing_derived:
        print("missing_derived_sample=" + ",".join(missing_derived.mapped("default_code")[:20]))


def main():
    staged_skus = _staged_skus()
    if not staged_skus:
        print("No hay SKUs en stg_wix_catalog. Ejecuta 01_stage.sql antes del postproceso.")
        return

    products = env["product.template"].search(_product_domain(staged_skus))
    print(f"staged_skus={len(staged_skus)}")
    print(f"matched_templates={len(products)}")
    regenerate_image_variants(products)
    print_summary(products)


main()
