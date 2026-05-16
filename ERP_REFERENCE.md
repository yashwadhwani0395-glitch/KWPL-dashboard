# KWPL ERP — Complete Database Reference
**Database:** KW2526 (FY 2025-26)  
**Confirmed from:** Full Schema Survey + 300 Diagnostics + DB Objects scan  
**Critical rule: All queries use `MsTransType.id_key` — NOT `MsTransType.TransTypeID`**

---

## 1. Tables (27 total — no views, no stored procedures)

| Table | Rows | Purpose |
|---|---|---|
| MsAccountHead | 319 | Chart of Accounts — every GL account |
| MsAcHeadOpening | 319 | GL account opening/closing balance summary |
| MsBatchMaster | 6,582 | Batch/lot master (batch number, month, date) |
| MsBrandMaster | 331 | Brand master |
| MsCodeMaster | 810 | Lookup codes (cities, states, districts, MainHeads, SubHeads) |
| MsCodeTypeMaster | 35 | Code type definitions |
| MsItemBatchOpening | 7,963 | **Live stock** at BranchID+ItemID+BatchID level |
| MsItemMaster | 863 | Item/product master with valuation + MRP rates |
| MsItemRates | 864 | **Dated sale & purchase rates** per item |
| MsLiquorType | 11 | Liquor type lookup (IMFL, Beer, Wine, etc.) |
| MsLocalityRateMaster | 3,127 | **Locality-specific sale rates** per item |
| MsOptionMaster | 226 | ERP menu/module definitions |
| MsPartyMaster | 4,265 | Customer / Supplier / GL account master |
| MsPartyOpening | 4,265 | **Live party balance summary** |
| MsPartyTCSLimit | 4,198 | TCS rate per party per financial year |
| MsSalesmanMaster | 32 | Salesman master |
| MsServiceItemMaster | 4,376 | Service line items (TCS, excise, discounts, handling) |
| MsSizeType | 26 | Bottle size lookup |
| MsTransType | 54 | Transaction type definitions |
| TrackInfo | 3,560 | Audit/tracking log |
| TrTPDetail | 0 | TP→Invoice linkage (TPNo + TransTypeID + VoucherNo) |
| TrTPHead | 59,128 | Transport Permit headers |
| TrVocDetail | 460,768 | **Double-entry accounting legs** |
| TrVocHead | 176,317 | **Voucher headers** |
| TrVocItem | 559,505 | **Voucher item lines** (products + service items) |
| TrVocTCS | 97,709 | TCS per voucher (rate + payment status) |
| XMainheadSubhead | 114 | MainHead → SubHead mapping |
| XMainheadTypeMainhead | 19 | MainHeadType → MainHead mapping (COA nature) |

---

## 2. Transaction Type ID Map (id_key = what TrVocHead.TransTypeID references)

### Sales — ShortName = 'MS'
| id_key | TransTypeName | FY25-26 Active |
|---|---|---|
| 1 | Sales - IMFL (Diageo) | old/rare |
| 6 | SALES - MCD NO1 | old |
| 7 | SALES - UB BEER | old |
| 11 | SALES -WINES | ✓ |
| 13 | SALES UB DAMAN ONE DAY | ✓ |
| 15 | SALES QUAFFINE | old |
| 16 | SALES-BEER INSTITUTION | old |
| 17 | SALES USL NEW MRP | old |
| 20 | MS44 DIAGEO NEW MRP | ✓ |
| 23 | SALE WILD DRUM BEER | ✓ |
| 24 | SALES - UB BEER NEW MRP | old |
| 25 | IMFL (Diageo) | old |
| 26 | SALES UB WIT BEER/DAMAN | ✓ |
| 32 | Sales-Wine (7 PEAKS) | ✓ |
| 33 | SALES WINE IMPORTED | old |
| 35 | ONE DAY LICENCE | ✓ |
| 47 | SALES -WINE IMPORTED TG | ✓ |
| 51 | SALE JD IMPORTED | ✓ |
| 52 | PROFARMA INVOICE | ✓ |

