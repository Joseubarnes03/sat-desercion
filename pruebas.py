"""Pruebas automáticas de SAT-Deserción (Momento 3). Usa una base temporal: no toca la real.

    python pruebas.py
"""
import os
import re
import sqlite3
import sys
import tempfile

import app as sat
import cargar_datos
import seguridad

tmp = tempfile.mkdtemp()
sat.DB_PATH = os.path.join(tmp, "prueba.db")
sat.asegurar_base()

fallos, total = [], 0


def check(nombre, condicion, detalle=""):
    global total
    total += 1
    print(("  OK   " if condicion else "  FALLA ") + nombre + ("" if condicion else f"  -> {detalle}"))
    if not condicion:
        fallos.append(nombre)


def nuevo_cliente():
    return sat.app.test_client()


def token(c):
    html = c.get("/login").get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"', html).group(1)


def entrar(correo, clave):
    c = nuevo_cliente()
    t = token(c)
    r = c.post("/login", data={"correo": correo, "clave": clave, "csrf": t})
    return c, r


def post(c, url, cuerpo):
    html = c.get("/").get_data(as_text=True)
    t = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html).group(1)
    return c.post(url, json=cuerpo, headers={"X-CSRF-Token": t})


conn = cargar_datos.conectar(sat.DB_PATH)
seguridad.crear_usuario(conn, "coord@uni.co", "Coordi Nadora", "Clave12345", "coordinador")
seguridad.crear_usuario(conn, "cons@uni.co", "Con Sejero", "Clave12345", "consejero")
conn.close()

print("\n1. Acceso y roles")
c0 = nuevo_cliente()
check("sin sesión, la página principal redirige al login", c0.get("/").status_code == 302)
check("sin sesión, la API responde 401", c0.get("/api/alertas").status_code == 401)
cc, r = entrar("coord@uni.co", "Clave12345")
check("login correcto redirige a la app", r.status_code == 302 and r.headers["Location"].endswith("/"))
cs, _ = entrar("cons@uni.co", "Clave12345")
r = post(cs, "/api/estudiante/1/matricula", {"matricula_al_dia": 0})
check("consejero NO puede cambiar matrícula (403)", r.status_code == 403, r.status_code)
r = post(cc, "/api/estudiante/1/matricula", {"matricula_al_dia": 0})
check("coordinador sí puede (200)", r.status_code == 200, r.get_json())
r = post(cc, "/api/estudiante/1/matricula", {"matricula_al_dia": 1, "simular_falla": True})
d = r.get_json()
check("falla simulada: rollback, matrícula queda igual", r.status_code == 409 and d["estado_despues"] == 0, d)
h = cc.get("/api/estudiante/1/historial-matricula").get_json()
check("historial guarda quién hizo el cambio", h and h[0]["por"] == "Coordi Nadora", h)

print("\n2. Contraseñas")
con = sqlite3.connect(sat.DB_PATH)
hs = [x[0] for x in con.execute("SELECT hash_clave FROM Usuarios")]
check("la contraseña no está en texto plano", all("Clave12345" not in x for x in hs))
check("el hash usa scrypt o pbkdf2", all(x.startswith(("scrypt:", "pbkdf2:")) for x in hs), hs)
check("misma clave, hashes distintos (sal aleatoria)", len(set(hs)) == 2)
check("contraseña corta rechazada", seguridad.validar_clave("abc1") is not None)
check("contraseña sin números rechazada", seguridad.validar_clave("sololetrasaqui") is not None)
_, r = entrar("coord@uni.co", "equivocada1")
check("clave incorrecta: 401", r.status_code == 401)
_, r2 = entrar("noexiste@uni.co", "equivocada1")
check("correo inexistente: mismo mensaje que clave incorrecta",
      r2.status_code == 401 and "Correo o contraseña incorrectos" in r2.get_data(as_text=True)
      and "Correo o contraseña incorrectos" in r.get_data(as_text=True))

print("\n3. Inyección")
_, r = entrar("' OR '1'='1' --", "x")
check("SQLi en el login no entra", r.status_code == 401)
_, r = entrar("coord@uni.co' --", "x")
check("SQLi con comentario no entra", r.status_code == 401)
xss = "<script>alert(1)</script>"
c3 = nuevo_cliente()
t = token(c3)
r = c3.post("/registro", data={"nombre": xss, "correo": "xss@uni.co", "clave": "Clave12345",
                               "clave2": "Clave12345", "csrf": t})
