# Documentacion tecnica de `dreyes_portal`

## Objetivo del modulo

`dreyes_portal` concentra exclusivamente la experiencia de acceso web de DReyes:

- redireccion de visitantes anonimos al login;
- personalizacion visual del login;
- personalizacion visual del registro;
- redireccion al home del sitio despues de login o signup.

La logica de formulario extendido fue movida al modulo `dreyes_dist`.

## Componentes principales

### Controladores

Archivo: `controllers/main.py`

Clases:

- `DreyesPortalRedirectMixin`
- `DreyesPortalController`
- `DreyesPortalHome`
- `DreyesPortalSignup`

Comportamiento:

- `/` redirige al login si el usuario es publico;
- `/` muestra el home del `website` si el usuario ya inicio sesion;
- el login exitoso vuelve al home del sitio cuando no se especifica otro `redirect`;
- el signup exitoso vuelve al home del sitio.

### Modelos

Archivo: `models/website.py`

Campos de branding del login/registro:

- `dreyes_auth_logo`
- `dreyes_auth_panel_start`
- `dreyes_auth_panel_end`
- `dreyes_auth_accent`
- `dreyes_auth_background`
- `dreyes_auth_welcome`
- `dreyes_auth_tagline`
- `dreyes_auth_footer_left`
- `dreyes_auth_footer_right`
- `dreyes_auth_login_title`
- `dreyes_auth_login_subtitle`
- `dreyes_auth_signup_title`
- `dreyes_auth_signup_subtitle`

Archivo: `models/res_config_settings.py`

Expone esos campos como `related` para configurarlos desde Website.

### Vistas y assets

- `templates/dreyes_portal_layout.xml`
- `templates/dreyes_login.xml`
- `templates/dreyes_register.xml`
- `views/res_config_settings_views.xml`
- `static/src/scss/login.scss`
- `static/src/js/login_page.js`

## Dependencias

- `base`
- `web`
- `website`
- `auth_signup`

## Notas de integracion

- Si se necesita el flujo de datos obligatorios despues del registro, instalar `dreyes_dist`.
- `dreyes_portal` ya no redirige a `/profile/new`, `/profile/view/<id>` ni `/profile/complete`.
