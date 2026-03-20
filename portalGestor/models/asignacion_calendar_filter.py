# -*- coding: utf-8 -*-
from odoo import fields, models


class AsignacionCalendarUsuarioFilter(models.Model):
    _name = 'portalgestor.asignacion.calendar.usuario.filter'
    _description = 'Filtro de calendario de asignaciones por usuario'

    user_id = fields.Many2one(
        'res.users',
        string='Usuario del sistema',
        required=True,
        default=lambda self: self.env.user,
        ondelete='cascade',
        index=True,
    )
    usuario_id = fields.Many2one(
        'usuarios.usuario',
        string='Usuario',
        required=True,
        ondelete='cascade',
        index=True,
    )
    usuario_checked = fields.Boolean(
        string='Seleccionado',
        default=True,
    )

    _sql_constraints = [
        (
            'uniq_user_usuario',
            'UNIQUE(user_id, usuario_id)',
            'No puedes tener el mismo usuario repetido en el calendario.',
        ),
    ]


class AsignacionCalendarTrabajadorFilter(models.Model):
    _name = 'portalgestor.asignacion.calendar.trabajador.filter'
    _description = 'Filtro de calendario de asignaciones por trabajador'

    user_id = fields.Many2one(
        'res.users',
        string='Usuario del sistema',
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
            'uniq_user_trabajador',
            'UNIQUE(user_id, trabajador_id)',
            'No puedes tener el mismo trabajador repetido en el calendario.',
        ),
    ]
