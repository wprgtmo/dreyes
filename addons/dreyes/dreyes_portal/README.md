# `dreyes_portal`

Modulo de acceso web para DReyes.

## Incluye

- templates de login;
- templates de registro;
- branding configurable del acceso;
- helpers de redireccion para entrada publica, login y signup;
- ruta raiz del portal.

## Dependencias

- `base`
- `web`
- `website`
- `auth_signup`

## Notas

- Redirige a usuarios publicos al login.
- Tras login o signup devuelve al usuario autenticado al home del sitio.
- El formulario extendido fue separado al modulo `dreyes_dist`.

Documentacion ampliada en `doc/README_TECNICO.md`.
