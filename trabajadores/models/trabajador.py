# -*- coding: utf-8 -*-
from odoo import api, fields, models


class Trabajador(models.Model):
    _name = 'trabajadores.trabajador'
    _description = 'AP'
    _order = 'name, apellido1, apellido2, id'

    name = fields.Char(string='Nombre', required=True)
    apellido1 = fields.Char(string='Primer Apellido')
    apellido2 = fields.Char(string='Segundo Apellido')
    nombre_completo = fields.Char(
        string='Nombre Apellidos',
        compute='_compute_nombre_completo',
        store=True,
    )
    dni_nie = fields.Char(string='DNI o NIE')
    telefono = fields.Char(string='Teléfono')
    direccion = fields.Char(string='Dirección')
    localidad_id = fields.Many2one(
        'zonastrabajo.localidad',
        string='Localidad',
        ondelete='restrict',
        index=True,
    )
    festivo_localidad_id = fields.Many2one(
        'zonastrabajo.localidad',
        string='Localidad festiva',
        ondelete='restrict',
        index=True,
    )
    festivo_localidad_ids = fields.Many2many(
        'zonastrabajo.localidad',
        'trabajadores_trabajador_festivo_localidad_rel',
        'trabajador_id',
        'localidad_id',
        string='Localidades festivas',
    )
    festivos_locales_ids = fields.Many2many(
        'trabajadores.festivo.local',
        compute='_compute_festivos_locales_ids',
        string='Festivos locales',
        readonly=True,
    )
    carnet_conducir = fields.Boolean(string='Carnet de conducir')
    observaciones = fields.Text(string='Observaciones')
    baja = fields.Boolean(string='Baja', default=False)
    color = fields.Integer(string='Color', default=0)
    vacaciones_ids = fields.One2many('trabajadores.vacacion', 'trabajador_id', string='Vacaciones')
    faltas_justificadas_ids = fields.One2many(
        'trabajadores.falta.justificada',
        'trabajador_id',
        string='Faltas justificadas',
    )
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
    def _compute_nombre_completo(self):
        for record in self:
            parts = [part for part in [record.name, record.apellido1, record.apellido2] if part]
            record.nombre_completo = " ".join(parts) if parts else ''

    @api.depends('festivo_localidad_ids', 'festivo_localidad_ids.festivo_local_ids')
    def _compute_festivos_locales_ids(self):
        for record in self:
            record.festivos_locales_ids = record.festivo_localidad_ids.mapped('festivo_local_ids')

    @api.depends('nombre_completo')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.nombre_completo or ''

    def action_open_faltas_justificadas(self):
        self.ensure_one()
        return {
            'name': 'Faltas justificadas',
            'type': 'ir.actions.act_window',
            'res_model': 'trabajadores.falta.justificada',
            'view_mode': 'list,form',
            'domain': [('trabajador_id', '=', self.id)],
            'context': {
                'default_trabajador_id': self.id,
                'default_localidad_id': self.localidad_id.id or False,
                'search_default_trabajador_id': self.id,
            },
            'target': 'current',
        }

    def action_open_festivos_locales(self):
        self.ensure_one()
        return {
            'name': 'Festivos locales',
            'type': 'ir.actions.act_window',
            'res_model': 'trabajadores.festivo.local',
            'view_mode': 'list,form',
            'domain': [('localidad_id', 'in', self.festivo_localidad_ids.ids)] if self.festivo_localidad_ids else [('id', '=', 0)],
            'context': {
                'search_default_localidad_id': self.festivo_localidad_ids[:1].id or False,
            },
            'target': 'current',
        }

    def action_open_festivo_localidad_assignment(self):
        self.ensure_one()
        return {
            'name': 'Asignar fiestas AP',
            'type': 'ir.actions.act_window',
            'res_model': 'trabajadores.trabajador',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('trabajadores.trabajadores_trabajador_festivo_localidad_form').id,
            'target': 'new',
        }

    def _ensure_legacy_festive_locality_link(self):
        if self.env.context.get('trabajadores_skip_legacy_festive_locality_sync'):
            return
        for record in self.filtered('festivo_localidad_id'):
            if record.festivo_localidad_id not in record.festivo_localidad_ids:
                record.with_context(trabajadores_skip_legacy_festive_locality_sync=True).write({
                    'festivo_localidad_ids': [(4, record.festivo_localidad_id.id)],
                })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_legacy_festive_locality_link()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'festivo_localidad_id' in vals:
            self._ensure_legacy_festive_locality_link()
        return result

    def init(self):
        super().init()
        self.env.cr.execute(
            """
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_name = 'trabajadores_trabajador_festivo_localidad_rel'
            """
        )
        if not self.env.cr.fetchone():
            return

        self.env.cr.execute(
            """
                INSERT INTO trabajadores_trabajador_festivo_localidad_rel (trabajador_id, localidad_id)
                SELECT trabajador.id, trabajador.festivo_localidad_id
                  FROM trabajadores_trabajador trabajador
                 WHERE trabajador.festivo_localidad_id IS NOT NULL
                   AND NOT EXISTS (
                        SELECT 1
                          FROM trabajadores_trabajador_festivo_localidad_rel rel
                         WHERE rel.trabajador_id = trabajador.id
                           AND rel.localidad_id = trabajador.festivo_localidad_id
                   )
            """
        )
        self.env.cr.execute(
            """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_name = 'trabajadores_festivo_local'
                   AND column_name = 'trabajador_id'
            """
        )
        if self.env.cr.fetchone():
            self.env.cr.execute(
                """
                    INSERT INTO trabajadores_trabajador_festivo_localidad_rel (trabajador_id, localidad_id)
                    SELECT DISTINCT festivo.trabajador_id, festivo.localidad_id
                      FROM trabajadores_festivo_local festivo
                     WHERE festivo.trabajador_id IS NOT NULL
                       AND festivo.localidad_id IS NOT NULL
                       AND NOT EXISTS (
                            SELECT 1
                              FROM trabajadores_trabajador_festivo_localidad_rel rel
                             WHERE rel.trabajador_id = festivo.trabajador_id
                               AND rel.localidad_id = festivo.localidad_id
                       )
                """
            )

    def _is_portalgestor_worker_selector_context(self):
        return bool(self.env.context.get('portalgestor_worker_selector'))

    def _sort_for_portalgestor_worker_selector(self, records):
        if not records:
            return records

        target_localidad = self.env.context.get('portalgestor_usuario_localidad')
        ordered_records = records.sorted(
            key=lambda record: (
                0 if target_localidad and record.localidad_id.id == target_localidad else 1,
                (record.nombre_completo or '').casefold(),
                (record.localidad_id.name or '').casefold(),
                record.id,
            )
        )
        return self.browse(ordered_records.ids)

    @api.model
    def _get_portalgestor_target_zone_id(self):
        target_zone = self.env.context.get('portalgestor_usuario_zona')
        if isinstance(target_zone, (list, tuple)):
            target_zone = target_zone[0] if target_zone else False
        try:
            return int(target_zone) if target_zone else False
        except (TypeError, ValueError):
            return False

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
        target_zone_id = self._get_portalgestor_target_zone_id() if self._is_portalgestor_worker_selector_context() else False
        if trabajadores_vacaciones:
            if isinstance(domain, tuple):
                domain = list(domain)
            elif not isinstance(domain, list):
                domain = []
            domain = domain + [('id', 'not in', trabajadores_vacaciones)]
        if target_zone_id:
            if isinstance(domain, tuple):
                domain = list(domain)
            elif not isinstance(domain, list):
                domain = []
            domain = domain + [('zona_trabajo_ids', 'in', [target_zone_id])]

        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not self._is_portalgestor_worker_selector_context():
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        results = super().name_search(name=name, args=args, operator=operator, limit=None)
        if not results:
            return results

        label_by_id = dict(results)
        ordered_records = self._sort_for_portalgestor_worker_selector(
            self.browse([record_id for record_id, __label in results]).exists()
        )
        if limit:
            ordered_records = ordered_records[:limit]
        return [(record.id, label_by_id.get(record.id, record.display_name)) for record in ordered_records]

    @api.model
    @api.readonly
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        if not self._is_portalgestor_worker_selector_context():
            return super().web_search_read(
                domain,
                specification,
                offset=offset,
                limit=limit,
                order=order,
                count_limit=count_limit,
            )

        fields_to_fetch = list(set(specification.keys()) | {'name', 'apellido1', 'apellido2', 'nombre_completo', 'localidad_id'})
        records = self.search_fetch(domain, fields_to_fetch, order=order or self._order)
        records = self._sort_for_portalgestor_worker_selector(records)
        total_length = len(records)
        if offset:
            records = records[offset:]
        if limit is not None:
            records = records[:limit]
        values_records = records.web_read(specification)
        return {
            'length': total_length,
            'records': values_records,
        }
