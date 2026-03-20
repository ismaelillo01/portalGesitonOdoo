# -*- coding: utf-8 -*-
from odoo import models, fields, api
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
