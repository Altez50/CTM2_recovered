"""Administrator-managed roles and organization grants; never user settings."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from api.auth_dependencies import get_current_user, get_db
from api.database import last_insert_id, new_uuid
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.security import hash_password
from api.trade_access import read_organization_ids

router = APIRouter(prefix='/api/users', tags=['users'])
Db = Annotated[object, Depends(get_db)]
User = Annotated[UserInfo, Depends(get_current_user)]


class Access(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['admin', 'manager', 'foreman', 'viewer']
    organization_ids: list[int] | None = None


class CreateUser(Access):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)


def admin(user):
    if user.role != 'admin' or user.organization_ids is not None:
        raise HTTPException(status_code=403, detail='Настройка доступа требует администратора без ограничения организаций')


def grants(connection, user_id, payload):
    ids = sorted(set(payload.organization_ids or []))
    for ident in ids:
        if not connection.execute('SELECT id FROM organizations WHERE id = ? AND marked_for_deletion = 0 AND is_deleted = 0', (ident,)).fetchone():
            raise HTTPException(status_code=400, detail='Организация доступа не найдена')
    connection.execute('UPDATE users SET role = ?, organizations_restricted = ? WHERE id = ?',
                       (payload.role, int(payload.organization_ids is not None), user_id))
    connection.execute('DELETE FROM user_organizations WHERE user_id = ?', (user_id,))
    for ident in ids:
        connection.execute('INSERT INTO user_organizations (user_id, organization_id) VALUES (?, ?)', (user_id, ident))


def list_items(connection):
    return [dict(row) | {'is_active': bool(row['is_active']), 'organization_ids': read_organization_ids(connection, row['id'])}
            for row in connection.execute('SELECT id, username, role, is_active FROM users WHERE is_deleted = 0 ORDER BY username').fetchall()]


@router.get('', response_model=ApiResponse)
def list_users(connection: Db, user: User):
    admin(user)
    return ApiResponse(data=list_items(connection))


@router.post('', response_model=ApiResponse, status_code=201)
def create_user(payload: CreateUser, connection: Db, user: User):
    admin(user)
    if connection.execute('SELECT id FROM users WHERE username = ?', (payload.username,)).fetchone():
        raise HTTPException(status_code=400, detail='Имя пользователя уже используется')
    try:
        connection.execute('INSERT INTO users (username, password_hash, role, uuid) VALUES (?, ?, ?, ?)',
                           (payload.username, hash_password(payload.password), payload.role, new_uuid()))
        ident = last_insert_id(connection)
        grants(connection, ident, payload)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return ApiResponse(data=next(row for row in list_items(connection) if row['id'] == ident))


@router.put('/{ident}/access', response_model=ApiResponse)
def update_access(ident: int, payload: Access, connection: Db, user: User):
    admin(user)
    if ident == user.id:
        raise HTTPException(status_code=400, detail='Собственный доступ администратора изменять нельзя')
    if not connection.execute('SELECT id FROM users WHERE id = ? AND is_deleted = 0', (ident,)).fetchone():
        raise HTTPException(status_code=404, detail='Пользователь не найден')
    try:
        connection.execute('UPDATE users SET id = id WHERE id = ?', (ident,))
        # An omitted field changes only the role. Explicit null grants all
        # organizations; [] explicitly removes access to trade organizations.
        if 'organization_ids' not in payload.model_fields_set:
            payload = payload.model_copy(update={'organization_ids': read_organization_ids(connection, ident)})
        grants(connection, ident, payload)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return ApiResponse(data=next(row for row in list_items(connection) if row['id'] == ident))