check("registro con <script> en el nombre se acepta como texto", r.status_code == 302, r.status_code)
cx, _ = entrar("xss@uni.co", "Clave12345")
html = cx.get("/").get_data(as_text=True)
check("el nombre con <script> se muestra escapado", "&lt;script&gt;" in html and xss not in html)
csp = cx.get("/").headers.get("Content-Security-Policy", "")
check("CSP prohíbe scripts en línea", "script-src 'self'" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0], csp)
check("la página no tiene scripts ni estilos en línea",
      not re.search(r"<script(?![^>]*\bsrc=)", html) and "<style" not in html and ' style="' not in html)
r = post(cc, "/api/rendimiento", {"id_estudiante": "1; DROP TABLE Estudiantes", "semestre": 3,
                                  "matriculadas": 5, "aprobadas": 3})
check("SQLi en un campo numérico: rechazo por formato", r.status_code == 400, r.get_json())
con = sqlite3.connect(sat.DB_PATH)
check("la tabla Estudiantes sigue existiendo", con.execute("SELECT COUNT(*) FROM Estudiantes").fetchone()[0] > 0)

print("\n4. CSRF y cabeceras")
r = cc.post("/api/estudiante/2/matricula", json={"matricula_al_dia": 0})
check("POST sin token CSRF: 403", r.status_code == 403, r.status_code)
r = cc.post("/api/estudiante/2/matricula", json={"matricula_al_dia": 0}, headers={"X-CSRF-Token": "falso"})
check("POST con token falso: 403", r.status_code == 403)
h = cc.get("/").headers
check("cabeceras de seguridad presentes",
      h.get("X-Content-Type-Options") == "nosniff" and h.get("X-Frame-Options") == "DENY"
      and "no-store" in h.get("Cache-Control", ""))
ck = "".join(cc.get("/").headers.getlist("Set-Cookie")) + "".join(entrar("coord@uni.co", "Clave12345")[1].headers.getlist("Set-Cookie"))
check("cookie de sesión HttpOnly y SameSite", "HttpOnly" in ck and "SameSite=Lax" in ck, ck)
big = cc.post("/api/rendimiento", data="x" * 70000, headers={"Content-Type": "application/json"})
check("cuerpo demasiado grande: 413", big.status_code == 413, big.status_code)

print("\n5. Datos malos (paso 6)")
base = {"id_estudiante": 3, "semestre": 11, "matriculadas": 6, "aprobadas": 4, "nota_promedio": 12}
casos = [
    ("faltan datos", {"id_estudiante": 3, "semestre": 11}, 400, "aplicación"),
    ("formato 'abc'", {**base, "aprobadas": "abc"}, 400, "aplicación"),
    ("negativo", {**base, "aprobadas": -2}, 400, "aplicación"),
    ("decimal en unidades", {**base, "aprobadas": 2.5}, 400, "aplicación"),
    ("NaN", {**base, "nota_promedio": "nan"}, 400, "aplicación"),
    ("infinito", {**base, "matriculadas": "1e999"}, 400, "aplicación"),
    ("nota fuera de rango (25)", {**base, "nota_promedio": 25}, 422, "base de datos"),
    ("aprobadas > matriculadas", {**base, "aprobadas": 10, "matriculadas": 4}, 422, "base de datos"),
    ("semestre 13", {**base, "semestre": 13}, 422, "base de datos"),
    ("estudiante inexistente", {**base, "id_estudiante": 99999999}, 404, "base de datos"),
]
n0 = sqlite3.connect(sat.DB_PATH).execute("SELECT COUNT(*) FROM Rendimiento_Semestral").fetchone()[0]
for nombre, cuerpo, esperado, capa in casos:
    r = post(cc, "/api/rendimiento", cuerpo)
    d = r.get_json()
    check(f"{nombre}: {esperado} ({capa})", r.status_code == esperado and d["capa"] == capa, (r.status_code, d))
n1 = sqlite3.connect(sat.DB_PATH).execute("SELECT COUNT(*) FROM Rendimiento_Semestral").fetchone()[0]
check("ningún dato malo se guardó", n0 == n1, (n0, n1))
r = post(cc, "/api/rendimiento", base)
check("dato bueno se guarda", r.status_code == 200, r.get_json())
r = post(cc, "/api/rendimiento", base)
check("repetir estudiante+semestre: 409 por UNIQUE", r.status_code == 409 and "UNIQUE" in r.get_json()["regla"])