### Purchases — ShortName = 'PU'
| id_key | TransTypeName | FY25-26 Active |
|---|---|---|
| 8 | Purchase Voucher-Kingfish | old |
| 10 | Purchase Voucher-IMPORTE | old |
| 14 | PURCHASE CORAL/QUAFFINE | ✓ (small) |
| 21 | Purchase Voucher Wine TG | ✓ |
| 22 | PURCHASE WILD DRUM BEER | ✓ |
| 27 | PURCHASE UB WIT/DAMAN | ✓ |
| 28 | PURCHASE TONIC WATER | ✓ |
| 30 | PURCHASE VOUCHER ONIV W | ✓ |
| 31 | PURCHASE 7 PEAKS | ✓ |
| 38 | Purchase Voucher-DIAGEO | ✓ (largest) |
| 49 | Purchase Voucher-I.M.F.L. | ✓ |
| 53 | PURCHASE JD IMPORTED | ✓ |

### Other Types
| id_key | ShortName | TransTypeName |
|---|---|---|
| 2 | BP | Bank Payment (old bank) |
| 3 | BR | Bank Receipts (old bank) |
| 4 | BP | Bank Payment (old bank) |
| 5 | BR | Bank Receipt (old bank) |
| 9 | SA | BREAKAGES-TRANSPORT |
| 12 | DN | DEBIT NOTE (SALES) |
| 18 | CE | Cash Payments -SHAH (main cash expense) |
| 19 | LD | LOAD DEMO |
| 29 | SA | SALES TONIC WATER |
| 34 | SO | Sales Order |
| 36 | CE | CASH PAY - SACHIN BHOSALE |
| 37 | CR | CASH RECEIPT - SACHIN |
| 39 | LD | LOAD (main load type) |
| 40 | BP | Bank Payment **(MAIN BP)** |
| 41 | BR | Bank Receipt **(MAIN BR)** |
| 42 | SA | Breakages **(MAIN SA)** |
| 43 | CR | Cash Receipts |
| 44 | CN | Credit Note - PURCH. |
| 45 | CN | Credit Note - SALES |
| 46 | DN | Debit Note - PURCH. |
| 47 | MS | SALES -WINE IMPORTED TG |
| 48 | JV | Journal Entries |
| 50 | BP | Return Cheques |
| 54 | RO | Receipt Order |

---

## 3. TrVocHead — Critical Column Facts

**HAS:** TransTypeID, VoucherDate, VoucherNo, Narration, VoucherFlag, UserID, DueDate,
TPNo, TPDate, Cancelled, SalesManID, FinancialYear, VehicleNumber, Address, InvoiceNo

**DOES NOT HAVE:** ~~PartyID~~, ~~TotalAmount~~

The **party** (customer/supplier) for any voucher is obtained from **TrVocDetail.PartyID**, not from TrVocHead. Always join via TrVocDetail to get the party.

---

## 4. Rate & Pricing Structure

### MsItemMaster rate columns
| Column | Meaning |
|---|---|
| ValuationBottleRate / ValuationCaseRate | **Valuation rate** — used for stock valuation & balance sheet |
| UDBottleRate / UDCaseRate | Distribution rate (same as valuation in most cases) |
| MrpBottRate / MrpCaseRate | **MRP** — government-set retail price per bottle / per case |
| TmpPurCaseRate / TmpPurBotRate | Temporary purchase rate (usually 0, cleared after use) |
| ExciseDutyCaseRate / ExciseDutyBottleRate | Excise duty rate per item (often 0 — stored at item level) |
| CapsRate | Capsule/cap rate |
| CommisionRate | Commission rate |
| LessPerMRP | Discount % below MRP |
| RateValuation | 'T' = use TotalBottleQty-based valuation |

### MsItemRates — the canonical dated rate table
| Column | Meaning |
|---|---|
| ItemID + ApplyDate | Composite key — rate valid from ApplyDate |
| SaleBottleRate / SaleCaseRate | **Current effective sale rate to retailers** |
| PurchaseBottleRate / PurchaseCaseRate | **Current effective purchase rate from principals** |
| FreeBottleRate / FreeCaseRate | Free goods rate |

**TrVocItem.BottleRate / CaseRate** = actual rate charged/paid in each transaction.

### MsLocalityRateMaster — area-specific pricing
Customers in different localities (LocalityID from MsPartyMaster) get different sale rates.  
Key: ItemID + LocalityID + ApplyFromDate → BottleRate / CaseRate

---

## 5. Stock Tracking

### MsItemBatchOpening — LIVE running stock
| Column | Meaning |
|---|---|
| BranchID + ItemID + BatchID | Composite key |
| OpeningQty | Opening stock at FY start |
| QtyIn | Total received (purchases) |
| QtyOut | Total dispatched (sales + breakages) |
| ClosingQty | FY-end computed closing |
| ClosingQtyTmp | **Live running closing stock** (use this) |
| FOpeningQty / FQtyIn / FQtyOut / FClosingQty | Free goods stock tracked separately |

