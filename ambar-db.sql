CREATE DATABASE IF NOT EXISTS ambar_escolar
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ambar_escolar;

-- ==========================================
-- 1. Gestión de Acceso y Usuarios
-- ==========================================
CREATE TABLE roles (
    id_rol INT AUTO_INCREMENT PRIMARY KEY,
    nombre_rol VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    correo VARCHAR(150) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,          -- guardar solo hash (bcrypt/argon2)
    id_rol INT NOT NULL,
    estatus ENUM('Activo', 'Inactivo') NOT NULL DEFAULT 'Activo',
    FOREIGN KEY (id_rol) REFERENCES roles(id_rol)
);

CREATE TABLE personal_secretaria (
    id_secretaria INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL UNIQUE,
    nombres VARCHAR(50) NOT NULL,
    apellidos VARCHAR(100) NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ==========================================
-- 2. Catálogo Académico Base
-- ==========================================
CREATE TABLE materias (
    id_materia INT AUTO_INCREMENT PRIMARY KEY,
    nombre_materia VARCHAR(150) NOT NULL,
    semestre INT NOT NULL
);

-- ==========================================
-- 3. Gestión de Alumnos y Expedientes
-- ==========================================
CREATE TABLE alumnos (
    numero_control VARCHAR(20) PRIMARY KEY,
    id_usuario INT UNIQUE,                   -- acceso al sistema (opcional, 1:1)
    numero_ficha VARCHAR(20) NOT NULL UNIQUE,
    nombres VARCHAR(50) NOT NULL,
    apellido_paterno VARCHAR(50) NOT NULL,
    apellido_materno VARCHAR(50) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    genero VARCHAR(15),
    curp VARCHAR(18) NOT NULL UNIQUE,
    rfc VARCHAR(13),
    ine VARCHAR(20),
    nss VARCHAR(11),
    domicilio VARCHAR(255) NOT NULL,
    celular VARCHAR(15) NOT NULL,
    celular_emergencia VARCHAR(15) NOT NULL,
    correo_personal VARCHAR(100) NOT NULL,
    correo_emergencia VARCHAR(100),
    correo_institucional VARCHAR(100) UNIQUE,
    alergias TEXT,
    preparatoria_procedencia VARCHAR(100) NOT NULL,
    promedio_preparatoria DECIMAL(4,2) NOT NULL,
    turno ENUM('Matutino', 'Vespertino') NOT NULL,
    semestre_actual INT NOT NULL DEFAULT 1,
    estatus ENUM('Activo', 'Inactivo') NOT NULL DEFAULT 'Activo',
    motivo_baja VARCHAR(255),
    eliminado BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    CONSTRAINT chk_promedio_prepa CHECK (promedio_preparatoria BETWEEN 7 AND 10),
    CONSTRAINT chk_semestre_actual CHECK (semestre_actual >= 1),
    INDEX idx_alumnos_estatus (estatus)
);

CREATE TABLE historial_alumnos (
    id_historial INT AUTO_INCREMENT PRIMARY KEY,
    numero_control VARCHAR(20) NOT NULL,
    accion ENUM('MODIFICACION', 'BAJA') NOT NULL,
    datos_anteriores LONGTEXT NOT NULL,
    datos_nuevos LONGTEXT,
    id_usuario INT NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (numero_control) REFERENCES alumnos(numero_control)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    INDEX idx_historial_alumno_fecha (numero_control, fecha)
);

CREATE TABLE expedientes_digitales (
    id_documento INT AUTO_INCREMENT PRIMARY KEY,
    numero_control VARCHAR(20) NOT NULL,
    tipo_documento ENUM('Acta de Nacimiento', 'CURP', 'Comprobante de domicilio', 'INE', 'Certificado Preparatoria', 'Certificado Medico', 'Constancia Situacion Fiscal') NOT NULL,
    ruta_archivo VARCHAR(255) NOT NULL,
    FOREIGN KEY (numero_control) REFERENCES alumnos(numero_control)
        ON UPDATE CASCADE ON DELETE CASCADE,
    UNIQUE (numero_control, tipo_documento)  -- un documento por tipo y alumno
);

-- ==========================================
-- 4. Operación Académica (Docentes, Grupos y Calificaciones)
-- ==========================================
CREATE TABLE empleados_docentes (
    id_docente INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL UNIQUE,
    nombres VARCHAR(50) NOT NULL,
    apellidos VARCHAR(100) NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

-- Tabla intermedia para agrupar materias al momento de reinscribir
CREATE TABLE paquetes_horario (
    id_paquete INT AUTO_INCREMENT PRIMARY KEY,
    nombre_paquete VARCHAR(50) NOT NULL,
    semestre INT NOT NULL
);

CREATE TABLE grupos (
    id_grupo INT AUTO_INCREMENT PRIMARY KEY,
    id_paquete INT NOT NULL,
    id_materia INT NOT NULL,
    id_docente INT NULL, -- NULL indica que el grupo aún no tiene docente asignado
    periodo_escolar VARCHAR(20) NOT NULL,
    turno ENUM('Matutino', 'Vespertino') NOT NULL,
    cupo_maximo INT NOT NULL DEFAULT 25,
    cupo_disponible INT NOT NULL DEFAULT 25, -- lo mantienen los triggers de inscripciones
    FOREIGN KEY (id_paquete) REFERENCES paquetes_horario(id_paquete),
    FOREIGN KEY (id_materia) REFERENCES materias(id_materia),
    FOREIGN KEY (id_docente) REFERENCES empleados_docentes(id_docente),
    CONSTRAINT chk_cupos CHECK (cupo_disponible >= 0 AND cupo_disponible <= cupo_maximo),
    INDEX idx_grupos_periodo (periodo_escolar)
);

CREATE TABLE inscripciones_grupos (
    id_inscripcion INT AUTO_INCREMENT PRIMARY KEY,
    numero_control VARCHAR(20) NOT NULL,
    id_grupo INT NOT NULL,
    FOREIGN KEY (numero_control) REFERENCES alumnos(numero_control)
        ON UPDATE CASCADE,
    FOREIGN KEY (id_grupo) REFERENCES grupos(id_grupo),
    UNIQUE (numero_control, id_grupo)        -- evita doble inscripción al mismo grupo
);

-- Mantienen cupo_disponible sincronizado (si no hay cupo, el CHECK rechaza la inscripción)
CREATE TRIGGER trg_inscripcion_alta
AFTER INSERT ON inscripciones_grupos
FOR EACH ROW
    UPDATE grupos SET cupo_disponible = cupo_disponible - 1 WHERE id_grupo = NEW.id_grupo;

CREATE TRIGGER trg_inscripcion_baja
AFTER DELETE ON inscripciones_grupos
FOR EACH ROW
    UPDATE grupos SET cupo_disponible = cupo_disponible + 1 WHERE id_grupo = OLD.id_grupo;

CREATE TABLE calificaciones (
    id_calificacion INT AUTO_INCREMENT PRIMARY KEY,
    id_inscripcion INT NOT NULL,
    periodo_evaluacion ENUM('Semana 5', 'Semana 9', 'Semana 13', 'Final') NOT NULL,
    valor DECIMAL(5,2),
    FOREIGN KEY (id_inscripcion) REFERENCES inscripciones_grupos(id_inscripcion),
    UNIQUE (id_inscripcion, periodo_evaluacion),
    CONSTRAINT chk_calificacion CHECK (valor IS NULL OR (valor >= 0 AND valor <= 100))
);

CREATE TABLE registro_asistencia (
    id_registro INT AUTO_INCREMENT PRIMARY KEY,
    id_inscripcion INT NOT NULL,
    fecha DATE NOT NULL,
    estatus ENUM('Asistencia', 'Falta', 'Retardo') NOT NULL,
    FOREIGN KEY (id_inscripcion) REFERENCES inscripciones_grupos(id_inscripcion),
    UNIQUE (id_inscripcion, fecha)
);

-- ==========================================
-- 5. Auditoría
-- ==========================================
CREATE TABLE bitacora_accesos (
    id_bitacora INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    fecha DATE NOT NULL,
    hora_entrada TIME NOT NULL,
    hora_salida TIME,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    INDEX idx_bitacora_usuario_fecha (id_usuario, fecha)
);
