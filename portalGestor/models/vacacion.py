# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import AccessError


class Vacacion(models.Model):
    _inherit = 'trabajadores.vacacion'

    @api.model
    def get_assignment_markers(self, trabajador_ids, date_start, date_end):
        if not trabajador_ids or not date_start or not date_end:
            return []

        start_date = fields.Date.to_date(date_start)
        end_date = fields.Date.to_date(date_end)
        if not start_date or not end_date:
            return []

        try:
            fechas_con_asignacion = self.env['portalgestor.asignacion.linea']._read_group(
                [
                    ('trabajador_id', 'in', trabajador_ids),
                    ('fecha', '>=', start_date),
                    ('fecha', '<=', end_date),
                ],
                ['fecha:day'],
                ['__count'],
                order='fecha:day ASC',
            )
        except AccessError:
            return []

        markers = []
        for fecha, __count in fechas_con_asignacion:
            fecha = fields.Date.to_string(fecha)
            if not fecha:
                continue
            markers.append({
                'id': f'portalgestor_workday_{fecha}',
                'date': fecha,
            })
        return markers
