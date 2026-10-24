# Guia funcional de `pwa_badge`

## Que hace este modulo

`pwa_badge` mejora la app instalada como PWA para que:

- el icono de instalacion funcione mejor en iPhone y iPad;
- el icono pueda mostrar una cantidad de pendientes o notificaciones;
- el administrador pueda decidir que numero mostrar y como comportarse en Android.

Este modulo no sustituye a `web_pwa_customize`. Lo complementa.

## Requisitos previos

Antes de usar `pwa_badge`, conviene tener configurado en `web_pwa_customize`:

- nombre corto de la web app;
- colores de la PWA;
- icono principal de la PWA.

Para iPhone/iPad, el icono principal debe ser:

- formato PNG;
- tamano minimo `512 x 512`.

Si el icono es SVG o es mas pequeno, el modulo no podra generar correctamente el icono Apple.

## Dónde se configura

Los ajustes aparecen dentro de la seccion PWA de Ajustes.

## Explicacion de cada parametro

### 1. Fuente del badge

Este ajuste define que numero se mostrara en el badge de la app instalada.

Valores disponibles:

- `Solo actividades`
  - muestra solo las actividades pendientes asignadas al usuario;
  - es util cuando el badge debe representar tareas por hacer.

- `Solo notificaciones mail`
  - muestra solo el contador de notificaciones o mensajes pendientes de mail/discuss, segun lo disponible en el sistema;
  - es util cuando el badge debe representar comunicacion pendiente.

- `Ambas`
  - suma actividades pendientes y notificaciones mail;
  - es el valor mas amplio y el predeterminado.

Significado practico:

- si eliges `Solo actividades`, el badge responde a trabajo pendiente;
- si eliges `Solo notificaciones mail`, responde a mensajes o alertas pendientes;
- si eliges `Ambas`, responde a una carga total de pendientes.

### 2. Comportamiento Android

Este ajuste define la estrategia para Android.

Valores disponibles:

- `Best effort`
  - el sistema intentara mantener el contador dentro de la PWA y en el titulo si hace falta;
  - no fuerza notificaciones del sistema;
  - es la opcion mas conservadora;
  - recomendable cuando no quieres generar avisos del sistema.

- `Notificaciones del sistema`
  - ademas de resincronizar el contador, intentara usar notificaciones del navegador cuando lleguen eventos compatibles;
  - mejora la posibilidad de que algunos launchers Android reflejen badge en el icono;
  - depende del navegador, del launcher y de los permisos del usuario.

Significado practico:

- `Best effort` reduce ruido visual y es la opcion base;
- `Notificaciones del sistema` busca mejor compatibilidad con Android, pero no garantiza que todos los telefonos muestren badge.

## Importante sobre Android

En Android no existe una garantia universal de badge para PWAs.

El resultado final depende de:

- navegador instalado;
- launcher del telefono;
- permisos de notificaciones;
- forma en que Android decide mostrar badges.

Por eso este modulo ofrece estrategias, no una promesa identica en todos los dispositivos.

## 3. Fallback en el titulo

Este ajuste activa o desactiva un plan alternativo cuando el navegador no soporta badge nativo.

Valores posibles:

- `Activado`
  - si no se puede mostrar badge nativo, el sistema antepone el numero al titulo de la pestana o ventana;
  - ejemplo: `(3) Ventas`.

- `Desactivado`
  - si no hay soporte nativo, no se mostrara ese indicador alternativo en el titulo.

Significado practico:

- activado mejora la visibilidad en navegadores sin soporte;
- desactivado mantiene el titulo limpio.

Valor por defecto:

- activado.

## 4. Solicitar permiso del navegador

Este boton sirve para pedir permiso de notificaciones al navegador del usuario.

Para que sirve:

- en iPhone/iPad es importante para que el sistema pueda mostrar el badge de la app instalada;
- en Android mejora escenarios donde las notificaciones del sistema participan en el badge.

Uso recomendado:

1. abrir Odoo desde el navegador o PWA donde se quiere usar el badge;
2. entrar en Ajustes;
3. pulsar `Solicitar permiso del navegador`;
4. aceptar el permiso cuando el dispositivo lo solicite.

## Como interpreta el sistema cada configuracion

### Escenario A: operacion orientada a tareas

Configuracion recomendada:

- `Fuente del badge`: `Solo actividades`
- `Comportamiento Android`: `Best effort`
- `Fallback en el titulo`: `Activado`

Interpretacion:

- el badge indica tareas asignadas pendientes;
- no se fuerza una estrategia mas invasiva en Android.

### Escenario B: operacion orientada a comunicacion

Configuracion recomendada:

- `Fuente del badge`: `Solo notificaciones mail`
- `Comportamiento Android`: `Notificaciones del sistema`
- `Fallback en el titulo`: `Activado`

Interpretacion:

- el badge representa mensajes o alertas pendientes;
- se busca mayor compatibilidad con Android.

### Escenario C: vista global de pendientes

Configuracion recomendada:

- `Fuente del badge`: `Ambas`
- `Comportamiento Android`: `Best effort` o `Notificaciones del sistema`, segun preferencia
- `Fallback en el titulo`: `Activado`

Interpretacion:

- el badge muestra una suma total de pendientes;
- es la opcion mas completa.

## Recomendaciones de uso

- Usa un icono PNG grande y claro para la PWA.
- Si el foco del trabajo son tareas, usa `Solo actividades`.
- Si el foco es comunicacion, usa `Solo notificaciones mail`.
- Si quieres una senal general de carga, usa `Ambas`.
- Mantén activado el fallback en el titulo si trabajas con muchos equipos o navegadores distintos.

## Limitaciones que conviene conocer

- En iPhone/iPad el badge depende de que la app este instalada como PWA y de que el usuario conceda permiso de notificaciones.
- En Android el badge del icono puede variar de un equipo a otro.
- Si no existe un icono PNG adecuado, iPhone/iPad no tendra la mejor experiencia de icono instalado.

## Resumen rapido de valores

### Fuente del badge

- `Solo actividades`: muestra tareas pendientes.
- `Solo notificaciones mail`: muestra mensajes/notificaciones pendientes.
- `Ambas`: suma tareas y notificaciones.

### Comportamiento Android

- `Best effort`: enfoque conservador, sin forzar notificaciones del sistema.
- `Notificaciones del sistema`: busca mejor compatibilidad con badge en Android.

### Fallback en el titulo

- `Activado`: muestra `(N)` en el titulo cuando no hay badge nativo.
- `Desactivado`: no muestra ese indicador alternativo.
