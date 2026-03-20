# -*- coding: utf-8 -*-
from odoo import models


class Trabajador(models.Model):
    _inherit = 'trabajadores.trabajador'

    def write(self, vals):
        trabajadores_baja = self.browse()
        if vals.get('baja') is True:
            trabajadores_baja = self.filtered(lambda trabajador: not trabajador.baja)

        result = super().write(vals)

        if trabajadores_baja:
            self.env['portalgestor.asignacion'].release_future_worker_assignments(trabajadores_baja.ids)

        return result


class Usuario(models.Model):
    _inherit = 'usuarios.usuario'

    def write(self, vals):
        usuarios_baja = self.browse()
        if vals.get('baja') is True:
            usuarios_baja = self.filtered(lambda usuario: not usuario.baja)

        result = super().write(vals)

        if usuarios_baja:
            self.env['portalgestor.asignacion'].cancel_future_user_assignments(usuarios_baja.ids)

        return result
