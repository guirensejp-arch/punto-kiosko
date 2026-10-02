from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app.decorators import admin_required
from app.extensions import db
from app.forms import ClienteForm
from app.models.cliente import Cliente
from app.services.phone_normalizer import normalize_phone
from app.utils.auditoria import registrar

clientes_bp = Blueprint('clientes', __name__, url_prefix='/clientes')


@clientes_bp.route('/')
@login_required
def lista():
    q = (request.args.get('q') or '').strip()
    consulta = Cliente.query

    if q:
        like = f'%{q}%'
        filtros = [
            Cliente.nombre.ilike(like),
            Cliente.apellido.ilike(like),
            Cliente.telefono.ilike(like),
        ]
        telefono = normalize_phone(q)
        if telefono:
            filtros.append(Cliente.telefono == telefono)
        consulta = consulta.filter(db.or_(*filtros))

    clientes = consulta.order_by(
        Cliente.activo.desc(), Cliente.apellido, Cliente.nombre
    ).all()
    return render_template('clientes/lista.html', clientes=clientes, q=q)


@clientes_bp.route('/<int:cliente_id>')
@login_required
def detalle(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    return render_template('clientes/detalle.html', cliente=cliente)


@clientes_bp.route('/buscar')
@login_required
def buscar():
    """Búsqueda por teléfono normalizado para autocompletar en Pedidos."""
    telefono = normalize_phone(request.args.get('telefono'))
    if not telefono:
        return jsonify({'encontrado': False})

    cliente = Cliente.query.filter_by(telefono=telefono).first()
    if cliente is None or not cliente.activo:
        return jsonify({'encontrado': False})

    return jsonify({
        'encontrado': True,
        'id': cliente.id,
        'nombre': cliente.nombre,
        'apellido': cliente.apellido or '',
        'direccion': cliente.direccion or '',
        'notas': cliente.notas or '',
        'telefono': cliente.telefono,
        'pedidos_previos': len(cliente.ventas),
    })


@clientes_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo():
    form = ClienteForm()
    if form.validate_on_submit():
        telefono = normalize_phone(form.telefono.data)
        if not telefono:
            flash('El teléfono no es válido.', 'danger')
        elif Cliente.query.filter_by(telefono=telefono).first():
            flash('Ya existe un cliente con ese teléfono.', 'danger')
        else:
            cliente = Cliente(
                nombre=form.nombre.data.strip(),
                apellido=(form.apellido.data or '').strip() or None,
                telefono=telefono,
                direccion=(form.direccion.data or '').strip() or None,
                notas=(form.notas.data or '').strip() or None,
                activo=form.activo.data,
            )
            db.session.add(cliente)
            db.session.commit()
            registrar('CREAR_CLIENTE', 'cliente', cliente.id)
            flash(f'Cliente {cliente.nombre_completo} creado.', 'success')
            return redirect(url_for('clientes.lista'))

    return render_template('clientes/form.html', form=form, cliente=None)


@clientes_bp.route('/<int:cliente_id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    form = ClienteForm(obj=cliente)

    if form.validate_on_submit():
        telefono = normalize_phone(form.telefono.data)
        duplicado = Cliente.query.filter(
            Cliente.telefono == telefono, Cliente.id != cliente.id
        ).first()
        if not telefono:
            flash('El teléfono no es válido.', 'danger')
        elif duplicado:
            flash('Ya existe otro cliente con ese teléfono.', 'danger')
        else:
            cliente.nombre = form.nombre.data.strip()
            cliente.apellido = (form.apellido.data or '').strip() or None
            cliente.telefono = telefono
            cliente.direccion = (form.direccion.data or '').strip() or None
            cliente.notas = (form.notas.data or '').strip() or None
            cliente.activo = form.activo.data
            db.session.commit()
            registrar('EDITAR_CLIENTE', 'cliente', cliente.id)
            flash('Cliente actualizado.', 'success')
            return redirect(url_for('clientes.detalle', cliente_id=cliente.id))

    return render_template('clientes/form.html', form=form, cliente=cliente)


@clientes_bp.route('/<int:cliente_id>/desactivar', methods=['POST'])
@login_required
@admin_required
def desactivar(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    cliente.activo = False
    db.session.commit()
    registrar('DESACTIVAR_CLIENTE', 'cliente', cliente.id)
    flash(f'Cliente {cliente.nombre_completo} desactivado.', 'info')
    return redirect(url_for('clientes.lista'))


@clientes_bp.route('/<int:cliente_id>/activar', methods=['POST'])
@login_required
@admin_required
def activar(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    cliente.activo = True
    db.session.commit()
    registrar('ACTIVAR_CLIENTE', 'cliente', cliente.id)
    flash(f'Cliente {cliente.nombre_completo} activado.', 'success')
    return redirect(url_for('clientes.lista'))
