# ════════════════════════════════════════════════════════════════════════════
# KWPL ERP — Confirmed constants from full schema survey + 300 diagnostics
# CRITICAL: TrVocHead.TransTypeID references MsTransType.id_key (NOT TransTypeID)
# CRITICAL: TrVocHead has NO PartyID and NO TotalAmount columns.
#           Get party from TrVocDetail.PartyID. Get amounts from TrVocItem/TrVocDetail.
# ════════════════════════════════════════════════════════════════════════════

# ── Transaction Type IDs (id_key values from MsTransType) ────────────────────

# All MS (Sales) id_keys — use ShortName filter 'MS' in queries for safety
SALES_TYPES = (1, 6, 7, 11, 13, 15, 16, 17, 20, 23, 24, 25, 26, 32, 33, 35, 47, 51, 52)

# Active MS types in FY 2025-26 (confirmed from diagnostics)
SALES_TYPES_ACTIVE = (11, 13, 20, 23, 26, 32, 35, 47, 51, 52)

# All PU (Purchase) id_keys
PURCHASE_TYPES = (8, 10, 14, 21, 22, 27, 28, 30, 31, 38, 49, 53)

# Active PU types in FY 2025-26
PURCHASE_TYPES_ACTIVE = (14, 21, 22, 27, 28, 30, 31, 38, 49, 53)

# BP = Bank Payment. id_key 40 = main BP; 2,4,50 = old/return cheque banks.
BP_TYPES = (2, 4, 40, 50)
BP_MAIN  = 40   # Main Bank Payment

# BR = Bank Receipt. id_key 41 = main BR; 3,5 = old banks.
BR_TYPES = (3, 5, 41)
BR_MAIN  = 41   # Main Bank Receipt

# CE = Cash Expenses. id_key 18 = SHAH cash; 36 = SACHIN BHOSALE cash.
CE_TYPES = (18, 36)

# CR = Cash Receipt. id_key 37 = SACHIN; 43 = main.
CR_TYPES = (37, 43)

# LD = Load/Demo dispatches. id_key 19 = LOAD DEMO; 39 = LOAD.
LD_TYPES = (19, 39)

# SA = Breakages/Write-offs. id_key 9 = transport; 29 = tonic water; 42 = main.
SA_TYPES = (9, 29, 42)

# DN = Debit Note. 12 = to customers (SALES); 46 = from suppliers (PURCH).
DN_TYPES      = (12, 46)
DN_SALES_TYPE = 12    # Debit note charged to customer
DN_PURCH_TYPE = 46    # Debit note from supplier (claim)

# CN = Credit Note. 44 = from supplier (PURCH); 45 = to customer (SALES).
CN_TYPES      = (44, 45)
CN_SALES_TYPE = 45    # Credit note given to customer
CN_PURCH_TYPE = 44    # Credit note received from supplier

# Other types
SO_TYPE  = 34   # Sales Order (no stock/accounting effect, PostingYN='N')
RO_TYPE  = 54   # Receipt Order
JV_TYPE  = 48   # Journal Voucher

# ── SQL filter fragments ──────────────────────────────────────────────────────
RECEIPT_CODES = ('BR', 'CR')
PAYMENT_CODES = ('BP', 'CE')

SALES_IN      = ",".join(str(x) for x in SALES_TYPES)
PURCHASE_IN   = ",".join(str(x) for x in PURCHASE_TYPES)

# BP (40) + CE (18,36) carry excise duty on imported goods — used for P&L purchases KPI
EXCISE_TYPES    = (40, 18, 36)
PURCHASE_ALL_IN = PURCHASE_IN + "," + ",".join(str(x) for x in EXCISE_TYPES)

# Standard SQL clauses
NOT_CANCELLED = "AND ISNULL(h.Cancelled,'N') <> 'Y'"
NOT_FREE      = "AND ISNULL(i.FreeItemYN,'N') <> 'Y'"

# FY 2025-26 date range
FY_START = "2025-04-01"
FY_END   = "2026-04-01"   # exclusive upper bound (< this date)

# ── Party prefix helpers ──────────────────────────────────────────────────────
# D% = customers (debtors), C% = suppliers (creditors), others = GL accounts
CUSTOMER_PREFIX  = "D"
SUPPLIER_PREFIX  = "C"

