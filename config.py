# Transaction Type IDs
SALES_TYPES = (9, 13, 18, 19, 23, 27, 34, 35, 38, 39, 40, 41, 44, 47, 49, 50, 51, 52, 53)
PURCHASE_TYPES = (11, 20, 22, 30, 32, 33, 36, 42, 45, 46, 48, 54)
RECEIPT_CODES = ('BR', 'CR')
PAYMENT_CODES = ('BP', 'CE')

SALES_IN    = ",".join(str(x) for x in SALES_TYPES)
PURCHASE_IN = ",".join(str(x) for x in PURCHASE_TYPES)

# SQL filter fragments
NOT_CANCELLED = "AND h.Cancelled <> 'Y'"
NOT_FREE      = "AND i.FreeItemYN <> 'Y'"

# Brand colours for charts
COLORS = {
    "primary":   "#7B2D8B",
    "sales":     "#7B2D8B",
    "purchase":  "#E84855",
    "collection":"#28A745",
    "warning":   "#FFC107",
    "info":      "#2E86AB",
}

COMPANY_NAME = "Kranti Wines Pvt Ltd"
