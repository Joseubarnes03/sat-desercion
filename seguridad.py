"""Cuentas y contraseñas de SAT-Deserción.

La contraseña nunca se guarda tal como se escribe. Se guarda un hash con sal aleatoria
(werkzeug: scrypt). Del hash no se puede volver a la contraseña; para comprobarla, se calcula el
hash de lo que la persona escribe con la misma sal y se comparan.
"""
import re
import secrets
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

CORREO_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")
ROLES = ("coordinador", "consejero")


def validar_clave(clave):
    """Devuelve un mensaje de error, o None si la contraseña sirve."""
    if not isinstance(clave, str) or len(clave) < 8:
        return "La contraseña debe tener al menos 8 caracteres"
    if len(clave) > 128:
        return "La contraseña no puede pasar de 128 caracteres"
    if not (re.search(r"[A-Za-z]", clave) and re.search(r"\d", clave)):
        return "La contraseña debe combinar letras y números"
    return None


def hashear(clave):
    return generate_password_hash(clave)


def verificar(hash_guardado, clave):
    return check_password_hash(hash_guardado, clave)


# Hash de relleno: si el correo no existe, igual se calcula un hash. Así la respuesta tarda lo mismo
# y no se puede descubrir qué correos tienen cuenta midiendo el tiempo.
HASH_RELLENO = generate_password_hash(secrets.token_hex(16))


def crear_usuario(db, correo, nombre, clave, rol):
    """Crea la cuenta. Lanza ValueError con un mensaje claro si algo no sirve."""
    correo = (correo or "").strip().lower()
    nombre = (nombre or "").strip()
    if not CORREO_RE.match(correo) or len(correo) > 120:
        raise ValueError("El correo no tiene un formato válido")
    if not 1 <= len(nombre) <= 80:
        raise ValueError("El nombre debe tener entre 1 y 80 caracteres")
    if rol not in ROLES:
        raise ValueError("El rol debe ser coordinador o consejero")
    error = validar_clave(clave)
    if error:
        raise ValueError(error)
    try:
        cur = db.execute(
            "INSERT INTO Usuarios (correo, nombre, rol, hash_clave) VALUES (?, ?, ?, ?)",
            (correo, nombre, rol, hashear(clave)),
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc):
            raise ValueError("Ya existe una cuenta con ese correo") from None
        raise ValueError("La base rechazó los datos de la cuenta") from None
    return cur.lastrowid
