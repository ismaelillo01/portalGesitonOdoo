# -*- coding: utf-8 -*-
from odoo import fields, models


class ZonaTrabajo(models.Model):
    _name = 'zonastrabajo.zona'
    _description = 'Zona de Trabajo'
    _order = 'sequence, name, id'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True, index=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    _sql_constraints = [
        ('uniq', 'UNIQUE(code)', 'El código de la zona de trabajo debe ser único.'),
    ]
