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
        counterpart_vals_list = [
            payline._prepare_netting_move_line_vals(
                self.date, self.destination_account_id
            )
            for payline in self.payment_line_ids
        ]
        liquidity_balance = self.company_id.currency_id.round(
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
        self.payment_line_ids._reconcile_netting_counterparts(
            counterpart_lines | writeoff_lines
        )
