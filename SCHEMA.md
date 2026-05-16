# KWPL Database Schema Documentation

## Databases
| Database | Description |
|---|---|
| `KW2526` | Current financial year (2025-26, merged with 2026-27) |
| `KW2425` | Financial year 2024-25 |
| `KW2324` | Financial year 2023-24 |
| `KW****` | One database per financial year |
| `WINFA` | Unknown — KWPL user has no access |
| `TempData` | Temporary data |
| `TempDataWINFA` | Temporary data for WINFA |

---

## Core Tables

### TrVocHead — Transaction/Invoice Header
Main table for all transactions. One row per voucher/invoice.

| Column | Description |
|---|---|
| `TransTypeID` | Type of transaction (see TransTypeID reference below) |
| `VoucherNo` | Unique voucher number |
| `VoucherDate` | Date of the transaction |
| `ParentDocDet` | Reference to parent document |
| `Narration` | Transaction notes/description |
| `VoucherFlag` | Status flag (space = normal, B = ?, N = ?, Y = ?) |
| `SalesManID` | Linked salesman |
| `Cancelled` | Whether voucher is cancelled |
| `FinancialYear` | Financial year of the transaction |
| `Location` | Location/branch |
| `InvoiceNo` | Invoice number |
| `VehicleNumber` | Delivery vehicle |
| `TPNo` / `TPDate` | Transport Permit number and date |
| `GSTNo` | GST number |
| `CDFlag` | Cash/Discount flag (rarely used) |

---

### TrVocDetail — Transaction Accounting Entries
Debit/Credit accounting lines for each voucher.

| Column | Description |
|---|---|
| `TransTypeID` | Links to TrVocHead |
| `VoucherNo` | Links to TrVocHead |
| `AccHeadID` | Account head (ledger) |
| `DrCrIndicator` | D = Debit, C = Credit |
| `Amount` | Transaction amount |
| `PartyID` | Customer/Party linked to this entry |
| `BalanceAmount` | Outstanding balance |
| `RemainingAmt` | Remaining amount to be settled |
| `FinancialYear` | Financial year |

---

### TrVocItem — Transaction Line Items (Products)
Individual product lines within each invoice.

| Column | Description |
|---|---|
| `TransTypeID` | Links to TrVocHead |
| `VoucherNo` | Links to TrVocHead |
| `SerialNo` | Line item serial number |
| `ItemID` | Product (links to MsItemMaster) |
| `BrandID` | Brand (links to MsBrandMaster) |
| `CaseQty` | Quantity in cases |
| `BottleQty` | Quantity in bottles |
| `TotalBottleQty` | Total bottles (cases converted + loose bottles) |
| `CaseRate` | Rate per case |
| `BottleRate` | Rate per bottle |
| `TotalAmount` | Total line amount |
| `BatchID` | Stock batch |
| `FreeItemYN` | Whether item is free (scheme) |
| `SchemeID` | Scheme applied |
| `FinancialYear` | Financial year |

---

### TrTPHead / TrTPDetail — Transport Permit
Used to record TPs generated at warehouse after billing at office.
- Billing happens at **office**
- TP generated at **warehouse** when vehicle is available
- Links invoice → physical delivery

---

### MsPartyMaster — Customers / Retailers
| Column | Description |
|---|---|
| `PartyID` | Unique party ID |
| `PartyName` | Customer/retailer name |
| `Address` | Address |
| `LicenseNo` | Liquor license number |
| `SalesManID` | Assigned salesman |
| `CreditDays` | Credit period allowed |
| `CreditLimit` | Credit limit amount |
| `BannedPartyYN` | Whether party is banned |
| `CategoryID` | Customer category |
| `LocalityID` | Area/locality |

---

### MsItemMaster — Products / Liquor Items
| Column | Description |
|---|---|
| `ItemID` | Unique item ID |
| `ItemDescription` | Product name |
| `BrandID` | Brand |
| `LiquorTypeID` | Type of liquor |
| `SizeTypeID` | Bottle size |
| `MrpCaseRate` | MRP per case |
| `MrpBottRate` | MRP per bottle |
| `BottlesPerCase` | Bottles in one case |
| `ImportedYN` | Imported product? |
| `Mls` | Volume in ML |

---

