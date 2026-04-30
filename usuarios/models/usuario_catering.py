# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class UsuarioCatering(models.Model):
    _inherit = 'usuarios.usuario'

    catering_config_ids = fields.One2many(
        'usuarios.catering.config',
        'usuario_id',
        string='Configuraciones de catering',
    )
    has_catering_comida_service = fields.Boolean(
        string='Tiene catering comida',
        compute='_compute_catering_service_flags',
    )
    has_catering_cena_service = fields.Boolean(
        string='Tiene catering cena',
        compute='_compute_catering_service_flags',
    )

    @api.depends('servicio_ids.code')
    def _compute_catering_service_flags(self):
        for record in self:
            service_codes = set(record.servicio_ids.mapped('code'))
            record.has_catering_comida_service = 'catering_comida' in service_codes
            record.has_catering_cena_service = 'catering_cena' in service_codes

    def _get_active_catering_service_codes(self):
        self.ensure_one()
        return {
            service.code
            for service in self.servicio_ids
            if service.code in {'catering_comida', 'catering_cena'}
        }

    def _get_active_catering_configs(self):
        self.ensure_one()
        active_codes = self._get_active_catering_service_codes()
        return self.catering_config_ids.filtered(lambda config: config.service_code in active_codes)

    def _build_catering_config_action(self, service_code):
        self.ensure_one()
        if not self.env.user._can_manage_target_group(self.grupo):
            raise AccessError(_("No puedes configurar servicios de catering para usuarios de otro grupo."))
        if service_code not in self._get_active_catering_service_codes():
            raise ValidationError(_("El usuario no tiene activo ese servicio de catering."))

        existing_config = self.catering_config_ids.filtered(
            lambda config: config.service_code == service_code
        )[:1]
        action = {
            'name': dict(self.env['usuarios.catering.config']._SERVICE_SELECTION).get(service_code, 'Catering'),
            'type': 'ir.actions.act_window',
            'res_model': 'usuarios.catering.config',
            'view_mode': 'form',
            'view_id': self.env.ref('usuarios.usuarios_catering_config_form').id,
            'target': 'new',
            'context': {
                'default_usuario_id': self.id,
                'default_service_code': service_code,
            },
        }
        if existing_config:
            action['res_id'] = existing_config.id
        return action

    def action_open_catering_comida_config(self):
        return self._build_catering_config_action('catering_comida')

    def action_open_catering_cena_config(self):
        return self._build_catering_config_action('catering_cena')

    def _get_catering_report_data(self, date_start, date_stop):
        self.ensure_one()
        grouped_occurrences = defaultdict(list)
        service_counts = defaultdict(int)

        for config in self._get_active_catering_configs():
            service_label = config._get_service_label()
            for occurrence_date in config._get_occurrence_dates(date_start, date_stop):
                grouped_occurrences[occurrence_date].append(service_label)
                service_counts[service_label] += 1

        lines = []
        for occurrence_date in sorted(grouped_occurrences):
            labels = sorted(set(grouped_occurrences[occurrence_date]))
            lines.append({
                'fecha_label': occurrence_date.strftime('%d/%m/%Y'),
                'services_label': ', '.join(labels),
            })

        summary_lines = [
            {
                'service_label': service_label,
                'count': service_counts[service_label],
            }
            for service_label in sorted(service_counts)
        ]
        return {
            'lines': lines,
            'summary_lines': summary_lines,
        }
