# -*- coding: utf-8 -*-
{
    'name': "zonasTrabajo",
    'summary': "Catálogo compartido de zonas de trabajo",
    'description': """
Catálogo común de zonas de trabajo usado por trabajadores, usuarios y portalGestor.
    """,
    'author': "My Company",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/zonas_trabajo_data.xml',
        'views/views.xml',
    ],
    'installable': True,
    'application': False,
}
