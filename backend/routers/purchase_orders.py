import sqlite3
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_connection

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])


# ── Request schemas ──────────────────────────────────────────────────────────


class PurchaseOrderItemCreate(BaseModel):
    productId: str | None = None
    sku: str
    name: str | None = None
    quantity: int
    unitCost: float


class PurchaseOrderCreate(BaseModel):
    supplierId: str
    items: list[PurchaseOrderItemCreate]
    auto_receive_on_approve: bool = False


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fetch_po(conn: sqlite3.Connection, po_id: str) -> dict:
    po = conn.execute(
        """
        SELECT po.id, po.supplierId, s.name AS supplierName,
               po.createdAt, po.status, po.totalAmount
        FROM PurchaseOrder po
        JOIN Supplier s ON po.supplierId = s.id
        WHERE po.id = ?
        """,
        (po_id,),
    ).fetchone()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    items = conn.execute(
        """
        SELECT poi.id, poi.productId, poi.sku, poi.name, poi.quantity, poi.unitCost,
               ROUND(poi.quantity * poi.unitCost, 2) AS lineTotal
        FROM PurchaseOrderItem poi
        WHERE poi.purchaseOrderId = ?
        """,
        (po_id,),
    ).fetchall()
    return {**po, "items": items}


def _receive_po(conn: sqlite3.Connection, po_id: str) -> list[dict]:
    """Execute receive logic: update inventory, create products if needed."""
    items = conn.execute(
        "SELECT id, productId, sku, name, quantity, unitCost FROM PurchaseOrderItem WHERE purchaseOrderId = ?",
        (po_id,),
    ).fetchall()

    now = datetime.utcnow().isoformat()
    inventory_changes = []

    for item in items:
        product_id = item["productId"]

        if product_id is None:
            # Try to find existing product by SKU or name before creating a new one
            if item["sku"]:
                row = conn.execute("SELECT id FROM Product WHERE sku = ?", (item["sku"],)).fetchone()
                if row:
                    product_id = row["id"]
            if product_id is None and item["name"]:
                row = conn.execute("SELECT id FROM Product WHERE name = ?", (item["name"],)).fetchone()
                if row:
                    product_id = row["id"]
            if product_id is not None:
                conn.execute("UPDATE PurchaseOrderItem SET productId = ? WHERE id = ?", (product_id, item["id"]))
            else:
                # Create new product only when truly not found
                product_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO Product (id, name, description, price, category, sku)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product_id,
                        item["name"] or f"New Product ({item['sku']})",
                        "Auto-created from purchase order",
                        item["unitCost"],
                        "Uncategorized",
                        item["sku"],
                    ),
                )
                conn.execute(
                    "UPDATE PurchaseOrderItem SET productId = ? WHERE id = ?",
                    (product_id, item["id"]),
                )

        # Check if Inventory row exists
        inv = conn.execute(
            "SELECT id, stockLevel FROM Inventory WHERE productId = ?",
            (product_id,),
        ).fetchone()

        if inv:
            before = inv["stockLevel"]
            after = before + item["quantity"]
            conn.execute(
                "UPDATE Inventory SET stockLevel = ?, lastRestock = ? WHERE id = ?",
                (after, now, inv["id"]),
            )
        else:
            before = 0
            after = item["quantity"]
            conn.execute(
                "INSERT INTO Inventory (id, productId, stockLevel, lastRestock) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), product_id, after, now),
            )

        inventory_changes.append({
            "sku": item["sku"],
            "name": item["name"],
            "productId": product_id,
            "stockBefore": before,
            "stockAfter": after,
            "added": item["quantity"],
        })

    conn.execute(
        "UPDATE PurchaseOrder SET status = 'Received' WHERE id = ?",
        (po_id,),
    )

    return inventory_changes


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/suppliers")
def list_suppliers() -> list[dict]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, name, email, phone FROM Supplier ORDER BY name"
        ).fetchall()


