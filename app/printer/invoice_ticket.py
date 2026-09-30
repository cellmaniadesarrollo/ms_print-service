def print_invoice_ticket(printer, req: dict, config):
    """
    Renderiza la factura o recibo fiscal usando comandos ESC/POS.
    """
    p = printer
    ancho = getattr(config.ticket, 'paper_width_chars', 48)

    tipo_doc = str(req.get("tipo_documento", "FACTURA")).upper()
    num_factura = req.get("numero_factura", "000-000-000000000")
    
    # 1. Encabezado
    p.set(align='center', text_type='B', width=2, height=2)
    p.text(f"{tipo_doc}\n")
    p.set(align='center', text_type='NORMAL', width=1, height=1)
    p.text(f"Nº: {num_factura}\n")
    p.text("-" * ancho + "\n")

    # 2. Emisor / Datos Fiscales
    p.set(align='left')
    p.text(f"Fecha: {req.get('fecha_emision', '')}   RUC: {req.get('ruc_emisor', '')}\n")
    if req.get("nombre_comercial"):
        p.text(f"Comercial: {req.get('nombre_comercial')}\n")
    if req.get("direccion"):
        p.text(f"Matriz: {req.get('direccion')}\n")
    p.text(f"Obligado Contabilidad: {req.get('obligado_contabilidad', 'NO')}\n")
    p.text(f"{req.get('regimen', 'Contribuyente Régimen General')}\n")
    p.text(f"Emisión: {req.get('emision', 'NORMAL')} | Ambiente: {req.get('ambiente', 'PRUEBAS')}\n")

    if tipo_doc == "FACTURA":
        if req.get("estado"):
            p.text(f"Estado: {req.get('estado')}\n")
        if req.get("fecha_autorizacion"):
            p.text(f"F. Aut: {req.get('fecha_autorizacion')}\n")
        if req.get("clave_acceso"):
            p.text("Clave de Acceso:\n")
            p.text(f"{req.get('clave_acceso')}\n")

    p.text("-" * ancho + "\n")

    # 3. Cliente
    p.set(align='center', text_type='B')
    p.text("INFORMACION DEL CLIENTE\n")
    p.set(align='left', text_type='NORMAL')
    p.text(f"Cliente: {req.get('cliente_nombre', 'CONSUMIDOR FINAL')}\n")
    p.text(f"RUC/CI: {req.get('cliente_identificacion', '9999999999999')}\n")

    imeis_globales = req.get("imeis_globales", [])
    if imeis_globales:
        for imei in imeis_globales:
            p.text(f"  * IMEI: {imei}\n")
            
    extra_details = req.get("extra_details", "")
    if extra_details and str(extra_details).strip() not in ["", "N/A"]:
        p.text(f"Detalles: {extra_details}\n")

    p.text("-" * ancho + "\n")

    # 4. Detalle de Items
    p.set(align='center', text_type='B')
    p.text("DETALLES DE PRODUCTOS\n")
    p.set(align='left', text_type='NORMAL')
    p.text(f"{'Cant':<5}{'Descripcion':<31}{'Total':>12}\n")
    p.text("-" * ancho + "\n")

    items = req.get("items", [])
    for item in items:
        cant = item.get("cantidad", 1)
        cant_str = f"{cant:g}" if isinstance(cant, (int, float)) and cant % 1 == 0 else f"{cant:.2f}"
        desc = str(item.get("descripcion", ""))[:30]
        total_item = float(item.get("total", 0.0))
        
        p.text(f"{cant_str:<5}{desc:<31}${total_item:>11.2f}\n")

        if item.get("sku"):
            p.text(f"     [SKU: {item.get('sku')}]\n")
        if item.get("imeis"):
            for imei in item.get("imeis", []):
                p.text(f"     IMEI: {imei}\n")

    p.text("-" * ancho + "\n")

    # 5. Totales
    subtotal = float(req.get("subtotal", 0.0))
    iva = float(req.get("iva", 0.0))
    total = float(req.get("total", 0.0))

    p.set(align='right')
    p.text(f"Subtotal: ${subtotal:.2f}\n")
    p.text(f"IVA: ${iva:.2f}\n")
    p.set(align='right', text_type='B', width=1, height=2)
    p.text(f"TOTAL: ${total:.2f}\n")
    p.set(align='left', text_type='NORMAL', width=1, height=1)
    p.text(f"Forma de Pago: {req.get('forma_pago', 'SIN UTILIZACION DEL SISTEMA FINANCIERO')}\n")
    p.text("-" * ancho + "\n")

    # 6. Pie y QR
    p.set(align='center', text_type='B')
    p.text("¡Gracias por su compra!\n")
    p.set(align='center', text_type='NORMAL')
    p.text("Consulta tu comprobante en la web\n\n")

    clave = req.get("clave_acceso")
    if clave:
        try:
            p.qr(clave, size=5)
        except Exception:
            pass

    p.text("\n\n")
    p.cut()