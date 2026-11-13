(function () {
  "use strict";
  var CSRF = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  function $(id) { return document.getElementById(id); }
  function el(tag, texto, cls) {
    var e = document.createElement(tag);
    if (texto !== undefined && texto !== null) e.textContent = String(texto);
    if (cls) e.className = cls;
    return e;
  }
  function pedir(url, metodo, cuerpo) {
    var op = { method: metodo || "GET", headers: { "Accept": "application/json" }, credentials: "same-origin" };
    if (metodo && metodo !== "GET") {
      op.headers["Content-Type"] = "application/json";
      op.headers["X-CSRF-Token"] = CSRF;
      op.body = JSON.stringify(cuerpo || {});
    }
    return fetch(url, op).then(function (r) {
      if (r.status === 401) { window.location = "/login"; throw new Error("sesión"); }
      return r.json().then(function (d) { return { ok: r.ok, status: r.status, datos: d }; });
    });
  }
  function nota(caja, ok, titulo, lineas) {
    caja.className = "note show " + (ok ? "ok" : "bad");
    caja.textContent = "";
    caja.appendChild(el("strong", titulo));
    (lineas || []).forEach(function (l) { if (l) caja.appendChild(el("span", l, "nota-alerta")); });
  }
  function tabla(cont, cols, filas, vacio) {
    cont.textContent = "";
    if (!filas.length) { cont.appendChild(el("p", vacio || "Sin datos.", "empty")); return; }
    var t = el("table"), th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { tr.appendChild(el("th", c.t)); });
    th.appendChild(tr); t.appendChild(th);
    var tb = el("tbody");
    filas.forEach(function (f) {
      var r = el("tr");
      cols.forEach(function (c) { r.appendChild(el("td", c.v(f), c.cls)); });
      tb.appendChild(r);
    });
    t.appendChild(tb); cont.appendChild(t);
  }
  function num(id) { var v = $(id).value; return v === "" ? null : Number(v); }
  function dato(v) { return v === null || v === undefined ? "—" : v; }
  function nota1(v) { return v === null || v === undefined ? "—" : Number(v).toFixed(1); }
  function detalleRechazo(d) {
    return [d.capa ? "Rechazado por: " + d.capa : "", d.regla ? "Regla: " + d.regla : ""];
  }

  // Muestra a qué estudiante corresponde el número escrito
  function consultarEstudiante(idCampo, idSalida) {
    var id = num(idCampo), salida = $(idSalida);
    if (!id) { salida.textContent = ""; return; }
    pedir("/api/estudiante/" + id).then(function (r) {
      var d = r.datos;
      salida.textContent = r.ok
        ? d.codigo_estudiante + " · " + d.programa + " · " + d.resultado +
          " · semestres registrados: " + (d.semestres_registrados.length ? d.semestres_registrados.join(", ") : "ninguno")
        : (d.message || "Ese estudiante no existe");
    });
  }
  $("r-est").addEventListener("change", function () { consultarEstudiante("r-est", "r-lookup"); });
  $("m-est").addEventListener("change", function () { consultarEstudiante("m-est", "m-lookup"); cargarHistorial(); });

  // ---- 1. Rendimiento ----
  function cargarRendimientos() {
    pedir("/api/rendimiento").then(function (r) {
      tabla($("r-tabla"), [
        { t: "Estudiante", v: function (f) { return f.codigo_estudiante; }, cls: "celda-mono" },
        { t: "Programa", v: function (f) { return f.programa; } },
        { t: "Semestre", v: function (f) { return f.semestre; } },
        { t: "Matriculadas", v: function (f) { return f.matriculadas; } },
        { t: "Aprobadas", v: function (f) { return f.aprobadas; } },
        { t: "Nota", v: function (f) { return nota1(f.nota_promedio); } }
      ], r.datos, "Todavía no hay registros.");
    });
  }
  $("form-rend").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var cuerpo = {
      id_estudiante: $("r-est").value, semestre: $("r-sem").value,
      matriculadas: $("r-mat").value, aprobadas: $("r-apr").value,
      nota_promedio: $("r-nota").value, creditadas: $("r-cre").value,
      evaluadas: $("r-eva").value, sin_evaluacion: $("r-sin").value
    };
    pedir("/api/rendimiento", "POST", cuerpo).then(function (r) {
      var d = r.datos;
      if (r.ok) {
        nota($("r-note"), true, d.message, [d.alerta ? d.alerta.mensaje : ""]);
        cargarRendimientos(); cargarAlertas(); consultarEstudiante("r-est", "r-lookup");
      } else {
        nota($("r-note"), false, d.message || "No se guardó", detalleRechazo(d));
      }
    });
  });

  // ---- 2. Alertas ----
  function cargarAlertas() {
    var u = $("a-umbral").value;
    pedir("/api/alertas?umbral=" + encodeURIComponent(u) + "&limite=15").then(function (r) {
      var d = r.datos;
      if (!r.ok) { $("a-resumen").textContent = d.message || "No se pudo calcular"; return; }
      $("a-resumen").textContent = d.en_alerta + " de " + d.matriculados + " estudiantes matriculados están en alerta" +
        (d.sin_datos ? " (" + d.sin_datos + " sin unidades matriculadas en su último semestre, no se pueden evaluar)" : "") +
        ". Se muestran los " + d.filas.length + " con menor aprobación.";
      tabla($("a-tabla"), [
        { t: "Estudiante", v: function (f) { return f.codigo_estudiante; }, cls: "celda-mono" },
        { t: "Programa", v: function (f) { return f.programa; } },
        { t: "Último semestre", v: function (f) { return f.semestre; } },
        { t: "Aprobadas / matriculadas", v: function (f) { return f.aprobadas + " / " + f.matriculadas; } },
        { t: "Aprobación", v: function (f) { return Math.round(f.proporcion * 100) + " %"; } }
      ], d.filas, "Ningún estudiante cae bajo el umbral.");
    });
  }
  $("a-umbral").addEventListener("change", cargarAlertas);

  // ---- 3. Resultado por programa ----
  function cargarProgramas() {
    var p = $("p-filtro").value;
    pedir("/api/resultado-por-programa" + (p ? "?id_curso=" + encodeURIComponent(p) : "")).then(function (r) {
      tabla($("p-tabla"), [
        { t: "Programa", v: function (f) { return f.programa; } },
        { t: "Estudiantes", v: function (f) { return f.total; } },
        { t: "Desertaron", v: function (f) { return f.desertores; } },
        { t: "Matriculados", v: function (f) { return f.matriculados; } },
        { t: "Graduados", v: function (f) { return f.graduados; } },
        { t: "% deserción", v: function (f) { return f.pct_desercion + " %"; } }
      ], r.datos, "Sin datos.");
    });
  }
  $("p-filtro").addEventListener("change", cargarProgramas);

  // ---- 4. Matrícula ----
  function cargarHistorial() {
    var id = num("m-est");
    if (!id) return;
    pedir("/api/estudiante/" + id + "/historial-matricula").then(function (r) {
      tabla($("m-hist"), [
        { t: "Fecha (UTC)", v: function (f) { return f.cambiado_en; } },
        { t: "Antes", v: function (f) { return f.estado_anterior ? "Al día" : "Atrasada"; } },
        { t: "Después", v: function (f) { return f.estado_nuevo ? "Al día" : "Atrasada"; } },
        { t: "Lo cambió", v: function (f) { return dato(f.por); } }
      ], Array.isArray(r.datos) ? r.datos : [], "Este estudiante no tiene cambios registrados.");
    });
  }
  $("form-mat").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var id = num("m-est");
    pedir("/api/estudiante/" + id + "/matricula", "POST", {
      matricula_al_dia: $("m-estado").value,
      simular_falla: $("m-falla").checked
    }).then(function (r) {
      var d = r.datos, l = [];
      if (d.pasos) l = d.pasos.concat(["Matrícula antes: " + d.estado_antes + " · después: " + d.estado_despues +
                                      " · filas en historial: " + d.filas_en_historial]);
      nota($("m-note"), r.ok, d.message || "No se actualizó", r.ok ? l : detalleRechazo(d).concat(l));
      cargarHistorial();
    });
  });

  // ---- 5. Rechazo ----
  $("btn-rechazo").addEventListener("click", function () {
    pedir("/api/prueba-rechazo", "POST", {}).then(function (r) {
      var d = r.datos;
      nota($("x-note"), false, d.message || "Rechazado",
        detalleRechazo(d).concat([d.intento ? "Intento: " + d.intento : "",
          d.filas_antes !== undefined ? "Filas antes: " + d.filas_antes + " · después: " + d.filas_despues : ""]));
    });
  });

  cargarRendimientos(); cargarAlertas(); cargarProgramas();
})();
