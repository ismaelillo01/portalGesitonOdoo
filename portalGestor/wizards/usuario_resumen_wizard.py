# -*- coding: utf-8 -*-
import calendar
from collections import defaultdict
from datetime import date

from odoo import api, fields, models


MESES_ES = {
    '1': 'Enero',
    '2': 'Febrero',
    '3': 'Marzo',
    '4': 'Abril',
    '5': 'Mayo',
    '6': 'Junio',
    '7': 'Julio',
    '8': 'Agosto',
    '9': 'Septiembre',
    '10': 'Octubre',
    '11': 'Noviembre',
    '12': 'Diciembre',
}


class UsuarioResumenWizard(models.TransientModel):
    _name = 'portalgestor.usuario.resumen.wizard'
    _description = 'Asistente de resumen mensual de usuarios'

    mes = fields.Selection(
        selection=[
            ('1', 'Enero'),
            ('2', 'Febrero'),
            ('3', 'Marzo'),
            ('4', 'Abril'),
            ('5', 'Mayo'),
            ('6', 'Junio'),
            ('7', 'Julio'),
            ('8', 'Agosto'),
            ('9', 'Septiembre'),
            ('10', 'Octubre'),
            ('11', 'Noviembre'),
            ('12', 'Diciembre'),
        ],
        string='Mes',
        required=True,
        default=lambda self: str(date.today().month),
    )
    anio = fields.Selection(
        selection='_selection_anios',
        string='Anio',
        required=True,
        default=lambda self: str(date.today().year),
    )
    fecha_inicio = fields.Date(string='Fecha inicio', compute='_compute_fechas')
    fecha_fin = fields.Date(string='Fecha fin', compute='_compute_fechas')
    line_ids = fields.One2many(
        'portalgestor.usuario.resumen.line',
        'wizard_id',
        string='Lineas',
    )

    @api.model
    def _selection_anios(self):
        current_year = date.today().year
        return [(str(year), str(year)) for year in range(current_year - 2, current_year + 3)]

    @api.depends('mes', 'anio')
    def _compute_fechas(self):
        for record in self:
            if record.mes and record.anio:
                month = int(record.mes)
                year = int(record.anio)
                last_day = calendar.monthrange(year, month)[1]
                record.fecha_inicio = date(year, month, 1)
                record.fecha_fin = date(year, month, last_day)
            else:
                record.fecha_inicio = False
                record.fecha_fin = False

    def _is_current_user_portalgestor_summary_admin(self):
        self.ensure_one()
        return self.env.user._get_gestor_management_scope() == 'admin'

    def _get_nombre_mes_anio(self):
        self.ensure_one()
        return f"{MESES_ES.get(self.mes, '')} {self.anio}"

    @staticmethod
    def _format_summary_duration(total_minutes):
        total_minutes = max(int(total_minutes or 0), 0)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        if not minutes:
            return f'{hours}h'
        return f'{hours}h {minutes:02d}m'

    def _get_summary_users(self):
        self.ensure_one()
        domain = []
        if not self._is_current_user_portalgestor_summary_admin():
            domain.append(('gestor_id.user_id', '=', self.env.user.id))

        usuarios = self.env['usuarios.usuario'].search(
            domain,
            order='name, apellido1, apellido2, id',
        )
        return usuarios.filtered(
            lambda usuario: self.env.user._can_manage_target_group(usuario.grupo)
        )

    def _get_ap_minutes_by_user(self, usuarios):
        self.ensure_one()
        minutes_by_user = defaultdict(int)
        if not usuarios or not self.fecha_inicio or not self.fecha_fin:
            return minutes_by_user

        domain = [
            ('asignacion_id.usuario_id', 'in', usuarios.ids),
            ('asignacion_id.confirmado', '=', True),
            ('trabajador_id', '!=', False),
            ('fecha', '>=', self.fecha_inicio),
            ('fecha', '<=', self.fecha_fin),
        ]
        if not self._is_current_user_portalgestor_summary_admin():
            domain.append(('gestor_owner_id', '=', self.env.user.id))

        assignment_lines = self.env['portalgestor.asignacion.linea'].search(
            domain,
            order='fecha asc, hora_inicio asc, hora_fin asc, id asc',
        )
        assignment_lines._recompute_falta_justificada_metrics()
        for line in assignment_lines:
            breakdown = line._get_report_breakdown()
            minutes_by_user[line.asignacion_id.usuario_id.id] += breakdown['computable_minutes']
        return minutes_by_user

    def _get_user_catering_summary(self, usuario):
        self.ensure_one()
        counts_by_service = {
            'catering_comida': 0,
            'catering_cena': 0,
        }
        providers = []

        for config in usuario._get_active_catering_configs():
            if config.date_start > self.fecha_fin:
                continue
            if config.date_stop and config.date_stop < self.fecha_inicio:
                continue

            provider_name = (config.proveedor_id.name or '').strip()
            if provider_name and provider_name not in providers:
                providers.append(provider_name)
            counts_by_service[config.service_code] = len(
                config._get_occurrence_dates(self.fecha_inicio, self.fecha_fin)
            )

        return {
            'proveedor': ' / '.join(providers) or '-',
            'catering_comida_count': counts_by_service['catering_comida'],
            'catering_cena_count': counts_by_service['catering_cena'],
        }

    def _build_summary_line_values(self):
        self.ensure_one()
        usuarios = self._get_summary_users()
        ap_minutes_by_user = self._get_ap_minutes_by_user(usuarios)
        values_list = []

        for usuario in usuarios:
            total_minutes = ap_minutes_by_user.get(usuario.id, 0)
            catering_summary = self._get_user_catering_summary(usuario)
            values_list.append({
                'wizard_id': self.id,
                'usuario_id': usuario.id,
                'name': usuario._get_full_name(),
                'ap_total_minutes': total_minutes,
                'ap_label': self._format_summary_duration(total_minutes),
                'proveedor': catering_summary['proveedor'],
                'catering_comida_count': catering_summary['catering_comida_count'],
                'catering_cena_count': catering_summary['catering_cena_count'],
            })
        return values_list

    def action_view_summary(self):
        self.ensure_one()
        Line = self.env['portalgestor.usuario.resumen.line']
        self.line_ids.unlink()
        line_values = self._build_summary_line_values()
        if line_values:
            Line.create(line_values)

        return {
            'name': f"Resumen usuarios - {self._get_nombre_mes_anio()}",
            'type': 'ir.actions.act_window',
            'res_model': 'portalgestor.usuario.resumen.line',
            'view_mode': 'list',
            'views': [(self.env.ref('portalGestor.view_portalgestor_usuario_resumen_line_list').id, 'list')],
            'domain': [('wizard_id', '=', self.id)],
            'context': {
                'create': False,
                'edit': False,
                'delete': False,
            },
            'target': 'current',
        }


class UsuarioResumenLine(models.TransientModel):
    _name = 'portalgestor.usuario.resumen.line'
    _description = 'Linea de resumen mensual de usuario'
    _order = 'name, id'

    wizard_id = fields.Many2one(
        'portalgestor.usuario.resumen.wizard',
        string='Resumen',
        required=True,
        ondelete='cascade',
    )
    usuario_id = fields.Many2one(
        'usuarios.usuario',
        string='Usuario',
        readonly=True,
    )
    name = fields.Char(string='Nombre y apellidos', readonly=True)
    ap_total_minutes = fields.Integer(string='Minutos AP', readonly=True)
    ap_label = fields.Char(string='AP', readonly=True)
    proveedor = fields.Char(string='Proveedor', readonly=True)
    catering_comida_count = fields.Integer(string='Catering comida', readonly=True)
    catering_cena_count = fields.Integer(string='Catering cena', readonly=True)
