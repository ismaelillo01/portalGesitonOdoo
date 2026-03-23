# -*- coding: utf-8 -*-
from odoo import _, models


class Usuario(models.Model):
    _inherit = 'usuarios.usuario'

    def action_open_horario_usuario_report_wizard(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'portalGestor.action_portalgestor_usuario_report_wizard'
        )
        action['context'] = {
            'default_usuario_ids': self.ids,
            'active_model': 'usuarios.usuario',
            'active_ids': self.ids,
        }
        return action
