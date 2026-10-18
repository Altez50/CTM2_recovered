from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from api.auth_dependencies import get_current_user, get_trade_db
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.models.goods import GoodsPriceAdjustmentCreate
from api import price_adjustment_services as service

router = APIRouter(prefix='/api/goods', tags=['price-adjustments'])
Db = Annotated[object, Depends(get_trade_db)]
User = Annotated[UserInfo, Depends(get_current_user)]


@router.get('/price-adjustment-sources/{kind}/{source_id}', response_model=ApiResponse)
def source(kind: Literal['sale', 'purchase'], source_id: int, connection: Db, user: User, exclude_id: int | None = None):
    return ApiResponse(data=service.get_source(connection, kind, source_id, exclude_id))


@router.get('/price-adjustments', response_model=ApiResponse)
def list_adjustments(connection: Db, user: User, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), kind: Literal['sale', 'purchase'] | None = None, search: str | None = None):
    items, pagination = service.list_adjustments(connection, page=page, page_size=page_size, kind=kind, search=search)
    return ApiResponse(data=items, pagination=pagination)


@router.post('/price-adjustments', response_model=ApiResponse, status_code=201)
def create_adjustment(payload: GoodsPriceAdjustmentCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_adjustment(connection, payload=payload.model_dump(), user=user))


@router.get('/price-adjustments/{adjustment_id}', response_model=ApiResponse)
def get_adjustment(adjustment_id: int, connection: Db, user: User):
    return ApiResponse(data=service.get_adjustment(connection, adjustment_id))


@router.put('/price-adjustments/{adjustment_id}', response_model=ApiResponse)
def update_adjustment(adjustment_id: int, payload: GoodsPriceAdjustmentCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_adjustment(connection, payload=payload.model_dump(), user=user, adjustment_id=adjustment_id))


@router.delete('/price-adjustments/{adjustment_id}', response_model=ApiResponse)
def delete_adjustment(adjustment_id: int, connection: Db, user: User):
    service.change_adjustment(connection, adjustment_id=adjustment_id, user=user, action='delete')
    return ApiResponse(data={'id': adjustment_id})


@router.post('/price-adjustments/{adjustment_id}/{action}', response_model=ApiResponse)
def change_adjustment(adjustment_id: int, action: Literal['post', 'unpost'], connection: Db, user: User):
    service.change_adjustment(connection, adjustment_id=adjustment_id, user=user, action=action)
    return ApiResponse(data=service.get_adjustment(connection, adjustment_id))


@router.get('/price-adjustments/{adjustment_id}/movements', response_model=ApiResponse)
def movements(adjustment_id: int, connection: Db, user: User):
    return ApiResponse(data=service.adjustment_movements(connection, adjustment_id))
