import base64
import calendar
import io
import zipfile
from datetime import date
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# Nombres de meses en español para el nombre de archivo y reporte
MESES_ES = {
    '1': 'Enero', '2': 'Febrero', '3': 'Marzo', '4': 'Abril',
    '5': 'Mayo', '6': 'Junio', '7': 'Julio', '8': 'Agosto',
    '9': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre',
}


class ReportWizard(models.TransientModel):
    _name = 'portalgestor.report.wizard'
    _description = 'Asistente de Reporte de Horario'

    exportar_todos = fields.Boolean(string='Exportar Todos los Trabajadores Activos', default=False)
    trabajador_ids = fields.Many2many('trabajadores.trabajador', string='Trabajadores')

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

    # Campos computados que reemplazan los antiguos fecha_inicio / fecha_fin
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
                m = int(record.mes)
                y = int(record.anio)
                ultimo_dia = calendar.monthrange(y, m)[1]  # maneja bisiestos
                record.fecha_inicio = date(y, m, 1)
                record.fecha_fin = date(y, m, ultimo_dia)
            else:
                record.fecha_inicio = False
                record.fecha_fin = False

    def _get_nombre_mes_anio(self):
        """Devuelve el string 'NombreMes Año', ej: 'Marzo 2026'."""
        return f"{MESES_ES.get(self.mes, '')} {self.anio}"

    def action_print_report(self):
        # Determinar los trabajadores a exportar
        if self.exportar_todos:
            domain = [('baja', '=', False)]
            user = self.env.user
            if user.has_group('gestores.group_gestores_agusto') and not user.has_group('gestores.group_gestores_intecum') and not user.has_group('gestores.group_gestores_administrador'):
                domain.append(('grupo', '=', 'agusto'))
            trabajadores = self.env['trabajadores.trabajador'].search(domain)
        else:
            trabajadores = self.trabajador_ids

        if not trabajadores:
            raise ValidationError(_("No hay trabajadores seleccionados para imprimir."))

        # Si es un único trabajador, usamos el flujo nativo de PDF simple
        if len(trabajadores) == 1:
            self.trabajador_ids = trabajadores
            return self.env.ref('portalGestor.action_report_horario_trabajador').report_action(self)

        # Si son varios, generamos un ZIP en memoria
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
