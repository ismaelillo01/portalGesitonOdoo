# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class UsuariosKilometrajeConfig(models.TransientModel):
    _name = 'usuarios.kilometraje.config'
    _description = 'Configuracion de kilometraje'

    PARAM_KILOMETRAJE_VALOR_KM = 'usuarios.kilometraje.valor_km'
    DEFAULT_KILOMETRAJE_VALOR_KM = 0.26

    valor_km = fields.Float(
        string='Valor por kilometro',
        required=True,
        default=lambda self: self.get_kilometraje_rate(),
    )

    @api.model
    def get_kilometraje_rate(self):
        value = self.env['ir.config_parameter'].sudo().get_param(
            self.PARAM_KILOMETRAJE_VALOR_KM,
            default=str(self.DEFAULT_KILOMETRAJE_VALOR_KM),
        )
        try:
            return max(float(value or 0.0), 0.0)
        except (TypeError, ValueError):
            return self.DEFAULT_KILOMETRAJE_VALOR_KM

    @api.constrains('valor_km')
    def _check_valor_km(self):
        for record in self:
            if record.valor_km < 0:
                raise ValidationError(_('El valor por kilometro no puede ser negativo.'))

    def action_save(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            self.PARAM_KILOMETRAJE_VALOR_KM,
            str(self.valor_km or 0.0),
        )
        return {'type': 'ir.actions.act_window_close'}
