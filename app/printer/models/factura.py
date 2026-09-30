from typing import List, Optional
from pydantic import BaseModel, Field

class ItemFactura(BaseModel):
    cantidad: float
    descripcion: str
    sku: Optional[str] = None
    imeis: Optional[List[str]] = None
    precio_unitario: Optional[float] = None
    total: float

class FacturaPrintRequest(BaseModel):
    tipo_documento: str = Field("FACTURA", description="FACTURA o RECIBO")
    numero_factura: str
    fecha_emision: str
    ruc_emisor: str
    nombre_comercial: str
    razon_social_emisor: str
    direccion: str
    obligado_contabilidad: str = "NO"
    regimen: str = "Contribuyente Régimen General"
    emision: str = "NORMAL"
    ambiente: str = "PRUEBAS"
    estado: str = "AUTORIZADO"
    fecha_autorizacion: str
    clave_acceso: str
    
    cliente_nombre: str
    cliente_identificacion: str
    
    # IMEIs o detalles adicionales globales
    imeis_globales: Optional[List[str]] = None
    extra_details: Optional[str] = None
    
    items: List[ItemFactura]
    subtotal: float
    iva: float
    total: float
    forma_pago: str = "SIN UTILIZACION DEL SISTEMA FINANCIERO"