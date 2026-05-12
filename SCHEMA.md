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

### Sales (TransType code = MS)
| ID | Description |
|---|---|
| 13 | Sales - IMFL Diageo |
| 18 | Sales - McDowell's No.1 |
| 19 | Sales - UB Beer |
| 23 | Sales - Wines |
| 38 | Sales - USL New MRP (United Spirits) |
| 39 | Sales - UB Beer New MRP |
| 40 | IMFL Diageo (new) |
| 41 | Sales UB Wit Beer / Daman |
| 47 | Sale Wild Drum Beer |
| 49 | Sales Quaffine |
| 51 | Sales - Beer Institution (KW + PCMC) |
| 53 | Sale JD Imported |
| 9  | Sales - Wine Imported TG |
| 34 | Sales - Wine 7 Peaks |
| 35 | Sales Wine Imported |
| 44 | MS44 Diageo New MRP |
| 27 | One Day Licence |
| 50 | Sales UB Daman One Day |
| 52 | Proforma Invoice |

### Purchases (TransType code = PU)
| ID | Description |
|---|---|
| 11 | Purchase - IMFL |
| 20 | Purchase - Kingfisher |
| 22 | Purchase - Imported |
| 30 | Purchase - Diageo |
| 32 | Purchase - ONIV Wine |
| 33 | Purchase - 7 Peaks |
| 36 | Purchase - Tonic Water |
| 42 | Purchase - UB Wit / Daman |
| 45 | Purchase - Wine TG |
| 46 | Purchase - Wild Drum Beer |
| 48 | Purchase - Coral / Quaffine |
| 54 | Purchase - JD Imported |

### Payments & Receipts
| ID | Code | Description |
|---|---|---|
| 1  | BP | Bank Payment |
| 2  | BR | Bank Receipt |
| 12 | BP | Return Cheques |
| 4  | CE | Cash Payments - Shah |
| 5  | CR | Cash Receipts |
| 28 | CE | Cash Pay - Sachin Bhosale |
| 29 | CR | Cash Receipt - Sachin |

### Other
| ID | Code | Description |
|---|---|---|
| 10 | JV | Journal Entries |
| 3  | SA | Breakages |
| 21 | SA | Breakages - Transport |
| 37 | SA | Sales Tonic Water |
| 25 | LD | Load (internal stock) |
| 26 | SO | Sales Order |
| 55 | RO | Receipt Order |
| 6  | CN | Credit Note - Purchase |
| 7  | CN | Credit Note - Sales |
| 8  | DN | Debit Note - Purchase |
| 24 | DN | Debit Note - Sales |

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
