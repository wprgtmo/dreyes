import argparse
import base64
import csv
import decimal
import hashlib
import mimetypes
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def parse_args() -> argparse.Namespace:
    default_root = pathlib.Path("/mnt/extra-addons/dreyes/productos")
    default_import_root = default_root / "import_sql"
    parser = argparse.ArgumentParser(
        description="Descarga imagenes Wix y genera stg_wix_images.csv para psql."
    )
    parser.add_argument(
        "--catalog-csv",
        default=str(default_root / "catalog_products.csv"),
        help="Ruta al CSV principal de catalogo Wix.",
    )
    parser.add_argument(
        "--inventory-csv",
        default=str(default_root / "product-inventory-v3_2026-05-04-2026-05-05.csv"),
        help="Ruta al CSV de inventario exportado de Wix.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(default_import_root / "output" / "images"),
        help="Directorio donde se guardaran las imagenes descargadas.",
    )
    parser.add_argument(
        "--csv-output",
        default=str(default_import_root / "output" / "stg_wix_images.csv"),
        help="CSV auxiliar para cargar en stg_wix_images.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout en segundos por descarga.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita la cantidad de SKUs a procesar. 0 = sin limite.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Si la imagen local ya existe, reutiliza el archivo y evita descargarlo de nuevo.",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=0,
        help="Espera opcional entre descargas para no golpear al origen.",
    )
    parser.add_argument(
        "--image-mode",
        choices=["original", "fit1200", "thumb"],
        default="original",
        help="Modo de descarga para URLs de Wix. 'original' usa el asset original, 'fit1200' pide una version grande, 'thumb' conserva la URL exportada.",
    )
    return parser.parse_args()


def read_inventory_rows(path: pathlib.Path):
    encodings = ["latin-1", "utf-8-sig", "utf-8"]
    last_error = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                return list(reader)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"No se pudo leer {path} con encodings soportados: {last_error}")


def build_catalog_name_map(path: pathlib.Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("fieldType") or "").strip().upper() != "PRODUCT":
                continue
            name = (row.get("name") or "").strip().lower()
            sku = normalize_sku(row.get("sku") or "")
            if name and sku:
                result[name] = sku
    return result


def sanitize_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value.strip())
    return safe or "sin_sku"


