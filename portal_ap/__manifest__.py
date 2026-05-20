# -*- coding: utf-8 -*-
{
    'name': 'Portal AP',
    'summary': 'Portal movil de horarios para AP',
    'description': """
        Portal publico movil para que los AP consulten sus horarios y vacaciones
        autenticandose solo con DNI/NIE.
    """,
    'author': 'My Company',
    'license': 'LGPL-3',
    'category': 'Services',
    'version': '18.0.1.1.0',
    'depends': [
        'web',
        'trabajadores',
        'portalGestor',
        'usuarios',
        'ui_brian_theme',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/backend_views.xml',
        'wizards/fichaje_report_wizard_views.xml',
        'views/mobile_views.xml',
        'reports/mobile_reports.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'portal_ap/static/src/scss/portal_ap.scss',
        ],
    },
    'installable': True,
    'application': False,
}
