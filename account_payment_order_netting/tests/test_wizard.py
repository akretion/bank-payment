# Copyright 2026 Akretion
# @author Guillaume MASSON <guillaume.masson@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import NettingCommon


@freeze_time("2026-01-15 12:00:00")
@tagged("-at_install", "post_install")
class TestNettingWizard(NettingCommon):
    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.other_partner = cls.env["res.partner"].create({"name": "Other Partner"})

    def _populate(self, order, **vals):
        wizard = (
            self.env["account.payment.line.create"]
            .with_context(active_model=order._name, active_id=order.id)
            .create(
                {
                    "date_type": "due",
                    "payment_mode": "any",
                    "due_date": fields.Date.today() + timedelta(days=30),
                    **vals,
                }
            )
        )
        wizard.populate()
        return wizard

    def _create_inbound_payment(self):
        journal = self.env["account.journal"].create(
            {"name": "Other bank", "type": "bank", "code": "OBNK"}
        )
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner.id,
                "amount": 300,
                "journal_id": journal.id,
            }
        )
        payment.action_post()
        return payment

    def _proposed(self, wizard):
        return wizard.move_line_ids.filtered(
            lambda line: line.partner_id in self.partner | self.other_partner
        )

    def test_receivables_of_selected_payable_partners(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        self._create_invoice("out_invoice", 200, partner=self.other_partner)
        wizard = self._populate(self._create_order(self.env["account.move.line"]))
        self.assertEqual(
            self._proposed(wizard),
            self._open_line(invoice) | self._open_line(customer_invoice),
        )

    def test_receivables_of_order_payable_partners(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        wizard = self._populate(self._create_order(self._open_line(invoice)))
        self.assertEqual(self._proposed(wizard), self._open_line(customer_invoice))

    def test_receivables_same_filters_as_payables(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        self._create_invoice(
            "out_invoice", 100, date_due=fields.Date.today() + timedelta(days=60)
        )
        self._create_invoice("out_invoice", 50).button_draft()
        ordered_invoice = self._create_invoice("out_invoice", 20)
        self._create_order(self._open_line(ordered_invoice))
        wizard = self._populate(self._create_order(self.env["account.move.line"]))
        self.assertEqual(
            self._proposed(wizard),
            self._open_line(invoice) | self._open_line(customer_invoice),
        )

    def test_receivables_excluded(self):
        invoice = self._create_invoice("in_invoice", 1000)
        self._create_invoice("out_invoice", 300)
        wizard = self._populate(
            self._create_order(self.env["account.move.line"]),
            include_receivables=False,
        )
        self.assertEqual(self._proposed(wizard), self._open_line(invoice))

    def test_mode_without_netting(self):
        mode = self.netting_mode.copy({"name": "Plain transfer", "netting": False})
        invoice = self._create_invoice("in_invoice", 1000)
        self._create_invoice("out_invoice", 300)
        wizard = self._populate(
            self._create_order(self.env["account.move.line"], mode=mode)
        )
        self.assertEqual(self._proposed(wizard), self._open_line(invoice))

    def test_receivables_partner_filter(self):
        invoice = self._create_invoice("in_invoice", 1000)
        other_invoice = self._create_invoice(
            "in_invoice", 500, partner=self.other_partner
        )
        self._create_invoice("out_invoice", 300)
        other_customer_invoice = self._create_invoice(
            "out_invoice", 200, partner=self.other_partner
        )
        wizard = self._populate(
            self._create_order(self._open_line(invoice)),
            partner_ids=[(6, 0, self.other_partner.ids)],
        )
        self.assertEqual(
            self._proposed(wizard),
            self._open_line(other_invoice) | self._open_line(other_customer_invoice),
        )

    def test_receivables_any_reconcilable_debit(self):
        invoice = self._create_invoice("in_invoice", 1000)
        refund = self._create_invoice("in_refund", 200)
        entry = self._create_debit_entry(self.receivable_account, 100)
        wizard = self._populate(self._create_order(self.env["account.move.line"]))
        self.assertEqual(
            self._proposed(wizard),
            self._open_line(invoice) | self._open_line(refund) | self._open_line(entry),
        )

    def test_receivables_exclude_payments(self):
        invoice = self._create_invoice("in_invoice", 1000)
        payment = self._create_inbound_payment()
        wizard = self._populate(self._create_order(self.env["account.move.line"]))
        self.assertIn(self._open_line(invoice), self._proposed(wizard))
        self.assertFalse(
            self._proposed(wizard).filtered(
                lambda line: line.move_id == payment.move_id and line.debit
            )
        )

    def test_receivables_ignore_payment_partners(self):
        customer_invoice = self._create_invoice("out_invoice", 300)
        payment = self._create_inbound_payment()
        self.assertTrue(payment.move_id)
        wizard = self._populate(self._create_order(self.env["account.move.line"]))
        self.assertNotIn(self._open_line(customer_invoice), self._proposed(wizard))

    def test_receivables_ignore_journal_and_mode_filters(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        wizard = self._populate(
            self._create_order(self._open_line(invoice)),
            journal_ids=[(6, 0, invoice.journal_id.ids)],
            payment_mode="same",
        )
        self.assertEqual(self._proposed(wizard), self._open_line(customer_invoice))

    def test_receivables_exclude_liquidity_account(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        self._create_debit_entry(self.outstanding_account, 100)
        order = self._create_order(self.env["account.move.line"])
        wizard = self._populate(order)
        self.assertEqual(
            self._proposed(wizard),
            self._open_line(invoice) | self._open_line(customer_invoice),
        )
        wizard.create_payment_lines()
        self.assertEqual(
            order.payment_line_ids.move_line_id.filtered(
                lambda line: line.partner_id == self.partner
            ),
            self._proposed(wizard),
        )

    def test_netting_refused_on_inbound_mode(self):
        mode = self.netting_mode.copy(
            {
                "name": "Direct debit",
                "netting": False,
                "payment_method_id": self.env.ref(
                    "account.account_payment_method_manual_in"
                ).id,
            }
        )
        with self.assertRaisesRegex(ValidationError, "outbound"):
            mode.netting = True

    def test_receivables_invoice_filter(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        self._create_debit_entry(self.receivable_account, 100)
        wizard = self._populate(
            self._create_order(self.env["account.move.line"]), invoice=True
        )
        self.assertEqual(
            self._proposed(wizard),
            self._open_line(invoice) | self._open_line(customer_invoice),
        )

    def test_receivables_ignore_order_netted_partners(self):
        customer_invoice = self._create_invoice("out_invoice", 300)
        self._create_invoice("out_invoice", 200)
        wizard = self._populate(self._create_order(self._open_line(customer_invoice)))
        self.assertFalse(self._proposed(wizard))

    def test_receivables_move_date_filter(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        entry = self._create_debit_entry(self.receivable_account, 100)
        entry.button_draft()
        entry.date = fields.Date.today() + timedelta(days=10)
        entry.action_post()
        wizard = self._populate(
            self._create_order(self.env["account.move.line"]),
            date_type="move",
            move_date=fields.Date.today(),
        )
        self.assertEqual(
            self._proposed(wizard),
            self._open_line(invoice) | self._open_line(customer_invoice),
        )

    def test_receivables_blocked_filter(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        self._open_line(customer_invoice).blocked = True
        order = self._create_order(self.env["account.move.line"])
        self.assertEqual(
            self._proposed(self._populate(order)), self._open_line(invoice)
        )
        self.assertEqual(
            self._proposed(self._populate(order, allow_blocked=True)),
            self._open_line(invoice) | self._open_line(customer_invoice),
        )

    def test_include_receivables_change_refreshes_domain(self):
        invoice = self._create_invoice("in_invoice", 1000)
        customer_invoice = self._create_invoice("out_invoice", 300)
        order = self._create_order(self.env["account.move.line"])
        wizard_model = self.env["account.payment.line.create"].with_context(
            active_model=order._name, active_id=order.id
        )
        values = {
            "order_id": order.id,
            "date_type": "due",
            "due_date": fields.Date.to_string(fields.Date.today() + timedelta(days=30)),
            "payment_mode": "any",
            "target_move": "posted",
        }
        for include_receivables, expected in (
            (True, self._open_line(invoice) | self._open_line(customer_invoice)),
            (False, self._open_line(invoice)),
        ):
            result = wizard_model.onchange(
                dict(values, include_receivables=include_receivables),
                "include_receivables",
                wizard_model._onchange_spec(),
            )
            lines = self.env["account.move.line"].search(
                result["domain"]["move_line_ids"]
            )
            self.assertEqual(
                lines.filtered(lambda line: line.partner_id == self.partner),
                expected,
            )
