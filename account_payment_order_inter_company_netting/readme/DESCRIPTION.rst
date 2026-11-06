Glue between ``account_payment_order_netting`` and
``account_payment_order_inter_company``.

A netted payment gets the mirror entry of
``account_payment_order_inter_company``: one line per payment line, with the
opposite sign, on the account of the linked inter-company invoice, reconciled
with it. A paid supplier invoice credits the receivable account, a netted
customer invoice debits the payable account.

A mirror line is left unreconciled, with a message on the payment order, when:

* the netted line has no linked invoice: booked on the partner's payable account;
* the linked invoice is not posted, its line is already fully reconciled, or it
  doesn't have the same number of installments as the netted invoice: booked on
  the account of the linked invoice.

A netted line on the paying company's dividend receivable account is a dividend:
its mirror line goes on the receiving company's dividend payable account. It is
reconciled only when exactly one open line of that account matches (partner =
paying company or empty, residual = amount). Otherwise it is left open, with a
message on the payment order. Two dividends of the same amount in one source are
both left open.

A net-zero group has no payment but its entry gets a mirror too: same lines, no
outstanding line, in the receiving company's inter-company netting journal. It
follows its source: reset to draft, cancelled or deleted with it. Posting the
source again doesn't post the mirror.