**For live stock per item:**
```sql
SELECT ItemID, SUM(ClosingQtyTmp) AS live_stock
FROM MsItemBatchOpening
WHERE BranchID = 230
GROUP BY ItemID
```

---

## 6. Party Balance / Outstanding

### MsPartyOpening — pre-computed balance summary
| Column | Meaning |
|---|---|
| PartyID | Party (D% = customer, C% = supplier) |
| AccHeadID | GL control account |
| OpenBal | Opening balance at FY start |
| TotalDebit / TotalCredit | FY-end totals |
| CloseBal | **FY-end closing balance** (use before cutoff date) |
| CloseBalTmp | **Live running balance** (use for current outstanding) |
| TotalDebitTmp / TotalCreditTmp | Live running totals |

### TrVocDetail.RemainingAmt — bill-wise outstanding
When a payment (BR/CR) is received, the original invoice's TrVocDetail entry has `RemainingAmt` updated. This is how bill-wise outstanding is tracked (no separate allocation table).

---

## 7. TCS (Tax Collected at Source)

### Where TCS is stored:
1. **TrVocItem** — S00026 ("T.C.S. 2%.") appears as a service line on each MS invoice. TotalAmount = TCS amount charged.
2. **TrVocTCS** — One record per voucher with TCSPercent, SURPercent, ETPercent, PayedYN, challan details.
3. **MsPartyTCSLimit** — Per-party TCS rate configuration per financial year (TCSPercent, TCSLimit, FromDate, ToDate).
4. **MsPartyMaster** — Also has TCSPercent, TCSLimit columns (static default).

### TCS on purchase payments:
TrVocTCS has rows for BP (id_key=40) and CE (id_key=18) vouchers — excise/purchase payments also attract TCS.

---

## 8. Service Items on Invoices (MsServiceItemMaster)

These appear as TrVocItem rows with SItemID (S00xxx) instead of ItemID (I00xxx):

| SItemID | Description | Typical amount |
|---|---|---|
| S00026 | T.C.S. 2%. | +ve (charged to customer) |
| S00021 | EXCISE DUTY | +ve |
| S00006 | ADD INCIDENTAL CHARGES | +ve (handling/transport) |
| S00005 | PRODUCT DISCOUNT | -ve |
| S00002 | CASH DISCOUNT 2% | -ve |
| S00008 | CASH DISCOUNT 1% | -ve |
| S00054 | SPECIAL DISCOUNT | -ve |
| S00014 | TRADE DISCOUNT (PURCHASE) | -ve |
| S00007 | VEND FEE | -ve |
| S00065 | CHEQUE RETURN CHARGES | +ve |

All service items post to MainHeadID=010009, SubHeadID=020041. TCS (S00026) uniquely posts to AccHead 000218 (sale side).

---

## 9. TrVocDetail Double-Entry Patterns

### MS Sale (ShortName=MS):
- DR: D% customer account (DrCrIndicator='D') — debits the customer
- CR: 000004 SALES account (DrCrIndicator='C') — credits sales

### PU Purchase (ShortName=PU):
- CR: C% supplier account (DrCrIndicator='C') — credits the supplier
- DR: 000005 PURCHASES account (DrCrIndicator='D') — debits purchases

### BR Bank Receipt (ShortName=BR):
- DR: D% customer account (DrCrIndicator='D') — debits customer (reduces their outstanding)
- CR: Bank/cash account (DrCrIndicator='C') — credits KWPL's bank

### BP Bank Payment (ShortName=BP):
- DR: Expense/payable account (DrCrIndicator='D')
- CR: Bank account (DrCrIndicator='C')

### LD Load (ShortName=LD):
- DR: D% customer account (DrCrIndicator='D')
- CR: GL account (DrCrIndicator='C')
(LD = stock dispatched on load/demo — creates customer receivable)

---

## 10. Chart of Accounts (COA) Structure

