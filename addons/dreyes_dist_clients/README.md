# `dreyes_dist_clients`

Aplicación administrativa para consultar y procesar solicitudes de clientes distribuidores.

## Funciones

- menú independiente **Clientes distribuidores**;
- bandeja de solicitudes En revisión y Pendientes de aprobación;
- vista Kanban agrupada por estado y sin arrastre entre columnas;
- vista de lista con datos de contacto, segmento y fechas;
- vistas gráfica y pivote para análisis por estado, segmento, compañía, ubicación y fecha;
- acceso al formulario completo de revisión y aprobación de `dreyes_dist`;
- edición de nombre, apellido, correo, teléfono y dirección del contacto desde el expediente;
- carga y descarga del tax permit desde Información fiscal (PDF/JPG/PNG, máximo 15 MB), con historial de versiones y nueva revisión al reemplazar un permiso aprobado;
- botones para pasar a revisión o volver a Sin perfil desde el backend, conservando los datos;
- revisión y aprobación con validación de datos obligatorios, segmento y lista de precios activos;
- al volver a revisión o Sin perfil se suspende la compra y se limpian las fechas de aprobación;
- administración de segmentos desde la misma aplicación.

## Seguridad

La aplicación sólo aparece para usuarios pertenecientes al grupo **Revisor de distribución**.
