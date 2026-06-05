"""
Corrector de precios de sucursal vs matriz.

Lee productos de la Odoo MATRIZ usando el código de barras como identificador
y actualiza en la Odoo SUCURSAL los campos:
  - list_price     (precio de venta)
  - standard_price (costo)

Uso:
    python fix_branch_prices.py              # modo real (pide confirmación)
    python fix_branch_prices.py --dry-run    # sin escribir nada
    python fix_branch_prices.py --pdf out.pdf  # reporte custom

Requiere: Python 3.8+, reportlab (pip install reportlab).
"""

from __future__ import annotations

import argparse
import getpass
import sys
import xmlrpc.client
from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
    )
except ImportError:
    print("ERROR: falta 'reportlab'. Instálalo con:\n    pip install reportlab")
    sys.exit(1)


@dataclass
class OdooConn:
    url: str
    db: str
    username: str
    password: str
    uid: int
    models: xmlrpc.client.ServerProxy

    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, list(args), kwargs or {}
        )


def prompt_credentials(label: str) -> OdooConn:
    print(f"\n=== Credenciales Odoo {label} ===")
    url = input(f"URL (ej: https://matriz.miempresa.com): ").strip().rstrip("/")
    db = input("Base de datos: ").strip()
    username = input("Usuario/email: ").strip()
    password = getpass.getpass("Contraseña: ")

    if not (url and db and username and password):
        print(f"ERROR: faltan datos de {label}.")
        sys.exit(1)

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    try:
        uid = common.authenticate(db, username, password, {})
    except Exception as e:
        print(f"ERROR al conectar a {label} ({url}): {e}")
        sys.exit(1)
    if not uid:
        print(f"ERROR: credenciales inválidas para {label}.")
        sys.exit(1)

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    print(f"  OK - conectado a {label} como uid={uid}")
    return OdooConn(url=url, db=db, username=username, password=password, uid=uid, models=models)


def fetch_products_by_barcode(conn: OdooConn, label: str) -> dict[str, dict]:
    """Devuelve {barcode: {id, name, list_price, standard_price}}"""
    print(f"\nLeyendo productos de {label}...")
    domain = [("barcode", "!=", False)]
    fields = ["id", "name", "default_code", "barcode", "list_price", "standard_price"]
    records = conn.execute("product.product", "search_read", domain, fields=fields)
    by_barcode: dict[str, dict] = {}
    dupes = 0
    for r in records:
        bc = (r.get("barcode") or "").strip()
        if not bc:
            continue
        if bc in by_barcode:
            dupes += 1
            continue
        by_barcode[bc] = r
    print(f"  {len(by_barcode)} productos con barcode único ({dupes} duplicados ignorados) en {label}")
    return by_barcode


def _row_from_plan(p: dict, status: str, error: str = "", applied: bool = False) -> dict:
    after_list = p["after_list"] if applied or status == "PLANNED" else p["old_list"]
    after_cost = p["after_cost"] if applied or status == "PLANNED" else p["old_cost"]
    return {
        "barcode": p["bc"],
        "status": status,
        "matriz_name": p["matriz_name"],
        "matriz_list_price": p["new_list"],
        "matriz_standard_price": p["new_cost"],
        "branch_id": p["id"],
        "branch_name": p["name"],
        "branch_list_price_before": p["old_list"],
        "branch_standard_price_before": p["old_cost"],
        "branch_list_price_after": after_list,
        "branch_standard_price_after": after_cost,
        "error": error,
    }


STATUS_COLORS = {
    "PLANNED":       colors.HexColor("#E3F2FD"),
    "UPDATED":       colors.HexColor("#C8E6C9"),
    "ERROR":         colors.HexColor("#FFCDD2"),
    "NOT_IN_BRANCH": colors.HexColor("#FFF9C4"),
}


def _fmt_money(val) -> str:
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return str(val or "")


