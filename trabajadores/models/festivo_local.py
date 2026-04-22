# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FestivoLocal(models.Model):
    _name = 'trabajadores.festivo.local'
    _description = 'Festivo local'
    _order = 'fecha desc, id desc'

    name = fields.Char(
        string='Descripcion',
        required=True,
    )
    fecha = fields.Date(string='Fecha', required=True, index=True)
    localidad_id = fields.Many2one(
        'zonastrabajo.localidad',
        string='Localidad',
        required=True,
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
    def _ensure_locality_date_is_available(self, fecha, localidad_id, exclude_ids=None):
        if not fecha or not localidad_id:
            return
        duplicate_domain = [
            ('fecha', '=', fecha),
            ('localidad_id', '=', localidad_id),
        ]
        if exclude_ids:
            duplicate_domain.append(('id', 'not in', exclude_ids))
        if self.search_count(duplicate_domain):
            raise ValidationError(_("Ya existe un festivo local para esta localidad en esa fecha."))

    @api.model_create_multi
    def create(self, vals_list):
        seen_keys = set()
        for vals in vals_list:
            fecha = vals.get('fecha')
            localidad_id = vals.get('localidad_id')
            if not fecha or not localidad_id:
                raise ValidationError(_("Debes seleccionar una localidad para el festivo local."))
            if isinstance(localidad_id, tuple):
                localidad_id = localidad_id[0]
            if isinstance(localidad_id, list):
                localidad_id = localidad_id[0] if localidad_id else False
            if not localidad_id:
                continue
            key = (fields.Date.to_date(fecha), localidad_id)
            if key in seen_keys:
                raise ValidationError(_("Ya existe un festivo local para esta localidad en esa fecha."))
            seen_keys.add(key)
            self._ensure_locality_date_is_available(key[0], localidad_id)
        return super().create(vals_list)

    def write(self, vals):
        for record in self:
            fecha = vals.get('fecha', record.fecha)
            localidad_id = vals.get('localidad_id', record.localidad_id.id)
            if isinstance(localidad_id, tuple):
                localidad_id = localidad_id[0]
            fecha = fields.Date.to_date(fecha) if fecha else False
            if not localidad_id:
                raise ValidationError(_("Debes seleccionar una localidad para el festivo local."))
            self._ensure_locality_date_is_available(fecha, localidad_id, exclude_ids=record.ids)
        return super().write(vals)

    @api.constrains('fecha', 'localidad_id')
    def _check_duplicate_locality_date(self):
        for record in self:
            if not record.fecha or not record.localidad_id:
                continue
            if self.search_count([
                ('id', '!=', record.id),
                ('fecha', '=', record.fecha),
                ('localidad_id', '=', record.localidad_id.id),
            ]):
                raise ValidationError(_("Ya existe un festivo local para esta localidad en esa fecha."))

    @api.constrains('localidad_id')
    def _check_localidad_required(self):
        for record in self:
            if not record.localidad_id:
                raise ValidationError(_("Debes seleccionar una localidad para el festivo local."))

    def init(self):
        super().init()
        self.env.cr.execute(
            """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_name = %s
                   AND column_name = 'trabajador_id'
            """,
            [self._table],
        )
        if self.env.cr.fetchone():
            self.env.cr.execute(
                """
                    WITH ranked_localities AS (
                        SELECT trabajador_id,
                               localidad_id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY trabajador_id
                                   ORDER BY fecha DESC, id DESC
                               ) AS rn
                          FROM trabajadores_festivo_local
                         WHERE trabajador_id IS NOT NULL
                           AND localidad_id IS NOT NULL
                    )
                    UPDATE trabajadores_trabajador trabajador
                       SET festivo_localidad_id = ranked_localities.localidad_id
                      FROM ranked_localities
                     WHERE ranked_localities.rn = 1
                       AND trabajador.id = ranked_localities.trabajador_id
                       AND (
                           trabajador.festivo_localidad_id IS NULL
                           OR trabajador.festivo_localidad_id <> ranked_localities.localidad_id
                       )
                """
            )

        self.env.cr.execute(
            """
                WITH grouped AS (
                    SELECT localidad_id,
                           fecha,
                           MIN(id) AS keep_id,
                           BOOL_OR(active) AS keep_active
                      FROM trabajadores_festivo_local
                     WHERE localidad_id IS NOT NULL
                       AND fecha IS NOT NULL
                     GROUP BY localidad_id, fecha
                    HAVING COUNT(*) > 1
                )
                UPDATE trabajadores_festivo_local festivo
                   SET active = grouped.keep_active
                  FROM grouped
                 WHERE festivo.id = grouped.keep_id
            """
        )
        self.env.cr.execute(
            """
                DELETE FROM trabajadores_festivo_local festivo
                 USING (
                    SELECT localidad_id,
                           fecha,
                           MIN(id) AS keep_id
                      FROM trabajadores_festivo_local
                     WHERE localidad_id IS NOT NULL
                       AND fecha IS NOT NULL
                     GROUP BY localidad_id, fecha
                    HAVING COUNT(*) > 1
                 ) grouped
                 WHERE festivo.localidad_id = grouped.localidad_id
                   AND festivo.fecha = grouped.fecha
                   AND festivo.id <> grouped.keep_id
            """
        )


class ZonaTrabajoLocalidad(models.Model):
    _inherit = 'zonastrabajo.localidad'

    festivo_local_ids = fields.One2many(
        'trabajadores.festivo.local',
        'localidad_id',
        string='Festivos locales',
    )
