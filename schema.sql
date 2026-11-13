-- Esquema de SAT-Deserción (Momento 3).
-- Cambios respecto al Momento 2:
--   Usuarios                       -> cuentas con rol y contraseña guardada como hash (nunca en claro)
--   Estudiantes.codigo_estudiante  -> identificador real: corregir un dato ya no crea un estudiante duplicado
--   Rendimiento_Semestral.registrado_por y Historial_Matricula.cambiado_por -> quién hizo cada cambio
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Usuarios (
    id_usuario   INTEGER PRIMARY KEY AUTOINCREMENT,
    correo       TEXT NOT NULL UNIQUE COLLATE NOCASE
                 CONSTRAINT ck_correo_formato CHECK (correo LIKE '%_@_%._%' AND length(correo) <= 120),
    nombre       TEXT NOT NULL CONSTRAINT ck_usuario_nombre CHECK (length(trim(nombre)) BETWEEN 1 AND 80),
    rol          TEXT NOT NULL CONSTRAINT ck_rol_valido CHECK (rol IN ('coordinador','consejero')),
    hash_clave   TEXT NOT NULL,
    creado_en    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS Cursos (
    id_curso        INTEGER PRIMARY KEY,
    codigo_origen   INTEGER NOT NULL UNIQUE,
    nombre          TEXT NOT NULL CONSTRAINT ck_curso_nombre CHECK (length(trim(nombre)) > 0)
);

CREATE TABLE IF NOT EXISTS Estudiantes (
    id_estudiante           INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_estudiante       TEXT NOT NULL UNIQUE CONSTRAINT ck_codigo_formato CHECK (codigo_estudiante GLOB 'E[0-9][0-9][0-9][0-9]*'),
    estado_civil            INTEGER NOT NULL,
    modo_admision           INTEGER NOT NULL,
    orden_admision          INTEGER NOT NULL CHECK (orden_admision >= 0),
    id_curso                INTEGER NOT NULL REFERENCES Cursos(id_curso),
    jornada                 INTEGER NOT NULL CHECK (jornada IN (0,1)),
    calificacion_previa     INTEGER NOT NULL,
    nacionalidad            INTEGER NOT NULL,
    calif_madre             INTEGER,
    calif_padre             INTEGER,
    ocupacion_madre         INTEGER,
    ocupacion_padre         INTEGER,
    desplazado              INTEGER CHECK (desplazado IN (0,1)),
    necesidades_especiales  INTEGER CHECK (necesidades_especiales IN (0,1)),
    deudor                  INTEGER CHECK (deudor IN (0,1)),
    matricula_al_dia        INTEGER CONSTRAINT ck_matricula_binaria CHECK (matricula_al_dia IN (0,1)),
    genero                  INTEGER CHECK (genero IN (0,1)),
    becado                  INTEGER CHECK (becado IN (0,1)),
    edad_matricula          INTEGER NOT NULL CHECK (edad_matricula BETWEEN 15 AND 100),
    internacional           INTEGER CHECK (internacional IN (0,1)),
    tasa_desempleo          REAL,
    tasa_inflacion          REAL,
    pib                     REAL,
    resultado               TEXT NOT NULL CONSTRAINT ck_resultado_valido CHECK (resultado IN ('Dropout','Enrolled','Graduate')),
    huella                  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Rendimiento_Semestral (
    id_rendimiento    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_estudiante     INTEGER NOT NULL REFERENCES Estudiantes(id_estudiante) ON DELETE CASCADE,
    semestre          INTEGER NOT NULL CONSTRAINT ck_semestre_rango CHECK (semestre BETWEEN 1 AND 12),
    creditadas        INTEGER NOT NULL CHECK (creditadas >= 0),
    matriculadas      INTEGER NOT NULL CHECK (matriculadas >= 0),
    evaluadas         INTEGER NOT NULL CHECK (evaluadas >= 0),
    aprobadas         INTEGER NOT NULL CONSTRAINT ck_aprobadas_le_matriculadas CHECK (aprobadas >= 0 AND aprobadas <= matriculadas),
    nota_promedio     REAL CONSTRAINT ck_nota_rango CHECK (nota_promedio BETWEEN 0 AND 20),
    sin_evaluacion    INTEGER NOT NULL CHECK (sin_evaluacion >= 0),
    registrado_por    INTEGER REFERENCES Usuarios(id_usuario),
    UNIQUE (id_estudiante, semestre)
);

CREATE TABLE IF NOT EXISTS Historial_Matricula (
    id_historial      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_estudiante     INTEGER NOT NULL REFERENCES Estudiantes(id_estudiante) ON DELETE CASCADE,
    estado_anterior   INTEGER NOT NULL CHECK (estado_anterior IN (0,1)),
    estado_nuevo      INTEGER NOT NULL CHECK (estado_nuevo IN (0,1)),
    cambiado_por      INTEGER NOT NULL REFERENCES Usuarios(id_usuario),
    cambiado_en       TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT ck_cambio_real CHECK (estado_anterior <> estado_nuevo)
);

CREATE INDEX IF NOT EXISTS idx_estudiantes_curso ON Estudiantes(id_curso);
