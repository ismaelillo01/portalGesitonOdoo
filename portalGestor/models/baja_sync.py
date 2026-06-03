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
        # Caso 1: baja pasa de False → True (nueva baja)
        nuevos_en_baja = self.browse()
        if vals.get('baja') is True:
            nuevos_en_baja = self.filtered(lambda u: not u.baja)

        # Caso 2: fecha_baja cambia mientras baja ya está activa
        # (el usuario corrigió la fecha sin tocar el checkbox)
        ya_en_baja_con_nueva_fecha = self.browse()
        if 'fecha_baja' in vals and vals.get('fecha_baja') and vals.get('baja') is not True:
            ya_en_baja_con_nueva_fecha = self.filtered(lambda u: u.baja)

        usuarios_a_cancelar = nuevos_en_baja | ya_en_baja_con_nueva_fecha

        result = super().write(vals)

        if usuarios_a_cancelar:
            for usuario in usuarios_a_cancelar:
                # fecha_baja ya está escrita en DB; usarla como start_date
                self.env['portalgestor.asignacion'].cancel_future_user_assignments(
                    [usuario.id],
                    start_date=usuario.fecha_baja,
                )

        return result
