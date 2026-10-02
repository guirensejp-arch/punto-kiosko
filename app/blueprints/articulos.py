from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from openpyxl import Workbook

from app.decorators import admin_required
from app.extensions import db
from app.forms import ProductoForm, ProductoInsumoForm
from app.models.proveedor import Insumo
from app.models.articulo import Articulo, ArticuloInsumo
from app.services.food_cost import costo_producto, margen_producto
from app.utils.auditoria import registrar
from app.utils.excel import (
    FORMATO_MONEDA,
    ajustar_anchos,
    formatear_columna,
    marcar_encabezado,
    pesos,
    respuesta_xlsx,
)
from app.utils.moneda import centavos_a_editable, parsear_centavos
from app.utils.numeros import parsear_decimal
from app.utils.unidades import convertir

articulos_bp = Blueprint('articulos', __name__, url_prefix='/articulos')


def _insumos_activos():
    return (
        Insumo.query.filter_by(activo=True).order_by(Insumo.nombre).all()
    )


@articulos_bp.route('/')
@login_required
def lista():
    q = (request.args.get('q') or '').strip()
    categoria = (request.args.get('categoria') or '').strip()

    consulta = Articulo.query
    if q:
        consulta = consulta.filter(Articulo.nombre.ilike(f'%{q}%'))
    if categoria:
        consulta = consulta.filter(Articulo.categoria == categoria)

    articulos = consulta.order_by(
        Articulo.activo.desc(), Articulo.categoria, Articulo.nombre
    ).all()
    categorias = [
        c[0]
        for c in db.session.query(Articulo.categoria)
        .filter(Articulo.categoria.isnot(None))
        .distinct()
        .order_by(Articulo.categoria)
        .all()
    ]

    filas = [
        {
            'articulo': p,
            'costo': costo_producto(p),
            'margen': margen_producto(p),
        }
        for p in articulos
    ]
    return render_template(
        'articulos/lista.html',
        filas=filas,
        categorias=categorias,
        q=q,
        categoria=categoria,
    )


@articulos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo():
    form = ProductoForm()
    if form.validate_on_submit():
        try:
            precio = parsear_centavos(form.precio_venta.data)
        except ValueError:
            flash('El precio no es un monto válido.', 'danger')
            return render_template('articulos/nuevo.html', form=form)

        articulo = Articulo(
            nombre=form.nombre.data.strip(),
            descripcion=(form.descripcion.data or '').strip() or None,
            categoria=form.categoria.data or None,
            precio_venta=precio,
            margen_objetivo=form.margen_objetivo.data,
            activo=form.activo.data,
        )
        db.session.add(articulo)
        db.session.commit()
        registrar('CREAR_PRODUCTO', 'articulo', articulo.id)
        flash('Articulo creado. Ahora cargá los insumos de la receta.', 'success')
        return redirect(url_for('articulos.detalle', articulo_id=articulo.id))

    return render_template('articulos/nuevo.html', form=form)


@articulos_bp.route('/<int:articulo_id>')
@login_required
def detalle(articulo_id):
    articulo = db.get_or_404(Articulo, articulo_id)
    form = ProductoForm(obj=articulo)
    form.precio_venta.data = centavos_a_editable(articulo.precio_venta)

    linea_form = ProductoInsumoForm()
    linea_form.insumo_id.choices = [(i.id, f'{i.nombre} ({i.unidad})') for i in _insumos_activos()]

    return render_template(
        'articulos/detalle.html',
        articulo=articulo,
        form=form,
        linea_form=linea_form,
        costo=costo_producto(articulo),
        margen=margen_producto(articulo),
    )


@articulos_bp.route('/<int:articulo_id>/guardar', methods=['POST'])
@login_required
@admin_required
def guardar(articulo_id):
    articulo = db.get_or_404(Articulo, articulo_id)
    form = ProductoForm()

    if form.validate_on_submit():
        try:
            articulo.precio_venta = parsear_centavos(form.precio_venta.data)
        except ValueError:
            flash('El precio no es un monto válido.', 'danger')
            return redirect(url_for('articulos.detalle', articulo_id=articulo.id))

        articulo.nombre = form.nombre.data.strip()
        articulo.descripcion = (form.descripcion.data or '').strip() or None
        articulo.categoria = form.categoria.data or None
        articulo.margen_objetivo = form.margen_objetivo.data
        articulo.activo = form.activo.data
        db.session.commit()
        registrar('EDITAR_PRODUCTO', 'articulo', articulo.id)
        flash('Articulo actualizado.', 'success')
    else:
        flash('Revisá los datos del articulo.', 'danger')

    return redirect(url_for('articulos.detalle', articulo_id=articulo.id))


