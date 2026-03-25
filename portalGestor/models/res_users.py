# -*- coding: utf-8 -*-
from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _get_portalgestor_home_action(self):
        return self.env.ref('portalGestor.action_portalgestor_asignacion', raise_if_not_found=False)

    @api.model_create_multi
    def create(self, vals_list):
        action = self._get_portalgestor_home_action()
        if action:
            for vals in vals_list:
                vals.setdefault('action_id', action.id)
        return super().create(vals_list)

    @api.model
    def set_portalgestor_home_action_for_internal_users(self):
        action = self._get_portalgestor_home_action()
        if not action:
            return False

        users = self.with_context(active_test=False).search([('share', '=', False)])
        users.write({'action_id': action.id})
        return True
