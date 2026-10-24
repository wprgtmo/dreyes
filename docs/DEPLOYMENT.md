# Instalar o restaurar D'Reyes en Odoo 19

## Preparar el código

```bash
git clone --branch 19.0 --recurse-submodules https://github.com/wprgtmo/dreyes.git
cd dreyes
cp .env.example .env
cp config/odoo.conf.example config/odoo.conf
```

Configurar una contraseña PostgreSQL privada en `.env` y una contraseña maestra
de bases de datos en `config/odoo.conf`. Si se usará Clover, configurar una clave
estable en `CLOVER_TOKEN_ENCRYPTION_KEY`; conservarla junto con los respaldos privados.
No cargar credenciales reales en Git.

```bash
docker compose up -d
```

La configuración crea volúmenes nuevos para PostgreSQL y `/var/lib/odoo`.
No utiliza nombres de volúmenes de la instalación de desarrollo.

## Restaurar los sitios ya migrados

Conservar privadamente el respaldo `dreyes19_with_local_modules.zip`, que incluye
la base de Odoo 19, páginas, menús, imágenes y módulos instalados. No está en GitHub.

Para acceder a un servidor remoto durante la restauración:

```bash
ssh -L 18069:127.0.0.1:8069 USUARIO@SERVIDOR
```

Abrir `http://localhost:18069/web/database/manager` en el equipo local y restaurar
el ZIP como `dreyes19_websites`, usando la contraseña maestra configurada.
Mantener la copia neutralizada durante la validación.

No instalar primero una base vacía con el mismo nombre si se va a restaurar el ZIP.
Un respaldo de Odoo 18 necesita migración de base; no se convierte al restaurarlo
directamente en Odoo 19.

## Configurar el servidor publicado

1. Configurar el dominio de Latin Market y el de Distribution en sus sitios de Odoo.
2. Configurar el proxy inverso y HTTPS. Activar `proxy_mode` cuando Odoo esté detrás del proxy.
3. Configurar `web.base.url` para el dominio administrativo elegido y revisar la opción de congelación de esa URL.
4. Cambiar las credenciales del administrador restaurado y comprobar los accesos por compañía y por módulo.
5. Configurar correo y probar formularios y pedidos con datos de prueba.
6. Revisar la neutralización y reactivar solamente las integraciones y tareas necesarias.
7. Tras restaurar, restringir el administrador de bases de datos según la política del servidor.

El archivo de ejemplo mantiene `max_cron_threads = 0` y escucha sólo en loopback
para la fase de restauración. Es necesario completar estos ajustes para producción.
Un proxy en otro contenedor requiere una red compartida o una configuración de
puerto apropiada; `127.0.0.1:8069` corresponde al host Docker.

## Actualizar código de la rama 19.0

Tomar un respaldo de base y filestore antes de actualizar:

```bash
git pull --ff-only
git submodule update --init --recursive
docker compose stop web
docker compose run --rm web odoo -d dreyes19_websites -u dreyes_portal,dreyes_client,dreyes_dist,dreyes_dist_clients,dreyes_product_pricing,dreyes_clover_sync,pwa_badge,web_responsive,web_pwa_customize --stop-after-init
docker compose up -d web
```

El commit fijado del submódulo se actualiza explícitamente en Git después de probarlo;
no se utiliza automáticamente el último commit de OCA al desplegar.
