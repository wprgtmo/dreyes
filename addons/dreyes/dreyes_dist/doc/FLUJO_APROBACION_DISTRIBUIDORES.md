# Flujo de aprobación para clientes distribuidores

## Objetivo

El módulo `dreyes_dist` permite que un cliente del portal de distribución consulte el catálogo desde el momento en que se registra, sin obligarlo a completar inmediatamente su expediente comercial.

Los precios y las compras sólo se habilitan cuando DReyes revisa el expediente, asigna un segmento de mercado y aprueba la cuenta. Esta restricción se aplica únicamente a los sitios web configurados con el formulario de registro `extended`; el sitio minorista conserva su comportamiento normal.

## Estados del expediente

| Estado | Significado | Precios | Compra |
|---|---|---:|---:|
| Sin perfil | El expediente no se ha enviado o requiere correcciones. Puede contener un borrador parcial. | No | No |
| En revisión | El cliente envió toda la información requerida y el equipo debe validarla. | No | No |
| Pendiente de aprobación | La información fue revisada y ya se asignó un segmento de mercado. | No | No |
| Aprobado | El expediente está aprobado y tiene un segmento y una lista de precios válidos. | Sí | Sí |

Flujo normal:

`Sin perfil → En revisión → Pendiente de aprobación → Aprobado`

El estado se muestra en el formulario del cliente, el panel del portal y el menú de perfil.

## Registro y perfil del cliente

Después del registro y en cada inicio de sesión mientras el expediente permanezca en **Sin perfil**, el cliente es dirigido a:

`/my/distributor-profile`

La ruta anterior `/profile/complete` se conserva como alias compatible.

El cliente dispone de las siguientes opciones:

- **Guardar borrador:** conserva información parcial sin iniciar la revisión.
- **Enviar a revisión:** valida que el expediente esté completo y cambia su estado a En revisión.
- **Completar después:** permite continuar al portal sin completar el formulario.

El formulario también está disponible permanentemente desde el menú **Perfil de distribuidor**.

### Información obligatoria para enviar

- Nombre legal de la empresa.
- Nombre, apellido y correo electrónico del contacto.
- Dirección, ciudad, estado, código postal y país.
- Teléfono.
- EIN de 9 dígitos.
- Número del permiso de Texas de 11 dígitos.
- Archivo del Texas Sales and Use Tax Permit.

Los guiones y espacios introducidos en EIN y número de permiso se eliminan antes de guardar. El archivo debe ser PDF, JPG, JPEG o PNG y no puede exceder 15 MB.

El EIN aparece enmascarado en el portal después de guardarlo. Dejar ese campo vacío conserva el valor almacenado.

## Historial del tax permit

Cada carga crea una versión nueva. Los archivos anteriores no se sobrescriben y permanecen disponibles en el historial del expediente con fecha y usuario de carga.

Los adjuntos son privados. Un cliente sólo puede descargar archivos pertenecientes a su propio expediente; los revisores acceden a ellos desde la vista administrativa.

Si un cliente aprobado reemplaza el tax permit:

1. La cuenta vuelve automáticamente a En revisión.
2. Se suspende temporalmente la visualización de precios y la compra.
3. El equipo revisor recibe una notificación.
4. El expediente debe completar nuevamente la revisión y aprobación.

Las modificaciones ordinarias de contacto o dirección de un cliente aprobado no revocan su aprobación.

## Revisión y aprobación interna

Los empleados responsables deben pertenecer al grupo **Revisor de distribución**.

Las opciones administrativas están disponibles en:

`Contactos → Distribución → Expedientes`

### Marcar revisado

Disponible únicamente para expedientes En revisión. Antes de continuar, el revisor debe:

1. Verificar la información y el tax permit.
2. Asignar un segmento de mercado activo.
3. Confirmar que el segmento tiene una lista de precios válida.
4. Pulsar **Marcar revisado**.

El expediente cambia a Pendiente de aprobación y el cliente recibe una notificación.

### Aprobar

Disponible únicamente para expedientes Pendiente de aprobación. Al pulsar **Aprobar**:

- el expediente cambia a Aprobado;
- la lista de precios del segmento se asigna al cliente;
- los carritos borrador del cliente se recalculan;
- se habilitan precios, carrito, checkout y pago;
- el cliente recibe una notificación.

El mismo miembro del grupo revisor puede ejecutar la revisión y la aprobación.

