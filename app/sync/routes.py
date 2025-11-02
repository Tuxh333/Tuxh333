# app/sync/routes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import datetime
from sqlalchemy import func, and_
from app.models import db, User, BaseTipoDocumento, BaseComunaCorregimiento, BaseBarrioVereda, \
                      Equipo, EquipoUser, EquipoComunaCorregimiento, \
                      ApsFichaFamilia, ApsPersona, ApsVisita, ApsUbicacionFamilia, \
                      ApsPersonaAntecedenteMedico, ApsPersonaComponenteMental, ApsPersonaCondicionesSalud, \
                      ApsPersonaDatoBasico, ApsPersonaEstilosVidaConducta, ApsPersonaMaternidad, \
                      ApsPersonaPracticasSaludSaludSexual, ApsCueOpcion, ApsCondicionesHabitatFamilia, \
                      ComProfesion, AuthOficina
from app.sync.utils import calculate_total_updated_fields_for_family_ficha, get_descriptions_from_comma_separated_ids

sync_bp = Blueprint('sync_bp', __name__, url_prefix='/api/v1/sync')

# Endpoint de Sincronización Inicial de Datos (GET)
@sync_bp.route("/initial-data", methods=["GET"])
@jwt_required()
def get_initial_data():
    current_user_identity_username = get_jwt_identity() # Obtiene el username
    user = User.query.filter_by(username=current_user_identity_username).first()

    if not user:
        return jsonify({"message": "Usuario no encontrado para sincronización"}), 404

    # --- Obtener parámetros de paginación ---
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)

    # --- 1. Obtener los IDs de las comunas/territorios asignados al usuario ---
    # a. Encontrar los IDs de los equipos a los que pertenece el usuario
    equipo_ids = [eu.equipo_id for eu in EquipoUser.query.filter_by(user_id=user.id).all()]

    if not equipo_ids:
        # Si el usuario no está en ningún equipo, no tiene territorios asignados
        return jsonify({
            "message": "Usuario no tiene equipos asignados, por lo tanto no tiene territorios.",
            "catalog_data": {
                "tipos_documento": [], # No enviamos catálogos de territorio si no tiene ninguno
                "comunas": [],
                "barrios": [],
                "profesiones": [],
                "oficinas": []
            },
            "transactional_data": {
                "familias": [],
                "personas": [],
                "visitas": []
            },
            "last_sync_timestamp": datetime.datetime.now().isoformat()
        }), 200

    # b. Encontrar los IDs de las comunas asociadas a esos equipos
    user_comuna_ids = [
        ecc.base_comuna_corregimiento_id
        for ecc in EquipoComunaCorregimiento.query.filter(
            EquipoComunaCorregimiento.equipo_id.in_(equipo_ids)
        ).distinct().all()
    ]

    if not user_comuna_ids:
        return jsonify({
            "message": "Usuario con equipos pero sin comunas/territorios asignados.",
            "catalog_data": {
                "tipos_documento": [],
                "comunas": [],
                "barrios": [],
                "profesiones": [],
                "oficinas": []
            },
            "transactional_data": {
                "familias": [],
                "personas": [],
                "visitas": []
            },
            "last_sync_timestamp": datetime.datetime.now().isoformat()
        }), 200


    # --- 2. Optimización: Eliminar catálogos que ahora se traducen server-side ---
    # NOTA: Se eliminaron del catalog_data porque ahora se envían traducidos directamente:
    # - tipos_documento: traducido en personas (tb_tipo_documento_tipo)  
    # - comunas/barrios: traducido en ubicaciones_familia (base_comuna_corregimiento_nombre, base_barrio_vereda_nombre)
    # - profesiones: traducido en familias (created_by_profesion, updated_by_profesion) y visitas (com_profesion_descripcion)
    # - oficinas: traducido en familias (created_by_oficina, updated_by_oficina) y visitas (auth_oficina_nombre)

    catalog_data = {
        # Catálogos eliminados para optimización - ahora se envían traducidos server-side
        # "tipos_documento": eliminado
        # "comunas": eliminado  
        # "barrios": eliminado
        # "profesiones": eliminado
        # "oficinas": eliminado
    }

    # --- 3. Obtener datos transaccionales filtrados por los territorios del usuario ---
    # a. Obtener los IDs de las visitas que pertenecen a las comunas del usuario
    visita_ids_in_territory = [
        au.aps_visita_id
        for au in ApsUbicacionFamilia.query.filter(
            ApsUbicacionFamilia.base_comuna_corregimiento_id.in_(user_comuna_ids)
        ).distinct().all()
    ]

    # Si no hay visitas en el territorio, devolver respuesta vacía
    if not visita_ids_in_territory:
        return jsonify({
            "message": "No hay visitas en los territorios asignados al usuario.",
            "catalog_data": catalog_data,
            "transactional_data": {
                "familias": [],
                "personas": [],
                "visitas": [],
                "ubicaciones_familia": [],
                "condiciones_habitat_familia": [],
                "persona_antecedente_medico": [],
                "persona_componente_mental": [],
                "persona_condiciones_salud": [],
                "persona_dato_basico": [],
                "persona_estilos_vida_conducta": [],
                "persona_maternidad": [],
                "persona_practicas_salud_salud_sexual": []
            },
            "pagination_meta": {
                "page": page,
                "per_page": per_page,
                "total": 0,
                "pages": 0,
                "has_next": False,
                "has_prev": False
            },
            "last_sync_timestamp": datetime.datetime.now().isoformat()
        }), 200

    # b. NUEVA ESTRATEGIA: Primero obtener familias válidas del territorio, luego filtrar visitas
    
    # Paso 1: Obtener todas las familias válidas del territorio (sin paginación aún)
    # Obtener todas las visitas del territorio para encontrar familias
    all_visitas_in_territory = ApsVisita.query.filter(
        ApsVisita.id.in_(visita_ids_in_territory),
        ApsVisita.estado_ficha == 800  # Solo fichas con estado 'Activa'
    ).all()
    
    # Obtener todas las personas de estas visitas con apellidos válidos
    all_visitas_ids = [v.id for v in all_visitas_in_territory]
    personas_territorio = ApsPersona.query.filter(
        ApsPersona.aps_visita_id.in_(all_visitas_ids),
        # ApsPersona.apellidos.isnot(None),    # No NULL
        # ApsPersona.apellidos != '',          # No vacío  
        ApsPersona.apellidos != 'NULL'       # No string 'NULL'
    ).all()
    
    # Obtener familias válidas del territorio
    familia_ids_territorio = list(set([p.aps_ficha_familia_id for p in personas_territorio if p.aps_ficha_familia_id]))
    familias_territorio = []
    if familia_ids_territorio:
        familias_territorio = ApsFichaFamilia.query.filter(
            ApsFichaFamilia.id.in_(familia_ids_territorio),
            ApsFichaFamilia.apellido_familiar.isnot(None),  # No NULL
            ApsFichaFamilia.apellido_familiar != '',        # No vacío
            ApsFichaFamilia.apellido_familiar != 'NULL'     # No string 'NULL'
        ).all()
    
    # Paso 2: Filtrar visitas que pertenecen a familias válidas Y obtener solo la última visita de cada familia
    familias_validas_ids = [f.id for f in familias_territorio]
    
    # Crear un diccionario para almacenar solo la última visita de cada familia
    ultima_visita_por_familia = {}
    
    for visita in all_visitas_in_territory:
        if visita.aps_ficha_familia_id in familias_validas_ids:
            familia_id = visita.aps_ficha_familia_id
            
            # Si no hay visita para esta familia o la actual es más reciente, la guardamos
            if (familia_id not in ultima_visita_por_familia or 
                visita.fecha_visita > ultima_visita_por_familia[familia_id].fecha_visita):
                ultima_visita_por_familia[familia_id] = visita
    
    # Convertir el diccionario a lista para mantener compatibilidad con el resto del código
    visitas_filtradas = list(ultima_visita_por_familia.values())
    
    # Si no hay visitas válidas después del filtrado
    if not visitas_filtradas:
        return jsonify({
            "message": "No hay visitas válidas con familias activas en los territorios asignados al usuario.",
            "catalog_data": catalog_data,
            "transactional_data": {
                "familias": [],
                "personas": [],
                "visitas": [],
                "ubicaciones_familia": [],
                "condiciones_habitat_familia": [],
                "persona_antecedente_medico": [],
                "persona_componente_mental": [],
                "persona_condiciones_salud": [],
                "persona_dato_basico": [],
                "persona_estilos_vida_conducta": [],
                "persona_maternidad": [],
                "persona_practicas_salud_salud_sexual": []
            },
            "pagination_meta": {
                "page": page,
                "per_page": per_page,
                "total": 0,
                "pages": 0,
                "has_next": False,
                "has_prev": False
            },
            "last_sync_timestamp": datetime.datetime.now().isoformat()
        }), 200
    
    # Paso 3: Aplicar paginación a las visitas filtradas
    total_visitas = len(visitas_filtradas)
    total_pages = (total_visitas + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    visitas_paginated_list = visitas_filtradas[start_idx:end_idx]
    
    # Crear alias para joins de usuarios
    UserCreated = db.aliased(User)
    UserUpdated = db.aliased(User)
    
    # Paso 4: Obtener información completa de las visitas paginadas con joins
    visitas_ids_paginated = [v.id for v in visitas_paginated_list]
    
    # Crear alias para las diferentes tablas de ApsCueOpcion
    DuracionOpcion = db.aliased(ApsCueOpcion)
    TipoActividadOpcion = db.aliased(ApsCueOpcion)
    
    visitas_with_details = db.session.query(
        ApsVisita,
        DuracionOpcion.descripcion.label('duracion_descripcion'),
        TipoActividadOpcion.descripcion.label('tipo_actividad_descripcion'),
        ComProfesion.tipo.label('profesion_descripcion'),
        AuthOficina.nombre.label('oficina_nombre'),
        UserCreated.username.label('created_by_username'),
        UserCreated.name.label('created_by_name'),
        UserCreated.documento.label('created_by_documento'),
        UserUpdated.username.label('updated_by_username'),
        UserUpdated.name.label('updated_by_name'),
        UserUpdated.documento.label('updated_by_documento')
    ).outerjoin(
        DuracionOpcion, ApsVisita.duracion == DuracionOpcion.id
    ).outerjoin(
        TipoActividadOpcion, ApsVisita.tipo_actividad == TipoActividadOpcion.id
    ).outerjoin(
        ComProfesion, ApsVisita.com_profesion == ComProfesion.id
    ).outerjoin(
        AuthOficina, ApsVisita.auth_oficina == AuthOficina.id
    ).outerjoin(
        UserCreated, ApsVisita.created_by == UserCreated.id
    ).outerjoin(
        UserUpdated, ApsVisita.updated_by == UserUpdated.id
    ).filter(
        ApsVisita.id.in_(visitas_ids_paginated)
    ).all()

    # Serializar las visitas de la página actual
    visitas_serialized = []
    for visita_obj, duracion_desc, tipo_actividad_desc, profesion_desc, oficina_nombre, created_by_username, created_by_name, created_by_documento, updated_by_username, updated_by_name, updated_by_documento in visitas_with_details:
        visita_data = {
            "id": visita_obj.id,
            "aps_ficha_familia_id": visita_obj.aps_ficha_familia_id,
            "fecha_visita": visita_obj.fecha_visita.isoformat() if visita_obj.fecha_visita else None,
            "tipo_actividad_id": visita_obj.tipo_actividad,
            "tipo_actividad_descripcion": tipo_actividad_desc,
            "codigo_cups": visita_obj.codigo_cups,
            "auth_oficina_id": visita_obj.auth_oficina,
            "auth_oficina_nombre": oficina_nombre,
            "com_profesion_id": visita_obj.com_profesion,
            "com_profesion_descripcion": profesion_desc,
            "created_at": visita_obj.created_at.isoformat() if visita_obj.created_at else None,
            "updated_at": visita_obj.updated_at.isoformat() if visita_obj.updated_at else None,
            "created_by": visita_obj.created_by,
            "created_by_username": created_by_username,
            "created_by_name": created_by_name,
            "created_by_documento": created_by_documento,
            "updated_by": visita_obj.updated_by,
            "updated_by_username": updated_by_username,
            "updated_by_name": updated_by_name,
            "updated_by_documento": updated_by_documento,
            "duracion_id": visita_obj.duracion,
            "duracion_descripcion": duracion_desc
        }
        visitas_serialized.append(visita_data)

    # c. Obtener los IDs de las visitas de la página actual
    current_page_visita_ids = [visita_obj.id for visita_obj, _, _, _, _, _, _, _, _, _, _ in visitas_with_details]
    
    # d. Obtener familias y personas de las visitas paginadas
    # Como ya filtramos las familias válidas, obtenemos las de la página actual
    current_page_familia_ids = list(set([v.aps_ficha_familia_id for v in visitas_paginated_list]))
    
    # Crear consulta con joins para obtener detalles de created_by y updated_by para familias
    # Incluimos también la información de oficina y profesión del responsable
    familias_with_details = db.session.query(
        ApsFichaFamilia,
        UserCreated.username.label('created_by_username'),
        UserCreated.name.label('created_by_name'), 
        UserCreated.documento.label('created_by_documento'),
        UserCreated.auth_oficina.label('created_by_oficina_id'),
        UserCreated.com_profesion.label('created_by_profesion_id'),
        UserUpdated.username.label('updated_by_username'),
        UserUpdated.name.label('updated_by_name'),
        UserUpdated.documento.label('updated_by_documento'),
        UserUpdated.auth_oficina.label('updated_by_oficina_id'),
        UserUpdated.com_profesion.label('updated_by_profesion_id')
    ).outerjoin(
        UserCreated, ApsFichaFamilia.created_by == UserCreated.id
    ).outerjoin(
        UserUpdated, ApsFichaFamilia.updated_by == UserUpdated.id
    ).filter(
        ApsFichaFamilia.id.in_(current_page_familia_ids)
    ).all()
    
    # Obtener TODAS las personas de las familias de la página actual con su último registro
    # Implementamos la lógica: MAX(fecha_visita) GROUP BY numero_documento por cada familia
    personas_finales = []
    
    for familia_id in current_page_familia_ids:
        # Para cada familia, obtenemos todas sus personas agrupadas por numero_documento
        # y seleccionamos el registro más reciente (última visita) de cada persona
        
        # Subconsulta para obtener la fecha máxima de visita por documento en esta familia
        subquery = db.session.query(
            ApsPersona.numero_documento,
            func.max(ApsVisita.fecha_visita).label('max_fecha_visita')
        ).join(
            ApsVisita, ApsPersona.aps_visita_id == ApsVisita.id
        ).filter(
            ApsPersona.aps_ficha_familia_id == familia_id,
            ApsPersona.apellidos != 'NULL'  # Filtro de apellidos válidos
        ).group_by(
            ApsPersona.numero_documento
        ).subquery()
        
        # Consulta principal para obtener el registro completo de cada persona
        # con su visita más reciente
        personas_familia = db.session.query(ApsPersona).join(
            ApsVisita, ApsPersona.aps_visita_id == ApsVisita.id
        ).join(
            subquery, 
            and_(
                ApsPersona.numero_documento == subquery.c.numero_documento,
                ApsVisita.fecha_visita == subquery.c.max_fecha_visita
            )
        ).filter(
            ApsPersona.aps_ficha_familia_id == familia_id
        ).all()
        
        personas_finales.extend(personas_familia)
    
    # Usar las personas finales en lugar del filtro anterior
    personas = personas_finales

    # g. Obtener las ubicaciones de familia asociadas a las visitas de la página actual
    ubicaciones_familia = ApsUbicacionFamilia.query.filter(ApsUbicacionFamilia.aps_visita_id.in_(current_page_visita_ids)).all()

    # --- Obtener todas las tablas de detalle de persona filtradas por personas específicas ---
    # ESTRATEGIA OPTIMIZADA: Filtramos por las personas específicas que están en la última visita
    # de cada familia. Esto asegura datos precisos y eficientes.
    
    # Obtener los IDs de las personas de la página actual
    current_page_persona_ids = [p.id for p in personas]
    
    # Antecedentes médicos
    persona_antecedente_medico = ApsPersonaAntecedenteMedico.query.filter(
        ApsPersonaAntecedenteMedico.aps_persona_id.in_(current_page_persona_ids)
    ).all()

    # Componente mental
    persona_componente_mental = ApsPersonaComponenteMental.query.filter(
        ApsPersonaComponenteMental.aps_persona_id.in_(current_page_persona_ids)
    ).all()

    # Condiciones de salud
    persona_condiciones_salud = ApsPersonaCondicionesSalud.query.filter(
        ApsPersonaCondicionesSalud.aps_persona_id.in_(current_page_persona_ids)
    ).all()

    # Datos básicos
    persona_dato_basico = ApsPersonaDatoBasico.query.filter(
        ApsPersonaDatoBasico.aps_persona_id.in_(current_page_persona_ids)
    ).all()

    # Estilos de vida y conducta
    persona_estilos_vida_conducta = ApsPersonaEstilosVidaConducta.query.filter(
        ApsPersonaEstilosVidaConducta.aps_persona_id.in_(current_page_persona_ids)
    ).all()

    # Maternidad
    persona_maternidad = ApsPersonaMaternidad.query.filter(
        ApsPersonaMaternidad.aps_persona_id.in_(current_page_persona_ids)
    ).all()

    # Prácticas de salud y salud sexual
    persona_practicas_salud_salud_sexual = ApsPersonaPracticasSaludSaludSexual.query.filter(
        ApsPersonaPracticasSaludSaludSexual.aps_persona_id.in_(current_page_persona_ids)
    ).all()

    # --- Obtener y serializar ApsCondicionesHabitatFamilia ---
    condiciones_habitat_familia_records = ApsCondicionesHabitatFamilia.query.filter(
        ApsCondicionesHabitatFamilia.aps_visita_id.in_(current_page_visita_ids)
    ).all()

    condiciones_habitat_familia_data = []
    for chf in condiciones_habitat_familia_records:
        chf_data = {
            "id": chf.id,
            "aps_visita_id": chf.aps_visita_id,
            "aps_ficha_familia": chf.aps_ficha_familia,
            # Procesar los campos _txt para obtener sus descripciones
            "aspectos_generales": get_descriptions_from_comma_separated_ids(chf.aps_aspectos_generales_txt),
            "condiciones_locativas": get_descriptions_from_comma_separated_ids(chf.aps_condiciones_locativas_txt),
            "condiciones_agua": get_descriptions_from_comma_separated_ids(chf.aps_condiciones_agua_txt),
            "dotacion_sanitaria": get_descriptions_from_comma_separated_ids(chf.aps_dotacion_sanitaria_txt),
            "alimentos": get_descriptions_from_comma_separated_ids(chf.aps_alimentos_txt),
            "tenencia_animales": get_descriptions_from_comma_separated_ids(chf.aps_tenencia_animales_txt),
            "entorno_vivienda": get_descriptions_from_comma_separated_ids(chf.aps_entorno_vivienda_txt),
            "numero_perros": chf.numero_perros,
            "numero_gatos": chf.numero_gatos,
            "created_at": chf.created_at.isoformat() if chf.created_at else None,
            "updated_at": chf.updated_at.isoformat() if chf.updated_at else None,
            "created_by": chf.created_by,
            "updated_by": chf.updated_by
        }
        condiciones_habitat_familia_data.append(chf_data)

    # --- Obtener traducciones de ApsCueOpcion para códigos ---
    # Crear diccionarios de traducciones para mejorar el rendimiento
    # Obtener todas las traducciones necesarias en una sola consulta
    all_opciones = ApsCueOpcion.query.all()
    traducciones = {opcion.id: opcion.descripcion for opcion in all_opciones}
    
    # --- Obtener traducciones de ubicaciones ---
    # Obtener todas las comunas y barrios para traducciones
    all_comunas = BaseComunaCorregimiento.query.all()
    traducciones_comunas = {comuna.id: comuna.nombre for comuna in all_comunas}
    
    all_barrios = BaseBarrioVereda.query.all()
    traducciones_barrios = {barrio.id: barrio.nombre for barrio in all_barrios}
    
    # --- Obtener traducciones de tipos de documento ---
    # Obtener todos los tipos de documento para traducciones
    all_tipos_documento = BaseTipoDocumento.query.all()
    traducciones_tipos_documento = {td.id: td.tipo for td in all_tipos_documento}
    
    # --- Obtener traducciones de oficinas y profesiones ---
    # Obtener todas las oficinas para traducciones
    all_oficinas = AuthOficina.query.all()
    traducciones_oficinas = {oficina.id: oficina.nombre for oficina in all_oficinas}
    
    # Obtener todas las profesiones para traducciones
    all_profesiones = ComProfesion.query.all()
    traducciones_profesiones = {profesion.id: profesion.tipo for profesion in all_profesiones}
    
    # Función helper para obtener descripción de códigos
    def get_traduccion(codigo_id):
        return traducciones.get(codigo_id, '') if codigo_id else ''
    
    # Función helper para obtener nombre de comuna
    def get_nombre_comuna(comuna_id):
        return traducciones_comunas.get(comuna_id, '') if comuna_id else ''
    
    # Función helper para obtener nombre de barrio
    def get_nombre_barrio(barrio_id):
        return traducciones_barrios.get(barrio_id, '') if barrio_id else ''
    
    # Función helper para obtener tipo de documento
    def get_tipo_documento(tipo_documento_id):
        return traducciones_tipos_documento.get(tipo_documento_id, '') if tipo_documento_id else ''
    
    # Función helper para obtener nombre de oficina
    def get_nombre_oficina(oficina_id):
        return traducciones_oficinas.get(oficina_id, '') if oficina_id else ''
    
    # Función helper para obtener tipo de profesión
    def get_tipo_profesion(profesion_id):
        return traducciones_profesiones.get(profesion_id, '') if profesion_id else ''

    # --- Obtener información de novedad para cada persona ---
    # Crear diccionario con novedad traducida por persona
    novedad_por_persona = {}
    for pevc in persona_estilos_vida_conducta:
        if pevc.aps_persona_id and pevc.novedad:
            novedad_por_persona[pevc.aps_persona_id] = get_traduccion(pevc.novedad)

    transactional_data = {
        "familias": [{
            "id": familia_obj.id,
            "apellido_familiar": familia_obj.apellido_familiar,
            "celular_cabeza_familia": familia_obj.celular_cabeza_familia,
            "numero_integrantes_familia": familia_obj.numero_integrantes_familia,
            "estado_ficha_id": familia_obj.estado_ficha,
            "estado_ficha_descripcion": get_traduccion(familia_obj.estado_ficha),
            "documento_cabeza_familia": familia_obj.documento_cabeza_familia,
            "created_at": familia_obj.created_at.isoformat() if familia_obj.created_at and hasattr(familia_obj.created_at, 'isoformat') else None,
            "updated_at": familia_obj.updated_at.isoformat() if familia_obj.updated_at and hasattr(familia_obj.updated_at, 'isoformat') else None,
            "created_by": familia_obj.created_by,
            "created_by_username": created_by_username,
            "created_by_name": created_by_name,
            "created_by_documento": created_by_documento,
            "created_by_oficina": get_nombre_oficina(created_by_oficina_id),
            "created_by_profesion": get_tipo_profesion(created_by_profesion_id),
            "updated_by": familia_obj.updated_by,
            "updated_by_username": updated_by_username,
            "updated_by_name": updated_by_name,
            "updated_by_documento": updated_by_documento,
            "updated_by_oficina": get_nombre_oficina(updated_by_oficina_id),
            "updated_by_profesion": get_tipo_profesion(updated_by_profesion_id),
            "fecha_ultima_correccion": familia_obj.fecha_ultima_correccion.isoformat() if familia_obj.fecha_ultima_correccion else None,
            "total_campos_actualizados_ultima_visita": calculate_total_updated_fields_for_family_ficha(familia_obj.id)
        } for familia_obj, created_by_username, created_by_name, created_by_documento, created_by_oficina_id, created_by_profesion_id, updated_by_username, updated_by_name, updated_by_documento, updated_by_oficina_id, updated_by_profesion_id in familias_with_details],
        "personas": [{
            "id": p.id,
            "aps_ficha_familia_id": p.aps_ficha_familia_id,
            "fecha_registro": p.fecha_registro.isoformat() if p.fecha_registro and hasattr(p.fecha_registro, 'isoformat') else None,
            "nombres": p.nombres,
            "apellidos": p.apellidos,
            "numero_documento": p.numero_documento,
            "tb_tipo_documento_id": p.tb_tipo_documento_id,
            "tb_tipo_documento_tipo": get_tipo_documento(p.tb_tipo_documento_id),
            "sexo_id": p.sexo,
            "sexo_descripcion": get_traduccion(p.sexo),
            "etnia_id": p.etnia,
            "etnia_descripcion": get_traduccion(p.etnia),
            "edad": p.edad,
            "fecha_nacimiento": p.fecha_nacimiento.isoformat() if p.fecha_nacimiento and hasattr(p.fecha_nacimiento, 'isoformat') else None,
            "created_at": p.created_at.isoformat() if p.created_at and hasattr(p.created_at, 'isoformat') else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at and hasattr(p.updated_at, 'isoformat') else None,
            "created_by": p.created_by,
            "updated_by": p.updated_by,
            "aps_visita_id": p.aps_visita_id,
            "novedad": novedad_por_persona.get(p.id, '')
        } for p in personas],
        "visitas": visitas_serialized,
        "ubicaciones_familia": [{
            "id": uf.id,
            "aps_visita_id": uf.aps_visita_id,
            "zona": uf.zona,
            "base_comuna_corregimiento_id": uf.base_comuna_corregimiento_id,
            "base_comuna_corregimiento_nombre": get_nombre_comuna(uf.base_comuna_corregimiento_id),
            "base_barrio_vereda_id": uf.base_barrio_vereda_id,
            "base_barrio_vereda_nombre": get_nombre_barrio(uf.base_barrio_vereda_id),
            "direccion": uf.direccion,
            "ficha_catastral": uf.ficha_catastral,
            "numero_cuadrante": uf.numero_cuadrante,
            "created_at": uf.created_at.isoformat() if uf.created_at and hasattr(uf.created_at, 'isoformat') else None,
            "updated_at": uf.updated_at.isoformat() if uf.updated_at and hasattr(uf.updated_at, 'isoformat') else None,
            "created_by": uf.created_by,
            "updated_by": uf.updated_by
        } for uf in ubicaciones_familia],
        "condiciones_habitat_familia": condiciones_habitat_familia_data,
        "persona_antecedente_medico": [{
            "id": pam.id,
            "aps_persona_id": pam.aps_persona_id,
            "aps_visita_id": pam.aps_visita_id,
            "created_at": pam.created_at.isoformat() if pam.created_at and hasattr(pam.created_at, 'isoformat') else None,
            "updated_at": pam.updated_at.isoformat() if pam.updated_at and hasattr(pam.updated_at, 'isoformat') else None,
            "created_by": pam.created_by,
            "updated_by": pam.updated_by
        } for pam in persona_antecedente_medico],
        "persona_componente_mental": [{
            "id": pcm.id,
            "aps_persona_id": pcm.aps_persona_id,
            "aps_visita_id": pcm.aps_visita_id,
            "created_at": pcm.created_at.isoformat() if pcm.created_at and hasattr(pcm.created_at, 'isoformat') else None,
            "updated_at": pcm.updated_at.isoformat() if pcm.updated_at and hasattr(pcm.updated_at, 'isoformat') else None,
            "created_by": pcm.created_by,
            "updated_by": pcm.updated_by
        } for pcm in persona_componente_mental],
        "persona_condiciones_salud": [{
            "id": pcs.id,
            "aps_persona_id": pcs.aps_persona_id,
            "aps_visita_id": pcs.aps_visita_id,
            "created_at": pcs.created_at.isoformat() if pcs.created_at and hasattr(pcs.created_at, 'isoformat') else None,
            "updated_at": pcs.updated_at.isoformat() if pcs.updated_at and hasattr(pcs.updated_at, 'isoformat') else None,
            "created_by": pcs.created_by,
            "updated_by": pcs.updated_by
        } for pcs in persona_condiciones_salud],
        "persona_dato_basico": [{
            "id": pdb.id,
            "aps_persona_id": pdb.aps_persona_id,
            "aps_visita_id": pdb.aps_visita_id,
            "created_at": pdb.created_at.isoformat() if pdb.created_at and hasattr(pdb.created_at, 'isoformat') else None,
            "updated_at": pdb.updated_at.isoformat() if pdb.updated_at and hasattr(pdb.updated_at, 'isoformat') else None,
            "created_by": pdb.created_by,
            "updated_by": pdb.updated_by
        } for pdb in persona_dato_basico],
        "persona_estilos_vida_conducta": [{
            "id": pevc.id,
            "aps_persona_id": pevc.aps_persona_id,
            "aps_visita_id": pevc.aps_visita_id,
            "created_at": pevc.created_at.isoformat() if pevc.created_at and hasattr(pevc.created_at, 'isoformat') else None,
            "updated_at": pevc.updated_at.isoformat() if pevc.updated_at and hasattr(pevc.updated_at, 'isoformat') else None,
            "created_by": pevc.created_by,
            "updated_by": pevc.updated_by
        } for pevc in persona_estilos_vida_conducta],
        "persona_maternidad": [{
            "id": pm.id,
            "aps_persona_id": pm.aps_persona_id,
            "aps_visita_id": pm.aps_visita_id,
            "created_at": pm.created_at.isoformat() if pm.created_at and hasattr(pm.created_at, 'isoformat') else None,
            "updated_at": pm.updated_at.isoformat() if pm.updated_at and hasattr(pm.updated_at, 'isoformat') else None,
            "created_by": pm.created_by,
            "updated_by": pm.updated_by
        } for pm in persona_maternidad],
        "persona_practicas_salud_salud_sexual": [{
            "id": ppsss.id,
            "aps_persona_id": ppsss.aps_persona_id,
            "aps_visita_id": ppsss.aps_visita_id,
            "created_at": ppsss.created_at.isoformat() if ppsss.created_at and hasattr(ppsss.created_at, 'isoformat') else None,
            "updated_at": ppsss.updated_at.isoformat() if ppsss.updated_at and hasattr(ppsss.updated_at, 'isoformat') else None,
            "created_by": ppsss.created_by,
            "updated_by": ppsss.updated_by
        } for ppsss in persona_practicas_salud_salud_sexual]
    }

    last_server_update_timestamp = datetime.datetime.now().isoformat()

    # Metadatos de paginación
    pagination_meta = {
        "page": page,
        "per_page": per_page,
        "total": total_visitas,
        "pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

    return jsonify({
        "catalog_data": catalog_data,
        "transactional_data": transactional_data,
        "pagination_meta": pagination_meta,
        "last_sync_timestamp": last_server_update_timestamp
    }), 200


# --- Endpoint para Sincronización de Cambios (POST) ---
@sync_bp.route("/changes", methods=["POST"])
@jwt_required()
def post_changes():
    current_user_identity_username = get_jwt_identity()
    user = User.query.filter_by(username=current_user_identity_username).first()

    if not user:
        return jsonify({"message": "Usuario no encontrado para sincronización"}), 401

    changes = request.json # Recibe el JSON con los cambios del móvil
    sync_results = {
    "familias": {"created": [], "updated": [], "deleted": []},
    "personas": {"created": [], "updated": [], "deleted": []},
    "visitas": {"created": [], "updated": [], "deleted": []},
    "ubicaciones_familia": {"created": [], "updated": [], "deleted": []},
    # --- Tablas de Detalle de Persona/Familia ---
    "condiciones_habitat_familia": {"created": [], "updated": [], "deleted": []},
    "persona_antecedente_medico": {"created": [], "updated": [], "deleted": []},
    "persona_componente_mental": {"created": [], "updated": [], "deleted": []},
    "persona_condiciones_salud": {"created": [], "updated": [], "deleted": []},
    "persona_dato_basico": {"created": [], "updated": [], "deleted": []},
    "persona_estilos_vida_conducta": {"created": [], "updated": [], "deleted": []},
    "persona_maternidad": {"created": [], "updated": [], "deleted": []},
    "persona_practicas_salud_salud_sexual": {"created": [], "updated": [], "deleted": []},
}

    # --- Procesar Cambios en Familias (aps_ficha_familia) ---
    if 'familias' in changes:
        # Inserciones (CREATED)
        for item in changes['familias'].get('created', []):
            local_id = item.pop('id') # El ID local de la app móvil
            # Pop los campos de sincronización que no van a la DB MySQL directamente
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None) # Lo usaremos para el servidor si es nuevo
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                # Crea un nuevo objeto familia con los datos recibidos
                # Asegúrate de mapear los nombres de los campos correctamente
                new_familia = ApsFichaFamilia(**item) # Esto asume que los keys de item coinciden con los nombres de las columnas
                new_familia.created_at = datetime.datetime.fromisoformat(item.get('created_at'))
                new_familia.updated_at = datetime.datetime.now() # Actualiza a la hora del servidor
                
                db.session.add(new_familia)
                db.session.flush() # Para obtener el ID de MySQL antes del commit

                sync_results['familias']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_familia.id, # El nuevo ID generado por MySQL
                    "new_last_modified_at": new_familia.updated_at.isoformat(), # Timestamp del servidor
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback() # Deshace si hay un error
                sync_results['familias']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['familias'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None) # Timestamp del móvil
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id: # No debería ocurrir si es una actualización
                sync_results['familias']['updated'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": "No remote_id provided for update"
                })
                continue

            try:
                familia_to_update = ApsFichaFamilia.query.get(remote_id)
                if not familia_to_update:
                    sync_results['familias']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "status": "failed",
                        "error": "Record not found on server"
                    })
                    continue

                # --- Resolución de Conflictos (Last Write Wins) ---
                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str) if mobile_last_modified_at_str else datetime.datetime.min
                server_ts = familia_to_update.updated_at # O el campo que uses como last_modified en MySQL

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()): # Si la versión del móvil es más reciente
                    for key, value in item.items():
                        # Actualiza solo los campos que están en 'item'
                        # Asegúrate de manejar los tipos de datos correctos
                        if hasattr(familia_to_update, key):
                            # Convierte fechas/datetime de string a objeto datetime si es necesario
                            if 'created_at' in key or 'updated_at' in key: # Ejemplo de manejo de fechas
                                setattr(familia_to_update, key, datetime.datetime.fromisoformat(value))
                            else:
                                setattr(familia_to_update, key, value)
                    familia_to_update.updated_at = datetime.datetime.now() # Actualiza la fecha de modificación del servidor

                    sync_results['familias']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": familia_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else: # La versión del servidor es igual o más reciente
                    sync_results['familias']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(), # Devolver el timestamp del servidor
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
                    # Opcional: Podrías añadir la data actual del servidor para que el móvil la descargue
                    # y resuelva el conflicto si es necesario.

            except Exception as e:
                db.session.rollback()
                sync_results['familias']['updated'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['familias'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['familias']['deleted'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": "No remote_id provided for deletion"
                })
                continue

            try:
                familia_to_delete = ApsFichaFamilia.query.get(remote_id)
                if not familia_to_delete:
                    sync_results['familias']['deleted'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "status": "failed",
                        "error": "Record not found on server for deletion"
                    })
                    continue

                # Asumo que tienes una columna como 'vigencia_registro' o 'deleted_at'
                # para realizar un soft delete. Si no, necesitarás añadirla a tu modelo.
                # Ejemplo con 'vigencia_registro' (0 = inactivo/eliminado)
                familia_to_delete.vigencia_registro = 0
                familia_to_delete.updated_at = datetime.datetime.now() # Actualizar timestamp de modificación

                sync_results['familias']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": familia_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['familias']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "failed",
                    "error": str(e)
                })

    # --- Procesar Cambios en Visitas (ApsVisita) ---
    if 'visitas' in changes:
        # Inserciones (CREATED)
        for item in changes['visitas'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                # Conversión de fechas de string a objeto Date
                item['fecha_visita'] = datetime.datetime.fromisoformat(item['fecha_visita']).date()
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date() # Fecha de creación/actualización del servidor

                # Confirmar de que item['aps_ficha_familia_id'] sea el remote_id de la familia en MySQL
                new_visita = ApsVisita(**item)
                db.session.add(new_visita)
                db.session.flush() # Obtener el ID de MySQL

                sync_results['visitas']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_visita.id,
                    "new_last_modified_at": new_visita.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['visitas']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['visitas'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['visitas']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                visita_to_update = ApsVisita.query.get(remote_id)
                if not visita_to_update:
                    sync_results['visitas']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                # Resolución de Conflictos (Last Write Wins)
                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = visita_to_update.updated_at # Asegúrate de que este campo exista en tu modelo ApsVisita

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(visita_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(visita_to_update, key, datetime.datetime.fromisoformat(value).date())
                            else:
                                setattr(visita_to_update, key, value)
                    visita_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['visitas']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": visita_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['visitas']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['visitas']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['visitas'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['visitas']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                visita_to_delete = ApsVisita.query.get(remote_id)
                if not visita_to_delete:
                    sync_results['visitas']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                # Para ApsVisita, según el dump, podrías usar 'vigencia_registro' o 'valido' para soft delete.
                # Usaremos 'valido' para marcarla como inválida (eliminada lógicamente).
                visita_to_delete.valido = False # O 0, si es TINYINT(1)
                visita_to_delete.updated_at = datetime.datetime.now().date() # Actualizar fecha de modificación
                visita_to_delete.invalidated_at = datetime.datetime.now().date() # Campo específico de la tabla para invalidación
                visita_to_delete.invalidated_by = user.id # Asignar el usuario que la invalida

                sync_results['visitas']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": visita_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['visitas']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Procesar Cambios en Personas (ApsPersona) ---
    if 'personas' in changes:
        # Inserciones (CREATED)
        for item in changes['personas'].get('created', []):
            local_id = item.pop('id')
            # Pop los campos de sincronización que no van a la DB MySQL directamente
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None) # Lo usaremos para el servidor si es nuevo
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                # Conversión de fechas de string a objeto Date o DateTime
                item['fecha_registro'] = datetime.datetime.fromisoformat(item['fecha_registro']).date()
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                # updated_at será la fecha actual del servidor al insertar
                item['updated_at'] = datetime.datetime.now().date()
                
                # Asegúrate de que los campos aps_ficha_familia_id, created_by, updated_by existan y sean válidos
                # Para aps_ficha_familia_id, la app móvil debería enviar el remote_id de la familia a la que pertenece
                # Si la familia es nueva y se creó en la misma sincronización, la app debe mapear el ID local temporal de la familia al ID local de la persona
                # y luego el backend debe resolver esto con el remote_id de la familia.
                # Por simplicidad aquí, asumimos que item['aps_ficha_familia_id'] ya es el remote_id de MySQL.
                
                new_persona = ApsPersona(**item)
                db.session.add(new_persona)
                db.session.flush() # Obtener el ID de MySQL antes del commit

                sync_results['personas']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_persona.id,
                    "new_last_modified_at": new_persona.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['personas']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['personas'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['personas']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                persona_to_update = ApsPersona.query.get(remote_id)
                if not persona_to_update:
                    sync_results['personas']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                # Resolución de Conflictos (Last Write Wins)
                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = persona_to_update.updated_at # Asegúrate de que este campo exista en tu modelo ApsPersona

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(persona_to_update, key):
                            # Manejar conversión de tipos si es necesario, especialmente para fechas
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(persona_to_update, key, datetime.datetime.fromisoformat(value).date())
                            else:
                                setattr(persona_to_update, key, value)
                    persona_to_update.updated_at = datetime.datetime.now().date() # Fecha de actualización del servidor

                    sync_results['personas']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": persona_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['personas']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['personas']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['personas'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['personas']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                persona_to_delete = ApsPersona.query.get(remote_id)
                if not persona_to_delete:
                    sync_results['personas']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                # Asumo que aps_persona tiene una columna 'vigencia_registro' o similar para soft delete.
                # Si no, necesitarás añadirla a tu modelo y base de datos.
                persona_to_delete.vigencia_registro = False # O 0, si usas TINYINT en MySQL
                persona_to_delete.updated_at = datetime.datetime.now().date() # Actualizar fecha de modificación

                sync_results['personas']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": persona_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['personas']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Procesar Cambios en Ubicaciones_Familia (ApsUbicacionFamilia) ---
    if 'ubicaciones_familia' in changes:
        # Inserciones (CREATED)
        for item in changes['ubicaciones_familia'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None) # Asegúrate de que no se envíe deleted_at si es una creación

            try:
                # Conversión de fechas de string a objeto Date
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date() # Fecha de creación/actualización del servidor
                
                # Asegúrate de que item['aps_visita_id'] sea el remote_id de la visita en MySQL
                # Y que base_comuna_corregimiento_id y base_barrio_vereda_id sean IDs válidos de MySQL
                new_ubicacion = ApsUbicacionFamilia(**item)
                db.session.add(new_ubicacion)
                db.session.flush() # Obtener el ID de MySQL

                sync_results['ubicaciones_familia']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_ubicacion.id,
                    "new_last_modified_at": new_ubicacion.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['ubicaciones_familia']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['ubicaciones_familia'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['ubicaciones_familia']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                ubicacion_to_update = ApsUbicacionFamilia.query.get(remote_id)
                if not ubicacion_to_update:
                    sync_results['ubicaciones_familia']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                # Resolución de Conflictos (Last Write Wins)
                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = ubicacion_to_update.updated_at # Asegúrate de que este campo exista en tu modelo

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(ubicacion_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(ubicacion_to_update, key, datetime.datetime.fromisoformat(value).date())
                            else:
                                setattr(ubicacion_to_update, key, value)
                    ubicacion_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['ubicaciones_familia']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": ubicacion_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['ubicaciones_familia']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['ubicaciones_familia']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['ubicaciones_familia'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['ubicaciones_familia']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                ubicacion_to_delete = ApsUbicacionFamilia.query.get(remote_id)
                if not ubicacion_to_delete:
                    sync_results['ubicaciones_familia']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                # Soft delete: Actualiza la columna 'deleted_at'
                ubicacion_to_delete.deleted_at = datetime.datetime.now().date()
                ubicacion_to_delete.updated_at = datetime.datetime.now().date() # También actualiza el updated_at

                sync_results['ubicaciones_familia']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": ubicacion_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['ubicaciones_familia']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Procesar Cambios en aps_persona_antecedente_medico ---
    if 'persona_antecedente_medico' in changes:
        # Inserciones (CREATED)
        for item in changes['persona_antecedente_medico'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date()
                
                # Asegúrate de que aps_persona_id y aps_visita_id sean los remote_id de MySQL
                new_antecedente = ApsPersonaAntecedenteMedico(**item)
                db.session.add(new_antecedente)
                db.session.flush()

                sync_results['persona_antecedente_medico']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_antecedente.id,
                    "new_last_modified_at": new_antecedente.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_antecedente_medico']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['persona_antecedente_medico'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['persona_antecedente_medico']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                antecedente_to_update = ApsPersonaAntecedenteMedico.query.get(remote_id)
                if not antecedente_to_update:
                    sync_results['persona_antecedente_medico']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = antecedente_to_update.updated_at

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(antecedente_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(antecedente_to_update, key, datetime.datetime.fromisoformat(value).date())
                            else:
                                setattr(antecedente_to_update, key, value)
                    antecedente_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['persona_antecedente_medico']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": antecedente_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['persona_antecedente_medico']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_antecedente_medico']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['persona_antecedente_medico'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['persona_antecedente_medico']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                antecedente_to_delete = ApsPersonaAntecedenteMedico.query.get(remote_id)
                if not antecedente_to_delete:
                    sync_results['persona_antecedente_medico']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                antecedente_to_delete.deleted_at = datetime.datetime.now().date()
                antecedente_to_delete.updated_at = datetime.datetime.now().date()

                sync_results['persona_antecedente_medico']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": antecedente_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_antecedente_medico']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Procesar Cambios en aps_persona_componente_mental ---
    if 'persona_componente_mental' in changes:
        # Inserciones (CREATED)
        for item in changes['persona_componente_mental'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date()
                
                # Asegúrate de que aps_persona_id y aps_visita_id sean los remote_id de MySQL
                new_componente = ApsPersonaComponenteMental(**item)
                db.session.add(new_componente)
                db.session.flush()

                sync_results['persona_componente_mental']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_componente.id,
                    "new_last_modified_at": new_componente.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_componente_mental']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['persona_componente_mental'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['persona_componente_mental']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                componente_to_update = ApsPersonaComponenteMental.query.get(remote_id)
                if not componente_to_update:
                    sync_results['persona_componente_mental']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = componente_to_update.updated_at

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(componente_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(componente_to_update, key, datetime.datetime.fromisoformat(value).date())
                            else:
                                setattr(componente_to_update, key, value)
                    componente_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['persona_componente_mental']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": componente_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['persona_componente_mental']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_componente_mental']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['persona_componente_mental'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['persona_componente_mental']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                componente_to_delete = ApsPersonaComponenteMental.query.get(remote_id)
                if not componente_to_delete:
                    sync_results['persona_componente_mental']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                componente_to_delete.deleted_at = datetime.datetime.now().date()
                componente_to_delete.updated_at = datetime.datetime.now().date()

                sync_results['persona_componente_mental']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": componente_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_componente_mental']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Procesar Cambios en aps_persona_condiciones_salud ---
    if 'persona_condiciones_salud' in changes:
        # Inserciones (CREATED)
        for item in changes['persona_condiciones_salud'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                # Conversión de fechas
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date()
                if 'fecha_programada_citologia_cervico_uterina' in item and item['fecha_programada_citologia_cervico_uterina']:
                    item['fecha_programada_citologia_cervico_uterina'] = datetime.datetime.fromisoformat(item['fecha_programada_citologia_cervico_uterina']).date()
                
                # Asegúrate de que aps_persona_id y aps_visita_id sean los remote_id de MySQL
                new_condicion_salud = ApsPersonaCondicionesSalud(**item)
                db.session.add(new_condicion_salud)
                db.session.flush()

                sync_results['persona_condiciones_salud']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_condicion_salud.id,
                    "new_last_modified_at": new_condicion_salud.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_condiciones_salud']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['persona_condiciones_salud'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['persona_condiciones_salud']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                condicion_salud_to_update = ApsPersonaCondicionesSalud.query.get(remote_id)
                if not condicion_salud_to_update:
                    sync_results['persona_condiciones_salud']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = condicion_salud_to_update.updated_at

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(condicion_salud_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(condicion_salud_to_update, key, datetime.datetime.fromisoformat(value).date() if value else None)
                            else:
                                setattr(condicion_salud_to_update, key, value)
                    condicion_salud_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['persona_condiciones_salud']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": condicion_salud_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['persona_condiciones_salud']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_condiciones_salud']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['persona_condiciones_salud'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['persona_condiciones_salud']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                condicion_salud_to_delete = ApsPersonaCondicionesSalud.query.get(remote_id)
                if not condicion_salud_to_delete:
                    sync_results['persona_condiciones_salud']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                condicion_salud_to_delete.deleted_at = datetime.datetime.now().date()
                condicion_salud_to_delete.updated_at = datetime.datetime.now().date()

                sync_results['persona_condiciones_salud']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": condicion_salud_to_update.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_condiciones_salud']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Procesar Cambios en aps_persona_dato_basico ---
    if 'persona_dato_basico' in changes:
        # Inserciones (CREATED)
        for item in changes['persona_dato_basico'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date()
                
                # Asegúrate de que aps_persona_id, aps_visita_id y eps_id sean los remote_id de MySQL
                new_dato_basico = ApsPersonaDatoBasico(**item)
                db.session.add(new_dato_basico)
                db.session.flush()

                sync_results['persona_dato_basico']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_dato_basico.id,
                    "new_last_modified_at": new_dato_basico.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_dato_basico']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['persona_dato_basico'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['persona_dato_basico']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                dato_basico_to_update = ApsPersonaDatoBasico.query.get(remote_id)
                if not dato_basico_to_update:
                    sync_results['persona_dato_basico']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = dato_basico_to_update.updated_at

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(dato_basico_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(dato_basico_to_update, key, datetime.datetime.fromisoformat(value).date() if value else None)
                            else:
                                setattr(dato_basico_to_update, key, value)
                    dato_basico_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['persona_dato_basico']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": dato_basico_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['persona_dato_basico']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_dato_basico']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['persona_dato_basico'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['persona_dato_basico']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                dato_basico_to_delete = ApsPersonaDatoBasico.query.get(remote_id)
                if not dato_basico_to_delete:
                    sync_results['persona_dato_basico']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                dato_basico_to_delete.deleted_at = datetime.datetime.now().date()
                dato_basico_to_delete.updated_at = datetime.datetime.now().date()

                sync_results['persona_dato_basico']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": dato_basico_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_dato_basico']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Procesar Cambios en aps_persona_estilos_vida_conducta ---
    if 'persona_estilos_vida_conducta' in changes:
        # Inserciones (CREATED)
        for item in changes['persona_estilos_vida_conducta'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                # Conversión de fechas y floats
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date()
                # Asegúrate de convertir los floats si vienen como string (aunque jsonify los mantiene como número)
                if 'peso' in item and item['peso'] is not None: item['peso'] = float(item['peso'])
                if 'talla' in item and item['talla'] is not None: item['talla'] = float(item['talla'])
                if 'valor_imc' in item and item['valor_imc'] is not None: item['valor_imc'] = float(item['valor_imc'])
                
                # Asegúrate de que aps_persona_id y aps_visita_id sean los remote_id de MySQL
                new_estilo_vida = ApsPersonaEstilosVidaConducta(**item)
                db.session.add(new_estilo_vida)
                db.session.flush()

                sync_results['persona_estilos_vida_conducta']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_estilo_vida.id,
                    "new_last_modified_at": new_estilo_vida.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_estilos_vida_conducta']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['persona_estilos_vida_conducta'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['persona_estilos_vida_conducta']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                estilo_vida_to_update = ApsPersonaEstilosVidaConducta.query.get(remote_id)
                if not estilo_vida_to_update:
                    sync_results['persona_estilos_vida_conducta']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = estilo_vida_to_update.updated_at

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(estilo_vida_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(estilo_vida_to_update, key, datetime.datetime.fromisoformat(value).date() if value else None)
                            elif key in ['peso', 'talla', 'valor_imc'] and value is not None: # Convertir floats
                                setattr(estilo_vida_to_update, key, float(value))
                            else:
                                setattr(estilo_vida_to_update, key, value)
                    estilo_vida_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['persona_estilos_vida_conducta']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": estilo_vida_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['persona_estilos_vida_conducta']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_estilos_vida_conducta']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['persona_estilos_vida_conducta'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['persona_estilos_vida_conducta']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                estilo_vida_to_delete = ApsPersonaEstilosVidaConducta.query.get(remote_id)
                if not estilo_vida_to_delete:
                    sync_results['persona_estilos_vida_conducta']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                estilo_vida_to_delete.deleted_at = datetime.datetime.now().date()
                estilo_vida_to_delete.updated_at = datetime.datetime.now().date()

                sync_results['persona_estilos_vida_conducta']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": estilo_vida_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_estilos_vida_conducta']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

# --- Procesar Cambios en aps_persona_maternidad ---
    if 'persona_maternidad' in changes:
        # Inserciones (CREATED)
        for item in changes['persona_maternidad'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                # Conversión de fechas
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date()
                if 'fecha_probable_parto' in item and item['fecha_probable_parto']:
                    item['fecha_probable_parto'] = datetime.datetime.fromisoformat(item['fecha_probable_parto']).date()
                
                # Asegúrate de que aps_persona_id y aps_visita_id sean los remote_id de MySQL
                new_maternidad = ApsPersonaMaternidad(**item)
                db.session.add(new_maternidad)
                db.session.flush()

                sync_results['persona_maternidad']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_maternidad.id,
                    "new_last_modified_at": new_maternidad.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_maternidad']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['persona_maternidad'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['persona_maternidad']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                maternidad_to_update = ApsPersonaMaternidad.query.get(remote_id)
                if not maternidad_to_update:
                    sync_results['persona_maternidad']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = maternidad_to_update.updated_at

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(maternidad_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(maternidad_to_update, key, datetime.datetime.fromisoformat(value).date() if value else None)
                            else:
                                setattr(maternidad_to_update, key, value)
                    maternidad_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['persona_maternidad']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": maternidad_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['persona_maternidad']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_maternidad']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['persona_maternidad'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['persona_maternidad']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                maternidad_to_delete = ApsPersonaMaternidad.query.get(remote_id)
                if not maternidad_to_delete:
                    sync_results['persona_maternidad']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                maternidad_to_delete.deleted_at = datetime.datetime.now().date()
                maternidad_to_delete.updated_at = datetime.datetime.now().date()

                sync_results['persona_maternidad']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": maternidad_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_maternidad']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Procesar Cambios en aps_persona_practicas_salud_salud_sexual ---
    if 'persona_practicas_salud_salud_sexual' in changes:
        # Inserciones (CREATED)
        for item in changes['persona_practicas_salud_salud_sexual'].get('created', []):
            local_id = item.pop('id')
            item.pop('remote_id', None)
            mobile_last_modified_at = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            try:
                # Conversión de fechas
                item['created_at'] = datetime.datetime.fromisoformat(item['created_at']).date()
                item['updated_at'] = datetime.datetime.now().date()
                if 'fecha_proxima_vacunacion' in item and item['fecha_proxima_vacunacion']:
                    item['fecha_proxima_vacunacion'] = datetime.datetime.fromisoformat(item['fecha_proxima_vacunacion']).date()
                
                # Asegúrate de que aps_persona_id y aps_visita_id sean los remote_id de MySQL
                new_practica = ApsPersonaPracticasSaludSaludSexual(**item)
                db.session.add(new_practica)
                db.session.flush()

                sync_results['persona_practicas_salud_salud_sexual']['created'].append({
                    "local_id": local_id,
                    "remote_id": new_practica.id,
                    "new_last_modified_at": new_practica.updated_at.isoformat(),
                    "status": "success"
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_practicas_salud_salud_sexual']['created'].append({
                    "local_id": local_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Actualizaciones (UPDATED)
        for item in changes['persona_practicas_salud_salud_sexual'].get('updated', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)
            mobile_last_modified_at_str = item.pop('last_modified_at', None)
            item.pop('is_synced', None)
            item.pop('deleted_at', None)

            if not remote_id:
                sync_results['persona_practicas_salud_salud_sexual']['updated'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue

            try:
                practica_to_update = ApsPersonaPracticasSaludSaludSexual.query.get(remote_id)
                if not practica_to_update:
                    sync_results['persona_practicas_salud_salud_sexual']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server"})
                    continue

                mobile_ts = datetime.datetime.fromisoformat(mobile_last_modified_at_str).date() if mobile_last_modified_at_str else datetime.date.min
                server_ts = practica_to_update.updated_at

                # Si server_ts es None o '0000-00-00', conviértelo a datetime.date.min para evitar errores
                if not server_ts or str(server_ts) in ("0000-00-00", "None"):
                    server_ts = datetime.date.min
                elif not isinstance(server_ts, datetime.date):
                    try:
                        server_ts = server_ts.date()
                    except Exception:
                        server_ts = datetime.date.min

                if datetime.datetime.combine(mobile_ts, datetime.time()) > datetime.datetime.combine(server_ts, datetime.time()):
                    for key, value in item.items():
                        if hasattr(practica_to_update, key):
                            if 'created_at' in key or 'updated_at' in key:
                                setattr(practica_to_update, key, datetime.datetime.fromisoformat(value).date() if value else None)
                            else:
                                setattr(practica_to_update, key, value)
                    practica_to_update.updated_at = datetime.datetime.now().date()

                    sync_results['persona_practicas_salud_salud_sexual']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": practica_to_update.updated_at.isoformat(),
                        "status": "success",
                        "conflict_resolved": "LWW"
                    })
                else:
                    sync_results['persona_practicas_salud_salud_sexual']['updated'].append({
                        "local_id": local_id,
                        "remote_id": remote_id,
                        "new_last_modified_at": server_ts.isoformat(),
                        "status": "success",
                        "conflict_resolved": "skipped_older_mobile_version"
                    })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_practicas_salud_salud_sexual']['updated'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

        # Eliminaciones (DELETED - Soft Delete)
        for item in changes['persona_practicas_salud_salud_sexual'].get('deleted', []):
            local_id = item.pop('id')
            remote_id = item.pop('remote_id', None)

            if not remote_id:
                sync_results['persona_practicas_salud_salud_sexual']['deleted'].append({"local_id": local_id, "status": "failed", "error": "No remote_id provided"})
                continue
            
            try:
                practica_to_delete = ApsPersonaPracticasSaludSaludSexual.query.get(remote_id)
                if not practica_to_delete:
                    sync_results['persona_practicas_salud_salud_sexual']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": "Record not found on server for deletion"})
                    continue

                practica_to_delete.deleted_at = datetime.datetime.now().date()
                practica_to_delete.updated_at = datetime.datetime.now().date()

                sync_results['persona_practicas_salud_salud_sexual']['deleted'].append({
                    "local_id": local_id,
                    "remote_id": remote_id,
                    "status": "success",
                    "action": "soft_deleted",
                    "new_last_modified_at": practica_to_delete.updated_at.isoformat()
                })
            except Exception as e:
                db.session.rollback()
                sync_results['persona_practicas_salud_salud_sexual']['deleted'].append({"local_id": local_id, "remote_id": remote_id, "status": "failed", "error": str(e)})

    # --- Commit final de todos los cambios de la sesión ---
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "Error al guardar cambios en la base de datos", "error": str(e)}), 500

    return jsonify({"message": "Sincronización de cambios procesada", "sync_results": sync_results}), 200