### MsAccountHead.MainHeadType → Nature
| MainHeadType | Nature | Example |
|---|---|---|
| 1 | Debtors (Application of Funds) | SUNDRY DEBTORS CONTROL (000002) |
| 2 | Creditors | SUNDRY CREDITORS CONTROL (000003) |
| 3 | Income (other) | |
| 4 | Expenditure (expenses) | |
| 5 | Purchases/COGS | PURCHASES - TRADING (000005) |
| 6 | Sales | SALES (000004) |
| 7 | Debtors (variation) | |
| 8 | Creditors (variation) | |
| 9 | Stock/Inventory | |
| 10 | Other income/expense | |
| 11 | Misc/Cancelled | Cancelled Vouchers (000001) |

### For P&L:
- **Revenue**: `MainHeadType IN (6)` (Sales accounts)
- **COGS**: `MainHeadType IN (5)` (Purchase accounts)
- **Operating Expenses**: `MainHeadType IN (4)` (Expenditure accounts)
- **Other Income**: `MainHeadType IN (3)`

### For Balance Sheet:
- **Debtors (Asset)**: `MainHeadType IN (1, 7)`
- **Creditors (Liability)**: `MainHeadType IN (2, 8)`
- **Stock (Asset)**: `MainHeadType IN (9)`

---

## 11. Salesman Structure

- **MsSalesmanMaster**: 32 salesmen with SalesManID (char 6), FullName, Designation, Salary
- **TrVocHead.SalesManID**: Direct salesman assignment per voucher
- **MsPartyMaster.SalesManID / SalesManID1 / SalesManID2 / SalesManID3**: Up to 4 salesmen per customer

For salesman-wise sales, join TrVocHead.SalesManID → MsSalesmanMaster.SalesManID.

---

## 12. Transport Permit (TP) Structure

- **TrTPHead**: One TP per customer delivery trip (TPNo, TPDate, PartyID=customer, VehicleNumber, Route, ValidityDate)
- **TrTPDetail**: Links TPNo → TransTypeID + VoucherNo (which invoices are on this TP)
- **TrVocHead.TPNo**: Links invoice → TP number
- 59,128 TPs in database (very active, one TP per customer per delivery)

---

## 13. Customer Master Key Fields

**MsPartyMaster critical columns for analysis:**
- `PartyID` (D% = customer, C% = supplier, blank/others = GL accounts)
- `PartyName`, `LocalityID`, `CategoryID`, `ClassID`, `CustomerGrpID`
- `SalesManID` (+ SalesManID1/2/3 for multiple salesmen)
- `CreditDays`, `CreditLimit`
- `TCSPercent`, `TCSLimit` (per-customer TCS config)
- `CDPercent` (cash discount percent)
- `BillFormulaID` (billing formula assigned to customer)
- `MainHeadID`, `SubHeadID` (COA group for this customer's ledger)

---

## 14. FY Scoping

All FY 2025-26 queries use:
```sql
WHERE h.VoucherDate >= '2025-04-01'
  AND h.VoucherDate <  '2026-04-01'
```

`TrVocHead.FinancialYear` also has '2025-2026' string — can be used as alternative filter.

---

## 15. Key Column Names (confirmed — avoid guessing)

| Table | Column | NOT | Confirmed |
|---|---|---|---|
| TrVocItem | SerialNo | ~~SrNo~~ | ✓ |
| TrVocHead | SalesManID | ~~SalesmanID~~ | ✓ |
| MsItemBatchOpening | ClosingQtyTmp | ~~ClosingQty~~ for live | ✓ |
| MsPartyOpening | CloseBalTmp | ~~CloseBal~~ for live | ✓ |
| MsItemMaster | ValuationBottleRate | ~~ValuationRate~~ | ✓ |
| MsItemRates | SaleBottleRate | ~~SaleRate~~ | ✓ |
| TrVocTCS | TCSPercent | ~~TCSRate~~ | ✓ |
| TrVocDetail | RemainingAmt | (bill-wise tracker) | ✓ |

---

## 16. FY 2025-26 Volume Summary

| Type | Vouchers | Value |
|---|---|---|
| MS Sales | 13,989 | ₹433 Cr |
| PU Purchases | ~17,500 | ₹184 Cr (excl excise) |
| BP Bank Payment | 20,631 | ₹100 Cr |
| CE Cash Payment | 10,104 | ₹147 Cr |
| LD Load/Demo | 22,710 | ₹104 Cr |
| BR Bank Receipt | 2,956 | ₹10.9 Cr |
| DN Debit Notes | 1,030 | ₹17.9 Cr (to customers) |
| Debtors Outstanding | 4,236 customers | ₹54.3 Cr |
| TPs issued | 59,128 | — |
