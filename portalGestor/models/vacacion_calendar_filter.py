# -*- coding: utf-8 -*-
from odoo import fields, models


class VacacionCalendarFilter(models.Model):
    _name = 'portalgestor.vacacion.calendar.filter'
    _description = 'Filtro de calendario de vacaciones por trabajador'

    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        default=lambda self: self.env.user,
        ondelete='cascade',
        index=True,
    )
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='Trabajador',
        required=True,
        ondelete='cascade',
        index=True,
    )
    trabajador_checked = fields.Boolean(
        string='Seleccionado',
        default=True,
    )

    _sql_constraints = [
        (
            'uniq',
            'UNIQUE(user_id, trabajador_id)',
            'No puedes tener el mismo trabajador repetido en el calendario.',
        ),
    ]
