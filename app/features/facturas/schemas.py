"""
Schemas for factura processing.
"""
from typing import List, Optional
from pydantic import BaseModel


class ProductoExtracted(BaseModel):
    """Product extracted from XML."""
    codigo: str
    descripcion: str
    cantidad: float
    codigo_barras: Optional[str] = None


class ExtractProductsResponse(BaseModel):
    """Response for extract products endpoint."""
    success: bool
    productos: List[ProductoExtracted]
    total_facturas: int
    total_productos: int
    message: str
