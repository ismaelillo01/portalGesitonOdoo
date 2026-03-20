# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ConflictWizard(models.TransientModel):
    _name = 'portalgestor.conflict.wizard'
    _description = 'Asistente de Conflictos de Horario'

    asignacion_id = fields.Many2one('portalgestor.asignacion')
    conflict_type = fields.Selection([
        ('overlapping', 'Solapamiento de Horas'),
        ('info_same_day', 'Aviso informativo: mismo día'),
    ])
    
    linea_actual_id = fields.Many2one('portalgestor.asignacion.linea')
    linea_conflicto_id = fields.Many2one('portalgestor.asignacion.linea')
    
    # Campo de texto libre para el resumen informativo (info_same_day)
    info_resumen = fields.Text(string='Resumen de avisos')
    
    mensaje = fields.Text(compute='_compute_mensaje')

    @staticmethod
    def _format_hora(h):
        """Convierte un float de horas (ej: 9.5) a formato HH:MM (ej: '09:30')."""
        return '%02d:%02d' % (int(h), int((h % 1) * 60))

    @api.depends('conflict_type', 'linea_actual_id', 'linea_conflicto_id', 'info_resumen')
    def _compute_mensaje(self):
        for record in self:
            if record.conflict_type == 'overlapping':
                trabajador = record.linea_actual_id.trabajador_id.name or ''
                usuario_conflicto = record.linea_conflicto_id.asignacion_id.usuario_id.name or ''
                horas_conf = f"{self._format_hora(record.linea_conflicto_id.hora_inicio)} - {self._format_hora(record.linea_conflicto_id.hora_fin)}"
                record.mensaje = (
                    f"¡Atención! El trabajador {trabajador} ya está asignado al usuario "
                    f"{usuario_conflicto} en el horario {horas_conf}. Si confirmas, la franja "
                    f"anterior quedará sin trabajador asignado para su revisión."
                )
            elif record.conflict_type == 'info_same_day':
                record.mensaje = (
                    "Los siguientes trabajadores ya tienen asignaciones el mismo día "
                    "con otros usuarios. Puede que no haya tiempo de desplazamiento:\n\n"
                    + (record.info_resumen or '')
                    + "\n\n¿Deseas confirmar el horario de todas formas?"
                )
            else:
                record.mensaje = ''

    def action_confirm(self):
        if self.conflict_type == 'overlapping':
            # Vaciar el trabajador para que el gestor vea que esa franja necesita reasignación
            self.linea_conflicto_id.write({'trabajador_id': False})
            
            # Re-verificar: puede haber más solapamientos
            result = self.asignacion_id.action_verificar_y_confirmar()
            if isinstance(result, dict):
                return result
            return {'type': 'ir.actions.act_window_close'}
        
        elif self.conflict_type == 'info_same_day':
            # Aviso informativo aceptado → confirmar directamente SIN re-verificar
            self.asignacion_id.confirmado = True
            return {'type': 'ir.actions.act_window_close'}
        
        return {'type': 'ir.actions.act_window_close'}
