# -*- coding: utf-8 -*-
from odoo import api, models


class FestivoOficial(models.Model):
    _inherit = 'trabajadores.festivo.oficial'

    def _get_portalgestor_impacted_lines(self):
        dates = [record.fecha for record in self if record.fecha]
        if not dates:
            return self.env['portalgestor.asignacion.linea']
        return self.env['portalgestor.asignacion.linea'].search([('fecha', 'in', dates)])

    def _sync_portalgestor_holidays(self, before_lines=None, action_kind='write'):
        line_model = self.env['portalgestor.asignacion.linea']
        before_lines = (before_lines or line_model).exists()
        after_lines = self._get_portalgestor_impacted_lines()
        impacted_lines = (before_lines | after_lines).exists()
        if impacted_lines:
            impacted_lines._recompute_festive_metrics()

        changed_dates = sorted({
            value
            for value in (
                before_lines.mapped('fecha') + after_lines.mapped('fecha') + self.mapped('fecha')
            )
            if value
        })
        self.env['portalgestor.asignacion']._send_calendar_update_notification({
            'action_kind': action_kind,
            'assignment_ids': sorted(set(impacted_lines.mapped('asignacion_id').ids)),
            'bucket_types': [],
            'changed_dates': [str(value) for value in changed_dates],
        })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_portalgestor_holidays(action_kind='create')
        return records

    def write(self, vals):
        before_lines = self._get_portalgestor_impacted_lines()
        result = super().write(vals)
        self._sync_portalgestor_holidays(before_lines=before_lines, action_kind='write')
        return result

    def unlink(self):
        before_lines = self._get_portalgestor_impacted_lines()
        result = super().unlink()
        before_lines._recompute_festive_metrics()
        self.env['portalgestor.asignacion']._send_calendar_update_notification({
            'action_kind': 'unlink',
            'assignment_ids': sorted(set(before_lines.mapped('asignacion_id').ids)),
            'bucket_types': [],
            'changed_dates': [str(value) for value in sorted(set(before_lines.mapped('fecha')))],
        })
        return result


class FestivoLocal(models.Model):
    _inherit = 'trabajadores.festivo.local'

    def _get_portalgestor_impacted_lines(self):
        keys = {
            (record.localidad_id.id, record.fecha)
            for record in self
            if record.localidad_id and record.fecha
        }
        if not keys:
            return self.env['portalgestor.asignacion.linea']

        festive_locality_ids = sorted({locality_id for locality_id, __fecha in keys})
        dates = sorted({fecha for __worker_id, fecha in keys})
        lines = self.env['portalgestor.asignacion.linea'].search([
            ('trabajador_id.festivo_localidad_id', 'in', festive_locality_ids),
            ('fecha', 'in', dates),
        ])
        return lines.filtered(
            lambda line: (
                line.trabajador_id.festivo_localidad_id.id,
                line.fecha,
            ) in keys
        )

    def _sync_portalgestor_holidays(self, before_lines=None, action_kind='write'):
        line_model = self.env['portalgestor.asignacion.linea']
        before_lines = (before_lines or line_model).exists()
        after_lines = self._get_portalgestor_impacted_lines()
        impacted_lines = (before_lines | after_lines).exists()
        if impacted_lines:
            impacted_lines._recompute_festive_metrics()

        changed_dates = sorted({
            value
            for value in (
                before_lines.mapped('fecha') + after_lines.mapped('fecha') + self.mapped('fecha')
            )
            if value
        })
        self.env['portalgestor.asignacion']._send_calendar_update_notification({
            'action_kind': action_kind,
            'assignment_ids': sorted(set(impacted_lines.mapped('asignacion_id').ids)),
            'bucket_types': [],
            'changed_dates': [str(value) for value in changed_dates],
        })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_portalgestor_holidays(action_kind='create')
        return records

    def write(self, vals):
        before_lines = self._get_portalgestor_impacted_lines()
        result = super().write(vals)
        self._sync_portalgestor_holidays(before_lines=before_lines, action_kind='write')
        return result

    def unlink(self):
        before_lines = self._get_portalgestor_impacted_lines()
        result = super().unlink()
        before_lines._recompute_festive_metrics()
        self.env['portalgestor.asignacion']._send_calendar_update_notification({
            'action_kind': 'unlink',
            'assignment_ids': sorted(set(before_lines.mapped('asignacion_id').ids)),
            'bucket_types': [],
            'changed_dates': [str(value) for value in sorted(set(before_lines.mapped('fecha')))],
        })
        return result


class Trabajador(models.Model):
    _inherit = 'trabajadores.trabajador'

    def _get_portalgestor_festive_locality_lines(self):
        workers = self.exists()
        if not workers:
            return self.env['portalgestor.asignacion.linea']
        return self.env['portalgestor.asignacion.linea'].search([
            ('trabajador_id', 'in', workers.ids),
            ('fecha', '!=', False),
        ])

    def _sync_portalgestor_festive_locality(self, before_lines=None, action_kind='write'):
        line_model = self.env['portalgestor.asignacion.linea']
        before_lines = (before_lines or line_model).exists()
        after_lines = self._get_portalgestor_festive_locality_lines()
        impacted_lines = (before_lines | after_lines).exists()
        if impacted_lines:
            impacted_lines._recompute_festive_metrics()

        changed_dates = sorted({
            value
            for value in (before_lines.mapped('fecha') + after_lines.mapped('fecha'))
            if value
        })
        self.env['portalgestor.asignacion']._send_calendar_update_notification({
            'action_kind': action_kind,
            'assignment_ids': sorted(set(impacted_lines.mapped('asignacion_id').ids)),
            'bucket_types': [],
            'changed_dates': [str(value) for value in changed_dates],
        })

    def write(self, vals):
        if 'festivo_localidad_id' not in vals:
            return super().write(vals)

        before_lines = self._get_portalgestor_festive_locality_lines()
        result = super().write(vals)
        self._sync_portalgestor_festive_locality(before_lines=before_lines, action_kind='write')
        return result
