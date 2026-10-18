from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from api.auth_dependencies import get_current_user, get_trade_db
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.models.sales import SalesKind, SalesOrderCreate, LinkedSaleCreate
from api import sales_services as service

router=APIRouter(prefix='/api/sales',tags=['sales'])
Db=Annotated[object,Depends(get_trade_db)]
User=Annotated[UserInfo,Depends(get_current_user)]


@router.get('/reserves',response_model=ApiResponse)
def reserves(connection:Db,user:User,date:str='9999-12-31'):
    return ApiResponse(data=service.reserves(connection,date))


@router.get('/revenue',response_model=ApiResponse)
def revenue(connection:Db,user:User,date_from:str='0001-01-01',date_to:str='9999-12-31'):
    return ApiResponse(data=service.revenue(connection,date_from,date_to))


@router.get('/{kind}',response_model=ApiResponse)
def list_items(kind:SalesKind,connection:Db,user:User,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    items,pagination=service.list_documents(connection,kind,page,page_size)
    return ApiResponse(data=items,pagination=pagination)


def payload_for(kind,payload):
    if (kind=='orders')!=isinstance(payload,SalesOrderCreate):
        raise HTTPException(status_code=422,detail='Неверный формат продажи')
    return payload.model_dump()


@router.post('/{kind}',response_model=ApiResponse,status_code=201)
def create(kind:SalesKind,payload:SalesOrderCreate|LinkedSaleCreate,connection:Db,user:User):
    return ApiResponse(data=service.save_document(connection,kind,payload_for(kind,payload),user))


@router.get('/{kind}/{ident}',response_model=ApiResponse)
def get(kind:SalesKind,ident:int,connection:Db,user:User):
    return ApiResponse(data=service.get_document(connection,ident,kind))


@router.put('/{kind}/{ident}',response_model=ApiResponse)
def update(kind:SalesKind,ident:int,payload:SalesOrderCreate|LinkedSaleCreate,connection:Db,user:User):
    return ApiResponse(data=service.save_document(connection,kind,payload_for(kind,payload),user,ident))


@router.delete('/{kind}/{ident}',response_model=ApiResponse)
def delete(kind:SalesKind,ident:int,connection:Db,user:User):
    return ApiResponse(data=service.change_document(connection,ident,kind,'delete',user))


@router.post('/{kind}/{ident}/{action}',response_model=ApiResponse)
def change(kind:SalesKind,ident:int,action:Literal['post','unpost'],connection:Db,user:User):
    return ApiResponse(data=service.change_document(connection,ident,kind,action,user))


@router.get('/{kind}/{ident}/movements',response_model=ApiResponse)
def movements(kind:SalesKind,ident:int,connection:Db,user:User):
    return ApiResponse(data=service.movements(connection,ident,kind))
