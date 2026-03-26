# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import AccessError


class Usuario(models.Model):
    _inherit = 'usuarios.usuario'

    def action_open_horario_usuario_report_wizard(self):
        self.ensure_one()
        if not self.env.user._can_manage_target_group(self.grupo):
            raise AccessError(_("Los gestores Agusto no pueden generar reportes de usuarios de Intecum."))
        action = self.env['ir.actions.act_window']._for_xml_id(
            'portalGestor.action_portalgestor_usuario_report_wizard'
        )
        action['context'] = {
            'default_usuario_ids': self.ids,
            'active_model': 'usuarios.usuario',
            'active_ids': self.ids,
        }
        return action
