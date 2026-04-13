# -*- coding: utf-8 -*-
import calendar
import re
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


class PortalAPService(models.AbstractModel):
    _name = 'portal.ap.service'
    _description = 'Servicio del Portal Movil de AP'

    @api.model
    def _normalize_dni(self, value):
        return re.sub(r'[\s-]+', '', value or '').upper()

    @api.model
    def _format_float_hour(self, hour_float):
        total_minutes = int(round((hour_float or 0.0) * 60))
        hour, minute = divmod(total_minutes, 60)
        return '%02d:%02d' % (hour % 24, minute)

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
    def _find_worker_by_dni(self, dni_nie):
        normalized_dni = self._normalize_dni(dni_nie)
        Worker = self.env['trabajadores.trabajador'].sudo()
        if not normalized_dni:
            return Worker.browse(), 'empty'

        workers_with_dni = Worker.search([('dni_nie', '!=', False)])
        matches = workers_with_dni.filtered(
            lambda worker: self._normalize_dni(worker.dni_nie) == normalized_dni
        )
        if not matches:
            return Worker.browse(), 'not_found'
        if len(matches) > 1:
            return Worker.browse(), 'duplicate'
        if matches.baja:
            return Worker.browse(), 'not_found'
        return matches, False

    @api.model
    def _get_navigation(self, year, month, url_pattern='/ap/horario/{year}/{month}'):
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
        vacation_by_date=None,
        url_pattern='/ap/horario/{year}/{month}',
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
                day_vacations = list((vacation_by_date or {}).get(date_value, [])) if in_month else []
                day_payload = {
                    'date': date_value,
                    'date_string': fields.Date.to_string(date_value),
                    'day': date_value.day,
                    'weekday_label': WEEKDAY_LABELS[date_value.weekday()],
                    'in_month': in_month,
                    'is_today': date_value == today,
                    'work_items': day_work,
                    'vacations': day_vacations,
                    'has_content': bool(day_work or day_vacations),
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
    def _get_worker_month_calendar(self, worker, year, month):
        worker = worker.sudo().exists()
        year = int(year)
        month = int(month)
        month_start, month_end = self._get_month_bounds(year, month)

        lines = self.env['portalgestor.asignacion.linea'].sudo().search([
            ('trabajador_id', '=', worker.id),
            ('fecha', '>=', month_start),
            ('fecha', '<=', month_end),
            ('asignacion_id.confirmado', '=', True),
        ], order='fecha, hora_inicio, hora_fin, id')

        user_view_data = self.env['usuarios.usuario'].sudo().get_portalgestor_user_view_data(
            lines.mapped('asignacion_id.usuario_id').ids
        )
        work_by_date = defaultdict(list)
        for line in lines:
            usuario = line.asignacion_id.usuario_id
            user_label = (
                user_view_data.get(usuario.id, {}).get('display_name')
                or usuario.display_name
                or usuario.name
                or _('Usuario')
            )
            work_by_date[line.fecha].append({
                'time_range': '%s - %s' % (
                    self._format_float_hour(line.hora_inicio),
                    self._format_float_hour(line.hora_fin),
                ),
                'label': user_label,
            })

        vacations = self.env['trabajadores.vacacion'].sudo().search([
            ('trabajador_id', '=', worker.id),
            ('date_start', '<=', month_end),
            ('date_stop', '>=', month_start),
        ], order='date_start, date_stop, id')
        vacation_by_date = defaultdict(list)
        for vacation in vacations:
            date_cursor = max(vacation.date_start, month_start)
            date_stop = min(vacation.date_stop, month_end)
            while date_cursor <= date_stop:
                vacation_by_date[date_cursor].append({
                    'label': vacation.name or _('Vacaciones'),
                })
                date_cursor += timedelta(days=1)

        payload = self._build_month_calendar_payload(
            year,
            month,
            work_by_date,
            vacation_by_date=vacation_by_date,
            url_pattern='/ap/horario/{year}/{month}',
        )
        payload.update({
            'worker': worker,
            'worker_name': worker.display_name or worker.nombre_completo or worker.name,
        })
        return payload

    @api.model
    def _get_user_month_calendar(self, usuario, year, month, viewer=None):
        viewer = viewer or self.env.user
        usuario = usuario.exists()
        year = int(year)
        month = int(month)
        month_start, month_end = self._get_month_bounds(year, month)

        lines = self.env['portalgestor.asignacion.linea'].sudo().search([
            ('asignacion_id.usuario_id', '=', usuario.id),
            ('fecha', '>=', month_start),
            ('fecha', '<=', month_end),
            ('asignacion_id.confirmado', '=', True),
        ], order='fecha, hora_inicio, hora_fin, id')

        work_by_date = defaultdict(list)
        for line in lines:
            worker_label = (
                line.trabajador_id.display_name
                or line.trabajador_id.nombre_completo
                or line.trabajador_id.name
                or _('Sin AP')
            )
            work_by_date[line.fecha].append({
                'time_range': '%s - %s' % (
                    self._format_float_hour(line.hora_inicio),
                    self._format_float_hour(line.hora_fin),
                ),
                'label': worker_label,
            })

        user_view_data = self.env['usuarios.usuario'].sudo().with_context(
            portalgestor_viewer_uid=viewer.id,
        ).get_portalgestor_user_view_data([usuario.id])

        payload = self._build_month_calendar_payload(
            year,
            month,
            work_by_date,
            vacation_by_date={},
            url_pattern=f'/consultar-horario/usuario/{usuario.id}' + '/{year}/{month}',
        )
        payload.update({
            'usuario': usuario,
            'user_name': user_view_data.get(usuario.id, {}).get('display_name')
            or usuario.display_name
            or usuario.name,
        })
        return payload

    @api.model
    def _get_manager_user_cards(self, viewer=None, search=''):
        viewer = viewer or self.env.user
        Usuario = self.env['usuarios.usuario'].sudo().with_context(portalgestor_viewer_uid=viewer.id)
        records = Usuario.search([('has_ap_service', '=', True)])
        records = Usuario._sort_for_portalgestor_user_selector(records, viewer=viewer)

        safe_names = records._get_safe_display_name_map(viewer)
        search_text = (search or '').strip().casefold()
        if search_text:
            records = records.filtered(
                lambda record: search_text in (safe_names.get(record.id, '') or '').casefold()
            )

        group_types = Usuario.get_portalgestor_user_types(records.ids)
        return [
            {
                'id': record.id,
                'display_name': safe_names.get(record.id, record.display_name or record.name),
                'group_badge': group_types.get(record.id, {}).get('badge', ''),
                'group_label': group_types.get(record.id, {}).get('label', ''),
                'zona': record.zona_trabajo_id.display_name or record.zona_trabajo_id.name or '',
                'localidad': record.localidad_id.display_name or record.localidad_id.name or '',
                'url': f'/consultar-horario/usuario/{record.id}',
            }
            for record in records
        ]
