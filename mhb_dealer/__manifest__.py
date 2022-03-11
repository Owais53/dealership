
{
    'name': 'Dealership',
    'category': 'misc',
    'depends': ['sale','purchase','crm'],
    'description': """
""",
    'data': [
        'ir.model.access.csv',
        'model_view.xml',
        'payment_view.xml',
        'report/car_inspection_report.xml',
        'report/report_view.xml',
        'report/provisional_sale_order.xml',
        'data/sequence.xml',
        'data/seq_provisional_sale.xml',
    ],
    'qweb': [
        # 'static/src/bugfix/bugfix.xml',
        # 'static/src/xml/  base.xml',
    ],
    'auto_install': False,
    'installable':True,
}
