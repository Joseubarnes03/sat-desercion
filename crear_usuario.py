"""Crea una cuenta desde la terminal. La contraseña se pide oculta: no queda en el historial ni en el código.

    python crear_usuario.py --rol coordinador --correo ana@correo.com --nombre "Ana Pérez"
"""
import argparse
import getpass
import sys

import cargar_datos
import seguridad

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--rol", choices=seguridad.ROLES, default="coordinador")
ap.add_argument("--correo", required=True)
ap.add_argument("--nombre", required=True)
a = ap.parse_args()

clave = getpass.getpass("Contraseña (mínimo 8, con letras y números): ")
if clave != getpass.getpass("Repite la contraseña: "):
    sys.exit("Las contraseñas no coinciden")

conn = cargar_datos.conectar()
cargar_datos.crear_esquema(conn)
try:
    seguridad.crear_usuario(conn, a.correo, a.nombre, clave, a.rol)
except ValueError as e:
    sys.exit(f"No se creó la cuenta: {e}")
print(f"Cuenta creada: {a.correo} ({a.rol})")
