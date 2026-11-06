# Copyright 2026 Akretion
# @author Guillaume MASSON <guillaume.masson@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from freezegun import freeze_time

from odoo.tests import tagged

from odoo.addons.account_invoice_inter_company.tests.test_inter_company_invoice import (
    TestAccountInvoiceInterCompanyBase,
)
from odoo.addons.account_payment_order_netting.tests.common import NettingCommon


@freeze_time("2026-01-15 12:00:00")
@tagged("post_install", "-at_install")
class TestInterCompanyNetting(NettingCommon, TestAccountInvoiceInterCompanyBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.company_ids |= cls.company_a | cls.company_b
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                allowed_company_ids=[cls.company_b.id, cls.company_a.id],
            )
        )
        (cls.company_a | cls.company_b).write(
            {"account_sale_tax_id": False, "account_purchase_tax_id": False}
        )
        cls.bank_journal_company_b.payment_credit_account_id = (
            cls._create_outstanding_account(cls.company_b)
        )
        cls.outstanding_account_company_a = cls._create_outstanding_account(
            cls.company_a
        )
        cls.bank_journal_company_a.payment_debit_account_id = (
            cls.outstanding_account_company_a
        )
        (
            cls.bank_journal_company_a.bank_account_id,
            cls.bank_journal_company_b.bank_account_id,
        ) = cls.env["res.partner.bank"].create(
            [
                {
                    "acc_number": acc_number,
                    "partner_id": partner.id,
                    "company_id": False,
                }
                for acc_number, partner in (
                    ("FR7600004", cls.partner_company_a),
                    ("FR7600005", cls.partner_company_b),
                )
            ]
        )
        cls.netting_mode = cls.env["account.payment.mode"].create(
            {
                "name": "Inter company netting transfer",
                "company_id": cls.company_b.id,
                "bank_account_link": "fixed",
                "fixed_journal_id": cls.bank_journal_company_b.id,
                "payment_method_id": cls.netting_mode.payment_method_id.id,
                "group_lines": True,
                "netting": True,
            }
        )
        cls.partner_company_a.with_company(cls.company_b).write(
            {
                "property_account_receivable_id": cls.a_recv_company_b.id,
                "property_account_payable_id": cls.a_pay_company_b.id,
            }
        )
        cls.partner_company_b.with_company(cls.company_a).write(
            {
                "property_account_receivable_id": cls.a_recv_company_a.id,
                "property_account_payable_id": cls.a_pay_company_a.id,
            }
        )
        cls.product_consultant_multi_company.with_company(cls.company_a).write(
            {
                "property_account_income_id": cls.a_sale_company_a.id,
                "property_account_expense_id": cls.a_expense_company_a.id,
            }
        )
        cls.product_consultant_multi_company.with_company(cls.company_b).write(
            {
                "property_account_income_id": cls.a_sale_company_b.id,
                "property_account_expense_id": cls.a_expense_company_b.id,
            }
        )

    @classmethod
    def _create_outstanding_account(cls, company):
        return cls.env["account.account"].create(
            {
                "code": f"X5118.{company.name[-1]}",
                "name": f"Outstanding - ({company.name})",
                "user_type_id": cls.env.ref(
                    "account.data_account_type_current_assets"
                ).id,
                "reconcile": True,
                "company_id": company.id,
            }
        )

    def _post_invoice(self, company, partner, account, move_type, amount):
        invoice = (
            self.env["account.move"]
            .with_company(company)
            .create(
                {
                    "move_type": move_type,
                    "partner_id": partner.id,
                    "invoice_date": "2026-01-15",
                    "ref": f"{move_type} {amount}",
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product_consultant_multi_company.id,
                                "account_id": account.id,
                                "quantity": 1,
                                "name": f"{move_type} {amount}",
                                "price_unit": amount,
                                "tax_ids": [(5,)],
                            },
                        )
                    ],
                }
            )
        )
        invoice.action_post()
        return invoice

    def _post_customer_invoice_company_a(self, amount):
        return self._post_invoice(
            self.company_a,
            self.partner_company_b,
            self.a_sale_company_a,
            "out_invoice",
            amount,
        )

    def _post_customer_invoice_company_b(self, amount):
        return self._post_invoice(
            self.company_b,
            self.partner_company_a,
            self.a_sale_company_b,
            "out_invoice",
            amount,
        )

    def _post_customer_refund_company_a(self, amount):
        return self._post_invoice(
            self.company_a,
            self.partner_company_b,
            self.a_sale_company_a,
            "out_refund",
            amount,
        )

    def _get_linked_invoice(self, invoice):
        return self.env["account.move"].search(
            [
                ("auto_invoice_id", "=", invoice.id),
                ("company_id", "!=", invoice.company_id.id),
            ],
            limit=1,
        )

    def _upload_netted(self, invoices):
        return self._upload(self._create_order(self._open_line(invoices)))

    def _mirror_line(self, order, account):
        return order.payment_ids.auto_move_id.line_ids.filtered(
            lambda line: line.account_id == account
        )

    def _assert_mirror_reconciled(self, mirror_line, invoice):
        invoice_line = invoice.line_ids.filtered(
            lambda line: line.account_id == mirror_line.account_id
        )
        self.assertTrue(mirror_line.reconciled)
        self.assertEqual(mirror_line.full_reconcile_id, invoice_line.full_reconcile_id)

    def test_netted_customer_invoice_with_link(self):
        customer_invoice_a = self._post_customer_invoice_company_a(1000.0)
        supplier_invoice_b = self._get_linked_invoice(customer_invoice_a)
        customer_invoice_b = self._post_customer_invoice_company_b(300.0)
        supplier_invoice_a = self._get_linked_invoice(customer_invoice_b)

        order = self._upload_netted(supplier_invoice_b | customer_invoice_b)

        payment = order.payment_ids
        self.assertEqual(payment.amount, 700.0)
        auto_move = payment.auto_move_id
        self.assertEqual(auto_move.company_id, self.company_a)
        self.assertEqual(auto_move.journal_id, self.bank_journal_company_a)
        self.assertEqual(auto_move.date, payment.date)
        self.assertEqual(auto_move.state, "posted")
        self.assertEqual(len(auto_move.line_ids), 3)
        self.assertEqual(
            self._mirror_line(order, self.outstanding_account_company_a).balance, 700.0
        )
        receivable_line = self._mirror_line(order, self.a_recv_company_a)
        self.assertEqual(receivable_line.balance, -1000.0)
        self._assert_mirror_reconciled(receivable_line, customer_invoice_a)
        payable_line = self._mirror_line(order, self.a_pay_company_a)
        self.assertEqual(payable_line.balance, 300.0)
        self._assert_mirror_reconciled(payable_line, supplier_invoice_a)
        for invoice in (
            supplier_invoice_b,
            customer_invoice_b,
            customer_invoice_a,
            supplier_invoice_a,
        ):
            self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

    def test_netted_customer_invoice_without_link(self):
        supplier_invoice_b = self._get_linked_invoice(
            self._post_customer_invoice_company_a(1000.0)
        )
        self.company_b.intercompany_invoicing = False
        unlinked_invoice = self._post_customer_invoice_company_b(300.0)
        self.assertFalse(self._get_linked_invoice(unlinked_invoice))

        order = self._upload_netted(supplier_invoice_b | unlinked_invoice)

        payable_line = self._mirror_line(order, self.a_pay_company_a)
        self.assertEqual(payable_line.balance, 300.0)
        self.assertFalse(payable_line.reconciled)
        unlinked_payment_line = order.payment_line_ids.filtered(
            lambda line: line.amount_currency < 0
        )
        auto_move = order.payment_ids.auto_move_id
        self.assertTrue(
            order.message_ids.filtered(
                lambda message: auto_move.name in (message.body or "")
                and unlinked_payment_line.communication in message.body
            )
        )
        self.assertTrue(
            self._mirror_line(order, self.a_recv_company_a).reconciled,
            "the linked line of the same mirror stays reconciled",
        )

    def test_multi_counterpart_mirror_balanced(self):
        supplier_invoice_b = self._get_linked_invoice(
            self._post_customer_invoice_company_a(1000.0)
        )
        customer_invoice_b = self._post_customer_invoice_company_b(300.0)
        supplier_refund_b = self._get_linked_invoice(
            self._post_customer_refund_company_a(200.0)
        )

        order = self._upload_netted(
            supplier_invoice_b | customer_invoice_b | supplier_refund_b
        )

        payment = order.payment_ids
        self.assertEqual(payment.amount, 500.0)
        self.assertEqual(len(payment.payment_line_ids), 3)
        line_balances = sorted(payment.auto_move_id.line_ids.mapped("balance"))
        self.assertEqual(line_balances, [-1000.0, 200.0, 300.0, 500.0])
        self.assertEqual(
            self._mirror_line(order, self.outstanding_account_company_a).balance, 500.0
        )
        unreconciled = payment.auto_move_id.line_ids.filtered(
            lambda line: line.account_id.reconcile
            and line.account_id != self.outstanding_account_company_a
            and not line.reconciled
        )
        self.assertFalse(unreconciled)
