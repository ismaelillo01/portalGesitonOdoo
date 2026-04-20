# -*- coding: utf-8 -*-
from odoo import api, models


class FaltaJustificada(models.Model):
    _inherit = 'trabajadores.falta.justificada'

    def _get_portalgestor_impacted_lines(self):
        keys = {
            (record.trabajador_id.id, record.fecha)
            for record in self
            if record.trabajador_id and record.fecha
        }
        if not keys:
            return self.env['portalgestor.asignacion.linea']

        worker_ids = sorted({worker_id for worker_id, __fecha in keys})
        dates = sorted({fecha for __worker_id, fecha in keys})
        lines = self.env['portalgestor.asignacion.linea'].search([
            ('trabajador_id', 'in', worker_ids),
            ('fecha', 'in', dates),
        ])
        return lines.filtered(lambda line: (line.trabajador_id.id, line.fecha) in keys)

    def _sync_portalgestor_justified_absences(self, before_lines=None, action_kind='write'):
        line_model = self.env['portalgestor.asignacion.linea']
        before_lines = (before_lines or line_model).exists()
        after_lines = self._get_portalgestor_impacted_lines()
        impacted_lines = (before_lines | after_lines).exists()
        if not impacted_lines:
            return

        impacted_assignments = impacted_lines.mapped('asignacion_id').exists()
        before_state = impacted_assignments._get_calendar_realtime_snapshot()
        impacted_lines._recompute_falta_justificada_metrics()
        after_state = impacted_assignments.exists()._get_calendar_realtime_snapshot()
        impacted_assignments._send_calendar_update_notification(
            self.env['portalgestor.asignacion']._build_calendar_update_payload(
                before_state=before_state,
                after_state=after_state,
                action_kind=action_kind,
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('portalgestor_skip_falta_sync'):
            return super().create(vals_list)

        records = super().create(vals_list)
        records._sync_portalgestor_justified_absences(action_kind='create')
        return records

    def write(self, vals):
        if self.env.context.get('portalgestor_skip_falta_sync'):
            return super().write(vals)

        before_lines = self._get_portalgestor_impacted_lines()
        result = super().write(vals)
        self._sync_portalgestor_justified_absences(before_lines=before_lines, action_kind='write')
        return result

    def unlink(self):
        if self.env.context.get('portalgestor_skip_falta_sync'):
            return super().unlink()

        before_lines = self._get_portalgestor_impacted_lines()
        impacted_assignments = before_lines.mapped('asignacion_id').exists()
        before_state = impacted_assignments._get_calendar_realtime_snapshot()
        result = super().unlink()
        before_lines._recompute_falta_justificada_metrics()
        after_state = impacted_assignments.exists()._get_calendar_realtime_snapshot()
        impacted_assignments._send_calendar_update_notification(
            self.env['portalgestor.asignacion']._build_calendar_update_payload(
                before_state=before_state,
                after_state=after_state,
                action_kind='unlink',
            )
        )
        return result
