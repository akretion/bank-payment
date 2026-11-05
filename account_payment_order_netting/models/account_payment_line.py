# Copyright 2026 Akretion
# @author Guillaume MASSON <guillaume.masson@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPaymentLine(models.Model):
    _inherit = "account.payment.line"

    @api.constrains("amount_currency", "move_line_id", "order_id")
    def _check_netting_line(self):
        for line in self:
            currency = line.currency_id
            if not (
                line.order_id.payment_mode_id.netting
                and currency.compare_amounts(line.amount_currency, 0) < 0
            ):
                continue
            move_line = line.move_line_id
            if (
                not move_line
                or move_line.balance <= 0
                or move_line.partner_id.commercial_partner_id
                != line.partner_id.commercial_partner_id
            ):
                raise ValidationError(
                    _(
                        "Payment line %(name)s is negative: it must be linked "
                        "to a debit journal item of its partner.",
                        name=line.name,
                    )
                )
            journal = line.order_id.journal_id
            if move_line.account_id in (
                journal.default_account_id
                | journal.payment_debit_account_id
                | journal.payment_credit_account_id
            ):
                raise ValidationError(
                    _(
                        "Payment line %(name)s can't net journal item "
                        "%(move_line)s: its account is a liquidity account of "
                        "journal %(journal)s.",
                        name=line.name,
                        move_line=move_line.display_name,
                        journal=journal.display_name,
                    )
                )
            netted_amount = -sum(
                line.order_id.payment_line_ids.filtered(
                    lambda other, move_line=move_line: other.move_line_id == move_line
                ).mapped("amount_currency")
            )
            if (
                currency.compare_amounts(
                    netted_amount, move_line.amount_residual_currency
                )
                > 0
            ):
                raise ValidationError(
                    _(
                        "On payment line %(name)s, the netted amount "
                        "%(amount).2f exceeds the residual %(residual).2f "
                        "of journal item %(move_line)s.",
                        name=line.name,
                        amount=netted_amount,
                        residual=move_line.amount_residual_currency,
                        move_line=move_line.display_name,
                    )
                )

    def _payment_line_grouping_account_key(self):
        if self.order_id.payment_mode_id.netting:
            return False
        return super()._payment_line_grouping_account_key()

    def _prepare_write_draft2open(self):
        vals = super()._prepare_write_draft2open()
        order = self.order_id
        if order.payment_mode_id.netting:
            today = fields.Date.context_today(self)
            order_date = (
                order.date_prefered == "fixed" and order.date_scheduled or today
            )
            vals["date"] = max(today, order_date)
        return vals

    def draft2open_payment_line_check(self):
        res = super().draft2open_payment_line_check()
        self._check_netting_line()
        if (
            self.order_id.payment_mode_id.netting
            and self.communication_type != "normal"
            and self.currency_id.compare_amounts(self.amount_currency, 0) < 0
        ):
            raise UserError(
                _(
                    "Payment line %(name)s has a structured reference: "
                    "it can't be netted.",
                    name=self.name,
                )
            )
        return res

    def _prepare_account_payment_vals(self):
        if not self.order_id.payment_mode_id.netting:
            return super()._prepare_account_payment_vals()
        paylines = self.sorted("amount_currency", reverse=True)
        vals = super(AccountPaymentLine, paylines[:1])._prepare_account_payment_vals()
        vals.update(
            {
                "amount": sum(paylines.mapped("amount_currency")),
                "date": paylines[:1].date,
                "payment_reference": " - ".join(paylines.mapped("communication")),
                "payment_line_ids": [(6, 0, paylines.ids)],
            }
        )
        return vals
