# `dreyes_portal`

Modulo de entrada al portal web de DReyes.

## Incluye

- templates de login;
- templates de registro;
- helpers de redireccion para entrada publica, login y signup;
- ruta raiz del portal.

## Dependencias

- `base`
- `web`
- `auth_signup`
- `dreyes_permission`

## Notas

- Centraliza la logica de destino inicial del usuario segun perfil activo y partida activa.
- Debe probarse siempre junto con creacion de usuario, perfil por defecto y sincronizacion de grupos.

Documentacion ampliada en `../docs/modulos/dreyes_portal.md`.
