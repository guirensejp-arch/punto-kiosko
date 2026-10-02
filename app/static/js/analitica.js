/* Gráficos de Analítica. Lee los datos embebidos en #analitica-datos y usa
   Chart.js (CDN). Si Chart.js no cargó, la página sigue funcionando con KPIs
   y tablas: el script sale sin hacer nada. */
(function () {
  'use strict';

  var contenedor = document.getElementById('analitica-datos');
  if (!contenedor || !window.Chart) {
    return;
  }

  var datos;
  try {
    datos = JSON.parse(contenedor.textContent);
  } catch (error) {
    return;
  }

  var estilos = getComputedStyle(document.documentElement);
  function color(nombre, respaldo) {
    var valor = (estilos.getPropertyValue(nombre) || '').trim();
    return valor || respaldo;
  }

  var tinta = color('--color-ink', '#1C1815');
  var tinta2 = color('--color-ink-2', '#5B534B');
  var tinta3 = color('--color-ink-3', '#8A8078');
  var linea = color('--color-line', '#E3D9C9');
  var acento = color('--color-accent', '#DB423C');
  var acentoFuerte = color('--color-accent-strong', '#A62B23');
  var arena = color('--tint-sand-ink', '#8A6A2F');

  // Paleta cálida y terrosa: nada de azul/cian/violeta.
  var paleta = [
    acento, acentoFuerte, tinta, arena, '#5F6B3F',
    '#B4763A', '#7A5A3A', '#9C8A6A',
  ];

  var fuente = "'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif";

  Chart.defaults.font.family = fuente;
  Chart.defaults.font.size = 12;
  Chart.defaults.color = tinta2;
  Chart.defaults.animation = false;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;

  function conAlfa(hex, alfa) {
    return /^#[0-9a-fA-F]{6}$/.test(hex) ? hex + alfa : hex;
  }

  var rejilla = {
    grid: { color: linea, drawTicks: false },
    border: { display: false },
    ticks: { color: tinta3, padding: 6 },
  };

  var formatoMoneda = new Intl.NumberFormat('es-AR', {
    style: 'currency', currency: 'ARS', maximumFractionDigits: 0,
  });
  var formatoNumero = new Intl.NumberFormat('es-AR');

  function moneda(centavos) {
    return formatoMoneda.format((centavos || 0) / 100);
  }

  function numero(valor) {
    return formatoNumero.format(valor || 0);
  }

  function crear(id, configuracion) {
    var canvas = document.getElementById(id);
    if (!canvas) {
      return;
    }
    new Chart(canvas, configuracion);
  }

  var ejesMoneda = {
    x: rejilla,
    y: Object.assign({}, rejilla, {
      ticks: { color: tinta3, callback: function (valor) { return moneda(valor); } },
    }),
  };
  var tooltipMoneda = {
    callbacks: {
      label: function (contexto) {
        return (contexto.dataset.label || '') + ': ' + moneda(contexto.parsed.y);
      },
    },
  };

  crear('graficoVentas', {
    type: 'line',
    data: {
      labels: datos.serie.labels,
      datasets: [{
        label: 'Ventas',
        data: datos.serie.ventas,
        borderColor: acento,
        backgroundColor: conAlfa(acento, '22'),
        fill: true,
        tension: 0.3,
        pointRadius: 2,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: tooltipMoneda },
      scales: ejesMoneda,
    },
  });

  crear('graficoPedidos', {
    type: 'bar',
    data: {
      labels: datos.serie.labels,
      datasets: [{
        label: 'Pedidos',
        data: datos.serie.ventas,
        backgroundColor: tinta,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (contexto) {
              return numero(contexto.parsed.y) + ' ventas';
            },
          },
        },
      },
      scales: { x: rejilla, y: rejilla },
    },
  });

  crear('graficoTicket', {
    type: 'line',
    data: {
      labels: datos.serie.labels,
      datasets: [{
        label: 'Ticket promedio',
        data: datos.serie.ticket,
        borderColor: acentoFuerte,
        backgroundColor: conAlfa(acentoFuerte, '22'),
        fill: true,
        tension: 0.3,
        pointRadius: 2,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: tooltipMoneda },
      scales: ejesMoneda,
    },
  });

  function tarta(id, bloque) {
    crear(id, {
      type: 'doughnut',
      data: {
        labels: bloque.labels,
        datasets: [{
          data: bloque.valores,
          backgroundColor: paleta,
          borderColor: color('--color-surface', '#ffffff'),
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        cutout: '62%',
        plugins: {
          legend: { position: 'bottom' },
          tooltip: {
            callbacks: {
              label: function (contexto) {
                return contexto.label + ': ' + moneda(contexto.parsed);
              },
            },
          },
        },
      },
    });
  }

  tarta('graficoMetodos', datos.metodos);

  function barraHorizontal(id, bloque, etiqueta, formateador) {
    crear(id, {
      type: 'bar',
      data: {
        labels: bloque.labels,
        datasets: [{
          label: etiqueta,
          data: bloque.valores,
          backgroundColor: acento,
          borderRadius: 3,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (contexto) {
                return etiqueta + ': ' + formateador(contexto.parsed.x);
              },
            },
          },
        },
        scales: {
          x: Object.assign({}, rejilla, {
            ticks: { color: tinta3, callback: function (valor) { return formateador(valor); } },
          }),
          y: rejilla,
        },
      },
    });
  }

  barraHorizontal('graficoTopUnidades', datos.top_unidades, 'Unidades', numero);
  barraHorizontal('graficoTopFacturacion', datos.top_facturacion, 'Facturación', moneda);
})();
