# Copyright 2026 Akretion
# @author Guillaume MASSON <guillaume.masson@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _prepare_payment_line_vals(self, payment_order):
        vals = super()._prepare_payment_line_vals(payment_order)
        if (
            payment_order.payment_mode_id.netting
            and self.move_id.move_type != "in_invoice"
        ):
            vals["partner_bank_id"] = self._get_netting_partner_bank(payment_order).id
        return vals

    def _get_netting_partner_bank(self, payment_order):
        supplier_invoice_lines = payment_order.payment_line_ids.filtered(
            lambda line: line.partner_id == self.partner_id
            and line.move_line_id.move_id.move_type == "in_invoice"
            and line.partner_bank_id
        )
        return supplier_invoice_lines.partner_bank_id[:1] or (
            self.partner_id.bank_ids.filtered(
                lambda bank: bank.company_id
                in (payment_order.company_id, bank.browse())
            )[:1]
        )

    def create_payment_line_from_move_line(self, payment_order):
        if not payment_order.payment_mode_id.netting:
            return super().create_payment_line_from_move_line(payment_order)
        supplier_invoice_lines = self.filtered(
            lambda line: line.move_id.move_type == "in_invoice"
        )
        return super(
            AccountMoveLine, supplier_invoice_lines
        ).create_payment_line_from_move_line(payment_order) | super(
            AccountMoveLine, self - supplier_invoice_lines
        ).create_payment_line_from_move_line(
            payment_order
        )
