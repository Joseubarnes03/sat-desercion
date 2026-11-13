"""Genera el PDF de entrega del Momento 3 (capturas + texto).
Uso:  REPO_URL=https://github.com/usuario/sat-desercion python docs/construir_pdf.py
Requiere: pip install playwright && playwright install chromium
"""
import html, os, base64, pathlib
from playwright.sync_api import sync_playwright

RAIZ = pathlib.Path(__file__).resolve().parent.parent
REPO = os.environ.get("REPO_URL", "(pegar aquí el enlace del repositorio)")

def img(n, ancho="100%"):
    b = base64.b64encode((RAIZ / "capturas" / n).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b}" style="width:{ancho}">'
def txt(n):
    return "<pre>" + html.escape((RAIZ / "ev" / n).read_text(encoding="utf-8")) + "</pre>"
def fig(n, pie, ancho="100%"):
    return f'<figure>{img(n, ancho)}<figcaption>{pie}</figcaption></figure>'

CSS = """
@page{size:A4;margin:16mm 15mm}
body{font-family:'Inter','Segoe UI',Arial,sans-serif;font-size:10.5pt;line-height:1.5;color:#1d2330}
h1{font-family:Georgia,serif;font-size:24pt;margin:0 0 4px}
h2{font-family:Georgia,serif;font-size:16pt;margin:0 0 6px;border-bottom:2px solid #1d2330;padding-bottom:4px}
h3{font-size:11pt;margin:14px 0 4px}
section{break-before:page}
section.portada{break-before:auto}
.meta{color:#566;margin:2px 0}
figure{margin:8px 0;break-inside:avoid}
figcaption{font-size:9pt;color:#566;margin-top:3px}
img{border:1px solid #cfcbbf;max-height:215mm;object-fit:contain}
pre{break-inside:avoid;background:#161b22;color:#e6edf3;padding:10px 12px;font-size:7.8pt;line-height:1.35;white-space:pre-wrap;word-break:break-all;border-radius:3px}
table{border-collapse:collapse;width:100%;font-size:9.5pt;margin:8px 0}
th,td{border:1px solid #cfcbbf;padding:4px 8px;text-align:left}
th{background:#eeebe3}
.caja{border-left:4px solid #1d2330;background:#f4f2ec;padding:8px 12px;margin:10px 0}
.dos{display:grid;grid-template-columns:1fr 1fr;gap:10px}
h3{break-after:avoid}
a{color:#1d2330}
"""