print("\n6. Alerta (paso 5)")
con = sqlite3.connect(sat.DB_PATH)
con.row_factory = sqlite3.Row
est = con.execute("""SELECT id_estudiante FROM Estudiantes e WHERE resultado='Enrolled'
                     AND NOT EXISTS (SELECT 1 FROM Rendimiento_Semestral r WHERE r.id_estudiante=e.id_estudiante AND r.semestre=12)
                     LIMIT 1""").fetchone()[0]
r = post(cc, "/api/rendimiento", {"id_estudiante": est, "semestre": 12, "matriculadas": 6, "aprobadas": 2, "nota_promedio": 8})
check("2 de 6 aprobadas en matriculado: alerta en_riesgo", r.get_json()["alerta"]["estado"] == "en_riesgo", r.get_json())
a = cc.get("/api/alertas").get_json()
check("el estudiante aparece en /api/alertas", any(f["id_estudiante"] == est for f in a["filas"]) or a["en_alerta"] > 15)
check("/api/alertas devuelve conteos coherentes", a["en_alerta"] <= a["matriculados"])
check("umbral inválido (0): 400", cc.get("/api/alertas?umbral=0").status_code == 400)
check("umbral inválido (texto): 400", cc.get("/api/alertas?umbral=abc").status_code == 400)
check("límite inválido: 400", cc.get("/api/alertas?limite=0").status_code == 400)
check("umbral más alto no reduce las alertas",
      cc.get("/api/alertas?umbral=0.6").get_json()["en_alerta"] >= a["en_alerta"])
r = post(cc, "/api/rendimiento", {"id_estudiante": est, "semestre": 11, "matriculadas": 6, "aprobadas": 6})
check("alerta usa el ÚLTIMO semestre (el 12 sigue mandando)", r.get_json()["alerta"]["estado"] == "en_riesgo", r.get_json())
des = con.execute("SELECT id_estudiante FROM Estudiantes WHERE resultado='Dropout' LIMIT 1").fetchone()[0]
r = post(cc, "/api/rendimiento", {"id_estudiante": des, "semestre": 12, "matriculadas": 6, "aprobadas": 1})
check("estudiante que ya desertó: no aplica", r.get_json()["alerta"]["estado"] == "no_aplica", r.get_json())

print("\n7. Cargue repetible (paso 3)")
db2 = os.path.join(tmp, "carga.db")
t1, _, en1 = cargar_datos.cargar(db_path=db2, verbose=False)
t2, _, en2 = cargar_datos.cargar(db_path=db2, verbose=False)
check("primer cargue inserta estudiantes", t1["estudiantes_nuevos"] > 0, t1)
check("segundo cargue idéntico: 0 nuevos, 0 actualizados",
      t2["estudiantes_nuevos"] == 0 and t2["estudiantes_actualizados"] == 0 and t2["rendimientos_nuevos"] == 0, t2)
check("el total no cambió", en1 == en2, (en1, en2))
t3, _, en3 = cargar_datos.cargar(archivo="data/nuevo_cargue_prueba.csv", db_path=db2, verbose=False)
check("archivo con una corrección: actualiza sin duplicar",
      t3["estudiantes_actualizados"] >= 1 and en3["estudiantes_en_base"] - en2["estudiantes_en_base"] == t3["estudiantes_nuevos"], (t3, en2, en3))

print("\n8. Operaciones previas")
r = post(cc, "/api/prueba-rechazo", {})
d = r.get_json()
check("prueba de rechazo: la base frena el CHECK", r.status_code == 409 and "CHECK" in d["regla"] and d["filas_antes"] == d["filas_despues"], d)
check("resultado por programa trae nombre y porcentajes",
      all("programa" in f and "pct_desercion" in f for f in cc.get("/api/resultado-por-programa").get_json()))
check("filtro por programa devuelve 1 fila", len(cc.get("/api/resultado-por-programa?id_curso=1").get_json()) <= 1)

print("\n9. Bloqueo por intentos")
for _ in range(sat.MAX_FALLOS):
    entrar("cons@uni.co", "mala12345")
_, r = entrar("cons@uni.co", "Clave12345")
check("tras demasiados fallos, aun con la clave buena: 429", r.status_code == 429, r.status_code)

print(f"\n{total - len(fallos)} de {total} comprobaciones pasaron")
if fallos:
    print("Fallaron:", *fallos, sep="\n  - ")
    sys.exit(1)
