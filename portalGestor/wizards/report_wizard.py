# -*- coding: utf-8 -*-
import base64
import calendar
import io
import zipfile
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

# Nombres de meses en español para el nombre de archivo y reporte
MESES_ES = {
    '1': 'Enero', '2': 'Febrero', '3': 'Marzo', '4': 'Abril',
    '5': 'Mayo', '6': 'Junio', '7': 'Julio', '8': 'Agosto',
    '9': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre',
}


class ReportWizard(models.TransientModel):
    _name = 'portalgestor.report.wizard'
    _description = 'Asistente de Reporte de Horario'

    exportar_todos = fields.Boolean(string='Exportar todos los APs del periodo', default=False)
    trabajador_ids = fields.Many2many('trabajadores.trabajador', string='APs')
    available_trabajador_ids = fields.Many2many(
        'trabajadores.trabajador',
        string='APs disponibles',
        compute='_compute_available_trabajador_ids',
    )

    mes = fields.Selection(
        selection=[
            ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'),
            ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
            ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'),
            ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
        ],
        string='Mes',
        required=True,
        default=lambda self: str(date.today().month),
    )
    anio = fields.Selection(
        selection='_selection_anios',
        string='Año',
        required=True,
        default=lambda self: str(date.today().year),
    )

    fecha_inicio = fields.Date(string='Fecha Inicio', compute='_compute_fechas')
    fecha_fin = fields.Date(string='Fecha Fin', compute='_compute_fechas')

    @api.model
    def _selection_anios(self):
        current_year = date.today().year
        return [(str(y), str(y)) for y in range(current_year - 2, current_year + 3)]

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

    @api.depends('mes', 'anio')
    def _compute_available_trabajador_ids(self):
        for record in self:
            record.available_trabajador_ids = record._get_available_trabajadores()

    def _is_current_user_portalgestor_report_admin(self):
        return self.env.user._get_gestor_management_scope() == 'admin'

    def _get_nombre_mes_anio(self):
        """Devuelve el string 'NombreMes Año', ej: 'Marzo 2026'."""
        return f"{MESES_ES.get(self.mes, '')} {self.anio}"

    def _get_owned_assignment_line_domain(self):
        self.ensure_one()
        domain = [
            ('fecha', '>=', self.fecha_inicio),
            ('fecha', '<=', self.fecha_fin),
            ('asignacion_id.confirmado', '=', True),
        ]
        if not self._is_current_user_portalgestor_report_admin():
            domain.append(('gestor_owner_id', '=', self.env.user.id))
        return domain

    def _get_available_trabajadores(self):
        self.ensure_one()
        Trabajador = self.env['trabajadores.trabajador']
        if not self.fecha_inicio or not self.fecha_fin:
            return Trabajador.browse()
        if self._is_current_user_portalgestor_report_admin():
            return Trabajador.search([('baja', '=', False)], order='name, id')

        owned_lines = self.env['portalgestor.asignacion.linea'].search(
            self._get_owned_assignment_line_domain(),
            order='fecha asc, hora_inicio asc, hora_fin asc, id asc',
        )
        trabajador_ids = sorted({line.trabajador_id.id for line in owned_lines if line.trabajador_id})
        if not trabajador_ids:
            return Trabajador.browse()
        return Trabajador.browse(trabajador_ids).exists().sorted(
            key=lambda trabajador: (trabajador.name or '', trabajador.id)
        )

    @api.onchange('mes', 'anio', 'exportar_todos')
    def _onchange_report_scope(self):
        for record in self:
            available_workers = record._get_available_trabajadores()
            if record.trabajador_ids:
                record.trabajador_ids = record.trabajador_ids & available_workers

    def _get_report_lines_for_worker(self, trabajador):
        self.ensure_one()
        domain = [('trabajador_id', '=', trabajador.id)] + self._get_owned_assignment_line_domain()
        lines = self.env['portalgestor.asignacion.linea'].search(
            domain,
            order='fecha asc, hora_inicio asc, hora_fin asc, id asc',
        )
        lines._recompute_festive_metrics()
        return lines

    def _get_report_payload_for_worker(self, trabajador):
        self.ensure_one()
        line_payloads = []
        total_computable_minutes = 0
        total_festive_minutes = 0
        for line in self._get_report_lines_for_worker(trabajador):
            breakdown = line._get_report_breakdown()
            total_computable_minutes += breakdown['computable_minutes']
            total_festive_minutes += breakdown['festive_minutes']
            line_payloads.append({
                'fecha_label': line.fecha.strftime('%d/%m/%Y') if line.fecha else '',
                'usuario_name': line.asignacion_id.usuario_id.display_name or line.asignacion_id.usuario_id.name,
                'hora_inicio': breakdown['hora_inicio_label'],
                'hora_fin': breakdown['hora_fin_label'],
                'horas_tramo_label': breakdown['duration_label'],
                'festive_label': breakdown['festive_label'],
                'festive_names': breakdown['festive_names'],
                'horas_festivas_label': breakdown['festive_hours_label'],
                'incidencia_label': breakdown['incidencia_label'],
                'motivo': breakdown['motivo'],
                'horas_no_trabajadas_label': breakdown['justified_label'],
                'horas_computables_label': breakdown['computable_label'],
            })

        return {
            'lines': line_payloads,
            'total_duration_label': self.env['portalgestor.asignacion.linea']._format_duration_minutes(
                total_computable_minutes
            ),
            'total_festive_label': self.env['portalgestor.asignacion.linea']._format_duration_minutes(
                total_festive_minutes
            ),
        }

    def _get_report_payload_for_worker(self, trabajador):
        self.ensure_one()
        line_payloads = []
        total_computable_minutes = 0
        total_festive_minutes = 0
        for line in self._get_report_lines_for_worker(trabajador):
            breakdown = line._get_report_breakdown()
            total_computable_minutes += breakdown['computable_minutes']
            total_festive_minutes += breakdown['festive_minutes']
            line_payloads.append({
                'fecha_label': line.fecha.strftime('%d/%m/%Y') if line.fecha else '',
                'usuario_name': line.asignacion_id.usuario_id.display_name or line.asignacion_id.usuario_id.name,
                'hora_inicio': breakdown['hora_inicio_label'],
                'hora_fin': breakdown['hora_fin_label'],
                'horas_tramo_label': breakdown['duration_label'],
                'festive_label': breakdown['festive_label'],
                'festive_names': breakdown['festive_names'],
                'horas_festivas_label': breakdown['festive_hours_label'],
                'incidencia_label': breakdown['incidencia_label'],
                'motivo': breakdown['motivo'],
                'horas_no_trabajadas_label': breakdown['justified_label'],
                'horas_computables_label': breakdown['computable_label'],
            })

        return {
            'lines': line_payloads,
            'total_duration_label': self.env['portalgestor.asignacion.linea']._format_duration_minutes(
                total_computable_minutes
            ),
            'total_festive_label': self.env['portalgestor.asignacion.linea']._format_duration_minutes(
                total_festive_minutes
            ),
        }

    def _get_selected_workers(self):
        self.ensure_one()
        if self.exportar_todos:
            if self._is_current_user_portalgestor_report_admin():
                trabajadores = self.env['trabajadores.trabajador'].search(
                    [('baja', '=', False)],
                    order='name, id',
                )
            else:
                trabajadores = self._get_available_trabajadores()
            if not trabajadores:
                raise ValidationError(_("No hay APs disponibles para imprimir en este periodo."))
            return trabajadores

        trabajadores = self.trabajador_ids.sorted(key=lambda trabajador: (trabajador.name or '', trabajador.id))
        if not trabajadores:
            raise ValidationError(_("No hay APs seleccionados para imprimir."))

        if self._is_current_user_portalgestor_report_admin():
            return trabajadores

        available_workers = self._get_available_trabajadores()
        forbidden_workers = trabajadores - available_workers
        if forbidden_workers:
            raise AccessError(_("Solo puedes sacar PDF de horarios asignados por ti."))
        return trabajadores

    def action_print_report(self):
        trabajadores = self._get_selected_workers()

        if len(trabajadores) == 1:
            self.trabajador_ids = trabajadores
            return self.env.ref('portalGestor.action_report_horario_trabajador').report_action(self)

        nombre_periodo = self._get_nombre_mes_anio()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            report_action = self.env.ref('portalGestor.action_report_horario_trabajador')

            for trabajador in trabajadores:
                self.trabajador_ids = [trabajador.id]
                pdf_content, _ = report_action._render_qweb_pdf(report_action.id, self.ids)
                filename = f"{trabajador.name} ({nombre_periodo}).pdf"
                zip_file.writestr(filename, pdf_content)

        zip_buffer.seek(0)
        zip_bytes = zip_buffer.read()

        attachment = self.env['ir.attachment'].create({
            'name': f'Horarios ({nombre_periodo}).zip',
            'type': 'binary',
            'datas': base64.b64encode(zip_bytes),
            'mimetype': 'application/zip',
            'public': False,
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
