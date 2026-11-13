"""SAT-Deserción · Momento 3 — aplicación conectada a la base del proyecto.

Qué hace:
  1. Cuentas con rol (coordinador, consejero) y contraseñas guardadas como hash.
  2. Registrar el rendimiento semestral de un estudiante, con respuesta de alerta al instante.
  3. Alerta de riesgo: matriculados con menos del 50 % de unidades aprobadas en su último semestre.
  4. Resultado por programa, con el nombre del programa.
  5. Actualizar el estado de matrícula (solo coordinador) con transacción e historial de quién cambió.
  6. Prueba del rechazo de la base (CHECK aprobadas <= matriculadas).

Seguridad: consultas parametrizadas, salida escapada, política CSP sin scripts en línea, token CSRF,
cookie de sesión HttpOnly/SameSite, contraseñas con hash y sal. No hay claves escritas en el código:
la clave de la sesión sale de la variable de entorno SAT_SECRET (o se genera al arrancar).
"""
import math
import os
import secrets
import sqlite3
import time
from datetime import timedelta
from functools import wraps

from flask import (Flask, g, jsonify, redirect, render_template, request, session, url_for)

import cargar_datos
import seguridad

DB_PATH = cargar_datos.DB_POR_DEFECTO
UMBRAL_POR_DEFECTO = 0.5

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SAT_SECRET") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    MAX_CONTENT_LENGTH=64 * 1024,
)


