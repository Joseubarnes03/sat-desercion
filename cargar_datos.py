"""Proceso de datos de SAT-Deserción: archivo original -> limpiar -> validar -> guardar.

Se puede correr las veces que se quiera sin crear registros dobles. Cada estudiante se identifica
por su codigo_estudiante (columna del archivo). Al volver a cargar:
  - fila igual a la que ya está guardada      -> no se toca nada
  - mismo código con algún dato corregido     -> se ACTUALIZA ese estudiante (no se crea otro)
  - código nuevo                              -> se inserta

Cada fila se guarda dentro de un SAVEPOINT: si la base rechaza algo de esa fila, se deshace solo esa
fila y el resto del archivo sigue. Todo el cargue ocurre en una sola transacción.

Uso:
    python cargar_datos.py                       # carga data/estudiantes.csv
    python cargar_datos.py --archivo otro.csv    # otro archivo con las mismas columnas
"""
import argparse
import csv
import hashlib
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parent
DB_POR_DEFECTO = Path(os.environ.get("SAT_DB", BASE / "sat_desercion.db"))
CSV_POR_DEFECTO = Path(os.environ.get("SAT_CSV", BASE / "data" / "estudiantes.csv"))
CURSOS_POR_DEFECTO = Path(os.environ.get("SAT_CURSOS", BASE / "data" / "cursos_nombres.csv"))

CODIGO_RE = re.compile(r"^E\d{4,}$")
BINARIAS = {
    "Daytime/evening attendance": "jornada", "Displaced": "desplazado",
    "Educational special needs": "necesidades_especiales", "Debtor": "deudor",
    "Tuition fees up to date": "matricula_al_dia", "Gender": "genero",
    "Scholarship holder": "becado", "International": "internacional",
}
ENTEROS = ["Marital status", "Application mode", "Application order", "Course", "Previous qualification",
           "Nacionality", "Age at enrollment"]
ENTEROS_OPCIONALES = ["Mother's qualification", "Father's qualification", "Mother's occupation", "Father's occupation"]
REALES = ["Unemployment rate", "Inflation rate", "GDP"]
RESULTADOS = {"Dropout", "Enrolled", "Graduate"}
SEMESTRES = {1: "1st", 2: "2nd"}

COLUMNAS_ESTUDIANTE = (
    "codigo_estudiante, estado_civil, modo_admision, orden_admision, id_curso, jornada, calificacion_previa, "
    "nacionalidad, calif_madre, calif_padre, ocupacion_madre, ocupacion_padre, desplazado, necesidades_especiales, "
    "deudor, matricula_al_dia, genero, becado, edad_matricula, internacional, tasa_desempleo, tasa_inflacion, pib, "
    "resultado, huella"
)


def conectar(db_path=DB_POR_DEFECTO):
    # isolation_level=None: nosotros controlamos BEGIN / COMMIT / ROLLBACK a mano.
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def crear_esquema(conn):
    conn.executescript((BASE / "schema.sql").read_text(encoding="utf-8"))


def huella(fila):
    """Resumen SHA-1 del contenido de la fila: sirve solo para saber si cambió algún dato."""
    contenido = "|".join((v or "").strip() for v in fila.values())
    return hashlib.sha1(contenido.encode("utf-8")).hexdigest()


def a_entero(valor):
    f = float(valor)
    if f != int(f):
        raise ValueError("no es entero")
    return int(f)


