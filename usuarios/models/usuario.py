# -*- coding: utf-8 -*-
from odoo import api, fields, models


class UsuarioServicio(models.Model):
    _name = 'usuarios.servicio'
    _description = 'Servicio de Usuario'
    _order = 'sequence, name, id'

    name = fields.Char(string='Servicio', required=True)
    code = fields.Char(string='Codigo', required=True, index=True)
    sequence = fields.Integer(string='Secuencia', default=10)

    _sql_constraints = [
        ('usuarios_servicio_code_uniq', 'unique(code)', 'El codigo del servicio debe ser unico.'),
    ]


class Usuario(models.Model):
    _name = 'usuarios.usuario'
    _description = 'Usuario'

    _GROUP_UI_DATA = {
        'agusto': {'badge': 'A', 'label': 'Agusto'},
        'intecum': {'badge': 'I', 'label': 'Intecum'},
    }

    name = fields.Char(string='Nombre', required=True)
    apellido1 = fields.Char(string='Primer Apellido')
    apellido2 = fields.Char(string='Segundo Apellido')
    dni_nie = fields.Char(string='DNI o NIE')
    telefono = fields.Char(string='Telefono')
    direccion = fields.Char(string='Direccion')
    baja = fields.Boolean(string='Baja', default=False)
    servicio_ids = fields.Many2many(
        'usuarios.servicio',
        'usuarios_usuario_servicio_rel',
        'usuario_id',
        'servicio_id',
        string='Servicios',
    )
    has_ap_service = fields.Boolean(
        string='Servicio AP activo',
        compute='_compute_has_ap_service',
        store=True,
        index=True,
    )

    grupo = fields.Selection([
        ('intecum', 'Intecum'),
        ('agusto', 'Agusto')
    ], string='Grupo', required=True, index=True)

    zona_trabajo_id = fields.Many2one(
        'zonastrabajo.zona',
        string='Zona de Trabajo',
        required=True,
        ondelete='restrict',
        index=True,
    )

    @api.depends('name', 'apellido1', 'apellido2')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record._get_full_name()

    @api.depends('servicio_ids.code')
    def _compute_has_ap_service(self):
        for record in self:
            record.has_ap_service = any(service.code == 'ap' for service in record.servicio_ids)

    def _get_full_name(self):
        self.ensure_one()
        parts = [part for part in [self.name, self.apellido1, self.apellido2] if part]
        return ' '.join(parts)

    def _get_service_names(self):
        self.ensure_one()
        return ', '.join(
            self.servicio_ids.sorted(key=lambda service: (service.sequence, service.name)).mapped('name')
        )

    @api.model
    def _get_group_ui_data(self, grupo):
        return dict(self._GROUP_UI_DATA.get(grupo, {'badge': '', 'label': ''}))

    @api.model
    def get_portalgestor_user_types(self, user_ids):
        users = self.browse(user_ids).exists()
        return {
            user.id: self._get_group_ui_data(user.grupo)
            for user in users
        }
