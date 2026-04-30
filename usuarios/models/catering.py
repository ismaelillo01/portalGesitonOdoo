# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

    @api.depends('usuario_id', 'service_code')
    def _compute_display_name(self):
        service_labels = dict(self._SERVICE_SELECTION)
        for record in self:
            user_name = record.usuario_id._get_full_name() if record.usuario_id else ''
            service_label = service_labels.get(record.service_code, record.service_code or '')
            record.display_name = f"{service_label} - {user_name}".strip(' -')

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
