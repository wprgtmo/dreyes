# `pwa_badge`: documentacion tecnica

## Objetivo del modulo

`pwa_badge` complementa a `web_pwa_customize` para cubrir dos necesidades:

1. personalizar mejor la experiencia de instalacion PWA en iPhone y iPad;
2. reflejar en el icono instalado de la app un contador de notificaciones, con fallback visual cuando la plataforma no soporta `Badging API`.

El modulo esta pensado para Odoo 19 y se apoya en los metadatos/icono ya gestionados por `web_pwa_customize`.

## Dependencias y alcance

Dependencias declaradas:

- `web`
- `mail`
- `bus`
- `web_pwa_customize`

Responsabilidades del modulo:

- exponer un endpoint con el contador actual del usuario;
- calcular el badge a partir de actividades y/o mail;
- extender el `manifest.webmanifest` con `id`;
- publicar `apple-touch-icon` para iPhone/iPad;
- inyectar meta tags PWA en `web.layout`;
- sincronizar badge y fallback visual desde el frontend backend.

Queda fuera del alcance actual:

- web push en background;
- service worker propio;
- sincronizacion offline;
- badge real garantizado en Android, porque depende de navegador y launcher.

## Estructura del addon

### Backend

- `controllers/main.py`
  - define `/pwa_badge/count`;
  - devuelve JSON para usuario autenticado.

- `controllers/webmanifest.py`
  - hereda el controlador de `web_pwa_customize`;
  - añade `manifest["id"]`.

- `models/res_users.py`
  - concentra el calculo del contador;
  - expone `_get_pwa_badge_counts()`;
  - expone helpers mas pequenos para extender o sobreescribir.

- `models/res_config_settings.py`
  - define los ajustes de configuracion;
  - genera/elimina el `apple-touch-icon`;
  - valida que la fuente para Apple sea PNG `>= 512x512`.

- `models/ir_http.py`
  - prepara datos compartidos para templates;
  - compone el `manifest_id`.

### Frontend

- `static/src/js/pwa_badge_service.esm.js`
  - registra un servicio OWL en `registry.category("services")`;
  - consulta `/pwa_badge/count`;
  - llama a `navigator.setAppBadge()` o `navigator.clearAppBadge()` cuando existe soporte;
  - actualiza `document.title` cuando el fallback esta activo;
  - escucha `focus`, `visibilitychange` y eventos de `bus_service`.

### Vistas

- `views/res_config_settings_views.xml`
  - añade la UI de configuracion al bloque PWA de Ajustes.

- `views/web_templates.xml`
  - inyecta:
    - `apple-touch-icon`
    - `apple-mobile-web-app-capable`
    - `apple-mobile-web-app-title`
    - `mobile-web-app-capable`
    - `theme-color`

## Flujo de datos

### 1. Calculo del contador

El flujo actual es:

1. el frontend hace `GET /pwa_badge/count`;
2. el controlador llama a `request.env.user.sudo()._get_pwa_badge_counts()`;
3. el modelo calcula:
   - `activities_count`: `mail.activity` asignadas al usuario;
   - `mail_count`: `message_needaction_counter` del partner, o `message_unread_counter` si el primero no existe;
   - `total_count`: segun `pwa_badge.count_mode`;
4. el frontend aplica badge nativo o fallback.

### 2. Generacion del icono Apple

El flujo actual es:

1. el administrador guarda ajustes;
2. `set_values()` busca el icono base de `web_pwa_customize`;
3. si no hay icono, elimina `/pwa_badge/apple-touch-icon.png`;
4. si hay icono, valida que sea PNG `>= 512x512`;
5. genera un PNG `180x180`;
6. crea o actualiza un `ir.attachment` con URL fija `/pwa_badge/apple-touch-icon.png`;
7. `web.layout` publica esa URL en el `head`.

## Parametros de sistema

El modulo usa estos `ir.config_parameter`:

