# -*- coding: utf-8 -*-
from odoo import api, models


class UsuarioFaltaJustificada(models.Model):
    _inherit = 'usuarios.falta.justificada'

    def _get_portalgestor_impacted_assignments(self):
        records = self.filtered(lambda record: record.usuario_id and record.fecha_inicio and record.fecha_fin)
        if not records:
            return self.env['portalgestor.asignacion']

        usuario_ids = records.mapped('usuario_id').ids
        date_start = min(records.mapped('fecha_inicio'))
        date_end = max(records.mapped('fecha_fin'))
        assignments = self.env['portalgestor.asignacion'].search([
            ('usuario_id', 'in', usuario_ids),
            ('fecha', '>=', date_start),
            ('fecha', '<=', date_end),
        ])
        return assignments.filtered(
            lambda assignment: any(
                record.usuario_id == assignment.usuario_id
                and record.fecha_inicio <= assignment.fecha <= record.fecha_fin
                for record in records
            )
        )

    def _cancel_portalgestor_assignments(self):
        assignments = self._get_portalgestor_impacted_assignments().exists()
        if not assignments:
            return assignments

        lines = assignments.mapped('lineas_ids')
        legacy_fixed_records = lines.mapped('asignacion_mensual_id').exists()
        fixed_records = lines.mapped('trabajo_fijo_id').exists()
        if legacy_fixed_records:
            legacy_fixed_records._mark_unconfirmed()
        if fixed_records:
            fixed_records.with_context(
                portalgestor_skip_trabajo_fijo_edit_check=True,
            ).write({'confirmado': False})

        assignments.with_context(
            portalgestor_skip_fixed_exception=True,
        ).unlink()
        return assignments

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('portalgestor_skip_usuario_falta_sync'):
            return super().create(vals_list)
        records = super().create(vals_list)
        records._cancel_portalgestor_assignments()
        return records

    def write(self, vals):
        if self.env.context.get('portalgestor_skip_usuario_falta_sync'):
            return super().write(vals)
        result = super().write(vals)
        if {'usuario_id', 'fecha_inicio', 'fecha_fin'} & set(vals):
            self._cancel_portalgestor_assignments()
        return result


class Asignacion(models.Model):
    _inherit = 'portalgestor.asignacion'

    def _get_user_absence_for_date(self):
        self.ensure_one()
        if not self.usuario_id or not self.fecha:
            return self.env['usuarios.falta.justificada']
        return self.env['usuarios.falta.justificada'].search([
            ('usuario_id', '=', self.usuario_id.id),
            ('fecha_inicio', '<=', self.fecha),
            ('fecha_fin', '>=', self.fecha),
        ], limit=1)
