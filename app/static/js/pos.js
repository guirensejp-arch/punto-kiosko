/* Punto de venta (POS) de Punto Kiosko.
   - Captura global de lector HID: acumula digitos por keydown y cierra con Enter
     o por timeout (los lectores escriben muy rapido).
   - Busqueda por nombre/SKU via /ventas/buscar.
   - Ticket en memoria + cobro via /ventas/cobrar (JSON).
*/
(function () {
  'use strict';

  var cfg = window.POS;
  if (!cfg) return;

  var scan = document.getElementById('pos-scan');
  var resultados = document.getElementById('pos-resultados');
  var lineasEl = document.getElementById('pos-lineas');
  var vacio = document.getElementById('pos-vacio');
  var cantidadEl = document.getElementById('pos-cantidad');
  var subtotalEl = document.getElementById('pos-subtotal');
  var totalEl = document.getElementById('pos-total');
  var descuentoEl = document.getElementById('pos-descuento');
  var metodoEl = document.getElementById('pos-metodo');
  var recibidoEl = document.getElementById('pos-recibido');
  var vueltoEl = document.getElementById('pos-vuelto');
  var cobrarBtn = document.getElementById('pos-cobrar');
  var errorEl = document.getElementById('pos-error');
  var efectivoBloque = document.getElementById('pos-efectivo-bloque');

  var lineas = [];  // [{ id, nombre, precio, cantidad, pesable }]

  var scanCfg = (cfg.scan) || { ms: 120, cantidad: 1, terminador: 'ENTER', prefijoBalanza: '2' };
  var cantDefault = scanCfg.cantidad || 1;

  var fmt = new Intl.NumberFormat('es-AR');

  function moneda(centavos) {
    return '$ ' + fmt.format(Math.round((centavos || 0) / 100));
  }

  function parsearMonto(texto) {
    // Acepta "1500", "15,50", "1.500", "$ 1.500,50".
    var t = (texto || '').replace(/[^\d,.-]/g, '').trim();
    if (!t) return 0;
    if (t.indexOf(',') !== -1) {
      t = t.replace(/\./g, '').replace(',', '.');
    } else {
      t = t.replace(/\./g, '');
    }
    var n = parseFloat(t);
    return isNaN(n) ? 0 : Math.round(n * 100);
  }

  function descuentoCentavos(subtotal) {
    var raw = (descuentoEl.value || '').trim();
    if (!raw) return 0;
    if (raw.endsWith('%')) {
      var pct = parseFloat(raw.replace('%', '').replace(',', '.'));
      if (isNaN(pct) || pct < 0 || pct > 100) return 0;
      return Math.round(subtotal * pct / 100);
    }
    return Math.min(parsearMonto(raw), subtotal);
  }

  function subtotal() {
    return lineas.reduce(function (acc, l) { return acc + l.precio * l.cantidad; }, 0);
  }

  function total() {
    var sub = subtotal();
    return sub - descuentoCentavos(sub);
  }

  function render() {
    lineasEl.querySelectorAll('.pos-linea').forEach(function (n) { n.remove(); });
    vacio.style.display = lineas.length ? 'none' : '';

    lineas.forEach(function (l) {
      var row = document.createElement('div');
      row.className = 'pos-linea';
      if (l.pesable) {
        row.innerHTML =
          '<span class="pos-linea-nombre"></span>' +
          '<span class="pos-linea-cant">' +
            '<input type="number" class="pos-peso form-control form-control-sm" min="0.001" step="0.001">' +
            '<button type="button" class="pos-menos" aria-label="Quitar">✕</button>' +
          '</span>' +
          '<span class="pos-linea-sub tabular"></span>';
        row.querySelector('.pos-linea-nombre').textContent = l.nombre + ' ($/kg)';
        var campo = row.querySelector('.pos-peso');
        campo.value = l.cantidad;
        campo.addEventListener('input', function () {
          var v = parseFloat(campo.value);
          l.cantidad = isNaN(v) || v < 0 ? 0 : v;
          row.querySelector('.pos-linea-sub').textContent = moneda(l.precio * l.cantidad);
          actualizarTotales();
        });
        row.querySelector('.pos-menos').addEventListener('click', function () { cambiar(l.id, 0, true); });
      } else {
        row.innerHTML =
          '<span class="pos-linea-nombre"></span>' +
          '<span class="pos-linea-cant">' +
            '<button type="button" class="pos-menos" aria-label="Quitar uno">−</button>' +
            '<span class="tabular"></span>' +
            '<button type="button" class="pos-mas" aria-label="Agregar uno">+</button>' +
          '</span>' +
          '<span class="pos-linea-sub tabular"></span>';
        row.querySelector('.pos-linea-nombre').textContent = l.nombre;
        row.querySelector('.pos-linea-cant .tabular').textContent = l.cantidad;
        row.querySelector('.pos-linea-sub').textContent = moneda(l.precio * l.cantidad);
        row.querySelector('.pos-menos').addEventListener('click', function () { cambiar(l.id, -1); });
        row.querySelector('.pos-mas').addEventListener('click', function () { cambiar(l.id, 1); });
      }
      lineasEl.appendChild(row);
    });

    actualizarTotales();
  }

  function actualizarTotales() {
    var sub = subtotal();
    var tot = total();
    cantidadEl.textContent = lineas.reduce(function (a, l) { return a + l.cantidad; }, 0);
    subtotalEl.textContent = moneda(sub);
    totalEl.textContent = moneda(tot);
    cobrarBtn.disabled = lineas.length === 0;
    actualizarVuelto();
  }

  function agregar(articulo) {
    var existente = lineas.filter(function (l) { return l.id === articulo.id; })[0];
    if (existente) {
      if (!existente.pesable) existente.cantidad += cantDefault;
    } else {
      lineas.push({
        id: articulo.id, nombre: articulo.nombre, precio: articulo.precio,
        cantidad: articulo.es_pesable ? 0.25 : cantDefault,
        pesable: !!articulo.es_pesable, unidad: articulo.unidad,
      });
    }
    render();
  }

  function cambiar(id, delta, quitar) {
    var l = lineas.filter(function (x) { return x.id === id; })[0];
    if (!l) return;
    if (quitar) {
      lineas = lineas.filter(function (x) { return x.id !== id; });
    } else {
      l.cantidad += delta;
      if (l.cantidad <= 0) {
        lineas = lineas.filter(function (x) { return x.id !== id; });
      }
    }
    render();
  }

  function actualizarVuelto() {
    var esEfectivo = metodoEl.options[metodoEl.selectedIndex].dataset.efectivo === 'true';
    efectivoBloque.classList.toggle('d-none', !esEfectivo);
    if (!esEfectivo) return;
    var recibido = parsearMonto(recibidoEl.value);
    var tot = total();
    vueltoEl.textContent = moneda(Math.max(recibido - tot, 0));
  }

  // ---- Busqueda / escaneo -------------------------------------------------
  function pedir(q) {
    return fetch(cfg.buscarUrl + '?q=' + encodeURIComponent(q))
      .then(function (r) { return r.json(); })
      .then(function (data) { return { articulos: data.articulos || [], match: data.match || null }; });
  }

  function mostrarResultados(articulos) {
    resultados.innerHTML = '';
    if (!articulos.length) {
      resultados.innerHTML = '<p class="empty-state small">Sin coincidencias.</p>';
      return;
    }
    articulos.forEach(function (a) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'pos-resultado';
      btn.innerHTML = '<span class="pos-resultado-nombre"></span><span class="pos-resultado-precio tabular"></span>';
      btn.querySelector('.pos-resultado-nombre').textContent = a.nombre;
      btn.querySelector('.pos-resultado-precio').textContent = moneda(a.precio);
      btn.addEventListener('click', function () {
        agregar(a);
        resultados.innerHTML = '';
        scan.value = '';
        scan.focus();
      });
      resultados.appendChild(btn);
    });
  }

  function buscar() {
    var q = scan.value.trim();
    if (!q) { resultados.innerHTML = ''; return; }
    pedir(q).then(function (res) {
      // Escaneo: solo si el codigo coincide exacto con un codigo de barras.
      // La busqueda por texto (teclado) siempre muestra la lista para elegir.
      if (res.match === 'codigo' && res.articulos.length === 1) {
        agregar(res.articulos[0]);
        scan.value = '';
        resultados.innerHTML = '';
        return;
      }
      mostrarResultados(res.articulos);
    });
  }

  scan.addEventListener('input', function () {
    clearTimeout(scan._timer);
    scan._timer = setTimeout(buscar, 220);
  });
  scan.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      clearTimeout(scan._timer);
      buscar();
    }
  });

  // ---- Captura global del lector HID (keyboard wedge) --------------------
  var buf = '';
  var ultimo = 0;
  document.addEventListener('keydown', function (ev) {
    if (ev.target === scan || ev.target.tagName === 'INPUT' || ev.target.tagName === 'SELECT') return;
    if (ev.key === 'Enter') {
      if (buf.length >= 4) {
        scan.value = buf;
        buscar();
        scan.value = '';
      }
      buf = '';
      return;
    }
    if (ev.key.length === 1) {
      var ahora = Date.now();
      if (ahora - ultimo > (scanCfg.ms || 120)) buf = '';  // tecleo humano lento
      buf += ev.key;
      ultimo = ahora;
    }
  });

  // ---- Cobro --------------------------------------------------------------
  metodoEl.addEventListener('change', actualizarVuelto);
  recibidoEl.addEventListener('input', actualizarVuelto);
  descuentoEl.addEventListener('input', render);

  cobrarBtn.addEventListener('click', function () {
    errorEl.classList.add('d-none');
    var payload = {
      lineas: lineas.map(function (l) { return { articulo_id: l.id, cantidad: l.cantidad }; }),
      metodo_pago_id: parseInt(metodoEl.value, 10) || 0,
      descuento: descuentoCentavos(subtotal()),
      pago_recibido: parsearMonto(recibidoEl.value)
    };
    cobrarBtn.disabled = true;
    fetch(cfg.cobrarUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': cfg.csrf },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (res.ok && res.data.ok) {
          var v = res.data.venta;
          window.open(v.ticket_url, '_blank');
          lineas = [];
          descuentoEl.value = '';
          recibidoEl.value = '';
          render();
          scan.focus();
        } else {
          errorEl.textContent = (res.data && res.data.error) || 'No se pudo cobrar.';
          errorEl.classList.remove('d-none');
          cobrarBtn.disabled = false;
        }
      })
      .catch(function () {
        errorEl.textContent = 'Error de red al cobrar.';
        errorEl.classList.remove('d-none');
        cobrarBtn.disabled = false;
      });
  });

  render();
  scan.focus();
})();