# ── COA / Account nature (MsAccountHead.MainHeadType) ────────────────────────
# Used for P&L and Balance Sheet categorisation
COA_DEBTORS    = (1, 7)    # Debtor control accounts → current assets
COA_CREDITORS  = (2, 8)    # Creditor control accounts → current liabilities
COA_INCOME_OTHER = (3,)    # Other income
COA_EXPENDITURE = (4,)     # Operating expenses
COA_PURCHASES  = (5,)      # Purchases / COGS
COA_SALES      = (6,)      # Sales revenue
COA_STOCK      = (9,)      # Stock / inventory accounts
COA_OTHER      = (10, 11)  # Misc / cancelled

# Key GL account IDs (confirmed from MsAccountHead)
GL_DEBTORS_CONTROL  = "000002"   # SUNDRY DEBTORS CONTROL
GL_CREDITORS_CONTROL = "000003"  # SUNDRY CREDITORS CONTROL
GL_SALES            = "000004"   # SALES
GL_PURCHASES        = "000005"   # PURCHASES - TRADING

# ── Rate columns (confirmed from MsItemMaster + MsItemRates) ─────────────────
# MsItemRates is the canonical dated rate table (use for current rates):
#   SaleBottleRate / SaleCaseRate      → current effective sale rate to retailers
#   PurchaseBottleRate / PurchaseCaseRate → current effective purchase rate
#   ApplyDate                           → effective from this date
#
# MsItemMaster rate columns:
#   ValuationBottleRate / ValuationCaseRate → stock valuation rate (balance sheet)
#   MrpBottRate / MrpCaseRate               → government MRP (retail price ceiling)
#   ExciseDutyCaseRate / ExciseDutyBottleRate → excise duty per item
#
# TrVocItem.BottleRate / CaseRate → ACTUAL rate used in each transaction

# ── Stock columns (confirmed from MsItemBatchOpening) ────────────────────────
# Use ClosingQtyTmp for LIVE stock, ClosingQty for FY-end computed stock.
# FOpeningQty / FQtyIn / FQtyOut / FClosingQty → free-goods stock tracked separately.
# Group by ItemID (records are at BranchID + ItemID + BatchID level).

# ── Balance columns (confirmed from MsPartyOpening) ──────────────────────────
# Use CloseBalTmp for LIVE outstanding, CloseBal for FY-end balance.
# Sign convention: positive = KWPL is owed money (debit balance = customer owes).

# ── TCS tracking tables ───────────────────────────────────────────────────────
# TrVocTCS        → one row per voucher: TCSPercent, PayedYN, challan details
# MsPartyTCSLimit → per-party TCS rate by financial year (FromDate, ToDate)
# S00026 in TrVocItem → TCS line on each MS invoice (TotalAmount = TCS charged)

# ── Service item IDs (MsServiceItemMaster) ───────────────────────────────────
SI_TCS             = "S00026"   # T.C.S. 2%. — charged on invoice
SI_EXCISE          = "S00021"   # Excise Duty
SI_HANDLING        = "S00006"   # Add Incidental Charges (transport/handling)
SI_PRODUCT_DISC    = "S00005"   # Product Discount
SI_CASH_DISC_2PCT  = "S00002"   # Cash Discount 2%
SI_CASH_DISC_1PCT  = "S00008"   # Cash Discount 1%
SI_SPECIAL_DISC    = "S00054"   # Special Discount
SI_TRADE_DISC_PU   = "S00014"   # Trade Discount (Purchase)
SI_VEND_FEE        = "S00007"   # Vend Fee

# ── TrVocHead column truth ────────────────────────────────────────────────────
# CONFIRMED PRESENT:   TransTypeID, VoucherDate, VoucherNo, Narration,
#                      VoucherFlag, UserID, DueDate, TPNo, TPDate, Cancelled,
#                      SalesManID, FinancialYear, VehicleNumber, Address, InvoiceNo
# CONFIRMED ABSENT:    PartyID, TotalAmount
# Get party via:       TrVocDetail.PartyID (D% or C% prefix)
# Get sale amount via: SUM(i.TotalAmount) FROM TrVocItem WHERE NOT FreeItemYN

# ── Brand → Principal mapping (verified from live brands.csv) ─────────────────
# BrandIDs for each principal — used to generate SQL CASE statements

