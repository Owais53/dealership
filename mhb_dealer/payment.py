from odoo import models, api, fields, _
from datetime import date

from odoo.exceptions import ValidationError


class Payment(models.Model):
    _inherit = 'account.payment'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order Reference')


class Payment(models.Model):
    _inherit = 'sale.order'

    advance_payments = fields.Float('Advance Payments', compute='get_advance_payments')
    amount_due = fields.Float('Amount Due', compute='get_amount_due')

    def get_advance_payments(self):
        for rec in self:
            payments = self.env['account.payment'].search([('sale_order_id', '=', rec.id), ('state', '=', 'posted')])
            adv_pay = 0
            for pay in payments:
                adv_pay = adv_pay + pay.amount
            rec.advance_payments = adv_pay

    @api.depends('advance_payments')
    def get_amount_due(self):
        for rec in self:
            rec.amount_due = rec.amount_total - rec.advance_payments
