# app/sync/utils.py
from app.models import db, ApsCueOpcion,ApsPersona, ApsPersonaEstilosVidaConducta # Importa los modelos necesarios
from sqlalchemy import func # Necesario para algunas queries de SQLAlchemy

def calculate_total_updated_fields_for_family_ficha(aps_ficha_familia_id):
    """
    Calcula el total de campos actualizados para una ficha familiar,
    sumando 'cantidad_campos_cambiados' para las personas de la familia
    que tienen más de una versión en el historial de 'aps_persona' (indicando una actualización).

    Args:
        aps_ficha_familia_id (int): El ID de la ficha familiar para la cual se calcularán los campos actualizados.

    Returns:
        int or str: La suma total de 'cantidad_campos_cambiados' si se encuentran
                    personas actualizadas, de lo contrario, 'N/A'.
    """
    total_campos_cambiados = 0
    hay_actualizaciones = False

    # 1. Obtener todas las personas (solo las versiones VIGENTES) asociadas a esta ficha familiar.
    # Usamos outerjoin para asegurar que incluso si una persona no tiene un registro
    # de EstilosVidaConducta, la incluimos en el resultado.
    persons_and_estilos = db.session.query(
        ApsPersona, ApsPersonaEstilosVidaConducta
    ).outerjoin(
        ApsPersonaEstilosVidaConducta,
        ApsPersona.id == ApsPersonaEstilosVidaConducta.aps_persona_id
    ).filter(
        ApsPersona.aps_ficha_familia_id == aps_ficha_familia_id,
        ApsPersona.vigencia_registro == True # Filtra solo por la versión vigente de la persona
    ).all()

    if not persons_and_estilos:
        # Si no hay personas vigentes asociadas a esta ficha familiar, no hay nada que contar.
        return 'N/A'

    for persona, estilo_vida_conducta in persons_and_estilos:
        # 2. Verificar si esta persona (por su numero_documento) tiene un historial de actualizaciones.
        # Esto se hace contando cuántos registros existen para su numero_documento en la tabla aps_persona.
        # Si count > 1, significa que ha habido al menos una actualización que creó una nueva versión.
        cantidad_versiones_persona = ApsPersona.query.filter(
            ApsPersona.numero_documento == persona.numero_documento
        ).count()

        if cantidad_versiones_persona > 1:
            hay_actualizaciones = True
            # 3. Sumar 'cantidad_campos_cambiados' de su registro de estilo de vida y conducta actual.
            # Solo sumamos si el registro de estilo de vida existe y el campo no es None.
            if estilo_vida_conducta and estilo_vida_conducta.cantidad_campos_cambiados is not None:
                total_campos_cambiados += estilo_vida_conducta.cantidad_campos_cambiados

    # 4. Retornar el contador o 'N/A' según si hubo actualizaciones
    return total_campos_cambiados if hay_actualizaciones else 'N/A'


def get_descriptions_from_comma_separated_ids(ids_string):
    """
    Toma una cadena de IDs separados por comas y devuelve una lista de sus descripciones
    desde la tabla aps_cue_opcion.
    """
    if not ids_string:
        return []

    try:
        # Convertir la cadena '1,2,3' a una lista de enteros [1, 2, 3]
        ids = [int(i.strip()) for i in ids_string.split(',') if i.strip().isdigit()]
    except ValueError:
        return [] # Retorna vacío si la cadena no es un formato de IDs válido

    if not ids:
        return []

    # Consultar la base de datos para obtener las descripciones de esos IDs
    descriptions = ApsCueOpcion.query.filter(ApsCueOpcion.id.in_(ids)).all()
    return [d.descripcion for d in descriptions]