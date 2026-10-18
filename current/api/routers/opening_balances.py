from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from api.auth_dependencies import get_current_user, get_trade_db
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.models.opening_balances import OpeningBalanceCreate
from api import opening_balance_services as service

router = APIRouter(prefix='/api/goods', tags=['opening-balances'])
Db = Annotated[object, Depends(get_trade_db)]
User = Annotated[UserInfo, Depends(get_current_user)]


@router.get('/opening-balances', response_model=ApiResponse)
def list_openings(connection: Db, user: User, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    items, pagination = service.list_openings(connection, page, page_size)
    return ApiResponse(data=items, pagination=pagination)


@router.post('/opening-balances', response_model=ApiResponse, status_code=201)
def create(payload: OpeningBalanceCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_opening(connection, payload.model_dump(), user))


@router.get('/opening-balances/{ident}', response_model=ApiResponse)
def get(ident: int, connection: Db, user: User):
    return ApiResponse(data=service.get_opening(connection, ident))


@router.put('/opening-balances/{ident}', response_model=ApiResponse)
def update(ident: int, payload: OpeningBalanceCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_opening(connection, payload.model_dump(), user, ident))


@router.delete('/opening-balances/{ident}', response_model=ApiResponse)
def delete(ident: int, connection: Db, user: User):
    service.change_opening(connection, ident, user, 'delete')
    return ApiResponse(data={'id': ident})


@router.post('/opening-balances/{ident}/{action}', response_model=ApiResponse)
def change(ident: int, action: Literal['post', 'unpost'], connection: Db, user: User):
    service.change_opening(connection, ident, user, action)
    return ApiResponse(data=service.get_opening(connection, ident))


@router.get('/opening-balances/{ident}/movements', response_model=ApiResponse)
def movements(ident: int, connection: Db, user: User):
    return ApiResponse(data=service.opening_movements(connection, ident))


@router.get('/inventory/turnover', response_model=ApiResponse)
def turnover(connection: Db, user: User, date_from: str, date_to: str, organization_id: int | None = None,
             warehouse_id: int | None = None, object_id: int | None = None, material_id: int | None = None,
             characteristic_id: int | None = None, series_id: int | None = None):
    return ApiResponse(data=service.inventory_turnover(connection, date_from, date_to,
        organization_id=organization_id, warehouse_id=warehouse_id, object_id=object_id, material_id=material_id,
        characteristic_id=characteristic_id, series_id=series_id))
