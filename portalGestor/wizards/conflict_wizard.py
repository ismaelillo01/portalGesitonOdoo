# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ConflictWizard(models.TransientModel):
    _name = 'portalgestor.conflict.wizard'
    _description = 'Asistente de Conflictos de Horario'

    asignacion_id = fields.Many2one('portalgestor.asignacion')
    asignacion_mensual_id = fields.Many2one('portalgestor.asignacion.mensual')
    conflict_type = fields.Selection([
        ('overlapping', 'Solapamiento de Horas'),
        ('info_same_day', 'Aviso informativo: mismo dia'),
    ])

    linea_actual_id = fields.Many2one('portalgestor.asignacion.linea')
    linea_conflicto_id = fields.Many2one('portalgestor.asignacion.linea')
    info_resumen = fields.Text(string='Resumen de avisos')
    mensaje = fields.Text(compute='_compute_mensaje')

    @staticmethod
    def _format_hora(hora):
        return '%02d:%02d' % (int(hora), int((hora % 1) * 60))

    @api.depends('conflict_type', 'linea_actual_id', 'linea_conflicto_id', 'info_resumen')
    def _compute_mensaje(self):
        for record in self:
            if record.conflict_type == 'overlapping':
                trabajador = record.linea_actual_id.trabajador_id.name or ''
                usuario_conflicto = record.linea_conflicto_id.asignacion_id.usuario_id.name or ''
                horas_conflicto = (
                    f"{self._format_hora(record.linea_conflicto_id.hora_inicio)} - "
                    f"{self._format_hora(record.linea_conflicto_id.hora_fin)}"
                )
                record.mensaje = (
                    f"Atencion. El trabajador {trabajador} ya esta asignado al usuario "
                    f"{usuario_conflicto} en el horario {horas_conflicto}. Si confirmas, la franja "
                    f"anterior quedara sin trabajador asignado para su revision."
                )
            elif record.conflict_type == 'info_same_day':
                record.mensaje = (
                    "Los siguientes trabajadores ya tienen asignaciones el mismo dia "
                    "con otros usuarios. Puede que no haya tiempo de desplazamiento:\n\n"
                    + (record.info_resumen or '')
                    + "\n\nDeseas confirmar el horario de todas formas?"
                )
            else:
                record.mensaje = ''

    def _resume_verification(self):
        self.ensure_one()
        if self.asignacion_mensual_id:
            return self.asignacion_mensual_id.with_context(
                portalgestor_skip_fixed_sync_before_verify=True,
            ).action_verificar_y_confirmar()
        return self.asignacion_id.action_verificar_y_confirmar()

    def action_confirm(self):
        self.ensure_one()
        if self.conflict_type == 'overlapping':
            self.linea_conflicto_id.write({'trabajador_id': False})
            result = self._resume_verification()
            if isinstance(result, dict):
                return result
            return {'type': 'ir.actions.act_window_close'}

        if self.conflict_type == 'info_same_day':
            self.asignacion_id.confirmado = True
            if self.asignacion_mensual_id:
                result = self._resume_verification()
                if isinstance(result, dict):
                    return result
            return {'type': 'ir.actions.act_window_close'}

        return {'type': 'ir.actions.act_window_close'}
