# -*- coding: utf-8 -*-
from odoo import fields, models


class AsignacionMensualExcepcion(models.Model):
    _name = 'portalgestor.asignacion.mensual.excepcion'
    _description = 'Excepcion de Trabajo Fijo por Dia'
    _order = 'fecha desc, id desc'

    _sql_constraints = [
        (
            'unique_asignacion_fecha',
            'unique(asignacion_mensual_id, fecha)',
            'Ya existe una excepcion para este trabajo fijo en esa fecha.',
        )
    ]

    asignacion_mensual_id = fields.Many2one(
        'portalgestor.asignacion.mensual',
        string='Trabajo fijo',
        required=True,
        ondelete='cascade',
        index=True,
    )
    asignacion_mensual_linea_id = fields.Many2one(
        'portalgestor.asignacion.mensual.linea',
        string='Tramo fijo',
        ondelete='set null',
        index=True,
    )
    fecha = fields.Date(
        string='Fecha',
        required=True,
        index=True,
    )
    tipo = fields.Selection(
        selection=[
            ('manual', 'Cambio manual'),
            ('omit', 'Omitido'),
        ],
        string='Tipo',
        required=True,
        default='manual',
    )