_B_DIAGEO = [
    # Johnnie Walker family
    277, 278, 279, 284, 286, 292, 293, 294, 295, 296, 297, 305, 342, 345, 346,
    371, 372, 373, 375, 376, 379, 388, 396, 401, 417, 437, 445, 458, 568,
    # Smirnoff family
    266, 269, 270, 271, 273, 274, 275, 276, 353, 354, 355, 356, 368, 419, 432,
    561, 563, 565,
    # Tanqueray family
    287, 382, 394, 522, 523,
    # Classic Malts & Rare
    282, 283, 288, 289, 290, 298, 330, 335, 389, 428, 429, 433, 446,
    # Singleton of Glendullan
    390, 391, 392, 434, 435, 436, 535,
    # Baileys
    280, 481, 542, 567,
    # Ketel One
    285, 380, 430,
    # Don Julio
    475, 476, 541, 560,
    # Captain Morgan, Ciroc, Gordon's, J&B Rare
    224, 281, 291, 381,
    # Godawan
    463, 464,
    # Roe & Co
    482,
    # Greater Than & Hapusa (mapped to Diageo in ERP)
    589, 590, 593,
]

_B_USL = [
    # McDowell's No.1 family
    213, 217, 223, 555, 556, 559, 569, 570, 582, 591, 594,
    # McDowell's Signature
    218, 360,
    # Antiquity
    323, 487,
    # Royal Challenge, Master Signature
    90, 110, 450,
    # Black Dog family
    215, 225, 331, 332,
    # Black & White family
    272, 333, 358,
    # VAT 69 family
    265, 267, 334,
    # Other USL
    477,
]

_B_UB = [
    # Kingfisher Strong
    78, 80, 109, 126, 189, 329, 483, 486, 557, 586, 595,
    # Kingfisher Lager / Ultra
    84, 112, 214, 327, 344, 378, 479,
    # Kingfisher Draught / Kegs
    478, 573, 574,
    # Kingfisher variants
    571, 572,
    # London Pilsner (UB brand)
    38,
    # Heineken
    219, 448, 552, 566,
    # Amstel
    443, 558,
    # Cannon, Queenfisher
    77, 554,
]

_B_BF = [
    # Jack Daniel's family
    576, 577, 578, 579, 583, 585,
    # Woodford Reserve
    580,
    # GlenDronach
    588, 592,
]

_B_WINE = [
    # 7 Peaks (all)
    452, 453, 454, 456, 457, 459, 460, 465, 466, 480, 511, 533, 538, 539, 540,
    550, 551,
    # Chantilli
    495, 496, 503, 504, 505, 512, 581,
    # Tiger Hill
    513, 515, 516, 517, 534, 536, 549, 575,
    # Vin Ballent
    497, 499, 500, 506, 508, 509, 584,
    # Figueira
    498, 507,
    # Riviera
    494, 502,
    # Vino Sparkling
    501, 510,
    # Mist of Shayadri
    519, 520, 521,
    # Ujva (South African)
    488, 489, 490, 491,
    # Athena, Omar Khayyam, Ivy Brut, Marquise de Pompadour
    451, 493, 532, 553,
    # Vero, NOI, Ziva, Kyra (Italian/European)
    227, 316, 317, 318, 319, 321, 322, 325, 326, 397, 398, 399, 402,
    # European imports (French, Australian etc.)
    159, 160, 161, 162, 163, 309, 405, 406, 407, 408, 409, 410, 411, 412,
    413, 414, 415, 416, 468, 469, 470, 471, 472, 473, 474,
    # Chilean wines (Casillero, Frontera)
    199, 200, 201,
    # Dessert wines
    514, 518,
    # Four Seasons, Golconda etc.
    230, 231, 232, 233, 234, 235, 236, 237, 240, 241, 242, 243,
]

PRINCIPAL_ORDER  = ["Diageo", "United Spirits", "United Breweries",
                    "Brown-Forman", "Wines & Imports", "Others"]

PRINCIPAL_COLORS = {
    "Diageo":           "#7B2D8B",
    "United Spirits":   "#E84855",
    "United Breweries": "#F7B731",
    "Brown-Forman":     "#8B4513",
    "Wines & Imports":  "#28A745",
    "Others":           "#6C757D",
}


def brand_case(alias: str = "i") -> str:
    """Return SQL CASE expression mapping i.BrandID → principal name."""
    def ids(lst):
        return ",".join(str(x) for x in lst)
    return f"""CASE
        WHEN {alias}.BrandID IN ({ids(_B_DIAGEO)}) THEN 'Diageo'
        WHEN {alias}.BrandID IN ({ids(_B_USL)})    THEN 'United Spirits'
        WHEN {alias}.BrandID IN ({ids(_B_UB)})     THEN 'United Breweries'
        WHEN {alias}.BrandID IN ({ids(_B_BF)})     THEN 'Brown-Forman'
        WHEN {alias}.BrandID IN ({ids(_B_WINE)})   THEN 'Wines & Imports'
        ELSE 'Others'
    END"""


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
