# Ferretería Don Perno (Bucaramanga)

_Bucaramanga hardware store with two accounts and a business card, whose biggest customer brings about a third of income and has started paying later._

## Story

Hernán Prueba Duarte runs a hardware store with five employees. Walk-in sales come by card and cash into the checking account, small contractors pay by transfer, and a construction company buys on 30-day invoices worth about $10,000 a month, about a third of income. That company pays into the savings account; two business days later Hernán moves the money to checking. Some purchases go on the business Visa, which is paid in full from checking every month.

Until spring 2026 the construction company paid on time. Since May each invoice has been paid later (6, 11, 15, 20 days late...); the September invoice will arrive 26 days late and the October one 30 days late. Cash on 2026-11-10 is $12,101.54 across both accounts and bottoms at about $5,750 before the next payment, just above the $5,000 minimum. One more month of delay would take it below.

## What it tests

- Transfers between the two own accounts must be neither income nor spending.
- Card purchases are spending once; PAGO TARJETA from checking is only paying the card.
- Card balance is debt, not cash; total cash = checking + savings.
- Concentration (>30% from one customer) and customers_paying_later must both appear.
- Owner pay (TRANSF A CTA AHORROS H PRUEBA) looks like an internal transfer but is not.

## Tricky parts

- Checking: separate Débito/Crédito columns, empty cell = zero, amounts like 1,250.00 in a comma-delimited file (quoted).
- Savings: semicolon-separated, decimal comma, newest line first, no GMF lines.
- Card statement in English with month-first dates (11/25/2025) and a positive 'Balance owed'.
- The same internal transfer appears in two files with different descriptions.
- TRANSF 0093 REF 61107 is truck leasing (category loan).
- The owner's ledger total must match what the big customer owes on 2026-11-10.

## Key numbers (from the ground truth)

- Cash on 2026-11-10: $12,101.54 (low-cash line $5,000.00)
- True lowest in the next 8 weeks: $5,750.00 on 2026-11-17
- First day below the line: never
- Acceptable risk levels: safe, watch
- Insights that must appear: few_customers, customers_paying_later
- Insights that must not appear: cost_creeping_up, costs_faster_than_sales, duplicate_charge, sales_slowing, net_flow_shrinking, idle_cash

## Solved and automatic values

- Checking balance solved at $8,951.54 so the true lowest total cash in the next 8 weeks is $5,750.00 (115% of the minimum); savings fixed at $3,150.00.

## Files

- `statements/cuenta_corriente_5510.csv`: bank_statement, Corriente 5510, 926 lines, 2025-11-11 to 2026-11-10
- `statements/cuenta_ahorros_7723.csv`: bank_statement, Ahorros 7723, 36 lines, 2025-11-30 to 2026-10-31
- `statements/visa_empresarial_9031.csv`: card_statement, Visa Empresarial 9031, 106 lines, 2025-11-17 to 2026-11-09
- `files/libro_auxiliar_cartera.xlsx`: owner file (ledger), 21 rows
- `files/inventario.xlsx`: owner file (inventory), 14 rows

All names of people and companies are invented.