# ---------------------------------------------------------------- base de datos
def get_db():
    if "db" not in g:
        g.db = cargar_datos.conectar(DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def asegurar_base():
    """Si la base no existe todavía, la crea y carga los estudiantes (proceso repetible)."""
    conn = cargar_datos.conectar(DB_PATH)
    cargar_datos.crear_esquema(conn)
    hay = conn.execute("SELECT COUNT(*) FROM Estudiantes").fetchone()[0]
    conn.close()
    if hay == 0:
        cargar_datos.cargar(db_path=DB_PATH)


# ---------------------------------------------------------------- reglas: qué frena cada restricción
REGLAS_BASE = [
    ("ck_aprobadas_le_matriculadas", "Las unidades aprobadas no pueden superar las matriculadas",
     "CHECK aprobadas <= matriculadas"),
    ("ck_nota_rango", "La nota promedio debe estar entre 0 y 20", "CHECK nota_promedio entre 0 y 20"),
    ("ck_semestre_rango", "El semestre debe estar entre 1 y 12", "CHECK semestre entre 1 y 12"),
    ("Rendimiento_Semestral.id_estudiante, Rendimiento_Semestral.semestre",
     "Ya existe un registro de rendimiento para ese estudiante en ese semestre",
     "UNIQUE (id_estudiante, semestre)"),
    ("FOREIGN KEY", "Ese estudiante no existe", "FOREIGN KEY id_estudiante → Estudiantes"),
    ("ck_cambio_real", "El estudiante ya estaba en ese estado de matrícula", "CHECK estado_anterior <> estado_nuevo"),
    ("ck_matricula_binaria", "El estado de matrícula solo puede ser 0 o 1", "CHECK matricula_al_dia IN (0,1)"),
]


def explicar_rechazo(exc):
    texto = str(exc)
    for clave, mensaje, regla in REGLAS_BASE:
        if clave in texto:
            return mensaje, regla
    return "La base rechazó el dato", texto


def respuesta_base(exc, status=409):
    mensaje, regla = explicar_rechazo(exc)
    return jsonify(ok=False, capa="base de datos", message=mensaje, regla=regla, detalle=str(exc)), status


def respuesta_app(mensaje, regla, status=400):
    return jsonify(ok=False, capa="aplicación", message=mensaje, regla=regla), status


def entero(valor, defecto=None):
    """Convierte a entero; devuelve defecto si viene vacío. Lanza ValueError si el formato es inválido."""
    if valor is None or valor == "":
        return defecto
    f = float(valor)
    if not math.isfinite(f) or f != int(f):
        raise ValueError("no es entero")
    return int(f)


# ---------------------------------------------------------------- sesión, CSRF y permisos
def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.context_processor
def contexto():
    return {"csrf": token_csrf(), "usuario": usuario_actual()}


def usuario_actual():
    if "usuario" in g:
        return g.usuario
    g.usuario = None
    uid = session.get("uid")
    if uid is not None:
        g.usuario = get_db().execute(
            "SELECT id_usuario, correo, nombre, rol FROM Usuarios WHERE id_usuario = ?", (uid,)).fetchone()
        if g.usuario is None:
            session.pop("uid", None)
    return g.usuario


def login_requerido(f):
    @wraps(f)
    def interno(*a, **k):
        if usuario_actual() is None:
            if request.path.startswith("/api/"):
                return jsonify(ok=False, capa="seguridad", message="Inicia sesión para continuar",
                               regla="autenticación requerida"), 401
            return redirect(url_for("login"))
        return f(*a, **k)
    return interno


def rol_requerido(rol):
    def deco(f):
        @wraps(f)
        @login_requerido
        def interno(*a, **k):
            if usuario_actual()["rol"] != rol:
                return jsonify(ok=False, capa="seguridad", message=f"Solo el rol {rol} puede hacer esto",
                               regla="autorización por rol"), 403
            return f(*a, **k)
        return interno
    return deco


@app.before_request
def proteger_posts():
    if request.method == "POST":
        enviado = request.headers.get("X-CSRF-Token") or request.form.get("csrf") or ""
        esperado = session.get("csrf", "")
        if not esperado or not secrets.compare_digest(enviado, esperado):
            if request.path.startswith("/api/"):
                return jsonify(ok=False, capa="seguridad", message="La sesión venció o la petición no es válida: recarga la página",
                               regla="token CSRF"), 403
            return "Petición no válida (token CSRF)", 403


@app.after_request
def cabeceras(resp):
    # Sin scripts en línea: aunque alguien lograra meter un <script> en la página, el navegador no lo ejecuta.
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none'; "
        "form-action 'self'; base-uri 'none'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    if not request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# Límite de intentos de inicio de sesión: 5 fallos en 5 minutos por correo y dirección.
INTENTOS = {}
VENTANA, MAX_FALLOS = 300, 5


def _clave_intento(correo):
    return (correo.lower(), request.remote_addr)


def bloqueado(correo):
    ahora = time.time()
    lista = [t for t in INTENTOS.get(_clave_intento(correo), []) if ahora - t < VENTANA]
    INTENTOS[_clave_intento(correo)] = lista
    return len(lista) >= MAX_FALLOS


# ---------------------------------------------------------------- cuentas
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)
    correo = (request.form.get("correo") or "").strip()
    clave = request.form.get("clave") or ""
    if bloqueado(correo):
        return render_template("login.html", error="Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo."), 429
    fila = get_db().execute(
        "SELECT id_usuario, hash_clave FROM Usuarios WHERE correo = ?", (correo,)).fetchone()  # consulta parametrizada
    ok = seguridad.verificar(fila["hash_clave"] if fila else seguridad.HASH_RELLENO, clave) and fila is not None
    if not ok:
        INTENTOS.setdefault(_clave_intento(correo), []).append(time.time())
        # Mismo mensaje exista o no el correo: no se revela qué cuentas existen.
        return render_template("login.html", error="Correo o contraseña incorrectos"), 401
    INTENTOS.pop(_clave_intento(correo), None)
    session.clear()  # sesión nueva al entrar (evita fijación de sesión)
    session["uid"] = fila["id_usuario"]
    session.permanent = True
    token_csrf()
    return redirect(url_for("index"))


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "GET":
        return render_template("registro.html", error=None, valores={})
    valores = {"correo": request.form.get("correo", ""), "nombre": request.form.get("nombre", "")}
    clave = request.form.get("clave") or ""
    if clave != (request.form.get("clave2") or ""):
        return render_template("registro.html", error="Las contraseñas no coinciden", valores=valores), 400
    db = get_db()
    try:
        # El registro público solo crea consejeros. Los coordinadores se crean con crear_usuario.py.
        seguridad.crear_usuario(db, valores["correo"], valores["nombre"], clave, "consejero")
    except ValueError as e:
        return render_template("registro.html", error=str(e), valores=valores), 400
    return redirect(url_for("login"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- páginas y consultas auxiliares
@app.route("/")
@login_requerido
def index():
    db = get_db()
    programas = db.execute("SELECT id_curso, nombre FROM Cursos ORDER BY nombre").fetchall()
    n_est = db.execute("SELECT COUNT(*) FROM Estudiantes").fetchone()[0]
    n_ren = db.execute("SELECT COUNT(*) FROM Rendimiento_Semestral").fetchone()[0]
    return render_template("index.html", programas=programas, n_est=n_est, n_ren=n_ren)


@app.route("/api/estudiante/<int:id_estudiante>")
@login_requerido
def ver_estudiante(id_estudiante):
    db = get_db()
    e = db.execute(
        """SELECT e.id_estudiante, e.codigo_estudiante, c.nombre AS programa, e.matricula_al_dia, e.resultado
           FROM Estudiantes e JOIN Cursos c ON c.id_curso = e.id_curso
           WHERE e.id_estudiante = ?""",
        (id_estudiante,),
    ).fetchone()
    if e is None:
        return jsonify(ok=False, message="Ese estudiante no existe"), 404
    semestres = [r[0] for r in db.execute(
        "SELECT semestre FROM Rendimiento_Semestral WHERE id_estudiante = ? ORDER BY semestre", (id_estudiante,))]
    return jsonify(ok=True, **dict(e), semestres_registrados=semestres)


# ---------------------------------------------------------------- registrar rendimiento
@app.route("/api/rendimiento", methods=["GET"])
@login_requerido
def listar_rendimiento():
    db = get_db()
    filas = db.execute(
        """SELECT r.id_rendimiento, e.codigo_estudiante, c.nombre AS programa, r.semestre,
                  r.matriculadas, r.aprobadas, r.nota_promedio
           FROM Rendimiento_Semestral r
           JOIN Estudiantes e ON e.id_estudiante = r.id_estudiante
           JOIN Cursos c ON c.id_curso = e.id_curso
           ORDER BY r.id_rendimiento DESC LIMIT 10"""
    ).fetchall()
    return jsonify([dict(f) for f in filas])


def evaluar_alerta(db, id_estudiante, umbral=UMBRAL_POR_DEFECTO):
    """Aplica la regla al último semestre registrado de un estudiante."""
    e = db.execute("SELECT resultado FROM Estudiantes WHERE id_estudiante = ?", (id_estudiante,)).fetchone()
    u = db.execute(
        "SELECT semestre, matriculadas, aprobadas FROM Rendimiento_Semestral WHERE id_estudiante = ? "
        "ORDER BY semestre DESC LIMIT 1", (id_estudiante,)).fetchone()
    if e is None or u is None:
        return {"estado": "sin_datos", "mensaje": "Todavía no hay rendimiento registrado"}
    if e["resultado"] != "Enrolled":
        return {"estado": "no_aplica", "mensaje": "La alerta aplica a estudiantes matriculados actualmente"}
    if u["matriculadas"] == 0:
        return {"estado": "sin_datos", "mensaje": "Sin unidades matriculadas en el último semestre: no se puede calcular"}
    p = u["aprobadas"] / u["matriculadas"]
    detalle = f"{u['aprobadas']} de {u['matriculadas']} unidades aprobadas ({round(100 * p)} %) en el semestre {u['semestre']}"
    if p < umbral:
        return {"estado": "en_riesgo", "proporcion": p, "mensaje": f"En alerta de riesgo: {detalle}"}
    return {"estado": "sin_riesgo", "proporcion": p, "mensaje": f"Sin alerta: {detalle}"}


@app.route("/api/rendimiento", methods=["POST"])
@login_requerido
def registrar_rendimiento():
    """La aplicación revisa que el dato llegue completo y bien escrito.
    La base decide si el dato tiene sentido (CHECK, UNIQUE, FOREIGN KEY)."""
    d = request.get_json(silent=True) or {}
    obligatorios = {"id_estudiante": "estudiante", "semestre": "semestre",
                    "matriculadas": "unidades matriculadas", "aprobadas": "unidades aprobadas"}
    faltan = [txt for k, txt in obligatorios.items() if d.get(k) in (None, "")]
    if faltan:
        return respuesta_app("Faltan datos obligatorios: " + ", ".join(faltan), "dato obligatorio")
    try:
        nota = float(d["nota_promedio"]) if d.get("nota_promedio") not in (None, "") else None
        if nota is not None and not math.isfinite(nota):
            raise ValueError("nota no finita")
        valores = (
            entero(d["id_estudiante"]), entero(d["semestre"]),
            entero(d.get("creditadas"), 0), entero(d["matriculadas"]), entero(d.get("evaluadas"), 0),
            entero(d["aprobadas"]), nota, entero(d.get("sin_evaluacion"), 0),
        )
    except (TypeError, ValueError, OverflowError):
        return respuesta_app("Un campo numérico no tiene un formato válido", "formato numérico")
    id_est, semestre, creditadas, matriculadas, evaluadas, aprobadas, nota, sin_eval = valores
    if min(creditadas, matriculadas, evaluadas, aprobadas, sin_eval) < 0:
        return respuesta_app("Las unidades no pueden ser negativas", "valor no negativo")

    db = get_db()
    db.execute("BEGIN")
    try:
        db.execute(
            """INSERT INTO Rendimiento_Semestral
               (id_estudiante, semestre, creditadas, matriculadas, evaluadas, aprobadas, nota_promedio,
                sin_evaluacion, registrado_por)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            valores + (usuario_actual()["id_usuario"],),
        )
        db.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        db.execute("ROLLBACK")
        status = 404 if "FOREIGN KEY" in str(exc) else (409 if "UNIQUE" in str(exc) else 422)
        return respuesta_base(exc, status)
    return jsonify(ok=True, message="Rendimiento registrado correctamente",
                   regla="pasó las revisiones de la aplicación y las de la base",
                   alerta=evaluar_alerta(db, id_est))


# ---------------------------------------------------------------- alerta de riesgo (regla determinista)
@app.route("/api/alertas")
@login_requerido
def alertas():
    """Regla: estudiante matriculado (Enrolled) cuyo último semestre registrado tiene más de 0 unidades
    matriculadas y una proporción aprobadas/matriculadas menor que el umbral (0,5 por defecto)."""
    try:
        umbral = float(request.args.get("umbral", UMBRAL_POR_DEFECTO))
        limite = entero(request.args.get("limite"), 25)
    except (ValueError, OverflowError):
        return respuesta_app("El umbral y el límite deben ser números", "formato numérico")
    if not (math.isfinite(umbral) and 0 < umbral <= 1):
        return respuesta_app("El umbral debe ser mayor que 0 y no pasar de 1", "umbral entre 0 y 1")
    if not 1 <= limite <= 100:
        return respuesta_app("El límite debe estar entre 1 y 100", "límite entre 1 y 100")
    db = get_db()
    base = """WITH ult AS (
                SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.id_estudiante ORDER BY r.semestre DESC) AS rn
                FROM Rendimiento_Semestral r)
              SELECT e.id_estudiante, e.codigo_estudiante, c.nombre AS programa, u.semestre, u.matriculadas,
                     u.aprobadas, u.nota_promedio, 1.0 * u.aprobadas / u.matriculadas AS proporcion
              FROM ult u
              JOIN Estudiantes e ON e.id_estudiante = u.id_estudiante
              JOIN Cursos c ON c.id_curso = e.id_curso
              WHERE u.rn = 1 AND e.resultado = 'Enrolled' AND u.matriculadas > 0
                AND 1.0 * u.aprobadas / u.matriculadas < :umbral"""
    total_alerta = db.execute(f"SELECT COUNT(*) FROM ({base})", {"umbral": umbral}).fetchone()[0]
    filas = db.execute(base + " ORDER BY proporcion ASC, u.nota_promedio ASC, e.id_estudiante ASC LIMIT :limite",
                       {"umbral": umbral, "limite": limite}).fetchall()
    resumen = db.execute(
        """WITH ult AS (
             SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.id_estudiante ORDER BY r.semestre DESC) AS rn
             FROM Rendimiento_Semestral r)
           SELECT COUNT(*) AS matriculados, COALESCE(SUM(u.matriculadas = 0), 0) AS sin_datos
           FROM ult u JOIN Estudiantes e ON e.id_estudiante = u.id_estudiante
           WHERE u.rn = 1 AND e.resultado = 'Enrolled'""").fetchone()
    return jsonify(umbral=umbral, matriculados=resumen["matriculados"], en_alerta=total_alerta,
                   sin_datos=resumen["sin_datos"], filas=[dict(f) for f in filas])


# ---------------------------------------------------------------- resultado por programa
@app.route("/api/resultado-por-programa")
@login_requerido
def resultado_por_programa():
    try:
        id_curso = entero(request.args.get("id_curso"))
    except (ValueError, OverflowError):
        return respuesta_app("El programa debe ser un número", "formato numérico")
    db = get_db()
    filas = db.execute(
        """SELECT c.id_curso, c.nombre AS programa, COUNT(*) AS total,
                  SUM(e.resultado = 'Dropout')  AS desertores,
                  SUM(e.resultado = 'Enrolled') AS matriculados,
                  SUM(e.resultado = 'Graduate') AS graduados,
                  ROUND(100.0 * SUM(e.resultado = 'Dropout') / COUNT(*), 1) AS pct_desercion
           FROM Estudiantes e JOIN Cursos c ON c.id_curso = e.id_curso
           WHERE (? IS NULL OR c.id_curso = ?)
           GROUP BY c.id_curso, c.nombre
           ORDER BY pct_desercion DESC""",
        (id_curso, id_curso),
    ).fetchall()
    return jsonify([dict(f) for f in filas])


# ---------------------------------------------------------------- actualizar matrícula (transacción)
class FallaSimulada(Exception):
    pass


@app.route("/api/estudiante/<int:id_estudiante>/matricula", methods=["POST"])
@rol_requerido("coordinador")
def actualizar_matricula(id_estudiante):
    """Dos escrituras que deben ocurrir juntas o no ocurrir:
         paso 1: UPDATE Estudiantes.matricula_al_dia
         paso 2: INSERT en Historial_Matricula (de qué a qué, cuándo y quién lo cambió)
    Si algo falla entre un paso y otro, ROLLBACK deja la base como estaba."""
    d = request.get_json(silent=True) or {}
    if d.get("matricula_al_dia") in (None, ""):
        return respuesta_app("Falta el nuevo estado de matrícula", "dato obligatorio")
    try:
        nuevo = entero(d["matricula_al_dia"])
    except (TypeError, ValueError, OverflowError):
        return respuesta_app("El estado de matrícula debe ser 0 o 1", "formato numérico")
    simular = d.get("simular_falla") is True

    db = get_db()
    pasos = []
    db.execute("BEGIN IMMEDIATE")  # bloquea escrituras de otros mientras leemos y cambiamos
    antes = db.execute("SELECT matricula_al_dia FROM Estudiantes WHERE id_estudiante = ?", (id_estudiante,)).fetchone()
    if antes is None:
        db.execute("ROLLBACK")
        return jsonify(ok=False, capa="aplicación", message="Ese estudiante no existe", regla="estudiante existente"), 404
    anterior = antes[0]
    try:
        db.execute("UPDATE Estudiantes SET matricula_al_dia = ? WHERE id_estudiante = ?", (nuevo, id_estudiante))
        pasos.append("paso 1: matrícula actualizada (todavía sin confirmar)")
        if simular:
            raise FallaSimulada()
        db.execute(
            "INSERT INTO Historial_Matricula (id_estudiante, estado_anterior, estado_nuevo, cambiado_por) VALUES (?,?,?,?)",
            (id_estudiante, anterior, nuevo, usuario_actual()["id_usuario"]),
        )
        pasos.append("paso 2: cambio anotado en el historial, con quién lo hizo")
        db.execute("COMMIT")
        pasos.append("COMMIT: los dos pasos quedaron guardados")
        resultado = dict(ok=True, message="Estado de matrícula actualizado y anotado en el historial")
    except FallaSimulada:
        db.execute("ROLLBACK")
        pasos.append("falla simulada antes del paso 2 → ROLLBACK: el paso 1 se deshizo")
        resultado = dict(ok=False, capa="transacción", message="La operación se canceló completa: no quedó nada a medias",
                         regla="transacción: los dos pasos juntos o ninguno")
    except sqlite3.IntegrityError as exc:
        db.execute("ROLLBACK")
        pasos.append("la base rechazó un paso → ROLLBACK: no quedó nada a medias")
        mensaje, regla = explicar_rechazo(exc)
        resultado = dict(ok=False, capa="base de datos", message=mensaje, regla=regla, detalle=str(exc))

    despues = db.execute("SELECT matricula_al_dia FROM Estudiantes WHERE id_estudiante = ?", (id_estudiante,)).fetchone()[0]
    n_hist = db.execute("SELECT COUNT(*) FROM Historial_Matricula WHERE id_estudiante = ?", (id_estudiante,)).fetchone()[0]
    resultado.update(pasos=pasos, estado_antes=anterior, estado_despues=despues, filas_en_historial=n_hist)
    return jsonify(resultado), (200 if resultado["ok"] else 409)


@app.route("/api/estudiante/<int:id_estudiante>/historial-matricula")
@login_requerido
def historial_matricula(id_estudiante):
    db = get_db()
    filas = db.execute(
        """SELECT h.estado_anterior, h.estado_nuevo, h.cambiado_en, u.nombre AS por
           FROM Historial_Matricula h JOIN Usuarios u ON u.id_usuario = h.cambiado_por
           WHERE h.id_estudiante = ? ORDER BY h.id_historial DESC LIMIT 10""",
        (id_estudiante,),
    ).fetchall()
    return jsonify([dict(f) for f in filas])


# ---------------------------------------------------------------- rechazo del CHECK en la base
@app.route("/api/prueba-rechazo", methods=["POST"])
@login_requerido
def prueba_rechazo():
    """Manda directo a la base un rendimiento con más aprobadas (10) que matriculadas (4), sin pasar por
    las revisiones de la aplicación, para ver quién lo frena. Siempre termina en ROLLBACK."""
    db = get_db()
    est = db.execute("SELECT MIN(id_estudiante) FROM Estudiantes").fetchone()[0]
    antes = db.execute("SELECT COUNT(*) FROM Rendimiento_Semestral").fetchone()[0]
    db.execute("BEGIN")
    try:
        db.execute(
            """INSERT INTO Rendimiento_Semestral
               (id_estudiante, semestre, creditadas, matriculadas, evaluadas, aprobadas, nota_promedio, sin_evaluacion)
               VALUES (?, 12, 0, 4, 4, 10, 15.0, 0)""",
            (est,),
        )
        db.execute("ROLLBACK")
        return jsonify(ok=False, message="La base NO rechazó el dato (esto no debería pasar)"), 500
    except sqlite3.IntegrityError as exc:
        db.execute("ROLLBACK")
        mensaje, regla = explicar_rechazo(exc)
        detalle = str(exc)
    despues = db.execute("SELECT COUNT(*) FROM Rendimiento_Semestral").fetchone()[0]
    return jsonify(
        ok=False, capa="base de datos", message=mensaje, regla=regla, detalle=detalle,
        intento="10 unidades aprobadas de 4 matriculadas", filas_antes=antes, filas_despues=despues,
    ), 409


if __name__ == "__main__":
    asegurar_base()
    app.run(host="127.0.0.1", port=5000, debug=False)