@articulos_bp.route('/<int:articulo_id>/insumos', methods=['POST'])
@login_required
@admin_required
def agregar_insumo(articulo_id):
    articulo = db.get_or_404(Articulo, articulo_id)
    form = ProductoInsumoForm()
    form.insumo_id.choices = [(i.id, i.nombre) for i in _insumos_activos()]

    if not form.validate_on_submit():
        flash('Revisá los datos del insumo.', 'danger')
        return redirect(url_for('articulos.detalle', articulo_id=articulo.id))

    insumo = db.session.get(Insumo, form.insumo_id.data)
    if insumo is None or not insumo.activo:
        flash('El insumo no existe o está inactivo.', 'danger')
        return redirect(url_for('articulos.detalle', articulo_id=articulo.id))

    try:
        cantidad = parsear_decimal(form.cantidad.data)
    except ValueError:
        cantidad = None
    if cantidad is None or cantidad <= 0:
        flash('La cantidad debe ser un número mayor a 0.', 'danger')
        return redirect(url_for('articulos.detalle', articulo_id=articulo.id))

    if convertir(cantidad, form.unidad.data, insumo.unidad) is None:
        flash(
            f'La unidad {form.unidad.data} no es compatible con la unidad del '
            f'insumo ({insumo.unidad}).',
            'danger',
        )
        return redirect(url_for('articulos.detalle', articulo_id=articulo.id))

    existente = ArticuloInsumo.query.filter_by(
        articulo_id=articulo.id, insumo_id=insumo.id
    ).first()
    if existente:
        existente.cantidad = cantidad
        existente.unidad = form.unidad.data
        flash('El insumo ya estaba en la receta: se actualizó la cantidad.', 'info')
    else:
        db.session.add(
            ArticuloInsumo(
                articulo_id=articulo.id,
                insumo_id=insumo.id,
                cantidad=cantidad,
                unidad=form.unidad.data,
            )
        )
        flash('Insumo agregado a la receta.', 'success')

    db.session.commit()
    registrar('EDITAR_RECETA', 'articulo', articulo.id, {'insumo_id': insumo.id})
    return redirect(url_for('articulos.detalle', articulo_id=articulo.id))


@articulos_bp.route('/<int:articulo_id>/insumos/<int:linea_id>/quitar', methods=['POST'])
@login_required
@admin_required
def quitar_insumo(articulo_id, linea_id):
    linea = db.get_or_404(ArticuloInsumo, linea_id)
    if linea.articulo_id != articulo_id:
        flash('La línea no pertenece a ese articulo.', 'danger')
        return redirect(url_for('articulos.detalle', articulo_id=articulo_id))

    db.session.delete(linea)
    db.session.commit()
    registrar('EDITAR_RECETA', 'articulo', articulo_id, {'quitar_insumo': linea.insumo_id})
    flash('Insumo quitado de la receta.', 'info')
    return redirect(url_for('articulos.detalle', articulo_id=articulo_id))


@articulos_bp.route('/<int:articulo_id>/desactivar', methods=['POST'])
@login_required
@admin_required
def desactivar(articulo_id):
    articulo = db.get_or_404(Articulo, articulo_id)
    articulo.activo = False
    db.session.commit()
    registrar('DESACTIVAR_PRODUCTO', 'articulo', articulo.id)
    flash(f'Articulo {articulo.nombre} desactivado.', 'info')
    return redirect(url_for('articulos.lista'))


@articulos_bp.route('/<int:articulo_id>/activar', methods=['POST'])
@login_required
@admin_required
def activar(articulo_id):
    articulo = db.get_or_404(Articulo, articulo_id)
    articulo.activo = True
    db.session.commit()
    registrar('ACTIVAR_PRODUCTO', 'articulo', articulo.id)
    flash(f'Articulo {articulo.nombre} activado.', 'success')
    return redirect(url_for('articulos.lista'))


@articulos_bp.route('/exportar.xlsx')
@login_required
def exportar_xlsx():
    articulos = Articulo.query.order_by(
        Articulo.categoria, Articulo.nombre
    ).all()

    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Recetas'
    hoja.append(
        ['Articulo', 'Categoría', 'Precio venta', 'Costo insumos', 'Margen %', 'Estado']
    )
    for articulo in articulos:
        margen = margen_producto(articulo)
        hoja.append([
            articulo.nombre,
            articulo.categoria or '',
            pesos(articulo.precio_venta),
            pesos(costo_producto(articulo)),
            margen if margen is not None else '',
            'Activo' if articulo.activo else 'Inactivo',
        ])

    marcar_encabezado(hoja)
    formatear_columna(hoja, 3, FORMATO_MONEDA)
    formatear_columna(hoja, 4, FORMATO_MONEDA)
    ajustar_anchos(hoja)
    hoja.freeze_panes = 'A2'

    return respuesta_xlsx(libro, 'articulos.xlsx')
