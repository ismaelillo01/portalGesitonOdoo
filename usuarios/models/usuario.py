# -*- coding: utf-8 -*-
from odoo import api, fields, models


class Usuario(models.Model):
    _name = 'usuarios.usuario'
    _description = 'Usuario'

    name = fields.Char(string='Nombre', required=True)
    apellido1 = fields.Char(string='Primer Apellido')
    apellido2 = fields.Char(string='Segundo Apellido')
    dni_nie = fields.Char(string='DNI o NIE')
    telefono = fields.Char(string='Teléfono')
    direccion = fields.Char(string='Dirección')
    baja = fields.Boolean(string='Baja', default=False)

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

    @api.depends('name', 'apellido1')
    def _compute_display_name(self):
        for record in self:
            if record.name and record.apellido1:
                record.display_name = f"{record.name} {record.apellido1}"
            else:
                record.display_name = record.name or ''
