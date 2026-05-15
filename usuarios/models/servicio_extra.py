# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class UsuarioServicioRegistro(models.Model):
    _name = 'usuarios.servicio.registro'
    _description = 'Registro de servicio de usuario'
    _order = 'fecha, id'
    _rec_name = 'display_name'

    _SERVICE_SELECTION = [
        ('taxi', 'Taxi'),
        ('lavanderia', 'Lavanderia'),
    ]

    usuario_id = fields.Many2one(
        'usuarios.usuario',
        string='Usuario',
        required=True,
        ondelete='cascade',
        index=True,
    )
    service_code = fields.Selection(
        selection=_SERVICE_SELECTION,
        string='Servicio',
        required=True,
        index=True,
    )
    display_name = fields.Char(
        string='Registro',
        compute='_compute_display_name',
    )
    fecha = fields.Date(string='Fecha', required=True, index=True)
    cantidad = fields.Integer(string='Cantidad', required=True, default=1)
    coste = fields.Float(string='Coste', digits=(16, 2), default=0.0)

    def init(self):
        super().init()
        self.env.cr.execute("SELECT to_regclass(%s)", [self._table])
        if not self.env.cr.fetchone()[0]:
            return
        self.env.cr.execute(
            f"""
                UPDATE {self._table}
                   SET cantidad = 1
                 WHERE service_code = 'taxi'
                   AND cantidad != 1
            """
        )

    @api.model
    def _normalize_service_vals(self, vals):
        vals = dict(vals)
        if vals.get('service_code') == 'taxi':
            vals['cantidad'] = 1
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([
            self._normalize_service_vals(vals)
            for vals in vals_list
        ])

    def write(self, vals):
        vals = dict(vals)
        if vals.get('service_code') == 'taxi':
            vals['cantidad'] = 1
        elif 'cantidad' in vals:
            taxi_records = self.filtered(lambda record: record.service_code == 'taxi')
            non_taxi_records = self - taxi_records
            if taxi_records:
                taxi_vals = dict(vals, cantidad=1)
                super(UsuarioServicioRegistro, taxi_records).write(taxi_vals)
            if non_taxi_records:
                super(UsuarioServicioRegistro, non_taxi_records).write(vals)
            return True
        return super().write(vals)

    @api.depends('usuario_id', 'service_code', 'fecha')
    def _compute_display_name(self):
        service_labels = dict(self._SERVICE_SELECTION)
        for record in self:
            user_name = record.usuario_id._get_full_name() if record.usuario_id else ''
            service_label = service_labels.get(record.service_code, record.service_code or '')
            date_label = record.fecha.strftime('%d/%m/%Y') if record.fecha else ''
            record.display_name = ' - '.join(
                part for part in [service_label, user_name, date_label] if part
            )

    @api.constrains('cantidad', 'coste')
    def _check_quantity_and_cost(self):
        for record in self:
            if record.cantidad <= 0:
                raise ValidationError(_("La cantidad debe ser mayor que cero."))
            if record.coste < 0:
                raise ValidationError(_("El coste no puede ser negativo."))

    def _get_service_label(self):
        self.ensure_one()
        return dict(self._SERVICE_SELECTION).get(self.service_code, self.service_code or '')


class UsuarioServicioExtra(models.Model):
    _inherit = 'usuarios.usuario'

    servicio_registro_ids = fields.One2many(
        'usuarios.servicio.registro',
        'usuario_id',
        string='Registros de servicios',
    )
    has_taxi_service = fields.Boolean(
        string='Tiene taxi',
        compute='_compute_extra_service_flags',
    )
    has_lavanderia_service = fields.Boolean(
        string='Tiene lavanderia',
        compute='_compute_extra_service_flags',
    )

    @api.depends('servicio_ids.code')
    def _compute_extra_service_flags(self):
        for record in self:
            service_codes = set(record.servicio_ids.mapped('code'))
            record.has_taxi_service = 'taxi' in service_codes
            record.has_lavanderia_service = 'lavanderia' in service_codes

    def _get_active_extra_service_codes(self):
        self.ensure_one()
        return {
            service.code
            for service in self.servicio_ids
            if service.code in {'taxi', 'lavanderia'}
        }

    def _build_extra_service_action(self, service_code):
        self.ensure_one()
        if not self.env.user._can_manage_target_group(self.grupo):
            raise AccessError(_("No puedes configurar servicios para usuarios de otro grupo."))
        if service_code not in self._get_active_extra_service_codes():
            raise ValidationError(_("El usuario no tiene activo ese servicio."))

        service_label = dict(self.env['usuarios.servicio.registro']._SERVICE_SELECTION).get(
            service_code,
            'Servicio',
        )
        view_prefix = 'taxi' if service_code == 'taxi' else 'lavanderia'
        return {
            'name': service_label,
            'type': 'ir.actions.act_window',
            'res_model': 'usuarios.servicio.registro',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref(f'usuarios.usuarios_servicio_registro_{view_prefix}_list').id, 'list'),
                (self.env.ref(f'usuarios.usuarios_servicio_registro_{view_prefix}_form').id, 'form'),
            ],
            'domain': [
                ('usuario_id', '=', self.id),
                ('service_code', '=', service_code),
            ],
            'context': {
                'default_usuario_id': self.id,
                'default_service_code': service_code,
            },
            'target': 'current',
        }

    def action_open_taxi_config(self):
        return self._build_extra_service_action('taxi')

    def action_open_lavanderia_config(self):
        return self._build_extra_service_action('lavanderia')

    def _get_extra_services_report_data(self, date_start, date_stop):
        self.ensure_one()
        active_codes = self._get_active_extra_service_codes()
        date_start = fields.Date.to_date(date_start)
        date_stop = fields.Date.to_date(date_stop)
        if not active_codes or not date_start or not date_stop:
            return {
                'lines': [],
                'summary_lines': [],
            }

        records = self.servicio_registro_ids.filtered(
            lambda record: (
                record.service_code in active_codes
                and record.fecha
                and date_start <= record.fecha <= date_stop
            )
        ).sorted(key=lambda record: (record.fecha, record.service_code, record.id))

        lines = []
        summary_by_service = defaultdict(lambda: {
            'service_label': '',
            'total_quantity': 0,
            'total_cost': 0.0,
        })
        for record in records:
            service_label = record._get_service_label()
            is_taxi = record.service_code == 'taxi'
            quantity = 1 if is_taxi else record.cantidad
            cost_total = record.coste if is_taxi else record.cantidad * record.coste
            quantity_label = _('Viajes') if is_taxi else _('Usos')
            quantity_display = '' if is_taxi else f"{quantity} {quantity_label}"
            lines.append({
                'fecha_label': record.fecha.strftime('%d/%m/%Y'),
                'service_label': service_label,
                'quantity_label': quantity_label,
                'quantity': quantity,
                'quantity_display': quantity_display,
                'cost': cost_total,
            })
            summary = summary_by_service[record.service_code]
            summary['service_label'] = service_label
            summary['quantity_label'] = quantity_label
            summary['total_quantity'] += quantity
            summary['total_cost'] += cost_total

        return {
            'lines': lines,
            'summary_lines': [
                summary_by_service[service_code]
                for service_code in ['taxi', 'lavanderia']
                if service_code in summary_by_service
            ],
        }
