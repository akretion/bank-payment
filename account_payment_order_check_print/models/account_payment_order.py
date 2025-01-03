# Copyright 2024 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from io import BytesIO

from reportlab.pdfgen import canvas

from odoo import _, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)

try:
    from pypdf import PdfReader, PdfWriter
except (ImportError, IOError) as err:
    logger.debug(err)


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.order"

    # we add the check strings via pypdf to have accurate positionning
    # for that, we have 2 options:
    # 1) add check strings directly in the report, via an inherit of ir.actions.report,
    # like in the module account_invoice_facturx.
    # Advantage: report can be retrieved directly from print menu.
    # 2) add check strings in generate_payment_file().
    # Advantage: makes the code simpler, less work when upgrading because the code
    # of ir.actions.report changes regularly
    # Decision : option 2, because the advantage of option 1 is pretty useless
    # (we don't need to get the report from the print menu)

    def draft2open(self):
        for order in self:
            if (
                order.payment_mode_id.payment_method_id.code == "check_payment_order"
                and order.date_prefered != "now"
            ):
                raise UserError(
                    _(
                        "On payment order %(order)s with payment mode '%(mode)s' "
                        "the Payment Execution Date Type "
                        "must be 'Immediately' because it is a check payment order.",
                        order=order.display_name,
                        mode=order.payment_mode_id.display_name,
                    )
                )
        return super().draft2open()

    def generate_payment_file(self):
        self.ensure_one()
        if self.payment_method_id.code != "check_payment_order":
            return super().generate_payment_file()
        filename = f"check_{self.name}.pdf"
        report = self.env.ref("account_payment_order_check_print.check_print_report")
        res = self.env["ir.actions.report"]._render(report, [self.id])
        if not res:
            raise UserError(_("Failed to render check print report."))
        report_bin, report_format = res
        new_report_bin = self._update_check_print_report(report, report_bin)
        return (new_report_bin, filename)

    def _update_check_print_report(self, report, report_bin):
        self.ensure_one()
        report_io = BytesIO(report_bin)
        # pdf_reader = PdfReader('/home/alexis/new_boite/lettre_cheque/lettre_cheque_sample.pdf')
        pdf_reader = PdfReader(report_io)
        page_count = pdf_reader.get_num_pages()
        pay_count = len(self.payment_ids)
        paper_format = report.paperformat_id or self.company_id.paperformat_id
        if not paper_format:
            raise UserError(
                _("Paper format not configured on company '%s'.")
                % self.company_id.display_name
            )
        logger.debug("paper_format is %s", paper_format.format)
        # pagzsize unit : points (1/72 of an inch). print_page_width/height are in mm
        pagesize = (
            paper_format.print_page_width * 72 / 25.4,
            paper_format.print_page_height * 72 / 25.4,
        )
        logger.debug("page_count=%s", page_count)

        if page_count != len(self.payment_ids):
            raise UserError(
                _(
                    "The generated check report has %(page_count)s pages "
                    "whereas there are %(pay_count)s payments. "
                    "This scenario is not supported.",
                    page_count=page_count,
                    pay_count=pay_count,
                )
            )
        pdf_writer = PdfWriter()
        for page_index in range(page_count):
            pay = self.payment_ids[page_index]
            check_print_vals = pay._check_print_data()
            packet = BytesIO()
            chq_canvas = canvas.Canvas(packet, pagesize=pagesize)
            for key, print_vals in check_print_vals.items():
                chq_canvas.setFont(
                    print_vals.get("font", "Helvetica"), print_vals["font_size"]
                )
                chq_canvas.drawString(
                    print_vals["x"], print_vals["y"], print_vals["value"]
                )
            chq_canvas.save()
            packet.seek(0)
            watermark_pdf_reader = PdfReader(packet)
            page = pdf_reader.pages[page_index]
            page.merge_page(watermark_pdf_reader.pages[0])
            pdf_writer.add_page(page)
            pdf_writer.pages[page_index].compress_content_streams()
        new_report_io = BytesIO()
        pdf_writer.write(new_report_io)
        new_report_bin = new_report_io.getvalue()
        return new_report_bin
