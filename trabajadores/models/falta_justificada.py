# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FaltaJustificada(models.Model):
    _name = 'trabajadores.falta.justificada'
    _description = 'Falta justificada de AP'
    _order = 'fecha desc, hora_inicio asc, id desc'

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        required=True,
        ondelete='cascade',
        index=True,
    )
    trabajador_color = fields.Integer(
        related='trabajador_id.color',
        string='Color del AP',
        store=True,
        readonly=True,
    )
    fecha = fields.Date(string='Fecha', required=True, index=True)
    hora_inicio = fields.Float(string='Hora inicio', required=True)
    hora_fin = fields.Float(string='Hora fin', required=True)
    motivo = fields.Text(string='Motivo', required=True)
    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('verified', 'Verificada'),
        ],
        string='Estado',
        required=True,
        default='draft',
        index=True,
    )

    @api.depends('trabajador_id.display_name', 'fecha', 'hora_inicio', 'hora_fin')
    def _compute_name(self):
        for record in self:
            if record.trabajador_id and record.fecha:
                record.name = _('%(worker)s %(date)s %(start)s-%(end)s') % {
                    'worker': record.trabajador_id.display_name or record.trabajador_id.name,
                    'date': fields.Date.to_string(record.fecha),
                    'start': self._format_hour(record.hora_inicio),
                    'end': self._format_hour(record.hora_fin),
                }
            else:
                record.name = _('Nueva falta justificada')

    @staticmethod
    def _format_hour(hour_float):
        total_minutes = int(round((hour_float or 0.0) * 60))
        return '%02d:%02d' % (total_minutes // 60, total_minutes % 60)

    def action_verificar(self):
        self.write({'state': 'verified'})
        return True

    def action_borrador(self):
        self.write({'state': 'draft'})
        return True

    @api.constrains('trabajador_id')
    def _check_worker_is_active(self):
        for record in self:
            if record.trabajador_id and record.trabajador_id.baja:
                raise ValidationError(_("No puedes registrar una falta justificada para un AP dado de baja."))

    @api.constrains('hora_inicio', 'hora_fin')
    def _check_hours(self):
        for record in self:
            if record.hora_inicio < 0 or record.hora_inicio >= 24:
                raise ValidationError(_("La hora de inicio debe estar entre 00:00 y 23:59."))
            if record.hora_fin < 0 or record.hora_fin >= 24:
                raise ValidationError(_("La hora de fin debe estar entre 00:00 y 23:59."))
            if record.hora_inicio >= record.hora_fin:
                raise ValidationError(_("La hora de inicio debe ser anterior a la hora de fin."))

    @api.constrains('trabajador_id', 'fecha', 'hora_inicio', 'hora_fin')
    def _check_overlapping_justified_absences(self):
        for record in self:
            if not record.trabajador_id or not record.fecha:
                continue

            overlapping_absence = self.search(
                [
                    ('id', '!=', record.id),
                    ('trabajador_id', '=', record.trabajador_id.id),
                    ('fecha', '=', record.fecha),
                    ('hora_inicio', '<', record.hora_fin),
                    ('hora_fin', '>', record.hora_inicio),
                ],
                limit=1,
            )
            if not overlapping_absence:
                continue

            raise ValidationError(
                _(
                    "El AP %(worker)s ya tiene una falta justificada entre %(start)s y %(end)s el dia %(date)s."
                )
                % {
                    'worker': record.trabajador_id.display_name or record.trabajador_id.name,
                    'start': self._format_hour(overlapping_absence.hora_inicio),
                    'end': self._format_hour(overlapping_absence.hora_fin),
                    'date': fields.Date.to_string(record.fecha),
                }
            )