cuerpo = f"""
<section class="portada">
<p class="meta">Universidad Cooperativa de Colombia · Optativa II · Grupo 7792 · Momento 3</p>
<h1>SAT-Deserción: entrega final</h1>
<p class="meta">Sistema de Alerta Temprana de Deserción Estudiantil</p>
<p><b>Equipo:</b> Jose David Ubarnes Barrios · Valentina Sáez Tordecilla · Valentina Genes López</p>
<p><b>Repositorio de la aplicación:</b> <a href="{html.escape(REPO)}">{html.escape(REPO)}</a></p>
<div class="caja"><b>Qué corrigieron respecto al Momento 2, y por qué</b>
<ol>
<li><b>Identidad del estudiante.</b> En el Momento 2 un estudiante se reconocía por una huella (SHA-1 de todos sus campos). Al corregir un solo dato —por ejemplo, la edad— la huella cambiaba y el sistema creaba <i>otro</i> estudiante: probamos el caso y la base pasó de 4.424 a 4.425. Ahora cada estudiante tiene un <b>código único (E0001…)</b>; si el código ya existe, el cargue <b>actualiza</b> (solo si algo cambió) y si no existe, <b>inserta</b>. La huella quedó solo para detectar cambios.</li>
<li><b>Seguridad.</b> El Momento 2 no tenía cuentas. Ahora hay inicio de sesión con roles (coordinador y consejero), contraseñas guardadas con hash scrypt y sal aleatoria, token CSRF en cada envío, política CSP sin scripts ni estilos en línea y consultas siempre parametrizadas.</li>
<li><b>Trazabilidad.</b> Cada cambio de matrícula y cada rendimiento guardan <i>quién</i> lo hizo (<code>cambiado_por</code>, <code>registrado_por</code>), y solo el coordinador puede cambiar matrículas.</li>
<li><b>La alerta cierra el ciclo.</b> Antes la aplicación solo guardaba y mostraba datos. Ahora, al registrar un rendimiento, responde si ese estudiante queda en alerta, y hay una lista de alertas ordenada por urgencia.</li>
<li><b>Dos capas de validación con mensajes claros.</b> La aplicación revisa lo obligatorio y el formato; la base (CHECK, UNIQUE, FOREIGN KEY con nombre) decide si el dato tiene sentido. Cada rechazo dice qué capa lo frenó y qué regla.</li>
</ol></div>
<p class="meta">Las capturas de este documento se tomaron de la aplicación en ejecución, con datos de prueba y cuentas de demostración. Las salidas de terminal son texto real de los programas del repositorio.</p>
</section>

<section>
<h2>Paso 1 · La idea</h2>
<p><b>Problema:</b> muchos estudiantes abandonan sus estudios y la universidad suele enterarse cuando ya se fueron.</p>
<p><b>Usuario:</b> el consejero o coordinador académico que acompaña a los estudiantes.</p>
<p><b>Necesidad:</b> ver a tiempo, y con una razón comprensible, qué estudiantes matriculados van mal en sus unidades, para llamarlos antes de que deserten. La aplicación registra el rendimiento por semestre, avisa de inmediato si el estudiante queda en riesgo y lista los casos más urgentes. Los datos son 4.424 estudiantes y 8.848 registros semestrales.</p>
{fig("05_app_inicio.png","Pantalla principal tras iniciar sesión: registro de rendimiento, alertas, resultado por programa, matrícula y prueba de rechazo.","78%")}
</section>

<section>
<h2>Paso 2 · La app funcionando</h2>
<p>Recorrido completo, del dato a la respuesta: el consejero escribe el estudiante E0017 (semestre 7, 6 unidades matriculadas, 2 aprobadas, nota 9,5). La aplicación consulta quién es, guarda el dato y responde en la misma pantalla que el estudiante queda en alerta; el registro aparece en la tabla de últimos guardados y el estudiante en la lista de alertas.</p>
{fig("06_rendimiento_alerta.png","Dato guardado y respuesta inmediata: «En alerta de riesgo: 2 de 6 unidades aprobadas (33 %) en el semestre 7».","70%")}
<p><b>Lo corregido del Momento 2</b> (ver portada): identidad por código, cuentas y roles, alerta en la respuesta y mensajes por capa. En la pantalla se nota en el nombre de quien registra, el código «E0017» y la respuesta de alerta.</p>
</section>

<section>
<h2>Paso 3 · Los datos</h2>
<p>El cargue limpia y valida cada fila (obligatorios, rangos, resultado permitido, programa con nombre), rechaza las malas diciendo la causa y <b>actualiza o inserta</b> según el código del estudiante. Cada fila va en su propio punto de guardado, así una fila mala no daña las demás.</p>
{txt("cargue.txt")}
<p>Lectura: el primer cargue inserta 4.424 estudiantes. El <b>mismo archivo</b> otra vez da 0 nuevos, 0 actualizados y 4.424 sin cambios: no se duplica nada. El tercero trae 9 filas: rechaza 5 con su causa, inserta 2, <b>corrige 1</b> existente y deja 1 sin cambios.</p>
</section>

<section>
<h2>Paso 4 · Seguridad</h2>
<h3>Código que un formulario no puede inyectar</h3>
<p>Se creó una cuenta con el nombre <code>&lt;script&gt;alert('hack')&lt;/script&gt;</code>. La aplicación lo muestra como texto, no lo ejecuta: la plantilla escapa la salida y además la política CSP prohíbe scripts en línea. Las consultas siempre usan parámetros, de modo que texto como <code>' OR '1'='1' --</code> en el login no cambia la consulta.</p>
<div class="dos" style="grid-template-columns:1fr 1fr 1fr">{fig("04_xss_escapado.png","El nombre con &lt;script&gt; aparece como texto.")}{fig("03_login_sqli.png","Intento de inyección SQL en el login: no entra.")}{fig("02_login_error.png","Clave incorrecta: mensaje genérico, igual que con un correo inexistente.")}</div>
<h3>Contraseñas guardadas de forma ilegible</h3>
<p>La base guarda un hash scrypt con sal aleatoria, nunca la contraseña. Las dos cuentas de demostración usan la misma clave y sus hashes son distintos.</p>
{txt("hash.txt")}
<h3>Otras medidas</h3>
<p>Mismo mensaje de error si el correo no existe o la clave falla; bloqueo tras 5 intentos fallidos en 5 minutos; token CSRF en cada POST; cookie HttpOnly y SameSite; sesión de 2 horas; cabeceras de seguridad; límite de tamaño de petición; la clave de sesión sale de una variable de entorno, no del código.</p>
</section>

<section>
<h2>Paso 5 · Inteligencia</h2>
<p><b>Tarea repetitiva elegida:</b> revisar a mano, cada semestre, quién de los matriculados va mal.</p>
<p><b>Decisión:</b> reglas deterministas. Alerta cuando un estudiante <i>matriculado</i> aprobó menos del 50 % de las unidades que matriculó en su último semestre registrado (el umbral se puede cambiar a 40 % o 60 %).</p>
<h3>Justificación con datos</h3>
<p>Comparamos la regla con modelos usando los mismos 4.424 estudiantes, objetivo «desertó» (32,1 %). Con las variables que nuestra aplicación realmente registra (unidades y nota por semestre), la regla queda a la par de los modelos:</p>
<table><tr><th>Método</th><th>Precisión</th><th>Cobertura</th><th>F1</th></tr>
<tr><td>Regla: aprobación del 2.º semestre &lt; 50 %</td><td>0,847</td><td>0,616</td><td>0,714</td></tr>
<tr><td>Regresión logística (validación cruzada 5 pliegues)</td><td>0,851</td><td>0,647</td><td>0,735</td></tr>
<tr><td>Árbol de decisión, profundidad 4 (5 pliegues)</td><td>0,836</td><td>0,616</td><td>0,710</td></tr></table>
<p><b>Por qué reglas:</b> (1) la ganancia de un modelo es de ~2 puntos de F1, dentro de lo que esperaríamos del azar de la partición; (2) el consejero necesita una razón que pueda decir a un estudiante («aprobaste 2 de 6»), y la regla se explica sola; (3) con pocos datos de entrada, un modelo no tiene de dónde sacar más señal; (4) los datos de la aplicación crecen despacio y un modelo habría que reentrenarlo y vigilarlo.</p>
<p><b>Por qué se descartó la IA:</b> no mejora lo bastante, no se puede explicar con la misma claridad y añade mantenimiento. Con las 35 variables del conjunto (edad, becas, pagos…) los modelos sí suben (F1 ≈ 0,76–0,79), pero la aplicación no captura esas variables todavía; sería la razón para reconsiderarlo más adelante.</p>
<p><b>Límites:</b> la regla deja pasar a casi 4 de cada 10 desertores (cobertura 0,62); mide al estudiante que ya reprobó, no al que está por hacerlo; la alerta propone y una persona decide.</p>
{fig("07_alertas.png","Lista de alertas: 150 de 794 matriculados bajo el 50 %; 28 sin unidades matriculadas quedan fuera porque no se puede calcular.","62%")}
</section>

<section>
<h2>Paso 6 · Un dato malo</h2>
<p>Se probaron los tres tipos de dato malo. La aplicación frena lo incompleto y lo mal escrito; la base frena lo que no tiene sentido. En ningún caso se guarda: la tabla no cambia (comprobado en las pruebas automáticas: 57 de 57 pasan).</p>
<div class="dos">
{fig("09_malo_incompleto.png","<b>Incompleto</b>: faltan datos obligatorios (capa aplicación).")}
{fig("10_malo_formato.png","<b>Formato</b>: «abc» en unidades aprobadas (capa aplicación).")}
{fig("11_malo_aprobadas_mayor.png","<b>Fuera de lógica</b>: 10 aprobadas de 4 matriculadas (capa base de datos, CHECK).")}
{fig("12_malo_nota.png","<b>Fuera de rango</b>: nota 25, el rango es 0 a 20 (capa base de datos).")}
{fig("13_malo_repetido.png","<b>Repetido</b>: mismo estudiante y semestre (UNIQUE).")}
{fig("15_rechazo_base.png","Prueba directa a la base: no guarda nada, filas antes = después.")}
</div>
<h3>Resultado de las pruebas automáticas</h3>
{txt("pruebas_pdf.txt")}
</section>

<section>
<h2>Paso 7 · La decisión</h2>
<p><b>Decisión importante:</b> identificar a cada estudiante por un <b>código único</b> y cargar con <b>actualizar-o-insertar</b>, en lugar de reconocerlo por una huella de todos sus datos.</p>
<p><b>Por qué:</b> los datos de las personas se corrigen (una edad, un programa). Con la huella, cada corrección creaba un estudiante nuevo y dejaba al viejo huérfano: lo verificamos, 4.424 pasaba a 4.425 con un solo campo corregido. Con el código, la corrección actualiza a la misma persona, su historial de rendimiento se conserva y recargar el mismo archivo no cambia nada.</p>
<p><b>Alternativa descartada:</b> mantener la huella como identidad. Era más simple y atrapaba duplicados exactos, pero convertía toda corrección en un duplicado. La huella se conserva, pero solo para saber si una fila cambió.</p>
<p><b>Segunda decisión, de producto:</b> la alerta solo <i>propone</i>; una persona revisa antes de actuar, porque la regla deja pasar a algunos desertores y señala a otros que no desertarán.</p>
</section>
"""

html_doc = f"<!doctype html><html lang='es'><meta charset='utf-8'><style>{CSS}</style><body>{cuerpo}</body></html>"
salida = RAIZ / "docs" / "Momento3_7792_SAT-Desercion.pdf"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    pg.set_content(html_doc); pg.wait_for_timeout(500)
    pg.pdf(path=str(salida), format="A4", print_background=True)
    b.close()
print("PDF:", salida)
