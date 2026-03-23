# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class Vacacion(models.Model):
    _inherit = 'trabajadores.vacacion'

    def _get_assignment_conflict_dates(self):
        self.ensure_one()
        if not self.trabajador_id or not self.date_start or not self.date_stop:
            return []

        grouped_dates = self.env['portalgestor.asignacion.linea'].sudo()._read_group(
            [
                ('trabajador_id', '=', self.trabajador_id.id),
                ('fecha', '>=', self.date_start),
                ('fecha', '<=', self.date_stop),
            ],
            ['fecha:day'],
            ['__count'],
            order='fecha:day ASC',
        )
        return [
            fields.Date.to_string(fecha)
            for fecha, __count in grouped_dates
            if fecha
        ]

    @api.constrains('trabajador_id', 'date_start', 'date_stop')
    def _check_no_work_assignments_in_vacation_range(self):
        for record in self:
            conflict_dates = record._get_assignment_conflict_dates()
            if not conflict_dates:
                continue

            sample_dates = ", ".join(conflict_dates[:5])
            extra_dates = ""
            if len(conflict_dates) > 5:
                extra_dates = _(" y %(count)s fechas mas") % {
                    'count': len(conflict_dates) - 5,
                }

            raise ValidationError(
                _(
                    "No puedes registrar vacaciones para %(worker)s porque ya tiene trabajo asignado en estas fechas: %(dates)s%(extra)s."
                )
                % {
                    'worker': record.trabajador_id.display_name or record.trabajador_id.name,
                    'dates': sample_dates,
                    'extra': extra_dates,
                }
            )

    @api.model
    def get_assignment_markers(self, trabajador_ids, date_start, date_end):
        if not trabajador_ids or not date_start or not date_end:
            return []

        start_date = fields.Date.to_date(date_start)
        end_date = fields.Date.to_date(date_end)
        if not start_date or not end_date:
            return []

        try:
            fechas_con_asignacion = self.env['portalgestor.asignacion.linea']._read_group(
                [
                    ('trabajador_id', 'in', trabajador_ids),
                    ('fecha', '>=', start_date),
                    ('fecha', '<=', end_date),
                ],
                ['fecha:day'],
                ['__count'],
                order='fecha:day ASC',
            )
        except AccessError:
            return []

        markers = []
        for fecha, __count in fechas_con_asignacion:
            fecha = fields.Date.to_string(fecha)
            if not fecha:
                continue
            markers.append({
                'id': f'portalgestor_workday_{fecha}',
                'date': fecha,
            })
        return markers
