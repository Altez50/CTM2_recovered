"""Orders snapshot dimensions; all dependent sales accept exact source lines."""
from typing import Literal
from api.models.purchases import PurchaseOrderCreate, LinkedPurchaseCreate

SalesKind=Literal['orders','realizations','expense-orders','cancellations']


class SalesOrderCreate(PurchaseOrderCreate):
    pass


class LinkedSaleCreate(LinkedPurchaseCreate):
    pass
