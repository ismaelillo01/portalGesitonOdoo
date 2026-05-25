# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError


class Vacacion(models.Model):
    _inherit = 'trabajadores.vacacion'

    def _get_portalgestor_assignment_lines_to_release(self):
        self.ensure_one()
        if not self.trabajador_id or not self.date_start or not self.date_stop:
            return self.env['portalgestor.asignacion.linea']

        return self.env['portalgestor.asignacion.linea'].search([
            ('trabajador_id', '=', self.trabajador_id.id),
            ('fecha', '>=', self.date_start),
            ('fecha', '<=', self.date_stop),
        ])

    def _release_portalgestor_assignment_lines(self):
        line_model = self.env['portalgestor.asignacion.linea']
        impacted_lines = line_model
        for record in self:
            impacted_lines |= record._get_portalgestor_assignment_lines_to_release()

        impacted_lines = impacted_lines.exists()
        if not impacted_lines:
            return impacted_lines

        impacted_assignments = impacted_lines.mapped('asignacion_id').exists()
        before_state = impacted_assignments._get_calendar_realtime_snapshot()

        legacy_fixed_lines = impacted_lines.filtered('asignacion_mensual_id')
        fixed_v2_lines = impacted_lines.filtered('trabajo_fijo_id')
        regular_lines = impacted_lines - legacy_fixed_lines - fixed_v2_lines

        legacy_pairs = {
            (line.asignacion_mensual_id.id, line.fecha)
            for line in legacy_fixed_lines
            if line.asignacion_mensual_id and line.fecha
        }
        if legacy_pairs:
            line_model._ensure_fixed_day_exceptions(legacy_pairs, 'manual')
            legacy_fixed_lines.mapped('asignacion_mensual_id')._mark_unconfirmed()

        fixed_v2_records = fixed_v2_lines.mapped('trabajo_fijo_id').exists()
        if fixed_v2_records:
            fixed_v2_records.with_context(
                portalgestor_skip_trabajo_fijo_edit_check=True,
            ).write({'confirmado': False})

        if regular_lines:
            regular_lines.with_context(
                portalgestor_skip_calendar_notify=True,
            ).write({'trabajador_id': False})
        if legacy_fixed_lines:
            legacy_fixed_lines.with_context(
                portalgestor_skip_fixed_exception=True,
                portalgestor_skip_calendar_notify=True,
            ).write({
                'trabajador_id': False,
                'asignacion_mensual_id': False,
                'asignacion_mensual_linea_id': False,
            })
        if fixed_v2_lines:
            fixed_v2_lines.with_context(
                portalgestor_skip_fixed_exception=True,
                portalgestor_skip_calendar_notify=True,
            ).write({
                'trabajador_id': False,
                'trabajo_fijo_id': False,
                'trabajo_fijo_linea_id': False,
            })

        impacted_lines._recompute_falta_justificada_metrics()
        after_state = impacted_assignments.exists()._get_calendar_realtime_snapshot()
        impacted_assignments._send_calendar_update_notification(
            self.env['portalgestor.asignacion']._build_calendar_update_payload(
                before_state=before_state,
                after_state=after_state,
                action_kind='write',
            )
        )
        return impacted_lines

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('portalgestor_skip_vacation_release'):
            return super().create(vals_list)
        records = super().create(vals_list)
        records._release_portalgestor_assignment_lines()
        return records

    def write(self, vals):
        if self.env.context.get('portalgestor_skip_vacation_release'):
            return super().write(vals)
        result = super().write(vals)
        if {'trabajador_id', 'date_start', 'date_stop'} & set(vals):
            self._release_portalgestor_assignment_lines()
        return result

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
