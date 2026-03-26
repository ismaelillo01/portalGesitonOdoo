# -*- coding: utf-8 -*-
import base64
import calendar
import csv
import io
import zipfile
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

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


class UsuarioReportWizard(models.TransientModel):
    _name = 'portalgestor.usuario.report.wizard'
    _description = 'Asistente de Reporte de Horario de Usuario'

    exportar_todos_activos = fields.Boolean(
        string='Sacar horario de todos los usuarios activos',
        default=False,
    )
    usuario_ids = fields.Many2many(
        'usuarios.usuario',
        string='Usuarios',
        domain=[('baja', '=', False)],
    )
    formato_salida = fields.Selection(
        selection=[
            ('pdf', 'PDF'),
            ('csv', 'CSV'),
        ],
        string='Formato de reporte',
        required=True,
        default='pdf',
    )
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
    download_file = fields.Binary(string='Archivo generado', attachment=False)
    download_filename = fields.Char(string='Nombre del archivo')

    @api.model
    def default_get(self, field_names):
        defaults = super().default_get(field_names)
        if 'usuario_ids' in field_names and not defaults.get('usuario_ids'):
            active_model = self.env.context.get('active_model')
            active_ids = self.env.context.get('active_ids') or []
            if active_model == 'usuarios.usuario' and active_ids:
                defaults['usuario_ids'] = [(6, 0, active_ids)]
        return defaults

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

    def _get_nombre_mes_anio(self):
        self.ensure_one()
        return f"{MESES_ES.get(self.mes, '')} {self.anio}"

    def _get_selected_users(self):
        self.ensure_one()
        if self.exportar_todos_activos:
            usuarios = self.env['usuarios.usuario'].search(
                [('baja', '=', False)],
                order='name, apellido1, apellido2, id',
            )
            if not usuarios:
                raise ValidationError(_("No hay usuarios activos para exportar."))
            return usuarios
        usuarios = self.usuario_ids.sorted(key=lambda usuario: (usuario.name, usuario.apellido1, usuario.apellido2, usuario.id))
        if not usuarios:
            raise ValidationError(_("Debes seleccionar al menos un usuario."))
        return usuarios

    def _ensure_current_user_can_export_users(self, usuarios):
        forbidden_users = usuarios.filtered(
            lambda usuario: not self.env.user._can_manage_target_group(usuario.grupo)
        )
        if forbidden_users:
            raise AccessError(
                _("Los gestores Agusto no pueden generar reportes ni exportaciones de usuarios de Intecum.")
            )

    def _get_report_users(self):
        self.ensure_one()
        single_usuario_id = self.env.context.get('single_usuario_id')
        if single_usuario_id:
            usuarios = self.env['usuarios.usuario'].browse(single_usuario_id).exists()
        else:
            usuarios = self._get_selected_users()
        self._ensure_current_user_can_export_users(usuarios)
        return usuarios

    @staticmethod
    def _format_hour(hour_float):
        total_minutes = int(round((hour_float or 0.0) * 60))
        return '%02d:%02d' % (total_minutes // 60, total_minutes % 60)

    @staticmethod
    def _format_duration(total_minutes):
        return '%d Horas y %02d minutos' % (total_minutes // 60, total_minutes % 60)

    def _get_report_lines_for_user(self, usuario):
        self.ensure_one()
        if not usuario or not self.fecha_inicio or not self.fecha_fin:
            return []

        assignment_lines = self.env['portalgestor.asignacion.linea'].search(
            [
                ('asignacion_id.usuario_id', '=', usuario.id),
                ('fecha', '>=', self.fecha_inicio),
                ('fecha', '<=', self.fecha_fin),
            ],
            order='fecha asc, hora_inicio asc, hora_fin asc, id asc',
        )

        lines = []
        for line in assignment_lines:
            duration_minutes = int(round((line.hora_fin - line.hora_inicio) * 60))
            lines.append({
                'fecha_label': line.fecha.strftime('%d/%m/%Y') if line.fecha else '',
                'ap_name': line.trabajador_id.display_name or 'Sin AP asignado',
                'hora_inicio': self._format_hour(line.hora_inicio),
                'hora_fin': self._format_hour(line.hora_fin),
                'duration_label': self._format_duration(duration_minutes),
                'duration_minutes': duration_minutes,
            })
        return lines

    def _get_report_payload_for_user(self, usuario):
        self.ensure_one()
        if not usuario:
            raise ValidationError(_("Debes seleccionar un usuario."))

        lines = self._get_report_lines_for_user(usuario)
        total_minutes = sum(line['duration_minutes'] for line in lines)
        return {
            'usuario_full_name': usuario._get_full_name(),
            'services_label': usuario._get_service_names() or 'Sin servicios',
            'period_label': self._get_nombre_mes_anio(),
            'has_ap_service': usuario.has_ap_service,
            'lines': lines,
            'total_duration_label': self._format_duration(total_minutes),
        }

    def _get_single_report_filename(self):
        self.ensure_one()
        usuario = self._get_report_users()[:1]
        if not usuario:
            return _('Horarios de usuarios')
        return f"{usuario._get_full_name()} ({self._get_nombre_mes_anio()})"

    def _build_csv_bytes_for_user(self, usuario):
        self.ensure_one()
        payload = self._get_report_payload_for_user(usuario)

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', lineterminator='\n')
        writer.writerow(['Usuario', payload['usuario_full_name']])
        writer.writerow(['Servicios', payload['services_label']])
        writer.writerow(['Periodo', payload['period_label']])
        if not payload['has_ap_service']:
            writer.writerow(['Aviso', 'El usuario no tiene activo el servicio AP.'])
        elif not payload['lines']:
            writer.writerow(['Aviso', 'Sin registros en este periodo.'])

        writer.writerow([])
        writer.writerow(['Fecha', 'AP', 'Hora inicio', 'Hora fin', 'Horas totales'])
        for line in payload['lines']:
            writer.writerow([
                line['fecha_label'],
                line['ap_name'],
                line['hora_inicio'],
                line['hora_fin'],
                line['duration_label'],
            ])
        writer.writerow([])
        writer.writerow(['Total periodo', '', '', '', payload['total_duration_label']])
        return ('\ufeff' + output.getvalue()).encode('utf-8')

    def _build_download_action(self, filename, file_bytes):
        self.ensure_one()
        self.write({
            'download_file': base64.b64encode(file_bytes),
            'download_filename': filename,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=download_file&filename_field=download_filename&download=true',
            'target': 'self',
        }

    def _build_zip_download_action(self, filename, file_entries):
        self.ensure_one()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for entry_name, entry_bytes in file_entries:
                zip_file.writestr(entry_name, entry_bytes)
        return self._build_download_action(filename, zip_buffer.getvalue())

    def action_generate_report(self):
        self.ensure_one()
        if self.formato_salida == 'csv':
            return self.action_export_csv()
        return self.action_print_report()

    def action_print_report(self):
        self.ensure_one()
        usuarios = self._get_report_users()
        report_action = self.env.ref('portalGestor.action_report_horario_usuario')
        if len(usuarios) == 1:
            return report_action.report_action(self)

        file_entries = []
        for usuario in usuarios:
            pdf_content, _content_type = report_action.with_context(
                single_usuario_id=usuario.id
            )._render_qweb_pdf(report_action.id, self.ids)
            file_entries.append((
                f"{usuario._get_full_name()} ({self._get_nombre_mes_anio()}).pdf",
                pdf_content,
            ))
        return self._build_zip_download_action(
            f"Horarios usuarios ({self._get_nombre_mes_anio()}).zip",
            file_entries,
        )

    def action_export_csv(self):
        self.ensure_one()
        usuarios = self._get_report_users()
        if len(usuarios) == 1:
            usuario = usuarios[0]
            csv_bytes = self._build_csv_bytes_for_user(usuario)
            return self._build_download_action(
                f"{usuario._get_full_name()} ({self._get_nombre_mes_anio()}).csv",
                csv_bytes,
            )

        file_entries = [
            (
                f"{usuario._get_full_name()} ({self._get_nombre_mes_anio()}).csv",
                self._build_csv_bytes_for_user(usuario),
            )
            for usuario in usuarios
        ]
        return self._build_zip_download_action(
            f"Horarios usuarios ({self._get_nombre_mes_anio()}).zip",
            file_entries,
        )
