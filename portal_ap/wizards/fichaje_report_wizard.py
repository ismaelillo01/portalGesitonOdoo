# -*- coding: utf-8 -*-
import calendar
import io
import re
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import xlsxwriter


class PortalAPFichajeReportWizard(models.TransientModel):
    _name = 'portal.ap.fichaje.report.wizard'
    _description = 'Asistente de reporte Excel de fichajes AP'

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
    trabajador_id = fields.Many2one(
        'trabajadores.trabajador',
        string='AP',
        required=True,
        default=lambda self: self._default_trabajador_id(),
    )

    @api.model
    def _selection_anios(self):
        current_year = date.today().year
        return [(str(year), str(year)) for year in range(current_year - 2, current_year + 3)]

    @api.model
    def _default_trabajador_id(self):
        if self.env.context.get('active_model') != 'portal.ap.fichaje':
            return False
        active_ids = self.env.context.get('active_ids') or []
        checks = self.env['portal.ap.fichaje'].browse(active_ids).exists()
        workers = checks.mapped('trabajador_id')
        return workers[:1].id if len(workers) == 1 else False

    @api.depends('mes', 'anio')
    def _compute_fechas(self):
        for record in self:
            if record.mes and record.anio:
                month = int(record.mes)
                year = int(record.anio)
                record.fecha_inicio = date(year, month, 1)
                record.fecha_fin = date(year, month, calendar.monthrange(year, month)[1])
            else:
                record.fecha_inicio = False
                record.fecha_fin = False

    def _check_report_access(self):
        self.ensure_one()
        scope = self.env.user._get_gestor_management_scope()
        if not scope:
            raise AccessError(_('No tienes permisos para generar reportes de Fichajes AP.'))
        if not self.trabajador_id:
            raise UserError(_('Selecciona un AP para generar el reporte.'))
        if not self.env.user._can_manage_target_group(self.trabajador_id.grupo):
            raise AccessError(_('No tienes permisos para generar reportes de este AP.'))
        return True

    def action_download_excel(self):
        self.ensure_one()
        self._check_report_access()
        return {
            'type': 'ir.actions.act_url',
            'url': '/portal_ap/fichajes/reporte_xlsx/%s' % self.id,
            'target': 'self',
        }

    def _get_fichajes_for_report(self):
        self.ensure_one()
        self._check_report_access()
        return self.env['portal.ap.fichaje'].sudo().search([
            ('trabajador_id', '=', self.trabajador_id.id),
            ('assignment_date', '>=', self.fecha_inicio),
            ('assignment_date', '<=', self.fecha_fin),
            ('state', 'in', ['valid', 'warning', 'pending']),
            ('assignment_line_id', '!=', False),
        ], order='assignment_date asc, planned_start asc, server_datetime asc, id asc')

    @staticmethod
    def _duration_label(minutes):
        minutes = max(int(minutes or 0), 0)
        hours = minutes // 60
        remaining = minutes % 60
        if remaining:
            return '%sh %02dm' % (hours, remaining)
        return '%sh' % hours

    def _report_timezone(self):
        return self.env.context.get('tz') or self.env.user.tz or 'Europe/Madrid'

    def _to_report_local_datetime(self, value):
        if not value:
            return False
        local_value = fields.Datetime.context_timestamp(
            self.with_context(tz=self._report_timezone()),
            value,
        )
        if getattr(local_value, 'tzinfo', None):
            local_value = local_value.replace(tzinfo=None)
        return local_value

    def _parse_client_datetime_for_report(self, value):
        raw_value = (value or '').strip()
        if not raw_value:
            return False
        try:
            parsed = datetime.fromisoformat(raw_value.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return False
        if not parsed.tzinfo:
            return parsed
        parsed_utc = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return self._to_report_local_datetime(parsed_utc)

    def _get_effective_check_datetime(self, check):
        self.ensure_one()
        if check.origin == 'offline':
            client_datetime = self._parse_client_datetime_for_report(check.client_datetime)
            if client_datetime:
                return client_datetime
        return self._to_report_local_datetime(check.server_datetime)

    def _format_datetime_for_report(self, value):
        if not value:
            return ''
        return value.strftime('%H:%M:%S')

    def _get_report_data(self):
        self.ensure_one()
        grouped = OrderedDict()
        for check in self._get_fichajes_for_report():
            line = check.assignment_line_id
            if line.id not in grouped:
                grouped[line.id] = {
                    'line': line,
                    'checks': self.env['portal.ap.fichaje'],
                }
            grouped[line.id]['checks'] |= check

        rows = []
        daily_totals = defaultdict(int)
        total_minutes = 0
        for data in grouped.values():
            line = data['line']
            checks = data['checks'].sorted(
                key=lambda item: (self._get_effective_check_datetime(item) or datetime.min, item.id)
            )
            check_ins = checks.filtered(lambda item: item.event_type == 'in')
            check_outs = checks.filtered(lambda item: item.event_type == 'out')
            check_in = check_ins[:1]
            check_out = check_outs[-1:] if check_outs else self.env['portal.ap.fichaje']

            incidences = []
            if not check_in:
                incidences.append(_('Sin entrada fichada'))
            if not check_out:
                incidences.append(_('Sin salida fichada'))
            if len(check_ins) > 1:
                incidences.append(_('Varias entradas; se usa la primera'))
            if len(check_outs) > 1:
                incidences.append(_('Varias salidas; se usa la ultima'))
            incidences.extend(checks.filtered('incidence').mapped('incidence'))

            minutes = 0
            check_in_datetime = self._get_effective_check_datetime(check_in) if check_in else False
            check_out_datetime = self._get_effective_check_datetime(check_out) if check_out else False
            if check_in and check_out:
                delta = check_out_datetime - check_in_datetime
                if delta.total_seconds() >= 0:
                    minutes = int(round(delta.total_seconds() / 60))
                else:
                    incidences.append(_('Salida anterior a entrada'))

            report_date = line.fecha or checks[:1].assignment_date
            daily_totals[report_date] += minutes
            total_minutes += minutes
            usuario = line.asignacion_id.usuario_id or checks[:1].usuario_id
            rows.append({
                'date': report_date,
                'ap': self.trabajador_id.display_name or self.trabajador_id.nombre_completo or self.trabajador_id.name,
                'usuario': usuario.display_name or usuario.name or '',
                'check_in': check_in_datetime,
                'check_out': check_out_datetime,
                'minutes': minutes,
                'incidence': ' | '.join(dict.fromkeys(item for item in incidences if item)),
            })

        return {
            'rows': rows,
            'daily_totals': daily_totals,
            'total_minutes': total_minutes,
        }

    def _get_report_filename(self):
        self.ensure_one()
        worker_name = self.trabajador_id.display_name or self.trabajador_id.name or 'AP'
        safe_worker_name = re.sub(r'[^A-Za-z0-9_-]+', '_', worker_name).strip('_') or 'AP'
        return 'fichajes_ap_%s_%s_%02d.xlsx' % (safe_worker_name, self.anio, int(self.mes))

    def _generate_xlsx_content(self):
        self.ensure_one()
        report_data = self._get_report_data()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Fichajes AP')

        title_format = workbook.add_format({'bold': True, 'font_size': 14})
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#20173f',
            'font_color': '#FFFFFF',
            'border': 1,
        })
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy', 'border': 1})
        text_format = workbook.add_format({'border': 1})
        duration_format = workbook.add_format({'num_format': '[h]:mm', 'border': 1})
        total_format = workbook.add_format({
            'bold': True,
            'bg_color': '#F4EAF1',
            'border': 1,
        })
        total_duration_format = workbook.add_format({
            'bold': True,
            'bg_color': '#F4EAF1',
            'border': 1,
            'num_format': '[h]:mm',
        })

        worksheet.write(0, 0, 'Reporte Fichajes AP', title_format)
        worksheet.write(1, 0, 'AP', header_format)
        worksheet.write(1, 1, self.trabajador_id.display_name or self.trabajador_id.name or '', text_format)
        worksheet.write(2, 0, 'Periodo', header_format)
        worksheet.write(2, 1, '%02d/%s' % (int(self.mes), self.anio), text_format)

        headers = [
            'Fecha',
            'AP',
            'Usuario',
            'Hora de entrada fichada',
            'Hora de salida fichada',
            'Horas total tramo',
            'Incidencia',
        ]
        header_row = 4
        for col, header in enumerate(headers):
            worksheet.write(header_row, col, header, header_format)

        row_index = header_row + 1
        current_date = None
        for row in report_data['rows']:
            if current_date and current_date != row['date']:
                row_index = self._write_day_total_row(
                    worksheet,
                    row_index,
                    current_date,
                    report_data['daily_totals'][current_date],
                    total_format,
                    total_duration_format,
                )
            current_date = row['date']
            worksheet.write(row_index, 0, fields.Date.to_string(row['date']), date_format)
            worksheet.write(row_index, 1, row['ap'], text_format)
            worksheet.write(row_index, 2, row['usuario'], text_format)
            worksheet.write(row_index, 3, self._format_datetime_for_report(row['check_in']), text_format)
            worksheet.write(row_index, 4, self._format_datetime_for_report(row['check_out']), text_format)
            worksheet.write_number(row_index, 5, row['minutes'] / 1440.0, duration_format)
            worksheet.write(row_index, 6, row['incidence'], text_format)
            row_index += 1

        if current_date:
            row_index = self._write_day_total_row(
                worksheet,
                row_index,
                current_date,
                report_data['daily_totals'][current_date],
                total_format,
                total_duration_format,
            )

        worksheet.write(row_index, 0, 'Total mes', total_format)
        worksheet.write(row_index, 5, report_data['total_minutes'] / 1440.0, total_duration_format)
        worksheet.write(row_index, 6, self._duration_label(report_data['total_minutes']), total_format)

        worksheet.set_column(0, 0, 12)
        worksheet.set_column(1, 2, 28)
        worksheet.set_column(3, 4, 22)
        worksheet.set_column(5, 5, 18)
        worksheet.set_column(6, 6, 48)
        worksheet.freeze_panes(header_row + 1, 0)
        workbook.close()
        return output.getvalue()

    def _write_day_total_row(self, worksheet, row_index, day, minutes, total_format, total_duration_format):
        worksheet.write(row_index, 0, 'Total dia', total_format)
        worksheet.write(row_index, 1, fields.Date.to_string(day), total_format)
        worksheet.write(row_index, 5, minutes / 1440.0, total_duration_format)
        worksheet.write(row_index, 6, self._duration_label(minutes), total_format)
        return row_index + 1
