# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.http import request


class PortalAPController(http.Controller):

    def _service(self):
        return request.env['portal.ap.service'].sudo()

    def _get_session_worker(self):
        worker_id = request.session.get('portal_ap_trabajador_id')
        if not worker_id:
            return request.env['trabajadores.trabajador'].sudo().browse()

        worker = request.env['trabajadores.trabajador'].sudo().browse(int(worker_id)).exists()
        if not worker or worker.baja:
            request.session.pop('portal_ap_trabajador_id', None)
            return request.env['trabajadores.trabajador'].sudo().browse()
        return worker

    def _render_login(self, error=False, dni_nie=''):
        return request.render('portal_ap.login', {
            'error': error,
            'dni_nie': dni_nie or '',
        })

    @http.route(['/ap'], type='http', auth='public', methods=['GET'], sitemap=False)
    def portal_ap_login(self, **kwargs):
        if self._get_session_worker():
            return request.redirect('/ap/horario')
        return self._render_login()

    @http.route(['/ap/login'], type='http', auth='public', methods=['POST'], csrf=True, sitemap=False)
    def portal_ap_login_submit(self, **post):
        dni_nie = post.get('dni_nie') or ''
        worker, error_code = self._service()._find_worker_by_dni(dni_nie)
        if error_code:
            if error_code == 'duplicate':
                error = 'No se puede iniciar sesion con este DNI/NIE. Contacte con administracion.'
            else:
                error = 'No se ha encontrado ningun AP con ese DNI/NIE.'
            return self._render_login(error=error, dni_nie=dni_nie)

        request.session['portal_ap_trabajador_id'] = worker.id
        return request.redirect('/ap/horario')

    @http.route([
        '/ap/horario',
        '/ap/horario/<int:year>/<int:month>',
    ], type='http', auth='public', methods=['GET'], sitemap=False)
    def portal_ap_schedule(self, year=None, month=None, **kwargs):
        worker = self._get_session_worker()
        if not worker:
            return request.redirect('/ap')

        today = fields.Date.context_today(request.env['portal.ap.service'])
        year = year or today.year
        month = month or today.month
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            return request.redirect('/ap/horario/%s/%s' % (today.year, today.month))

        calendar_data = self._service()._get_worker_month_calendar(worker, year, month)
        return request.render('portal_ap.schedule', calendar_data)

    @http.route(['/ap/logout'], type='http', auth='public', methods=['POST'], csrf=True, sitemap=False)
    def portal_ap_logout(self, **post):
        request.session.pop('portal_ap_trabajador_id', None)
        return request.redirect('/ap')
