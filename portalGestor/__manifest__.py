# -*- coding: utf-8 -*-
{
    'name': "Portal Gestor",
    'summary': "Asignación de Trabajadores a Usuarios",
    'description': """
        Módulo para que los gestores asignen horarios a trabajadores para distintos usuarios.
    """,
    'author': "My Company",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': ['base', 'web', 'bus', 'gestores', 'trabajadores', 'usuarios', 'zonasTrabajo'],
    'assets': {
        'web.assets_backend': [
            'portalGestor/static/src/js/portalgestor_calendar_order.js',
            'portalGestor/static/src/js/trabajadores_vacacion_markers.js',
            'portalGestor/static/src/js/portalgestor_calendar_summary.js',
            'portalGestor/static/src/scss/trabajadores_vacacion_markers.scss',
            'portalGestor/static/src/scss/portalgestor_calendar_summary.scss',
            'portalGestor/static/src/xml/portalgestor_calendar_templates.xml',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'security/portalgestor_security.xml',
        'reports/horario_report.xml',
        'views/asignacion_views.xml',
        'views/asignacion_mensual_views.xml',
        'views/trabajadores_vacacion_calendar_views.xml',
        'wizards/conflict_wizard_views.xml',
        'wizards/report_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
}
