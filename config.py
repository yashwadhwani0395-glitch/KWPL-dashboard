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

PRINCIPAL_ORDER  = ["Diageo", "USL / McDowell's", "UB / Kingfisher",
                    "Brown-Forman", "Wines & Imports", "Others"]

PRINCIPAL_COLORS = {
    "Diageo":           "#7B2D8B",
    "USL / McDowell's": "#E84855",
    "UB / Kingfisher":  "#F7B731",
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
        WHEN {alias}.BrandID IN ({ids(_B_USL)})    THEN 'USL / McDowell''s'
        WHEN {alias}.BrandID IN ({ids(_B_UB)})     THEN 'UB / Kingfisher'
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
