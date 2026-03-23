# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class Vacacion(models.Model):
    _name = 'trabajadores.vacacion'
    _description = 'Vacaciones de Trabajador'

    name = fields.Char(string='Descripción', default='Vacaciones')
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='Trabajador',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date_start = fields.Date(string='Fecha Inicio', required=True, index=True)
    date_stop = fields.Date(string='Fecha Fin', required=True, index=True)

    @api.depends('trabajador_id')
    def _compute_display_name(self):
        for record in self:
            if record.trabajador_id:
                record.display_name = record.trabajador_id.display_name
            else:
                record.display_name = record.name

    @api.constrains('date_start', 'date_stop')
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_stop and record.date_start > record.date_stop:
                raise ValidationError("La fecha de inicio no puede ser posterior a la fecha de fin.")

    @api.constrains('trabajador_id')
    def _check_worker_is_active(self):
        for record in self:
            if record.trabajador_id and record.trabajador_id.baja:
                raise ValidationError(_("No puedes registrar vacaciones para un AP dado de baja."))

    @api.constrains('trabajador_id', 'date_start', 'date_stop')
    def _check_overlapping_vacations(self):
        for record in self:
            if not record.trabajador_id or not record.date_start or not record.date_stop:
                continue

            overlapping_vacation = self.search(
                [
                    ('id', '!=', record.id),
                    ('trabajador_id', '=', record.trabajador_id.id),
                    ('date_start', '<=', record.date_stop),
                    ('date_stop', '>=', record.date_start),
                ],
                limit=1,
            )
            if not overlapping_vacation:
                continue

            raise ValidationError(
                _(
                    "El AP %(worker)s ya tiene vacaciones entre %(date_start)s y %(date_stop)s."
                )
                % {
                    'worker': record.trabajador_id.display_name or record.trabajador_id.name,
                    'date_start': fields.Date.to_string(overlapping_vacation.date_start),
                    'date_stop': fields.Date.to_string(overlapping_vacation.date_stop),
                }
            )