def _write_pdf(
    path: str,
    title: str,
    matriz_url: str,
    sucursal_url: str,
    summary: dict,
    rows: list[dict],
) -> None:
    doc = SimpleDocTemplate(
        path,
        pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=7, leading=9)
    story: list = []

    story.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
    story.append(Paragraph(
        f"Generado: {datetime.now():%Y-%m-%d %H:%M:%S}", styles["Normal"]))
    story.append(Paragraph(f"<b>Matriz:</b> {matriz_url}", styles["Normal"]))
    story.append(Paragraph(f"<b>Sucursal:</b> {sucursal_url}", styles["Normal"]))
    story.append(Spacer(1, 6))

    # Resumen
    summary_rows = [["Concepto", "Cantidad"]]
    for k, v in summary.items():
        summary_rows.append([k, str(v)])
    t = Table(summary_rows, hAlign="LEFT", colWidths=[70 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1976D2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # Tabla detallada
    headers = ["Barcode", "Status", "Producto",
               "Venta antes", "Venta después",
               "Costo antes", "Costo después", "Error"]
    data: list = [headers]
    row_styles: list = []

    for i, r in enumerate(rows, start=1):
        name = (r.get("branch_name") or r.get("matriz_name") or "")
        data.append([
            Paragraph(str(r.get("barcode") or ""), small),
            r.get("status", ""),
            Paragraph(name, small),
            _fmt_money(r.get("branch_list_price_before")),
            _fmt_money(r.get("branch_list_price_after")),
            _fmt_money(r.get("branch_standard_price_before")),
            _fmt_money(r.get("branch_standard_price_after")),
            Paragraph(str(r.get("error") or ""), small),
        ])
        bg = STATUS_COLORS.get(r.get("status", ""))
        if bg:
            row_styles.append(("BACKGROUND", (0, i), (-1, i), bg))

    col_widths = [28 * mm, 22 * mm, 65 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 55 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    base_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1976D2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 1), (6, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]
    table.setStyle(TableStyle(base_style + row_styles))
    story.append(table)

    doc.build(story)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza precios de sucursal con matriz usando barcode.")
    parser.add_argument("--dry-run", action="store_true", help="No escribe cambios, solo reporta.")
    parser.add_argument(
        "--pdf",
        default=f"fix_branch_prices_{datetime.now():%Y%m%d_%H%M%S}.pdf",
        help="Ruta del reporte PDF (default: timestamp).",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.001,
        help="Diferencia mínima para considerar actualización (default 0.001).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Corrector de precios: MATRIZ -> SUCURSAL (por barcode)")
    print("=" * 60)
    if args.dry_run:
        print(">>> MODO DRY-RUN: no se escribirá nada en la sucursal <<<")

    matriz = prompt_credentials("MATRIZ (origen)")
    sucursal = prompt_credentials("SUCURSAL (destino)")

    matriz_by_bc = fetch_products_by_barcode(matriz, "MATRIZ")
    sucursal_by_bc = fetch_products_by_barcode(sucursal, "SUCURSAL")

    if not matriz_by_bc:
        print("ERROR: matriz no tiene productos con barcode.")
        return 1

    # ---------- FASE 1: VALIDACIÓN / PLAN ----------
    rows: list[dict] = []
    planned: list[dict] = []  # cambios a aplicar: {id, vals, bc, name, old_list, old_cost, new_list, new_cost}
    skipped_equal = 0
    not_found = 0

    print("\n[FASE 1] Validando y construyendo plan de cambios...")
    for bc, m in matriz_by_bc.items():
        s = sucursal_by_bc.get(bc)
        if not s:
            not_found += 1
            rows.append({
                "barcode": bc,
                "status": "NOT_IN_BRANCH",
                "matriz_name": m.get("name"),
                "matriz_list_price": m.get("list_price"),
                "matriz_standard_price": m.get("standard_price"),
                "branch_id": "",
                "branch_name": "",
                "branch_list_price_before": "",
                "branch_standard_price_before": "",
                "branch_list_price_after": "",
                "branch_standard_price_after": "",
                "error": "",
            })
            continue

        new_list = float(m.get("list_price") or 0.0)
        new_cost = float(m.get("standard_price") or 0.0)
        old_list = float(s.get("list_price") or 0.0)
        old_cost = float(s.get("standard_price") or 0.0)

        list_changed = abs(new_list - old_list) > args.tolerance
        cost_changed = abs(new_cost - old_cost) > args.tolerance

        if not list_changed and not cost_changed:
            skipped_equal += 1
            continue

        vals: dict[str, float] = {}
        if list_changed:
            vals["list_price"] = new_list
        if cost_changed:
            vals["standard_price"] = new_cost

        after_list = new_list if list_changed else old_list
        after_cost = new_cost if cost_changed else old_cost

        planned.append({
            "id": s["id"],
            "vals": vals,
            "bc": bc,
            "name": s.get("name") or m.get("name"),
            "matriz_name": m.get("name"),
            "old_list": old_list,
            "old_cost": old_cost,
            "new_list": new_list,
            "new_cost": new_cost,
            "after_list": after_list,
            "after_cost": after_cost,
        })

    # Resumen del plan
    print("\n" + "=" * 60)
    print("PLAN DE CAMBIOS (aún no se ha escrito nada)")
    print("=" * 60)
    print(f"  Productos en matriz (con barcode):   {len(matriz_by_bc)}")
    print(f"  Productos en sucursal (con barcode): {len(sucursal_by_bc)}")
    print(f"  A actualizar:                        {len(planned)}")
    print(f"  Sin cambios (precios iguales):       {skipped_equal}")
    print(f"  No existen en sucursal:              {not_found}")

    # Preview de los primeros N
    preview_n = min(10, len(planned))
    if preview_n:
        print(f"\n  Primeros {preview_n} cambios:")
        print(f"  {'BARCODE':<18} {'NOMBRE':<35} {'VENTA':>18} {'COSTO':>18}")
        for p in planned[:preview_n]:
            name = (p["name"] or "")[:33]
            venta = f"{p['old_list']:.2f} -> {p['new_list']:.2f}" if "list_price" in p["vals"] else "(sin cambio)"
            costo = f"{p['old_cost']:.2f} -> {p['new_cost']:.2f}" if "standard_price" in p["vals"] else "(sin cambio)"
            print(f"  {p['bc']:<18} {name:<35} {venta:>18} {costo:>18}")
        if len(planned) > preview_n:
            print(f"  ... y {len(planned) - preview_n} más (ver CSV).")

    # Guardar PDF del plan ANTES de escribir
    plan_pdf = args.pdf.replace(".pdf", "_plan.pdf") if args.pdf.endswith(".pdf") else args.pdf + "_plan.pdf"
    plan_summary = {
        "Productos en matriz (con barcode)": len(matriz_by_bc),
        "Productos en sucursal (con barcode)": len(sucursal_by_bc),
        "A actualizar": len(planned),
        "Sin cambios (precios iguales)": skipped_equal,
        "No existen en sucursal": not_found,
    }
    plan_rows = rows + [_row_from_plan(p, "PLANNED") for p in planned]
    _write_pdf(
        plan_pdf,
        "Plan de sincronización de precios (preview)",
        matriz.url, sucursal.url,
        plan_summary, plan_rows,
    )
    print(f"\n  Plan guardado en: {plan_pdf}")

    if args.dry_run:
        print("\n>>> DRY-RUN: no se escribirá nada. Revisa el PDF del plan. <<<")
        return 0

    if not planned:
        print("\nNo hay cambios por aplicar. Saliendo.")
        return 0

    # ---------- CONFIRMACIÓN ----------
    print("\n" + "=" * 60)
    prompt = f"¿Aplicar {len(planned)} cambios en SUCURSAL ({sucursal.url})? Escribe 'SI' para confirmar: "
    answer = input(prompt).strip()
    if answer != "SI":
        print("Cancelado por el usuario. No se escribió nada.")
        return 0

    # ---------- FASE 2: APLICACIÓN ----------
    print("\n[FASE 2] Aplicando cambios...")
    applied = 0
    errors = 0
    for p in planned:
        status = "UPDATED"
        error_msg = ""
        try:
            sucursal.execute("product.product", "write", [p["id"]], p["vals"])
            applied += 1
        except Exception as e:
            status = "ERROR"
            error_msg = str(e)[:300]
            errors += 1

        rows.append(_row_from_plan(p, status, error=error_msg, applied=(status == "UPDATED")))

        if applied and applied % 50 == 0:
            print(f"  ... aplicados {applied}/{len(planned)}")

    # PDF final
    final_summary = {
        "Planificados": len(planned),
        "Aplicados OK": applied,
        "Errores": errors,
        "No existen en sucursal": not_found,
    }
    _write_pdf(
        args.pdf,
        "Resultado de sincronización de precios",
        matriz.url, sucursal.url,
        final_summary, rows,
    )

    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    print(f"  Planificados:   {len(planned)}")
    print(f"  Aplicados OK:   {applied}")
    print(f"  Errores:        {errors}")
    print(f"  No en sucursal: {not_found}")
    print(f"  Reporte PDF:    {args.pdf}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
