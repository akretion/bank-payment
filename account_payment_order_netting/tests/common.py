# Copyright 2026 Akretion
# @author Guillaume MASSON <guillaume.masson@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class NettingCommon(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env.user.groups_id = [
            (4, cls.env.ref("account_payment_order.group_account_payment").id)
        ]
        cls.company = cls.company_data["company"]
        cls.payable_account = cls.company_data["default_account_payable"]
        cls.receivable_account = cls.company_data["default_account_receivable"]
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.outstanding_account = cls.bank_journal.payment_credit_account_id
        cls.partner = cls.env["res.partner"].create({"name": "Netting Partner"})
        cls.bank_a, cls.bank_b = cls.env["res.partner.bank"].create(
            [
                {"acc_number": acc_number, "partner_id": cls.partner.id}
                for acc_number in ("FR7600001", "FR7600002")
            ]
        )
        cls.bank_journal.bank_account_id = cls.env["res.partner.bank"].create(
            {"acc_number": "FR7600003", "partner_id": cls.company.partner_id.id}
        )
        payment_method = cls.env.ref("account.account_payment_method_manual_out")
        payment_method.sudo().bank_account_required = True
        cls.netting_mode = cls.env["account.payment.mode"].create(
            {
                "name": "Netting transfer",
                "company_id": cls.company.id,
                "bank_account_link": "fixed",
                "fixed_journal_id": cls.bank_journal.id,
                "payment_method_id": payment_method.id,
                "group_lines": True,
                "netting": True,
            }
        )

    @classmethod
    def _create_invoice(
        cls,
        move_type,
        amount,
        partner=None,
        date_due=None,
        open_account=None,
        currency=None,
    ):
        account = (
            cls.company_data["default_account_expense"]
            if move_type in ("in_invoice", "in_refund")
            else cls.company_data["default_account_revenue"]
        )
        invoice = cls.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": (partner or cls.partner).id,
                "invoice_date": fields.Date.today(),
                "currency_id": (currency or cls.company.currency_id).id,
                "ref": f"{move_type} {amount}",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": f"{move_type} line",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": account.id,
                            "tax_ids": [(5,)],
                        },
                    )
                ],
            }
        )
        if date_due:
            cls._open_line(invoice).date_maturity = date_due
        if open_account:
            cls._open_line(invoice).account_id = open_account
        invoice.action_post()
        return invoice

    @classmethod
    def _create_debit_entry(cls, account, amount, partner=None):
        entry = cls.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": cls.company_data["default_journal_misc"].id,
                "ref": f"Debit {amount}",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Debit",
                            "account_id": account.id,
                            "partner_id": (partner or cls.partner).id,
                            "debit": amount,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Counterpart",
                            "account_id": cls.company_data[
                                "default_account_revenue"
                            ].id,
                            "credit": amount,
                        },
                    ),
                ],
            }
        )
        entry.action_post()
        return entry

    @classmethod
    def _open_line(cls, move):
        return move.line_ids.filtered(
            lambda line: line.account_id.reconcile and line.partner_id
        )

    def _create_order(self, move_lines, mode=None):
        order = self.env["account.payment.order"].create(
            {
                "payment_type": "outbound",
                "payment_mode_id": (mode or self.netting_mode).id,
            }
        )
        move_lines.create_payment_line_from_move_line(order)
        return order

    def _confirm(self, order):
        order.draft2open()
        return order

    def _upload(self, order):
        if order.state == "draft":
            order.draft2open()
        order.open2generated()
        order.generated2uploaded()
        return order
