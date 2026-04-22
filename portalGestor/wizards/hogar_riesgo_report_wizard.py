# -*- coding: utf-8 -*-
import base64
import calendar
import io
import zipfile
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


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


class HogarRiesgoReportWizard(models.TransientModel):
    _name = 'portalgestor.hogar.riesgo.report.wizard'
    _description = 'Asistente de Reporte de Hogares de Riesgo'

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

    @staticmethod
    def _format_duration(total_minutes):
        return '%d Horas y %02d minutos' % (total_minutes // 60, total_minutes % 60)

    def _get_nombre_mes_anio(self):
        self.ensure_one()
        return f"{MESES_ES.get(self.mes, '')} {self.anio}"

    def _get_allowed_hogar_riesgo_options(self):
        Usuario = self.env['usuarios.usuario']
        return [
            (value, label)
            for value, label in Usuario._get_hogar_riesgo_options()
            if self.env.user._can_manage_target_group(Usuario._get_hogar_riesgo_group(value))
        ]

    def _get_report_hogar_riesgo_options(self):
        self.ensure_one()
        allowed_options = self._get_allowed_hogar_riesgo_options()
        allowed_map = dict(allowed_options)
        single_hogar_riesgo = self.env.context.get('single_hogar_riesgo')
        if single_hogar_riesgo:
            if single_hogar_riesgo not in allowed_map:
                raise AccessError(_("No puedes generar el reporte de este hogar de riesgo."))
            return [(single_hogar_riesgo, allowed_map[single_hogar_riesgo])]
        if not allowed_options:
            raise AccessError(_("No tienes permisos para generar este reporte."))
        return allowed_options

    def _get_users_for_hogar_riesgo(self, hogar_riesgo):
        self.ensure_one()
        return self.env['usuarios.usuario'].search(
            [
                ('baja', '=', False),
                ('has_ap_service', '=', True),
                ('hogar_riesgo', '=', hogar_riesgo),
            ],
            order='name, apellido1, apellido2, id',
        )

    def _get_assignment_lines_for_users(self, usuarios):
        self.ensure_one()
        if not usuarios or not self.fecha_inicio or not self.fecha_fin:
            return self.env['portalgestor.asignacion.linea']
        lines = self.env['portalgestor.asignacion.linea'].search(
            [
                ('asignacion_id.usuario_id', 'in', usuarios.ids),
                ('fecha', '>=', self.fecha_inicio),
                ('fecha', '<=', self.fecha_fin),
            ],
            order='fecha asc, hora_inicio asc, hora_fin asc, id asc',
        )
        lines._recompute_falta_justificada_metrics()
        return lines

    def _get_report_payload_for_hogar_riesgo(self, hogar_riesgo):
        self.ensure_one()
        Usuario = self.env['usuarios.usuario']
        hogar_group = Usuario._get_hogar_riesgo_group(hogar_riesgo)
        if hogar_group and not self.env.user._can_manage_target_group(hogar_group):
            raise AccessError(_("No puedes generar el reporte de este hogar de riesgo."))

        usuarios = self._get_users_for_hogar_riesgo(hogar_riesgo)
        lines = self._get_assignment_lines_for_users(usuarios)
        minutes_by_user = {usuario.id: 0 for usuario in usuarios}
        for line in lines:
            usuario_id = line.asignacion_id.usuario_id.id
            if usuario_id in minutes_by_user:
                minutes_by_user[usuario_id] += line.minutos_computables or 0

        user_rows = []
        total_minutes = 0
        for usuario in usuarios:
            user_minutes = minutes_by_user.get(usuario.id, 0)
            total_minutes += user_minutes
            user_rows.append({
                'full_name': usuario._get_full_name(),
                'localidad_name': usuario.localidad_id.display_name or usuario.localidad_id.name or '',
                'hours_minutes': user_minutes,
                'hours_label': self._format_duration(user_minutes),
            })

        return {
            'hogar_riesgo': hogar_riesgo,
            'hogar_label': Usuario._get_hogar_riesgo_label(hogar_riesgo) or hogar_riesgo.upper(),
            'group_label': Usuario._get_group_ui_data(hogar_group).get('label', hogar_group or ''),
            'period_label': self._get_nombre_mes_anio(),
            'user_count': len(usuarios),
            'total_minutes': total_minutes,
            'total_hours_label': self._format_duration(total_minutes),
            'user_rows': user_rows,
        }

    def _get_single_report_filename(self):
        self.ensure_one()
        hogar_options = self._get_report_hogar_riesgo_options()
        if len(hogar_options) == 1:
            return f"{hogar_options[0][1]} ({self._get_nombre_mes_anio()})"
        return f"Hogares de Riesgo ({self._get_nombre_mes_anio()})"

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
        hogar_options = self._get_report_hogar_riesgo_options()
        report_action = self.env.ref('portalGestor.action_report_hogar_riesgo')
        if len(hogar_options) == 1:
            return report_action.with_context(single_hogar_riesgo=hogar_options[0][0]).report_action(self)

        file_entries = []
        for hogar_riesgo, hogar_label in hogar_options:
            pdf_content, _content_type = report_action.with_context(
                single_hogar_riesgo=hogar_riesgo
            )._render_qweb_pdf(report_action.id, self.ids)
            file_entries.append((
                f"{hogar_label} ({self._get_nombre_mes_anio()}).pdf",
                pdf_content,
            ))
        return self._build_zip_download_action(
            f"Hogares de Riesgo ({self._get_nombre_mes_anio()}).zip",
            file_entries,
        )
