# Copyright 2026 Akretion
# @author Guillaume MASSON <guillaume.masson@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _is_netting(self):
        self.ensure_one()
        return bool(
            self.payment_order_id.payment_mode_id.netting and self.payment_line_ids
        )

    def _prepare_move_line_default_vals(self, write_off_line_vals=None):
        vals_list = super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals
        )
        if not self._is_netting():
            return vals_list
        liquidity_vals = vals_list[0]
        company = self.company_id
        counterpart_vals_list = []
        for payline in self.payment_line_ids:
            balance = self.currency_id._convert(
                payline.amount_currency, company.currency_id, company, self.date
            )
            counterpart_vals_list.append(
                {
                    "name": payline.communication,
                    "date_maturity": liquidity_vals["date_maturity"],
                    "partner_id": self.partner_id.id,
                    "account_id": (
                        payline.move_line_id.account_id or self.destination_account_id
                    ).id,
                    "currency_id": self.currency_id.id,
                    "amount_currency": payline.amount_currency,
                    "debit": max(balance, 0.0),
                    "credit": max(-balance, 0.0),
                }
            )
        liquidity_balance = company.currency_id.round(
            sum(vals["credit"] - vals["debit"] for vals in counterpart_vals_list)
        )
        liquidity_vals.update(
            {
                "debit": max(liquidity_balance, 0.0),
                "credit": max(-liquidity_balance, 0.0),
            }
        )
        return [liquidity_vals] + counterpart_vals_list

    def _synchronize_from_moves(self, changed_fields):
        payments = self.filtered(lambda pay: not pay._is_netting())
        return super(AccountPayment, payments)._synchronize_from_moves(changed_fields)

    def _synchronize_to_moves(self, changed_fields):
        payments = self.filtered(lambda pay: not pay._is_netting())
        return super(AccountPayment, payments)._synchronize_to_moves(changed_fields)

    def _reconcile_payment_lines(self):
        if not self._is_netting():
            return super()._reconcile_payment_lines()
        _liquidity_lines, counterpart_lines, writeoff_lines = self._seek_for_lines()
        counterpart_lines |= writeoff_lines
        for payline in self.payment_line_ids.filtered("move_line_id"):
            counterpart = counterpart_lines.filtered(
                lambda line, payline=payline: line.account_id
                == payline.move_line_id.account_id
                and self.currency_id.compare_amounts(
                    line.amount_currency, payline.amount_currency
                )
                == 0
            )[:1]
            counterpart_lines -= counterpart
            (counterpart | payline.move_line_id).reconcile()
