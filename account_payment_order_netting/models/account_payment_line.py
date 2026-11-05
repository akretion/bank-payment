# Copyright 2026 Akretion
# @author Guillaume MASSON <guillaume.masson@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPaymentLine(models.Model):
    _inherit = "account.payment.line"

    bank_account_required = fields.Boolean(
        related=None, compute="_compute_bank_account_required"
    )

    @api.depends(
        "order_id.payment_method_id.bank_account_required",
        "order_id.payment_mode_id.netting",
        "order_id.payment_mode_id.group_lines",
        "order_id.payment_line_ids.amount_currency",
        "order_id.payment_line_ids.partner_bank_id",
        "order_id.payment_line_ids.partner_id",
        "order_id.payment_line_ids.currency_id",
        "order_id.payment_line_ids.communication_type",
    )
    def _compute_bank_account_required(self):
        for line in self:
            line.bank_account_required = (
                line.order_id.payment_method_id.bank_account_required
                and not line._is_net_zero_group_without_bank()
            )

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
            if move_line.account_id in line.order_id._get_liquidity_accounts():
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

    def _is_net_zero_group_without_bank(self):
        self.ensure_one()
        payment_mode = self.order_id.payment_mode_id
        if not payment_mode.netting or not payment_mode.group_lines:
            return False
        if self.partner_bank_id:
            return False
        grouping_fields = [
            field
            for field in self._get_payment_line_grouping_fields()
            if field != "date"
        ]
        group_lines = self.order_id.payment_line_ids.filtered(
            lambda line: all(line[field] == self[field] for field in grouping_fields)
        )
        return self.currency_id.is_zero(sum(group_lines.mapped("amount_currency")))

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

    def _prepare_netting_move_line_vals(self, date, default_account):
        self.ensure_one()
        company = self.company_id
        balance = self.currency_id._convert(
            self.amount_currency, company.currency_id, company, date
        )
        return {
            "name": self.communication,
            "date_maturity": date,
            "partner_id": self.partner_id.id,
            "account_id": (self.move_line_id.account_id or default_account).id,
            "currency_id": self.currency_id.id,
            "amount_currency": self.amount_currency,
            "debit": max(balance, 0.0),
            "credit": max(-balance, 0.0),
        }

    def _prepare_netting_move_vals(self):
        order = self.order_id
        date = self[:1].date
        default_account = (
            self[:1]
            .partner_id.with_company(order.company_id)
            .property_account_payable_id
        )
        line_vals_list = [
            payline._prepare_netting_move_line_vals(date, default_account)
            for payline in self.sorted("amount_currency", reverse=True)
        ]
        first_vals = line_vals_list[0]
        first_balance = (
            first_vals["debit"]
            - first_vals["credit"]
            - order.company_id.currency_id.round(
                sum(vals["debit"] - vals["credit"] for vals in line_vals_list)
            )
        )
        first_vals.update(
            {"debit": max(first_balance, 0.0), "credit": max(-first_balance, 0.0)}
        )
        return {
            "move_type": "entry",
            "journal_id": order.journal_id.id,
            "date": date,
            "ref": order.name,
            "netting_payment_order_id": order.id,
            "line_ids": [(0, 0, vals) for vals in line_vals_list],
        }

    def _reconcile_netting_counterparts(self, counterpart_lines):
        for payline in self.filtered("move_line_id"):
            counterpart = counterpart_lines.filtered(
                lambda line, payline=payline: line.account_id
                == payline.move_line_id.account_id
                and payline.currency_id.compare_amounts(
                    line.amount_currency, payline.amount_currency
                )
                == 0
            )[:1]
            counterpart_lines -= counterpart
            (counterpart | payline.move_line_id).reconcile()
