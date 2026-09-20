# DReyes Clover Sync

Conector bidireccional para Odoo 18 y Clover. Cada empresa Odoo puede tener una conexión activa; los sitios web de esa empresa la heredan.

## Puesta en marcha

1. Defina una clave estable y privada en el contenedor Odoo: `CLOVER_TOKEN_ENCRYPTION_KEY`.
2. Instale **DReyes Clover Sync** y asigne los grupos *Administrador Clover* u *Operador Clover*.
3. En Clover Developer cree una aplicación web con permisos de lectura/escritura de inventario, lectura de clientes y lectura de pedidos, pagos y devoluciones.
4. Configure como callback `https://SU-DOMINIO/clover/oauth/callback` y como webhook `https://SU-DOMINIO/clover/webhook`.
5. Cree una conexión, seleccione empresa, almacén, ubicación, lista de precios y un POS dedicado; capture App ID, App Secret y código de autenticación del webhook.
6. Conecte OAuth, pruebe la conexión y ejecute primero la importación inicial en Clover Sandbox.

Los tokens, refresh tokens, App Secret y código del webhook se guardan cifrados. Cambiar la clave del servidor impide descifrar credenciales existentes.

## Autoridad de datos

- La primera importación toma Clover como origen y excluye de esa conexión los productos de Odoo que no existan en Clover.
- Después del corte, Odoo gobierna catálogo, precios, coste, impuestos y disponibilidad; cambios equivalentes recibidos desde Clover se registran como conflictos.
- Clover gobierna ventas, pagos, devoluciones y ajustes POS.
- El inventario recibido genera movimientos auditables contra la ubicación de inventario; nunca escribe directamente en `stock.quant`.

La cola reintenta a 1, 5, 15 y 60 minutos, después cada seis horas y detiene el evento tras diez intentos. La conciliación nocturna recupera eventos perdidos.
