"""Chart of accounts.

Balances are reported as ``debits - credits``; liability, revenue and
contra accounts therefore usually show negative balances.
"""

CASH = "1000_cash"
ACCOUNTS_RECEIVABLE = "1100_accounts_receivable"
TAX_PAYABLE = "2100_tax_payable"
CUSTOMER_CREDIT = "2200_customer_credit"
REVENUE = "4000_revenue"
BAD_DEBT = "6100_bad_debt_expense"

ACCOUNTS = {
    CASH: "asset",
    ACCOUNTS_RECEIVABLE: "asset",
    TAX_PAYABLE: "liability",
    CUSTOMER_CREDIT: "liability",
    REVENUE: "revenue",
    BAD_DEBT: "expense",
}
