# Copyright 2024 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from textwrap import wrap

from num2words import num2words

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang

logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _check_print_params(self):
        """This method is designed to be inherited"""
        return {
            "amount_words_l1_size": 53,  # used in warp()
            "use_stars": True,
            "amount_digits_size": 14,
            "amount_digits_prefix_star_count": 1,
            "amount_words_suffix_star_count": 4,
            "amount_words_l2_empty_star_count": 10,
            "star": "✱",  # heay asterisk U+2731
        }

    def _check_print_lang(self):
        lang = self.partner_id.lang
        return lang

    def _check_print_data(self):
        """Inherit this method to change position of fields"""
        self.ensure_one()
        params = self._check_print_params()
        city = self.company_id.city
        if not city:
            raise UserError(
                _("City is not set on company '%s'.") % self.company_id.city
            )
        assert self.currency_id == self.company_id.currency_id
        lang = self._check_print_lang()
        if lang != self.company_id.partner_id.lang:
            logger.warning(
                "check print lang %s is different from company lang %s",
                lang,
                self.company_id.partner_id.lang,
            )
        env_lang = self.with_context(lang=lang).env
        amount_rounded = self.currency_id.round(self.amount)
        amount_digits = formatLang(
            env_lang, amount_rounded, digits=self.currency_id.decimal_places
        )
        if params["use_stars"]:
            if params["amount_digits_prefix_star_count"]:
                amount_digits = "".join(
                    [
                        params["star"] * params["amount_digits_prefix_star_count"],
                        amount_digits,
                    ]
                )
            if len(amount_digits) < params["amount_digits_size"]:
                suffix = params["star"] * (
                    params["amount_digits_size"] - len(amount_digits)
                )
                amount_digits = f"{amount_digits}{suffix}"
                assert len(amount_digits) == params["amount_digits_size"]
        amount_words = num2words(amount_rounded, lang=lang, to="currency")
        if params["use_stars"] and params["amount_words_suffix_star_count"]:
            amount_words = " ".join(
                [
                    amount_words,
                    params["star"] * params["amount_words_suffix_star_count"],
                ]
            )
        amount_words_wrap = wrap(amount_words, width=params["amount_words_l1_size"])
        if len(amount_words_wrap) > 1:
            amount_words_l2_value = " ".join(amount_words_wrap[1:])
        else:
            if params["use_stars"] and params["amount_words_l2_empty_star_count"]:
                amount_words_l2_value = (
                    params["star"] * params["amount_words_l2_empty_star_count"]
                )
            else:
                amount_words_l2_value = " "
        res = {
            "city": {
                "x": 485,  # same as date
                "y": 108,
                "value": city,
                "font_size": 10,
            },
            "date": {
                "x": 485,  # same as city
                "y": 94,
                "value": format_date(env_lang, fields.Date.context_today(self)),
                "font_size": 10,
            },
            "partner_name": {
                "x": 119,
                "y": 134,
                "value": self.partner_id.name,
                "font_size": 11,
            },
            "amount_digits": {
                "x": 473,
                "y": 133,
                "value": amount_digits,
                "font_size": 12,
            },
            "amount_words_l1": {
                "x": 186,
                "y": 168,
                "value": amount_words_wrap[0],
                "font_size": 11,
            },
            "amount_words_l2": {
                "x": 108,
                "y": 151,
                "value": amount_words_l2_value,
                "font_size": 11,
            },
            # 'test': {'x': 0, 'y': 0, 'value': 'TEST', 'font_size': 10},
        }
        return res
