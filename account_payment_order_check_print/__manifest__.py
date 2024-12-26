# Copyright 2024 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Payment Order Check Print",
    "version": "16.0.1.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Check printing module for OCA payment orders",
    "author": "Akretion,Odoo Community Association (OCA)",
    "maintainers": ["alexis-via"],
    "development_status": "Mature",
    "website": "https://github.com/OCA/bank-payment",
    "depends": ["account_payment_order"],
    "external_dependencies": {"python": ["pypdf", "num2words"]},
    "data": [
        "data/account_payment_method.xml",
        "reports/report.xml",
        "reports/letter.xml",
    ],
    "installable": True,
}
