# Copyright 2024 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, models
from odoo.exceptions import ValidationError


class AccountPaymentMode(models.Model):
    _inherit = "account.payment.mode"

    @api.constrains("default_date_prefered", "payment_method_id")
    def _constrains_check_print(self):
        for mode in self:
            if (
                mode.payment_method_id.code == "check_payment_order"
                and mode.default_date_prefered != "now"
            ):
                raise ValidationError(
                    _(
                        "On the payment mode '%s' configured with the payment "
                        "method 'Check Payment Order', the Payment Execution Date Type "
                        "must be 'Immediately'."
                    )
                    % mode.display_name
                )
