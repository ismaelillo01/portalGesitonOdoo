# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PortalGestorUsuarioApMovilidad(models.Model):
    _name = 'portalgestor.usuario.ap.movilidad'
    _description = 'Movilidad por Usuario y AP'
    _order = 'usuario_id, trabajador_id, id'
    _rec_name = 'display_name'

    usuario_id = fields.Many2one(
        'usuarios.usuario',
        string='Usuario',
        required=True,
        ondelete='cascade',
        index=True,
    )
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        required=True,
        ondelete='cascade',
        index=True,
    )
    kilometraje_km = fields.Float(string='Kilometraje', default=0.0)
    desplazamiento_horas = fields.Float(string='Desplazamiento', default=0.0)
    display_name = fields.Char(string='Movilidad', compute='_compute_display_name')

    _sql_constraints = [
        (
            'portalgestor_usuario_ap_movilidad_unique_pair',
            'unique(usuario_id, trabajador_id)',
            'Ya existe una configuracion de movilidad para este usuario y AP.',
        ),
    ]

    @api.depends('usuario_id.display_name', 'trabajador_id.display_name')
    def _compute_display_name(self):
        for record in self:
            usuario_name = record.usuario_id.display_name or record.usuario_id.name or ''
            trabajador_name = record.trabajador_id.display_name or record.trabajador_id.name or ''
            record.display_name = f'{usuario_name} - {trabajador_name}'.strip(' -')

    @api.constrains('kilometraje_km', 'desplazamiento_horas')
    def _check_non_negative_values(self):
        for record in self:
            if record.kilometraje_km < 0:
                raise ValidationError(_('El kilometraje no puede ser negativo.'))
            if record.desplazamiento_horas < 0:
                raise ValidationError(_('El desplazamiento no puede ser negativo.'))

    @api.model
    def _get_or_create_for_pair(self, usuario_id, trabajador_id):
        if not usuario_id or not trabajador_id:
            return self.browse()
        Mobility = self.sudo()
        mobility = Mobility.search([
            ('usuario_id', '=', usuario_id),
            ('trabajador_id', '=', trabajador_id),
        ], limit=1)
        if mobility:
            return mobility
        return Mobility.create({
            'usuario_id': usuario_id,
            'trabajador_id': trabajador_id,
        })


class PortalGestorUsuarioApMovilidadMixin(models.AbstractModel):
    _register = False

    kilometraje_km = fields.Float(
        string='Kilometraje',
        compute='_compute_portalgestor_movilidad_values',
        inverse='_inverse_portalgestor_kilometraje_km',
        readonly=False,
    )
    desplazamiento_horas = fields.Float(
        string='Desplazamiento',
        compute='_compute_portalgestor_movilidad_values',
        inverse='_inverse_portalgestor_desplazamiento_horas',
        readonly=False,
    )

    def _portalgestor_get_movilidad_usuario(self):
        return self.env['usuarios.usuario']

    def _portalgestor_get_movilidad_pair_ids(self):
        self.ensure_one()
        usuario = self._portalgestor_get_movilidad_usuario()
        trabajador = self.trabajador_id if 'trabajador_id' in self._fields else False
        return (
            usuario.id if usuario and usuario.id else False,
            trabajador.id if trabajador and trabajador.id else False,
        )

    @api.depends('trabajador_id')
    def _compute_portalgestor_movilidad_values(self):
        record_pairs = []
        usuario_ids = set()
        trabajador_ids = set()
        for record in self:
            pair = record._portalgestor_get_movilidad_pair_ids()
            record_pairs.append((record, pair))
            if pair[0] and pair[1]:
                usuario_ids.add(pair[0])
                trabajador_ids.add(pair[1])

        mobility_map = {}
        if usuario_ids and trabajador_ids:
            mobility_records = self.env['portalgestor.usuario.ap.movilidad'].sudo().search([
                ('usuario_id', 'in', list(usuario_ids)),
                ('trabajador_id', 'in', list(trabajador_ids)),
            ])
            mobility_map = {
                (mobility.usuario_id.id, mobility.trabajador_id.id): mobility
                for mobility in mobility_records
            }

        for record, pair in record_pairs:
            mobility = mobility_map.get(pair)
            record.kilometraje_km = mobility.kilometraje_km if mobility else 0.0
            record.desplazamiento_horas = mobility.desplazamiento_horas if mobility else 0.0

    def _portalgestor_write_movilidad_values(self, field_names):
        Mobility = self.env['portalgestor.usuario.ap.movilidad']
        for record in self:
            usuario_id, trabajador_id = record._portalgestor_get_movilidad_pair_ids()
            if not usuario_id or not trabajador_id:
                continue
            vals = {}
            if 'kilometraje_km' in field_names:
                if record.kilometraje_km < 0:
                    raise ValidationError(_('El kilometraje no puede ser negativo.'))
                vals['kilometraje_km'] = record.kilometraje_km or 0.0
            if 'desplazamiento_horas' in field_names:
                if record.desplazamiento_horas < 0:
                    raise ValidationError(_('El desplazamiento no puede ser negativo.'))
                vals['desplazamiento_horas'] = record.desplazamiento_horas or 0.0
            if vals:
                Mobility._get_or_create_for_pair(usuario_id, trabajador_id).write(vals)

    def _inverse_portalgestor_kilometraje_km(self):
        self._portalgestor_write_movilidad_values({'kilometraje_km'})

    def _inverse_portalgestor_desplazamiento_horas(self):
        self._portalgestor_write_movilidad_values({'desplazamiento_horas'})

    @api.onchange('trabajador_id')
    def _onchange_portalgestor_movilidad_pair(self):
        for record in self:
            record._compute_portalgestor_movilidad_values()


class PortalGestorAsignacionLineaMovilidad(PortalGestorUsuarioApMovilidadMixin, models.Model):
    _inherit = 'portalgestor.asignacion.linea'

    def _portalgestor_get_movilidad_usuario(self):
        self.ensure_one()
        return self.asignacion_id.usuario_id


class PortalGestorAsignacionMensualLineaMovilidad(PortalGestorUsuarioApMovilidadMixin, models.Model):
    _inherit = 'portalgestor.asignacion.mensual.linea'

    def _portalgestor_get_movilidad_usuario(self):
        self.ensure_one()
        return self.asignacion_mensual_id.usuario_id


class PortalGestorAsignacionMensualDiaLineaMovilidad(PortalGestorUsuarioApMovilidadMixin, models.Model):
    _inherit = 'portalgestor.asignacion.mensual.dia.linea'

    def _portalgestor_get_movilidad_usuario(self):
        self.ensure_one()
        parent = self.asignacion_mensual_id or self.template_day_id.asignacion_mensual_id
        return parent.usuario_id


class PortalGestorTrabajoFijoLineaMovilidad(PortalGestorUsuarioApMovilidadMixin, models.Model):
    _inherit = 'portalgestor.trabajo_fijo.linea'

    def _portalgestor_get_movilidad_usuario(self):
        self.ensure_one()
        return self.trabajo_fijo_id.usuario_id
