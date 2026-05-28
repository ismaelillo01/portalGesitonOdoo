# -*- coding: utf-8 -*-
import calendar
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models


MONTH_LABELS = {
    1: 'Enero',
    2: 'Febrero',
    3: 'Marzo',
    4: 'Abril',
    5: 'Mayo',
    6: 'Junio',
    7: 'Julio',
    8: 'Agosto',
    9: 'Septiembre',
    10: 'Octubre',
    11: 'Noviembre',
    12: 'Diciembre',
}

WEEKDAY_LABELS = ['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab', 'Dom']


class PortalUsuarioService(models.AbstractModel):
    _name = 'portal.usuario.service'
    _description = 'Servicio del Portal Movil de Usuario'

    @api.model
    def _format_float_hour(self, hour_float):
        from odoo.addons.portalGestor.models.utils import format_float_hour
        return format_float_hour(hour_float)

    @api.model
    def _get_month_bounds(self, year, month):
        year = int(year)
        month = int(month)
        month_start = fields.Date.to_date(f'{year:04d}-{month:02d}-01')
        month_end = month_start + timedelta(days=calendar.monthrange(year, month)[1] - 1)
        return month_start, month_end

    @api.model
    def _get_month_label(self, month):
        return MONTH_LABELS.get(int(month), '')

    @api.model
    def _find_usuario_by_codigo(self, codigo):
        """Find a usuario by their 4-digit authentication code."""
        codigo = (codigo or '').strip()
        Usuario = self.env['usuarios.usuario'].sudo()
        if not codigo:
            return Usuario.browse(), 'empty'

        matches = Usuario.search([
            ('codigo_autenticacion', '=', codigo),
            ('baja', '=', False),
        ])
        if not matches:
            return Usuario.browse(), 'not_found'
        if len(matches) > 1:
            return Usuario.browse(), 'duplicate'
        if not matches.has_ap_service:
            return Usuario.browse(), 'no_ap_service'
        return matches, False

    @api.model
    def _get_navigation(self, year, month, url_pattern='/usuario/horario/{year}/{month}'):
        previous_month = month - 1
        previous_year = year
        if previous_month < 1:
            previous_month = 12
            previous_year -= 1

        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year += 1

        return {
            'previous': {
                'year': previous_year,
                'month': previous_month,
                'url': url_pattern.format(year=previous_year, month=previous_month),
            },
            'next': {
                'year': next_year,
                'month': next_month,
                'url': url_pattern.format(year=next_year, month=next_month),
            },
        }

    @api.model
    def _build_month_calendar_payload(
        self,
        year,
        month,
        work_by_date,
        url_pattern='/usuario/horario/{year}/{month}',
    ):
        year = int(year)
        month = int(month)
        month_start, month_end = self._get_month_bounds(year, month)
        today = fields.Date.context_today(self)
        weeks = []
        month_days = []

        for week_dates in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
            week = []
            for date_value in week_dates:
                in_month = date_value.month == month
                day_work = list(work_by_date.get(date_value, [])) if in_month else []
                day_payload = {
                    'date': date_value,
                    'date_string': fields.Date.to_string(date_value),
                    'day': date_value.day,
                    'weekday_label': WEEKDAY_LABELS[date_value.weekday()],
                    'in_month': in_month,
                    'is_today': date_value == today,
                    'work_items': day_work,
                    'has_content': bool(day_work),
                }
                week.append(day_payload)
                if in_month:
                    month_days.append(day_payload)
            weeks.append(week)

        navigation = self._get_navigation(year, month, url_pattern=url_pattern)
        return {
            'year': year,
            'month': month,
            'month_label': self._get_month_label(month),
            'month_start': fields.Date.to_string(month_start),
            'month_end': fields.Date.to_string(month_end),
            'weekday_labels': WEEKDAY_LABELS,
            'weeks': weeks,
            'month_days': month_days,
            'previous': navigation['previous'],
            'next': navigation['next'],
        }

    @api.model
    def _get_usuario_month_calendar(
        self,
        usuario,
        year,
        month,
        url_pattern='/usuario/horario/{year}/{month}',
    ):
        """Build the month calendar for a usuario showing their scheduled services."""
        usuario = usuario.sudo().exists()
        year = int(year)
        month = int(month)
        month_start, month_end = self._get_month_bounds(year, month)

        # Find all confirmed assignment lines for this usuario
        lines = self.env['portalgestor.asignacion.linea'].sudo().search([
            ('asignacion_id.usuario_id', '=', usuario.id),
            ('fecha', '>=', month_start),
            ('fecha', '<=', month_end),
            ('asignacion_id.confirmado', '=', True),
        ], order='fecha, hora_inicio, hora_fin, id')

        work_by_date = defaultdict(list)
        for line in lines:
            worker = line.trabajador_id
            worker_label = (
                worker.display_name
                or worker.nombre_completo
                or worker.name
                or _('Sin AP asignado')
            )
            work_by_date[line.fecha].append({
                'time_range': '%s - %s' % (
                    self._format_float_hour(line.hora_inicio),
                    self._format_float_hour(line.hora_fin),
                ),
                'label': worker_label,
            })

        payload = self._build_month_calendar_payload(
            year,
            month,
            work_by_date,
            url_pattern=url_pattern,
        )

        usuario_name = usuario._get_full_name() or usuario.display_name or usuario.name
        payload.update({
            'usuario': usuario,
            'usuario_name': usuario_name,
        })
        return payload
