# Copyright 2020 Camptocamp
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    selected_for_payment = fields.Boolean(
        string="To Pay", compute="_compute_selected_for_payment", readonly=False
    )

    def action_toggle_select_for_payment(self):
        selected = self.filtered(lambda rec: rec.selected_for_payment)
        unselected = self - selected
        if selected:
            selected.write({"selected_for_payment": False})
        if unselected:
            unselected.write({"selected_for_payment": True})

    @api.depends("payment_state")
    def _compute_selected_for_payment(self):
        if self.payment_state == "paid":
            self.selected_for_payment = False
