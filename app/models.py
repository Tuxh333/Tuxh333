from flask_jwt_extended import create_access_token, jwt_required, JWTManager, get_jwt_identity
from flask_sqlalchemy import SQLAlchemy

# from . import app # Importa la instancia de app desde __init__.py

# Inicializar extensiones sin la instancia de app
jwt = JWTManager()
db = SQLAlchemy()

# --- Modelos SQLAlchemy (representan tus tablas MySQL) ---
# Definimos modelos para las tablas más relevantes, simplificando algunos campos.
# Solo incluimos los campos que realmente necesitarás para la app móvil.

# Modelo para la tabla User (para created_by/updated_by y territorio del usuario)
class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(255), unique=True, nullable=False)
    com_profesion = db.Column(db.Integer, db.ForeignKey('com_profesion.id'))
    documento = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    auth_key = db.Column(db.String(32), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    password_reset_token = db.Column(db.String(255))
    estado = db.Column(db.Integer, nullable=False)
    auth_oficina = db.Column(db.Integer, db.ForeignKey('auth_oficina.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)
    created_by = db.Column(db.Integer, nullable=False)
    updated_by = db.Column(db.Integer, nullable=False)
    ultima_lectura_recordatorio = db.Column(db.Date)
    
    # Relaciones para acceder fácilmente a la información relacionada
    profesion = db.relationship('ComProfesion', foreign_keys=[com_profesion])
    oficina = db.relationship('AuthOficina', foreign_keys=[auth_oficina])

    def __repr__(self):
        return f"<User {self.username}>"

class AuthOficina(db.Model):
    __tablename__ = 'auth_oficina'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, unique=True) # varchar(150) NOT NULL, UNIQUE
    estado = db.Column(db.Integer, nullable=False, default=1) # int(11) NOT NULL DEFAULT 1

    def __repr__(self):
        return f"<AuthOficina {self.nombre}>"

class ComProfesion(db.Model):
    __tablename__ = 'com_profesion'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(250), nullable=False) # varchar(250) NOT NULL
    estado = db.Column(db.Integer, nullable=False, default=1) # int(11) NOT NULL DEFAULT 1
    grupo = db.Column(db.Integer, nullable=False) # int(11) NOT NULL

    def __repr__(self):
        return f"<ComProfesion {self.tipo}>"

# Modelos para sistema de autorización
class AuthItem(db.Model):
    __tablename__ = 'auth_item'
    name = db.Column(db.String(64), primary_key=True)
    type = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    rule_name = db.Column(db.String(64))
    data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f"<AuthItem {self.name}>"

class AuthAssignment(db.Model):
    __tablename__ = 'auth_assignment'
    item_name = db.Column(db.String(64), db.ForeignKey('auth_item.name'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False)
    
    # Relaciones
    auth_item = db.relationship('AuthItem', backref='assignments')
    user = db.relationship('User', backref='permissions')

    def __repr__(self):
        return f"<AuthAssignment {self.user_id}:{self.item_name}>"

# Modelo para base_comuna_corregimiento
class BaseComunaCorregimiento(db.Model):
    __tablename__ = 'base_comuna_corregimiento'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    zona = db.Column(db.SmallInteger, nullable=False) # Usamos SmallInteger para TINYINT

# Modelo para base_barrio_vereda
class BaseBarrioVereda(db.Model):
    __tablename__ = 'base_barrio_vereda'
    id = db.Column(db.Integer, primary_key=True)
    base_comuna_corregimiento = db.Column(db.Integer, db.ForeignKey('base_comuna_corregimiento.id'), nullable=False)
    codigo = db.Column(db.String(30), nullable=False)
    nombre = db.Column(db.String(140), nullable=False)
    microterritorio = db.Column(db.Integer)

# Modelo para aps_ficha_familia
class ApsFichaFamilia(db.Model):
    __tablename__ = 'aps_ficha_familia'
    id = db.Column(db.Integer, primary_key=True)
    apellido_familiar = db.Column(db.String(200))
    telefono_cabeza_familia = db.Column(db.String(40))
    celular_cabeza_familia = db.Column(db.String(40))
    numero_integrantes_familia = db.Column(db.Integer, default=1)
    estado_ficha = db.Column(db.Integer)
    integrantes_con_ficha = db.Column(db.Integer)
    documento_cabeza_familia = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    fecha_ultima_correccion = db.Column(db.DateTime)

# app/models.py

# ... (tus otras importaciones como db, User, ApsFichaFamilia, ApsVisita, ApsPersonaEstilosVidaConducta) ...

class ApsPersona(db.Model):
    __tablename__ = 'aps_persona'
    id = db.Column(db.Integer, primary_key=True)
    puntaje = db.Column(db.Integer) # int(8)
    aps_ficha_familia_id = db.Column(db.Integer, db.ForeignKey('aps_ficha_familia.id'), nullable=False)
    fecha_registro = db.Column(db.Date, nullable=False) # date NOT NULL DEFAULT '0000-00-00'
    nombres = db.Column(db.String(200), nullable=False)
    nombre2 = db.Column(db.String(200))
    apellidos = db.Column(db.String(200), nullable=False)
    apellido2 = db.Column(db.String(200))
    tb_tipo_documento_id = db.Column(db.Integer, db.ForeignKey('tb_tipo_documento.id'), nullable=False) # int(11) NOT NULL
    numero_documento = db.Column(db.String(30), nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=False) # date NOT NULL DEFAULT '0000-00-00'
    edad = db.Column(db.Integer, nullable=False) # int(10) unsigned NOT NULL
    rango_edad = db.Column(db.Integer, nullable=False) # int(11) NOT NULL
    sexo = db.Column(db.Integer, nullable=False) # int(11) NOT NULL
    etnia = db.Column(db.Integer, nullable=False) # int(11) NOT NULL
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Campos de Riesgo y Puntaje (muchos son VARCHAR(8) en MySQL, mapeados a String en SQLAlchemy)
    riesgo_gestante = db.Column(db.String(8))
    puntaje_riesgo_gestante = db.Column(db.Integer)
    evento_gestante = db.Column(db.String(8))
    puntaje_evento_gestante = db.Column(db.Integer)
    evento_critico_gestante = db.Column(db.String(8))
    puntaje_critico_gestante = db.Column(db.Integer)
    riesgo_epoc = db.Column(db.String(8))
    puntaje_epoc = db.Column(db.Integer)
    sintomas_epoc = db.Column(db.String(8))
    evento_epoc = db.Column(db.String(8))
    puntaje_evento_epoc = db.Column(db.Integer)
    evento_critico_epoc = db.Column(db.String(8))
    puntaje_critico_epoc = db.Column(db.Integer)
    riesgo_cardiovascular = db.Column(db.String(8))
    puntaje_cardiovascular = db.Column(db.Integer)
    sintomas_cardiovascular = db.Column(db.String(8))
    evento_cardiovascular = db.Column(db.String(8))
    puntaje_evento_cardiovascular = db.Column(db.Integer)
    evento_critico_cardiovascular = db.Column(db.String(8))
    puntaje_critico_cardiovascular = db.Column(db.Integer)
    riesgo_diabetes = db.Column(db.String(8))
    puntaje_diabetes = db.Column(db.Integer)
    sintomas_diabetes = db.Column(db.String(8))
    evento_diabetes = db.Column(db.String(8))
    puntaje_evento_diabetes = db.Column(db.Integer)
    evento_critico_diabetes = db.Column(db.String(8))
    puntaje_critico_diabetes = db.Column(db.Integer)
    riesgo_cancer_mama = db.Column(db.String(8))
    puntaje_cancer_mama = db.Column(db.Integer)
    sintomas_cancer_mama = db.Column(db.String(8))
    evento_cancer_mama = db.Column(db.String(8))
    puntaje_evento_mama = db.Column(db.Integer)
    evento_critico_cancer_mama = db.Column(db.String(8))
    puntaje_critico_cancer_mama = db.Column(db.Integer)
    riesgo_cancer_prostata = db.Column(db.String(8))
    puntaje_cancer_prostata = db.Column(db.Integer)
    sintomas_cancer_prostata = db.Column(db.String(8))
    evento_cancer_prostata = db.Column(db.String(8))
    puntaje_evento_prostata = db.Column(db.Integer)
    evento_critico_cancer_prostata = db.Column(db.String(8))
    puntaje_critico_prostata = db.Column(db.Integer)
    riesgo_cancer_estomago = db.Column(db.String(8))
    puntaje_cancer_estomago = db.Column(db.Integer)
    sintomas_cancer_estomago = db.Column(db.String(8))
    evento_cancer_estomago = db.Column(db.String(8))
    puntaje_evento_estomago = db.Column(db.Integer)
    evento_critico_cancer_estomago = db.Column(db.String(8))
    puntaje_critico_estomago = db.Column(db.Integer)
    riesgo_cuello_uterino = db.Column(db.String(8))
    puntaje_cuello_uterino = db.Column(db.Integer)
    sintomas_cuello_uterino = db.Column(db.String(8))
    evento_cancer_cuello_uterino = db.Column(db.String(8))
    puntaje_evento_cuello_uterino = db.Column(db.Integer)
    evento_critico_cuello_uterino = db.Column(db.String(8))
    puntaje_critico_cuello_uterino = db.Column(db.Integer)
    riesgo_leucemia = db.Column(db.String(8))
    puntaje_leucemia = db.Column(db.Integer)
    sintomas_leucemia = db.Column(db.String(8))
    evento_leucemia = db.Column(db.String(8))
    puntaje_evento_leucemia = db.Column(db.Integer)
    evento_critico_leucemia = db.Column(db.String(8))
    puntaje_critico_leucemia = db.Column(db.Integer)
    riesgo_cancer_pulmon = db.Column(db.String(8))
    puntaje_cancer_pulmon = db.Column(db.Integer)
    sintomas_cancer_pulmon = db.Column(db.String(8))
    evento_cancer_pulmon = db.Column(db.String(8))
    puntaje_evento_pulmon = db.Column(db.Integer)
    evento_critico_cancer_pulmon = db.Column(db.String(8))
    puntaje_critico_pulmon = db.Column(db.Integer)
    riesgo_cancer_colon = db.Column(db.String(8))
    puntaje_cancer_colon = db.Column(db.Integer)
    sintomas_cancer_colon = db.Column(db.String(8))
    evento_colon = db.Column(db.String(8))
    puntaje_evento_colon = db.Column(db.Integer)
    evento_cancer_colon = db.Column(db.String(8))
    puntaje_critico_colon = db.Column(db.Integer)
    riesgo_trastorno_mental = db.Column(db.String(8))
    puntaje_riesgo_trastorno_mental = db.Column(db.Integer)
    sintomas_trastorno_mental = db.Column(db.String(8))
    evento_trastorno_mental = db.Column(db.String(8))
    puntaje_evento_trastorno = db.Column(db.Integer)
    evento_critico_trastorno_mental = db.Column(db.String(8))
    puntaje_critico_trastorno_mental = db.Column(db.Integer)
    riesgo_vih = db.Column(db.String(8))
    puntaje_vih = db.Column(db.Integer)
    sintomas_vih = db.Column(db.String(8))
    evento_vih = db.Column(db.String(8))
    puntaje_evento_vih = db.Column(db.Integer)
    evento_critico_vih = db.Column(db.String(8))
    puntaje_critico_vih = db.Column(db.Integer)
    riesgo_ninos_menores = db.Column(db.String(8))
    puntaje_ninos_menores = db.Column(db.Integer)
    evento_ninos_menores = db.Column(db.String(8))
    puntaje_evento_ninos = db.Column(db.Integer)
    evento_critico_ninos_menores = db.Column(db.String(8))
    puntaje_critico_ninos_menores = db.Column(db.Integer)
    riesgo_discapacidad = db.Column(db.String(8))
    puntaje_discapacidad = db.Column(db.Integer)
    evento_discapacidad = db.Column(db.String(8))
    puntaje_evento_discapacidad = db.Column(db.Integer)
    evento_critico_discapacidad = db.Column(db.String(8))
    puntaje_critico_discapacidad = db.Column(db.Integer)
    riesgo_violencia = db.Column(db.String(8))
    puntaje_violencia = db.Column(db.Integer)
    evento_violencia = db.Column(db.String(8))
    puntaje_evento_violencia = db.Column(db.Integer)
    evento_critico_violencia = db.Column(db.String(8))
    puntaje_critico_violencia = db.Column(db.Integer)
    riesgo_tuberculosis = db.Column(db.String(8))
    puntaje_tuberculosis = db.Column(db.Integer)
    sintomas_tuberculosis = db.Column(db.String(8))
    evento_tuberculosis = db.Column(db.String(8))
    puntaje_evento_tuberculosis = db.Column(db.Integer)
    evento_critico_tuberculosis = db.Column(db.String(8))
    puntaje_critico_tuberculosis = db.Column(db.Integer)

    identidad_sexual = db.Column(db.Integer, nullable=False) # int(11) NOT NULL
    transgenero = db.Column(db.String(12), nullable=False) # varchar(12) NOT NULL
    auth_oficina = db.Column(db.Integer, db.ForeignKey('auth_oficina.id')) # int(11) DEFAULT NULL
    com_profesion = db.Column(db.Integer, db.ForeignKey('com_profesion.id')) # int(11) DEFAULT NULL
    aps_persona_origen_id = db.Column(db.Integer, db.ForeignKey('aps_persona.id')) # int(11) unsigned DEFAULT NULL
    vigencia_registro = db.Column(db.Boolean, default=True) # tinyint(1) DEFAULT 1
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'), nullable=False) # int(11) unsigned NOT NULL

    # Relación para acceder fácilmente a los datos de estilo de vida
    estilos_vida_conducta_info = db.relationship(
        'ApsPersonaEstilosVidaConducta',
        backref='persona',
        uselist=False, # Si solo esperamos un registro relevante por persona en esta relación
        primaryjoin="ApsPersona.id == ApsPersonaEstilosVidaConducta.aps_persona_id"
    )

    def __repr__(self):
        return f"<ApsPersona {self.nombres} {self.apellidos}>"

# Modelo para aps_visita (simplificado)
class ApsVisita(db.Model):
    __tablename__ = 'aps_visita'
    id = db.Column(db.Integer, primary_key=True)
    aps_ficha_familia_id = db.Column(db.Integer, db.ForeignKey('aps_ficha_familia.id'), nullable=False)
    fecha_visita = db.Column(db.Date, nullable=False)
    tipo_actividad = db.Column(db.Integer)
    codigo_cups = db.Column(db.String(255))
    auth_oficina = db.Column(db.Integer, db.ForeignKey('auth_oficina.id'))
    com_profesion = db.Column(db.Integer, db.ForeignKey('com_profesion.id'))
    # Asegúrate de que esta columna esté presente:
    duracion = db.Column(db.Integer) # Este campo almacena el ID de aps_cue_opcion
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    aps_visita_origen_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    vigencia_registro = db.Column(db.Boolean)
    valido = db.Column(db.Boolean)
    invalidated_by = db.Column(db.Integer)
    invalidated_at = db.Column(db.Date)
    apellido_familiar = db.Column(db.String(200))
    celular_cabeza_familia = db.Column(db.String(40))
    numero_integrantes_familia = db.Column(db.Integer)
    estado_ficha = db.Column(db.Integer)

    # Opcional: Definir una relación para facilitar el acceso a la descripción de la duración
    # duracion_opcion = db.relationship('ApsCueOpcion', primaryjoin="ApsVisita.duracion == ApsCueOpcion.id", uselist=False)
    
    # Relaciones para acceder a la información de profesión y oficina
    profesion = db.relationship('ComProfesion', foreign_keys=[com_profesion])
    oficina = db.relationship('AuthOficina', foreign_keys=[auth_oficina])

    def __repr__(self):
        return f"<ApsVisita {self.id}>"

class ApsCueOpcion(db.Model):
    __tablename__ = 'aps_cue_opcion'
    id = db.Column(db.Integer, primary_key=True)
    aps_cue_pregunta = db.Column(db.Integer, nullable=False) # FK a aps_cue_pregunta
    orden = db.Column(db.SmallInteger)
    descripcion = db.Column(db.String(255), nullable=False) # Este es el campo que necesitamos
    estado = db.Column(db.Boolean, default=True) # 1=visible, 0=oculto

    def __repr__(self):
        return f"<ApsCueOpcion {self.descripcion}>"

# Modelo para BaseTipoDocumento
class BaseTipoDocumento(db.Model):
    __tablename__ = 'tb_tipo_documento' # Asegúrate de que este sea el nombre real de tu tabla en MySQL
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(255), nullable=False) # O el tipo de dato real si es diferente

# ... (otras importaciones y configuraciones) ...

# Modelo para Equipo
class Equipo(db.Model):
    __tablename__ = 'equipo'
    id = db.Column(db.Integer, primary_key=True)
    numero_equipo = db.Column(db.Integer, nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    estado = db.Column(db.Boolean, default=True) # tinyint(1) a Boolean
    tipo = db.Column(db.Enum('Equipo básico', 'Equipo complementario', 'Centro de escucha', 'Transversal'))

# Modelo para EquipoUser (Tabla de relación entre Equipo y User)
class EquipoUser(db.Model):
    __tablename__ = 'equipo_user'
    id = db.Column(db.Integer, primary_key=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey('equipo.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Modelo para EquipoComunaCorregimiento (Tabla de relación entre Equipo y Comuna)
class EquipoComunaCorregimiento(db.Model):
    __tablename__ = 'equipo_comuna_corregimiento'
    id = db.Column(db.Integer, primary_key=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey('equipo.id'), nullable=False)
    base_comuna_corregimiento_id = db.Column(db.Integer, db.ForeignKey('base_comuna_corregimiento.id'), nullable=False)

# ... (Tus modelos existentes, asegúrate de que User tenga su 'id' como Primary Key si no lo tiene) ...

# Actualización de ApsUbicacionFamilia para incluir la FK a ApsVisita
class ApsUbicacionFamilia(db.Model):
    __tablename__ = 'aps_ubicacion_familia'
    id = db.Column(db.Integer, primary_key=True)
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'), nullable=False)
    zona = db.Column(db.Integer, nullable=False)
    base_comuna_corregimiento_id = db.Column(db.Integer, db.ForeignKey('base_comuna_corregimiento.id'), nullable=False)
    base_barrio_vereda_id = db.Column(db.Integer, db.ForeignKey('base_barrio_vereda.id'), nullable=False)
    direccion = db.Column(db.String(255), nullable=False)
    ficha_catastral = db.Column(db.String(255), default='')
    numero_cuadrante = db.Column(db.Integer, default=0)
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Date, nullable=False)
    updated_by = db.Column(db.Date, nullable=False)
    # deleted_at = db.Column(db.Date) # Para soft delete

# Asegúrate de que este modelo esté en tu app.py
class ApsPersonaEstilosVidaConducta(db.Model):
    __tablename__ = 'aps_persona_estilos_vida_conducta'
    id = db.Column(db.Integer, primary_key=True)
    aps_persona_id = db.Column(db.Integer, db.ForeignKey('aps_persona.id'))
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    practica_actividad_fisica_minutos = db.Column(db.Integer)
    aps_habitos_alimentacion_txt = db.Column(db.String(260), nullable=False)
    aps_exposicion_humo_txt = db.Column(db.String(260), nullable=False)
    aps_inasistencia_controles_txt = db.Column(db.String(260), nullable=False)
    eps_entrega_cumplidamente_metodo_planificacion_familiar = db.Column(db.Integer)
    aps_adherencia_tratamiento_txt = db.Column(db.String(260), nullable=False)
    aps_dificultades_recibir_tratamiento_txt = db.Column(db.String(260), nullable=False)
    aps_remision_a_txt = db.Column(db.String(260), nullable=False)
    especifique_remision_a = db.Column(db.Text)
    aps_valoracion_equipo_aps_txt = db.Column(db.String(260), nullable=False)
    cual_valoracion = db.Column(db.String(250))
    peso = db.Column(db.Float) # Mapeado de FLOAT(5,1)
    talla = db.Column(db.Float) # Mapeado de FLOAT(5,1)
    interpretacion_IMC = db.Column(db.Text)
    valor_imc = db.Column(db.Float, nullable=False) # Mapeado de FLOAT(5,2)
    perimetro_brazo = db.Column(db.Integer)
    interpretacion_perimetro = db.Column(db.Text)
    interpretacion_FINDRICS = db.Column(db.Text)
    valor_findrics = db.Column(db.Integer)
    interpretacion_riesgo_epoc = db.Column(db.Text)
    valor_riesgo_epoc = db.Column(db.Integer)
    interpretacion_riesgo_caries = db.Column(db.Text)
    valor_riesgo_caries = db.Column(db.Integer)
    novedad = db.Column(db.Integer)
    observaciones = db.Column(db.Text)
    intervenciones = db.Column(db.Text)
    estado_registro = db.Column(db.Integer, default=0)
    tipo_actividad = db.Column(db.Integer, default=0)
    adjunto = db.Column(db.String(100)) # Podría ser la ruta a un archivo
    cantidad_campos_cambiados = db.Column(db.Integer) # Campo clave para el cálculo
    razon_remision_ebs = db.Column(db.Text)
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    updated_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    # deleted_at = db.Column(db.Date) # Para soft delete (añadir si no existe en tu tabla MySQL)

    def __repr__(self):
        return f"<ApsPersonaEstilosVidaConducta {self.id}>"

class ApsPersonaAntecedenteMedico(db.Model):
    __tablename__ = 'aps_persona_antecedente_medico'
    id = db.Column(db.Integer, primary_key=True)
    aps_persona_id = db.Column(db.Integer, db.ForeignKey('aps_persona.id'))
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    aps_antecedente_personal_txt = db.Column(db.String(260), nullable=False)
    aps_enfermedad_actual_txt = db.Column(db.String(260), nullable=False)
    aps_antecedente_familiar_primer_segundo_grado_txt = db.Column(db.String(260), nullable=False)
    aps_sintoma_reciente_sin_causa_aparente_txt = db.Column(db.String(260), nullable=False)
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    updated_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    # deleted_at = db.Column(db.Date) # Para soft delete (añadir si no existe en tu tabla MySQL)

    def __repr__(self):
        return f"<ApsPersonaAntecedenteMedico {self.id}>"

class ApsPersonaComponenteMental(db.Model):
    __tablename__ = 'aps_persona_componente_mental'
    id = db.Column(db.Integer, primary_key=True)
    aps_persona_id = db.Column(db.Integer, db.ForeignKey('aps_persona.id'))
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    se_ha_sentido_triste_decaido_ultimas_dos_semanas = db.Column(db.Integer)
    ha_pensado_deseado_estaria_mejor_muerto = db.Column(db.Integer)
    miembro_familia_comportamiento_extranio_diferente_anormal = db.Column(db.Integer)
    situacion_reciente_problema_psicosocial = db.Column(db.Integer)
    resultado_apgar_familiar = db.Column(db.String(100))
    sospecha_confirmacion_violencia_intrafamiliar = db.Column(db.Integer)
    agredido_fisica_psicologica_por_familiar_ultimos_tres_meses = db.Column(db.Integer)
    hospitalizado_debido_violencia_intrafamiliar = db.Column(db.Integer)
    han_utilizado_elementos_contundentes_para_agredirle = db.Column(db.Integer)
    aps_consumo_spa_txt = db.Column(db.String(260), nullable=False)
    # persona_cuidadora = db.Column(db.Integer)
    # aps_pcd_adulto_mayor_txt = db.Column(db.String(260))
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    updated_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    # deleted_at = db.Column(db.Date) # Para soft delete (añadir si no existe en tu tabla MySQL)

    def __repr__(self):
        return f"<ApsPersonaComponenteMental {self.id}>"

class ApsPersonaCondicionesSalud(db.Model):
    __tablename__ = 'aps_persona_condiciones_salud'
    id = db.Column(db.Integer, primary_key=True)
    aps_persona_id = db.Column(db.Integer, db.ForeignKey('aps_persona.id'))
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    circunferencia_abdominal_cm = db.Column(db.Integer)
    interpretacion_circunferencia = db.Column(db.Text)
    presion_arterial_sistolica = db.Column(db.Integer)
    presion_arterial_diastolica = db.Column(db.Integer)
    nivel = db.Column(db.Text)
    resultado_ultima_citologia_cervico_uterina = db.Column(db.Integer)
    fecha_programada_citologia_cervico_uterina = db.Column(db.Date)
    resultado_antigeno_prostatico = db.Column(db.Integer)
    resultado_ultima_mamografia = db.Column(db.Integer)
    en_su_embarazo_su_madre_consumio_alcohol_cigarrillo = db.Column(db.Integer)
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    updated_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    # deleted_at = db.Column(db.Date) # Para soft delete (añadir si no existe en tu tabla MySQL)

    def __repr__(self):
        return f"<ApsPersonaCondicionesSalud {self.id}>"

# Asegúrate de que este modelo esté en tu app.py
class ApsPersonaDatoBasico(db.Model):
    __tablename__ = 'aps_persona_dato_basico'
    id = db.Column(db.Integer, primary_key=True)
    aps_persona_id = db.Column(db.Integer, db.ForeignKey('aps_persona.id'))
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    aps_dato_basico_condicion_txt = db.Column(db.String(260), nullable=False)
    aps_dato_basico_discapacidad_txt = db.Column(db.String(260), nullable=False)
    condicion_dependencia_discapacidad = db.Column(db.String(100))
    parentesco = db.Column(db.Integer, nullable=False)
    regimen = db.Column(db.Integer, nullable=False)
    eps_id = db.Column(db.Integer, db.ForeignKey('eps.id'))
    ocupacion_principal = db.Column(db.Integer)
    depende_economicamente_familiar = db.Column(db.Integer)
    escolaridad = db.Column(db.Integer)
    abandono_estudios_primaria_bachiller = db.Column(db.Integer)
    # Campos de puntaje (mapear según tu necesidad real, muchos son VARCHAR(8) en MySQL)
    puntaje_hacinamiento = db.Column(db.Integer)
    puntaje_vivienda = db.Column(db.Integer)
    puntaje_residuo = db.Column(db.Integer)
    puntaje_solido = db.Column(db.Integer)
    puntaje_excreta = db.Column(db.Integer)
    puntaje_plaga = db.Column(db.Integer)
    puntaje_almacenamiento = db.Column(db.Integer)
    puntaje_casero = db.Column(db.Integer)
    puntaje_piso = db.Column(db.Integer)
    puntaje_techo = db.Column(db.Integer)
    puntaje_pared = db.Column(db.Integer)
    puntaje_iluminacion = db.Column(db.Integer)
    puntaje_ventilacion = db.Column(db.Integer)
    puntaje_conexion = db.Column(db.Integer)
    puntaje_agua = db.Column(db.Integer)
    puntaje_deposito = db.Column(db.Integer)
    puntaje_lavamano = db.Column(db.Integer)
    puntaje_lavavajilla = db.Column(db.Integer)
    puntaje_lavarropa = db.Column(db.Integer)
    puntaje_ducha = db.Column(db.Integer)
    puntaje_inodoro = db.Column(db.Integer)
    puntaje_cocina = db.Column(db.Integer)
    puntaje_alimento = db.Column(db.Integer)
    puntaje_coccion = db.Column(db.Integer)
    puntaje_higiene = db.Column(db.Integer)
    puntaje_sanidad = db.Column(db.Integer)
    puntaje_acustica = db.Column(db.Integer)
    puntaje_fuente = db.Column(db.Integer)
    puntaje_plaguicida = db.Column(db.Integer)
    puntaje_entorno = db.Column(db.Integer)
    puntaje_comunidad = db.Column(db.Integer)
    puntaje_asi = db.Column(db.Integer)
    puntaje_calle = db.Column(db.Integer)
    puntaje_pna = db.Column(db.Integer)
    # Los siguientes puntajes eran VARCHAR(8) en MySQL, los mapeamos a String
    puntaje_desempleado = db.Column(db.String(8))
    puntaje_depende = db.Column(db.String(8))
    puntaje_escolaridad = db.Column(db.String(8))
    puntaje_estudio = db.Column(db.String(8))
    puntaje_biberon = db.Column(db.String(8))
    puntaje_esquema = db.Column(db.String(8))
    puntaje_cepillado = db.Column(db.String(8))
    puntaje_seda = db.Column(db.String(8))
    puntaje_condon = db.Column(db.String(8))
    puntaje_natural = db.Column(db.String(8))
    puntaje_planificacion = db.Column(db.String(8))
    puntaje_embarazo = db.Column(db.String(8))
    puntaje_circunferencia = db.Column(db.String(8))
    puntaje_citologia = db.Column(db.String(8))
    puntaje_prostatico = db.Column(db.String(8))
    puntaje_mamografia = db.Column(db.String(8))
    puntaje_triste = db.Column(db.String(8))
    puntaje_muerto = db.Column(db.String(8))
    puntaje_anormal = db.Column(db.String(8))
    puntaje_psicosocial = db.Column(db.String(8))
    puntaje_apgar = db.Column(db.String(8))
    puntaje_alcohol = db.Column(db.String(8))
    puntaje_abuso = db.Column(db.String(8))
    puntaje_cigarrillo = db.Column(db.String(8))
    puntaje_spa = db.Column(db.String(8))
    puntaje_fisica = db.Column(db.String(8))
    puntaje_sal = db.Column(db.String(8))
    puntaje_fruta = db.Column(db.String(8))
    puntaje_verdura = db.Column(db.String(8))
    puntaje_grasa = db.Column(db.String(8))
    puntaje_azucar = db.Column(db.String(8))
    puntaje_salsa = db.Column(db.String(8))
    puntaje_humo = db.Column(db.String(8))
    puntaje_carbon = db.Column(db.String(8))
    puntaje_control = db.Column(db.String(8))
    puntaje_medicamento = db.Column(db.String(8))
    puntaje_gestiona = db.Column(db.String(8))
    puntaje_asiste = db.Column(db.String(8))
    puntaje_asume = db.Column(db.String(8))
    puntaje_brazo = db.Column(db.String(8))
    puntaje_ficha = db.Column(db.Integer)
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    updated_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    # deleted_at = db.Column(db.Date) # Para soft delete (añadir si no existe en tu tabla MySQL)

    def __repr__(self):
        return f"<ApsPersonaDatoBasico {self.id}>"

# Asegúrate de que este modelo esté en tu app.py
class ApsPersonaMaternidad(db.Model):
    __tablename__ = 'aps_persona_maternidad'
    id = db.Column(db.Integer, primary_key=True)
    aps_persona_id = db.Column(db.Integer, db.ForeignKey('aps_persona.id'))
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    numero_partos_cesareas = db.Column(db.Integer)
    antecedente_cesarea_parto_instrumentado = db.Column(db.Integer)
    edad_momento_nacer_primer_hijo = db.Column(db.Integer)
    ha_lactado = db.Column(db.Integer)
    embarazo_actual_aceptado = db.Column(db.Integer)
    clasificacion_riesgo_obstetrico = db.Column(db.Integer)
    aps_motivo_riesgo_txt = db.Column(db.String(260), nullable=False)
    primigestante = db.Column(db.Integer)
    conoce_fecha_probable_parto = db.Column(db.Integer)
    fecha_probable_parto = db.Column(db.Date)
    complicaciones_parto_puerperio = db.Column(db.Integer)
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    updated_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    # deleted_at = db.Column(db.Date) # Para soft delete (añadir si no existe en tu tabla MySQL)

    def __repr__(self):
        return f"<ApsPersonaMaternidad {self.id}>"

# Asegúrate de que este modelo esté en tu app.py
class ApsPersonaPracticasSaludSaludSexual(db.Model):
    __tablename__ = 'aps_persona_practicas_salud_salud_sexual'
    id = db.Column(db.Integer, primary_key=True)
    aps_persona_id = db.Column(db.Integer, db.ForeignKey('aps_persona.id'))
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    biberon = db.Column(db.Integer)
    esquema_vacunacion_completo = db.Column(db.Integer)
    fecha_proxima_vacunacion = db.Column(db.Date)
    cepillado_diario_minimo = db.Column(db.Integer, nullable=False)
    seda_dental_minimo = db.Column(db.Integer)
    primera_menstruacion_antes_doce_anios = db.Column(db.Integer)
    ultima_menstruacion_despues_cincuenta_anios = db.Column(db.Integer)
    actualmente_tiene_relaciones_sexuales = db.Column(db.Integer)
    aps_practica_sexual_riesgosa_txt = db.Column(db.String(260), nullable=False)
    aps_metodo_planificacion_txt = db.Column(db.String(260), nullable=False)
    constante_metodo_planificacion = db.Column(db.Integer)
    utilizado_anticonceptivos_orales_mas_diez_anios = db.Column(db.Integer)
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    updated_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    # deleted_at = db.Column(db.Date) # Para soft delete (añadir si no existe en tu tabla MySQL)

    def __repr__(self):
        return f"<ApsPersonaPracticasSaludSaludSexual {self.id}>"

class ApsCondicionesHabitatFamilia(db.Model):
    __tablename__ = 'aps_condiciones_habitat_familia'
    id = db.Column(db.Integer, primary_key=True)
    aps_visita_id = db.Column(db.Integer, db.ForeignKey('aps_visita.id'))
    aps_ficha_familia = db.Column(db.Integer) # No es una FK en el modelo si solo almacena el ID
    aps_aspectos_generales_txt = db.Column(db.String(260), nullable=False, default='') # Clave aquí
    aps_condiciones_locativas_txt = db.Column(db.String(260), nullable=False, default='')
    aps_condiciones_agua_txt = db.Column(db.String(260), nullable=False, default='')
    aps_dotacion_sanitaria_txt = db.Column(db.String(260), nullable=False, default='')
    aps_alimentos_txt = db.Column(db.String(260), nullable=False, default='')
    aps_tenencia_animales_txt = db.Column(db.String(260), nullable=False, default='')
    aps_entorno_vivienda_txt = db.Column(db.String(260), nullable=False, default='')
    numero_perros = db.Column(db.Integer)
    numero_gatos = db.Column(db.Integer)
    created_at = db.Column(db.Date, nullable=False)
    updated_at = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    updated_by = db.Column(db.Integer, nullable=False) # Considerar FK a User
    # deleted_at = db.Column(db.Date) # Para soft delete (añadir si no existe en tu tabla MySQL)

    def __repr__(self):
        return f"<ApsCondicionesHabitatFamilia {self.id}>"