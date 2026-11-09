# LCTR Extraction Agent: Instructions and Field Spec

Scope: Loomis delivery orders, trade tickets, and Bank of America shipment documents (Travelex flow).
Status: DRAFT v0.1, built from the 6 sample shipments. Not validated against any other document layout.
Companion files: `LCTR_Demo_Workbook.xlsx` (mapping, gaps, data quality) and `LCTR_draft_payload.json`.

## 1. Design

The agent only **extracts what is printed on the documents**. It does not build the FINTRAC payload and does not fill in FINTRAC identifiers, indicators or codes. A separate step (flow or code) maps the extraction JSON to the FINTRAC LCTR structure, using the Field Mapping sheet.

Assumption: the PDF text (or OCR text) is supplied to the agent as plain text. The PDF-to-text step is outside this spec. Trade-ticket tables can break across pages (the first sample ticket does), so the text must keep page order.

Why this split: extraction can be tested against the documents; reportability, conductor identity, disposition and 24-hour-rule treatment are compliance decisions and must not be guessed by a model.

## 2. Document types the agent must recognise

| Type | How to recognise | Notes |
|---|---|---|
| Loomis Delivery Order | Title "Delivery Order", Loomis International (CA) Inc. header, "Shipment : YYZ-..." | One per shipment; 1 page |
| Trade Ticket Insert | "TRADE TICKET INSERT", "Deal no : <digits>- 1" | 1 or more follow each Delivery Order; one DO can reference two deals (comma-separated Reference) |
| Incoming Cash Shipment Log | "Incoming Cash Shipment log", bank header | BofA format; no shipment ID |
| Letter of Authorization | "LETTER OF AUTHORIZATION - COMMERCIAL INVOICE" | Gives consignor/delivery address and denominations |

Pair a Trade Ticket to a Delivery Order when its deal number appears in the DO's `Reference` field.

## 3. Agent instructions (paste into Copilot Studio)

```
You extract structured data from cash-shipment documents for a compliance reporting workflow.

RULES
1. Extract only what is printed in the document text. Never infer, guess, or fill from general knowledge.
2. If a value is absent or illegible, return null and add the field name to "missing_fields". Do not substitute a similar value.
3. Copy names, addresses and numbers exactly as printed. Do not translate, abbreviate, or correct spelling. Put any normalisation in separate "_normalized" fields only where the schema asks for it.
4. Dates: return ISO 8601 (yyyy-mm-dd). Times: return hh:mm 24-hour, or null. Do not add a time zone.
5. Amounts: return numbers with a dot as the decimal separator and no thousands separators.
6. A Delivery Order may be followed by one or more Trade Tickets. A comma-separated "Reference" lists their deal numbers. Return one trade_tickets[] entry per ticket, in document order. A ticket table may continue on the next page; keep reading until "Total :" appears.
7. Return every trade-ticket leg as its own row. Never merge or skip rows. If two rows appear on one text line because of a page break, split them using the leg numbers.
8. "External Remarks" and "Internal Remarks" are free text. Copy them verbatim into remarks fields. Do NOT treat a name there as a customer, conductor or any other role.
9. Do not decide whether anything is reportable. Do not output FINTRAC codes.
10. Return JSON only, matching the schema below. No commentary.

If the input is not one of the four known document types, return {"document_type": "unknown"} and nothing else.
```

## 4. Output schema (extraction JSON)

```json
{
  "document_type": "delivery_order | trade_ticket | incoming_cash_log | letter_of_authorization | unknown",
  "source_file": "string",
  "delivery_order": {
    "shipment_id": "YYZ-1057026-YYZ-1",
    "document_date": "2026-05-08",
    "consignor_name": "TRAVELEX CANADA LIMITED",
    "consignor_address_line": "CA-M5J 2T3 Toronto, ON",
    "reference_deal_numbers": ["2026050800006"],
    "shipper": { "name": "", "address_lines": [], "postal_code": "", "city": "", "province": null },
    "consignee": { "name": "", "address_lines": [], "postal_code": "", "city": "", "province": null },
    "pickup_from": "2026-05-11T10:00", "pickup_to": null,
    "delivery_from": "2026-05-11T12:00", "delivery_to": null,
    "goods_value": 355381.21, "goods_value_currency": "CAD",
    "insurance_value": 355381.21,
    "bags": 2, "weight_kg": 6, "goods_description": "Bank notes",
    "seals": ["KA000960390", "KA000960391"],
    "custody_signatures": { "date": null, "time": null, "print_name": null, "signature_present": false },
    "hashcode": "18D2"
  },
  "trade_tickets": [{
    "deal_no": "2026050800006-1",
    "deal_type": "Bank Notes Normal / CUSTOMER",
    "customer_name": "", "branch": "", "sdi_address_lines": [], "sdi_province": "ON",
    "travelex_side": "BUY | SELL",
    "settlement_currency": "CAD",
    "trade_date": "2026-05-08", "value_date": "2026-05-11",
    "vault_date": "2026-05-11", "release_date": "2026-05-11",
    "legs": [{ "leg": 1, "ccy": "EUR", "bn_type": "FIT", "denomination": 5, "pieces": 50,
               "amount": 250.00, "deal_rate": 1.597521, "settlement_amt": 399.38 }],
    "total": 355381.21, "total_settlement": 355381.21, "settlement_local_equivalent": 355381.21,
    "eqv_usd_value": 263863.46, "eqv_base_value": 360239.58,
    "internal_remarks": "EFT", "external_remarks": "verbatim text"
  }],
  "incoming_cash_log": { "log_date": null, "contract": null, "currency": null, "country_of_origin": null,
                         "purpose": null, "amount": null, "currency_exchange_rate": null, "cad_rate": null,
                         "cad_equivalent": null, "prepared_by": null, "verified_by": null },
  "letter_of_authorization": { "letter_date": null, "addressed_to": null, "pickup_date": null, "delivery_date": null,
                               "contract_numbers": [], "consignor_lines": [], "delivery_address_lines": [],
                               "contents_description": null, "denominations_text": null,
                               "value_cad": null, "authorized_by": null },
  "missing_fields": [],
  "extraction_notes": []
}
```

