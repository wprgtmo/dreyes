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

- Los usuarios publicos pueden navegar el sitio sin iniciar sesion.
- Tras login o signup devuelve al usuario autenticado al home del sitio.
- El login o registro queda para el momento en que otro flujo del sitio lo requiera, por ejemplo checkout.
- El formulario extendido fue separado al modulo `dreyes_dist`.

Documentacion ampliada en `doc/README_TECNICO.md`.
