# -*- coding: utf-8 -*-
from odoo import api, fields, models


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

    fecha_baja = fields.Date(
        string='Fecha de baja',
        copy=False,
        help='Fecha desde la que se cancelarán los horarios al dar de baja al usuario.',
    )

    @api.onchange('baja')
    def _onchange_baja_fecha_baja(self):
        """Al activar baja propone hoy como fecha; al desactivarla limpia la fecha."""
        if self.baja:
            if not self.fecha_baja:
                self.fecha_baja = fields.Date.today()
        else:
            self.fecha_baja = False

    def write(self, vals):
        usuarios_baja = self.browse()
        if vals.get('baja') is True:
            usuarios_baja = self.filtered(lambda usuario: not usuario.baja)

        result = super().write(vals)

        if usuarios_baja:
            for usuario in usuarios_baja:
                # Usa fecha_baja ya escrita (viene de vals o del registro)
                self.env['portalgestor.asignacion'].cancel_future_user_assignments(
                    [usuario.id],
                    start_date=usuario.fecha_baja,
                )

        return result
