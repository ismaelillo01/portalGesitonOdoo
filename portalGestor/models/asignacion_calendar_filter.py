# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
        domain=[('baja', '=', False), ('has_ap_service', '=', True)],
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

    @api.constrains('usuario_id')
    def _check_usuario_has_ap_service(self):
        for record in self:
            if record.usuario_id and not record.usuario_id.has_ap_service:
                raise ValidationError(_("Solo puedes filtrar usuarios con el servicio AP activo en portalGestor."))


class AsignacionCalendarTrabajadorFilter(models.Model):
    _name = 'portalgestor.asignacion.calendar.trabajador.filter'
    _description = 'Filtro de calendario de asignaciones por AP'

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
        string='AP',
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
            'No puedes tener el mismo AP repetido en el calendario.',
        ),
    ]
