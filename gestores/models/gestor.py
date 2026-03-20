# -*- coding: utf-8 -*-
from odoo import models, fields, api


class Gestor(models.Model):
    _name = 'gestores.gestor'
    _description = 'Gestor'

    name = fields.Char(string="Nombre", required=True)
    grupo = fields.Selection([
        ('intecum', 'Intecum'),
        ('agusto', 'Agusto'),
        ('administrador', 'Administrador')
    ], string="Grupo", required=True)
    user_id = fields.Many2one('res.users', string="Usuario Odoo", help="Usuario de Odoo asociado a este gestor")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._sync_user_groups(records.mapped('user_id'))
        return records

    def write(self, vals):
        previous_users = self.mapped('user_id')
        res = super().write(vals)
        if 'grupo' in vals or 'user_id' in vals:
            self._sync_user_groups(previous_users | self.mapped('user_id'))
        return res

    def unlink(self):
        users = self.mapped('user_id')
        res = super().unlink()
        self._sync_user_groups(users)
        return res

    def _get_managed_groups(self):
        return {
            'intecum': self.env.ref('gestores.group_gestores_intecum', raise_if_not_found=False),
            'agusto': self.env.ref('gestores.group_gestores_agusto', raise_if_not_found=False),
            'administrador': self.env.ref('gestores.group_gestores_administrador', raise_if_not_found=False),
        }

    def _sync_user_groups(self, users):
        managed_groups_by_key = self._get_managed_groups()
        managed_groups = self.env['res.groups']
        for group in managed_groups_by_key.values():
            if group:
                managed_groups |= group

        for user in users.filtered('id'):
            user_gestors = self.search([('user_id', '=', user.id)])
            groups_to_add = self.env['res.groups']
            for gestor in user_gestors:
                group = managed_groups_by_key.get(gestor.grupo)
                if group:
                    groups_to_add |= group

            commands = [(3, group.id) for group in managed_groups if group in user.groups_id]
            commands += [(4, group.id) for group in groups_to_add if group not in user.groups_id]
            if commands:
                user.write({'groups_id': commands})
