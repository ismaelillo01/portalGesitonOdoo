# -*- coding: utf-8 -*-
{
    'name': 'Portal Usuario',
    'summary': 'Portal movil de horarios para Usuarios',
    'description': """
        Portal publico movil para que los Usuarios consulten sus dias y horas
        de atencion autenticandose solo con DNI/NIE.
    """,
    'author': 'My Company',
    'license': 'LGPL-3',
    'category': 'Services',
    'version': '18.0.1.0.0',
    'depends': [
        'web',
        'trabajadores',
        'portalGestor',
        'usuarios',
        'ui_brian_theme',
    ],
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'portal_usuario/static/src/scss/portal_usuario.scss',
        ],
    },
    'installable': True,
    'application': False,
}
