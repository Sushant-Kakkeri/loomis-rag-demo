# LCTR Extraction Agent: Instructions and Field Spec

Scope: Loomis delivery orders and trade tickets (Travelex flow), Bank of America shipment documents, and import shipments documented by a Letter of Authorization plus a CBSA Form E667E.
Status: DRAFT v0.2, built from 8 sample shipments (adds Deutsche Bundesbank and Numisma imports). Not validated against any other layout.
Companion files: `LCTR_Demo_Workbook.xlsx` (mapping, gaps, data quality), `LCTR_draft_payload.json` (8 draft reports) and `lctr-schema.json` (FINTRAC schema, draft-07).

## 1. Design

The agent only **extracts what is printed on the documents**. It does not build the FINTRAC payload and does not fill in FINTRAC identifiers, indicators or codes. A separate mapper maps the extraction JSON to the FINTRAC LCTR structure using the Field Mapping sheet. The staging application then validates (section 6) and routes problems to a reviewer before anything is sent to FINTRAC.

Pipeline: documents -> extraction JSON (this agent) -> mapper -> candidate payload -> staging validation (schema + reconciliation + completeness) -> review queue -> FINTRAC API.

Assumption: the PDF text (or OCR text) is supplied to the agent as plain text, plus page images where checkboxes matter (see rule 13). The PDF-to-text step is outside this spec. Trade-ticket tables can break across pages (the first sample ticket does), so the text must keep page order.

Why this split: extraction can be tested against the documents. Reportability, conductor identity, disposition and 24-hour-rule treatment are compliance decisions and must not be guessed by a model.

Important: **every sender uses its own Letter of Authorization layout** (three seen so far). Do not rely on fixed positions. Extract by label and meaning, and let the validation checks catch errors.

## 2. Document types the agent must recognise

| Type | How to recognise | Notes |
|---|---|---|
| Loomis Delivery Order | Title "Delivery Order", Loomis International (CA) Inc. header, "Shipment : YYZ-..." | One per shipment; 1 page |
| Trade Ticket Insert | "TRADE TICKET INSERT", "Deal no : <digits>- 1" | 1 or more follow each Delivery Order; one DO can reference two deals (comma-separated Reference) |
| Incoming Cash Shipment Log | "Incoming Cash Shipment log", bank header | BofA format; no shipment ID |
| Letter of Authorization | Title contains "Letter of Authorization" and "Commercial Invoice" | 3 layouts seen: BofA domestic (CONSIGNOR + Delivery Address, contract number); Deutsche Bundesbank (Consignor and Consignee name/address blocks, "REF:"); Numisma (Deal Number, CONSIGNOR, CONSIGNEE, PICK UP LOCATION, denomination table) |
| CBSA Form E667E | "CROSS-BORDER CURRENCY OR MONETARY INSTRUMENTS REPORT - GENERAL", parts A to E | 6 pages; two editions seen, E667E (21) and (24). Goes to CBSA, not FINTRAC, but supplies party details and a CAD value |

Pair a Trade Ticket to a Delivery Order when its deal number appears in the DO's `Reference` field. Pair an E667 to its Letter by matching consignor/consignee names, currency and amount.

## 3. Agent instructions (paste into Copilot Studio)

```
You extract structured data from cash-shipment documents for a compliance reporting workflow.

RULES
1. Extract only what is printed in the document text. Never infer, guess, or fill from general knowledge.
2. If a value is absent or illegible, return null and add the field name to "missing_fields". Do not substitute a similar value.
3. Copy names, addresses and numbers exactly as printed, including misspellings. Do not translate, abbreviate, or correct spelling. Put any normalisation in separate "_normalized" fields only where the schema asks for it.
4. Dates: return ISO 8601 (yyyy-mm-dd). Times: return hh:mm 24-hour, or null. Do not add a time zone. Dates written dd/mm vs mm/dd: copy the printed text into "_raw" and add a note if the order is ambiguous.
5. Amounts: return numbers with a dot as the decimal separator and no thousands separators.
6. A Delivery Order may be followed by one or more Trade Tickets. A comma-separated "Reference" lists their deal numbers. Return one trade_tickets[] entry per ticket, in document order. A ticket table may continue on the next page; keep reading until "Total :" appears.
7. Return every trade-ticket leg as its own row. Never merge or skip rows. If two rows appear on one text line because of a page break, split them using the leg numbers.
8. "External Remarks" and "Internal Remarks" are free text. Copy them verbatim into remarks fields. Do NOT treat a name there as a customer, conductor or any other role.
9. Do not decide whether anything is reportable. Do not output FINTRAC codes.
10. Return JSON only, matching the schema below. No commentary.
11. Letter-spaced text (character-box forms such as the E667 print as "D E U T S C H E"): join the characters into words. Keep a single space where there is a clear wider gap between words.
12. On the E667, a long name can continue into the "First name" line, marked "(cont.)". Join it to the name field and return one name.
13. Checkboxes (Import/Export, Courier/Mail/Other, ID type) are not in the text layer. Set a checkbox only when a ticked mark is visible in the page image supplied. If no image is available, return null and add the field to "missing_fields".
14. Personal data: on the E667, return the transporter's date of birth and identification number as null unless the input contains the line RESTRICTED_FIELDS_ALLOWED. Never copy them into notes or any other field.
15. A Letter lists denominations as "quantity X denomination" (4000X50 means 4000 notes of 50). Return pieces and denomination separately.

If the input is not one of the five known document types, return {"document_type": "unknown"} and nothing else.
```

