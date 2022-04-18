from odoo import models, api, fields, _
from datetime import datetime, date

from odoo.exceptions import ValidationError


class Users(models.Model):
    _inherit = 'res.users'

    categ_id = fields.Many2one('product.category', string='Product Category')


class InheritCrmLead(models.Model):
    _inherit = 'crm.lead'

    walkincustomer = fields.Many2one('walk.in')
    en_id = fields.Many2one('res.users', related='walkincustomer.en_id')
    product_id = fields.Many2many('product.product')
    cnic = fields.Char('CNIC', readonly=1)
    sale_check = fields.Boolean(compute='GetSaleCheck')

    def GetSaleCheck(self):
        for rec in self:
            rec.sale_check = False
            if self.env['sale.order'].search([('state', '=', 'sale'), ('opportunity_id', '=', rec.id)]):
                rec.sale_check = True


class InheritSaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_date = fields.Date(string='Delivery Date')
    po_id = fields.Many2one('purchase.order', 'Purchase Order', compute='GetPO')
    name_seq = fields.Char(string='Order Reference', required=False, copy=False, readonly=True, index=True, )
    check_po = fields.Boolean()
    inspection_id = fields.Many2one('car.inspection')
    account_type = fields.Selection([
        ('advance_payment', 'Advanced Payment Booking'),
        ('full_payment', 'Full Payment Booking'),
        ('booking_daraz', 'Booking Vehicle From Daraz'),
        ('investment', 'Investment'),
    ])
    sale_type = fields.Integer()
    chassis = fields.Char('Chassis #')

    def action_confirm(self):
        if self.sale_type:
            self.write({'type_id': self.sale_type})
        return super(InheritSaleOrder, self).action_confirm()




    def GetPO(self):
        for rec in self:
            self.po_id = False
            self.check_po = False
            for line in self.env['purchase.order'].search([('sale_id', '=', self.id), ('state', '=', 'purchase')]):
                line.sale_id = self.id
                self.po_id = line.id
                self.check_po = True

    def CreatePurchaseOrder(self):
        product_id = False
        line_items = []
        for line in self.order_line:
            vals = {'product_id': line.product_id.id, 'name': line.product_id.name, 'chassis': line.chassis,
                    'product_qty': 1, 'product_uom': line.product_id.uom_id.id,
                    'price_unit': 1, 'sequence': 10, 'date_planned': datetime.now()}
            line_items.append(vals)

        return {
            'name': "Purchase Order",
            'view_mode': 'form',
            'view_type': 'form',
            'res_model': 'purchase.order',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'domain': '[]',
            'context': {'default_sale_id': self.id, 'default_delivery_date': self.delivery_date,
                        'default_partner_id': self.partner_id.id, 'default_order_line': line_items
                        }
        }

    def CreatePayment(self):
        return {
            'name': "Payments",
            'view_mode': 'form',
            'view_type': 'form',
            'res_model': 'account.payment',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'domain': '[]',
            'context': {'default_partner_type': 'customer', 'default_partner_id': self.partner_id.id,
                        'default_sale_order_id': self.id,
                        'default_amount': self.amount_due
                        }
        }

    @api.onchange('opportunity_id')
    def GetSaleOrderLine(self):
        if self.opportunity_id:
            type = self.env['sale.order.type'].search([('name', '=', 'Dealer Sales Order')]).id
            # self.type_id = type
            self.sale_type = type
            values = []
            for product_id in self.opportunity_id.product_id:
                values.append((0, 0, {'product_id': product_id.id, 'product_uom_qty': 1,
                                      'name': product_id.name, 'price_unit': 0.0, 'product_uom': 1}))
            self.order_line = values

    @api.model
    def create(self, vals_list):
        rec = super(InheritSaleOrder, self).create(vals_list)
        # rec.state='sale'
        return rec
    # seq field for provisional sale order
    # @api.model
    # def create(self, vals):
    #     # print(vals.get('name_seq'))
    #     if vals.get('name_seq2', _('New')) == _('New'):
    #         vals['name_seq2'] = self.env['ir.sequence'].next_by_code('sale.order') or _('New')
    #     result = super(InheritSaleOrder, self).create(vals)
    #     return result


