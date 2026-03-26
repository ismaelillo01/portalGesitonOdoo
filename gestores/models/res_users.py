# -*- coding: utf-8 -*-
from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

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