@router.post("")
def create_purchase_order(payload: PurchaseOrderCreate) -> dict:
    with get_connection() as conn:
        # Validate supplier
        supplier = conn.execute(
            "SELECT id FROM Supplier WHERE id = ?", (payload.supplierId,)
        ).fetchone()
        if not supplier:
            raise HTTPException(status_code=400, detail="Supplier not found.")

        po_id = str(uuid.uuid4())
        total = round(sum(i.quantity * i.unitCost for i in payload.items), 2)

        conn.execute(
            """
            INSERT INTO PurchaseOrder (id, supplierId, createdAt, status, totalAmount)
            VALUES (?, ?, CURRENT_TIMESTAMP, 'Draft', ?)
            """,
            (po_id, payload.supplierId, total),
        )

        for item in payload.items:
            conn.execute(
                """
                INSERT INTO PurchaseOrderItem (id, purchaseOrderId, productId, sku, name, quantity, unitCost)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    po_id,
                    item.productId,
                    item.sku,
                    item.name,
                    item.quantity,
                    item.unitCost,
                ),
            )

        conn.commit()

        result = _fetch_po(conn, po_id)

        # Auto-receive if requested
        if payload.auto_receive_on_approve:
            conn.execute(
                "UPDATE PurchaseOrder SET status = 'Approved' WHERE id = ?",
                (po_id,),
            )
            inventory_changes = _receive_po(conn, po_id)
            conn.commit()
            result = _fetch_po(conn, po_id)
            result["inventory_changes"] = inventory_changes

        return result


@router.post("/{po_id}/approve")
def approve_purchase_order(po_id: str, auto_receive: bool = False) -> dict:
    with get_connection() as conn:
        po = conn.execute(
            "SELECT id, status FROM PurchaseOrder WHERE id = ?", (po_id,)
        ).fetchone()
        if not po:
            raise HTTPException(status_code=404, detail="Purchase order not found.")
        if po["status"] not in ("Draft",):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve a PO with status '{po['status']}'. Must be Draft.",
            )

        conn.execute(
            "UPDATE PurchaseOrder SET status = 'Approved' WHERE id = ?",
            (po_id,),
        )

        result = _fetch_po(conn, po_id)

        if auto_receive:
            inventory_changes = _receive_po(conn, po_id)
            conn.commit()
            result = _fetch_po(conn, po_id)
            result["inventory_changes"] = inventory_changes
        else:
            conn.commit()

        return result


@router.post("/{po_id}/receive")
def receive_purchase_order(po_id: str) -> dict:
    with get_connection() as conn:
        po = conn.execute(
            "SELECT id, status FROM PurchaseOrder WHERE id = ?", (po_id,)
        ).fetchone()
        if not po:
            raise HTTPException(status_code=404, detail="Purchase order not found.")
        if po["status"] == "Received":
            # Idempotent: already received
            result = _fetch_po(conn, po_id)
            result["inventory_changes"] = []
            result["note"] = "Already received — no stock changes applied."
            return result
        if po["status"] not in ("Approved", "Sent"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot receive a PO with status '{po['status']}'. Must be Approved or Sent.",
            )

        inventory_changes = _receive_po(conn, po_id)
        conn.commit()

        result = _fetch_po(conn, po_id)
        result["inventory_changes"] = inventory_changes
        return result


@router.get("/{po_id}")
def get_purchase_order(po_id: str) -> dict:
    with get_connection() as conn:
        return _fetch_po(conn, po_id)


@router.get("")
def list_purchase_orders() -> list[dict]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT po.id, s.name AS supplierName, po.createdAt, po.status,
                   po.totalAmount, COUNT(poi.id) AS itemCount
            FROM PurchaseOrder po
            JOIN Supplier s ON po.supplierId = s.id
            LEFT JOIN PurchaseOrderItem poi ON poi.purchaseOrderId = po.id
            GROUP BY po.id
            ORDER BY po.createdAt DESC
            """
        ).fetchall()
