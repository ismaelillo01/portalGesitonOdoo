# -*- coding: utf-8 -*-
from odoo import api, fields, models


class Trabajador(models.Model):
    _name = 'trabajadores.trabajador'
    _description = 'Trabajador'

    name = fields.Char(string='Nombre', required=True)
    apellido1 = fields.Char(string='Primer Apellido')
    apellido2 = fields.Char(string='Segundo Apellido')
    dni_nie = fields.Char(string='DNI o NIE')
    telefono = fields.Char(string='Teléfono')
    direccion = fields.Char(string='Dirección')
    baja = fields.Boolean(string='Baja', default=False)
    vacaciones_ids = fields.One2many('trabajadores.vacacion', 'trabajador_id', string='Vacaciones')

    grupo = fields.Selection([
        ('intecum', 'Intecum'),
        ('agusto', 'Agusto')
    ], string='Grupo', required=True, index=True)

    zona_trabajo_ids = fields.Many2many(
        'zonastrabajo.zona',
        'trabajadores_trabajador_zona_rel',
        'trabajador_id',
        'zona_id',
        string='Zonas de Trabajo',
        required=True,
    )

    @api.depends('name', 'apellido1', 'apellido2')
    def _compute_display_name(self):
        for record in self:
            parts = [part for part in [record.name, record.apellido1, record.apellido2] if part]
            record.display_name = " ".join(parts) if parts else ''

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        fecha = self.env.context.get('exclude_vacaciones_fecha')
        if fecha:
            # El contexto puede enviar la fecha como string ISO desde la vista JS
            if isinstance(fecha, str):
                fecha = fields.Date.to_date(fecha)
            if fecha:
                trabajadores_vacaciones = [
                    trabajador.id
                    for trabajador, __count in self.env['trabajadores.vacacion']._read_group(
                        [
                            ('date_start', '<=', fecha),
                            ('date_stop', '>=', fecha),
                        ],
                        ['trabajador_id'],
                        ['__count'],
                    )
                    if trabajador
                ]
                if trabajadores_vacaciones:
                    if isinstance(domain, tuple):
                        domain = list(domain)
                    elif not isinstance(domain, list):
                        domain = []
                    domain = domain + [('id', 'not in', trabajadores_vacaciones)]

        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)