def limpiar_y_validar(fila, nombres_curso):
    """Devuelve (registro_limpio, None) o (None, causa_de_rechazo)."""
    fila = {(k or "").strip(): (v or "").strip() for k, v in fila.items()}
    codigo = fila.get("codigo_estudiante", "")
    if not codigo:
        return None, "dato obligatorio vacío"
    if not CODIGO_RE.match(codigo):
        return None, "código de estudiante con formato inválido"
    try:
        r = {"codigo": codigo}
        for col in ENTEROS:
            if fila.get(col, "") == "":
                return None, "dato obligatorio vacío"
            r[col] = a_entero(fila[col])
        for col in ENTEROS_OPCIONALES:
            r[col] = a_entero(fila[col]) if fila.get(col, "") != "" else None
        for col in BINARIAS:
            r[col] = a_entero(fila[col]) if fila.get(col, "") != "" else None
        for col in REALES:
            r[col] = float(fila[col]) if fila.get(col, "") != "" else None
        r["Target"] = fila.get("Target", "")
        sem = {}
        for n, pref in SEMESTRES.items():
            base = f"Curricular units {pref} sem"
            for etiqueta in ("credited", "enrolled", "evaluations", "approved", "without evaluations"):
                if fila.get(f"{base} ({etiqueta})", "") == "":
                    return None, "dato obligatorio vacío"
            nota = fila.get(f"{base} (grade)", "")
            sem[n] = (
                a_entero(fila[f"{base} (credited)"]), a_entero(fila[f"{base} (enrolled)"]),
                a_entero(fila[f"{base} (evaluations)"]), a_entero(fila[f"{base} (approved)"]),
                float(nota) if nota != "" else None, a_entero(fila[f"{base} (without evaluations)"]),
            )
    except (ValueError, KeyError):
        return None, "formato numérico inválido"

    if r["Course"] not in nombres_curso:
        return None, "curso sin nombre de programa"
    if r["Target"] not in RESULTADOS:
        return None, "resultado fuera de Dropout/Enrolled/Graduate"
    if any(r[c] not in (0, 1) for c in BINARIAS if r[c] is not None):
        return None, "variable binaria fuera de 0/1"
    if not 15 <= r["Age at enrollment"] <= 100:
        return None, "edad de matrícula fuera de 15–100"
    for cre, mat, eva, apr, nota, sin in sem.values():
        if min(cre, mat, eva, apr, sin) < 0:
            return None, "unidades negativas"
        if apr > mat:
            return None, "aprobadas mayor que matriculadas"
        if nota is not None and not 0 <= nota <= 20:
            return None, "nota promedio fuera de 0–20"
    r["_semestres"] = sem
    return r, None


def cargar_catalogo_cursos(conn, ruta):
    """Carga Cursos con su nombre. Un curso sin nombre no entra."""
    nombres = {}
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            nombre = (fila["nombre"] or "").strip()
            if nombre:
                nombres[int(fila["codigo_origen"])] = nombre
    for codigo, nombre in nombres.items():
        conn.execute(
            "INSERT INTO Cursos (codigo_origen, nombre) VALUES (?, ?) "
            "ON CONFLICT(codigo_origen) DO UPDATE SET nombre = excluded.nombre",
            (codigo, nombre),
        )
    return nombres


def _valores_estudiante(r, id_curso, h):
    return (
        r["codigo"], r["Marital status"], r["Application mode"], r["Application order"], id_curso,
        r["Daytime/evening attendance"], r["Previous qualification"], r["Nacionality"],
        r["Mother's qualification"], r["Father's qualification"], r["Mother's occupation"], r["Father's occupation"],
        r["Displaced"], r["Educational special needs"], r["Debtor"], r["Tuition fees up to date"], r["Gender"],
        r["Scholarship holder"], r["Age at enrollment"], r["International"], r["Unemployment rate"],
        r["Inflation rate"], r["GDP"], r["Target"], h,
    )


def _guardar_fila(conn, r, h, id_curso):
    """Guarda un estudiante y sus semestres. Devuelve contadores de lo que realmente cambió."""
    c = Counter()
    valores = _valores_estudiante(r, id_curso, h)
    actual = conn.execute("SELECT id_estudiante, huella FROM Estudiantes WHERE codigo_estudiante = ?", (r["codigo"],)).fetchone()
    if actual is None:
        marcas = ",".join("?" * len(valores))
        conn.execute(f"INSERT INTO Estudiantes ({COLUMNAS_ESTUDIANTE}) VALUES ({marcas})", valores)
        c["estudiantes_nuevos"] += 1
    elif actual["huella"] != h:
        sets = ", ".join(f"{col.strip()} = ?" for col in COLUMNAS_ESTUDIANTE.split(","))
        conn.execute(f"UPDATE Estudiantes SET {sets} WHERE id_estudiante = ?", valores + (actual["id_estudiante"],))
        c["estudiantes_actualizados"] += 1
    else:
        c["estudiantes_sin_cambios"] += 1
    id_est = conn.execute("SELECT id_estudiante FROM Estudiantes WHERE codigo_estudiante = ?", (r["codigo"],)).fetchone()[0]
    for n, datos in r["_semestres"].items():
        previo = conn.execute(
            "SELECT creditadas, matriculadas, evaluadas, aprobadas, nota_promedio, sin_evaluacion "
            "FROM Rendimiento_Semestral WHERE id_estudiante = ? AND semestre = ?", (id_est, n)).fetchone()
        if previo is None:
            conn.execute(
                """INSERT INTO Rendimiento_Semestral
                   (id_estudiante, semestre, creditadas, matriculadas, evaluadas, aprobadas, nota_promedio, sin_evaluacion)
                   VALUES (?,?,?,?,?,?,?,?)""", (id_est, n) + datos)
            c["rendimientos_nuevos"] += 1
        elif tuple(previo) != datos:
            conn.execute(
                """UPDATE Rendimiento_Semestral SET creditadas=?, matriculadas=?, evaluadas=?, aprobadas=?,
                   nota_promedio=?, sin_evaluacion=? WHERE id_estudiante=? AND semestre=?""", datos + (id_est, n))
            c["rendimientos_actualizados"] += 1
    return c


