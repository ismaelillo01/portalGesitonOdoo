# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError


class ConflictWizard(models.TransientModel):
    _name = 'portalgestor.conflict.wizard'
    _description = 'Asistente de Conflictos de Horario'

    asignacion_id = fields.Many2one('portalgestor.asignacion')
    asignacion_mensual_id = fields.Many2one('portalgestor.asignacion.mensual')
    conflict_type = fields.Selection([
        ('overlapping', 'Solapamiento de Horas'),
        ('overlapping_batch', 'Solapamiento de Horas en lote'),
        ('protected_intecum_overlapping', 'Solapamiento protegido de Intecum'),
        ('protected_intecum_overlapping_batch', 'Solapamiento protegido de Intecum en lote'),
        ('info_same_day', 'Aviso informativo: mismo dia'),
    ])

    linea_actual_id = fields.Many2one('portalgestor.asignacion.linea')
    linea_conflicto_id = fields.Many2one('portalgestor.asignacion.linea')
    batch_conflict_line_ids = fields.Many2many(
        'portalgestor.asignacion.linea',
        'portalgestor_conflict_wizard_line_rel',
        'wizard_id',
        'line_id',
        string='Lineas en conflicto',
    )
    info_resumen = fields.Text(string='Resumen de avisos')
    mensaje = fields.Text(compute='_compute_mensaje')
    can_override = fields.Boolean(compute='_compute_can_override')

    @staticmethod
    def _format_hora(hora):
        return '%02d:%02d' % (int(hora), int((hora % 1) * 60))

    @api.depends('conflict_type', 'linea_actual_id', 'linea_conflicto_id', 'info_resumen')
    def _compute_mensaje(self):
        for record in self:
            if record.conflict_type == 'overlapping':
                trabajador = record.linea_actual_id.trabajador_id.name or ''
                usuario_conflicto = record.linea_conflicto_id.asignacion_id.usuario_id.display_name or ''
                horas_conflicto = (
                    f"{self._format_hora(record.linea_conflicto_id.hora_inicio)} - "
                    f"{self._format_hora(record.linea_conflicto_id.hora_fin)}"
                )
                record.mensaje = (
                    f"Atencion. El AP {trabajador} ya esta asignado al usuario "
                    f"{usuario_conflicto} en el horario {horas_conflicto}. Si confirmas, la franja "
                    f"anterior quedara sin AP asignado para su revision."
                )
            elif record.conflict_type == 'overlapping_batch':
                total = len(record.batch_conflict_line_ids)
                record.mensaje = (
                    f"Atencion. Se van a reemplazar {total} tramos ya asignados en el trabajo fijo. "
                    "Si confirmas, esas franjas anteriores quedaran sin AP asignado para su revision.\n\n"
                    + (record.info_resumen or '')
                )
            elif record.conflict_type == 'protected_intecum_overlapping':
                trabajador = record.linea_actual_id.trabajador_id.name or ''
                usuario_conflicto = record.linea_conflicto_id.asignacion_id.usuario_id.display_name or ''
                horas_conflicto = (
                    f"{self._format_hora(record.linea_conflicto_id.hora_inicio)} - "
                    f"{self._format_hora(record.linea_conflicto_id.hora_fin)}"
                )
                record.mensaje = (
                    f"El AP {trabajador} ya esta asignado a {usuario_conflicto} en el horario "
                    f"{horas_conflicto}. Los gestores Agusto no pueden sobrescribir horarios de usuarios Intecum."
                )
            elif record.conflict_type == 'protected_intecum_overlapping_batch':
                record.mensaje = (
                    "Hay tramos del trabajo fijo que ya pertenecen a usuarios Intecum. "
                    "Los gestores Agusto no pueden sobrescribirlos.\n\n"
                    + (record.info_resumen or '')
                )
            elif record.conflict_type == 'info_same_day':
                record.mensaje = (
                    "Los siguientes APs ya tienen asignaciones el mismo dia "
                    "con otros usuarios. Puede que no haya tiempo de desplazamiento:\n\n"
                    + (record.info_resumen or '')
                    + "\n\nDeseas confirmar el horario de todas formas?"
                )
            else:
                record.mensaje = ''

    @api.depends('conflict_type')
    def _compute_can_override(self):
        for record in self:
            record.can_override = record.conflict_type in ('overlapping', 'overlapping_batch', 'info_same_day')

    def _resume_verification(self):
        self.ensure_one()
        if self.asignacion_mensual_id:
            return self.asignacion_mensual_id.with_context(
                portalgestor_skip_fixed_sync_before_verify=True,
            ).action_verificar_y_confirmar()
        return self.asignacion_id.action_verificar_y_confirmar()

    def action_confirm(self):
        self.ensure_one()
        if self.conflict_type in ('protected_intecum_overlapping', 'protected_intecum_overlapping_batch'):
            raise AccessError("Los gestores Agusto no pueden sobrescribir horarios de usuarios Intecum.")
        if self.conflict_type == 'overlapping':
            self.linea_conflicto_id.write({'trabajador_id': False})
            result = self._resume_verification()
            if isinstance(result, dict):
                return result
            return {'type': 'ir.actions.act_window_close'}
        if self.conflict_type == 'overlapping_batch':
            self.batch_conflict_line_ids.write({'trabajador_id': False})
            result = self._resume_verification()
            if isinstance(result, dict):
                return result
            return {'type': 'ir.actions.act_window_close'}

        if self.conflict_type == 'info_same_day':
            self.asignacion_id._apply_confirmation_as_current_manager()
            if self.asignacion_mensual_id:
                result = self._resume_verification()
                if isinstance(result, dict):
                    return result
            return {'type': 'ir.actions.act_window_close'}

        return {'type': 'ir.actions.act_window_close'}
