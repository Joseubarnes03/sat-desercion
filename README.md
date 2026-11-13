# SAT-Deserción · Momento 3

Sistema de Alerta Temprana de Deserción Estudiantil. Universidad Cooperativa de Colombia · Optativa II · Grupo 7792.
Equipo: Jose David Ubarnes Barrios, Valentina Sáez Tordecilla, Valentina Genes López.

Registra el rendimiento semestral de cada estudiante, avisa al instante si queda en riesgo, lista las alertas
más urgentes, muestra la deserción por programa y permite al coordinador cambiar la matrícula con historial.

## Cómo ejecutarlo

```bash
python -m venv .venv && source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
export SAT_SECRET="una-clave-larga-y-aleatoria"          # Windows: set SAT_SECRET=...  (si no, se genera una al arrancar)
python crear_usuario.py --rol coordinador --correo tu@correo.com --nombre "Tu Nombre"   # pide la contraseña oculta
python app.py                                          # abre http://127.0.0.1:5000
```

La primera vez, la aplicación crea la base `sat_desercion.db` y carga `data/estudiantes.csv` (4.424 estudiantes).
Las cuentas nuevas desde `/registro` son de **consejero**; los **coordinadores** se crean solo con `crear_usuario.py`.
Se puede cambiar la base con `SAT_DB`, el archivo con `SAT_CSV`.

## Datos

```bash
python cargar_datos.py                                    # carga o recarga: el mismo archivo no duplica nada
python cargar_datos.py --archivo data/nuevo_cargue_prueba.csv   # 9 filas: rechaza 5, inserta 2, corrige 1
```
Cada estudiante se identifica por su `codigo_estudiante` (E0001…): si existe, se actualiza solo lo que cambió; si no, se inserta.

## Seguridad

Contraseñas con hash scrypt y sal (`python mostrar_usuarios.py` lo muestra); consultas parametrizadas; salida escapada;
CSP sin scripts ni estilos en línea; token CSRF en cada POST; cookie HttpOnly + SameSite; bloqueo tras 5 intentos fallidos;
roles (coordinador / consejero); sin claves en el código.

## Pruebas

```bash
python pruebas.py       # 57 comprobaciones sobre una base temporal
```

## PDF de entrega

`docs/construir_pdf.py` (requiere Playwright) arma el PDF con las capturas. El repositorio no incluye la base de datos.
