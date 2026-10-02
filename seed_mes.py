"""Generador de datos ficticios de un mes para Punto Kiosko.

Crea:
- Catálogo realista de kiosco con códigos de barras (bebidas, golosinas,
  cigarrillos, snacks, almacén, kiosco).
- Ventas de jueves a domingo durante ~4 semanas, con varios medios de pago.
- Un turno de caja por día abierto: la mayoría cerrado con cierre Z; en el
  medio, un cierre X informativo (no persistido, se registra en auditoría).
- Ingresos de mercadería (reposición de stock) y algún egreso (gastos).

Uso:
    venv\\Scripts\\python.exe seed_mes.py
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.articulo import Articulo, ArticuloInsumo, CodigoBarras
from app.models.caja import (
    CategoriaMovimientoCaja,
    EstadoTurno,
    MetodoPago,
    MovimientoCaja,
    TipoMovimientoCaja,
    TurnoCaja,
)
from app.models.inventario import Lote, MovimientoInventario, TipoMovimientoInventario
from app.models.proveedor import Insumo, Proveedor
from app.models.sistema import Auditoria
from app.models.usuario import RolUsuario, Usuario
from app.models.venta import Venta
from app.services import caja_service, venta_service

DIAS_ABIERTOS = (3, 4, 5, 6)  # jueves a domingo
FONDO_CAJA = 500000  # $5.000
HORARIO = (9, 23)  # 9:00 a 23:59
MESES_ATRAS = 1

# (nombre, categoria, precio_venta, precio_costo, unidad, stock, codigo)
CATALOGO = [
    # Bebidas
    ('Coca-Cola 500ml', 'Bebidas', 150000, 95000, 'ud', 48, '7790895001234'),
    ('Coca-Cola 1.5L', 'Bebidas', 280000, 190000, 'ud', 24, '7790895001241'),
    ('Pepsi 500ml', 'Bebidas', 140000, 90000, 'ud', 30, '7790895002001'),
    ('Sprite 500ml', 'Bebidas', 140000, 90000, 'ud', 28, '7790895003002'),
    ('Fanta 500ml', 'Bebidas', 140000, 90000, 'ud', 26, '7790895004003'),
    ('Agua mineral 500ml', 'Bebidas', 90000, 50000, 'ud', 40, '7790895005004'),
    ('Agua saborizada 600ml', 'Bebidas', 110000, 65000, 'ud', 36, '7790895006005'),
    ('Cerveza rubia lata 473ml', 'Bebidas', 320000, 220000, 'ud', 48, '7790895007006'),
    ('Cerveza negra lata 473ml', 'Bebidas', 340000, 235000, 'ud', 24, '7790895008007'),
    ('Energizante 500ml', 'Bebidas', 350000, 240000, 'ud', 20, '7790895009008'),
    ('Jugo en caja 200ml', 'Bebidas', 80000, 45000, 'ud', 60, '7790895010009'),
    ('Gaseosa 2.25L', 'Bebidas', 320000, 220000, 'ud', 18, '7790895011010'),
    # Golosinas
    ('Alfajor de chocolate', 'Golosinas', 60000, 35000, 'ud', 120, '7791234001010'),
    ('Alfajor de dulce de leche', 'Golosinas', 60000, 35000, 'ud', 110, '7791234002021'),
    ('Chocolate con leche 25g', 'Golosinas', 55000, 32000, 'ud', 90, '7791234003032'),
    ('Chicles menta', 'Golosinas', 30000, 15000, 'ud', 150, '7791234004043'),
    ('Caramelos surtidos', 'Golosinas', 25000, 12000, 'ud', 200, '7791234005054'),
    ('Gomitas ositos', 'Golosinas', 40000, 22000, 'ud', 100, '7791234006065'),
    ('Turrón de maní', 'Golosinas', 35000, 18000, 'ud', 80, '7791234007076'),
    ('Oblea rellena', 'Golosinas', 45000, 25000, 'ud', 90, '7791234008087'),
    # Snacks
    ('Papas fritas chicas', 'Snacks', 70000, 42000, 'ud', 70, '7792345001010'),
    ('Papas fritas medianas', 'Snacks', 120000, 75000, 'ud', 50, '7792345002021'),
    ('Palitos salados', 'Snacks', 65000, 38000, 'ud', 60, '7792345003032'),
    ('Maní salado 50g', 'Snacks', 55000, 30000, 'ud', 55, '7792345004043'),
    ('Nachos con queso', 'Snacks', 130000, 80000, 'ud', 40, '7792345005054'),
    # Cigarrillos
    ('Cigarrillos Marlboro', 'Cigarrillos', 250000, 210000, 'ud', 60, '7793456001010'),
    ('Cigarrillos Camel', 'Cigarrillos', 240000, 200000, 'ud', 50, '7793456002021'),
    ('Cigarrillos Lucky', 'Cigarrillos', 235000, 195000, 'ud', 45, '7793456003032'),
    ('Cigarrillos armados', 'Cigarrillos', 200000, 165000, 'ud', 40, '7793456004043'),
    # Almacén
    ('Leche en sachet 1L', 'Almacén', 130000, 95000, 'ud', 30, '7794567001010'),
    ('Yerba mate 1kg', 'Almacén', 450000, 330000, 'ud', 20, '7794567002021'),
    ('Azúcar 1kg', 'Almacén', 120000, 85000, 'ud', 25, '7794567003032'),
    ('Fideos 500g', 'Almacén', 95000, 65000, 'ud', 35, '7794567004043'),
    ('Arroz 1kg', 'Almacén', 140000, 100000, 'ud', 22, '7794567005054'),
    ('Aceite 900ml', 'Almacén', 260000, 195000, 'ud', 18, '7794567006065'),
    ('Pan lactal', 'Almacén', 150000, 105000, 'ud', 20, '7794567007076'),
    ('Huevos x6', 'Almacén', 180000, 130000, 'ud', 24, '7794567008087'),
    # Kiosco / varios
    ('Encendedor', 'Kiosco', 90000, 45000, 'ud', 40, '7795678001010'),
    ('Pilas AA x2', 'Kiosco', 150000, 95000, 'ud', 30, '7795678002021'),
    ('Preservativos x3', 'Kiosco', 280000, 180000, 'ud', 25, '7795678003032'),
    ('Pañuelos descartables', 'Kiosco', 70000, 38000, 'ud', 50, '7795678004043'),
    ('Curitas', 'Kiosco', 50000, 25000, 'ud', 45, '7795678005054'),
    ('Gel alcohol 250ml', 'Kiosco', 110000, 70000, 'ud', 30, '7795678006065'),
]

# Proveedores e insumos (para artículos elaborados). costo en centavos por unidad.
PROVEEDORES = [
    ('Fiambrería Don Pedro', 'Fiambres', 'Av. Siempre Viva 123', '381 555-1000'),
    ('Panadería La Espiga', 'Panadería', 'Mitre 456', '381 555-2000'),
    ('Distribuidora del Norte', 'Almacén', 'Ruta 9 km 12', '381 555-3000'),
]

# (insumo, proveedor, unidad, costo, stock_inicial)
INSUMOS = [
    ('Pan de miga', 'Panadería La Espiga', 'ud', 20000, 60),
    ('Jamón cocido', 'Fiambrería Don Pedro', 'kg', 800000, 4),
    ('Queso fresco', 'Fiambrería Don Pedro', 'kg', 800000, 4),
    ('Salchicha (pancho)', 'Fiambrería Don Pedro', 'ud', 30000, 40),
    ('Pan de pancho', 'Panadería La Espiga', 'ud', 15000, 40),
    ('Café molido', 'Distribuidora del Norte', 'kg', 1200000, 2),
    ('Leche', 'Distribuidora del Norte', 'l', 130000, 10),
    ('Azúcar', 'Distribuidora del Norte', 'kg', 120000, 5),
    ('Pan de hamburguesa', 'Panadería La Espiga', 'ud', 25000, 30),
    ('Medallón de carne', 'Fiambrería Don Pedro', 'ud', 90000, 30),
]

# Artículos elaborados: (nombre, categoria, precio_venta, [(insumo, cantidad, unidad)])
ELABORADOS = [
    ('Sánguche de jamón y queso', 'Kiosco', 250000,
     [('Pan de miga', '2', 'ud'), ('Jamón cocido', '0.050', 'kg'), ('Queso fresco', '0.050', 'kg')]),
    ('Pancho', 'Kiosco', 180000,
     [('Salchicha (pancho)', '1', 'ud'), ('Pan de pancho', '1', 'ud')]),
    ('Café con leche', 'Kiosco', 150000,
     [('Café molido', '0.010', 'kg'), ('Leche', '0.150', 'l'), ('Azúcar', '0.010', 'kg')]),
    ('Hamburguesa de kiosco', 'Kiosco', 350000,
     [('Pan de hamburguesa', '1', 'ud'), ('Medallón de carne', '1', 'ud'), ('Queso fresco', '0.030', 'kg')]),
]


def crear_usuarios():
    admin = Usuario.query.filter_by(email_personal='admin@kiosko.com').first()
    if admin is None:
        admin = Usuario(nombre='Admin', apellido='Kiosko',
                        email_personal='admin@kiosko.com',
                        rol=RolUsuario.ADMIN, activo=True)
        admin.set_password('password123')
        db.session.add(admin)
    cajero = Usuario.query.filter_by(email_personal='cajero@kiosko.com').first()
    if cajero is None:
        cajero = Usuario(nombre='Cami', apellido='Cajera',
                         email_personal='cajero@kiosko.com',
                         rol=RolUsuario.CAJERO, activo=True)
        cajero.set_password('password123')
        db.session.add(cajero)
    db.session.commit()
    return admin, cajero


def crear_metodos():
    metodos = {}
    for nombre, efectivo in [('Efectivo', True), ('QR', False),
                             ('Transferencia', False), ('Débito', False),
                             ('MercadoPago', False)]:
        m = MetodoPago.query.filter_by(nombre=nombre).first()
        if m is None:
            m = MetodoPago(nombre=nombre, es_efectivo=efectivo)
            db.session.add(m)
        metodos[nombre] = m
    db.session.commit()
    return metodos


def crear_catalogo():
    articulos = []
    for nombre, categoria, precio, costo, unidad, stock, codigo in CATALOGO:
        art = Articulo.query.filter_by(nombre=nombre).first()
        if art is None:
            art = Articulo(nombre=nombre, categoria=categoria,
                           precio_venta=precio, precio_costo=costo,
                           stock_propio=True, stock=Decimal('0'),
                           unidad=unidad, activo=True)
            db.session.add(art)
            db.session.flush()
        if not CodigoBarras.query.filter_by(codigo=codigo).first():
            db.session.add(CodigoBarras(codigo=codigo, articulo_id=art.id))
        articulos.append((art, stock))
    db.session.commit()
    return articulos


def crear_elaborados(admin):
    """Crea proveedores, insumos con costo y lote, y artículos elaborados con receta."""
    proveedores = {}
    for nombre, rubro, ubicacion, telefono in PROVEEDORES:
        p = Proveedor.query.filter_by(nombre=nombre).first()
        if p is None:
            p = Proveedor(nombre=nombre, rubro=rubro, ubicacion=ubicacion,
                          telefono=telefono, activo=True)
            db.session.add(p)
        proveedores[nombre] = p
    db.session.commit()

    insumos = {}
    for nombre, proveedor, unidad, costo, stock in INSUMOS:
        insumo = Insumo.query.filter_by(nombre=nombre).first()
        if insumo is None:
            insumo = Insumo(proveedor_id=proveedores[proveedor].id, nombre=nombre,
                            rubro=proveedores[proveedor].rubro, costo=costo,
                            unidad=unidad, activo=True)
            db.session.add(insumo)
            db.session.flush()
        cargar = Lote.query.filter_by(insumo_id=insumo.id).count() == 0
        insumos[nombre] = (insumo, stock if cargar else 0, unidad)
    db.session.commit()

    # Lotes iniciales con vencimiento a ~30 días.
    for nombre, (insumo, stock, unidad) in insumos.items():
        if stock:
            from datetime import timedelta as _td
            db.session.add(Lote(
                insumo_id=insumo.id, numero='SEED', cantidad=Decimal(str(stock)),
                unidad=unidad, fecha_ingreso=datetime.utcnow(),
                fecha_vencimiento=datetime.utcnow() + _td(days=30),
            ))
    db.session.commit()

    elaborados = []
    for nombre, categoria, precio, receta in ELABORADOS:
        art = Articulo.query.filter_by(nombre=nombre).first()
        if art is None:
            art = Articulo(nombre=nombre, categoria=categoria, precio_venta=precio,
                           precio_costo=0, stock_propio=False, stock=Decimal('0'),
                           unidad='ud', activo=True)
            db.session.add(art)
            db.session.flush()
            for insumo_nombre, cantidad, unidad in receta:
                insumo = insumos[insumo_nombre][0]
                db.session.add(ArticuloInsumo(
                    articulo_id=art.id, insumo_id=insumo.id,
                    cantidad=Decimal(cantidad), unidad=unidad,
                ))
        elaborados.append((art, 0))
    db.session.commit()
    return elaborados


def cargar_stock_inicial(articulos, turno, admin, momento):
    """Repone el stock inicial como ingreso de mercadería (sin caja)."""
    for art, stock in articulos:
        if art.stock and art.stock > 0:
            continue
        art.stock = Decimal(str(stock))
        db.session.add(MovimientoInventario(
            articulo_id=art.id,
            tipo=TipoMovimientoInventario.CARGA,
            cantidad=Decimal(str(stock)),
            usuario_id=admin.id,
            motivo='Carga inicial',
            fecha_hora=momento,
        ))
    db.session.commit()


def _elegir_articulos(articulos):
    """Arma un ticket kiosco: 1-5 items, sesgado a los más vendibles."""
    cantidad = random.choices([1, 2, 3, 4, 5], weights=[35, 28, 18, 12, 7])[0]
    elegidos = []
    for _ in range(cantidad):
        art, _ = random.choice(articulos)
        cant = random.choices([1, 1, 1, 2], k=1)[0]
        elegidos.append((art, cant))
    # Fusiona repetidos.
    fusion = {}
    for art, cant in elegidos:
        fusion[art.id] = fusion.get(art.id, (art, 0))
        fusion[art.id] = (art, fusion[art.id][1] + cant)
    return list(fusion.values())


def generar_dia(dia, articulos, cajeros, metodos, admin):
    turno = caja_service.abrir_turno(FONDO_CAJA, random.choice(cajeros).id)
    turno.fecha_apertura = datetime.combine(dia, time(9, 0))
    db.session.commit()

    n = random.randint(18, 34)
    inicio = datetime.combine(dia, time(HORARIO[0], 0))
    fin = datetime.combine(dia, time(HORARIO[1], 59))
    ventana = int((fin - inicio).total_seconds())
    slots = sorted(random.randint(0, ventana) for _ in range(n))

    for segundo in slots:
        momento = inicio + timedelta(seconds=segundo)
        lineas = _elegir_articulos(articulos)
        # Repone stock de reventa si hace falta.
        for art, cant in lineas:
            if art.stock_propio and art.stock < cant:
                art.stock = art.stock + Decimal('12')
        metodo = random.choices(
            list(metodos.values()),
            weights=[55, 18, 12, 10, 5],
        )[0]
        total = sum(a.precio_venta * c for a, c in lineas)
        pago = total
        if metodo.es_efectivo:
            pago = total + random.choice([0, 0, 0, 10000, 50000, 100000])
        try:
            venta = venta_service.crear_venta(
                lineas, random.choice(cajeros).id, metodo_pago=metodo,
                pago_recibido=pago, turno=turno,
            )
        except ValueError:
            # Un elaborado sin insumos suficientes: se salta la venta.
            db.session.rollback()
            continue
        venta.fecha_hora = momento
        for mov in MovimientoCaja.query.filter_by(turno_caja_id=turno.id).all():
            if mov.fecha_hora > momento:
                mov.fecha_hora = momento
        db.session.commit()

    # Reposición de mercadería a mitad de turno (ingreso de stock de reventa).
    reventa = [a for a, _ in articulos if a.stock_propio]
    if random.random() < 0.6 and reventa:
        for _ in range(random.randint(1, 3)):
            art = random.choice(reventa)
            cant = Decimal(str(random.choice([6, 12, 24])))
            art.stock = art.stock + cant
            db.session.add(MovimientoInventario(
                articulo_id=art.id, tipo=TipoMovimientoInventario.CARGA,
                cantidad=cant, usuario_id=admin.id, motivo='Reposición',
                fecha_hora=datetime.combine(dia, time(13, 30)),
            ))
        db.session.commit()

    # Gasto ocasional.
    if random.random() < 0.35:
        gasto = random.choice([500000, 800000, 1200000])
        mov = caja_service.registrar_movimiento(
            turno, TipoMovimientoCaja.EGRESO, gasto, admin.id,
            categoria=CategoriaMovimientoCaja.GASTO,
            motivo=random.choice(['Limpieza', 'Hielo', 'Bolsas', 'Delivery']),
        )
        mov.fecha_hora = datetime.combine(dia, time(20, 15))
        db.session.commit()

    # Cierre X informativo un día de cada dos (no persistido).
    if random.random() < 0.5:
        resumen = caja_service.resumen_x(turno, caja_service.efectivo_esperado(turno))
        db.session.add(Auditoria(
            usuario_id=admin.id, accion='CIERRE_X', entidad='turno_caja',
            entidad_id=turno.id,
            detalles={'ventas': resumen['ventas'], 'diferencia': 0},
            fecha_hora=datetime.combine(dia, time(18, 30)),
        ))
        db.session.commit()

    # Cierre Z (arqueo). Puede quedar una diferencia chica a propósito.
    esperado = caja_service.efectivo_esperado(turno)
    diferencia = 0
    if random.random() < 0.3:
        diferencia = random.choice([-100000, -50000, 50000, 100000])
    motivo = 'Diferencia de arqueo' if diferencia else None
    caja_service.cerrar_turno(
        turno, esperado + diferencia, admin.id,
        motivo_diferencia=motivo, diferencia_confirmada=bool(diferencia),
    )
    turno.fecha_cierre = datetime.combine(dia, time(23, 45))
    db.session.commit()


def main():
    app = create_app()
    with app.app_context():
        print('Creando usuarios y métodos de pago...')
        admin, cajero = crear_usuarios()
        metodos = crear_metodos()
        cajeros = [admin, cajero]

        print('Creando catálogo...')
        articulos = crear_catalogo()

        print('Creando proveedores, insumos y elaborados...')
        elaborados = crear_elaborados(admin)
        # La reposición de stock solo aplica a reventa (los elaborados usan insumos).
        pool_venta = articulos + elaborados

        hoy = date.today()
        inicio = hoy - timedelta(days=30)
        dias = [
            inicio + timedelta(days=i)
            for i in range(31)
            if (inicio + timedelta(days=i)).weekday() in DIAS_ABIERTOS
        ]
        print(f'Generando {len(dias)} días de ventas (jue-dom)...')

        primer_turno = caja_service.abrir_turno(FONDO_CAJA, admin.id)
        primer_turno.fecha_apertura = datetime.combine(dias[0], time(9, 0))
        db.session.commit()
        cargar_stock_inicial(articulos, primer_turno, admin,
                             datetime.combine(dias[0], time(8, 30)))
        caja_service.cerrar_turno(primer_turno, caja_service.efectivo_esperado(primer_turno), admin.id)
        primer_turno.fecha_cierre = datetime.combine(dias[0], time(9, 5))
        db.session.commit()

        for dia in dias:
            generar_dia(dia, pool_venta, cajeros, metodos, admin)
            print(f'  {dia} ok')

        ventas = db.session.query(db.func.count()).select_from(Venta).scalar()
        print('\nListo.')
        print(f'Ventas: {ventas}')
        print(f'Turnos: {TurnoCaja.query.count()}')
        print(f'Artículos: {Articulo.query.count()} · Códigos: {CodigoBarras.query.count()}')
        print('Login: admin@kiosko.com / password123')


if __name__ == '__main__':
    main()