- `pwa_badge.count_mode`
  - `activities`
  - `mail`
  - `both`

- `pwa_badge.android_mode`
  - `best_effort`
  - `system_notifications`

- `pwa_badge.title_fallback`
  - booleano serializado como texto

Tambien consume parametros creados por `web_pwa_customize`:

- `pwa.manifest.short_name`
- `pwa.manifest.background_color`
- `pwa.manifest.theme_color`

## Contratos tecnicos utiles

### Endpoint `/pwa_badge/count`

Metodo:

- `GET`
- `POST`

Autenticacion:

- `auth="user"`

Respuesta JSON esperada:

```json
{
  "activities_count": 3,
  "mail_count": 5,
  "total_count": 8,
  "android_mode": "best_effort",
  "count_mode": "both",
  "title_fallback": true
}
```

### Helper principal

Metodo principal para extensiones:

```python
res.users._get_pwa_badge_counts()
```

Helpers disponibles:

- `_get_pwa_badge_count_mode()`
- `_get_pwa_badge_android_mode()`
- `_get_pwa_badge_title_fallback()`
- `_get_pwa_badge_mail_count()`
- `_get_pwa_badge_activities_count()`
- `_get_pwa_badge_total_count(activities_count, mail_count, count_mode)`

Si otro addon necesita cambiar la semantica del badge, la opcion mas limpia es heredar `res.users` y sobreescribir `_get_pwa_badge_counts()` o alguno de los helpers pequenos.

## Limitaciones de plataforma

### iPhone / iPad

- `setAppBadge` y `clearAppBadge` solo tienen sentido en una PWA anclada a pantalla de inicio.
- el badge visible depende del permiso de notificaciones del sistema.
- `apple-touch-icon` tiene prioridad sobre iconos del manifest en escenarios Apple.

### Android

- Chromium en Android no expone `Badging API` de la misma forma que Safari iOS.
- el badge del icono instalado depende de notificaciones visibles del sistema y del launcher.
- por eso `system_notifications` es una estrategia de compatibilidad, no una garantia.

## Riesgos y puntos a revisar si se amplia

- El listener generico de `bus_service` se usa como resincronizacion oportunista. Si en el futuro existe un canal de negocio mas preciso, conviene suscribirse a ese canal.
- La seleccion del icono base hoy asume las URLs de `web_pwa_customize` (`/web_pwa_customize/icon.png` o `.svg`). Si ese addon cambia su estrategia de almacenamiento, habra que adaptar la busqueda.
- El fallback del titulo afecta solo el documento abierto, no una notificacion del sistema.
- `Notification.requestPermission()` solo funciona correctamente bajo interaccion explicita del usuario, por eso el boton de Ajustes es importante.

## Pruebas disponibles

### Python

Archivo:

- `tests/test_pwa_badge.py`

Cubre:

- calculo de `activities`, `mail` y `total`;
- respuesta del endpoint;
- presencia de `id` en el manifest;
- presencia de `apple-touch-icon` en layout;
- validacion de SVG para icono Apple.

### JS

Archivo:

- `static/tests/pwa_badge_service.test.js`

Cubre:

- prefijo del titulo;
- limpieza de prefijo;
- uso de `setAppBadge`;
- uso de `clearAppBadge`.

## Recomendaciones para agentes y desarrolladores

- Si vas a cambiar el origen del contador, hazlo en `res_users.py` antes de tocar el JS.
- Si vas a tocar iconos o experiencia de instalacion, revisa primero la integracion con `web_pwa_customize`.
- Si quieres soporte real de Android con mayor fidelidad, la siguiente pieza logica es introducir Web Push y service worker, no seguir cargando logica al contador actual.
- Si algo falla solo en iPhone, valida primero:
  - que la app este instalada como PWA;
  - que exista `apple-touch-icon`;
  - que el usuario haya concedido permisos de notificaciones;
  - que el icono base sea PNG `>= 512x512`.
