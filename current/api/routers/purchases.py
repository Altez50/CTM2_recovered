from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth_dependencies import get_current_user, get_trade_db
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.models.purchases import PurchaseKind, PurchaseOrderCreate, LinkedPurchaseCreate
from api import purchase_services as service

router = APIRouter(prefix='/api/purchases', tags=['purchases'])
Db = Annotated[object, Depends(get_trade_db)]
User = Annotated[UserInfo, Depends(get_current_user)]


@router.get('/expenses', response_model=ApiResponse)
def expenses(connection: Db, user: User, date_from: str = '0001-01-01', date_to: str = '9999-12-31'):
    return ApiResponse(data=service.expenses(connection, date_from, date_to))


@router.get('/{kind}', response_model=ApiResponse)
def list_items(kind: PurchaseKind, connection: Db, user: User, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    items, pagination = service.list_documents(connection, kind, page, page_size)
    return ApiResponse(data=items, pagination=pagination)


def checked_payload(kind, payload):
    if (kind == 'orders') != isinstance(payload, PurchaseOrderCreate):
        raise HTTPException(status_code=422, detail='Неверный формат закупочного документа')
    return payload.model_dump()


@router.post('/{kind}', response_model=ApiResponse, status_code=201)
def create(kind: PurchaseKind, payload: PurchaseOrderCreate | LinkedPurchaseCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_document(connection, kind, checked_payload(kind, payload), user))


@router.get('/{kind}/{ident}', response_model=ApiResponse)
def get(kind: PurchaseKind, ident: int, connection: Db, user: User):
    return ApiResponse(data=service.get_document(connection, ident, kind))


@router.put('/{kind}/{ident}', response_model=ApiResponse)
def update(kind: PurchaseKind, ident: int, payload: PurchaseOrderCreate | LinkedPurchaseCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_document(connection, kind, checked_payload(kind, payload), user, ident))


@router.delete('/{kind}/{ident}', response_model=ApiResponse)
def delete(kind: PurchaseKind, ident: int, connection: Db, user: User):
    return ApiResponse(data=service.change_document(connection, ident, kind, 'delete', user))


@router.post('/{kind}/{ident}/{action}', response_model=ApiResponse)
def change(kind: PurchaseKind, ident: int, action: Literal['post', 'unpost'], connection: Db, user: User):
    return ApiResponse(data=service.change_document(connection, ident, kind, action, user))


@router.get('/{kind}/{ident}/movements', response_model=ApiResponse)
def movements(kind: PurchaseKind, ident: int, connection: Db, user: User):
    return ApiResponse(data=service.movements(connection, ident, kind))
