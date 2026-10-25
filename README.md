# D'Reyes — Odoo Community 19.0

Repositorio de módulos locales de D'Reyes, organizado por ramas de versión.

| Rama | Uso |
| --- | --- |
| `18.0` | Código e historial de Odoo 18 conservados desde `master` |
| `19.0` | Módulos adaptados a Odoo 19 y configuración reproducible |

Cada rama contiene su propia versión de los módulos. Los cambios de Odoo 19
se desarrollan en `19.0`; no se fusiona esta rama completa en `18.0`.

## Módulos

Los módulos locales están en `addons/`, siguiendo la estructura de OCA.

| Módulo | Función |
| --- | --- |
| `dreyes_portal` | Acceso, registro y branding de los sitios |
| `dreyes_client` | Panel del cliente en `/my/home` |
| `dreyes_dist` | Registro, revisión y aprobación de distribuidores |
| `dreyes_dist_clients` | Gestión administrativa de distribuidores |
| `dreyes_product_pricing` | Consulta y edición de precios por producto y lista |
| `dreyes_clover_sync` | Integración de catálogo, inventario y pedidos con Clover |
| `pwa_badge` | Contadores e iconos de la aplicación PWA |

OCA Web se incorpora como submódulo en `addons/oca/web`, en su rama `19.0` y fijado
al commit probado `884c09e3ed1b0b8d651e9827b84d3d77a7d98ff4`.
Se utilizan `web_responsive` y `web_pwa_customize`.

## Clonar

```bash
git clone --branch 19.0 --recurse-submodules https://github.com/wprgtmo/dreyes.git
cd dreyes
```

Si el repositorio ya está clonado:

```bash
git switch 19.0
git submodule update --init --recursive
```

Para Odoo 18, clonar o seleccionar la rama `18.0` en una carpeta independiente.

## Arranque de Odoo 19

Requisitos: Docker Engine con Docker Compose v2 y Git.

```bash
cp .env.example .env
cp config/odoo.conf.example config/odoo.conf
```

Antes de iniciar, reemplazar las contraseñas de ejemplo de `.env` y
`config/odoo.conf`. La contraseña maestra de bases de datos es independiente
de la contraseña de acceso del usuario administrador.

```bash
docker compose up -d
docker compose ps
```

Odoo escucha localmente en `http://localhost:8069`. PostgreSQL no publica un puerto.
El proyecto crea volúmenes propios para la base y los adjuntos en un servidor nuevo.

Ver [instalación y restauración](docs/DEPLOYMENT.md) para conservar los dos sitios.

## Base nueva sin contenido web

Si no se va a restaurar un respaldo, inicializar una base vacía e instalar los módulos:

```bash
docker compose stop web
docker compose run --rm web odoo -d dreyes19_websites -i dreyes_portal,dreyes_client,dreyes_dist,dreyes_dist_clients,dreyes_product_pricing,dreyes_clover_sync,pwa_badge,web_responsive,web_pwa_customize --without-demo --stop-after-init
docker compose up -d web
```

Este paso crea una base nueva. El diseño y el contenido de los sitios existentes
se recuperan restaurando su respaldo de Odoo 19, como explica la guía de despliegue.

## Pruebas

```bash
docker compose -f compose.tests.yml run --rm web
```

Las pruebas usan una base y volúmenes independientes. Incluyen el portal del cliente,
los permisos y el carrito de distribuidores, precios, PWA e integración Clover simulada.
La migración se verificó con 50 pruebas funcionales/HTTP; no se conectó a Clover real.

## Archivos privados

Guardar fuera de Git los respaldos, exportaciones de sitios, filestore, claves Clover,
contraseñas y configuraciones reales. Los ejemplos incluidos usan valores de sustitución.
Las páginas construidas con el editor de Odoo y sus imágenes viven en la base y el
filestore: el código fuente por sí solo no incluye esos contenidos.

## Licencias

Consultar el manifiesto y los avisos de cada módulo. La dependencia OCA conserva
sus propios autores y licencias en su repositorio.
