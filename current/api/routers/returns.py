from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from api.auth_dependencies import get_current_user, get_trade_db
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.models.goods import GoodsReturnCreate, GoodsReturnRefundCreate
from api import return_services as service

router = APIRouter(prefix='/api/goods', tags=['returns'])
Db = Annotated[object, Depends(get_trade_db)]
User = Annotated[UserInfo, Depends(get_current_user)]


@router.get('/return-sources/{kind}/{source_id}', response_model=ApiResponse)
def return_source(kind: Literal['customer', 'supplier'], source_id: int, connection: Db, user: User, exclude_id: int | None = None):
    return ApiResponse(data=service.return_source(connection, kind, source_id, exclude_id))


@router.get('/returns', response_model=ApiResponse)
def list_returns(connection: Db, user: User, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), kind: Literal['customer', 'supplier'] | None = None, search: str | None = None):
    items, pagination = service.list_returns(connection, page=page, page_size=page_size, kind=kind, search=search)
    return ApiResponse(data=items, pagination=pagination)


@router.post('/returns', response_model=ApiResponse, status_code=201)
def create_return(payload: GoodsReturnCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_return(connection, payload=payload.model_dump(), user=user))


@router.get('/returns/{document_id}', response_model=ApiResponse)
def get_return(document_id: int, connection: Db, user: User):
    return ApiResponse(data=service.get_return(connection, document_id))


@router.put('/returns/{document_id}', response_model=ApiResponse)
def update_return(document_id: int, payload: GoodsReturnCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_return(connection, payload=payload.model_dump(), document_id=document_id, user=user))


@router.delete('/returns/{document_id}', response_model=ApiResponse)
def delete_return(document_id: int, connection: Db, user: User):
    service.change_return(connection, document_id=document_id, user=user, action='delete')
    return ApiResponse(data={'id': document_id})


@router.post('/returns/{document_id}/{action}', response_model=ApiResponse)
def return_action(document_id: int, action: Literal['post', 'unpost'], connection: Db, user: User):
    service.change_return(connection, document_id=document_id, user=user, action=action)
    return ApiResponse(data=service.get_return(connection, document_id))


@router.get('/returns/{document_id}/movements', response_model=ApiResponse)
def return_movements(document_id: int, connection: Db, user: User):
    return ApiResponse(data=service.return_movements(connection, document_id))


@router.post('/return-refunds', response_model=ApiResponse, status_code=201)
def create_refund(payload: GoodsReturnRefundCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_refund(connection, payload=payload.model_dump(), user=user))


@router.get('/return-refunds/{refund_id}', response_model=ApiResponse)
def get_refund(refund_id: int, connection: Db, user: User):
    return ApiResponse(data=service.get_refund(connection, refund_id))


@router.put('/return-refunds/{refund_id}', response_model=ApiResponse)
def update_refund(refund_id: int, payload: GoodsReturnRefundCreate, connection: Db, user: User):
    return ApiResponse(data=service.save_refund(connection, payload=payload.model_dump(), refund_id=refund_id, user=user))


@router.delete('/return-refunds/{refund_id}', response_model=ApiResponse)
def delete_refund(refund_id: int, connection: Db, user: User):
    service.change_refund(connection, refund_id=refund_id, user=user, action='delete')
    return ApiResponse(data={'id': refund_id})


@router.post('/return-refunds/{refund_id}/{action}', response_model=ApiResponse)
def refund_action(refund_id: int, action: Literal['post', 'unpost'], connection: Db, user: User):
    service.change_refund(connection, refund_id=refund_id, user=user, action=action)
    return ApiResponse(data=service.get_refund(connection, refund_id))


@router.get('/return-refunds/{refund_id}/movements', response_model=ApiResponse)
def refund_movements(refund_id: int, connection: Db, user: User):
    doc = service.get_refund(connection, refund_id)
    return ApiResponse(data={'document': doc, **{name: service.rows_to_dicts(connection.execute(f"SELECT * FROM {table} WHERE recorder_type = 'goods_return_refund' AND recorder_id = ?", (refund_id,)).fetchall()) for name, table in (('settlements', 'mutual_settlements_register'), ('cash', 'payment_schedule_register'))}})
