# Transaction Type IDs — verified from live MsTransType table
# MS (Sales): 1,6,7,11,13,15,16,17,20,23,24,25,26,32,33,35,47,51,52
SALES_TYPES = (1, 6, 7, 11, 13, 15, 16, 17, 20, 23, 24, 25, 26, 32, 33, 35, 47, 51, 52)
# PU (Purchases): 8,10,14,21,22,27,28,30,31,38,49,53
PURCHASE_TYPES = (8, 10, 14, 21, 22, 27, 28, 30, 31, 38, 49, 53)
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
