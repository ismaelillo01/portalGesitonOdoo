# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FestivoLocal(models.Model):
    _name = 'trabajadores.festivo.local'
    _description = 'Festivo local AP'
    _order = 'fecha desc, id desc'

    _sql_constraints = [
        (
            'trabajadores_festivo_local_unique_worker_date_localidad',
            'unique(trabajador_id, fecha, localidad_id)',
            'Ya existe un festivo local para este AP en esa fecha y localidad.',
        ),
    ]

    name = fields.Char(
        string='Descripción',
        required=True,
    )
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        required=True,
        ondelete='cascade',
        index=True,
    )
    fecha = fields.Date(string='Fecha', required=True, index=True)
    localidad_id = fields.Many2one(
        'zonastrabajo.localidad',
        string='Localidad',
        ondelete='restrict',
        index=True,
    )
    active = fields.Boolean(string='Activo', default=True)

    def _get_local_holiday_label(self):
        self.ensure_one()
        description = (self.name or '').strip()
        localidad = (self.localidad_id.display_name or self.localidad_id.name or '').strip()
        if description and localidad:
            return "%s (%s)" % (description, localidad)
        return description or localidad

    @api.model
    def _ensure_worker_date_is_available(self, trabajador_id, fecha, localidad_id, exclude_ids=None):
        if not trabajador_id or not fecha or not localidad_id:
            return
        duplicate_domain = [
            ('trabajador_id', '=', trabajador_id),
            ('fecha', '=', fecha),
        ]
        if exclude_ids:
            duplicate_domain.append(('id', 'not in', exclude_ids))
        duplicate_records = self.search(duplicate_domain)
        if duplicate_records.filtered(lambda record: not record.localidad_id or record.localidad_id.id == localidad_id):
            raise ValidationError(_("Ya existe un festivo local para este AP en esa fecha y localidad."))

    @api.model_create_multi
    def create(self, vals_list):
        seen_keys = set()
        for vals in vals_list:
            trabajador_id = vals.get('trabajador_id')
            fecha = vals.get('fecha')
            localidad_id = vals.get('localidad_id')
            if not trabajador_id or not fecha or not localidad_id:
                raise ValidationError(_("Debes seleccionar una localidad para el festivo del AP."))
            if isinstance(localidad_id, tuple):
                localidad_id = localidad_id[0]
            if isinstance(localidad_id, list):
                localidad_id = localidad_id[0] if localidad_id else False
            if not localidad_id:
                continue
            worker_id = trabajador_id[0] if isinstance(trabajador_id, tuple) else trabajador_id
            key = (worker_id, fields.Date.to_date(fecha), localidad_id)
            if key in seen_keys:
                raise ValidationError(_("Ya existe un festivo local para este AP en esa fecha y localidad."))
            seen_keys.add(key)
            self._ensure_worker_date_is_available(worker_id, key[1], localidad_id)
        return super().create(vals_list)

    def write(self, vals):
        for record in self:
            trabajador_id = vals.get('trabajador_id', record.trabajador_id.id)
            fecha = vals.get('fecha', record.fecha)
            localidad_id = vals.get('localidad_id', record.localidad_id.id)
            if isinstance(trabajador_id, tuple):
                trabajador_id = trabajador_id[0]
            if isinstance(localidad_id, tuple):
                localidad_id = localidad_id[0]
            fecha = fields.Date.to_date(fecha) if fecha else False
            if not localidad_id:
                raise ValidationError(_("Debes seleccionar una localidad para el festivo del AP."))
            self._ensure_worker_date_is_available(trabajador_id, fecha, localidad_id, exclude_ids=record.ids)
        return super().write(vals)

    @api.constrains('trabajador_id')
    def _check_worker_is_active(self):
        for record in self:
            if record.trabajador_id and record.trabajador_id.baja:
                raise ValidationError(_("No puedes registrar un festivo local para un AP dado de baja."))

    @api.constrains('trabajador_id', 'fecha', 'localidad_id')
    def _check_duplicate_worker_date(self):
        for record in self:
            if not record.trabajador_id or not record.fecha or not record.localidad_id:
                continue
            duplicate_domain = [
                ('id', '!=', record.id),
                ('trabajador_id', '=', record.trabajador_id.id),
                ('fecha', '=', record.fecha),
            ]
            duplicate_records = self.search(duplicate_domain)
            if duplicate_records.filtered(
                lambda duplicate: not duplicate.localidad_id or duplicate.localidad_id.id == record.localidad_id.id
            ):
                raise ValidationError(_("Ya existe un festivo local para este AP en esa fecha y localidad."))

    @api.constrains('localidad_id')
    def _check_localidad_required(self):
        for record in self:
            if not record.localidad_id:
                raise ValidationError(_("Debes seleccionar una localidad para el festivo del AP."))
