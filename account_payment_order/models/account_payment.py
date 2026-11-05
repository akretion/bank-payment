# Copyright 2019 ACSONE SA/NV
# Copyright 2022 Tecnativa - Pedro M. Baeza
# Copyright 2024 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.tools import float_compare


class AccountPayment(models.Model):
    _inherit = "account.payment"

    payment_order_id = fields.Many2one(comodel_name="account.payment.order")
    payment_line_ids = fields.Many2many(comodel_name="account.payment.line")
    payment_line_date = fields.Date(compute="_compute_payment_line_date")
    # Compatibility with previous approach for returns - To be removed on v16
    old_bank_payment_line_name = fields.Char()

    def _get_default_journal(self):
        res = super()._get_default_journal()
        return res.filtered(lambda journal: not journal.inbound_payment_order_only)

    @api.depends(
        "payment_type",
        "journal_id.inbound_payment_method_ids",
        "journal_id.outbound_payment_method_ids",
    )
    def _compute_payment_method_fields(self):
        res = super()._compute_payment_method_fields()
        for pay in self:
            if pay.payment_type == "inbound":
                pay.available_payment_method_ids = (
                    pay.journal_id.inbound_payment_method_ids.filtered(
                        lambda m: not m.payment_order_only
                    )
                )
            else:
                pay.available_payment_method_ids = (
                    pay.journal_id.outbound_payment_method_ids.filtered(
                        lambda m: not m.payment_order_only
                    )
                )

            pay.hide_payment_method = (
                len(pay.available_payment_method_ids) == 1
                and pay.available_payment_method_ids.code == "manual"
            )
        return res

    @api.depends("payment_line_ids", "payment_line_ids.date")
    def _compute_payment_line_date(self):
        for item in self:
            item.payment_line_date = item.payment_line_ids[:1].date

    def _prepare_move_line_default_vals(self, write_off_line_vals=None):
        """Overwrite date_maturity of the move_lines that are generated when related
        to a payment order.
        """
        vals_list = super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals
        )
        if not self.payment_order_id:
            return vals_list
        for vals in vals_list:
            vals["date_maturity"] = self.payment_line_ids[:1].date
        return vals_list

    def _reconcile_payment_lines(self):
        self.ensure_one()
        payment_move_line_id = self.move_id.line_ids.filtered(
            lambda x: x.account_id == self.destination_account_id
        )
        apr = self.env["account.partial.reconcile"]
        excl_pay_lines = self.env["account.payment.line"]
        for line in self.payment_line_ids:
            if not line.move_line_id:
                continue
            sign = -1 if self.payment_order_id.payment_type == "outbound" else 1
            if (
                float_compare(
                    line.amount_currency,
                    (line.move_line_id.amount_residual_currency * sign),
                    precision_rounding=line.move_line_id.currency_id.rounding,
                )
                != 0
            ):
                if line.move_line_id.amount_residual_currency < 0:
                    debit_move_id = payment_move_line_id.id
                    credit_move_id = line.move_line_id.id
                else:
                    debit_move_id = line.move_line_id.id
                    credit_move_id = payment_move_line_id.id
                apr.create(
                    {
                        "debit_move_id": debit_move_id,
                        "credit_move_id": credit_move_id,
                        "amount": abs(line.amount_company_currency),
                        "debit_amount_currency": abs(line.amount_currency),
                        "credit_amount_currency": abs(line.amount_currency),
                    }
                )
                excl_pay_lines |= line
        pay_lines = self.payment_line_ids - excl_pay_lines
        if pay_lines:
            (pay_lines.move_line_id + payment_move_line_id).reconcile()
