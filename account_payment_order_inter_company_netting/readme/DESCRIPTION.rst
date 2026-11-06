Glue between ``account_payment_order_netting`` and
``account_payment_order_inter_company``.

A netted payment gets the mirror entry of
``account_payment_order_inter_company``: one line per payment line, with the
opposite sign, on the account of the linked inter-company invoice, reconciled
with it. A paid supplier invoice credits the receivable account, a netted
customer invoice debits the payable account. A netted line without linked
invoice is booked on the partner's payable account, left unreconciled, with a
message on the payment order.