class INheritPoID(models.Model):
    _inherit = 'purchase.order'

    sale_id = fields.Many2one('sale.order')

    def CreatePass(self):
        product_id = False
        for line in self.order_line:
            product_id = line.product_id

        return {
            'name': "Goods Notes",
            'view_mode': 'form',
            'view_type': 'form',
            'res_model': 'deliver.product',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_sale_id': self.sale_id.id, 'default_id': self.id, 'default_in_date': date.today(),
                        'default_partner_id': self.sale_id.partner_id.id, 'default_product_id': product_id.id
                        }
        }

    def CreateBeforeValidation(self):
        return True


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    check_validation = fields.Boolean(default=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Another Operation'),
        ('confirmed', 'Waiting'),
        ('assigned', 'Ready'),
        ('intransit', 'Intransit'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', compute='_compute_state',
        copy=False, index=True, readonly=True, store=True, tracking=True,
        help=" * Draft: The transfer is not confirmed yet. Reservation doesn't apply.\n"
             " * Waiting another operation: This transfer is waiting for another operation before being ready.\n"
             " * Waiting: The transfer is waiting for the availability of some products.\n(a) The shipping policy is \"As soon as possible\": no product could be reserved.\n(b) The shipping policy is \"When all products are ready\": not all the products could be reserved.\n"
             " * Ready: The transfer is ready to be processed.\n(a) The shipping policy is \"As soon as possible\": at least one product has been reserved.\n(b) The shipping policy is \"When all products are ready\": all product have been reserved.\n"
             " * Done: The transfer has been processed.\n"
             " * Cancelled: The transfer has been cancelled.")

    def beforevalidation(self):
        self.check_validation = True


class Questions(models.Model):
    _name = 'survey.questions'
    _description = "Question"

    name = fields.Char()
    is_active = fields.Boolean("Active")


class CustomerSurvey(models.Model):
    _name = 'customer.survey'
    _rec_name = 'name'

    name = fields.Char("Survey Name")
    partner_id = fields.Many2one('res.partner', "Name")
    survay_date_start = fields.Date("Start Date")
    survay_date_end = fields.Date("End Date")
    state = fields.Selection([('draft', 'Draft'), ('start', 'Start'), ('done', 'Done')], string="State",
                             default='draft')
    survey_q_lines = fields.One2many('survey.question.lines', 'question_id', "Survey Lines")

    def start_survey(self):
        for rec in self:
            questions = self.env['survey.questions'].search([('is_active', '=', True)])
            if questions:
                for q in questions:
                    vals = {'question': q.name}
                    rec.survey_q_lines = [(0, 0, vals)]
            self.state = 'start'

    def done(self):
        for records in self:
            records.state = 'done'


class SurveyLines(models.Model):
    _name = 'survey.question.lines'
    _description = "Survey Question Lines"

    question = fields.Char()
    answer = fields.Text()
    question_id = fields.Many2one('customer.survey')


class GateInwardPass(models.Model):
    _name = 'gate.inward.pass'
    # _rec_name = 'gate_number '
    _rec_name = 'chassis'

    partner_name = fields.Many2one('res.partner')
    en_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    date = fields.Datetime()
    gate_number = fields.Char()
    # car_number = fields.Integer()
    chassis = fields.Char()
    car_name = fields.Char()
    # chassis_id = fields.Many2one('product.product', required=True)
    state = fields.Selection([('Draft', 'Draft'), ('in', 'Gate Inward')], default='Draft')

    # product_line = fields.One2many('gate.order.line', 'gate_id', string="Products",
    #                                states={'in': [('readonly', True)], 'out': [('readonly', True)]}, copy=True,
    #                                auto_join=True)

    def SetIn(self):
        self.state = 'in'
        self.date = fields.Datetime.today()

    def SetOut(self):
        self.state = 'out'
        self.date = fields.Datetime.today()

    @api.constrains('chassis')
    def validate_chassis_number(self):
        for record in self:
            if not record.chassis:
                raise ValidationError(_('Please enter chassis number'))

    @api.constrains('car_name')
    def validate_cnic_number(self):
        for record in self:
            count = self.search_count([('car_name', '=', record.car_name)])
            if count > 1:
                raise ValidationError(_('Please enter unique Registration number'))


class CarInspection(models.Model):
    _name = 'car.inspection'
    _description = "Car Inspection"
    _rec_name = 'partner'

    name_seq = fields.Char(string='Order Reference', required=False, copy=False, readonly=True, index=True,
                           default=lambda self: _('New'))
    date = fields.Date()
    partner = fields.Many2one('res.partner')
    car_name = fields.Char()
    insurance_claim = fields.Char()

    warranty_claim = fields.Char()

    file_upload = fields.Binary('File', attachment=True)
    inspection_ids = fields.One2many('gate.order.line', 'inspection_id')
    insurance_ids = fields.One2many('insurance.claim.line', 'insurance_id')
    warrenty_ids = fields.One2many('warrenty.claim.line', 'warrenty_id')
    job_ids = fields.One2many('job.description', 'job_id')

    # state = fields.Selection([('Draft', 'Draft'), ('confirmed','Confirmed'), ('so','Sale Order'),('in_progress','In Progress'),('complete','Complete')], default='Draft')
    state = fields.Selection([('Draft', 'Draft'), ('receiving_checklist', 'Receiving Checklist'), ('so', 'Sale Order'),
                              ('return_checklist', 'Return Checklist'), ('complete', 'Gate Out')], default='Draft')
    address = fields.Char()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    mobile = fields.Char()
    phone = fields.Char()
    fuel = fields.Selection([('E', 'E'), ('1/4', '1/4'), ('1/2', '1/2'), ('3/4', '3/4'), ('F', 'F')], default='E',
                            string='Fuel')
    registration_no = fields.Char()
    chassis = fields.Many2one('gate.inward.pass')
    sale_o = fields.Char(readonly=1)
    # chassis = fields.Integer()
    engine_no = fields.Char()
    make = fields.Char()
    model = fields.Char()
    color = fields.Char()
    km = fields.Char()
    cassettes_player = fields.Boolean()
    cd = fields.Boolean()
    cassettes = fields.Boolean()
    cig = fields.Boolean()
    floor = fields.Boolean()
    rv = fields.Boolean()
    sv = fields.Boolean()
    wiper = fields.Boolean()
    vin = fields.Boolean()
    wheel = fields.Boolean()
    tool = fields.Boolean()
    jack = fields.Boolean()
    spare = fields.Boolean()
    monogram = fields.Boolean()
    mud = fields.Boolean()
    top_cover = fields.Boolean()
    original = fields.Boolean()
    gst = fields.Char()
    total = fields.Char()
    technical = fields.Char()
    technician = fields.Char()
    cassettes_player1 = fields.Boolean()
    cd1 = fields.Boolean()
    cassettes1 = fields.Boolean()
    cig1 = fields.Boolean()
    floor1 = fields.Boolean()
    rv1 = fields.Boolean()
    sv1 = fields.Boolean()
    wiper1 = fields.Boolean()
    vin1 = fields.Boolean()
    wheel1 = fields.Boolean()
    tool1 = fields.Boolean()
    jack1 = fields.Boolean()
    spare1 = fields.Boolean()
    monogram1 = fields.Boolean()
    mud1 = fields.Boolean()
    top_cover1 = fields.Boolean()
    original1 = fields.Boolean()
    check_invoicess = fields.Char(compute='_check_invoice', default='True')
    check_invoices = fields.Char()

    #
    # def inprogress(self):
    #     self.state = 'in_progress'
    #     self.date=fields.Datetime.today()

    # def get_ref_from_sale(self):
    #
    #     get_ref = self.env['sale.order'].search([('inspection_id', '=', self.id)])

    # @api.constrains('inspection_ids')
    # def _check_product_availablity(self):
    #     if self.inspection_ids is None:
    #         raise ValidationError(_('Please Check product'))

    def receivingchecklist(self):
        self.state = 'receiving_checklist'
        self.date = fields.Datetime.today()

    def returnchecklist(self):
        self.state = 'return_checklist'
        self.date = fields.Datetime.today()

    def complete(self):
        if self.check_invoicess == 'True':
            raise ValidationError(_('Order is not paid'))
        else:
            self.state = 'complete'
            self.date = fields.Datetime.today()

    def So(self):
        self.state = 'so'
        self.date = fields.Datetime.today()

        product_line = self.env['gate.order.line'].search([('inspection_id', '=', self.id)])
        name = self.env['ir.sequence'].next_by_code('sale.seq')

        if not product_line:
            raise ValidationError(_('Please Check product'))
        type = self.env['sale.order.type'].search([('name', '=', 'Services Sale Order')]).id
        if product_line:
            vlas = {
                'partner_id': self.partner.id,
                'date_order': self.date,
                'state': 'sale',
                'name_seq': self.name_seq,
                'type_id': type
            }
            so = self.env['sale.order'].create(vlas)
            self.sale_o = so.name

            for lines in product_line:
                lines = {
                    'order_id': so.id,
                    'name': lines.name,
                    'product_id': lines.product_id.id,
                    'product_uom_qty': lines.product_uom_qty
                }
                so_line = self.env['sale.order.line'].create(lines)

        # insurance claim
        product_line_i = self.env['insurance.claim.line'].search([('insurance_id', '=', self.id)])
        name = self.env['ir.sequence'].next_by_code('sale.seq')

        if product_line_i:
            vlas = {
                'partner_id': self.partner.id,
                'date_order': self.date,
                'state': 'sale',
                'name_seq': self.name_seq,
                'type_id': type
            }
            so = self.env['sale.order'].create(vlas)
            self.insurance_claim = so.name

            for lines_i in product_line_i:
                lines_i = {
                    'order_id': so.id,
                    'name': lines_i.name,
                    'product_id': lines_i.product_id.id,
                    'product_uom_qty': lines_i.product_uom_qty
                }
                so_line = self.env['sale.order.line'].create(lines_i)

        # warrenty claim
        product_line_c = self.env['warrenty.claim.line'].search([('warrenty_id', '=', self.id)])
        name = self.env['ir.sequence'].next_by_code('sale.seq')

        if product_line_c:
            vlas = {
                'partner_id': self.partner.id,
                'date_order': self.date,
                'state': 'sale',
                'name_seq': self.name_seq,
                'type_id': type
            }
            so = self.env['sale.order'].create(vlas)
            self.warranty_claim = so.name

            for lines_c in product_line_c:
                lines_c = {
                    'order_id': so.id,
                    'name': lines_c.name,
                    'product_id': lines_c.product_id.id,
                    'product_uom_qty': lines_c.product_uom_qty
                }
                so_line = self.env['sale.order.line'].create(lines_c)

    def _check_invoice(self):
        sale_order = self.env['sale.order'].search([('name', '=', self.sale_o)]).invoice_ids
        if sale_order:
            for invoices in sale_order:
                if invoices.amount_residual > 0:
                    self.check_invoicess = 'True'
                else:
                    self.check_invoicess = 'False'
        else:
            self.check_invoicess = 'True'

    # sequence field fuction in car inspection form
    @api.model
    def create(self, vals):
        # print(vals.get('name_seq'))
        if vals.get('name_seq', _('New')) == _('New'):
            vals['name_seq'] = self.env['ir.sequence'].next_by_code('car.inspection') or _('New')
        result = super(CarInspection, self).create(vals)
        return result

    @api.onchange('chassis')
    def check_chassis(self):
        for rec in self:
            if rec.chassis:
                service = self.env['car.inspection'].search([('chassis', '=', rec.chassis.chassis)]).chassis
                sale = self.env['sale.order'].search([('chassis', '=', rec.chassis.chassis)]).chassis
                if sale and service:
                    return {
                        'warning': {'title': "Warning", 'message': "This Car was serviced and sold."},
                    }
                if service:
                    return {
                        'warning': {'title': "Warning", 'message': "This Car was serviced before"},
                    }
                if sale:
                    return {
                        'warning': {'title': "Warning", 'message': "This Car was sold before."},
                    }

    @api.onchange('chassis')
    def Onchange_chassis(self):
        res = {}
        if self.chassis:
            if self.chassis.partner_name:
                self.partner = self.chassis.partner_name
            if self.chassis.car_name:
                self.registration_no = self.chassis.car_name
            partners = self.env['res.partner'].search([])
            sales = self.env['sale.order'].search([('chassis', '=', self.chassis.chassis)]).order_line
            for sale in sales:
                self.car_name = sale.product_id.name
            for partner in partners:
                if partner.name == self.chassis.partner_name.name:
                    if partner.street:
                        self.address = partner.street
                    if partner.mobile:
                        self.mobile = partner.mobile
                    if partner.phone:
                        self.phone = partner.phone
            if res:
                return res

    # def invoice(self):
    #     p = self.env['account.move'].search([('partner_id', '=', self.id)])
    #     print(p.payment_state)
    #     print(self.payment_state)
    # @api.onchange('So')
    # def Onchange_chassis(self):
    #     r = self.env['sale.order'].search([('partner_id', '=', self.partner)])
    #     if r:
    #         self.sale_o = r.patient_id.name


class GateInwardPassLine(models.Model):
    _name = 'gate.order.line'

    product_id = fields.Many2one('product.product', required=True)
    inspection_id = fields.Many2one('car.inspection')
    gate_id = fields.Many2one('gate.inward.pass', string='Order Reference', ondelete='cascade', index=True, copy=False)
    name = fields.Text(string='Description', required=1)
    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', default=1.0)


class CrateCustomer(models.Model):
    _name = 'walk.in'

    name = fields.Char('Name')
    contact_no = fields.Char('Contact Number')
    cnic = fields.Char('CNIC')
    product_id = fields.Many2many('product.product', string='Variant')
    email = fields.Char(string='Email')
    description = fields.Text()
    en_id = fields.Many2one('res.users', default=lambda self: self.env.user)

    # @api.constrains('cnic')
    # def validate_cnic_number(self):
    #     for record in self:
    #         count = self.search_count([('cnic', '=', self.cnic)])
    #         if count > 1:
    #             raise ValidationError(_('Please enter unique cnic number'))
    #         if len(record.cnic) < 13 or len(record.cnic) > 13:
    #             raise ValidationError(_("The cnic number exceeds the maximum length of 13 characters."))

    @api.constrains('contact_no')
    def validate_contact_no(self):
        for record in self:
            if self.contact_no:
                group_e = self.env.ref('mhb_dealer.access_walkin_customer', False)
                group_e.write({'users': [(3, self.env.uid)]})
                count = self.search_count([('contact_no', '=', self.contact_no)])
                user_id = self.env['walk.in'].search([('contact_no', '=', self.contact_no)])
                for id in user_id:
                    user = self.env['walk.in'].search_read([('id', '=', id.id)])
                    break
                group_e.write({'users': [(4, self.env.uid)]})
                if count > 1:
                    raise ValidationError(
                        _('This Contact Number has been already registered by ' + user[0]['en_id'][1] + ''))
            else:
                raise ValidationError(_('This Contact Number is required'))

    @api.model
    def create(self, vals):
        rec = super(CrateCustomer, self).create(vals)
        products_list = []
        for pid in rec['product_id']:
            products_list.append(pid.id)
        partner = {
            'name': rec.name, 'contact_no': rec.contact_no, 'cnic': rec.cnic, 'product_id': products_list,
            'email': rec.email, 'mobile': rec.contact_no

        }
        partner = self.env['res.partner'].create(partner)
        lead = {
            'name': str(partner.name) + ':-' + str(rec.contact_no), 'user_id': False, 'team_id': False,
            'partner_id': partner.id, 'phone': rec.contact_no, 'email_from': rec.email, 'product_id': products_list,
            'cnic': rec.cnic

        }
        self.env['crm.lead'].create(lead)

        return rec


class InheritResPartner(models.Model):
    _inherit = 'res.partner'

    cnic = fields.Char('CNIC')
    product_id = fields.Many2many('product.product')
    contact_no = fields.Char('Contact Number')
    tax_status = fields.Boolean()
    institution = fields.Char()
    f_name = fields.Char()
    file_upload = fields.Binary('File', attachment=True)
    chassis_no = fields.Char('Chassis No', compute='get_chassis_from_so')

    @api.depends('chassis_no')
    def get_chassis_from_so(self):
        for rec in self:
            chassis = self.env['sale.order'].search([('partner_id', '=', rec.id)])
            rec.chassis_no = False
            for record in chassis:
                if record.chassis:
                    rec.chassis_no = record.chassis


    def name_get(self):
        res = []
        for rec in self:
            res.append((rec.id, '%s - %s' % (rec.name, rec.phone) if rec.phone else rec.name))
        return res


class InheritProductProduct(models.Model):
    _inherit = 'product.product'

    car = fields.Boolean(string='Is Car')
    model = fields.Char()
    car_type = fields.Char()
    vehicle_two = fields.Char()


class SaleOrderLineInherited(models.Model):
    _inherit = 'sale.order.line'

    model = fields.Char(related='product_id.model')
    car_type = fields.Char(related='product_id.car_type')
    vehicle_categ = fields.Char(related='product_id.categ_id.name')
    vehicle_two = fields.Char()
    chassis = fields.Char()
    engine = fields.Char()
    colour = fields.Many2one('colour.colour')


class GateInOut(models.Model):
    _name = 'deliver.product'
    _rec_name = 'po_id'

    product_id = fields.Many2one('product.product', string='Car')
    po_id = fields.Many2one('purchase.order', 'Booking Reference', required=1)
    employee_id = fields.Many2one('hr.employee', 'Receiver')
    gate_number = fields.Char(string='Gate Number')
    vehicle_number = fields.Char(string='Vehicle Number')
    in_date = fields.Date(readonly=1, string='Received On')
    #
    out_gate = fields.Char(string='Out Gate Number')
    sale_id = fields.Many2one('sale.order')
    partner_id = fields.Many2one('res.partner')
    out_date = fields.Date(readonly=1, string='Delivered on')
    #
    state = fields.Selection([('Draft', 'Draft'), ('Received', 'Received'), ('Delivered', 'Delivered')],
                             default='Draft')

    def SetReceived(self):
        self.state = 'Received'

    def SetDelivered(self):
        self.state = 'Delivered'


class InsuranceClaim(models.Model):
    _name = 'insurance.claim.line'

    product_id = fields.Many2one('product.product', required=True)
    insurance_id = fields.Many2one('car.inspection')
    # gate_id = fields.Many2one('gate.inward.pass', string='Order Reference', ondelete='cascade', index=True, copy=False)
    name = fields.Text(string='Description', required=1)
    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', default=1.0)


class WarrentyClaim(models.Model):
    _name = 'warrenty.claim.line'

    product_id = fields.Many2one('product.product', required=True)
    warrenty_id = fields.Many2one('car.inspection')
    # gate_id = fields.Many2one('gate.inward.pass', string='Order Reference', ondelete='cascade', index=True, copy=False)
    name = fields.Text(string='Description', required=1)
    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', default=1.0)

class JobDescription(models.Model):
    _name = 'job.description'

    job_id = fields.Many2one('car.inspection')
    job_des = fields.Char('Jobs Description & Remarks')
    labour = fields.Char(string='Labour')
    Part_lub = fields.Many2one('product.product',string='Parts & Lubricant Description')
    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', default=1.0)
    amount = fields.Char(string='Amount')

class PurchaseLine(models.Model):
    _inherit = 'purchase.order.line'

    chassis = fields.Char()
    colour = fields.Many2one('colour.colour')

    
class ColourCar(models.Model):
    _name = 'colour.colour'
    _rec_name = 'colour'

    colour = fields.Char(string='Color')    
