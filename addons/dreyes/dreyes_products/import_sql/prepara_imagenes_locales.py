import argparse
import base64
import csv
import hashlib
import mimetypes
import pathlib


def parse_args() -> argparse.Namespace:
    default_root = pathlib.Path("/mnt/extra-addons/dreyes/dreyes_products/import_sql/output")
    parser = argparse.ArgumentParser(
        description="Genera stg_wix_images.csv a partir de una carpeta local de imagenes."
    )
    parser.add_argument(
        "--images-dir",
        default=str(default_root / "images_no_bg"),
        help="Carpeta con imagenes finales a cargar a Odoo. El nombre del archivo debe ser el SKU.",
    )
    parser.add_argument(
        "--csv-output",
        default=str(default_root / "stg_wix_images.csv"),
        help="Ruta del CSV auxiliar para stg_wix_images.",
    )
    return parser.parse_args()


def build_row(file_path: pathlib.Path) -> dict[str, str]:
    raw = file_path.read_bytes()
    sku = file_path.stem.strip()
    mimetype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    checksum = hashlib.sha1(raw).hexdigest()
    return {
        "sku": sku,
        "image_url": str(file_path),
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
    images_dir = pathlib.Path(args.images_dir)
    csv_output = pathlib.Path(args.csv_output)
    csv_output.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(
        [
            path
            for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ],
        key=lambda p: p.name.lower(),
    )

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

    with csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for file_path in files:
            writer.writerow(build_row(file_path))

    print(f"csv={csv_output} files={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