### Solicitar correcciones

El revisor debe escribir primero un motivo en **Correcciones solicitadas** y luego pulsar **Solicitar correcciones**.

La acción:

- conserva toda la información y los archivos existentes;
- cambia el estado a Sin perfil;
- suspende el acceso a precios y compras;
- muestra el motivo en el portal;
- notifica al cliente por correo.

Si el cliente modifica un expediente Pendiente de aprobación, éste regresa automáticamente a En revisión. Los cambios realizados durante En revisión notifican nuevamente al equipo.

## Segmentos y listas de precios

Los segmentos se administran en:

`Contactos → Distribución → Segmentos de mercado`

Cada segmento requiere:

- un nombre único dentro de la compañía;
- una compañía;
- una lista de precios activa de esa misma compañía.

No se puede usar una lista de precios perteneciente a la compañía minorista para un segmento de la compañía de distribución. Tampoco se puede archivar un segmento utilizado por clientes aprobados ni eliminar un segmento que tenga expedientes asociados.

Para un cliente aprobado, la lista del segmento es obligatoria. El portal ignora listas seleccionadas previamente en la sesión y no permite al cliente cambiarla. Si se cambia la lista configurada en el segmento, los clientes aprobados y sus carritos borrador se actualizan automáticamente.

Cambiar el segmento directamente en un expediente aprobado lo devuelve a Pendiente de aprobación y suspende las compras hasta una nueva aprobación.

## Comportamiento del catálogo

En el sitio de distribución, los visitantes anónimos y los clientes no aprobados pueden consultar:

- productos publicados;
- imágenes;
- nombres, categorías y descripciones;
- variantes disponibles.

En lugar del importe se muestra **Precio disponible al aprobar la cuenta**. No aparecen los controles para agregar al carrito ni el acceso al carrito.

La protección se aplica también en el servidor a:

- actualización normal y JSON del carrito;
- compra rápida y variantes;
- reordenamiento de pedidos anteriores;
- carrito, checkout y pago;
- información dinámica de precios.

Un visitante que intenta abrir el carrito es enviado al login. Un cliente autenticado no aprobado es enviado a su perfil de distribuidor.

## Notificaciones

El módulo crea correos para los siguientes eventos:

- expediente enviado a revisión;
- cambios durante la revisión;
- expediente pendiente de aprobación;
- cuenta aprobada;
- correcciones solicitadas;
- reemplazo del tax permit de una cuenta aprobada.

Los avisos internos se envían a los usuarios del grupo Revisor de distribución que tengan acceso a la compañía correspondiente. Los correos quedan en la cola estándar de Odoo, por lo que el servidor de correo saliente y la tarea programada de envío deben estar configurados.

## Configuración inicial

1. Confirmar que el sitio de distribución utiliza el formulario `extended`.
2. Crear listas de precios pertenecientes a la compañía de distribución.
3. Crear los segmentos y asociar cada uno con su lista.
4. Asignar el grupo **Revisor de distribución** a los empleados responsables.
5. Configurar el correo saliente de Odoo.
6. Probar el proceso con un usuario de portal antes de habilitar el registro público.

## Migración de usuarios existentes

Al actualizar desde una versión anterior, el proceso es idempotente y sólo considera usuarios de portal de compañías con formulario `extended`. Se excluyen usuarios internos, públicos y plantillas.

- Un perfil que ya contenía todos los datos anteriores y un tax permit se crea En revisión.
- Un perfil incompleto se crea Sin perfil.
- La referencia al tax permit anterior se incorpora como primera versión del historial.
- Ejecutar nuevamente la migración no crea expedientes duplicados.

Los nuevos datos comerciales —EIN y número de permiso— siguen siendo obligatorios antes de que el revisor pueda avanzar el expediente a Pendiente de aprobación.

## Diagnóstico rápido

- **El cliente está Aprobado pero no puede comprar:** comprobar que el segmento esté activo y que su lista esté activa y pertenezca a la compañía correcta.
- **No llegan avisos internos:** comprobar la pertenencia al grupo Revisor de distribución, la compañía permitida del usuario y el correo configurado en su contacto.
- **El precio no coincide:** revisar la lista asociada al segmento y recalcular o volver a aprobar el expediente si se cambió el segmento.
- **El formulario no aparece después del login:** comprobar que el sitio esté configurado como `extended` y que el usuario esté entrando por el dominio del sitio de distribución.
