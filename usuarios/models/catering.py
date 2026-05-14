# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class UsuarioCateringProveedor(models.Model):
    _name = 'usuarios.catering.proveedor'
    _description = 'Proveedor de catering'
    _order = 'name, id'

    name = fields.Char(string='Nombre', required=True)

    _sql_constraints = [
        (
            'usuarios_catering_proveedor_name_uniq',
            'unique(name)',
            'Ya existe un proveedor de catering con ese nombre.',
        ),
    ]


class UsuarioCateringConfig(models.Model):
    _name = 'usuarios.catering.config'
    _description = 'Configuracion de Catering de Usuario'
    _order = 'usuario_id, service_code, id'
    _rec_name = 'display_name'

    _SERVICE_SELECTION = [
        ('catering_comida', 'Catering comida'),
        ('catering_cena', 'Catering cena'),
    ]
    _WEEKDAY_FIELD_MAP = {
        0: 'lunes',
        1: 'martes',
        2: 'miercoles',
        3: 'jueves',
        4: 'viernes',
        5: 'sabado',
        6: 'domingo',
    }

    usuario_id = fields.Many2one(
        'usuarios.usuario',
        string='Usuario',
        required=True,
        ondelete='cascade',
        index=True,
    )
    service_code = fields.Selection(
        selection=_SERVICE_SELECTION,
        string='Servicio catering',
        required=True,
        index=True,
    )
    display_name = fields.Char(
        string='Configuracion',
        compute='_compute_display_name',
    )
    proveedor_id = fields.Many2one(
        'usuarios.catering.proveedor',
        string='Proveedor',
        ondelete='restrict',
        index=True,
    )
    proovedor = fields.Char(
        string='Proveedor legado',
        compute='_compute_proovedor',
        search='_search_proovedor',
    )
    date_start = fields.Date(string='Inicio alta', required=True)
    date_stop = fields.Date(string='Inicio baja')
    lunes = fields.Boolean(string='Lunes')
    martes = fields.Boolean(string='Martes')
    miercoles = fields.Boolean(string='Miercoles')
    jueves = fields.Boolean(string='Jueves')
    viernes = fields.Boolean(string='Viernes')
    sabado = fields.Boolean(string='Sabado')
    domingo = fields.Boolean(string='Domingo')
    suspension_ids = fields.One2many(
        'usuarios.catering.suspension',
        'config_id',
        string='Dias suspendidos',
    )

    _sql_constraints = [
        (
            'usuarios_catering_config_unique_service_per_user',
            'unique(usuario_id, service_code)',
            'Solo puede existir una configuracion por usuario y servicio de catering.',
        ),
    ]

    def init(self):
        super().init()
        self._migrate_legacy_provider_names()

    @api.model
    def _get_or_create_provider(self, provider_name):
        provider_name = (provider_name or '').strip()
        if not provider_name:
            return self.env['usuarios.catering.proveedor']
        Provider = self.env['usuarios.catering.proveedor'].sudo()
        provider = Provider.search([('name', '=', provider_name)], limit=1)
        return provider or Provider.create({'name': provider_name})

    @api.model
    def _normalize_provider_vals(self, vals):
        if 'proovedor' not in vals:
            return vals

        vals = dict(vals)
        if 'proveedor_id' in vals:
            vals.pop('proovedor', None)
            return vals

        provider_name = vals.pop('proovedor') or ''
        provider = self._get_or_create_provider(provider_name)
        vals['proveedor_id'] = provider.id if provider else False
        return vals

    @api.model
    def _migrate_legacy_provider_names(self):
        config_table = self._table
        provider_table = self.env['usuarios.catering.proveedor']._table
        self.env.cr.execute(
            """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_name = %s
                   AND column_name IN ('proovedor', 'proveedor_id')
            """,
            [config_table],
        )
        config_columns = {row[0] for row in self.env.cr.fetchall()}
        self.env.cr.execute("SELECT to_regclass(%s)", [provider_table])
        provider_table_exists = bool(self.env.cr.fetchone()[0])
        if not provider_table_exists or not {'proovedor', 'proveedor_id'} <= config_columns:
            return

        self.env.cr.execute(
            f"""
                SELECT DISTINCT btrim(proovedor)
                  FROM {config_table}
                 WHERE proveedor_id IS NULL
                   AND proovedor IS NOT NULL
                   AND btrim(proovedor) != ''
                 ORDER BY btrim(proovedor)
            """
        )
        for provider_name, in self.env.cr.fetchall():
            provider = self._get_or_create_provider(provider_name)
            if provider:
                self.env.cr.execute(
                    f"""
                        UPDATE {config_table}
                           SET proveedor_id = %s
                         WHERE proveedor_id IS NULL
                           AND btrim(proovedor) = %s
                    """,
                    [provider.id, provider_name],
                )

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([
            self._normalize_provider_vals(vals)
            for vals in vals_list
        ])

    def write(self, vals):
        return super().write(self._normalize_provider_vals(vals))

    @api.depends('usuario_id', 'service_code')
    def _compute_display_name(self):
        service_labels = dict(self._SERVICE_SELECTION)
        for record in self:
            user_name = record.usuario_id._get_full_name() if record.usuario_id else ''
            service_label = service_labels.get(record.service_code, record.service_code or '')
            record.display_name = f"{service_label} - {user_name}".strip(' -')

    @api.depends('proveedor_id.name')
    def _compute_proovedor(self):
        for record in self:
            record.proovedor = record.proveedor_id.name or ''

    @api.model
    def _search_proovedor(self, operator, value):
        return [('proveedor_id.name', operator, value)]

    @api.constrains('date_start', 'date_stop')
    def _check_date_range(self):
        for record in self:
            if record.date_start and record.date_stop and record.date_stop < record.date_start:
                raise ValidationError(_("La fecha de Inicio baja no puede ser anterior a Inicio alta."))

    @api.constrains(
        'lunes',
        'martes',
        'miercoles',
        'jueves',
        'viernes',
        'sabado',
        'domingo',
    )
    def _check_weekdays_selected(self):
        weekday_fields = self._WEEKDAY_FIELD_MAP.values()
        for record in self:
            if not any(record[field_name] for field_name in weekday_fields):
                raise ValidationError(_("Debes seleccionar al menos un dia de la semana para el catering."))

    def _get_service_label(self):
        self.ensure_one()
        return dict(self._SERVICE_SELECTION).get(self.service_code, self.service_code or '')

    def _matches_weekday(self, target_date):
        self.ensure_one()
        weekday_field = self._WEEKDAY_FIELD_MAP[target_date.weekday()]
        return bool(self[weekday_field])

    def _is_suspended_on(self, target_date):
        self.ensure_one()
        return any(
            suspension.date_start <= target_date <= suspension.date_stop
            for suspension in self.suspension_ids
        )

    def _get_occurrence_dates(self, date_start, date_stop):
        self.ensure_one()
        if not date_start or not date_stop:
            return []

        target_start = fields.Date.to_date(date_start)
        target_stop = fields.Date.to_date(date_stop)
        config_start = fields.Date.to_date(self.date_start)
        config_stop = fields.Date.to_date(self.date_stop) if self.date_stop else target_stop
        effective_start = max(target_start, config_start)
        effective_stop = min(target_stop, config_stop)
        if effective_start > effective_stop:
            return []

        current_date = effective_start
        occurrences = []
        while current_date <= effective_stop:
            if self._matches_weekday(current_date) and not self._is_suspended_on(current_date):
                occurrences.append(current_date)
            current_date += timedelta(days=1)
        return occurrences


class UsuarioCateringSuspension(models.Model):
    _name = 'usuarios.catering.suspension'
    _description = 'Suspension de Catering de Usuario'
    _order = 'date_start, date_stop, id'

    config_id = fields.Many2one(
        'usuarios.catering.config',
        string='Configuracion catering',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date_start = fields.Date(string='Desde', required=True)
    date_stop = fields.Date(string='Hasta', required=True)
    name = fields.Char(string='Motivo')

    @api.constrains('date_start', 'date_stop')
    def _check_date_range(self):
        for record in self:
            if record.date_stop < record.date_start:
                raise ValidationError(_("La fecha final de la suspension no puede ser anterior a la inicial."))
