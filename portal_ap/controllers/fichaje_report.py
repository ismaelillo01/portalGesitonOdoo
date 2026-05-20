# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import content_disposition, request


class PortalAPFichajeReportController(http.Controller):

    @http.route(
        '/portal_ap/fichajes/reporte_xlsx/<int:wizard_id>',
        type='http',
        auth='user',
        methods=['GET'],
    )
    def download_fichaje_report_xlsx(self, wizard_id, **kwargs):
        wizard = request.env['portal.ap.fichaje.report.wizard'].browse(wizard_id).exists()
        if not wizard:
            return request.not_found()

        wizard._check_report_access()
        content = wizard._generate_xlsx_content()
        filename = wizard._get_report_filename()
        return request.make_response(
            content,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename)),
            ],
        )