def normalize_sku(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return ""
    upper_value = value.upper()
    if "E+" in upper_value or "E-" in upper_value:
        try:
            normalized = format(decimal.Decimal(upper_value), "f")
            if "." in normalized:
                normalized = normalized.rstrip("0").rstrip(".")
            return normalized
        except decimal.InvalidOperation:
            return value
    if value.endswith(".0"):
        return value[:-2]
    return value


def guess_extension(url: str, mimetype: str | None) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = pathlib.Path(parsed.path).suffix.lower()
    if suffix:
        return suffix
    if mimetype:
        guessed = mimetypes.guess_extension(mimetype.split(";")[0].strip())
        if guessed:
            return guessed
    return ".img"


def transform_wix_image_url(url: str, mode: str) -> str:
    """Convierte thumbnails Wix en URLs de mayor resolucion."""
    if not url or "static.wixstatic.com/media/" not in url:
        return url
    if mode == "thumb":
        return url

    match = re.search(r"(https://static\.wixstatic\.com/media/[^/]+)", url)
    if not match:
        return url

    base_url = match.group(1)
    base_suffix = pathlib.Path(urllib.parse.urlparse(base_url).path).suffix.lower()
    if mode == "original":
        # Odoo/Pillow in this stack cannot decode AVIF reliably. Ask Wix for a
        # large WEBP derivative instead of the raw AVIF asset.
        if base_suffix == ".avif":
            return f"{base_url}/v1/fit/w_1200,h_1200,q_95/file.webp"
        return base_url

    suffix = base_suffix or ".jpg"
    return f"{base_url}/v1/fit/w_1200,h_1200,q_95,enc_auto/file{suffix}"


def collect_unique_skus(rows: list[dict], catalog_name_map: dict[str, str], limit: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in rows:
        raw_sku = normalize_sku(row.get("SKU") or "")
        product_name = (row.get("Product name") or "").strip()
        resolved_sku = catalog_name_map.get(product_name.lower(), raw_sku)
        url = (row.get("Product image") or "").strip()
        if not resolved_sku:
            continue
        current = seen.get(resolved_sku)
        if current is None:
            cloned = dict(row)
            cloned["_resolved_sku"] = resolved_sku
            seen[resolved_sku] = cloned
            continue
        if not (current.get("Product image") or "").strip() and url:
            cloned = dict(row)
            cloned["_resolved_sku"] = resolved_sku
            seen[resolved_sku] = cloned
    items = list(seen.values())
    if limit > 0:
        return items[:limit]
    return items


def build_row_for_existing_file(
    sku: str,
    url: str,
    file_path: pathlib.Path,
    explicit_mimetype: str | None = None,
) -> dict:
    raw = file_path.read_bytes()
    checksum = hashlib.sha1(raw).hexdigest()
    mimetype = explicit_mimetype or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return {
        "sku": sku,
        "image_url": url,
        "image_path": str(file_path),
        "mimetype": mimetype,
        "file_size": str(len(raw)),
        "checksum": checksum,
        "db_datas_base64": base64.b64encode(raw).decode("ascii"),
        "download_status": "downloaded",
        "error_message": "",
    }


def download_image(
    sku: str,
    url: str,
    output_dir: pathlib.Path,
    timeout: int,
    skip_existing: bool,
    image_mode: str,
) -> dict:
    if not url:
        return {
            "sku": sku,
            "image_url": "",
            "image_path": "",
            "mimetype": "",
            "file_size": "",
            "checksum": "",
            "db_datas_base64": "",
            "download_status": "missing_url",
            "error_message": "El SKU no trae Product image.",
        }

    download_url = transform_wix_image_url(url, image_mode)
    headers = {"User-Agent": "dreyes-wix-import/1.0"}
    request = urllib.request.Request(download_url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            mimetype = response.headers.get_content_type() or "application/octet-stream"
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {
            "sku": sku,
            "image_url": download_url,
            "image_path": "",
            "mimetype": "",
            "file_size": "",
            "checksum": "",
            "db_datas_base64": "",
            "download_status": "error",
            "error_message": str(exc),
        }

    extension = guess_extension(download_url, mimetype)
    file_name = f"{sanitize_filename(sku)}{extension}"
    file_path = output_dir / file_name

    if skip_existing and file_path.exists():
        return build_row_for_existing_file(sku, download_url, file_path, explicit_mimetype=mimetype)

    file_path.write_bytes(raw)
    checksum = hashlib.sha1(raw).hexdigest()

    return {
        "sku": sku,
        "image_url": download_url,
        "image_path": str(file_path),
        "mimetype": mimetype,
        "file_size": str(len(raw)),
        "checksum": checksum,
        "db_datas_base64": base64.b64encode(raw).decode("ascii"),
        "download_status": "downloaded",
        "error_message": "",
    }


def main() -> int:
    args = parse_args()
    catalog_path = pathlib.Path(args.catalog_csv)
    inventory_path = pathlib.Path(args.inventory_csv)
    output_dir = pathlib.Path(args.output_dir)
    csv_output = pathlib.Path(args.csv_output)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_output.parent.mkdir(parents=True, exist_ok=True)

    rows = read_inventory_rows(inventory_path)
    catalog_name_map = build_catalog_name_map(catalog_path)
    unique_rows = collect_unique_skus(rows, catalog_name_map, args.limit)

    fieldnames = [
        "sku",
        "image_url",
        "image_path",
        "mimetype",
        "file_size",
        "checksum",
        "db_datas_base64",
        "download_status",
        "error_message",
    ]

    processed = 0
    ok = 0
    failed = 0

    with csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for row in unique_rows:
            sku = (row.get("_resolved_sku") or "").strip()
            url = (row.get("Product image") or "").strip()
            result = download_image(
                sku=sku,
                url=url,
                output_dir=output_dir,
                timeout=args.timeout,
                skip_existing=args.skip_existing,
                image_mode=args.image_mode,
            )
            writer.writerow(result)

            processed += 1
            if result["download_status"] == "downloaded":
                ok += 1
                print(f"[OK] {sku} -> {result['image_path']}")
            else:
                failed += 1
                print(f"[WARN] {sku} -> {result['download_status']}: {result['error_message']}")

            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)

    print(
        f"Procesados={processed} descargados={ok} con_error={failed} csv={csv_output}",
        file=sys.stderr if failed else sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
