# Copyright 2026 Akretion
# @author Guillaume MASSON <guillaume.masson@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountPaymentMode(models.Model):
    _inherit = "account.payment.mode"

    netting = fields.Boolean(
        help="Allow receivables as negative lines of outbound payment orders: "
        "each transfer pays the net amount of its lines.",
    )

    @api.constrains("netting", "payment_method_id")
    def _check_netting_outbound(self):
        for mode in self:
            if mode.netting and mode.payment_type != "outbound":
                raise ValidationError(
                    _(
                        "Payment mode %(name)s can't use netting: "
                        "it isn't an outbound payment mode.",
                        name=mode.name,
                    )
                )
