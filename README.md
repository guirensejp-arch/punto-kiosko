# Punto Kiosko

Punto de venta (POS) para **kioscos y despensas**: venta rápida de mostrador,
código de barras, caja con cierre X y Z, y control de stock.

Construido en **Flask + SQLAlchemy + Jinja + Bootstrap 5**.

## Qué hace

- **Vender (POS)**: escaneo de código de barras, búsqueda por nombre/SKU, ticket
  con cantidades, cobro por medio de pago, cálculo de vuelto y venta ocasional
  (sin cliente).
- **Ventas**: historial con filtros por estado, medio de pago y fecha; anulación
  con reversión de stock y caja; ticket térmico 80 mm.
- **Caja**: turnos, ingresos/egresos, compras a proveedores, arqueo, **cierre X**
  (parcial, sin cerrar) y **cierre Z** (final).
- **Artículos**: catálogo con SKU, precio de venta y costo, categoría y uno o más
  **códigos de barras** por artículo.
- **Inventario**: stock por lote con FEFO y vencimientos (para elaborados y
  reventa fraccionada).
- **Proveedores**, **Clientes**, **Promociones**, **Usuarios** y **Analítica**.

## Puesta en marcha

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m flask --app run db upgrade
venv\Scripts\python.exe -m flask --app run crear-admin
venv\Scripts\python.exe run.py
```

Abrir http://127.0.0.1:5000 e ingresar con el usuario administrador creado.

## Lector de código de barras

Se soporta cualquier lector **HID / keyboard wedge** (emula teclado y termina en
Enter). Cargá el código en el artículo y luego escaneá en la pantalla **Vender**.
El POS captura el escaneo de forma global, sin necesidad de mantener el foco.

## Marca

El nombre, los colores y el logo se editan en `branding.yaml` (sin tocar código).

## Estado

En desarrollo. Roadmap por fases: catálogo con códigos, POS, cierre X, stock de
reventa, y más adelante balanza/pesables y facturación electrónica (ARCA).
