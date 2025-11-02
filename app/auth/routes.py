# app/auth/routes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import check_password_hash
import bcrypt # Asegúrate de importar bcrypt aquí también
from app.models import db, jwt, User, AuthOficina, ComProfesion, AuthItem, AuthAssignment

import datetime

auth_bp = Blueprint('auth_bp', __name__, url_prefix='/api/v1/auth')

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    # En un entorno real, buscarías el usuario en tu DB MySQL:
    user = User.query.filter_by(username=identity).first()
    
    # Validar que el usuario exista y esté activo (estado=1)
    if user and user.estado == 1:
        return user
    
    # Si el usuario no existe o está inactivo, retornar None
    # Esto hará que JWT lance un error de token inválido
    return None

# --- Funciones para manejar tokens (se mantienen igual) ---
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_data):
    return jsonify({"message": "El token ha expirado", "error": "token_expired"}), 401

# Función para manejar tokens inválidos
@jwt.invalid_token_loader
def invalid_token_callback(callback):
    return jsonify({"message": "Firma del token inválida", "error": "invalid_token"}), 401

# Función para manejar tokens ausentes
@jwt.unauthorized_loader
def unauthorized_callback(callback):
    return jsonify({"message": "Solicitud sin token de acceso", "error": "authorization_required"}), 401

# --- Endpoints de la API ---

# --- Endpoint de Login ---
@auth_bp.route("/login", methods=["POST"])
def login():
    username = request.json.get("username", None)
    password = request.json.get("password", None)

    # Autenticación contra la tabla 'user' de MySQL
    user = User.query.filter_by(username=username).first()
    
    # Validación de usuario existente
    if not user:
        return jsonify({
            "success": False,
            "message": "Usuario o contraseña inválidos",
            "data": None
        }), 401
    
    # Validación de estado del usuario (1=activo, 0=inactivo)
    if user.estado != 1:
        return jsonify({
            "success": False,
            "message": "Usuario inactivo. Contacte al administrador",
            "data": None
        }), 403
    
    # Verificar contraseña
    if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return jsonify({
            "success": False,
            "message": "Usuario o contraseña inválidos",
            "data": None
        }), 401

    # Crear token de acceso
    access_token = create_access_token(identity=user.username)
    
    # Calcular fecha de expiración del token
    from app.config import Config
    expires_at = datetime.datetime.utcnow() + Config.JWT_ACCESS_TOKEN_EXPIRES
    
    # Obtener información de profesión
    profesion_data = None
    if user.com_profesion:
        profesion = ComProfesion.query.get(user.com_profesion)
        if profesion:
            profesion_data = {
                "id": profesion.id,
                "remote_id": profesion.id,
                "tipo": profesion.tipo,
                "descripcion": profesion.tipo,  # Usando tipo como descripción
                "grupo": profesion.grupo,
                "estado": profesion.estado
            }
    
    # Obtener información de oficina
    oficina_data = None
    if user.auth_oficina:
        oficina = AuthOficina.query.get(user.auth_oficina)
        if oficina:
            oficina_data = {
                "id": oficina.id,
                "remote_id": oficina.id,
                "nombre": oficina.nombre,
                "descripcion": oficina.nombre,  # Usando nombre como descripción
                "estado": oficina.estado
            }
    
    # Obtener permisos del usuario
    permisos = []
    user_assignments = AuthAssignment.query.filter_by(user_id=user.id).all()
    for assignment in user_assignments:
        permisos.append(assignment.item_name)
    
    # Construir respuesta según el esquema requerido
    response_data = {
        "success": True,
        "message": "Login exitoso",
        "data": {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "documento": user.documento,
                "nombres": user.name,  # Usando el campo 'name' como nombres
                "apellidos": "",  # El modelo User no tiene apellidos separados
                "estado": user.estado,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None
            },
            "profesion": profesion_data,
            "oficina": oficina_data,
            "permisos": permisos,
            "token": access_token,
            "expires_at": expires_at.isoformat()
        }
    }
    
    return jsonify(response_data), 200

# Endpoint protegido (requiere JWT)
@auth_bp.route("/protected", methods=["GET"])
@jwt_required()
def protected():
    # Accede a la identidad del usuario actual con get_jwt_identity
    current_user_identity = get_jwt_identity()
    user = User.query.filter_by(username=current_user_identity).first() # Obtener el objeto User completo

    if not user:
        return jsonify({"message": "Usuario no encontrado"}), 404

    return jsonify({
        "message": "Acceso concedido a un recurso protegido",
        "logged_in_as": user.username,
        "user_office_id": user.auth_oficina # Retornamos el ID de la oficina para el filtrado
    }), 200
