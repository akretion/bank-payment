# Copyright 2024 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, models
from odoo.exceptions import UserError


class AccountPaymentLine(models.Model):
    _inherit = "account.payment.line"

    def draft2open_payment_line_check(self):
        self.ensure_one()
        order = self.order_id
        if (
            order.payment_mode_id.payment_method_id.code == "check_payment_order"
            and self.currency_id != order.company_id.currency_id
        ):
            raise UserError(
                _(
                    "Checks can only be used to pay in the company currency. "
                    "On payment line %(payline)s of payment order %(order)s, "
                    "the currency is %(payline_currency)s whereas the company currency "
                    "is %(company_currency)s.",
                    payline=self.display_name,
                    order=order.display_name,
                    payline_currency=self.currency_id.name,
                    company_currency=order.company_id.currency_id.name,
                )
            )
        return super().draft2open_payment_line_check()
