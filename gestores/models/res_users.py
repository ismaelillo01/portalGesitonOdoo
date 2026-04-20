# -*- coding: utf-8 -*-
from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _get_linked_gestor_record(self):
        self.ensure_one()
        gestores = self.env['gestores.gestor'].sudo().search([('user_id', '=', self.id), ('grupo', '!=', 'administrador')])
        if not gestores:
            return self.env['gestores.gestor']

        scope = self._get_gestor_management_scope()
        if scope in ('agusto', 'intecum'):
            scoped_gestor = gestores.filtered(lambda gestor: gestor.grupo == scope)[:1]
            if scoped_gestor:
                return scoped_gestor
        return gestores[:1]

    def _get_linked_gestor_id_for_user_priority(self):
        self.ensure_one()
        if self._get_gestor_management_scope() not in ('agusto', 'intecum'):
            return False
        return self._get_linked_gestor_record().id or False

    def _get_gestor_management_scope(self):
        self.ensure_one()
        if self.has_group('base.group_system') or self.has_group('gestores.group_gestores_administrador'):
            return 'admin'
        if self.has_group('gestores.group_gestores_intecum'):
            return 'intecum'
        if self.has_group('gestores.group_gestores_agusto'):
            return 'agusto'
        return False

    def _can_manage_intecum_records(self):
        self.ensure_one()
        return self._get_gestor_management_scope() in ('admin', 'intecum')

    def _can_manage_target_group(self, target_group):
        self.ensure_one()
        if not target_group:
            return True
        if target_group == 'intecum':
            return self._can_manage_intecum_records()
        return True

    def _should_mask_intecum_users(self):
        self.ensure_one()
        return self._get_gestor_management_scope() == 'agusto'

    def _should_hide_case_manager_apps_sidebar(self):
        self.ensure_one()
        return self._get_gestor_management_scope() in ('agusto', 'intecum')
