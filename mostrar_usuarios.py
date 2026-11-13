"""Muestra cómo quedan guardadas las cuentas: la contraseña aparece como hash, no como texto."""
import cargar_datos

conn = cargar_datos.conectar()
filas = conn.execute("SELECT correo, nombre, rol, hash_clave FROM Usuarios ORDER BY id_usuario").fetchall()
if not filas:
    print("Todavía no hay cuentas. Crea una con crear_usuario.py o desde /registro.")
for f in filas:
    print(f"correo:     {f['correo']}")
    print(f"nombre:     {f['nombre']}")
    print(f"rol:        {f['rol']}")
    print(f"hash_clave: {f['hash_clave']}")
    print()