### MsSalesmanMaster — Sales Representatives
| Column | Description |
|---|---|
| `SalesManID` | Unique salesman ID |
| `FullName` | Full name |
| `Designation` | Job title |
| `ContactNo` | Phone number |
| `ResignDate` | If resigned, date |

---

### MsBrandMaster — Liquor Brands
Brand master (Diageo, USL, UB, McDowell's etc.)

### MsLiquorType — Liquor Categories
IMFL, Beer, Wine, Imported etc.

### MsTransType — Transaction Type Master
Defines all transaction types used in the system.

---

## TransTypeID Reference

### Sales (TransType code = MS) — verified from live DB
| ID | Description | Principal |
|---|---|---|
| 1  | Sales - IMFL (Diageo) | Diageo |
| 20 | MS44 Diageo New MRP | Diageo |
| 25 | IMFL (Diageo) | Diageo |
| 6  | Sales - MCD No1 | USL / McDowell's |
| 17 | Sales USL New MRP | USL / McDowell's |
| 7  | Sales - UB Beer | UB / Kingfisher |
| 24 | Sales - UB Beer New MRP | UB / Kingfisher |
| 26 | Sales UB Wit Beer / Daman | UB / Kingfisher |
| 13 | Sales UB Daman One Day | UB / Kingfisher |
| 16 | Sales - Beer Institution | UB / Kingfisher |
| 51 | Sale JD Imported | Brown-Forman |
| 11 | Sales - Wines | Wines & Imports |
| 47 | Sales - Wine Imported TG | Wines & Imports |
| 32 | Sales - Wine (7 Peaks) | Wines & Imports |
| 33 | Sales Wine Imported | Wines & Imports |
| 23 | Sale Wild Drum Beer | Others |
| 15 | Sales Quaffine | Others |
| 35 | One Day Licence | Others |
| 52 | Proforma Invoice | Others |

### Purchases (TransType code = PU) — verified from live DB
| ID | Description |
|---|---|
| 8  | Purchase - Kingfisher |
| 10 | Purchase - Imported |
| 14 | Purchase - Coral / Quaffine |
| 21 | Purchase - Wine TG |
| 22 | Purchase - Wild Drum Beer |
| 27 | Purchase - UB Wit / Daman |
| 28 | Purchase - Tonic Water |
| 30 | Purchase - ONIV Wine |
| 31 | Purchase - 7 Peaks |
| 38 | Purchase - Diageo |
| 49 | Purchase - IMFL |
| 53 | Purchase - JD Imported |

### Payments & Receipts — verified from live DB
| ID | Code | Description |
|---|---|---|
| 3  | BR | Bank Receipts |
| 5  | BR | Bank Receipt |
| 41 | BR | Bank Receipt |
| 37 | CR | Cash Receipt - Sachin |
| 43 | CR | Cash Receipts |
| 2  | BP | Bank Payment |
| 4  | BP | Bank Payment |
| 40 | BP | Bank Payment |
| 50 | BP | Return Cheques |
| 18 | CE | Cash Payments - Shah |
| 36 | CE | Cash Pay - Sachin Bhosale |

### Other
| ID | Code | Description |
|---|---|---|
| 48 | JV | Journal Entries |
| 9  | SA | Breakages - Transport |
| 29 | SA | Sales Tonic Water |
| 42 | SA | Breakages |
| 19 | LD | Load Demo |
| 39 | LD | Load |
| 34 | SO | Sales Order |
| 54 | RO | Receipt Order |
| 44 | CN | Credit Note - Purchase |
| 45 | CN | Credit Note - Sales |
| 12 | DN | Debit Note - Sales |
| 46 | DN | Debit Note - Purchase |

---

## Key Relationships
```
TrVocHead (TransTypeID + VoucherNo)
    ├── TrVocDetail (accounting entries)
    ├── TrVocItem (product line items)
    └── TrTPHead (transport permit)

TrVocItem
    ├── MsItemMaster (ItemID)
    └── MsBrandMaster (BrandID)

TrVocHead / TrVocDetail
    └── MsPartyMaster (PartyID)

TrVocHead
    └── MsSalesmanMaster (SalesManID)
```

---

## Open Questions
- `VoucherFlag` values: space=normal, B=?, N=?, Y=? — needs clarification
- `WINFA` database — KWPL user has no access, purpose unknown
- `XMainheadSubhead` / `XMainheadTypeMainhead` — chart of accounts hierarchy
- `CDFlag` — rarely used, purpose unclear
