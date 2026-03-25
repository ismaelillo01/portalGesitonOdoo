# -*- coding: utf-8 -*-
from odoo import api, fields, models


class Trabajador(models.Model):
    _name = 'trabajadores.trabajador'
    _description = 'AP'

    name = fields.Char(string='Nombre', required=True)
    apellido1 = fields.Char(string='Primer Apellido')
    apellido2 = fields.Char(string='Segundo Apellido')
    dni_nie = fields.Char(string='DNI o NIE')
    telefono = fields.Char(string='Teléfono')
    direccion = fields.Char(string='Dirección')
    baja = fields.Boolean(string='Baja', default=False)
    color = fields.Integer(string='Color', default=0)
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
    def _get_excluded_vacation_worker_ids(self):
        fecha = self.env.context.get('exclude_vacaciones_fecha')
        fecha_inicio = self.env.context.get('exclude_vacaciones_fecha_inicio')
        fecha_fin = self.env.context.get('exclude_vacaciones_fecha_fin')

        if fecha and not (fecha_inicio or fecha_fin):
            fecha_inicio = fecha
            fecha_fin = fecha

        fecha_inicio = fields.Date.to_date(fecha_inicio) if fecha_inicio else False
        fecha_fin = fields.Date.to_date(fecha_fin) if fecha_fin else False
        if not fecha_inicio and not fecha_fin:
            return []

        fecha_inicio = fecha_inicio or fecha_fin
        fecha_fin = fecha_fin or fecha_inicio
        if fecha_inicio > fecha_fin:
            fecha_inicio, fecha_fin = fecha_fin, fecha_inicio

        return [
            trabajador.id
            for trabajador, __count in self.env['trabajadores.vacacion']._read_group(
                [
                    ('date_start', '<=', fecha_fin),
                    ('date_stop', '>=', fecha_inicio),
                ],
                ['trabajador_id'],
                ['__count'],
            )
            if trabajador
        ]

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        trabajadores_vacaciones = self._get_excluded_vacation_worker_ids()
        if trabajadores_vacaciones:
            if isinstance(domain, tuple):
                domain = list(domain)
            elif not isinstance(domain, list):
                domain = []
            domain = domain + [('id', 'not in', trabajadores_vacaciones)]

        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)
