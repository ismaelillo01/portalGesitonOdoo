# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FaltaJustificada(models.Model):
    _name = 'trabajadores.falta.justificada'
    _description = 'Falta justificada de AP'
    _order = 'fecha_inicio desc, hora_inicio asc, id desc'

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
    fecha = fields.Date(string='Fecha legacy', index=True)
    fecha_inicio = fields.Date(string='Fecha inicio', required=True, index=True)
    fecha_fin = fields.Date(string='Fecha fin', required=True, index=True)
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

    def init(self):
        super().init()
        self.env.cr.execute(
            """
                UPDATE trabajadores_falta_justificada
                   SET fecha_inicio = COALESCE(fecha_inicio, fecha),
                       fecha_fin = COALESCE(fecha_fin, fecha),
                       fecha = COALESCE(fecha, fecha_inicio)
                 WHERE fecha IS NOT NULL
                    OR fecha_inicio IS NOT NULL
                    OR fecha_fin IS NOT NULL
            """
        )

    @api.model
    def _prepare_date_range_vals(self, vals, for_create=False):
        values = dict(vals)
        legacy_date = values.get('fecha')
        if legacy_date:
            values.setdefault('fecha_inicio', legacy_date)
            values.setdefault('fecha_fin', legacy_date)
        if values.get('fecha_inicio') and not values.get('fecha'):
            values['fecha'] = values['fecha_inicio']
        if for_create and values.get('fecha_inicio') and not values.get('fecha_fin'):
            values['fecha_fin'] = values['fecha_inicio']
        if for_create and values.get('fecha_fin') and not values.get('fecha_inicio'):
            values['fecha_inicio'] = values['fecha_fin']
        return values

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._prepare_date_range_vals(vals, for_create=True) for vals in vals_list])

    def write(self, vals):
        values = self._prepare_date_range_vals(vals)
        return super().write(values)

    @api.depends('trabajador_id.display_name', 'fecha_inicio', 'fecha_fin', 'hora_inicio', 'hora_fin')
    def _compute_name(self):
        for record in self:
            if record.trabajador_id and record.fecha_inicio:
                date_label = fields.Date.to_string(record.fecha_inicio)
                if record.fecha_fin and record.fecha_fin != record.fecha_inicio:
                    date_label = '%s -> %s' % (
                        fields.Date.to_string(record.fecha_inicio),
                        fields.Date.to_string(record.fecha_fin),
                    )
                record.name = _('%(worker)s %(date)s %(start)s-%(end)s') % {
                    'worker': record.trabajador_id.display_name or record.trabajador_id.name,
                    'date': date_label,
                    'start': self._format_hour(record.hora_inicio),
                    'end': self._format_hour(record.hora_fin),
                }
            else:
                record.name = _('Nueva falta justificada')

    @staticmethod
    def _format_hour(hour_float):
        from odoo.addons.portalGestor.models.utils import format_float_hour
        return format_float_hour(hour_float)

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

    @api.constrains('fecha_inicio', 'fecha_fin')
    def _check_dates(self):
        for record in self:
            if record.fecha_inicio and record.fecha_fin and record.fecha_inicio > record.fecha_fin:
                raise ValidationError(_("La fecha de inicio no puede ser posterior a la fecha de fin."))

    @api.constrains('hora_inicio', 'hora_fin')
    def _check_hours(self):
        for record in self:
            if record.hora_inicio < 0 or record.hora_inicio >= 24:
                raise ValidationError(_("La hora de inicio debe estar entre 00:00 y 23:59."))
            if record.hora_fin < 0 or record.hora_fin >= 24:
                raise ValidationError(_("La hora de fin debe estar entre 00:00 y 23:59."))
            if record.hora_inicio >= record.hora_fin:
                raise ValidationError(_("La hora de inicio debe ser anterior a la hora de fin."))

    @api.constrains('trabajador_id', 'fecha_inicio', 'fecha_fin', 'hora_inicio', 'hora_fin')
    def _check_overlapping_justified_absences(self):
        for record in self:
            if not record.trabajador_id or not record.fecha_inicio or not record.fecha_fin:
                continue

            overlapping_absence = self.search(
                [
                    ('id', '!=', record.id),
                    ('trabajador_id', '=', record.trabajador_id.id),
                    ('fecha_inicio', '<=', record.fecha_fin),
                    ('fecha_fin', '>=', record.fecha_inicio),
                    ('hora_inicio', '<', record.hora_fin),
                    ('hora_fin', '>', record.hora_inicio),
                ],
                limit=1,
            )
            if not overlapping_absence:
                continue

            raise ValidationError(
                _(
                    "El AP %(worker)s ya tiene una falta justificada entre %(start)s y %(end)s en el rango %(date_start)s - %(date_end)s."
                )
                % {
                    'worker': record.trabajador_id.display_name or record.trabajador_id.name,
                    'start': self._format_hour(overlapping_absence.hora_inicio),
                    'end': self._format_hour(overlapping_absence.hora_fin),
                    'date_start': fields.Date.to_string(overlapping_absence.fecha_inicio),
                    'date_end': fields.Date.to_string(overlapping_absence.fecha_fin),
                }
            )