def cargar(archivo=CSV_POR_DEFECTO, cursos=CURSOS_POR_DEFECTO, db_path=DB_POR_DEFECTO, verbose=True):
    conn = conectar(db_path)
    crear_esquema(conn)
    total = Counter(entran=0, aceptadas=0, rechazadas=0, estudiantes_nuevos=0, estudiantes_actualizados=0,
                    estudiantes_sin_cambios=0, rendimientos_nuevos=0, rendimientos_actualizados=0)
    causas = Counter()

    conn.execute("BEGIN")  # todo el cargue es una sola transacción
    try:
        nombres_curso = cargar_catalogo_cursos(conn, cursos)
        id_curso = {r["codigo_origen"]: r["id_curso"] for r in conn.execute("SELECT id_curso, codigo_origen FROM Cursos")}
        vistos = set()
        with open(archivo, newline="", encoding="utf-8-sig") as f:
            for fila in csv.DictReader(f):
                total["entran"] += 1
                r, causa = limpiar_y_validar(fila, nombres_curso)
                if causa is None and r["codigo"] in vistos:
                    causa = "código repetido dentro del archivo"
                if causa:
                    total["rechazadas"] += 1
                    causas[causa] += 1
                    continue
                vistos.add(r["codigo"])
                conn.execute("SAVEPOINT fila")
                try:
                    c = _guardar_fila(conn, r, huella(fila), id_curso[r["Course"]])
                    conn.execute("RELEASE fila")
                except sqlite3.IntegrityError as exc:  # segunda línea de defensa: la base también valida
                    conn.execute("ROLLBACK TO fila")
                    conn.execute("RELEASE fila")
                    total["rechazadas"] += 1
                    causas[f"la base lo rechazó: {exc}"] += 1
                    continue
                total["aceptadas"] += 1
                total.update(c)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    en_base = {
        "estudiantes_en_base": conn.execute("SELECT COUNT(*) FROM Estudiantes").fetchone()[0],
        "rendimientos_en_base": conn.execute("SELECT COUNT(*) FROM Rendimiento_Semestral").fetchone()[0],
    }
    conn.close()
    if verbose:
        print(f"Archivo: {Path(archivo).name}")
        print(f"  Entran:      {total['entran']}")
        print(f"  Se aceptan:  {total['aceptadas']}")
        print(f"  Se rechazan: {total['rechazadas']}")
        for causa, n in causas.most_common():
            print(f"      - {causa}: {n}")
        print(f"  Estudiantes: {total['estudiantes_nuevos']} nuevos, {total['estudiantes_actualizados']} actualizados, "
              f"{total['estudiantes_sin_cambios']} sin cambios")
        print(f"  Rendimientos: {total['rendimientos_nuevos']} nuevos, {total['rendimientos_actualizados']} actualizados")
        print(f"  En la base ahora: {en_base['estudiantes_en_base']} estudiantes, {en_base['rendimientos_en_base']} rendimientos")
    return dict(total), dict(causas), en_base


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivo", default=str(CSV_POR_DEFECTO))
    ap.add_argument("--cursos", default=str(CURSOS_POR_DEFECTO))
    ap.add_argument("--db", default=str(DB_POR_DEFECTO))
    a = ap.parse_args()
    cargar(a.archivo, a.cursos, a.db)