Fill only the object that matches `document_type`; set the others to null.

## 5. Field spec (where each value comes from)

| Extraction field | Printed label / location | Format and parsing hint |
|---|---|---|
| shipment_id | "Shipment :" | `YYZ-<7 digits>-YYZ-<n>` |
| document_date | "Date" top right | `yyyy/mm/dd` -> ISO |
| reference_deal_numbers | "Reference :" | 13 digits; split on comma |
| consignor_name | "Consignor :" | text before first `, CA-` |
| shipper / consignee blocks | "Shipper" / "Consignee" table cells | Postal line: `CA - <A1A1A1> <City>`; unit appears as `#n`, `Suite n` or `Unit n`; a lone number on its own line can be the unit (e.g. `4`) or the building (e.g. `5617`) - return it as printed in address_lines and let the mapping step split it |
| pickup / delivery | "Pickup date" / "Delivery date" | `yyyy/mm/dd hh:mm - yyyy/mm/dd`; the second date is not a time |
| goods_value | "Goods value" | `355,381.21 CAD` |
| bags, weight_kg | row under "Qty." and "Weight KG/LB" | weight shown as `6 / 13.23` (kg / lb) |
| seals | "Seals (total n)" | seal count must equal n |
| custody_signatures | "Custody signature 1-3" | blank dotted lines mean null; set `signature_present` only if text or mark is present |
| deal_no | "Deal no :" | `<13 digits>- 1` |
| travelex_side | "Travelex :" | BUY or SELL |
| legs | table "Leg CCY BN Type Denom. No. of Pcs Amount Deal Rate Settlement Amt" | `MIXED` denomination and blank pieces allowed on CAD legs; pieces use thousands separators (`4,000`) |
| total, total_settlement, settlement_local_equivalent | lines below the table | can differ from each other (see 6.3) |
| external_remarks | "External Remarks :" | verbatim; may hold a person's name; role unknown |

## 6. Validation rules (run after extraction, in the flow, not in the model)

| # | Check | On failure |
|---|---|---|
| 6.1 | Sum of leg `settlement_amt` = ticket `total` (tolerance 0.01) | Route to exceptions |
| 6.2 | Sum of all ticket totals for a DO = DO `goods_value` (tolerance 0.01) | Route to exceptions |
| 6.3 | `total_settlement` = `settlement_local_equivalent` | Warn (sample YYZ-1057030 differs by 25.59) |
| 6.4 | `denomination x pieces = amount` for each leg with numeric denomination | Route to exceptions |
| 6.5 | Count of `seals` = "Seals (total n)" | Warn |
| 6.6 | Every deal number in `Reference` has a matching ticket | Route to exceptions (ticket missing) |
| 6.7 | Shipper or consignee address on the DO matches the ticket's SDI address for the customer | Warn (sample YYZ-1057066 mismatch) |
| 6.8 | `custody_signatures.time` is null | Flag "no actual receipt time" (blocking for FINTRAC) |
| 6.9 | Incoming log: `amount x cad_rate` = `cad_equivalent`; denominations in the letter sum to the amount | Warn |
| 6.10 | Letter date is after pickup/delivery date | Warn (sample BofA letter) |

Note: per-leg `settlement_amt` can differ from `amount x deal_rate` by up to about CAD 0.70 because rates print to 6 decimals. Never recompute; use the printed settlement.

## 7. Exception handling

- Route to a review list with: source file, shipment ID, failed check, extracted values, and the original page reference.
- Never retry silently with a different interpretation. A failed sum means a missing or mis-split row.
- Log every extraction (input hash, output JSON, checks passed or failed) for audit.

## 8. Test cases (from the 6 samples)

| Source | Expected |
|---|---|
| YYZ-1057026-YYZ-1 (12-page PDF, first order) | 1 DO, 1 ticket, 42 legs, 14 currencies, total 355,381.21, seals 2, BUY |
| YYZ-1057030-YYZ-1 | 7 legs, total 149,055.00, local equivalent 149,029.41 (6.3 warns), SELL |
| YYZ-1057061-YYZ-1 | 2 tickets (...030 and ...023), 4 + 12 legs, totals 17,028.30 and 108,678.07, DO value 125,706.37 |
| YYZ-1057065-YYZ-1 | 3 EUR legs, total 58,396.87 |
| YYZ-1057066-YYZ-1 | 1 CAD leg (MIXED), 115,380.00, BUY, address mismatch warning (6.7) |
| BofA log + letter | MXN 1,900,000 at 0.0796 = CAD 151,240.00; 4 denominations summing to 1,900,000; letter-date warning (6.10); no shipment ID |

Total across all six: 73 legs and CAD 955,159.45.

## 9. Open items before building

1. Confirm the PDF-to-text path and that it preserves page order and table rows.
2. Get a few more document samples (other consignors, 3+ tickets per DO, non-CAD settlement) to test the schema.
3. Decide where exceptions land (Teams, SharePoint list, or Excel) and who owns review.
4. The mapping from this JSON to FINTRAC fields is in the workbook's Field Mapping sheet; its open items (conductor, identifiers, method code, disposition) are Loomis compliance decisions, not extraction work.