## 4. Output schema (extraction JSON)

```json
{
  "document_type": "delivery_order | trade_ticket | incoming_cash_log | letter_of_authorization | cbsa_e667 | unknown",
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
  "letter_of_authorization": {
    "layout": "bofa_domestic | bundesbank | numisma | other",
    "letter_date": null, "letter_timestamp_note": null, "addressed_to": null,
    "pickup_date": null, "pickup_location_text": null, "delivery_date": null, "delivery_location_text": null,
    "references": [{ "label": "Contract Numbers | REF | Deal Number", "value": "" }],
    "consignor": { "name": null, "address_lines": [] },
    "consignee_or_delivery_address": { "name": null, "address_lines": [] },
    "pickup_location": { "name": null, "address_lines": [] },
    "contents_description": null,
    "currency_lines": [{ "ccy": "EUR", "amount": 5850000.00,
                         "denominations": [{ "denomination": 50000, "pieces": 5 }] }],
    "stated_value": { "label": "USD Value | Value | Total CAD", "currency": null, "amount": null },
    "weight_text": null, "pieces_text": null, "fast_packs": null,
    "prepared_by": null, "verified_or_authorized_by": null
  },
  "cbsa_e667": {
    "form_edition": "E667E (24)",
    "import_or_export": null, "method_of_shipment": null,
    "date_of_shipment": null, "date_of_shipment_legible": true, "date_of_report": null,
    "part_a_transporter": { "surname": null, "first_name": null, "address_lines": [], "city": null,
                            "province": null, "postal_code": null, "country": null, "telephone": null,
                            "citizenship": null, "id_type_text": null, "date_of_birth": null, "id_number": null },
    "part_b_entity": { "name": null, "nature_of_business": null, "address_lines": [], "city": null, "province": null,
                       "postal_code": null, "country": null, "telephone": null,
                       "contact_name": null, "contact_title": null, "registration_country": null, "registration_province": null },
    "part_c_person": null,
    "shipped_to": { "name": null, "address_lines": [], "city": null, "province": null, "postal_code": null, "country": null },
    "shipped_from": { "name": null, "address_lines": [], "city": null, "province": null, "postal_code": null, "country": null },
    "courier": { "name": null, "address_lines": [], "telephone": null, "contact_name": null, "contact_title": null },
    "ultimate_origin": { "name": null, "nature_of_business": null, "address_lines": [] },
    "ultimate_destination": { "name": null, "nature_of_business": null, "address_lines": [] },
    "departure": { "city": null, "country": null, "date": null },
    "arrival": { "city": null, "country": null, "date": null },
    "currency_lines": [{ "currency": "EUR", "country_of_origin": null, "purpose": null,
                         "amount": 5850000.00, "cad_rate": 1.6000842, "cad_amount": 9360492.57 }],
    "grand_total_cad": null,
    "declaration": { "name": null, "signature_present": false }
  },
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
| letter.references | "Contract Numbers:", "REF:" or "Deal Number:" | keep the printed label; one letter can have more than one |
| letter dates | "Date", "Pick-up Date", "Delivery Date" | The Bundesbank letter prints `10/07/26` and `10/09/26`. These are mm/dd/yy (7 and 9 October), which the matching E667 date of 2026-10-07 confirms. Note the ambiguity per rule 4 |
| letter.consignor / consignee | "CONSIGNOR", "Consignee", "Delivery Address" blocks | name line(s) then address lines; keep c/o lines |
| letter.pickup_location | "PICK UP LOCATION" (Numisma) or "Location:" next to the pick-up date (Bundesbank) | may differ from the consignor |
| letter.currency_lines | "Curr Amount Denomination Breakdown", "CCY FCY Amount Denomination", or a USD denomination table | denominations are `quantity X denomination` (Bundesbank, BofA) or a table of Denom, Quantity, Total (Numisma) |
| letter.stated_value | "USD Value", "VALUE:", "Total CAD $" | label can be wrong for the currency (Bundesbank labels EUR 5,850,000 as a USD value) - copy the label as printed |
| e667.import_or_export, method | Part D tick boxes | read from the page image only (rule 13) |
| e667.date_of_shipment | Part D, character boxes | set `date_of_shipment_legible` to false when overtyped or unclear (Numisma form: 13 with 9 above) |
| e667.part_a | Part A | personal data; rule 14 applies to date of birth and ID number |
| e667.shipped_to / shipped_from | Part D | name can continue into "first name" (rule 12) |
| e667.currency_lines | Part E table | `amount x cad_rate = cad_amount`; the form prints the rate to 4 to 8 decimals |
| e667.grand_total_cad | Part E "GRAND TOTALS" | CAD |

## 6. Validation rules (run after extraction, in the staging application, not in the model)

Three layers: **schema** (the mapped payload against `lctr-schema.json`), **reconciliation** (the checks below), and **completeness** (every `<<REQUIRED>>` or null mandatory field becomes a "needs input" flag).

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
| 6.11 | Letter: for each currency line, sum of `denomination x pieces` = `amount` | Route to exceptions |
| 6.12 | E667: for each currency line, `amount x cad_rate` = `cad_amount` (tolerance 0.01), and the sum of lines = `grand_total_cad` | Route to exceptions |
| 6.13 | Paired Letter and E667 agree on currency, amount, consignor and consignee (name match after case and punctuation are ignored) | Route to exceptions |
| 6.14 | E667 shipment, departure and arrival dates fall inside the Letter's pick-up to delivery window, and `date_of_shipment_legible` is true | Warn (Numisma: date of shipment unclear) |
| 6.15 | Letter `stated_value` currency matches the currency line (Bundesbank: label says USD, line is EUR) | Warn |
| 6.16 | Mapped payload validates against `lctr-schema.json` (placeholders excluded) | Route to exceptions |
| 6.17 | Required import/export tick box and method were readable (rule 13) | Warn |

Note: per-leg `settlement_amt` can differ from `amount x deal_rate` by up to about CAD 0.70 because rates print to 6 decimals. Never recompute; use the printed settlement. For letters and E667 forms there is no per-leg CAD, so compute `amount x rate` per leg and confirm that the total equals the printed CAD value (it does for all 3 samples).

## 7. Exception handling

- Route to a review list with: source file, shipment ID, failed check, extracted values, and the original page reference.
- Never retry silently with a different interpretation. A failed sum means a missing or mis-split row.
- Log every extraction (input hash, output JSON, checks passed or failed) for audit.
- Restrict access to E667 personal data (rule 14) and keep it out of logs and exception emails.

## 8. Test cases (from the 8 samples)

| Source | Expected |
|---|---|
| YYZ-1057026-YYZ-1 (12-page PDF, first order) | 1 DO, 1 ticket, 42 legs, 14 currencies, total 355,381.21, seals 2, BUY |
| YYZ-1057030-YYZ-1 | 7 legs, total 149,055.00, local equivalent 149,029.41 (6.3 warns), SELL |
| YYZ-1057061-YYZ-1 | 2 tickets (...030 and ...023), 4 + 12 legs, totals 17,028.30 and 108,678.07, DO value 125,706.37 |
| YYZ-1057065-YYZ-1 | 3 EUR legs, total 58,396.87 |
| YYZ-1057066-YYZ-1 | 1 CAD leg (MIXED), 115,380.00, BUY, address mismatch warning (6.7) |
| BofA log + letter | MXN 1,900,000 at 0.0796 = CAD 151,240.00; 4 denominations summing to 1,900,000; letter-date warning (6.10); no shipment ID |
| Deutsche Bundesbank letter + E667 | EUR 5,850,000; 5 denominations (5, 10, 20, 50, 100) sum to 5,850,000; E667 rate 1.6000842 gives CAD 9,360,492.57; 6.15 warns (letter says USD value 6,585,637.50 for EUR); E667 Part B entity at 181 Bay Street vs consignee at 95 Browns Line |
| Numisma letter + E667 | USD 1,680,000; 4 denominations (5, 10, 20, 50) sum to 1,680,000; E667 rate 1.4257 gives CAD 2,395,176.00; 6.14 warns (date of shipment unclear); consignee name split across two E667 fields; 5 fast packs, 83 kg |

Total across all eight: 82 legs and CAD 12,710,828.02.

## 9. Open items before building

1. Confirm the PDF-to-text path and that it preserves page order and table rows. For E667 forms, also supply page images so checkboxes can be read (rule 13).
2. Get more document samples (other consignors, other banks' letters, 3+ tickets per DO, non-CAD settlement) to test the schema. Letter layouts vary by sender.
3. Decide where exceptions land (Teams, SharePoint list, or Excel) and who owns review.
4. The mapping from this JSON to FINTRAC fields is in the workbook's Field Mapping sheet; its open items (conductor, identifiers, method code, disposition, reporting entity for imports) are Loomis compliance decisions, not extraction work.
5. Decide whether the staging application receives the full payload or the extraction JSON plus its own mapper, and where one-time configuration (entity numbers, location IDs, entity reference data) lives.
